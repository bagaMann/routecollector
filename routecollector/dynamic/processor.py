"""
Process one DNS response through the dynamic RouteCollector pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network
from threading import Lock
from typing import Iterable, Protocol

from routecollector.dynamic.dns_observation import (
    DnsAnswerRecord,
    DynamicDnsObservation,
    build_dynamic_observations,
)
from routecollector.dynamic.domain_matcher import DomainMatcher
from routecollector.dynamic.observation_store import (
    DynamicObservationStore,
    DynamicStoreResult,
)
from routecollector.dynamic.publish_queue import (
    DynamicPublishQueue,
)
from routecollector.dynamic.publisher import (
    DynamicPublishResult,
)


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
    publication_required: bool = False

    @property
    def published(self) -> bool:
        """Return whether a publication cycle ran."""

        return self.publish_result is not None


class DynamicDnsProcessor:
    """
    Convert one DNS response into observations and publish routes.

    A publish queue may be supplied to skip publication for prefixes
    already present in the active route plan and debounce new prefixes.
    """

    def __init__(
        self,
        *,
        matcher: DomainMatcher,
        store: DynamicObservationStore,
        publisher: DynamicPublisherLike | None = None,
        publish_queue: DynamicPublishQueue | None = None,
        enable_ipv6: bool = False,
        global_only: bool = True,
        publish_empty: bool = False,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> None:
        if publisher is None and publish_queue is None:
            raise ValueError(
                "Publisher or publish queue is required"
            )

        if publisher is not None and publish_queue is not None:
            raise ValueError(
                "Publisher and publish queue are mutually exclusive"
            )

        self._matcher = matcher
        self._store = store
        self._publisher = publisher
        self._publish_queue = publish_queue
        self._enable_ipv6 = enable_ipv6
        self._global_only = global_only
        self._publish_empty = publish_empty
        self._ipv4_prefix = ipv4_prefix
        self._ipv6_prefix = ipv6_prefix
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
                    self._publish_direct()
                    if self._publish_empty
                    and self._publisher is not None
                    else None
                ),
                publication_required=False,
            )

        store_result = self._store.store(
            observations,
            dns_server=dns_server,
        )

        prefixes = self._observation_prefixes(
            observations
        )

        if self._publish_queue is not None:
            queue_result = self._publish_queue.submit(
                prefixes
            )
            publish_result = (
                queue_result.publish_result
            )
            publication_required = bool(
                queue_result.missing_prefixes
            )
        else:
            publish_result = self._publish_direct()
            publication_required = True

        return DynamicProcessResult(
            query_name=observations[0].query_name,
            matched=True,
            observations_built=len(observations),
            store_result=store_result,
            publish_result=publish_result,
            publication_required=publication_required,
        )

    def _publish_direct(self) -> DynamicPublishResult:
        if self._publisher is None:
            raise RuntimeError(
                "Direct publisher is not configured"
            )

        with self._publish_lock:
            return self._publisher.publish()

    def _observation_prefixes(
        self,
        observations: tuple[
            DynamicDnsObservation,
            ...,
        ],
    ) -> tuple[str, ...]:
        prefixes = {
            str(
                ip_network(
                    (
                        observation.ip,
                        (
                            self._ipv4_prefix
                            if observation.family == 4
                            else self._ipv6_prefix
                        ),
                    ),
                    strict=False,
                )
            )
            for observation in observations
        }

        return tuple(sorted(prefixes))
