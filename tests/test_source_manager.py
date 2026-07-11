"""
Tests for domain source manager.
"""

from __future__ import annotations

from routecollector.sources.base import (
    DomainSource,
    DomainSourceRequest,
    DomainSourceResult,
)
from routecollector.sources.manager import SourceManager
from routecollector.sources.registry import SourceRegistry


class FakeSource(DomainSource):
    """Configurable source used by manager tests."""

    def __init__(
        self,
        source_name: str,
        domains: set[str],
    ) -> None:
        self._source_name = source_name
        self._domains = domains
        self.requests: list[DomainSourceRequest] = []

    @property
    def name(self) -> str:
        """Return source name."""

        return self._source_name

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        """Return predefined domains and record request."""

        self.requests.append(request)

        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=self.normalize_domains(self._domains),
            metadata={"count": len(self._domains)},
        )


def test_source_manager_merges_domains_and_preserves_provenance() -> None:
    """Manager must merge duplicates and keep source provenance."""

    source_a = FakeSource(
        "alpha",
        {
            "discord.com",
            "discord.gg",
        },
    )
    source_b = FakeSource(
        "beta",
        {
            "discord.gg",
            "cdn.discordapp.com",
        },
    )

    manager = SourceManager(
        SourceRegistry([source_a, source_b])
    )

    result = manager.load(
        service_name="discord",
        source_names=["alpha", "beta"],
    )

    assert result.service_name == "discord"

    domains = {
        item.domain: item.sources
        for item in result.domains
    }

    assert domains == {
        "cdn.discordapp.com": frozenset({"beta"}),
        "discord.com": frozenset({"alpha"}),
        "discord.gg": frozenset({"alpha", "beta"}),
    }

    assert len(result.source_results) == 2


def test_source_manager_passes_source_options() -> None:
    """Each source must receive only its configured options."""

    alpha = FakeSource("alpha", {"discord.com"})
    beta = FakeSource("beta", {"discord.gg"})

    manager = SourceManager(
        SourceRegistry([alpha, beta])
    )

    manager.load(
        service_name="discord",
        source_names=["alpha", "beta"],
        source_options={
            "alpha": {
                "list": "discord",
                "timeout": 10,
            },
            "beta": {
                "path": "custom/discord.txt",
            },
        },
    )

    assert alpha.requests[0].source_options == {
        "list": "discord",
        "timeout": 10,
    }
    assert beta.requests[0].source_options == {
        "path": "custom/discord.txt",
    }


def test_source_manager_returns_empty_result_for_no_sources() -> None:
    """Empty source list must produce an empty merged result."""

    manager = SourceManager(SourceRegistry())

    result = manager.load(
        service_name="discord",
        source_names=[],
    )

    assert result.service_name == "discord"
    assert result.domains == ()
    assert result.source_results == ()


def test_source_manager_normalizes_source_lookup_names() -> None:
    """Manager must resolve configured source names case-insensitively."""

    source = FakeSource("Alpha", {"discord.com"})
    manager = SourceManager(SourceRegistry([source]))

    result = manager.load(
        service_name="discord",
        source_names=[" ALPHA "],
    )

    assert len(result.domains) == 1
    assert result.domains[0].domain == "discord.com"
    assert result.domains[0].sources == frozenset({"alpha"})


def test_source_manager_keeps_source_result_order() -> None:
    """Source result order must match configured source order."""

    alpha = FakeSource("alpha", {"a.example"})
    beta = FakeSource("beta", {"b.example"})

    manager = SourceManager(
        SourceRegistry([alpha, beta])
    )

    result = manager.load(
        service_name="test",
        source_names=["beta", "alpha"],
    )

    assert tuple(
        item.source_name
        for item in result.source_results
    ) == ("beta", "alpha")
