"""
Tests for batch DNS resolver behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from routecollector.core.repository import Domain
from routecollector.resolver.resolver import DnsResolver, ResolveResult


class FakeRepository:
    """Repository stub for resolver tests."""

    def __init__(self) -> None:
        self.stored: list[Any] = []

    def list_domains(
        self,
        service_name: str | None = None,
    ) -> list[Domain]:
        assert service_name == "test"

        return [
            Domain(
                id=1,
                service_id=1,
                domain="example.com",
                source="manual",
                active=True,
            ),
            Domain(
                id=2,
                service_id=1,
                domain="example.com",
                source="domain-list-community",
                active=True,
            ),
        ]

    def add_observations(self, observations: list[Any]) -> int:
        self.stored.extend(observations)
        return len(observations)


def test_resolver_deduplicates_dns_queries_and_preserves_provenance(
    monkeypatch: Any,
) -> None:
    """One domain query must fan out to all provenance rows."""

    repository = FakeRepository()
    resolver = DnsResolver(
        repository=repository,  # type: ignore[arg-type]
        progress_every=1,
    )
    calls = 0

    def fake_resolve_domain(_: Domain) -> list[ResolveResult]:
        nonlocal calls
        calls += 1
        return [
            ResolveResult(
                domain="example.com",
                record_type="A",
                ip="93.184.216.34",
                ttl=300,
                dns_server="1.1.1.1",
            )
        ]

    monkeypatch.setattr(
        resolver,
        "resolve_domain",
        fake_resolve_domain,
    )

    domains, observations = resolver.resolve_all("test")

    assert calls == 1
    assert domains == 1
    assert observations == 2
    assert {item.domain_id for item in repository.stored} == {1, 2}


def test_resolver_uses_ipv4_only_by_default() -> None:
    """IPv6 resolution must be disabled by default."""

    resolver = DnsResolver(
        repository=SimpleNamespace(),  # type: ignore[arg-type]
    )

    assert resolver._enable_ipv6 is False


def test_resolver_can_enable_ipv6() -> None:
    """IPv6 resolution must be explicitly enabled."""

    resolver = DnsResolver(
        repository=SimpleNamespace(),  # type: ignore[arg-type]
        enable_ipv6=True,
    )

    assert resolver._enable_ipv6 is True
