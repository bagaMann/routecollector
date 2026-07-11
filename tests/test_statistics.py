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
    hits: int = 1,
    first_seen: str = "2026-07-01 00:00:00",
    last_seen: str = "2026-07-11 00:00:00",
) -> Observation:
    """Build an observation for statistics tests."""

    return Observation(
        id=observation_id,
        domain_id=domain_id,
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
    """IPv4 observations in one /24 must produce one route statistic."""

    builder = RouteStatisticsBuilder()

    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="192.0.2.10",
                dns_server="1.1.1.1",
                hits=4,
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="192.0.2.20",
                dns_server="8.8.8.8",
                hits=6,
            ),
        ]
    )

    assert len(stats) == 1

    stat = stats[0]

    assert stat.prefix == "192.0.2.0/24"
    assert stat.family == 4
    assert stat.source_ips == 2
    assert stat.total_hits == 10
    assert stat.confidence == 40
    assert stat.first_seen == "2026-07-01 00:00:00"
    assert stat.last_seen == "2026-07-11 00:00:00"


def test_statistics_builder_aggregates_ipv6_prefix() -> None:
    """IPv6 observations in one /48 must produce one route statistic."""

    builder = RouteStatisticsBuilder()

    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="2001:db8:1::10",
                dns_server="1.1.1.1",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="2001:db8:1::20",
                dns_server="8.8.8.8",
            ),
        ]
    )

    assert len(stats) == 1
    assert stats[0].prefix == "2001:db8:1::/48"
    assert stats[0].family == 6


def test_statistics_builder_counts_unique_evidence_only() -> None:
    """Duplicate IP, domain and resolver values must not inflate evidence."""

    builder = RouteStatisticsBuilder()

    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="192.0.2.10",
                dns_server="1.1.1.1",
                hits=5,
            ),
            make_observation(
                observation_id=2,
                domain_id=10,
                ip="192.0.2.10",
                dns_server="1.1.1.1",
                hits=7,
            ),
        ]
    )

    assert len(stats) == 1

    stat = stats[0]

    assert stat.source_ips == 1
    assert stat.total_hits == 12
    assert stat.confidence == 25


def test_statistics_builder_uses_earliest_and_latest_dates() -> None:
    """Builder must preserve the oldest first_seen and newest last_seen."""

    builder = RouteStatisticsBuilder()

    stats = builder.build(
        [
            make_observation(
                observation_id=1,
                domain_id=10,
                ip="192.0.2.10",
                dns_server="1.1.1.1",
                first_seen="2026-07-05 00:00:00",
                last_seen="2026-07-08 00:00:00",
            ),
            make_observation(
                observation_id=2,
                domain_id=11,
                ip="192.0.2.20",
                dns_server="8.8.8.8",
                first_seen="2026-07-01 00:00:00",
                last_seen="2026-07-11 00:00:00",
            ),
        ]
    )

    assert stats[0].first_seen == "2026-07-01 00:00:00"
    assert stats[0].last_seen == "2026-07-11 00:00:00"


def test_statistics_builder_skips_invalid_observations() -> None:
    """Invalid IP addresses and timestamps must be ignored."""

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
                ip="192.0.2.10",
                dns_server="1.1.1.1",
                first_seen="invalid-date",
            ),
        ]
    )

    assert stats == []


def test_statistics_builder_rejects_invalid_prefix_lengths() -> None:
    """Invalid IPv4 and IPv6 prefix lengths must be rejected."""

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
