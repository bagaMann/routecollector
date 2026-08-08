"""
Tests for normalized route statistics builder.
"""

from __future__ import annotations

from routecollector.core.repository import Observation
from routecollector.policy.statistics import RouteStatisticsBuilder


def make_observation(
    *,
    observation_id: int,
    domain_id: int | None,
    ip: str,
    dns_server: str | None,
    domain_source: str | None = "manual",
    hits: int = 1,
    first_seen: str = "2026-07-01 00:00:00",
    last_seen: str = "2026-07-11 00:00:00",
) -> Observation:
    return Observation(
        id=observation_id,
        domain_id=domain_id,
        domain_source=domain_source,
        ip=ip,
        source="resolver",
        dns_server=dns_server,
        hits=hits,
        ttl=300,
        confidence=999,
        first_seen=first_seen,
        last_seen=last_seen,
    )


def test_statistics_builder_aggregates_ipv4_prefix() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="8.8.8.8",
                dns_server="1.1.1.1",
                hits=4,
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="8.8.8.9",
                dns_server="8.8.8.8",
                hits=6,
            ),
        ]
    )

    stat = stats[0]
    assert len(stats) == 1
    assert stat.prefix == "8.8.8.0/24"
    assert stat.family == 4
    assert stat.source_ips == 2
    assert stat.unique_domains == 2
    assert stat.unique_resolvers == 2
    assert stat.source_count == 1
    assert stat.source_trust == 100
    assert stat.total_hits == 10
    assert stat.confidence == 55


def test_statistics_builder_aggregates_ipv6_prefix() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="2606:4700:4700::1111",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="2606:4700:4700::1001",
                dns_server="8.8.8.8",
            ),
        ]
    )

    assert len(stats) == 1
    assert stats[0].prefix == "2606:4700:4700::/48"
    assert stats[0].family == 6


def test_statistics_builder_counts_unique_evidence_only() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="8.8.8.8",
                dns_server="1.1.1.1",
                hits=5,
            ),
            make_observation(
                observation_id=2,
                domain_id=10,
                ip="8.8.8.8",
                dns_server="1.1.1.1",
                hits=7,
            ),
        ]
    )

    stat = stats[0]
    assert stat.source_ips == 1
    assert stat.unique_domains == 1
    assert stat.unique_resolvers == 1
    assert stat.source_count == 1
    assert stat.source_trust == 100
    assert stat.total_hits == 12
    assert stat.confidence == 45


def test_statistics_builder_counts_independent_sources() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                domain_source="manual",
                ip="8.8.8.8",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                domain_source="domain-list-community:youtube",
                ip="8.8.8.9",
                dns_server="8.8.8.8",
            ),
        ]
    )

    assert stats[0].source_count == 2
    assert stats[0].source_trust == 100
    assert stats[0].confidence == 55


def test_statistics_builder_scores_dynamic_dns_source() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                domain_source="dynamic-dns",
                ip="8.8.8.8",
                dns_server="1.1.1.1",
                first_seen="2026-07-11 00:00:00",
                last_seen="2026-07-11 00:00:00",
            )
        ]
    )

    stat = stats[0]
    assert stat.source_count == 1
    assert stat.source_trust == 50
    assert stat.confidence == 25


def test_statistics_builder_uses_earliest_and_latest_dates() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="8.8.8.8",
                dns_server="1.1.1.1",
                first_seen="2026-07-05 00:00:00",
                last_seen="2026-07-08 00:00:00",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="8.8.8.9",
                dns_server="8.8.8.8",
                first_seen="2026-07-01 00:00:00",
                last_seen="2026-07-11 00:00:00",
            ),
        ]
    )

    assert stats[0].first_seen == "2026-07-01 00:00:00"
    assert stats[0].last_seen == "2026-07-11 00:00:00"


def test_statistics_builder_skips_invalid_observations() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="not-an-ip",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="8.8.8.8",
                dns_server="1.1.1.1",
                first_seen="invalid-date",
            ),
        ]
    )

    assert stats == []


def test_statistics_builder_skips_non_global_addresses() -> None:
    builder = RouteStatisticsBuilder()
    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="127.0.0.1",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="192.168.1.10",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=3,
                domain_id=12,
                ip="192.0.2.10",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=4,
                domain_id=13,
                ip="2001:db8::10",
                dns_server="1.1.1.1",
            ),
        ]
    )

    assert stats == []


def test_statistics_builder_rejects_invalid_prefix_lengths() -> None:
    try:
        RouteStatisticsBuilder(ipv4_prefix=33)
    except ValueError as exc:
        assert "IPv4 prefix length" in str(exc)
    else:
        raise AssertionError("Expected IPv4 prefix validation error")

    try:
        RouteStatisticsBuilder(ipv6_prefix=129)
    except ValueError as exc:
        assert "IPv6 prefix length" in str(exc)
    else:
        raise AssertionError("Expected IPv6 prefix validation error")
