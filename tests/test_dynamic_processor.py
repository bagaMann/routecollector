"""Tests for the complete dynamic DNS processing pipeline."""

from __future__ import annotations

from pathlib import Path

from routecollector.dynamic import (
    DnsAnswerRecord,
    DomainMatcher,
    DomainMatchRule,
    DynamicDnsProcessor,
    DynamicDnsObservation,
    DynamicPublishResult,
    DynamicStoreResult,
)


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[DynamicDnsObservation, ...], str | None]] = []

    def store(
        self,
        observations: tuple[DynamicDnsObservation, ...],
        *,
        dns_server: str | None = None,
    ) -> DynamicStoreResult:
        materialized = tuple(observations)
        self.calls.append((materialized, dns_server))
        return DynamicStoreResult(
            received=len(materialized),
            stored=len(materialized),
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
            generated_config=Path("bird/routecollector.conf"),
            generated_changed=True,
            installed_config=Path("/etc/bird/routecollector.conf"),
            installed_changed=True,
            bird_checked=True,
            bird_reloaded=True,
            rollback_performed=False,
        )


def build_processor(
    *,
    enable_ipv6: bool = False,
    publish_empty: bool = False,
) -> tuple[DynamicDnsProcessor, FakeStore, FakePublisher]:
    matcher = DomainMatcher(
        [
            DomainMatchRule(
                service_name="youtube",
                domains=("googlevideo.com", "ytimg.com"),
            )
        ]
    )
    store = FakeStore()
    publisher = FakePublisher()
    processor = DynamicDnsProcessor(
        matcher=matcher,
        store=store,  # type: ignore[arg-type]
        publisher=publisher,
        enable_ipv6=enable_ipv6,
        publish_empty=publish_empty,
    )
    return processor, store, publisher


def test_processes_matched_dns_response() -> None:
    processor, store, publisher = build_processor()
    result = processor.process(
        query_name="rr2---sn-test.googlevideo.com",
        records=[
            DnsAnswerRecord("A", "142.250.74.238", 120),
            DnsAnswerRecord("A", "142.250.74.206", 120),
        ],
        dns_server="1.1.1.1",
    )
    assert result.matched is True
    assert result.observations_built == 2
    assert result.store_result is not None
    assert result.publish_result is not None
    assert result.published is True
    assert len(store.calls) == 1
    assert store.calls[0][1] == "1.1.1.1"
    assert publisher.calls == 1


def test_ignores_unmatched_domain() -> None:
    processor, store, publisher = build_processor()
    result = processor.process(
        query_name="example.com",
        records=[DnsAnswerRecord("A", "8.8.8.8", 300)],
    )
    assert result.matched is False
    assert result.observations_built == 0
    assert result.published is False
    assert store.calls == []
    assert publisher.calls == 0


def test_matched_response_without_usable_addresses() -> None:
    processor, store, publisher = build_processor()
    result = processor.process(
        query_name="i.ytimg.com",
        records=[DnsAnswerRecord("A", "192.168.1.1", 300)],
    )
    assert result.matched is True
    assert result.observations_built == 0
    assert result.published is False
    assert store.calls == []
    assert publisher.calls == 0


def test_can_publish_empty_matched_response() -> None:
    processor, store, publisher = build_processor(publish_empty=True)
    result = processor.process(query_name="i.ytimg.com", records=[])
    assert result.matched is True
    assert result.publish_result is not None
    assert store.calls == []
    assert publisher.calls == 1


def test_ipv6_is_filtered_by_default() -> None:
    processor, store, publisher = build_processor()
    result = processor.process(
        query_name="i.ytimg.com",
        records=[DnsAnswerRecord("AAAA", "2001:4860:4860::8888", 300)],
    )
    assert result.observations_built == 0
    assert store.calls == []
    assert publisher.calls == 0


def test_ipv6_can_be_processed() -> None:
    processor, store, publisher = build_processor(enable_ipv6=True)
    result = processor.process(
        query_name="i.ytimg.com",
        records=[DnsAnswerRecord("AAAA", "2001:4860:4860::8888", 300)],
    )
    assert result.observations_built == 1
    assert result.publish_result is not None
    assert store.calls[0][0][0].record_type == "AAAA"
    assert publisher.calls == 1


def test_materializes_record_generator_once() -> None:
    processor, store, publisher = build_processor()
    records = (
        DnsAnswerRecord("A", address, 120)
        for address in ("142.250.74.238", "142.250.74.206")
    )
    result = processor.process(
        query_name="rr2.googlevideo.com",
        records=records,
    )
    assert result.observations_built == 2
    assert len(store.calls[0][0]) == 2
    assert publisher.calls == 1
