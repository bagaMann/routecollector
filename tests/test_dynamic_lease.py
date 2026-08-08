"""
Tests for persistent dynamic route leases.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from routecollector.dynamic import DynamicRouteLeaseStore


class Clock:
    def __init__(self) -> None:
        self.value = datetime(
            2026,
            8,
            8,
            12,
            0,
            0,
        )

    def now(self) -> datetime:
        return self.value

    def advance(
        self,
        seconds: int,
    ) -> None:
        self.value += timedelta(
            seconds=seconds
        )


def test_lease_store_renews_and_expires(
    tmp_path: Path,
) -> None:
    clock = Clock()
    store = DynamicRouteLeaseStore(
        tmp_path / "leases.json",
        lease_seconds=3600,
        now=clock.now,
    )

    store.renew(
        ["85.249.244.44/24"]
    )

    assert store.active_prefixes() == (
        "85.249.244.0/24",
    )
    assert store.expired_prefixes() == ()

    clock.advance(3600)

    assert store.active_prefixes() == ()
    assert store.expired_prefixes() == (
        "85.249.244.0/24",
    )


def test_lease_store_persists_across_instances(
    tmp_path: Path,
) -> None:
    clock = Clock()
    path = tmp_path / "leases.json"

    DynamicRouteLeaseStore(
        path,
        lease_seconds=3600,
        now=clock.now,
    ).renew(
        ["172.217.131.0/24"]
    )

    second = DynamicRouteLeaseStore(
        path,
        lease_seconds=3600,
        now=clock.now,
    )

    assert second.active_prefixes() == (
        "172.217.131.0/24",
    )


def test_renew_extends_existing_lease(
    tmp_path: Path,
) -> None:
    clock = Clock()
    store = DynamicRouteLeaseStore(
        tmp_path / "leases.json",
        lease_seconds=3600,
        now=clock.now,
    )

    first = store.renew(
        ["85.249.244.0/24"]
    )[0]

    clock.advance(1800)

    second = store.renew(
        ["85.249.244.0/24"]
    )[0]

    assert second.expires_at > first.expires_at
