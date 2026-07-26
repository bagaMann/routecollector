"""
Match observed DNS names to configured services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True, frozen=True)
class DomainMatchRule:
    """Dynamic DNS matching rule for one service."""

    service_name: str
    domains: tuple[str, ...]
    include_subdomains: bool = True

    def __post_init__(self) -> None:
        if not self.service_name.strip():
            raise ValueError(
                "Service name cannot be empty"
            )

        if not self.domains:
            raise ValueError(
                "Domain match rule requires at least one domain"
            )


@dataclass(slots=True, frozen=True)
class DomainMatch:
    """Result of matching one DNS query name."""

    service_name: str
    query_name: str
    matched_domain: str


class DomainMatcher:
    """Match exact domains and their subdomains."""

    def __init__(
        self,
        rules: Iterable[DomainMatchRule],
    ) -> None:
        normalized: list[DomainMatchRule] = []

        for rule in rules:
            domains = tuple(
                sorted(
                    {
                        self.normalize_domain(domain)
                        for domain in rule.domains
                    },
                    key=lambda value: (
                        -value.count("."),
                        -len(value),
                        value,
                    ),
                )
            )

            normalized.append(
                DomainMatchRule(
                    service_name=rule.service_name.strip(),
                    domains=domains,
                    include_subdomains=rule.include_subdomains,
                )
            )

        self._rules = tuple(normalized)

    def match(
        self,
        query_name: str,
    ) -> tuple[DomainMatch, ...]:
        """Return every service matching the queried domain."""

        normalized_query = self.normalize_domain(
            query_name
        )
        matches: list[DomainMatch] = []
        seen_services: set[str] = set()

        for rule in self._rules:
            for domain in rule.domains:
                exact = normalized_query == domain
                subdomain = (
                    rule.include_subdomains
                    and normalized_query.endswith(
                        f".{domain}"
                    )
                )

                if not exact and not subdomain:
                    continue

                if rule.service_name in seen_services:
                    break

                seen_services.add(rule.service_name)

                matches.append(
                    DomainMatch(
                        service_name=rule.service_name,
                        query_name=normalized_query,
                        matched_domain=domain,
                    )
                )
                break

        return tuple(matches)

    def matches(
        self,
        query_name: str,
    ) -> bool:
        """Return whether at least one service matches."""

        return bool(self.match(query_name))

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Normalize a DNS name for comparison."""

        normalized = domain.strip().rstrip(".").lower()

        if not normalized:
            raise ValueError(
                "Domain cannot be empty"
            )

        if len(normalized) > 253:
            raise ValueError(
                "Domain exceeds maximum DNS name length"
            )

        labels = normalized.split(".")

        for label in labels:
            if not label:
                raise ValueError(
                    f"Invalid empty DNS label: {domain}"
                )

            if len(label) > 63:
                raise ValueError(
                    f"DNS label is too long: {label}"
                )

        return normalized
