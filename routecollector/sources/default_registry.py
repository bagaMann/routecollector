"""
Built-in and external source registry.
"""

from __future__ import annotations

from routecollector.sources.domain_list_community_source import (
    DomainListCommunitySource,
)
from routecollector.sources.http_text import HttpTextSource
from routecollector.sources.manual import ManualDomainSource
from routecollector.sources.plugin_loader import (
    register_external_sources,
)
from routecollector.sources.registry import SourceRegistry


def create_default_registry(
    *,
    include_external: bool = True,
) -> SourceRegistry:
    """Create registry with built-in and optionally external sources."""

    registry = SourceRegistry()
    registry.register(ManualDomainSource())
    registry.register(DomainListCommunitySource())
    registry.register(HttpTextSource())

    if include_external:
        register_external_sources(registry)

    return registry
