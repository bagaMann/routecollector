"""
Tests for dynamic DNS observations.
"""

from __future__ import annotations

import pytest

from routecollector.dynamic import (
    DnsAnswerRecord,
    DomainMatcher,
    DomainMatchRule,
    build_dynamic_observations,
)


def build_matcher() -> DomainMatcher:
    return DomainMatcher(
        [
            DomainMatchRule(
                service_name="youtube",
                domains=(
                    "googlevideo.com",
                    "ytimg.com",
                    "ggpht.com",
                ),
            )
        ]
    )


def test_dns_answer_record_normalizes_values() -> None:
    record = DnsAnswerRecord(
        record_type="a",
        value="142.250.74.238",
        ttl=300,
    )

    assert record.record_type == "A"
    assert record.value == "142.250.74.238"
    assert record.ttl == 300


@pytest.mark.parametrize(
    ("record_type", "value"),
    [
        ("TXT", "example"),
        ("A", "2001:db8::1"),
        ("AAAA", "8.8.8.8"),
        ("A", "invalid"),
    ],
)
def test_dns_answer_record_rejects_invalid_values(
    record_type: str,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        DnsAnswerRecord(
            record_type=record_type,
            value=value,
            ttl=300,
        )


def test_dns_answer_record_rejects_negative_ttl() -> None:
    with pytest.raises(
        ValueError,
        match="cannot be negative",
    ):
        DnsAnswerRecord(
            record_type="A",
            value="8.8.8.8",
            ttl=-1,
        )


def test_builds_observation_for_matched_domain() -> None:
    observations = build_dynamic_observations(
        query_name=(
            "rr2---sn-test.googlevideo.com"
        ),
        records=[
            DnsAnswerRecord(
                record_type="A",
                value="142.250.74.238",
                ttl=120,
            )
        ],
        matcher=build_matcher(),
    )

    assert len(observations) == 1

    observation = observations[0]

    assert observation.service_name == "youtube"
    assert observation.query_name == (
        "rr2---sn-test.googlevideo.com"
    )
    assert observation.matched_domain == (
        "googlevideo.com"
    )
    assert observation.record_type == "A"
    assert observation.ip == "142.250.74.238"
    assert observation.ttl == 120
    assert observation.source == "dynamic-dns"
    assert observation.family == 4


def test_returns_empty_for_unmatched_domain() -> None:
    observations = build_dynamic_observations(
        query_name="example.com",
        records=[
            DnsAnswerRecord(
                record_type="A",
                value="8.8.8.8",
                ttl=300,
            )
        ],
        matcher=build_matcher(),
    )

    assert observations == ()


def test_filters_private_and_loopback_addresses() -> None:
    observations = build_dynamic_observations(
        query_name="i.ytimg.com",
        records=[
            DnsAnswerRecord(
                "A",
                "192.168.1.1",
                300,
            ),
            DnsAnswerRecord(
                "A",
                "127.0.0.1",
                300,
            ),
            DnsAnswerRecord(
                "A",
                "8.8.8.8",
                300,
            ),
        ],
        matcher=build_matcher(),
    )

    assert tuple(
        observation.ip
        for observation in observations
    ) == ("8.8.8.8",)


def test_can_keep_non_global_addresses() -> None:
    observations = build_dynamic_observations(
        query_name="i.ytimg.com",
        records=[
            DnsAnswerRecord(
                "A",
                "192.168.1.1",
                300,
            )
        ],
        matcher=build_matcher(),
        global_only=False,
    )

    assert observations[0].ip == "192.168.1.1"


def test_ipv6_is_disabled_by_default() -> None:
    observations = build_dynamic_observations(
        query_name="i.ytimg.com",
        records=[
            DnsAnswerRecord(
                "AAAA",
                "2001:4860:4860::8888",
                300,
            )
        ],
        matcher=build_matcher(),
    )

    assert observations == ()


def test_ipv6_can_be_enabled() -> None:
    observations = build_dynamic_observations(
        query_name="i.ytimg.com",
        records=[
            DnsAnswerRecord(
                "AAAA",
                "2001:4860:4860::8888",
                300,
            )
        ],
        matcher=build_matcher(),
        enable_ipv6=True,
    )

    assert len(observations) == 1
    assert observations[0].family == 6


def test_deduplicates_identical_service_ip() -> None:
    observations = build_dynamic_observations(
        query_name="i.ytimg.com",
        records=[
            DnsAnswerRecord(
                "A",
                "8.8.8.8",
                300,
            ),
            DnsAnswerRecord(
                "A",
                "8.8.8.8",
                60,
            ),
        ],
        matcher=build_matcher(),
    )

    assert len(observations) == 1


def test_one_answer_can_match_multiple_services() -> None:
    matcher = DomainMatcher(
        [
            DomainMatchRule(
                service_name="youtube",
                domains=("googleusercontent.com",),
            ),
            DomainMatchRule(
                service_name="google",
                domains=("googleusercontent.com",),
            ),
        ]
    )

    observations = build_dynamic_observations(
        query_name="lh3.googleusercontent.com",
        records=[
            DnsAnswerRecord(
                "A",
                "8.8.8.8",
                300,
            )
        ],
        matcher=matcher,
    )

    assert {
        observation.service_name
        for observation in observations
    } == {
        "youtube",
        "google",
    }
