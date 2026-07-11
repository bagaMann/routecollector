"""
Single-run RouteCollector workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from routecollector.core.repository import Repository
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import (
    BirdConfigInstaller,
    BirdControl,
    BirdControlError,
)
from routecollector.parser.service_config import ServiceConfigSync
from routecollector.planner.planner import RoutePlanner
from routecollector.resolver.resolver import DnsResolver


class RunOnceError(RuntimeError):
    """Workflow execution error."""


@dataclass(slots=True, frozen=True)
class RunOnceResult:
    """Result of one complete RouteCollector cycle."""

    services_synced: int
    domains_synced: int
    domains_resolved: int
    observations_stored: int
    route_stats_built: int
    planned_routes: int

    generated_config: Path
    generated_changed: bool

    installed_config: Path
    installed_changed: bool

    bird_check_output: str
    bird_reload_output: str | None

    bird_reloaded: bool
    rollback_performed: bool


class RunOnceWorkflow:
    """Execute one complete RouteCollector cycle."""

    def __init__(
        self,
        repository: Repository,
        services_dir: Path,
        generated_config: Path,
        installed_config: Path,
        main_bird_config: Path,
        min_confidence_ipv4: int = 10,
        min_confidence_ipv6: int = 10,
        max_age_days: int = 30,
    ) -> None:
        if max_age_days <= 0:
            raise ValueError("Route maximum age must be greater than zero")

        self._repository = repository
        self._services_dir = services_dir
        self._generated_config = generated_config
        self._installed_config = installed_config
        self._main_bird_config = main_bird_config
        self._min_confidence_ipv4 = min_confidence_ipv4
        self._min_confidence_ipv6 = min_confidence_ipv6
        self._max_age_days = max_age_days

    def run(
        self,
        service_name: str | None = None,
    ) -> RunOnceResult:
        """Execute a complete update cycle."""

        services_synced, domains_synced = ServiceConfigSync(
            repository=self._repository,
            services_dir=self._services_dir,
        ).sync()

        domains_resolved, observations_stored = DnsResolver(
            self._repository
        ).resolve_all(service_name)

        route_stats_built = self._repository.rebuild_route_stats()

        routes = RoutePlanner(
            repository=self._repository,
            min_confidence_ipv4=self._min_confidence_ipv4,
            min_confidence_ipv6=self._min_confidence_ipv6,
            max_age_days=self._max_age_days,
        ).build_plan()

        if not routes:
            raise RunOnceError(
                "Route plan is empty; refusing to replace BIRD configuration"
            )

        export_result = BirdExporter(
            self._generated_config
        ).export(routes)

        installer = BirdConfigInstaller(
            source_file=export_result.path,
            target_file=self._installed_config,
            main_config=self._main_bird_config,
        )

        install_result = installer.install()
        bird = BirdControl()

        bird_check_output = ""
        bird_reload_output: str | None = None
        bird_reloaded = False
        rollback_performed = False

        try:
            bird_check_output = bird.configure_check()

            if install_result.changed:
                bird_reload_output = bird.configure()
                bird_reloaded = True
                installer.remove_backup(install_result.backup_path)

        except BirdControlError as exc:
            if install_result.changed:
                installer.rollback(install_result.backup_path)
                rollback_performed = True

                try:
                    bird.configure_check()
                    bird.configure()
                except BirdControlError as rollback_exc:
                    raise RunOnceError(
                        "New BIRD configuration failed and rollback "
                        f"could not be applied: {rollback_exc}"
                    ) from rollback_exc

            raise RunOnceError(
                f"New BIRD configuration rejected; rollback completed: {exc}"
            ) from exc

        return RunOnceResult(
            services_synced=services_synced,
            domains_synced=domains_synced,
            domains_resolved=domains_resolved,
            observations_stored=observations_stored,
            route_stats_built=route_stats_built,
            planned_routes=len(routes),
            generated_config=export_result.path,
            generated_changed=export_result.changed,
            installed_config=install_result.path,
            installed_changed=install_result.changed,
            bird_check_output=bird_check_output,
            bird_reload_output=bird_reload_output,
            bird_reloaded=bird_reloaded,
            rollback_performed=rollback_performed,
        )
