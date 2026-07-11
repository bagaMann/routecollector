"""
Manual domain source plugin.
"""

from __future__ import annotations

from collections.abc import Iterable

from routecollector.sources.base import (
    DomainSource,
    DomainSourceError,
    DomainSourceRequest,
    DomainSourceResult,
)


class ManualDomainSource(DomainSource):
    """Load manually configured domains from source options."""

    @property
    def name(self) -> str:
        """Return unique source name."""

        return "manual"

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        """Load domains from the ``domains`` source option."""

        raw_domains = request.source_options.get("domains", [])

        if isinstance(raw_domains, str):
            values: Iterable[object] = [raw_domains]
        elif isinstance(raw_domains, (list, tuple, set, frozenset)):
            values = raw_domains
        else:
            raise DomainSourceError(
                "manual source option 'domains' must be a string or list"
            )

        domains: list[str] = []

        for value in values:
            if not isinstance(value, str):
                raise DomainSourceError(
                    "manual source domains must contain only strings"
                )

            domains.append(value)

        normalized_domains = self.normalize_domains(domains)

        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=normalized_domains,
            metadata={
                "input_count": len(domains),
                "domain_count": len(normalized_domains),
            },
        )
