"""External source plugin discovery through Python entry points."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Iterable

from routecollector.sources.base import DomainSource, DomainSourceError
from routecollector.sources.registry import SourceRegistry


SOURCE_ENTRY_POINT_GROUP = "routecollector.sources"


@dataclass(slots=True, frozen=True)
class ExternalSourcePlugin:
    """Loaded external source with package metadata."""

    source: DomainSource
    package_name: str
    package_version: str
    entry_point: str


def discover_external_plugins() -> tuple[ExternalSourcePlugin, ...]:
    """Load external source plugins and distribution metadata."""

    discovered: list[ExternalSourcePlugin] = []

    for entry_point in _source_entry_points():
        source = _load_entry_point(entry_point)
        distribution = entry_point.dist

        discovered.append(
            ExternalSourcePlugin(
                source=source,
                package_name=(
                    distribution.metadata["Name"]
                    if distribution is not None
                    else "unknown"
                ),
                package_version=(
                    distribution.version
                    if distribution is not None
                    else "unknown"
                ),
                entry_point=entry_point.value,
            )
        )

    return tuple(discovered)


def discover_external_sources() -> tuple[DomainSource, ...]:
    """Load source instances registered through Python entry points."""

    return tuple(
        plugin.source
        for plugin in discover_external_plugins()
    )


def register_external_sources(
    registry: SourceRegistry,
) -> tuple[str, ...]:
    """Discover external plugins and register them in a registry."""

    registered: list[str] = []

    for plugin in discover_external_plugins():
        registry.register(plugin.source)
        registered.append(plugin.source.name)

    return tuple(sorted(registered))


def _source_entry_points() -> Iterable[EntryPoint]:
    """Return entry points from the RouteCollector source group."""

    discovered = entry_points()

    if hasattr(discovered, "select"):
        return discovered.select(group=SOURCE_ENTRY_POINT_GROUP)

    return discovered.get(  # type: ignore[union-attr]
        SOURCE_ENTRY_POINT_GROUP,
        (),
    )


def _load_entry_point(entry_point: EntryPoint) -> DomainSource:
    """Load and validate one external source entry point."""

    try:
        loaded = entry_point.load()
    except Exception as exc:
        raise DomainSourceError(
            "Unable to load external domain source "
            f"'{entry_point.name}': {exc}"
        ) from exc

    try:
        source = loaded() if isinstance(loaded, type) else loaded
    except Exception as exc:
        raise DomainSourceError(
            "Unable to initialize external domain source "
            f"'{entry_point.name}': {exc}"
        ) from exc

    if not isinstance(source, DomainSource):
        raise DomainSourceError(
            "External domain source "
            f"'{entry_point.name}' must be a DomainSource instance "
            "or DomainSource class"
        )

    entry_name = entry_point.name.strip().lower()
    source_name = source.name.strip().lower()

    if entry_name != source_name:
        raise DomainSourceError(
            "External domain source entry-point name "
            f"'{entry_point.name}' does not match plugin name "
            f"'{source.name}'"
        )

    return source
