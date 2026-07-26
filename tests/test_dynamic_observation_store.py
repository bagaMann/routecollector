"""
Tests for dynamic DNS observation persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from routecollector.dynamic import (
    DynamicDnsObservation,
    DynamicObservationStore,
)


@dataclass(slots=True)
class FakeService:
    id: int
    name: str
    enabled: bool = True


class FakeRepository:
    def __init__(self) -> None:
        self.services = [
            FakeService(
                id=1,
                name="youtube",
            ),
            FakeService(
                id=2,
                name="disabled",
                enabled=False,
            ),
        ]
        self.domain_calls: list[dict[str, Any]] = []
        self.observation_calls: list[dict[str, Any]] = []
        self._next_domain_id = 100

    def list_services(
        self,
    ) -> list[FakeService]:
        return self.services

    def upsert_domain(
        self,
        service_id: int,
        domain: str,
        source: str,
        active: bool = True,
    ) -> int:
        self.domain_calls.append(
            {
                "service_id": service_id,
                "domain": domain,
                "source": source,
                "active": active,
            }
        )

        domain_id = self._next_domain_id
        self._next_domain_id += 1
        return domain_id

    def add_observation(
        self,
        domain_id: int | None,
        ip: str,
        source: str,
        dns_server: str | None,
        ttl: int | None,
        confidence: int = 1,
    ) -> int:
        self.observation_calls.append(
            {
                "domain_id": domain_id,
                "ip": ip,
                "source": source,
                "dns_server": dns_server,
                "ttl": ttl,
                "confidence": confidence,
            }
        )
        return len(self.observation_calls)


def make_observation(
    *,
    ip: str = "142.250.74.238",
    query_name: str = (
        "rr2---sn-test.googlevideo.com"
    ),
    service_name: str = "youtube",
    ttl: int = 120,
) -> DynamicDnsObservation:
    return DynamicDnsObservation(
        service_name=service_name,
        query_name=query_name,
        matched_domain="googlevideo.com",
        record_type="A",
        ip=ip,
        ttl=ttl,
    )


def test_store_persists_domain_and_observation() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(
        repository,
        confidence=100,
    )

    result = store.store(
        [make_observation()],
        dns_server="1.1.1.1",
    )

    assert result.received == 1
    assert result.stored == 1
    assert result.domains_touched == 1
    assert result.services_touched == 1
    assert result.skipped_duplicates == 0

    assert repository.domain_calls == [
        {
            "service_id": 1,
            "domain": (
                "rr2---sn-test.googlevideo.com"
            ),
            "source": "dynamic-dns",
            "active": True,
        }
    ]

    assert repository.observation_calls == [
        {
            "domain_id": 100,
            "ip": "142.250.74.238",
            "source": "dynamic-dns",
            "dns_server": "1.1.1.1",
            "ttl": 120,
            "confidence": 100,
        }
    ]


def test_store_reuses_domain_within_batch() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(repository)

    result = store.store(
        [
            make_observation(
                ip="142.250.74.238",
            ),
            make_observation(
                ip="142.250.74.206",
            ),
        ]
    )

    assert result.stored == 2
    assert result.domains_touched == 1
    assert len(repository.domain_calls) == 1
    assert len(repository.observation_calls) == 2

    assert {
        call["ip"]
        for call in repository.observation_calls
    } == {
        "142.250.74.238",
        "142.250.74.206",
    }


def test_store_deduplicates_identical_observation() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(repository)

    observation = make_observation()

    result = store.store(
        [
            observation,
            observation,
        ]
    )

    assert result.received == 2
    assert result.stored == 1
    assert result.skipped_duplicates == 1
    assert len(repository.observation_calls) == 1


def test_store_keeps_same_ip_for_different_domains() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(repository)

    result = store.store(
        [
            make_observation(
                query_name=(
                    "rr1.googlevideo.com"
                ),
            ),
            make_observation(
                query_name=(
                    "rr2.googlevideo.com"
                ),
            ),
        ]
    )

    assert result.stored == 2
    assert result.domains_touched == 2
    assert len(repository.domain_calls) == 2


def test_store_rejects_unknown_service() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(repository)

    with pytest.raises(
        ValueError,
        match="unknown or disabled service",
    ):
        store.store(
            [
                make_observation(
                    service_name="missing",
                )
            ]
        )


def test_store_rejects_disabled_service() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(repository)

    with pytest.raises(
        ValueError,
        match="unknown or disabled service",
    ):
        store.store(
            [
                make_observation(
                    service_name="disabled",
                )
            ]
        )


def test_store_accepts_empty_batch() -> None:
    repository = FakeRepository()
    store = DynamicObservationStore(repository)

    result = store.store([])

    assert result.received == 0
    assert result.stored == 0
    assert result.domains_touched == 0
    assert result.services_touched == 0
    assert result.skipped_duplicates == 0

    assert repository.domain_calls == []
    assert repository.observation_calls == []


def test_store_rejects_non_positive_confidence() -> None:
    repository = FakeRepository()

    with pytest.raises(
        ValueError,
        match="must be positive",
    ):
        DynamicObservationStore(
            repository,
            confidence=0,
        )


def test_store_counts_multiple_services() -> None:
    repository = FakeRepository()
    repository.services.append(
        FakeService(
            id=3,
            name="google",
        )
    )

    store = DynamicObservationStore(repository)

    result = store.store(
        [
            make_observation(
                service_name="youtube",
            ),
            make_observation(
                service_name="google",
            ),
        ]
    )

    assert result.stored == 2
    assert result.services_touched == 2
