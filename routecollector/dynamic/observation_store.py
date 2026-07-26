"""
Persist matched dynamic DNS observations through RouteCollector repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from routecollector.dynamic.dns_observation import (
    DynamicDnsObservation,
)


class ServiceLike(Protocol):
    """Minimum service fields required by the store."""

    id: int
    name: str
    enabled: bool


class DynamicRepository(Protocol):
    """Repository operations required for dynamic observations."""

    def list_services(
        self,
    ) -> list[ServiceLike]:
        """Return configured services."""

    def upsert_domain(
        self,
        service_id: int,
        domain: str,
        source: str,
        active: bool = True,
    ) -> int:
        """Create or reactivate a domain."""

    def add_observation(
        self,
        domain_id: int | None,
        ip: str,
        source: str,
        dns_server: str | None,
        ttl: int | None,
        confidence: int = 1,
    ) -> int:
        """Create or update one IP observation."""


@dataclass(slots=True, frozen=True)
class DynamicStoreResult:
    """Summary of one dynamic observation write batch."""

    received: int
    stored: int
    domains_touched: int
    services_touched: int
    skipped_duplicates: int


class DynamicObservationStore:
    """Store matched DNS answers using existing repository methods."""

    def __init__(
        self,
        repository: DynamicRepository,
        *,
        confidence: int = 100,
    ) -> None:
        if confidence < 1:
            raise ValueError(
                "Dynamic observation confidence must be positive"
            )

        self._repository = repository
        self._confidence = confidence

    def store(
        self,
        observations: Sequence[DynamicDnsObservation],
        *,
        dns_server: str | None = None,
    ) -> DynamicStoreResult:
        """Persist one batch of matched DNS observations."""

        services = {
            service.name: service
            for service in self._repository.list_services()
            if service.enabled
        }

        unique_observations: list[DynamicDnsObservation] = []
        seen: set[tuple[str, str, str]] = set()

        for observation in observations:
            key = (
                observation.service_name,
                observation.query_name,
                observation.ip,
            )

            if key in seen:
                continue

            seen.add(key)
            unique_observations.append(observation)

        domain_ids: dict[tuple[int, str], int] = {}
        touched_services: set[str] = set()
        stored = 0

        for observation in unique_observations:
            service = services.get(
                observation.service_name
            )

            if service is None:
                raise ValueError(
                    "Dynamic observation references unknown or "
                    f"disabled service: {observation.service_name}"
                )

            domain_key = (
                service.id,
                observation.query_name,
            )

            domain_id = domain_ids.get(domain_key)

            if domain_id is None:
                domain_id = self._repository.upsert_domain(
                    service_id=service.id,
                    domain=observation.query_name,
                    source=observation.source,
                    active=True,
                )
                domain_ids[domain_key] = domain_id

            self._repository.add_observation(
                domain_id=domain_id,
                ip=observation.ip,
                source=observation.source,
                dns_server=dns_server,
                ttl=observation.ttl,
                confidence=self._confidence,
            )

            touched_services.add(
                observation.service_name
            )
            stored += 1

        return DynamicStoreResult(
            received=len(observations),
            stored=stored,
            domains_touched=len(domain_ids),
            services_touched=len(touched_services),
            skipped_duplicates=(
                len(observations) - len(unique_observations)
            ),
        )
