"""
Build dynamic RouteCollector observations from DNS answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Iterable

from routecollector.dynamic.domain_matcher import DomainMatcher


IPAddress = IPv4Address | IPv6Address


@dataclass(slots=True, frozen=True)
class DnsAnswerRecord:
    """One address record extracted from a DNS response."""

    record_type: str
    value: str
    ttl: int

    def __post_init__(self) -> None:
        normalized_type = self.record_type.strip().upper()

        if normalized_type not in {"A", "AAAA"}:
            raise ValueError(
                f"Unsupported DNS record type: {self.record_type}"
            )

        if self.ttl < 0:
            raise ValueError(
                "DNS TTL cannot be negative"
            )

        address = ip_address(self.value.strip())

        if normalized_type == "A" and address.version != 4:
            raise ValueError(
                "A record must contain an IPv4 address"
            )

        if normalized_type == "AAAA" and address.version != 6:
            raise ValueError(
                "AAAA record must contain an IPv6 address"
            )

        object.__setattr__(
            self,
            "record_type",
            normalized_type,
        )
        object.__setattr__(
            self,
            "value",
            str(address),
        )


@dataclass(slots=True, frozen=True)
class DynamicDnsObservation:
    """Address observation associated with a matched service."""

    service_name: str
    query_name: str
    matched_domain: str
    record_type: str
    ip: str
    ttl: int
    source: str = "dynamic-dns"

    @property
    def family(self) -> int:
        """Return IP family number."""

        return ip_address(self.ip).version


def build_dynamic_observations(
    *,
    query_name: str,
    records: Iterable[DnsAnswerRecord],
    matcher: DomainMatcher,
    enable_ipv6: bool = False,
    global_only: bool = True,
) -> tuple[DynamicDnsObservation, ...]:
    """
    Match one DNS query and build service observations.

    One DNS response may belong to multiple services. Duplicate
    service/IP pairs are emitted only once.
    """

    matches = matcher.match(query_name)

    if not matches:
        return ()

    observations: list[DynamicDnsObservation] = []
    seen: set[tuple[str, str]] = set()

    for record in records:
        address = ip_address(record.value)

        if address.version == 6 and not enable_ipv6:
            continue

        if global_only and not address.is_global:
            continue

        for match in matches:
            key = (
                match.service_name,
                str(address),
            )

            if key in seen:
                continue

            seen.add(key)

            observations.append(
                DynamicDnsObservation(
                    service_name=match.service_name,
                    query_name=match.query_name,
                    matched_domain=match.matched_domain,
                    record_type=record.record_type,
                    ip=str(address),
                    ttl=record.ttl,
                )
            )

    return tuple(observations)
