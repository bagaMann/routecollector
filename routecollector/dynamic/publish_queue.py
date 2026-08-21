"""
Debounced publication queue for dynamic DNS route changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network
from threading import Condition, Event, Thread
from time import monotonic
from typing import Iterable, Protocol

from routecollector.dynamic.publisher import DynamicPublishResult
from routecollector.dynamic.route_cache import DynamicRouteCache


IPNetwork = IPv4Network | IPv6Network


class DynamicPublishQueueError(RuntimeError):
    """Queued dynamic publication failed."""


class DynamicPublisherLike(Protocol):
    def publish(
        self,
        required_prefixes: Iterable[str] = (),
    ) -> DynamicPublishResult:
        ...


class DynamicLeaseStoreLike(Protocol):
    def renew(
        self,
        prefixes: Iterable[str],
    ) -> object:
        ...


@dataclass(slots=True, frozen=True)
class DynamicQueueResult:
    requested_prefixes: tuple[IPNetwork, ...]
    missing_prefixes: tuple[IPNetwork, ...]
    published: bool
    publish_result: DynamicPublishResult | None


@dataclass(slots=True)
class _Waiter:
    requested: tuple[IPNetwork, ...]
    missing: tuple[IPNetwork, ...]
    event: Event
    result: DynamicPublishResult | None = None
    error: BaseException | None = None


class DynamicPublishQueue:
    """Batch concurrent dynamic publications and maintain route leases."""

    def __init__(
        self,
        *,
        publisher: DynamicPublisherLike,
        route_cache: DynamicRouteCache,
        lease_store: DynamicLeaseStoreLike | None = None,
        debounce_seconds: float = 0.25,
        wait_timeout_seconds: float = 10.0,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError(
                "Debounce interval cannot be negative"
            )
        if wait_timeout_seconds <= 0:
            raise ValueError(
                "Publish wait timeout must be positive"
            )

        self._publisher = publisher
        self._route_cache = route_cache
        self._lease_store = lease_store
        self._debounce_seconds = debounce_seconds
        self._wait_timeout_seconds = wait_timeout_seconds

        self._condition = Condition()
        self._pending: set[IPNetwork] = set()
        self._inflight: set[IPNetwork] = set()
        self._waiters: list[_Waiter] = []
        self._stopping = False

        self._worker = Thread(
            target=self._run,
            name="routecollector-dynamic-publisher",
            daemon=True,
        )
        self._worker.start()

    def submit(
        self,
        prefixes: Iterable[str | IPNetwork],
    ) -> DynamicQueueResult:
        requested = self._normalize(prefixes)
        deadline = monotonic() + self._wait_timeout_seconds

        while True:
            with self._condition:
                if self._stopping:
                    raise DynamicPublishQueueError(
                        "Dynamic publish queue is stopping"
                    )

                missing = self._route_cache.missing(
                    requested
                )

                if not missing:
                    self._renew_leases(requested)

                    return DynamicQueueResult(
                        requested_prefixes=requested,
                        missing_prefixes=(),
                        published=False,
                        publish_result=None,
                    )

                if any(
                    prefix in self._inflight
                    for prefix in missing
                ):
                    remaining = deadline - monotonic()

                    if remaining <= 0:
                        raise DynamicPublishQueueError(
                            "Timed out waiting for in-flight "
                            "dynamic route publication"
                        )

                    self._condition.wait(remaining)
                    continue

                waiter = _Waiter(
                    requested=requested,
                    missing=missing,
                    event=Event(),
                )

                self._pending.update(missing)
                self._waiters.append(waiter)
                self._condition.notify()
                break

        remaining = deadline - monotonic()

        if remaining <= 0 or not waiter.event.wait(remaining):
            raise DynamicPublishQueueError(
                "Timed out waiting for dynamic route publication"
            )

        if waiter.error is not None:
            raise DynamicPublishQueueError(
                f"Dynamic route publication failed: {waiter.error}"
            ) from waiter.error

        return DynamicQueueResult(
            requested_prefixes=requested,
            missing_prefixes=missing,
            published=True,
            publish_result=waiter.result,
        )

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()

        self._worker.join(
            timeout=self._wait_timeout_seconds
        )

    @property
    def running(self) -> bool:
        return self._worker.is_alive()

    def _run(self) -> None:
        while True:
            with self._condition:
                while (
                    not self._pending
                    and not self._stopping
                ):
                    self._condition.wait()

                if self._stopping:
                    error = DynamicPublishQueueError(
                        "Dynamic publish queue stopped"
                    )
                    waiters = self._waiters
                    self._waiters = []
                    self._pending.clear()

                    for waiter in waiters:
                        waiter.error = error
                        waiter.event.set()

                    return

                deadline = (
                    monotonic()
                    + self._debounce_seconds
                )

                while not self._stopping:
                    remaining = deadline - monotonic()

                    if remaining <= 0:
                        break

                    self._condition.wait(remaining)

                batch_prefixes = tuple(
                    self._pending
                )
                batch_waiters = self._waiters
                self._pending = set()
                self._waiters = []
                self._inflight = set(batch_prefixes)

            try:
                result = self._publisher.publish(
                    str(prefix)
                    for prefix in batch_prefixes
                )

                self._route_cache.add(
                    result.dynamic_published_prefixes
                )
                self._renew_leases(
                    result.dynamic_published_prefixes
                )

                for waiter in batch_waiters:
                    waiter.result = result
                    waiter.event.set()

            except BaseException as exc:
                for waiter in batch_waiters:
                    waiter.error = exc
                    waiter.event.set()

            finally:
                with self._condition:
                    self._inflight.clear()
                    self._condition.notify_all()

    def _renew_leases(
        self,
        prefixes: Iterable[str | IPNetwork],
    ) -> None:
        if self._lease_store is None:
            return

        self._lease_store.renew(
            str(prefix)
            for prefix in prefixes
        )

    @staticmethod
    def _normalize(
        prefixes: Iterable[str | IPNetwork],
    ) -> tuple[IPNetwork, ...]:
        cache = DynamicRouteCache(prefixes)
        return cache.snapshot()
