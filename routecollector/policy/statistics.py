"""
Build normalized route statistics from DNS observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ipaddress
from typing import TYPE_CHECKING

from routecollector.policy.scoring import RouteScoreInput, RouteScorer
from routecollector.policy.source_trust import SourceTrustPolicy

if TYPE_CHECKING:
    from routecollector.core.repository import Observation


@dataclass(slots=True, frozen=True)
class CalculatedRouteStat:
    """Calculated statistics for one network prefix."""

    prefix: str
    family: int
    source_ips: int
    unique_domains: int
    unique_resolvers: int
    source_count: int
    source_trust: int
    total_hits: int
    confidence: int
    first_seen: str
    last_seen: str


class RouteStatisticsBuilder:
    """Aggregate DNS observations into network statistics."""

    def __init__(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
        scorer: RouteScorer | None = None,
        source_trust_policy: SourceTrustPolicy | None = None,
    ) -> None:
        if not 0 <= ipv4_prefix <= 32:
            raise ValueError("IPv4 prefix length must be between 0 and 32")

        if not 0 <= ipv6_prefix <= 128:
            raise ValueError("IPv6 prefix length must be between 0 and 128")

        self._ipv4_prefix = ipv4_prefix
        self._ipv6_prefix = ipv6_prefix
        self._scorer = scorer or RouteScorer()
        self._source_trust_policy = (
            source_trust_policy or SourceTrustPolicy()
        )

    def build(
        self,
        observations: list[Observation],
    ) -> list[CalculatedRouteStat]:
        """Build normalized statistics from observations."""

        aggregated: dict[str, dict[str, object]] = {}

        for observation in observations:
            try:
                address = ipaddress.ip_address(observation.ip)
                first_seen = datetime.fromisoformat(observation.first_seen)
                last_seen = datetime.fromisoformat(observation.last_seen)
            except ValueError:
                continue

            # Never publish loopback, private, link-local, multicast,
            # reserved, unspecified or other non-globally-routable addresses.
            if not address.is_global:
                continue

            prefix_length = (
                self._ipv4_prefix
                if address.version == 4
                else self._ipv6_prefix
            )

            network = ipaddress.ip_network(
                f"{address}/{prefix_length}",
                strict=False,
            )
            prefix = str(network)

            if prefix not in aggregated:
                aggregated[prefix] = {
                    "family": address.version,
                    "ips": set(),
                    "domains": set(),
                    "resolvers": set(),
                    "sources": set(),
                    "total_hits": 0,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                }

            item = aggregated[prefix]

            ips = self._require_set(item, "ips")
            domains = self._require_set(item, "domains")
            resolvers = self._require_set(item, "resolvers")
            sources = self._require_set(item, "sources")

            ips.add(str(address))

            if observation.domain_id is not None:
                domains.add(observation.domain_id)

            if observation.dns_server:
                resolvers.add(observation.dns_server)

            domain_source = getattr(
                observation,
                "domain_source",
                None,
            )

            if isinstance(domain_source, str) and domain_source.strip():
                sources.add(
                    self._normalize_source_name(domain_source)
                )

            item["total_hits"] = (
                int(item["total_hits"]) + observation.hits
            )

            existing_first_seen = item["first_seen"]
            existing_last_seen = item["last_seen"]

            if not isinstance(existing_first_seen, datetime):
                raise RuntimeError("Invalid first_seen aggregation state")

            if not isinstance(existing_last_seen, datetime):
                raise RuntimeError("Invalid last_seen aggregation state")

            if first_seen < existing_first_seen:
                item["first_seen"] = first_seen

            if last_seen > existing_last_seen:
                item["last_seen"] = last_seen

        result: list[CalculatedRouteStat] = []

        for prefix, item in aggregated.items():
            ips = self._require_set(item, "ips")
            domains = self._require_set(item, "domains")
            resolvers = self._require_set(item, "resolvers")
            sources = self._require_set(item, "sources")

            first_seen = item["first_seen"]
            last_seen = item["last_seen"]

            if not isinstance(first_seen, datetime):
                raise RuntimeError("Invalid first_seen aggregation state")

            if not isinstance(last_seen, datetime):
                raise RuntimeError("Invalid last_seen aggregation state")

            normalized_sources = {
                str(source)
                for source in sources
            }

            source_trust = self._source_trust_policy.score(
                normalized_sources
            )

            score = self._scorer.calculate(
                RouteScoreInput(
                    unique_ips=len(ips),
                    unique_domains=len(domains),
                    unique_resolvers=len(resolvers),
                    first_seen=first_seen,
                    last_seen=last_seen,
                    source_trust=source_trust.total,
                )
            )

            result.append(
                CalculatedRouteStat(
                    prefix=prefix,
                    family=int(item["family"]),
                    source_ips=len(ips),
                    unique_domains=len(domains),
                    unique_resolvers=len(resolvers),
                    source_count=len(sources),
                    source_trust=source_trust.total,
                    total_hits=int(item["total_hits"]),
                    confidence=score.total,
                    first_seen=first_seen.isoformat(sep=" "),
                    last_seen=last_seen.isoformat(sep=" "),
                )
            )

        return sorted(
            result,
            key=lambda stat: (stat.family, stat.prefix),
        )

    @staticmethod
    def _normalize_source_name(source_name: str) -> str:
        """Normalize stored provenance source names.

        Legacy values may include a list suffix such as
        ``domain-list-community:youtube``.
        """

        normalized = source_name.strip().lower()

        if ":" in normalized:
            normalized = normalized.split(":", 1)[0]

        return normalized

    @staticmethod
    def _require_set(
        item: dict[str, object],
        key: str,
    ) -> set[object]:
        """Return an aggregation set or raise an internal error."""

        value = item[key]

        if not isinstance(value, set):
            raise RuntimeError(f"Invalid {key} aggregation state")

        return value
