"""
Additional validation tests for dynamic fast-publication runtime options.
"""

import pytest

from routecollector.dynamic import (
    DnsProxyConfig,
    DynamicRuntimeConfig,
)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("dynamic_min_confidence_ipv4", -1),
        ("dynamic_min_confidence_ipv4", 101),
        ("dynamic_min_confidence_ipv6", -1),
        ("dynamic_min_confidence_ipv6", 101),
        ("dynamic_min_source_trust", -1),
        ("dynamic_min_source_trust", 101),
    ],
)
def test_runtime_rejects_invalid_fast_policy_values(
    field_name: str,
    value: int,
) -> None:
    kwargs = {
        field_name: value,
    }

    with pytest.raises(
        ValueError,
        match="between 0 and 100",
    ):
        DynamicRuntimeConfig(
            dns_proxy=DnsProxyConfig(),
            **kwargs,
        )
