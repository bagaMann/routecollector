"""
Command line interface for RouteCollector.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from routecollector import __version__
from routecollector.core.application import Application
from routecollector.core.version import get_version
from routecollector.exporter.bird import BirdExporter
from routecollector.exporter.birdctl import BirdConfigInstaller, BirdControl
from routecollector.parser.service_config import ServiceConfigSync
from routecollector.planner.planner import RoutePlanner
from routecollector.resolver.resolver import DnsResolver
from routecollector.workflow.run_once import RunOnceWorkflow


DEFAULT_CONFIG = Path("config/config.yaml")
DEFAULT_SERVICES_DIR = Path("config/services")
DEFAULT_BIRD_OUTPUT = Path("bird/routecollector.conf")
DEFAULT_BIRD_TARGET = Path("/etc/bird/routecollector.conf")
DEFAULT_BIRD_MAIN_CONFIG = Path("/etc/bird/bird.conf")


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

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version", help="Show version information")
    subparsers.add_parser("status", help="Show application status")
    subparsers.add_parser("init", help="Initialize RouteCollector state")
    subparsers.add_parser(
        "sync",
        help="Sync service configuration into database",
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

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build route plan from statistics",
    )
    add_confidence_arguments(plan_parser)

    subparsers.add_parser(
        "stats",
        help="Rebuild and show route statistics",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="Export route plan to BIRD",
    )
    add_confidence_arguments(export_parser)

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
        help="Run complete update cycle without reloading BIRD",
    )
    run_once_parser.add_argument(
        "service",
        nargs="?",
        default=None,
        help="Optional service name",
    )
    add_confidence_arguments(run_once_parser)

    return parser


def add_confidence_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    """Add route confidence options to a command parser."""

    parser.add_argument(
        "--min-confidence-ipv4",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--min-confidence-ipv6",
        type=int,
        default=10,
    )


def get_app(config_path: Path) -> Application:
    """Create initialized application."""

    app = Application(config_path)
    app.initialize()

    if app.repository is None:
        raise RuntimeError("Repository is not initialized")

    return app


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
    """Synchronize service configuration."""

    app = get_app(config_path)
    assert app.repository is not None

    services, domains = ServiceConfigSync(
        repository=app.repository,
        services_dir=DEFAULT_SERVICES_DIR,
    ).sync()

    print("Service configuration synced")
    print(f"Services: {services}")
    print(f"Domains: {domains}")

    return 0


def command_resolve(
    config_path: Path,
    service_name: str | None,
) -> int:
    """Resolve configured domains."""

    app = get_app(config_path)
    assert app.repository is not None

    domains, observations = DnsResolver(
        app.repository
    ).resolve_all(service_name)

    print("DNS resolve completed")
    print(f"Domains: {domains}")
    print(f"Observations: {observations}")

    return 0


def build_route_plan(
    app: Application,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
):
    """Build a route plan for an initialized application."""

    assert app.repository is not None

    return RoutePlanner(
        repository=app.repository,
        min_confidence_ipv4=min_confidence_ipv4,
        min_confidence_ipv6=min_confidence_ipv6,
    ).build_plan()


def command_plan(
    config_path: Path,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
) -> int:
    """Build and print route plan."""

    app = get_app(config_path)
    routes = build_route_plan(
        app,
        min_confidence_ipv4,
        min_confidence_ipv6,
    )

    print("Route plan")
    print(f"Prefixes: {len(routes)}")
    print()

    for route in routes:
        print(
            f"{route.prefix:<24} "
            f"family=IPv{route.family} "
            f"source_ips={route.source_ips:<4} "
            f"confidence={route.confidence}"
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


def command_export(
    config_path: Path,
    min_confidence_ipv4: int,
    min_confidence_ipv6: int,
) -> int:
    """Export route plan to BIRD configuration."""

    app = get_app(config_path)
    routes = build_route_plan(
        app,
        min_confidence_ipv4,
        min_confidence_ipv6,
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
) -> int:
    """Execute complete update cycle without reloading BIRD."""

    app = get_app(config_path)
    assert app.repository is not None

    result = RunOnceWorkflow(
        repository=app.repository,
        services_dir=DEFAULT_SERVICES_DIR,
        generated_config=DEFAULT_BIRD_OUTPUT,
        installed_config=DEFAULT_BIRD_TARGET,
        main_bird_config=DEFAULT_BIRD_MAIN_CONFIG,
        min_confidence_ipv4=min_confidence_ipv4,
        min_confidence_ipv6=min_confidence_ipv6,
    ).run(service_name)

    print("RouteCollector cycle completed")
    print()
    print(f"Services synced:     {result.services_synced}")
    print(f"Domains synced:      {result.domains_synced}")
    print(f"Domains resolved:    {result.domains_resolved}")
    print(f"Observations stored: {result.observations_stored}")
    print(f"Route statistics:    {result.route_stats_built}")
    print(f"Planned routes:      {result.planned_routes}")
    print(f"Generated config:    {result.generated_config}")
    print(
        "Generated changed:   "
        f"{'yes' if result.generated_changed else 'no'}"
    )
    print(f"Installed config:    {result.installed_config}")
    print(
        "Installed changed:   "
        f"{'yes' if result.installed_changed else 'no'}"
    )
    print()
    print(result.bird_check_output)
    print()

    if result.installed_changed:
        print("BIRD configuration changed; reload is required.")
    else:
        print("No BIRD route changes detected; reload is not required.")

    return 0


def main() -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "version":
        return command_version()

    if args.command == "status":
        return command_status(args.config)

    if args.command == "init":
        return command_init(args.config)

    if args.command == "sync":
        return command_sync(args.config)

    if args.command == "resolve":
        return command_resolve(args.config, args.service)

    if args.command == "plan":
        return command_plan(
            args.config,
            args.min_confidence_ipv4,
            args.min_confidence_ipv6,
        )

    if args.command == "stats":
        return command_stats(args.config)

    if args.command == "export":
        return command_export(
            args.config,
            args.min_confidence_ipv4,
            args.min_confidence_ipv6,
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
        )

    parser.print_help()
    return 0
