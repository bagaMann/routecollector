"""
Tests for the dns-proxy CLI command.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import routecollector.cli as cli_module


def test_parser_accepts_dns_proxy_command() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "dns-proxy",
            "--listen",
            "0.0.0.0",
            "--port",
            "5353",
            "--upstream",
            "9.9.9.9",
            "--upstream-port",
            "53",
            "--timeout",
            "2.5",
            "--udp-only",
            "--fail-closed",
            "--dynamic-confidence",
            "90",
            "--enable-ipv6",
        ]
    )

    assert args.command == "dns-proxy"
    assert args.listen == "0.0.0.0"
    assert args.port == 5353
    assert args.upstream == "9.9.9.9"
    assert args.timeout == 2.5
    assert args.udp_only is True
    assert args.fail_closed is True
    assert args.dynamic_confidence == 90
    assert args.enable_ipv6 is True


def test_command_dns_proxy_builds_and_runs_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = SimpleNamespace(
        repository=object(),
        logger=object(),
    )
    created: list[Any] = []

    class FakeRuntime:
        def __init__(
            self,
            *,
            app: object,
            config: object,
        ) -> None:
            created.append(
                (
                    app,
                    config,
                )
            )
            self.run_calls = 0

        def run(self) -> None:
            self.run_calls += 1

    monkeypatch.setattr(
        cli_module,
        "get_app",
        lambda _: app,
    )
    monkeypatch.setattr(
        cli_module,
        "DynamicRuntime",
        FakeRuntime,
    )

    result = cli_module.command_dns_proxy(
        config_path=Path(
            "config/config.yaml"
        ),
        listen_address="127.0.0.1",
        listen_port=5353,
        upstream_address="1.1.1.1",
        upstream_port=53,
        timeout_seconds=3.0,
        udp_only=False,
        tcp_only=False,
        fail_closed=False,
        dynamic_confidence=100,
        min_confidence_ipv4=60,
        min_confidence_ipv6=60,
        max_age_days=30,
        enable_ipv6=False,
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "dynamic DNS proxy" in output
    assert "127.0.0.1:5353" in output
    assert "1.1.1.1:53" in output
    assert created[0][0] is app
    assert created[0][1].dns_proxy.fail_open is True


def test_command_dns_proxy_rejects_conflicting_transports() -> None:
    with pytest.raises(
        ValueError,
        match="cannot be used together",
    ):
        cli_module.command_dns_proxy(
            config_path=Path(
                "config/config.yaml"
            ),
            listen_address="127.0.0.1",
            listen_port=5353,
            upstream_address="1.1.1.1",
            upstream_port=53,
            timeout_seconds=3.0,
            udp_only=True,
            tcp_only=True,
            fail_closed=False,
            dynamic_confidence=100,
            min_confidence_ipv4=60,
            min_confidence_ipv6=60,
            max_age_days=30,
            enable_ipv6=False,
        )
