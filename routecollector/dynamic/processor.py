"""
Process one DNS response through the dynamic RouteCollector pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Iterable, Protocol

from routecollector.dynamic.dns_observation import (
    DnsAnswerRecord,
    build_dynamic_observations,
)
from routecollector.dynamic.domain_matcher import DomainMatcher
from routecollector.dynamic.observation_store import (
    DynamicObservationStore,
    DynamicStoreResult,
)
from routecollector.dynamic.publisher import DynamicPublishResult


class DynamicPublisherLike(Protocol):
    """Publisher interface required by the processor."""

    def publish(self) -> DynamicPublishResult:
        """Publish the current dynamic route plan."""


@dataclass(slots=True, frozen=True)
class DynamicProcessResult:
    """Result of processing one DNS response."""

    query_name: str
    matched: bool
    observations_built: int
    store_result: DynamicStoreResult | None
    publish_result: DynamicPublishResult | None

    @property
    def published(self) -> bool:
        """Return whether publication was attempted."""

        return self.publish_result is not None


class DynamicDnsProcessor:
    """
    Convert one DNS response into observations and publish routes.

    Publication is serialized so concurrent DNS requests cannot install
    or reload BIRD configuration at the same time.
    """

    def __init__(
        self,
        *,
        matcher: DomainMatcher,
        store: DynamicObservationStore,
        publisher: DynamicPublisherLike,
        enable_ipv6: bool = False,
        global_only: bool = True,
        publish_empty: bool = False,
    ) -> None:
        self._matcher = matcher
        self._store = store
        self._publisher = publisher
        self._enable_ipv6 = enable_ipv6
        self._global_only = global_only
        self._publish_empty = publish_empty
        self._publish_lock = Lock()

    def process(
        self,
        *,
        query_name: str,
        records: Iterable[DnsAnswerRecord],
        dns_server: str | None = None,
    ) -> DynamicProcessResult:
        """Process one DNS response synchronously."""

        observations = build_dynamic_observations(
            query_name=query_name,
            records=tuple(records),
            matcher=self._matcher,
            enable_ipv6=self._enable_ipv6,
            global_only=self._global_only,
        )

        if not observations:
            return DynamicProcessResult(
                query_name=query_name,
                matched=self._matcher.matches(query_name),
                observations_built=0,
                store_result=None,
                publish_result=(
                    self._publish()
                    if self._publish_empty
                    else None
                ),
            )

        store_result = self._store.store(
            observations,
            dns_server=dns_server,
        )

        return DynamicProcessResult(
            query_name=observations[0].query_name,
            matched=True,
            observations_built=len(observations),
            store_result=store_result,
            publish_result=self._publish(),
        )

    def _publish(self) -> DynamicPublishResult:
        """Serialize BIRD publication."""

        with self._publish_lock:
            return self._publisher.publish()
