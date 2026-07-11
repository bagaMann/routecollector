"""
Domain source manager.

Loads multiple registered sources, merges domains and preserves provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

from routecollector.sources.base import (
    DomainSourceRequest,
    DomainSourceResult,
)
from routecollector.sources.registry import SourceRegistry


@dataclass(slots=True, frozen=True)
class MergedDomain:
    """One normalized domain with source provenance."""

    domain: str
    sources: frozenset[str]


@dataclass(slots=True, frozen=True)
class SourceManagerResult:
    """Merged result for one service."""

    service_name: str
    domains: tuple[MergedDomain, ...]
    source_results: tuple[DomainSourceResult, ...]


class SourceManager:
    """Load and merge domains from multiple registered sources."""

    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

    def load(
        self,
        service_name: str,
        source_names: list[str] | tuple[str, ...],
        source_options: dict[str, dict[str, object]] | None = None,
    ) -> SourceManagerResult:
        """Load configured sources and merge normalized domains."""

        options_by_source = source_options or {}
        provenance: dict[str, set[str]] = {}
        source_results: list[DomainSourceResult] = []

        for source_name in source_names:
            source = self._registry.get(source_name)
            normalized_source_name = source.name.strip().lower()

            request = DomainSourceRequest(
                service_name=service_name,
                source_name=normalized_source_name,
                source_options=options_by_source.get(
                    normalized_source_name,
                    {},
                ),
            )

            result = source.load(request)

            source_results.append(result)

            for domain in result.domains:
                provenance.setdefault(domain, set()).add(
                    normalized_source_name
                )

        merged_domains = tuple(
            MergedDomain(
                domain=domain,
                sources=frozenset(sorted(provenance[domain])),
            )
            for domain in sorted(provenance)
        )

        return SourceManagerResult(
            service_name=service_name,
            domains=merged_domains,
            source_results=tuple(source_results),
        )
