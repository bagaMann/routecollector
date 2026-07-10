"""
Tests for route planning.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from routecollector.core.repository import RouteStat
from routecollector.planner.planner import RoutePlanner


class FakeRepository:
    """Repository stub for planner tests."""

    def __init__(self, stats: list[RouteStat]) -> None:
        self._stats = stats

    def list_route_stats(self) -> list[RouteStat]:
        """Return predefined route statistics."""

        return self._stats


NOW = datetime(2026, 7, 10, 20, 0, 0)


def make_stat(
    *,
    prefix: str,
    family: int,
    confidence: int,
    source_ips: int = 1,
    total_hits: int = 1,
    last_seen: datetime | None = NOW,
) -> RouteStat:
    """Build a RouteStat for tests."""

    return RouteStat(
        prefix=prefix,
        family=family,
        source_ips=source_ips,
        total_hits=total_hits,
        confidence=confidence,
        first_seen="2026-07-01 00:00:00",
        last_seen=(
            last_seen.isoformat(sep=" ")
            if last_seen is not None
            else None
        ),
    )


def test_planner_filters_routes_by_confidence() -> None:
    """Routes below configured confidence must be excluded."""

    repository = FakeRepository(
        [
            make_stat(
                prefix="192.0.2.0/24",
                family=4,
                source_ips=5,
                total_hits=20,
                confidence=20,
            ),
            make_stat(
                prefix="198.51.100.0/24",
                family=4,
                source_ips=1,
                total_hits=2,
                confidence=2,
            ),
            make_stat(
                prefix="2001:db8::/48",
                family=6,
                source_ips=8,
                total_hits=30,
                confidence=30,
            ),
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        min_confidence_ipv4=10,
        min_confidence_ipv6=25,
        now=NOW,
    )

    routes = planner.build_plan()

    assert [route.prefix for route in routes] == [
        "192.0.2.0/24",
        "2001:db8::/48",
    ]


def test_planner_accepts_route_at_exact_threshold() -> None:
    """A route at the exact confidence threshold must be included."""

    repository = FakeRepository(
        [
            make_stat(
                prefix="203.0.113.0/24",
                family=4,
                source_ips=3,
                total_hits=10,
                confidence=10,
            )
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        min_confidence_ipv4=10,
        now=NOW,
    )

    routes = planner.build_plan()

    assert len(routes) == 1
    assert routes[0].prefix == "203.0.113.0/24"
    assert routes[0].confidence == 10


def test_planner_excludes_stale_route() -> None:
    """Route older than maximum age must be excluded."""

    repository = FakeRepository(
        [
            make_stat(
                prefix="192.0.2.0/24",
                family=4,
                confidence=100,
                last_seen=NOW - timedelta(days=31),
            )
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        min_confidence_ipv4=10,
        max_age_days=30,
        now=NOW,
    )

    assert planner.build_plan() == []


def test_planner_accepts_route_at_exact_age_limit() -> None:
    """Route at the exact age limit must remain publishable."""

    repository = FakeRepository(
        [
            make_stat(
                prefix="192.0.2.0/24",
                family=4,
                confidence=100,
                last_seen=NOW - timedelta(days=30),
            )
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        max_age_days=30,
        now=NOW,
    )

    routes = planner.build_plan()

    assert len(routes) == 1
    assert routes[0].prefix == "192.0.2.0/24"


def test_planner_excludes_route_without_last_seen() -> None:
    """Route without last_seen must not be published."""

    repository = FakeRepository(
        [
            make_stat(
                prefix="192.0.2.0/24",
                family=4,
                confidence=100,
                last_seen=None,
            )
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        now=NOW,
    )

    assert planner.build_plan() == []


def test_planner_excludes_route_with_invalid_last_seen() -> None:
    """Route with invalid last_seen must not be published."""

    stat = RouteStat(
        prefix="192.0.2.0/24",
        family=4,
        source_ips=1,
        total_hits=1,
        confidence=100,
        first_seen="2026-07-01 00:00:00",
        last_seen="not-a-date",
    )

    planner = RoutePlanner(
        repository=FakeRepository([stat]),  # type: ignore[arg-type]
        now=NOW,
    )

    assert planner.build_plan() == []


def test_planner_rejects_non_positive_max_age() -> None:
    """Maximum route age must be greater than zero."""

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        RoutePlanner(
            repository=FakeRepository([]),  # type: ignore[arg-type]
            max_age_days=0,
        )


def test_planner_rejects_negative_confidence() -> None:
    """Confidence thresholds cannot be negative."""

    with pytest.raises(
        ValueError,
        match="cannot be negative",
    ):
        RoutePlanner(
            repository=FakeRepository([]),  # type: ignore[arg-type]
            min_confidence_ipv4=-1,
        )
