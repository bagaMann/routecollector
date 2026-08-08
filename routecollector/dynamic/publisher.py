"""
Fast publication path for dynamic DNS observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterable, Protocol

from routecollector.dynamic.fast_publish import DynamicFastPublishPolicy
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import (
    BirdConfigInstaller,
    BirdControl,
    BirdControlError,
)
from routecollector.planner.planner import PlannedRoute, RoutePlanner


class DynamicPublishError(RuntimeError):
    """Dynamic route publication failed."""


class DynamicPublishRepository(Protocol):
    def rebuild_route_stats(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> int:
        ...

    def list_route_stats(self) -> list[object]:
        ...


class DynamicPlanner(Protocol):
    def build_plan(self) -> list[PlannedRoute]:
        ...


class DynamicExporter(Protocol):
    def export(
        self,
        routes: list[PlannedRoute],
    ) -> object:
        ...


class DynamicInstaller(Protocol):
    def install(self) -> object:
        ...

    def rollback(
        self,
        backup_path: Path | None,
    ) -> None:
        ...

    def remove_backup(
        self,
        backup_path: Path | None,
    ) -> None:
        ...


class DynamicBirdControl(Protocol):
    def configure_check(self) -> str:
        ...

    def configure(self) -> str:
        ...


@dataclass(slots=True, frozen=True)
class DynamicPublishResult:
    route_stats_built: int
    planned_routes: int
    generated_config: Path
    generated_changed: bool
    installed_config: Path
    installed_changed: bool
    bird_checked: bool
    bird_reloaded: bool
    rollback_performed: bool
    dynamic_requested_prefixes: tuple[str, ...] = ()
    dynamic_published_prefixes: tuple[str, ...] = ()
    dynamic_rejected_prefixes: tuple[str, ...] = ()


class DynamicPublisher:
    """Safely publish normal and fast dynamic route plans."""

    def __init__(
        self,
        repository: DynamicPublishRepository,
        *,
        generated_config: Path,
        installed_config: Path,
        main_bird_config: Path,
        min_confidence_ipv4: int = 60,
        min_confidence_ipv6: int = 60,
        max_age_days: int = 30,
        enable_ipv6: bool = False,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
        dynamic_min_confidence_ipv4: int = 25,
        dynamic_min_confidence_ipv6: int = 25,
        dynamic_min_source_trust: int = 50,
        planner: DynamicPlanner | None = None,
        fast_policy: DynamicFastPublishPolicy | None = None,
        exporter: DynamicExporter | None = None,
        installer: DynamicInstaller | None = None,
        bird: DynamicBirdControl | None = None,
    ) -> None:
        if not 0 <= min_confidence_ipv4 <= 100:
            raise ValueError(
                "IPv4 publication threshold must be between 0 and 100"
            )
        if not 0 <= min_confidence_ipv6 <= 100:
            raise ValueError(
                "IPv6 publication threshold must be between 0 and 100"
            )
        if max_age_days <= 0:
            raise ValueError(
                "Route maximum age must be greater than zero"
            )
        if not 0 <= ipv4_prefix <= 32:
            raise ValueError(
                "IPv4 prefix length must be between 0 and 32"
            )
        if not 0 <= ipv6_prefix <= 128:
            raise ValueError(
                "IPv6 prefix length must be between 0 and 128"
            )

        self._repository = repository
        self._ipv4_prefix = ipv4_prefix
        self._ipv6_prefix = ipv6_prefix
        self._lock = Lock()

        self._planner = planner or RoutePlanner(
            repository=repository,  # type: ignore[arg-type]
            min_confidence_ipv4=min_confidence_ipv4,
            min_confidence_ipv6=min_confidence_ipv6,
            max_age_days=max_age_days,
            enable_ipv6=enable_ipv6,
        )

        self._fast_policy = fast_policy or DynamicFastPublishPolicy(
            min_confidence_ipv4=dynamic_min_confidence_ipv4,
            min_confidence_ipv6=dynamic_min_confidence_ipv6,
            min_source_trust=dynamic_min_source_trust,
            enable_ipv6=enable_ipv6,
        )

        self._exporter = exporter or BirdExporter(
            generated_config
        )
        self._installer = installer or BirdConfigInstaller(
            source_file=generated_config,
            target_file=installed_config,
            main_config=main_bird_config,
        )
        self._bird = bird or BirdControl()

    def publish(
        self,
        required_prefixes: Iterable[str] = (),
    ) -> DynamicPublishResult:
        """Serialize and execute one complete publication cycle."""

        requested = tuple(required_prefixes)

        with self._lock:
            return self._publish_locked(
                requested
            )

    def _publish_locked(
        self,
        required_prefixes: tuple[str, ...],
    ) -> DynamicPublishResult:
        route_stats_built = (
            self._repository.rebuild_route_stats(
                ipv4_prefix=self._ipv4_prefix,
                ipv6_prefix=self._ipv6_prefix,
            )
        )

        base_routes = self._planner.build_plan()

        fast_result = self._fast_policy.augment(
            base_routes=base_routes,
            route_stats=self._repository.list_route_stats(),
            required_prefixes=required_prefixes,
        )
        routes = list(fast_result.routes)

        if not routes:
            raise DynamicPublishError(
                "Dynamic route plan is empty; refusing "
                "to replace BIRD configuration"
            )

        export_result = self._exporter.export(routes)
        install_result = self._installer.install()

        bird_reloaded = False
        rollback_performed = False

        try:
            self._bird.configure_check()

            if install_result.changed:
                self._bird.configure()
                bird_reloaded = True

            self._installer.remove_backup(
                install_result.backup_path
            )

        except BirdControlError as exc:
            if install_result.changed:
                self._installer.rollback(
                    install_result.backup_path
                )
                rollback_performed = True

                try:
                    self._bird.configure_check()
                    self._bird.configure()
                except BirdControlError as rollback_exc:
                    raise DynamicPublishError(
                        "Dynamic BIRD configuration failed "
                        "and rollback could not be applied: "
                        f"{rollback_exc}"
                    ) from rollback_exc

            raise DynamicPublishError(
                "Dynamic BIRD configuration rejected; "
                f"rollback completed: {exc}"
            ) from exc

        return DynamicPublishResult(
            route_stats_built=route_stats_built,
            planned_routes=len(routes),
            generated_config=export_result.path,
            generated_changed=export_result.changed,
            installed_config=install_result.path,
            installed_changed=install_result.changed,
            bird_checked=True,
            bird_reloaded=bird_reloaded,
            rollback_performed=rollback_performed,
            dynamic_requested_prefixes=(
                fast_result.requested_prefixes
            ),
            dynamic_published_prefixes=(
                fast_result.accepted_prefixes
            ),
            dynamic_rejected_prefixes=(
                fast_result.rejected_prefixes
            ),
        )
