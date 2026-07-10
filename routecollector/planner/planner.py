"""
Route planning module.

Builds publishable route prefixes from accumulated route statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from routecollector.core.repository import Repository


@dataclass(slots=True, frozen=True)
class PlannedRoute:
    """Planned route prefix."""

    prefix: str
    family: int
    source_ips: int
    confidence: int


class RoutePlanner:
    """Build route plan from route statistics and publication policy."""

    def __init__(
        self,
        repository: Repository,
        min_confidence_ipv4: int = 10,
        min_confidence_ipv6: int = 10,
        max_age_days: int = 30,
        now: datetime | None = None,
    ) -> None:
        if min_confidence_ipv4 < 0:
            raise ValueError("IPv4 confidence threshold cannot be negative")

        if min_confidence_ipv6 < 0:
            raise ValueError("IPv6 confidence threshold cannot be negative")

        if max_age_days <= 0:
            raise ValueError("Route maximum age must be greater than zero")

        self._repository = repository
        self._min_confidence_ipv4 = min_confidence_ipv4
        self._min_confidence_ipv6 = min_confidence_ipv6
        self._max_age = timedelta(days=max_age_days)
        self._now = now

    def build_plan(self) -> list[PlannedRoute]:
        """Build publishable route prefixes."""

        current_time = self._now or datetime.now()
        routes: list[PlannedRoute] = []

        for stat in self._repository.list_route_stats():
            if stat.family not in {4, 6}:
                continue

            if stat.last_seen is None:
                continue

            try:
                last_seen = datetime.fromisoformat(stat.last_seen)
            except ValueError:
                continue

            if current_time - last_seen > self._max_age:
                continue

            minimum_confidence = (
                self._min_confidence_ipv4
                if stat.family == 4
                else self._min_confidence_ipv6
            )

            if stat.confidence < minimum_confidence:
                continue

            routes.append(
                PlannedRoute(
                    prefix=stat.prefix,
                    family=stat.family,
                    source_ips=stat.source_ips,
                    confidence=stat.confidence,
                )
            )

        return sorted(
            routes,
            key=lambda route: (route.family, route.prefix),
        )
