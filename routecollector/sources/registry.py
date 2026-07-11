"""
Registry for RouteCollector domain source plugins.
"""

from __future__ import annotations

from collections.abc import Iterable

from routecollector.sources.base import DomainSource, DomainSourceError


class SourceRegistry:
    """Store and resolve domain source plugins by unique name."""

    def __init__(
        self,
        sources: Iterable[DomainSource] | None = None,
    ) -> None:
        self._sources: dict[str, DomainSource] = {}

        if sources is not None:
            for source in sources:
                self.register(source)

    def register(self, source: DomainSource) -> None:
        """Register one source plugin."""

        source_name = source.name.strip().lower()

        if not source_name:
            raise DomainSourceError("Domain source name cannot be empty")

        if source_name in self._sources:
            raise DomainSourceError(
                f"Domain source is already registered: {source_name}"
            )

        self._sources[source_name] = source

    def get(self, source_name: str) -> DomainSource:
        """Return registered source by name."""

        normalized_name = source_name.strip().lower()

        try:
            return self._sources[normalized_name]
        except KeyError as exc:
            raise DomainSourceError(
                f"Unknown domain source: {source_name}"
            ) from exc

    def contains(self, source_name: str) -> bool:
        """Return whether a source is registered."""

        return source_name.strip().lower() in self._sources

    def names(self) -> tuple[str, ...]:
        """Return registered source names in stable order."""

        return tuple(sorted(self._sources))

    def all(self) -> tuple[DomainSource, ...]:
        """Return registered source instances in stable order."""

        return tuple(
            self._sources[name]
            for name in sorted(self._sources)
        )
