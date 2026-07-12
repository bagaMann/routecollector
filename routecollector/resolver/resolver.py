"""
DNS resolver module.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import ipaddress

import dns.exception
import dns.resolver

from routecollector.core.repository import (
    Domain,
    ObservationInput,
    Repository,
)


@dataclass(slots=True, frozen=True)
class ResolveResult:
    """DNS resolve result."""

    domain: str
    record_type: str
    ip: str
    ttl: int
    dns_server: str


class DnsResolver:
    """Resolve domains and store observations in one transaction."""

    def __init__(
        self,
        repository: Repository,
        dns_servers: list[str] | None = None,
        timeout: float = 3.0,
        lifetime: float = 5.0,
        enable_ipv6: bool = False,
        progress_every: int = 25,
    ) -> None:
        if progress_every <= 0:
            raise ValueError("Progress interval must be greater than zero")

        self._repository = repository
        self._dns_servers = dns_servers or ["8.8.8.8", "1.1.1.1"]
        self._timeout = timeout
        self._lifetime = lifetime
        self._enable_ipv6 = enable_ipv6
        self._progress_every = progress_every

    def resolve_all(
        self,
        service_name: str | None = None,
    ) -> tuple[int, int]:
        """Resolve unique domains and batch-store observations."""

        domain_rows = self._repository.list_domains(service_name)

        domains_by_name: dict[str, list[Domain]] = defaultdict(list)

        for domain in domain_rows:
            domains_by_name[domain.domain].append(domain)

        unique_domains = sorted(domains_by_name)
        pending: list[ObservationInput] = []
        total = len(unique_domains)

        for index, domain_name in enumerate(unique_domains, start=1):
            representative = domains_by_name[domain_name][0]
            results = self.resolve_domain(representative)

            for domain in domains_by_name[domain_name]:
                for result in results:
                    pending.append(
                        ObservationInput(
                            domain_id=domain.id,
                            ip=result.ip,
                            source="resolver",
                            dns_server=result.dns_server,
                            ttl=result.ttl,
                            confidence=1,
                        )
                    )

            if index % self._progress_every == 0 or index == total:
                print(
                    "Resolving domains: "
                    f"{index}/{total}; "
                    f"observations prepared: {len(pending)}",
                    flush=True,
                )

        print(
            f"Writing {len(pending)} observations to SQLite...",
            flush=True,
        )

        stored = self._repository.add_observations(pending)

        print(
            f"Observation batch committed: {stored}",
            flush=True,
        )

        return total, stored

    def resolve_domain(self, domain: Domain) -> list[ResolveResult]:
        """Resolve one domain through configured DNS servers."""

        results: list[ResolveResult] = []
        record_types = ["A"]

        if self._enable_ipv6:
            record_types.append("AAAA")

        for dns_server in self._dns_servers:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [dns_server]
            resolver.timeout = self._timeout
            resolver.lifetime = self._lifetime

            for record_type in record_types:
                try:
                    answer = resolver.resolve(
                        domain.domain,
                        record_type,
                    )
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
                        address = ipaddress.ip_address(ip)
                    except ValueError:
                        continue

                    if not address.is_global:
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
