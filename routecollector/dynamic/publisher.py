"""
Fast publication path for dynamic DNS observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from routecollector.dynamic.fast_publish import (
    DynamicFastPublishPolicy,
)
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import (
    BirdConfigInstaller,
    BirdControl,
    BirdControlError,
)
from routecollector.planner.planner import (
    PlannedRoute,
    RoutePlanner,
)


class DynamicPublishError(RuntimeError):
    """Dynamic route publication failed."""


class DynamicPublishRepository(Protocol):
    """Repository operations required by dynamic publication."""

    def rebuild_route_stats(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> int:
        """Rebuild route statistics."""

    def list_route_stats(self) -> list[object]:
        """Return route statistics for the planner and fast policy."""


class DynamicPlanner(Protocol):
    """Route planner interface used by the publisher."""

    def build_plan(self) -> list[PlannedRoute]:
        """Build complete publishable route plan."""


class DynamicExporter(Protocol):
    """BIRD exporter interface used by the publisher."""

    def export(
        self,
        routes: list[PlannedRoute],
    ) -> object:
        """Export route plan."""


class DynamicInstaller(Protocol):
    """BIRD configuration installer interface."""

    def install(self) -> object:
        """Install generated configuration."""

    def rollback(
        self,
        backup_path: Path | None,
    ) -> None:
        """Restore previous configuration."""

    def remove_backup(
        self,
        backup_path: Path | None,
    ) -> None:
        """Remove successful backup."""


class DynamicBirdControl(Protocol):
    """BIRD control interface."""

    def configure_check(self) -> str:
        """Validate installed BIRD configuration."""

    def configure(self) -> str:
        """Reload BIRD configuration."""


@dataclass(slots=True, frozen=True)
class DynamicPublishResult:
    """Result of one dynamic publication cycle."""

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
    """
    Publish a route plan without source sync or DNS resolution.

    The normal planner remains authoritative for ordinary routes. Prefixes
    explicitly supplied by the matched dynamic-DNS path may additionally
    use the conservative fast-publication policy.
    """

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
        """Rebuild, augment and safely publish the route plan."""

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
