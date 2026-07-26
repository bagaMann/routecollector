"""
Tests for the dynamic DNS forwarding proxy.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from dnslib import A, AAAA, CNAME, DNSRecord, QTYPE, RR

from routecollector.dynamic import (
    DnsAnswerRecord,
    DnsProxyConfig,
    DnsProxyError,
    DnsProxyEvent,
    ForwardingDynamicResolver,
)


class FakeProcessor:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def process(
        self,
        *,
        query_name: str,
        records: tuple[DnsAnswerRecord, ...],
        dns_server: str | None = None,
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "query_name": query_name,
                "records": records,
                "dns_server": dns_server,
            }
        )

        if self.error is not None:
            raise self.error

        return SimpleNamespace(
            matched=True,
            observations_built=len(records),
        )


def make_request(
    name: str = "i.ytimg.com",
) -> DNSRecord:
    return DNSRecord.question(
        name,
        "A",
    )


def make_response(
    request: DNSRecord,
) -> DNSRecord:
    response = request.reply()

    response.add_answer(
        RR(
            rname="i.ytimg.com",
            rtype=QTYPE.CNAME,
            ttl=60,
            rdata=CNAME(
                "cdn.ytimg.com"
            ),
        )
    )
    response.add_answer(
        RR(
            rname="cdn.ytimg.com",
            rtype=QTYPE.A,
            ttl=120,
            rdata=A(
                "142.250.74.238"
            ),
        )
    )
    response.add_answer(
        RR(
            rname="cdn.ytimg.com",
            rtype=QTYPE.AAAA,
            ttl=300,
            rdata=AAAA(
                "2001:4860:4860::8888"
            ),
        )
    )

    return response


def test_config_defaults() -> None:
    config = DnsProxyConfig()

    assert config.listen_address == "127.0.0.1"
    assert config.listen_port == 5353
    assert config.upstream_address == "1.1.1.1"
    assert config.enable_udp is True
    assert config.enable_tcp is True
    assert config.fail_open is True


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("listen_address", ""),
        ("upstream_address", ""),
        ("listen_port", 0),
        ("listen_port", 65536),
        ("upstream_port", 0),
        ("timeout_seconds", 0),
    ],
)
def test_config_rejects_invalid_values(
    keyword: str,
    value: object,
) -> None:
    arguments: dict[str, object] = {
        keyword: value,
    }

    with pytest.raises(ValueError):
        DnsProxyConfig(
            **arguments,  # type: ignore[arg-type]
        )


def test_config_requires_transport() -> None:
    with pytest.raises(
        ValueError,
        match="At least one",
    ):
        DnsProxyConfig(
            enable_udp=False,
            enable_tcp=False,
        )


def test_extracts_a_and_aaaa_only() -> None:
    request = make_request()
    response = make_response(request)

    records = (
        ForwardingDynamicResolver
        .extract_address_records(response)
    )

    assert records == (
        DnsAnswerRecord(
            "A",
            "142.250.74.238",
            120,
        ),
        DnsAnswerRecord(
            "AAAA",
            "2001:4860:4860::8888",
            300,
        ),
    )


def test_forwards_udp_and_processes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    response = make_response(request)
    processor = FakeProcessor()
    events: list[DnsProxyEvent] = []

    def fake_send(
        self: DNSRecord,
        dest: str,
        port: int,
        tcp: bool,
        timeout: float,
    ) -> bytes:
        assert dest == "1.1.1.1"
        assert port == 53
        assert tcp is False
        assert timeout == 3.0
        return response.pack()

    monkeypatch.setattr(
        DNSRecord,
        "send",
        fake_send,
    )

    resolver = ForwardingDynamicResolver(
        processor=processor,
        config=DnsProxyConfig(),
        event_callback=events.append,
    )

    returned = resolver.resolve(
        request,
        SimpleNamespace(
            protocol="udp"
        ),
    )

    assert returned.pack() == response.pack()
    assert len(processor.calls) == 1
    assert processor.calls[0]["query_name"] == (
        "i.ytimg.com"
    )
    assert processor.calls[0]["dns_server"] == (
        "1.1.1.1"
    )
    assert len(
        processor.calls[0]["records"]
    ) == 2

    assert events[0].protocol == "udp"
    assert events[0].record_count == 2
    assert events[0].processing_error is None


def test_forwards_tcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    response = make_response(request)
    processor = FakeProcessor()

    def fake_send(
        self: DNSRecord,
        dest: str,
        port: int,
        tcp: bool,
        timeout: float,
    ) -> bytes:
        assert tcp is True
        return response.pack()

    monkeypatch.setattr(
        DNSRecord,
        "send",
        fake_send,
    )

    resolver = ForwardingDynamicResolver(
        processor=processor,
        config=DnsProxyConfig(),
    )

    resolver.resolve(
        request,
        SimpleNamespace(
            protocol="tcp"
        ),
    )

    assert len(processor.calls) == 1


def test_does_not_process_response_without_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    response = request.reply()
    processor = FakeProcessor()
    events: list[DnsProxyEvent] = []

    monkeypatch.setattr(
        DNSRecord,
        "send",
        lambda *args, **kwargs: response.pack(),
    )

    resolver = ForwardingDynamicResolver(
        processor=processor,
        config=DnsProxyConfig(),
        event_callback=events.append,
    )

    resolver.resolve(
        request,
        SimpleNamespace(
            protocol="udp"
        ),
    )

    assert processor.calls == []
    assert events[0].record_count == 0


def test_fail_open_returns_upstream_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    response = make_response(request)
    processor = FakeProcessor(
        error=RuntimeError(
            "publication failed"
        )
    )
    events: list[DnsProxyEvent] = []

    monkeypatch.setattr(
        DNSRecord,
        "send",
        lambda *args, **kwargs: response.pack(),
    )

    resolver = ForwardingDynamicResolver(
        processor=processor,
        config=DnsProxyConfig(
            fail_open=True
        ),
        event_callback=events.append,
    )

    returned = resolver.resolve(
        request,
        SimpleNamespace(
            protocol="udp"
        ),
    )

    assert returned.pack() == response.pack()
    assert events[0].processing_error == (
        "publication failed"
    )


def test_fail_closed_raises_processing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    response = make_response(request)
    processor = FakeProcessor(
        error=RuntimeError(
            "publication failed"
        )
    )

    monkeypatch.setattr(
        DNSRecord,
        "send",
        lambda *args, **kwargs: response.pack(),
    )

    resolver = ForwardingDynamicResolver(
        processor=processor,
        config=DnsProxyConfig(
            fail_open=False
        ),
    )

    with pytest.raises(
        DnsProxyError,
        match="processing failed",
    ):
        resolver.resolve(
            request,
            SimpleNamespace(
                protocol="udp"
            ),
        )


def test_wraps_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    processor = FakeProcessor()

    def fail_send(
        *args: object,
        **kwargs: object,
    ) -> bytes:
        raise TimeoutError(
            "upstream timeout"
        )

    monkeypatch.setattr(
        DNSRecord,
        "send",
        fail_send,
    )

    resolver = ForwardingDynamicResolver(
        processor=processor,
        config=DnsProxyConfig(),
    )

    with pytest.raises(
        DnsProxyError,
        match="Unable to query upstream",
    ):
        resolver.resolve(
            request,
            SimpleNamespace(
                protocol="udp"
            ),
        )
