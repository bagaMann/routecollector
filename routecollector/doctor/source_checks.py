"""
Service configuration and source plugin checks for RouteCollector doctor.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.doctor.models import (
    DoctorCheck,
    DoctorStatus,
)
from routecollector.parser.service_config import (
    ServiceConfigLoader,
)
from routecollector.sources.default_registry import (
    create_default_registry,
)
from routecollector.sources.plugin_loader import (
    discover_external_plugins,
)


def check_service_configuration(
    services_dir: Path,
) -> tuple[DoctorCheck, ...]:
    """Validate service YAML and configured source availability."""

    try:
        configs = ServiceConfigLoader(
            services_dir
        ).load_all()
    except Exception as exc:
        return (
            DoctorCheck(
                category="Service configuration",
                name="YAML",
                status=DoctorStatus.ERROR,
                message=str(exc),
            ),
        )

    checks: list[DoctorCheck] = [
        DoctorCheck(
            category="Service configuration",
            name="YAML",
            status=DoctorStatus.OK,
            message=f"{len(configs)} services",
        )
    ]

    if not configs:
        checks.append(
            DoctorCheck(
                category="Service configuration",
                name="Services",
                status=DoctorStatus.WARNING,
                message="no service configurations found",
            )
        )
        return tuple(checks)

    source_definition_count = sum(
        len(config.source_configs)
        for config in configs
    )

    checks.append(
        DoctorCheck(
            category="Service configuration",
            name="Source definitions",
            status=DoctorStatus.OK,
            message=str(source_definition_count),
        )
    )

    for config in sorted(
        configs,
        key=lambda item: item.name,
    ):
        state = (
            DoctorStatus.OK
            if config.enabled
            else DoctorStatus.WARNING
        )
        state_message = (
            f"enabled, {len(config.source_configs)} sources"
            if config.enabled
            else f"disabled, {len(config.source_configs)} sources"
        )

        checks.append(
            DoctorCheck(
                category="Service configuration",
                name=config.name,
                status=state,
                message=state_message,
            )
        )

    return tuple(checks)


def check_source_plugins(
    services_dir: Path,
) -> tuple[DoctorCheck, ...]:
    """Check available plugins and configured source type coverage."""

    try:
        registry = create_default_registry()
    except Exception as exc:
        return (
            DoctorCheck(
                category="Source plugins",
                name="Registry",
                status=DoctorStatus.ERROR,
                message=str(exc),
            ),
        )

    checks: list[DoctorCheck] = [
        DoctorCheck(
            category="Source plugins",
            name="Registry",
            status=DoctorStatus.OK,
            message=f"{len(registry.names())} available",
        )
    ]

    external_by_name = {
        plugin.source.name: plugin
        for plugin in discover_external_plugins()
    }

    for source_name in registry.names():
        external = external_by_name.get(source_name)

        if external is None:
            message = "built-in"
        else:
            message = (
                f"external: {external.package_name} "
                f"{external.package_version}"
            )

        checks.append(
            DoctorCheck(
                category="Source plugins",
                name=source_name,
                status=DoctorStatus.OK,
                message=message,
            )
        )

    try:
        configs = ServiceConfigLoader(
            services_dir
        ).load_all()
    except Exception as exc:
        checks.append(
            DoctorCheck(
                category="Source plugins",
                name="Configured usage",
                status=DoctorStatus.ERROR,
                message=str(exc),
            )
        )
        return tuple(checks)

    configured_types = sorted(
        {
            source.type
            for config in configs
            for source in config.source_configs
        }
    )

    missing_types = [
        source_type
        for source_type in configured_types
        if not registry.contains(source_type)
    ]

    if missing_types:
        checks.append(
            DoctorCheck(
                category="Source plugins",
                name="Configured usage",
                status=DoctorStatus.ERROR,
                message=(
                    "unavailable: "
                    + ", ".join(missing_types)
                ),
            )
        )
    else:
        checks.append(
            DoctorCheck(
                category="Source plugins",
                name="Configured usage",
                status=DoctorStatus.OK,
                message=(
                    f"{len(configured_types)} source types"
                ),
            )
        )

    return tuple(checks)
