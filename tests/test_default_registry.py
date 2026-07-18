"""
Tests for the default source registry.
"""

from __future__ import annotations

from typing import Any

import routecollector.sources.default_registry as registry_module
from routecollector.sources.base import (
    DomainSource,
    DomainSourceRequest,
    DomainSourceResult,
)
from routecollector.sources.default_registry import (
    create_default_registry,
)


class ExternalExampleSource(DomainSource):
    """External source used to test registry integration."""

    @property
    def name(self) -> str:
        return "external-example"

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=frozenset(),
        )


def test_default_registry_contains_builtin_sources() -> None:
    """Built-in registry must contain all bundled plugins."""

    registry = create_default_registry(
        include_external=False
    )

    assert registry.names() == (
        "domain-list-community",
        "http-text",
        "manual",
    )


def test_default_registry_loads_external_sources(
    monkeypatch: Any,
) -> None:
    """External discovery must extend the default registry."""

    def fake_register(registry: object) -> tuple[str, ...]:
        registry.register(ExternalExampleSource())
        return ("external-example",)

    monkeypatch.setattr(
        registry_module,
        "register_external_sources",
        fake_register,
    )

    registry = create_default_registry()

    assert registry.names() == (
        "domain-list-community",
        "external-example",
        "http-text",
        "manual",
    )


def test_default_registry_can_skip_external_discovery(
    monkeypatch: Any,
) -> None:
    """Tests and controlled callers may disable external discovery."""

    called = False

    def fake_register(_: object) -> tuple[str, ...]:
        nonlocal called
        called = True
        return ()

    monkeypatch.setattr(
        registry_module,
        "register_external_sources",
        fake_register,
    )

    registry = create_default_registry(
        include_external=False
    )

    assert called is False
    assert registry.contains("manual") is True
