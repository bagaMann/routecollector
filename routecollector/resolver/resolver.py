"""
DNS resolver module.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress

import dns.exception
import dns.resolver

from routecollector.core.repository import Domain, Repository


@dataclass(slots=True, frozen=True)
class ResolveResult:
    """DNS resolve result."""

    domain: str
    record_type: str
    ip: str
    ttl: int
    dns_server: str


class DnsResolver:
    """Resolve domains and store observations."""

    def __init__(
        self,
        repository: Repository,
        dns_servers: list[str] | None = None,
        timeout: float = 3.0,
        lifetime: float = 5.0,
    ) -> None:
        self._repository = repository
        self._dns_servers = dns_servers or ["8.8.8.8", "1.1.1.1"]
        self._timeout = timeout
        self._lifetime = lifetime

    def resolve_all(self, service_name: str | None = None) -> tuple[int, int]:
        """Resolve all domains from repository.

        Returns:
            tuple[int, int]: Number of domains processed and observations stored.
        """

        domains = self._repository.list_domains(service_name)
        observation_count = 0

        for domain in domains:
            results = self.resolve_domain(domain)

            for result in results:
                self._repository.add_observation(
                    domain_id=domain.id,
                    ip=result.ip,
                    source="resolver",
                    dns_server=result.dns_server,
                    ttl=result.ttl,
                    confidence=1,
                )
                observation_count += 1

        return len(domains), observation_count

    def resolve_domain(self, domain: Domain) -> list[ResolveResult]:
        """Resolve single domain."""

        results: list[ResolveResult] = []

        for dns_server in self._dns_servers:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [dns_server]
            resolver.timeout = self._timeout
            resolver.lifetime = self._lifetime

            for record_type in ("A", "AAAA"):
                try:
                    answer = resolver.resolve(domain.domain, record_type)
                except (
                    dns.resolver.NXDOMAIN,
                    dns.resolver.NoAnswer,
                    dns.resolver.NoNameservers,
                    dns.exception.Timeout,
                ):
                    continue

                ttl = int(answer.rrset.ttl) if answer.rrset else 0

                for item in answer:
                    ip = str(item)

                    try:
                        ipaddress.ip_address(ip)
                    except ValueError:
                        continue

                    results.append(
                        ResolveResult(
                            domain=domain.domain,
                            record_type=record_type,
                            ip=ip,
                            ttl=ttl,
                            dns_server=dns_server,
                        )
                    )

        return results
