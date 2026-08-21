"""
Tests for dynamic lease environment overrides.
"""

from __future__ import annotations

import pytest

from routecollector.dynamic import (
    DnsProxyConfig,
    DynamicRuntimeConfig,
)


def test_runtime_reads_lease_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ROUTECOLLECTOR_DYNAMIC_LEASE_SECONDS",
        "30",
    )
    monkeypatch.setenv(
        "ROUTECOLLECTOR_DYNAMIC_LEASE_CHECK_SECONDS",
        "2.5",
    )

    config = DynamicRuntimeConfig(
        dns_proxy=DnsProxyConfig(),
    )

    assert config.dynamic_lease_seconds == 30
    assert config.dynamic_lease_check_seconds == 2.5


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        (
            "ROUTECOLLECTOR_DYNAMIC_LEASE_SECONDS",
            "invalid",
            "must be an integer",
        ),
        (
            "ROUTECOLLECTOR_DYNAMIC_LEASE_CHECK_SECONDS",
            "invalid",
            "must be a number",
        ),
    ],
)
def test_runtime_rejects_invalid_lease_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(
        ValueError,
        match=message,
    ):
        DynamicRuntimeConfig(
            dns_proxy=DnsProxyConfig(),
        )
