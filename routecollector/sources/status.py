"""Source plugin diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from routecollector.parser.service_config import ServiceConfigLoader
from routecollector.sources.default_registry import create_default_registry
from routecollector.sources.plugin_loader import discover_external_plugins


@dataclass(slots=True, frozen=True)
class SourcePluginInfo:
    """Diagnostic metadata for one available source plugin."""

    name: str
    origin: str
    package_name: str
    package_version: str
    entry_point: str | None


@dataclass(slots=True, frozen=True)
class ConfiguredSourceUsage:
    """Source plugins configured for one service."""

    service_name: str
    enabled: bool
    source_names: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SourceStatus:
    """Available source plugins and configured usage."""

    plugins: tuple[SourcePluginInfo, ...]
    configured_usage: tuple[ConfiguredSourceUsage, ...]


def collect_source_status(services_dir: Path) -> SourceStatus:
    """Collect available plugins and source usage from YAML configs."""

    registry = create_default_registry()
    external_plugins = {
        plugin.source.name: plugin
        for plugin in discover_external_plugins()
    }

    plugins: list[SourcePluginInfo] = []

    for source_name in registry.names():
        external = external_plugins.get(source_name)

        if external is None:
            plugins.append(
                SourcePluginInfo(
                    name=source_name,
                    origin="built-in",
                    package_name="routecollector",
                    package_version="core",
                    entry_point=None,
                )
            )
        else:
            plugins.append(
                SourcePluginInfo(
                    name=source_name,
                    origin="external",
                    package_name=external.package_name,
                    package_version=external.package_version,
                    entry_point=external.entry_point,
                )
            )

    configs = ServiceConfigLoader(services_dir).load_all()
    usage = tuple(
        ConfiguredSourceUsage(
            service_name=config.name,
            enabled=config.enabled,
            source_names=tuple(config.sources),
        )
        for config in sorted(configs, key=lambda item: item.name)
    )

    return SourceStatus(
        plugins=tuple(plugins),
        configured_usage=usage,
    )
