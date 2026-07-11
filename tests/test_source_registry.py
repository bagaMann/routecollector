"""
Tests for domain source registry.
"""

from __future__ import annotations

import pytest

from routecollector.sources.base import (
    DomainSource,
    DomainSourceError,
    DomainSourceRequest,
    DomainSourceResult,
)
from routecollector.sources.registry import SourceRegistry


class FakeSource(DomainSource):
    """Simple source plugin used by registry tests."""

    def __init__(self, source_name: str) -> None:
        self._source_name = source_name

    @property
    def name(self) -> str:
        """Return source name."""

        return self._source_name

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        """Return an empty fake result."""

        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=frozenset(),
        )


def test_registry_registers_and_returns_source() -> None:
    """Registered source must be returned by name."""

    source = FakeSource("custom")
    registry = SourceRegistry()

    registry.register(source)

    assert registry.get("custom") is source
    assert registry.contains("custom") is True


def test_registry_normalizes_source_names() -> None:
    """Source lookups must ignore surrounding spaces and letter case."""

    source = FakeSource("V2Fly")
    registry = SourceRegistry([source])

    assert registry.get(" v2fly ") is source
    assert registry.contains("V2FLY") is True
    assert registry.names() == ("v2fly",)


def test_registry_rejects_duplicate_source_name() -> None:
    """Duplicate normalized source names must be rejected."""

    registry = SourceRegistry([FakeSource("custom")])

    with pytest.raises(
        DomainSourceError,
        match="already registered",
    ):
        registry.register(FakeSource("CUSTOM"))


def test_registry_rejects_empty_source_name() -> None:
    """Source names cannot be empty."""

    registry = SourceRegistry()

    with pytest.raises(
        DomainSourceError,
        match="cannot be empty",
    ):
        registry.register(FakeSource("   "))


def test_registry_rejects_unknown_source() -> None:
    """Unknown source lookup must raise a clear error."""

    registry = SourceRegistry()

    with pytest.raises(
        DomainSourceError,
        match="Unknown domain source",
    ):
        registry.get("missing")


def test_registry_returns_sources_in_stable_order() -> None:
    """Registered source names and instances must be sorted."""

    alpha = FakeSource("alpha")
    beta = FakeSource("beta")
    registry = SourceRegistry([beta, alpha])

    assert registry.names() == ("alpha", "beta")
    assert registry.all() == (alpha, beta)
