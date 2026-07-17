"""
Built-in source registry.
"""

from __future__ import annotations

from routecollector.sources.domain_list_community_source import (
    DomainListCommunitySource,
)
from routecollector.sources.http_text import HttpTextSource
from routecollector.sources.manual import ManualDomainSource
from routecollector.sources.registry import SourceRegistry


def create_default_registry() -> SourceRegistry:
    """Create registry with all built-in domain sources."""

    registry = SourceRegistry()
    registry.register(ManualDomainSource())
    registry.register(DomainListCommunitySource())
    registry.register(HttpTextSource())

    return registry
