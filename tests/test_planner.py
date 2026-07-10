"""
Tests for route planning.
"""

from __future__ import annotations

from routecollector.core.repository import RouteStat
from routecollector.planner.planner import RoutePlanner


class FakeRepository:
    """Repository stub for planner tests."""

    def __init__(self, stats: list[RouteStat]) -> None:
        self._stats = stats

    def list_route_stats(self) -> list[RouteStat]:
        """Return predefined route statistics."""

        return self._stats


def test_planner_filters_routes_by_confidence() -> None:
    """Routes below configured confidence must be excluded."""

    repository = FakeRepository(
        [
            RouteStat(
                prefix="192.0.2.0/24",
                family=4,
                source_ips=5,
                total_hits=20,
                confidence=20,
                first_seen=None,
                last_seen=None,
            ),
            RouteStat(
                prefix="198.51.100.0/24",
                family=4,
                source_ips=1,
                total_hits=2,
                confidence=2,
                first_seen=None,
                last_seen=None,
            ),
            RouteStat(
                prefix="2001:db8::/48",
                family=6,
                source_ips=8,
                total_hits=30,
                confidence=30,
                first_seen=None,
                last_seen=None,
            ),
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        min_confidence_ipv4=10,
        min_confidence_ipv6=25,
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
            RouteStat(
                prefix="203.0.113.0/24",
                family=4,
                source_ips=3,
                total_hits=10,
                confidence=10,
                first_seen=None,
                last_seen=None,
            )
        ]
    )

    planner = RoutePlanner(
        repository=repository,  # type: ignore[arg-type]
        min_confidence_ipv4=10,
    )

    routes = planner.build_plan()

    assert len(routes) == 1
    assert routes[0].prefix == "203.0.113.0/24"
    assert routes[0].confidence == 10
