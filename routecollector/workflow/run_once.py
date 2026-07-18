"""
Single-run RouteCollector workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from routecollector.core.database import Database
from routecollector.core.repository import Repository
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import (
    BirdConfigInstaller,
    BirdControl,
    BirdControlError,
)
from routecollector.history.cycle_history import (
    CycleHistoryStore,
    NewCycleHistoryEntry,
)
from routecollector.history.plan_snapshot import PlanSnapshotStore
from routecollector.planner.planner import PlannedRoute, RoutePlanner
from routecollector.resolver.resolver import DnsResolver
from routecollector.sources.service_source_sync import (
    ServiceSourceSync,
    SourceSyncResult,
)


class RunOnceError(RuntimeError):
    """Workflow execution error."""


@dataclass(slots=True, frozen=True)
class RunOnceResult:
    """Result of one complete RouteCollector cycle."""

    sync_result: SourceSyncResult
    services_synced: int
    domains_synced: int
    domains_resolved: int
    observations_stored: int
    route_stats_built: int
    planned_routes: int
    routes_added: int
    routes_removed: int
    generated_config: Path
    generated_changed: bool
    installed_config: Path | None
    installed_changed: bool
    bird_check_output: str | None
    bird_reload_output: str | None
    bird_reloaded: bool
    rollback_performed: bool
    duration_seconds: float
    dry_run: bool


class RunOnceWorkflow:
    """Execute one complete RouteCollector cycle."""

    def __init__(
        self,
        repository: Repository,
        database: Database,
        services_dir: Path,
        generated_config: Path,
        installed_config: Path,
        main_bird_config: Path,
        min_confidence_ipv4: int = 10,
        min_confidence_ipv6: int = 10,
        max_age_days: int = 30,
        enable_ipv6: bool = False,
        snapshot_directory: Path = Path("state/plans"),
        dry_run_config: Path = Path(
            "state/dry-run/routecollector.conf"
        ),
    ) -> None:
        if max_age_days <= 0:
            raise ValueError(
                "Route maximum age must be greater than zero"
            )

        self._repository = repository
        self._database = database
        self._services_dir = services_dir
        self._generated_config = generated_config
        self._installed_config = installed_config
        self._main_bird_config = main_bird_config
        self._min_confidence_ipv4 = min_confidence_ipv4
        self._min_confidence_ipv6 = min_confidence_ipv6
        self._max_age_days = max_age_days
        self._enable_ipv6 = enable_ipv6
        self._snapshot_directory = snapshot_directory
        self._dry_run_config = dry_run_config

    def run(
        self,
        service_name: str | None = None,
        dry_run: bool = False,
    ) -> RunOnceResult:
        """Execute a complete update cycle."""

        started_at = datetime.now()

        sync_result = ServiceSourceSync(
            repository=self._repository,
            services_dir=self._services_dir,
        ).sync()

        services_synced = sync_result.service_count
        domains_synced = sync_result.domain_count

        domains_resolved, observations_stored = DnsResolver(
            self._repository,
            enable_ipv6=self._enable_ipv6,
        ).resolve_all(service_name)

        route_stats_built = self._repository.rebuild_route_stats()

        routes = RoutePlanner(
            repository=self._repository,
            min_confidence_ipv4=self._min_confidence_ipv4,
            min_confidence_ipv6=self._min_confidence_ipv6,
            max_age_days=self._max_age_days,
            enable_ipv6=self._enable_ipv6,
        ).build_plan()

        if not routes:
            raise RunOnceError(
                "Route plan is empty; refusing to replace "
                "BIRD configuration"
            )

        if dry_run:
            return self._complete_dry_run(
                routes=routes,
                started_at=started_at,
                sync_result=sync_result,
                services_synced=services_synced,
                domains_synced=domains_synced,
                domains_resolved=domains_resolved,
                observations_stored=observations_stored,
                route_stats_built=route_stats_built,
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

            installer.remove_backup(
                install_result.backup_path
            )

        except BirdControlError as exc:
            if install_result.changed:
                installer.rollback(
                    install_result.backup_path
                )
                rollback_performed = True

                try:
                    bird.configure_check()
                    bird.configure()
                except BirdControlError as rollback_exc:
                    raise RunOnceError(
                        "New BIRD configuration failed and "
                        "rollback could not be applied: "
                        f"{rollback_exc}"
                    ) from rollback_exc

            raise RunOnceError(
                "New BIRD configuration rejected; "
                f"rollback completed: {exc}"
            ) from exc

        snapshot_store = PlanSnapshotStore(
            self._snapshot_directory
        )
        snapshot_store.save(routes)

        changes = snapshot_store.changes()
        routes_added = (
            len(changes.added)
            if changes is not None
            else 0
        )
        routes_removed = (
            len(changes.removed)
            if changes is not None
            else 0
        )

        completed_at = datetime.now()

        history_entry = NewCycleHistoryEntry(
            started_at=started_at,
            completed_at=completed_at,
            service_name=service_name,
            services_synced=services_synced,
            domains_synced=domains_synced,
            domains_resolved=domains_resolved,
            observations_stored=observations_stored,
            route_stats_built=route_stats_built,
            planned_routes=len(routes),
            routes_added=routes_added,
            routes_removed=routes_removed,
            generated_changed=export_result.changed,
            installed_changed=install_result.changed,
            bird_reloaded=bird_reloaded,
        )
        CycleHistoryStore(
            self._database
        ).add(history_entry)

        return RunOnceResult(
            sync_result=sync_result,
            services_synced=services_synced,
            domains_synced=domains_synced,
            domains_resolved=domains_resolved,
            observations_stored=observations_stored,
            route_stats_built=route_stats_built,
            planned_routes=len(routes),
            routes_added=routes_added,
            routes_removed=routes_removed,
            generated_config=export_result.path,
            generated_changed=export_result.changed,
            installed_config=install_result.path,
            installed_changed=install_result.changed,
            bird_check_output=bird_check_output,
            bird_reload_output=bird_reload_output,
            bird_reloaded=bird_reloaded,
            rollback_performed=rollback_performed,
            duration_seconds=history_entry.duration_seconds,
            dry_run=False,
        )

    def _complete_dry_run(
        self,
        routes: Iterable[PlannedRoute],
        started_at: datetime,
        sync_result: SourceSyncResult,
        services_synced: int,
        domains_synced: int,
        domains_resolved: int,
        observations_stored: int,
        route_stats_built: int,
    ) -> RunOnceResult:
        """Generate preview output without publishing routes."""

        route_list = list(routes)
        export_result = BirdExporter(
            self._dry_run_config
        ).export(route_list)

        routes_added, routes_removed = (
            self._compare_with_latest_snapshot(route_list)
        )

        completed_at = datetime.now()
        duration_seconds = max(
            0.0,
            (completed_at - started_at).total_seconds(),
        )

        return RunOnceResult(
            sync_result=sync_result,
            services_synced=services_synced,
            domains_synced=domains_synced,
            domains_resolved=domains_resolved,
            observations_stored=observations_stored,
            route_stats_built=route_stats_built,
            planned_routes=len(route_list),
            routes_added=routes_added,
            routes_removed=routes_removed,
            generated_config=export_result.path,
            generated_changed=export_result.changed,
            installed_config=None,
            installed_changed=False,
            bird_check_output=None,
            bird_reload_output=None,
            bird_reloaded=False,
            rollback_performed=False,
            duration_seconds=duration_seconds,
            dry_run=True,
        )

    def _compare_with_latest_snapshot(
        self,
        routes: Iterable[PlannedRoute],
    ) -> tuple[int, int]:
        """Compare preview routes with latest published snapshot."""

        latest = PlanSnapshotStore(
            self._snapshot_directory
        ).latest()

        if latest is None:
            return 0, 0

        previous_keys = {
            (route.family, route.prefix)
            for route in latest.routes
        }
        current_keys = {
            (route.family, route.prefix)
            for route in routes
        }

        return (
            len(current_keys - previous_keys),
            len(previous_keys - current_keys),
        )
