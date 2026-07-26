"""
Additional processor tests for route-cache-aware publication.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.dynamic import (
    DnsAnswerRecord,
    DomainMatcher,
    DomainMatchRule,
    DynamicDnsProcessor,
    DynamicPublishQueue,
    DynamicPublishResult,
    DynamicRouteCache,
    DynamicStoreResult,
)


class FakeStore:
    def store(
        self,
        observations: object,
        *,
        dns_server: str | None = None,
    ) -> DynamicStoreResult:
        del observations
        del dns_server

        return DynamicStoreResult(
            received=1,
            stored=1,
            domains_touched=1,
            services_touched=1,
            skipped_duplicates=0,
        )


class FakePublisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish(self) -> DynamicPublishResult:
        self.calls += 1

        return DynamicPublishResult(
            route_stats_built=100,
            planned_routes=51,
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
        )


def build_processor(
    cache: DynamicRouteCache,
    publisher: FakePublisher,
) -> tuple[
    DynamicDnsProcessor,
    DynamicPublishQueue,
]:
    queue = DynamicPublishQueue(
        publisher=publisher,
        route_cache=cache,
        debounce_seconds=0.01,
    )

    processor = DynamicDnsProcessor(
        matcher=DomainMatcher(
            [
                DomainMatchRule(
                    service_name="youtube",
                    domains=(
                        "googlevideo.com",
                    ),
                )
            ]
        ),
        store=FakeStore(),  # type: ignore[arg-type]
        publish_queue=queue,
    )

    return processor, queue


def test_processor_skips_known_prefix_publish() -> None:
    publisher = FakePublisher()
    processor, queue = build_processor(
        DynamicRouteCache(
            ["142.250.74.0/24"]
        ),
        publisher,
    )

    try:
        result = processor.process(
            query_name=(
                "rr2.googlevideo.com"
            ),
            records=[
                DnsAnswerRecord(
                    "A",
                    "142.250.74.238",
                    120,
                )
            ],
        )
    finally:
        queue.stop()

    assert result.publication_required is False
    assert result.publish_result is None
    assert publisher.calls == 0


def test_processor_publishes_new_prefix() -> None:
    publisher = FakePublisher()
    processor, queue = build_processor(
        DynamicRouteCache(),
        publisher,
    )

    try:
        result = processor.process(
            query_name=(
                "rr2.googlevideo.com"
            ),
            records=[
                DnsAnswerRecord(
                    "A",
                    "142.250.74.238",
                    120,
                )
            ],
        )
    finally:
        queue.stop()

    assert result.publication_required is True
    assert result.publish_result is not None
    assert publisher.calls == 1
