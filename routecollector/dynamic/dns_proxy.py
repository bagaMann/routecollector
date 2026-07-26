"""
DNS forwarding resolver integrated with the dynamic RouteCollector pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable, Protocol

from dnslib import DNSRecord, QTYPE
from dnslib.server import (
    BaseResolver,
    DNSHandler,
    DNSLogger,
    DNSServer,
)

from routecollector.dynamic.dns_observation import DnsAnswerRecord
from routecollector.dynamic.processor import (
    DynamicProcessResult,
)


class DnsProxyError(RuntimeError):
    """DNS proxy operation failed."""


class DynamicProcessorLike(Protocol):
    """Processor interface required by the DNS proxy."""

    def process(
        self,
        *,
        query_name: str,
        records: tuple[DnsAnswerRecord, ...],
        dns_server: str | None = None,
    ) -> DynamicProcessResult:
        """Process one forwarded DNS response."""


@dataclass(slots=True, frozen=True)
class DnsProxyConfig:
    """Runtime configuration for the DNS proxy."""

    listen_address: str = "127.0.0.1"
    listen_port: int = 5353
    upstream_address: str = "1.1.1.1"
    upstream_port: int = 53
    timeout_seconds: float = 3.0
    enable_udp: bool = True
    enable_tcp: bool = True
    fail_open: bool = True

    def __post_init__(self) -> None:
        if not self.listen_address.strip():
            raise ValueError(
                "DNS proxy listen address cannot be empty"
            )

        if not self.upstream_address.strip():
            raise ValueError(
                "DNS proxy upstream address cannot be empty"
            )

        if not 1 <= self.listen_port <= 65535:
            raise ValueError(
                "DNS proxy listen port must be between 1 and 65535"
            )

        if not 1 <= self.upstream_port <= 65535:
            raise ValueError(
                "DNS proxy upstream port must be between 1 and 65535"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "DNS proxy timeout must be greater than zero"
            )

        if not self.enable_udp and not self.enable_tcp:
            raise ValueError(
                "At least one DNS transport must be enabled"
            )


@dataclass(slots=True, frozen=True)
class DnsProxyEvent:
    """Information about one dynamically inspected DNS response."""

    query_name: str
    record_count: int
    protocol: str
    process_result: DynamicProcessResult | None
    processing_error: str | None


class ForwardingDynamicResolver(BaseResolver):
    """
    Forward DNS requests and inspect successful A/AAAA responses.

    The original upstream response is returned unchanged. Dynamic
    processing runs before the response is returned. With fail_open
    enabled, publication errors do not break client DNS resolution.
    """

    def __init__(
        self,
        *,
        processor: DynamicProcessorLike,
        config: DnsProxyConfig,
        event_callback: Callable[[DnsProxyEvent], None] | None = None,
    ) -> None:
        self._processor = processor
        self._config = config
        self._event_callback = event_callback

    def resolve(
        self,
        request: DNSRecord,
        handler: DNSHandler,
    ) -> DNSRecord:
        """Forward one request and inspect its response."""

        protocol = self._handler_protocol(handler)
        use_tcp = protocol == "tcp"

        try:
            response_data = request.send(
                self._config.upstream_address,
                self._config.upstream_port,
                tcp=use_tcp,
                timeout=self._config.timeout_seconds,
            )
            response = DNSRecord.parse(response_data)
        except Exception as exc:
            raise DnsProxyError(
                "Unable to query upstream DNS server "
                f"{self._config.upstream_address}:"
                f"{self._config.upstream_port}: {exc}"
            ) from exc

        query_name = self._query_name(request)
        records = self.extract_address_records(response)

        process_result: DynamicProcessResult | None = None
        processing_error: str | None = None

        if records:
            try:
                process_result = self._processor.process(
                    query_name=query_name,
                    records=records,
                    dns_server=self._config.upstream_address,
                )
            except Exception as exc:
                processing_error = str(exc)

                if not self._config.fail_open:
                    raise DnsProxyError(
                        "Dynamic DNS processing failed: "
                        f"{exc}"
                    ) from exc

        self._emit_event(
            DnsProxyEvent(
                query_name=query_name,
                record_count=len(records),
                protocol=protocol,
                process_result=process_result,
                processing_error=processing_error,
            )
        )

        return response

    @staticmethod
    def extract_address_records(
        response: DNSRecord,
    ) -> tuple[DnsAnswerRecord, ...]:
        """Extract valid A and AAAA records from an answer section."""

        records: list[DnsAnswerRecord] = []

        for answer in response.rr:
            record_type = QTYPE.get(answer.rtype)

            if record_type not in {"A", "AAAA"}:
                continue

            records.append(
                DnsAnswerRecord(
                    record_type=record_type,
                    value=str(answer.rdata),
                    ttl=int(answer.ttl),
                )
            )

        return tuple(records)

    @staticmethod
    def _query_name(request: DNSRecord) -> str:
        if not request.questions:
            raise DnsProxyError(
                "DNS request does not contain a question"
            )

        return str(
            request.questions[0].qname
        ).rstrip(".")

    @staticmethod
    def _handler_protocol(handler: DNSHandler) -> str:
        protocol = str(
            getattr(handler, "protocol", "udp")
        ).lower()

        return "tcp" if protocol == "tcp" else "udp"

    def _emit_event(
        self,
        event: DnsProxyEvent,
    ) -> None:
        if self._event_callback is not None:
            self._event_callback(event)


class DynamicDnsProxyServer:
    """Run UDP and TCP dnslib servers over one resolver."""

    def __init__(
        self,
        *,
        resolver: ForwardingDynamicResolver,
        config: DnsProxyConfig,
        logger: DNSLogger | None = None,
    ) -> None:
        self._resolver = resolver
        self._config = config
        self._logger = logger or DNSLogger(
            log="request,error",
            prefix=False,
        )
        self._servers: list[DNSServer] = []
        self._stopped = Event()

    def start(self) -> None:
        """Start configured DNS transports in background threads."""

        if self._servers:
            raise DnsProxyError(
                "DNS proxy server is already started"
            )

        if self._config.enable_udp:
            self._servers.append(
                DNSServer(
                    self._resolver,
                    address=self._config.listen_address,
                    port=self._config.listen_port,
                    tcp=False,
                    logger=self._logger,
                )
            )

        if self._config.enable_tcp:
            self._servers.append(
                DNSServer(
                    self._resolver,
                    address=self._config.listen_address,
                    port=self._config.listen_port,
                    tcp=True,
                    logger=self._logger,
                )
            )

        for server in self._servers:
            server.start_thread()

    def stop(self) -> None:
        """Stop all configured DNS transports."""

        for server in self._servers:
            server.stop()

        self._servers.clear()
        self._stopped.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait until the proxy is stopped."""

        return self._stopped.wait(timeout)

    @property
    def running(self) -> bool:
        """Return whether at least one transport is running."""

        return bool(self._servers)
