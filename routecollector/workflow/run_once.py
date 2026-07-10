"""
Single-run RouteCollector workflow.

This module executes a complete data collection and route generation cycle.
It installs a generated BIRD configuration only when its content changed,
checks the resulting BIRD configuration, but does not reload BIRD.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from routecollector.core.repository import Repository
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import BirdConfigInstaller, BirdControl
from routecollector.parser.service_config import ServiceConfigSync
from routecollector.planner.planner import RoutePlanner
from routecollector.resolver.resolver import DnsResolver


class RunOnceError(RuntimeError):
    """Run-once workflow error."""


@dataclass(slots=True, frozen=True)
class RunOnceResult:
    """Result of a complete RouteCollector cycle."""

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


class RunOnceWorkflow:
    """Execute one complete RouteCollector update cycle."""

    def __init__(
        self,
        repository: Repository,
        services_dir: Path,
        generated_config: Path,
        installed_config: Path,
        main_bird_config: Path,
        min_confidence_ipv4: int = 10,
        min_confidence_ipv6: int = 10,
    ) -> None:
        self._repository = repository
        self._services_dir = services_dir
        self._generated_config = generated_config
        self._installed_config = installed_config
        self._main_bird_config = main_bird_config
        self._min_confidence_ipv4 = min_confidence_ipv4
        self._min_confidence_ipv6 = min_confidence_ipv6

    def run(self, service_name: str | None = None) -> RunOnceResult:
        """Execute a complete update cycle without reloading BIRD."""

        sync = ServiceConfigSync(
            repository=self._repository,
            services_dir=self._services_dir,
        )
        services_synced, domains_synced = sync.sync()

        resolver = DnsResolver(self._repository)
        domains_resolved, observations_stored = resolver.resolve_all(
            service_name
        )

        route_stats_built = self._repository.rebuild_route_stats()

        planner = RoutePlanner(
            repository=self._repository,
            min_confidence_ipv4=self._min_confidence_ipv4,
            min_confidence_ipv6=self._min_confidence_ipv6,
        )
        routes = planner.build_plan()

        if not routes:
            raise RunOnceError(
                "Route plan is empty; refusing to replace BIRD configuration"
            )

        export_result = BirdExporter(
            self._generated_config
        ).export(routes)

        install_result = BirdConfigInstaller(
            source_file=export_result.path,
            target_file=self._installed_config,
            main_config=self._main_bird_config,
        ).install()

        bird_check_output = BirdControl().configure_check()

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
        )
