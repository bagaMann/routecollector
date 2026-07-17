"""
Tests for the HTTP text source plugin.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

import routecollector.sources.http_text as http_module
from routecollector.sources.base import (
    DomainSourceError,
    DomainSourceRequest,
)
from routecollector.sources.http_text import HttpTextSource


class FakeResponse:
    """Minimal context-managed HTTP response."""

    def __init__(self, content: bytes) -> None:
        self._content = BytesIO(content)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        *_: object,
    ) -> None:
        pass

    def read(self) -> bytes:
        return self._content.read()


def make_request(
    **options: object,
) -> DomainSourceRequest:
    """Create source request for tests."""

    return DomainSourceRequest(
        service_name="example",
        source_name="http-text",
        source_options={
            "url": "https://example.test/domains.txt",
            **options,
        },
    )


def test_http_text_loads_plain_and_hosts_formats(
    monkeypatch: Any,
) -> None:
    """Plugin must parse common domain-list formats."""

    content = b"""
# comment
example.com
domain:cdn.example.com
full:www.example.com
*.wild.example.com
0.0.0.0 blocked.example.com
127.0.0.1 one.example.com two.example.com
invalid
https://unsupported.example.com/path
example.com # duplicate
"""

    def fake_urlopen(
        request: object,
        timeout: float,
    ) -> FakeResponse:
        assert timeout == 20.0
        assert request.full_url == (
            "https://example.test/domains.txt"
        )
        assert request.get_header("User-agent") == (
            "RouteCollector/1.2"
        )

        return FakeResponse(content)

    monkeypatch.setattr(
        http_module,
        "urlopen",
        fake_urlopen,
    )

    result = HttpTextSource().load(
        make_request()
    )

    assert result.source_name == "http-text"
    assert result.service_name == "example"
    assert result.domains == frozenset(
        {
            "example.com",
            "cdn.example.com",
            "www.example.com",
            "wild.example.com",
            "blocked.example.com",
            "one.example.com",
            "two.example.com",
        }
    )
    assert result.metadata["domain_count"] == 7


def test_http_text_uses_custom_options(
    monkeypatch: Any,
) -> None:
    """Timeout, user agent and encoding must be configurable."""

    def fake_urlopen(
        request: object,
        timeout: float,
    ) -> FakeResponse:
        assert timeout == 5.5
        assert request.get_header("User-agent") == "Custom"
        return FakeResponse(
            "пример.рф\n".encode("utf-8")
        )

    monkeypatch.setattr(
        http_module,
        "urlopen",
        fake_urlopen,
    )

    result = HttpTextSource().load(
        make_request(
            timeout=5.5,
            user_agent="Custom",
            encoding="utf-8",
        )
    )

    assert result.domains == frozenset(
        {"пример.рф"}
    )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (
            {"url": ""},
            "cannot be empty",
        ),
        (
            {"url": "ftp://example.test/list"},
            "HTTP or HTTPS",
        ),
        (
            {"timeout": 0},
            "greater than zero",
        ),
        (
            {"timeout": "invalid"},
            "must be numeric",
        ),
        (
            {"user_agent": ""},
            "user_agent cannot be empty",
        ),
        (
            {"encoding": ""},
            "encoding cannot be empty",
        ),
    ],
)
def test_http_text_rejects_invalid_options(
    options: dict[str, object],
    message: str,
) -> None:
    """Invalid options must fail before network access."""

    with pytest.raises(
        DomainSourceError,
        match=message,
    ):
        HttpTextSource().load(
            make_request(**options)
        )


def test_http_text_wraps_http_error(
    monkeypatch: Any,
) -> None:
    """HTTP status failures must become source errors."""

    def fake_urlopen(
        *_: object,
        **__: object,
    ) -> None:
        raise HTTPError(
            url="https://example.test/domains.txt",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        http_module,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        DomainSourceError,
        match="HTTP 404",
    ):
        HttpTextSource().load(
            make_request()
        )


def test_http_text_wraps_url_error(
    monkeypatch: Any,
) -> None:
    """Transport failures must become source errors."""

    def fake_urlopen(
        *_: object,
        **__: object,
    ) -> None:
        raise URLError("network unavailable")

    monkeypatch.setattr(
        http_module,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        DomainSourceError,
        match="network unavailable",
    ):
        HttpTextSource().load(
            make_request()
        )


def test_http_text_rejects_invalid_encoding(
    monkeypatch: Any,
) -> None:
    """Invalid bytes must produce a clear source error."""

    monkeypatch.setattr(
        http_module,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            b"\xff\xfe"
        ),
    )

    with pytest.raises(
        DomainSourceError,
        match="Unable to decode",
    ):
        HttpTextSource().load(
            make_request()
        )
