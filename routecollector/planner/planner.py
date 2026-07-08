"""
Route planning module.

Builds route prefixes from DNS observations.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress

from routecollector.core.repository import Repository


@dataclass(slots=True, frozen=True)
class PlannedRoute:
    """Planned route prefix."""

    prefix: str
    family: int
    source_ips: int


class RoutePlanner:
    """Build route plan from observations."""

    def __init__(
        self,
        repository: Repository,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> None:
        self._repository = repository
        self._ipv4_prefix = ipv4_prefix
        self._ipv6_prefix = ipv6_prefix

    def build_plan(self) -> list[PlannedRoute]:
        """Build planned route prefixes."""

        observations = self._repository.list_observations()
        networks: dict[str, set[str]] = {}

        for observation in observations:
            ip = ipaddress.ip_address(observation.ip)

            if ip.version == 4:
                network = ipaddress.ip_network(
                    f"{ip}/{self._ipv4_prefix}",
                    strict=False,
                )
            else:
                network = ipaddress.ip_network(
                    f"{ip}/{self._ipv6_prefix}",
                    strict=False,
                )

            key = str(network)
            networks.setdefault(key, set()).add(str(ip))

        routes = [
            PlannedRoute(
                prefix=prefix,
                family=ipaddress.ip_network(prefix).version,
                source_ips=len(source_ips),
            )
            for prefix, source_ips in networks.items()
        ]

        return sorted(routes, key=lambda route: (route.family, route.prefix))
