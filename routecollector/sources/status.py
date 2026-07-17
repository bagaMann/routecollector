"""Source plugin diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from routecollector.parser.service_config import ServiceConfigLoader
from routecollector.sources.default_registry import create_default_registry


@dataclass(slots=True, frozen=True)
class ConfiguredSourceUsage:
    """Source plugins configured for one service."""

    service_name: str
    enabled: bool
    source_names: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SourceStatus:
    """Built-in sources and their configured usage."""

    built_in_sources: tuple[str, ...]
    configured_usage: tuple[ConfiguredSourceUsage, ...]


def collect_source_status(services_dir: Path) -> SourceStatus:
    """Collect registered plugins and source usage from YAML configs."""

    registry = create_default_registry()
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
        built_in_sources=registry.names(),
        configured_usage=usage,
    )
