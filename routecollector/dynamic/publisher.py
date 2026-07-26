"""
Fast publication path for dynamic DNS observations.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
        """Return route statistics for the planner."""


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


class DynamicPublisher:
    """
    Publish a route plan without source sync or DNS resolution.

    The publisher rebuilds statistics from already stored observations,
    creates the complete route plan and safely updates BIRD.
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
        planner: DynamicPlanner | None = None,
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
        self._generated_config = generated_config
        self._installed_config = installed_config
        self._main_bird_config = main_bird_config
        self._ipv4_prefix = ipv4_prefix
        self._ipv6_prefix = ipv6_prefix

        self._planner = planner or RoutePlanner(
            repository=repository,  # type: ignore[arg-type]
            min_confidence_ipv4=min_confidence_ipv4,
            min_confidence_ipv6=min_confidence_ipv6,
            max_age_days=max_age_days,
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

    def publish(self) -> DynamicPublishResult:
        """Rebuild the route plan and safely publish it to BIRD."""

        route_stats_built = (
            self._repository.rebuild_route_stats(
                ipv4_prefix=self._ipv4_prefix,
                ipv6_prefix=self._ipv6_prefix,
            )
        )

        routes = self._planner.build_plan()

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
        )
