"""
Fast publication policy for prefixes discovered by matched dynamic DNS.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network
from typing import Iterable, Protocol

from routecollector.planner.planner import PlannedRoute
from routecollector.policy.publish_score import (
    PublishScoreInput,
    PublishScorePolicy,
)


class RouteStatLike(Protocol):
    """Route statistic fields required by fast publication."""

    prefix: str
    family: int
    source_ips: int
    unique_domains: int
    unique_resolvers: int
    source_count: int
    source_trust: int
    confidence: int


@dataclass(slots=True, frozen=True)
class DynamicFastPublishResult:
    """Result of augmenting the normal plan with dynamic prefixes."""

    routes: tuple[PlannedRoute, ...]
    requested_prefixes: tuple[str, ...]
    accepted_prefixes: tuple[str, ...]
    rejected_prefixes: tuple[str, ...]


class DynamicFastPublishPolicy:
    """
    Admit only explicitly requested dynamic prefixes below normal threshold.

    Prefixes arrive here only from the matched dynamic-DNS processing path.
    Normal RoutePlanner behavior is not changed.
    """

    def __init__(
        self,
        *,
        min_confidence_ipv4: int = 25,
        min_confidence_ipv6: int = 25,
        min_source_trust: int = 50,
        enable_ipv6: bool = False,
        publish_score_policy: PublishScorePolicy | None = None,
    ) -> None:
        for name, value in (
            ("IPv4 dynamic confidence", min_confidence_ipv4),
            ("IPv6 dynamic confidence", min_confidence_ipv6),
            ("Dynamic source trust", min_source_trust),
        ):
            if not 0 <= value <= 100:
                raise ValueError(
                    f"{name} must be between 0 and 100"
                )

        self._min_confidence_ipv4 = min_confidence_ipv4
        self._min_confidence_ipv6 = min_confidence_ipv6
        self._min_source_trust = min_source_trust
        self._enable_ipv6 = enable_ipv6
        self._publish_score_policy = (
            publish_score_policy or PublishScorePolicy()
        )

    def augment(
        self,
        *,
        base_routes: Iterable[PlannedRoute],
        route_stats: Iterable[RouteStatLike],
        required_prefixes: Iterable[str],
    ) -> DynamicFastPublishResult:
        """Add eligible requested prefixes to the normal route plan."""

        requested = self._normalize_prefixes(required_prefixes)
        route_map = {
            route.prefix: route
            for route in base_routes
        }
        stat_map = {
            self._normalize_prefix(stat.prefix): stat
            for stat in route_stats
        }

        accepted: set[str] = set()
        rejected: set[str] = set()

        for prefix in requested:
            if prefix in route_map:
                accepted.add(prefix)
                continue

            stat = stat_map.get(prefix)

            if stat is None or not self._eligible(stat):
                rejected.add(prefix)
                continue

            publish_score = self._publish_score_policy.calculate(
                PublishScoreInput(
                    confidence=stat.confidence,
                    source_trust=stat.source_trust,
                    source_count=stat.source_count,
                )
            )

            route_map[prefix] = PlannedRoute(
                prefix=prefix,
                family=stat.family,
                source_ips=stat.source_ips,
                unique_domains=stat.unique_domains,
                unique_resolvers=stat.unique_resolvers,
                source_count=stat.source_count,
                source_trust=stat.source_trust,
                confidence=stat.confidence,
                publish_score=publish_score.total,
            )
            accepted.add(prefix)

        routes = tuple(
            sorted(
                route_map.values(),
                key=lambda route: (
                    route.family,
                    route.prefix,
                ),
            )
        )

        return DynamicFastPublishResult(
            routes=routes,
            requested_prefixes=requested,
            accepted_prefixes=tuple(sorted(accepted)),
            rejected_prefixes=tuple(sorted(rejected)),
        )

    def _eligible(self, stat: RouteStatLike) -> bool:
        if stat.family not in {4, 6}:
            return False

        if stat.family == 6 and not self._enable_ipv6:
            return False

        threshold = (
            self._min_confidence_ipv4
            if stat.family == 4
            else self._min_confidence_ipv6
        )

        return (
            stat.confidence >= threshold
            and stat.source_trust >= self._min_source_trust
        )

    @classmethod
    def _normalize_prefixes(
        cls,
        prefixes: Iterable[str],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    cls._normalize_prefix(prefix)
                    for prefix in prefixes
                }
            )
        )

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        return str(
            ip_network(
                prefix,
                strict=False,
            )
        )
