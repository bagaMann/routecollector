"""
Tests for debounced dynamic route publication.
"""

from __future__ import annotations

from pathlib import Path
from threading import Barrier, Thread
from typing import Iterable

from routecollector.dynamic import (
    DynamicPublishQueue,
    DynamicPublishResult,
    DynamicRouteCache,
)


class FakePublisher:
    def __init__(
        self,
        *,
        accept: bool = True,
    ) -> None:
        self.calls = 0
        self.accept = accept
        self.requested: list[tuple[str, ...]] = []

    def publish(
        self,
        required_prefixes: Iterable[str] = (),
    ) -> DynamicPublishResult:
        self.calls += 1
        requested = tuple(
            sorted(required_prefixes)
        )
        self.requested.append(requested)

        return DynamicPublishResult(
            route_stats_built=100,
            planned_routes=52,
            generated_config=Path(
                "bird/routecollector.conf"
            ),
            generated_changed=self.accept,
            installed_config=Path(
                "/etc/bird/routecollector.conf"
            ),
            installed_changed=self.accept,
            bird_checked=True,
            bird_reloaded=self.accept,
            rollback_performed=False,
            dynamic_requested_prefixes=requested,
            dynamic_published_prefixes=(
                requested
                if self.accept
                else ()
            ),
            dynamic_rejected_prefixes=(
                ()
                if self.accept
                else requested
            ),
        )


class FakeLeaseStore:
    def __init__(self) -> None:
        self.renewed: list[tuple[str, ...]] = []

    def renew(
        self,
        prefixes: Iterable[str],
    ) -> object:
        renewed = tuple(
            sorted(prefixes)
        )
        self.renewed.append(renewed)
        return renewed


def test_known_prefix_returns_without_publish() -> None:
    publisher = FakePublisher()
    cache = DynamicRouteCache(
        ["142.250.74.0/24"]
    )
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        debounce_seconds=0.01,
    )

    try:
        result = queue.submit(
            ["142.250.74.238/24"]
        )
    finally:
        queue.stop()

    assert result.published is False
    assert result.publish_result is None
    assert publisher.calls == 0


def test_known_prefix_renews_lease_without_publish() -> None:
    publisher = FakePublisher()
    lease_store = FakeLeaseStore()
    cache = DynamicRouteCache(
        ["142.250.74.0/24"]
    )
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        lease_store=lease_store,
        debounce_seconds=0.01,
    )

    try:
        result = queue.submit(
            ["142.250.74.238/24"]
        )
    finally:
        queue.stop()

    assert result.published is False
    assert publisher.calls == 0
    assert lease_store.renewed == [
        ("142.250.74.0/24",)
    ]


def test_missing_prefix_is_published_and_cached() -> None:
    publisher = FakePublisher()
    cache = DynamicRouteCache()
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        debounce_seconds=0.01,
    )

    try:
        result = queue.submit(
            ["142.250.74.238/24"]
        )
        second = queue.submit(
            ["142.250.74.1/24"]
        )
    finally:
        queue.stop()

    assert result.published is True
    assert second.published is False
    assert publisher.calls == 1


def test_missing_prefix_renews_lease_after_publish() -> None:
    publisher = FakePublisher()
    lease_store = FakeLeaseStore()
    cache = DynamicRouteCache()
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        lease_store=lease_store,
        debounce_seconds=0.01,
    )

    try:
        result = queue.submit(
            ["142.250.74.238/24"]
        )
    finally:
        queue.stop()

    assert result.published is True
    assert publisher.calls == 1
    assert lease_store.renewed == [
        ("142.250.74.0/24",)
    ]


def test_rejected_prefix_is_not_cached() -> None:
    publisher = FakePublisher(
        accept=False
    )
    cache = DynamicRouteCache()
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        debounce_seconds=0.01,
    )

    try:
        first = queue.submit(
            ["142.250.74.0/24"]
        )
        second = queue.submit(
            ["142.250.74.0/24"]
        )
    finally:
        queue.stop()

    assert first.published is True
    assert second.published is True
    assert publisher.calls == 2
    assert not cache.contains(
        "142.250.74.0/24"
    )


def test_concurrent_requests_share_one_publish() -> None:
    publisher = FakePublisher()
    cache = DynamicRouteCache()
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        debounce_seconds=0.05,
    )
    barrier = Barrier(3)
    results: list[object] = []

    def submit(prefix: str) -> None:
        barrier.wait()
        results.append(
            queue.submit([prefix])
        )

    threads = [
        Thread(
            target=submit,
            args=("142.250.74.0/24",),
        ),
        Thread(
            target=submit,
            args=("173.194.221.0/24",),
        ),
    ]

    for thread in threads:
        thread.start()

    barrier.wait()

    for thread in threads:
        thread.join()

    queue.stop()

    assert len(results) == 2
    assert publisher.calls == 1
    assert cache.contains(
        "142.250.74.0/24"
    )
    assert cache.contains(
        "173.194.221.0/24"
    )
