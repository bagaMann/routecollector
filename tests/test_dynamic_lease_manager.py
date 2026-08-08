"""
Tests for dynamic route lease reconciliation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from routecollector.dynamic import (
    DynamicLeaseManager,
    DynamicPublishResult,
    DynamicRouteCache,
    DynamicRouteLeaseStore,
)


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


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def publish(
        self,
        required_prefixes: Iterable[str] = (),
    ) -> DynamicPublishResult:
        requested = tuple(
            sorted(required_prefixes)
        )
        self.calls.append(requested)

        return DynamicPublishResult(
            route_stats_built=10,
            planned_routes=50,
            generated_config=Path(
                "bird/routecollector.conf"
            ),
            generated_changed=True,
            installed_config=Path(
                "/etc/bird/routecollector.conf"
            ),
            installed_changed=True,
            bird_checked=True,
            bird_reloaded=True,
            rollback_performed=False,
            dynamic_requested_prefixes=requested,
            dynamic_published_prefixes=requested,
            dynamic_rejected_prefixes=(),
        )


def test_manager_republishes_only_active_leases(
    tmp_path: Path,
) -> None:
    clock = Clock()
    store = DynamicRouteLeaseStore(
        tmp_path / "leases.json",
        lease_seconds=3600,
        now=clock.now,
    )

    store.renew(
        [
            "85.249.244.0/24",
            "172.217.131.0/24",
        ]
    )

    clock.value += timedelta(
        seconds=1800
    )

    store.renew(
        ["172.217.131.0/24"]
    )

    clock.value += timedelta(
        seconds=1800
    )

    cache = DynamicRouteCache(
        [
            "85.249.244.0/24",
            "172.217.131.0/24",
        ]
    )
    publisher = FakePublisher()

    manager = DynamicLeaseManager(
        store=store,
        publisher=publisher,
        route_cache=cache,
    )

    result = manager.reconcile_once()

    assert result is not None
    assert publisher.calls == [
        (
            "172.217.131.0/24",
        )
    ]
    assert not cache.contains(
        "85.249.244.0/24"
    )
    assert cache.contains(
        "172.217.131.0/24"
    )
    assert store.expired_prefixes() == ()
