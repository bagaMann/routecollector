"""
Route planning module.

Builds route prefixes from route statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

from routecollector.core.repository import Repository


@dataclass(slots=True, frozen=True)
class PlannedRoute:
    """Planned route prefix."""

    prefix: str
    family: int
    source_ips: int
    confidence: int


class RoutePlanner:
    """Build route plan from route statistics."""

    def __init__(
        self,
        repository: Repository,
        min_confidence_ipv4: int = 10,
        min_confidence_ipv6: int = 10,
    ) -> None:
        self._repository = repository
        self._min_confidence_ipv4 = min_confidence_ipv4
        self._min_confidence_ipv6 = min_confidence_ipv6

    def build_plan(self) -> list[PlannedRoute]:
        """Build planned route prefixes."""

        route_stats = self._repository.list_route_stats()
        routes: list[PlannedRoute] = []

        for stat in route_stats:
            min_confidence = (
                self._min_confidence_ipv4
                if stat.family == 4
                else self._min_confidence_ipv6
            )

            if stat.confidence < min_confidence:
                continue

            routes.append(
                PlannedRoute(
                    prefix=stat.prefix,
                    family=stat.family,
                    source_ips=stat.source_ips,
                    confidence=stat.confidence,
                )
            )

        return sorted(routes, key=lambda route: (route.family, route.prefix))
