"""Tests for external source plugin discovery metadata."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

import routecollector.sources.plugin_loader as loader_module
from routecollector.sources.base import (
    DomainSource,
    DomainSourceError,
    DomainSourceRequest,
    DomainSourceResult,
)
from routecollector.sources.plugin_loader import (
    discover_external_plugins,
    discover_external_sources,
    register_external_sources,
)
from routecollector.sources.registry import SourceRegistry


class ExampleSource(DomainSource):
    @property
    def name(self) -> str:
        return "example"

    def load(self, request: DomainSourceRequest) -> DomainSourceResult:
        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=frozenset({"example.com"}),
        )


@dataclass
class FakeEntryPoint:
    name: str
    loaded: object | None = None
    error: Exception | None = None
    value: str = "example_package:ExampleSource"
    package_name: str = "routecollector-source-example"
    package_version: str = "0.1.0"

    @property
    def dist(self) -> object:
        return SimpleNamespace(
            metadata={"Name": self.package_name},
            version=self.package_version,
        )

    def load(self) -> object:
        if self.error is not None:
            raise self.error
        return self.loaded


def set_entry_points(monkeypatch: Any, *items: FakeEntryPoint) -> None:
    monkeypatch.setattr(loader_module, "_source_entry_points", lambda: items)


def test_discover_external_plugin_metadata(monkeypatch: Any) -> None:
    set_entry_points(
        monkeypatch,
        FakeEntryPoint(name="example", loaded=ExampleSource),
    )

    plugin = discover_external_plugins()[0]

    assert isinstance(plugin.source, ExampleSource)
    assert plugin.package_name == "routecollector-source-example"
    assert plugin.package_version == "0.1.0"
    assert plugin.entry_point == "example_package:ExampleSource"


def test_discover_external_source_class(monkeypatch: Any) -> None:
    set_entry_points(
        monkeypatch,
        FakeEntryPoint(name="example", loaded=ExampleSource),
    )

    sources = discover_external_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], ExampleSource)


def test_register_external_sources(monkeypatch: Any) -> None:
    set_entry_points(
        monkeypatch,
        FakeEntryPoint(name="example", loaded=ExampleSource),
    )

    registry = SourceRegistry()
    names = register_external_sources(registry)

    assert names == ("example",)
    assert registry.contains("example") is True


def test_loader_wraps_import_failure(monkeypatch: Any) -> None:
    set_entry_points(
        monkeypatch,
        FakeEntryPoint(
            name="example",
            error=RuntimeError("broken import"),
        ),
    )

    with pytest.raises(DomainSourceError, match="broken import"):
        discover_external_plugins()


def test_loader_rejects_non_source_object(monkeypatch: Any) -> None:
    set_entry_points(
        monkeypatch,
        FakeEntryPoint(name="example", loaded=object()),
    )

    with pytest.raises(DomainSourceError, match="must be a DomainSource"):
        discover_external_plugins()


def test_loader_rejects_entry_name_mismatch(monkeypatch: Any) -> None:
    set_entry_points(
        monkeypatch,
        FakeEntryPoint(name="different", loaded=ExampleSource),
    )

    with pytest.raises(DomainSourceError, match="does not match plugin name"):
        discover_external_plugins()
