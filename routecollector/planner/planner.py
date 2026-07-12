"""
Route planning module.

Builds publishable route prefixes from accumulated route statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from routecollector.core.repository import Repository
from routecollector.policy.publish_score import (
    PublishScoreInput,
    PublishScorePolicy,
)


@dataclass(slots=True, frozen=True)
class PlannedRoute:
    """Planned route prefix."""

    prefix: str
    family: int
    source_ips: int
    unique_domains: int
    unique_resolvers: int
    source_count: int
    source_trust: int
    confidence: int
    publish_score: int


class RoutePlanner:
    """Build route plan from route statistics and publication policy."""

    def __init__(
        self,
        repository: Repository,
        min_confidence_ipv4: int = 10,
        min_confidence_ipv6: int = 10,
        max_age_days: int = 30,
        now: datetime | None = None,
        publish_score_policy: PublishScorePolicy | None = None,
        enable_ipv6: bool = False,
    ) -> None:
        if not 0 <= min_confidence_ipv4 <= 100:
            raise ValueError(
                "IPv4 publication threshold must be between 0 and 100"
            )

        if not 0 <= min_confidence_ipv6 <= 100:
            raise ValueError(
                "IPv6 publication threshold must be between 0 and 100"
            )

        if max_age_days <= 0:
            raise ValueError("Route maximum age must be greater than zero")

        self._repository = repository
        self._min_publish_score_ipv4 = min_confidence_ipv4
        self._min_publish_score_ipv6 = min_confidence_ipv6
        self._max_age = timedelta(days=max_age_days)
        self._now = now
        self._publish_score_policy = (
            publish_score_policy or PublishScorePolicy()
        )
        self._enable_ipv6 = enable_ipv6

    def build_plan(self) -> list[PlannedRoute]:
        """Build publishable route prefixes."""

        current_time = self._now or datetime.now()
        routes: list[PlannedRoute] = []

        for stat in self._repository.list_route_stats():
            if stat.family not in {4, 6}:
                continue

            if stat.family == 6 and not self._enable_ipv6:
                continue

            if stat.last_seen is None:
                continue

            try:
                last_seen = datetime.fromisoformat(stat.last_seen)
            except ValueError:
                continue

            if current_time - last_seen > self._max_age:
                continue

            publish_score = self._publish_score_policy.calculate(
                PublishScoreInput(
                    confidence=stat.confidence,
                    source_trust=stat.source_trust,
                    source_count=stat.source_count,
                )
            )

            minimum_publish_score = (
                self._min_publish_score_ipv4
                if stat.family == 4
                else self._min_publish_score_ipv6
            )

            if publish_score.total < minimum_publish_score:
                continue

            routes.append(
                PlannedRoute(
                    prefix=stat.prefix,
                    family=stat.family,
                    source_ips=stat.source_ips,
                    unique_domains=stat.unique_domains,
                    unique_resolvers=stat.unique_resolvers,
                    source_count=stat.source_count,
                    source_trust=stat.source_trust,
                    confidence=stat.confidence,
                    publish_score=publish_score.total,
                )
            )

        return sorted(
            routes,
            key=lambda route: (route.family, route.prefix),
        )
