"""
Command line interface for RouteCollector.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from time import monotonic
from typing import Sequence

from routecollector import __version__
from routecollector.core.application import Application
from routecollector.core.version import get_version
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import BirdConfigInstaller, BirdControl
from routecollector.history.cycle_history import CycleHistoryStore
from routecollector.history.plan_snapshot import PlanSnapshotStore
from routecollector.sources.service_source_sync import ServiceSourceSync
from routecollector.sources.status import collect_source_status
from routecollector.planner.planner import PlannedRoute, RoutePlanner
from routecollector.resolver.resolver import DnsResolver
from routecollector.workflow.daemon import (
    DaemonConfig,
    RouteCollectorDaemon,
)
from routecollector.workflow.run_once import RunOnceWorkflow


DEFAULT_CONFIG = Path("config/config.yaml")
DEFAULT_SERVICES_DIR = Path("config/services")
DEFAULT_BIRD_OUTPUT = Path("bird/routecollector.conf")
DEFAULT_BIRD_TARGET = Path("/etc/bird/routecollector.conf")
DEFAULT_BIRD_MAIN_CONFIG = Path("/etc/bird/bird.conf")
DEFAULT_DAEMON_LOCK = Path("state/routecollector.lock")
DEFAULT_PLAN_SNAPSHOTS = Path("state/plans")
DEFAULT_DAEMON_INTERVAL = 1800
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_MIN_PUBLISH_SCORE_IPV4 = 60
DEFAULT_MIN_PUBLISH_SCORE_IPV6 = 60


def add_route_policy_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    """Add route publication policy arguments."""

    parser.add_argument(
        "--min-confidence-ipv4",
        type=int,
        default=DEFAULT_MIN_PUBLISH_SCORE_IPV4,
        help="Minimum publish score for IPv4 routes",
    )
    parser.add_argument(
        "--min-confidence-ipv6",
        type=int,
        default=DEFAULT_MIN_PUBLISH_SCORE_IPV6,
        help="Minimum publish score for IPv6 routes",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help="Maximum route age in days",
    )
    parser.add_argument(
        "--enable-ipv6",
        action="store_true",
        help="Resolve and publish IPv6 routes",
    )

def build_parser() -> argparse.ArgumentParser:
    """Build command line parser."""

    parser = argparse.ArgumentParser(
        prog="routecollector",
        description="Dynamic BGP Route Collector",
    )

    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG,
        type=Path,
        help="Path to configuration file",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational log messages",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "version",
        help="Show version information",
    )
    subparsers.add_parser(
        "status",
        help="Show application status",
    )
    subparsers.add_parser(
        "init",
        help="Initialize RouteCollector state",
    )
    subparsers.add_parser(
        "sync",
        help="Synchronize service configuration",
    )
    subparsers.add_parser(
        "sources",
        help="Show source plugins and configured usage",
    )
    subparsers.add_parser(
        "plugin-info",
        help="Show detailed source plugin metadata",
    )

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Resolve configured domains",
    )
    resolve_parser.add_argument(
        "service",
        nargs="?",
        default=None,
        help="Optional service name",
    )
    resolve_parser.add_argument(
        "--enable-ipv6",
        action="store_true",
        help="Resolve IPv6 AAAA records",
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build route plan from statistics",
    )
    add_route_policy_arguments(plan_parser)

    subparsers.add_parser(
        "stats",
        help="Rebuild and show route statistics",
    )
    subparsers.add_parser(
        "changes",
        help="Show changes between the latest route plans",
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Show successful RouteCollector cycle history",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of cycles to display",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="Export route plan to BIRD",
    )
    add_route_policy_arguments(export_parser)

    subparsers.add_parser(
        "bird-check",
        help="Check BIRD configuration",
    )
    subparsers.add_parser(
        "install-bird-config",
        help="Install generated RouteCollector BIRD config",
    )
    subparsers.add_parser(
        "bird-reload",
        help="Apply BIRD configuration",
    )

    run_once_parser = subparsers.add_parser(
        "run-once",
        help="Run one complete update cycle",
    )
    run_once_parser.add_argument(
        "service",
        nargs="?",
        default=None,
        help="Optional service name",
    )
    run_once_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Build a preview without installing or reloading "
            "BIRD configuration"
        ),
    )
    add_route_policy_arguments(run_once_parser)

    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Run RouteCollector continuously",
    )
    daemon_parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_DAEMON_INTERVAL,
        help="Seconds between update cycles",
    )
    daemon_parser.add_argument(
        "--service",
        default=None,
        help="Optional service name",
    )
    daemon_parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_DAEMON_LOCK,
        help="Daemon process lock file",
    )
    add_route_policy_arguments(daemon_parser)

    return parser


def get_app(config_path: Path) -> Application:
    """Create initialized application."""

    app = Application(config_path)
    app.initialize()

    if app.repository is None:
        raise RuntimeError("Repository is not initialized")

    return app


def build_workflow(
    app: Application,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
    max_age_days: int,
    enable_ipv6: bool,
) -> RunOnceWorkflow:
    """Build complete RouteCollector workflow."""

    if app.repository is None:
        raise RuntimeError("Repository is not initialized")

    if app.database is None:
        raise RuntimeError("Database is not initialized")

    return RunOnceWorkflow(
        repository=app.repository,
        database=app.database,
        services_dir=DEFAULT_SERVICES_DIR,
        generated_config=DEFAULT_BIRD_OUTPUT,
        installed_config=DEFAULT_BIRD_TARGET,
        main_bird_config=DEFAULT_BIRD_MAIN_CONFIG,
        min_confidence_ipv4=min_confidence_ipv4,
        min_confidence_ipv6=min_confidence_ipv6,
        max_age_days=max_age_days,
        enable_ipv6=enable_ipv6,
    )


def build_route_plan(
    app: Application,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
    max_age_days: int,
    enable_ipv6: bool,
) -> list[PlannedRoute]:
    """Build route plan for initialized application."""

    if app.repository is None:
        raise RuntimeError("Repository is not initialized")

    return RoutePlanner(
        repository=app.repository,
        min_confidence_ipv4=min_confidence_ipv4,
        min_confidence_ipv6=min_confidence_ipv6,
        max_age_days=max_age_days,
        enable_ipv6=enable_ipv6,
    ).build_plan()


def command_version() -> int:
    """Print version information."""

    version = get_version()

    print(f"RouteCollector {version.version}")
    print(f"Python {version.python}")
    print(f"Platform {version.platform}")

    return 0


def command_status(config_path: Path) -> int:
    """Print application status."""

    app = Application(config_path)
    app.initialize()

    print(f"RouteCollector {__version__}")
    print()

    for name, status in app.status().items():
        print(f"{name:<16} {status}")

    return 0


def command_init(config_path: Path) -> int:
    """Initialize RouteCollector state."""

    app = Application(config_path)
    app.init_database()

    print("RouteCollector initialized")
    print(f"Database: {app.database.path if app.database else 'unknown'}")

    return 0


def command_sync(config_path: Path) -> int:
    """Synchronize service configuration and print a detailed report."""

    app = get_app(config_path)

    assert app.repository is not None

    started_at = monotonic()

    result = ServiceSourceSync(
        repository=app.repository,
        services_dir=DEFAULT_SERVICES_DIR,
    ).sync()

    duration_seconds = max(
        0.0,
        monotonic() - started_at,
    )

    print("Service synchronization completed")
    print()

    if not result.services:
        print("No configured services were synchronized.")
        print()

    for service in result.services:
        state = "enabled" if service.enabled else "disabled"
        print(f"{service.service_name} [{state}]")
        print("-" * (len(service.service_name) + len(state) + 3))

        source_width = max(
            (
                len(source.source_name)
                for source in service.sources
            ),
            default=0,
        )

        for source in service.sources:
            print(
                f"  {source.source_name:<{source_width}}  "
                f"{source.domain_count:>6} domains"
            )

        print()
        print(
            f"  Merged domains       : "
            f"{service.domain_count}"
        )
        print(
            f"  Rows deactivated     : "
            f"{service.deactivated_count}"
        )
        print()

    print("Summary")
    print("-------")
    print(
        f"Configured services   : "
        f"{result.service_count}"
    )
    print(
        f"Disabled services     : "
        f"{result.disabled_service_count}"
    )
    print(
        f"Source plugins        : "
        f"{result.source_count}"
    )
    print(
        f"Merged domains        : "
        f"{result.domain_count}"
    )
    print(
        f"Rows deactivated      : "
        f"{result.deactivated_count}"
    )
    print(
        f"Duration              : "
        f"{duration_seconds:.2f}s"
    )

    return 0


def command_sources(
    services_dir: Path = DEFAULT_SERVICES_DIR,
) -> int:
    """Print available plugins and configured source usage."""

    status = collect_source_status(services_dir)

    print("Available sources")
    print("-----------------")

    if not status.plugins:
        print("No source plugins are available.")
    else:
        name_width = max(
            len(plugin.name)
            for plugin in status.plugins
        )

        for plugin in status.plugins:
            print(
                f"{plugin.name:<{name_width}}  "
                f"{plugin.origin}"
            )

    print()
    print("Configured usage")
    print("----------------")

    if not status.configured_usage:
        print("No service sources are configured.")
        return 0

    service_width = max(
        len(item.service_name)
        for item in status.configured_usage
    )

    for item in status.configured_usage:
        state = "enabled" if item.enabled else "disabled"
        source_names = (
            ", ".join(item.source_names)
            if item.source_names
            else "(none)"
        )
        print(
            f"{item.service_name:<{service_width}} "
            f"[{state}] : {source_names}"
        )

    return 0


def command_plugin_info(
    services_dir: Path = DEFAULT_SERVICES_DIR,
) -> int:
    """Print detailed metadata for every available source plugin."""

    status = collect_source_status(services_dir)

    print("Source plugin information")
    print("=========================")

    if not status.plugins:
        print()
        print("No source plugins are available.")
        return 0

    for plugin in status.plugins:
        print()
        print(plugin.name)
        print("-" * len(plugin.name))
        print(f"Origin      : {plugin.origin}")
        print(f"Package     : {plugin.package_name}")
        print(f"Version     : {plugin.package_version}")
        print(
            "Entry point : "
            + (
                plugin.entry_point
                if plugin.entry_point is not None
                else "built into RouteCollector"
            )
        )

    return 0


def command_resolve(
    config_path: Path,
    service_name: str | None,
    enable_ipv6: bool,
) -> int:
    """Resolve configured domains."""

    app = get_app(config_path)

    assert app.repository is not None

    domains, observations = DnsResolver(
        app.repository,
        enable_ipv6=enable_ipv6,
    ).resolve_all(service_name)

    print("DNS resolve completed")
    print(f"Domains: {domains}")
    print(f"Observations: {observations}")

    return 0


def command_plan(
    config_path: Path,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
    max_age_days: int,
    enable_ipv6: bool,
) -> int:
    """Build and print route plan."""

    app = get_app(config_path)

    routes = build_route_plan(
        app,
        min_confidence_ipv4,
        min_confidence_ipv6,
        max_age_days,
        enable_ipv6,
    )

    print("Route plan")
    print(f"Prefixes: {len(routes)}")
    print()

    for route in routes:
        print(
            f"{route.prefix:<24} "
            f"family=IPv{route.family} "
            f"source_ips={route.source_ips:<4} "
            f"confidence={route.confidence:<3} "
            f"publish_score={route.publish_score:<3} "
            f"trust={route.source_trust:<3} "
            f"sources={route.source_count}"
        )

    return 0


def command_stats(config_path: Path) -> int:
    """Rebuild and print route statistics."""

    app = get_app(config_path)

    assert app.repository is not None

    count = app.repository.rebuild_route_stats()
    stats = app.repository.list_route_stats()

    print("Route statistics rebuilt")
    print(f"Prefixes: {count}")
    print()

    for stat in stats:
        print(
            f"{stat.prefix:<24} "
            f"family=IPv{stat.family} "
            f"source_ips={stat.source_ips:<4} "
            f"hits={stat.total_hits:<5} "
            f"confidence={stat.confidence}"
        )

    return 0



def command_changes(
    snapshot_directory: Path = DEFAULT_PLAN_SNAPSHOTS,
) -> int:
    """Print route membership changes between latest snapshots."""

    store = PlanSnapshotStore(snapshot_directory)
    changes = store.changes()

    if changes is None:
        snapshot_count = len(store.list_paths())

        print("Route plan changes")
        print()

        if snapshot_count == 0:
            print("No route plan snapshots are available.")
            print("Run routecollector run-once to create the first snapshot.")
        else:
            print("Only one route plan snapshot is available.")
            print("At least two snapshots are required for comparison.")

        return 0

    print("Route plan changes")
    print()
    print(f"Routes before: {changes.previous_count}")
    print(f"Routes now:    {changes.current_count}")
    print(f"Added:         {len(changes.added)}")
    print(f"Removed:       {len(changes.removed)}")
    print()

    if not changes.changed:
        print("No route membership changes detected.")
        return 0

    if changes.added:
        print("Added routes")
        print("------------")

        for route in changes.added:
            print(
                f"+ {route.prefix:<24} "
                f"family=IPv{route.family} "
                f"publish_score={route.publish_score:<3} "
                f"confidence={route.confidence:<3} "
                f"trust={route.source_trust:<3} "
                f"sources={route.source_count}"
            )

        print()

    if changes.removed:
        print("Removed routes")
        print("--------------")

        for route in changes.removed:
            print(
                f"- {route.prefix:<24} "
                f"family=IPv{route.family} "
                f"publish_score={route.publish_score:<3} "
                f"confidence={route.confidence:<3} "
                f"trust={route.source_trust:<3} "
                f"sources={route.source_count}"
            )

    return 0



def command_history(
    config_path: Path,
    limit: int,
) -> int:
    """Print recent successful RouteCollector cycles."""

    app = get_app(config_path)

    if app.database is None:
        raise RuntimeError("Database is not initialized")

    entries = CycleHistoryStore(
        app.database
    ).list_recent(limit=limit)

    print("RouteCollector cycle history")
    print()

    if not entries:
        print("No successful cycles are stored.")
        return 0

    for entry in entries:
        service = entry.service_name or "all"
        reload_state = "yes" if entry.bird_reloaded else "no"

        print(
            f"#{entry.id:<4} "
            f"{entry.completed_at} "
            f"duration={entry.duration_seconds:.1f}s "
            f"service={service}"
        )
        print(
            f"      routes={entry.planned_routes} "
            f"added={entry.routes_added} "
            f"removed={entry.routes_removed} "
            f"bird_reloaded={reload_state}"
        )
        print(
            f"      services={entry.services_synced} "
            f"domains={entry.domains_synced} "
            f"resolved={entry.domains_resolved} "
            f"observations={entry.observations_stored} "
            f"route_stats={entry.route_stats_built}"
        )
        print()

    return 0

def command_export(
    config_path: Path,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
    max_age_days: int,
    enable_ipv6: bool,
) -> int:
    """Export route plan to BIRD configuration."""

    app = get_app(config_path)

    routes = build_route_plan(
        app,
        min_confidence_ipv4,
        min_confidence_ipv6,
        max_age_days,
        enable_ipv6,
    )

    if not routes:
        raise RuntimeError(
            "Route plan is empty; refusing to generate BIRD configuration"
        )

    result = BirdExporter(DEFAULT_BIRD_OUTPUT).export(routes)

    print("BIRD config export completed")
    print(f"File: {result.path}")
    print(f"Prefixes: {result.route_count}")
    print(f"Changed: {'yes' if result.changed else 'no'}")

    return 0


def command_bird_check() -> int:
    """Check BIRD configuration."""

    print(BirdControl().configure_check())

    return 0


def command_install_bird_config() -> int:
    """Install generated BIRD configuration."""

    result = BirdConfigInstaller(
        source_file=DEFAULT_BIRD_OUTPUT,
        target_file=DEFAULT_BIRD_TARGET,
        main_config=DEFAULT_BIRD_MAIN_CONFIG,
    ).install()

    print("BIRD config installation completed")
    print(f"File: {result.path}")
    print(f"Changed: {'yes' if result.changed else 'no'}")

    return 0


def command_bird_reload() -> int:
    """Apply BIRD configuration."""

    control = BirdControl()

    print(control.configure_check())
    print(control.configure())

    return 0


def command_run_once(
    config_path: Path,
    service_name: str | None,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
    max_age_days: int,
    enable_ipv6: bool,
    dry_run: bool,
) -> int:
    """Execute one complete update cycle and print a structured report."""

    app = get_app(config_path)

    result = build_workflow(
        app,
        min_confidence_ipv4,
        min_confidence_ipv6,
        max_age_days,
        enable_ipv6,
    ).run(
        service_name,
        dry_run=dry_run,
    )

    print(
        "RouteCollector dry run completed"
        if result.dry_run
        else "RouteCollector cycle completed"
    )
    print()

    print("Synchronization")
    print("---------------")
    print(f"Configured services   : {result.sync_result.service_count}")
    print(f"Disabled services     : {result.sync_result.disabled_service_count}")
    print(f"Source plugins        : {result.sync_result.source_count}")
    print(f"Merged domains        : {result.sync_result.domain_count}")
    print(f"Rows deactivated      : {result.sync_result.deactivated_count}")

    for service in result.sync_result.services:
        state = "enabled" if service.enabled else "disabled"
        print()
        print(f"  {service.service_name} [{state}]")

        source_width = max(
            [len(source.source_name) for source in service.sources]
            + [len("merged")]
        )

        for source in service.sources:
            print(
                f"    {source.source_name:<{source_width}}  "
                f"{source.domain_count:>6} domains"
            )

        print(
            f"    {'merged':<{source_width}}  "
            f"{service.domain_count:>6} domains"
        )

    print()
    print("DNS")
    print("---")
    print(f"Resolved domains      : {result.domains_resolved}")
    print(f"Observations stored   : {result.observations_stored}")

    print()
    print("Routing")
    print("-------")
    print(f"Route statistics      : {result.route_stats_built}")
    print(f"Planned routes        : {result.planned_routes}")
    print(f"Routes added          : {result.routes_added}")
    print(f"Routes removed        : {result.routes_removed}")

    print()
    print("Publication")
    print("-----------")
    print(f"Generated config      : {result.generated_config}")
    print(
        "Generated changed     : "
        + ("yes" if result.generated_changed else "no")
    )

    if result.dry_run:
        print("Installed config      : not modified")
        print("Installed changed     : no")
        print()
        print("BIRD")
        print("----")
        print("Configuration check   : skipped")
        print("Reload                : skipped")
        print("Rollback              : not required")
        print()
        print("History")
        print("-------")
        print("Snapshot              : not stored")
        print("Cycle history         : not stored")
        print()
        print(f"Duration              : {result.duration_seconds:.1f}s")
        return 0

    print(f"Installed config      : {result.installed_config}")
    print(
        "Installed changed     : "
        + ("yes" if result.installed_changed else "no")
    )
    print()
    print("BIRD")
    print("----")
    print("Configuration check   : passed")
    print(
        "Reload                : "
        + ("completed" if result.bird_reloaded else "not required")
    )
    print(
        "Rollback              : "
        + ("performed" if result.rollback_performed else "not required")
    )
    print()
    print("History")
    print("-------")
    print("Snapshot              : stored")
    print("Cycle history         : stored")
    print()
    print(f"Duration              : {result.duration_seconds:.1f}s")

    return 0

def command_daemon(
    config_path: Path,
    interval_seconds: int,
    service_name: str | None,
    lock_file: Path,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
    max_age_days: int,
    enable_ipv6: bool,
) -> int:
    """Run RouteCollector continuously."""

    app = get_app(config_path)

    if app.logger is None:
        raise RuntimeError("Logger is not initialized")

    workflow = build_workflow(
        app,
        min_confidence_ipv4,
        min_confidence_ipv6,
        max_age_days,
        enable_ipv6,
    )

    daemon = RouteCollectorDaemon(
        workflow=workflow,
        config=DaemonConfig(
            interval_seconds=interval_seconds,
            lock_file=lock_file,
            service_name=service_name,
        ),
        logger=app.logger,
    )

    daemon.run()

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.quiet:
        logging.disable(logging.INFO)

    if args.command == "version":
        return command_version()

    if args.command == "status":
        return command_status(args.config)

    if args.command == "init":
        return command_init(args.config)

    if args.command == "sync":
        return command_sync(args.config)

    if args.command == "sources":
        return command_sources()

    if args.command == "plugin-info":
        return command_plugin_info()

    if args.command == "resolve":
        return command_resolve(
            args.config,
            args.service,
            args.enable_ipv6,
        )

    if args.command == "plan":
        return command_plan(
            args.config,
            args.min_confidence_ipv4,
            args.min_confidence_ipv6,
            args.max_age_days,
            args.enable_ipv6,
            args.dry_run,
        )

    if args.command == "stats":
        return command_stats(args.config)

    if args.command == "changes":
        return command_changes()

    if args.command == "history":
        return command_history(
            args.config,
            args.limit,
        )

    if args.command == "export":
        return command_export(
            args.config,
            args.min_confidence_ipv4,
            args.min_confidence_ipv6,
            args.max_age_days,
            args.enable_ipv6,
        )

    if args.command == "bird-check":
        return command_bird_check()

    if args.command == "install-bird-config":
        return command_install_bird_config()

    if args.command == "bird-reload":
        return command_bird_reload()

    if args.command == "run-once":
        return command_run_once(
            args.config,
            args.service,
            args.min_confidence_ipv4,
            args.min_confidence_ipv6,
            args.max_age_days,
            args.enable_ipv6,
            args.dry_run,
        )

    if args.command == "daemon":
        return command_daemon(
            args.config,
            args.interval,
            args.service,
            args.lock_file,
            args.min_confidence_ipv4,
            args.min_confidence_ipv6,
            args.max_age_days,
            args.enable_ipv6,
        )

    parser.print_help()
    return 0
