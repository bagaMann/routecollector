"""
Command line interface for RouteCollector.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from routecollector import __version__
from routecollector.core.application import Application
from routecollector.core.version import get_version
from routecollector.parser.service_config import ServiceConfigSync
from routecollector.resolver.resolver import DnsResolver


DEFAULT_CONFIG = Path("config/config.yaml")
DEFAULT_SERVICES_DIR = Path("config/services")


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
    subparsers.add_parser("sync", help="Sync service configuration into database")

    resolve_parser = subparsers.add_parser("resolve", help="Resolve configured domains")
    resolve_parser.add_argument(
        "service",
        nargs="?",
        default=None,
        help="Optional service name",
    )

    return parser


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
    """Sync service configuration."""

    app = Application(config_path)
    app.initialize()

    if app.repository is None:
        raise RuntimeError("Repository is not initialized")

    sync = ServiceConfigSync(app.repository, DEFAULT_SERVICES_DIR)
    services, domains = sync.sync()

    print("Service configuration synced")
    print(f"Services: {services}")
    print(f"Domains: {domains}")

    return 0


def command_resolve(config_path: Path, service_name: str | None) -> int:
    """Resolve configured domains."""

    app = Application(config_path)
    app.initialize()

    if app.repository is None:
        raise RuntimeError("Repository is not initialized")

    resolver = DnsResolver(app.repository)
    domains, observations = resolver.resolve_all(service_name)

    print("DNS resolve completed")
    print(f"Domains: {domains}")
    print(f"Observations: {observations}")

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

    parser.print_help()
    return 0
