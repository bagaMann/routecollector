"""
Tests for source trust scoring policy.
"""

from __future__ import annotations

import pytest

from routecollector.policy.source_trust import (
    SourceTrustPolicy,
)


def test_source_trust_returns_configured_value() -> None:
    """Single known source must return its configured trust value."""

    policy = SourceTrustPolicy(
        {
            "manual": 100,
            "domain-list-community": 95,
        }
    )

    result = policy.score({"manual"})

    assert result.total == 100
    assert result.matched_sources == ("manual",)
    assert result.unknown_sources == ()
    assert result.source_values == {"manual": 100}


def test_source_trust_combines_independent_sources() -> None:
    """Additional independent sources must increase trust."""

    policy = SourceTrustPolicy(
        {
            "manual": 80,
            "domain-list-community": 60,
            "custom": 40,
        }
    )

    result = policy.score(
        {
            "manual",
            "domain-list-community",
            "custom",
        }
    )

    assert result.total == 100
    assert result.matched_sources == (
        "custom",
        "domain-list-community",
        "manual",
    )


def test_source_trust_deduplicates_source_names() -> None:
    """Duplicate and differently cased names must not be counted twice."""

    policy = SourceTrustPolicy({"manual": 80})

    result = policy.score(
        [
            "manual",
            "MANUAL",
            " manual ",
        ]
    )

    assert result.total == 80
    assert result.matched_sources == ("manual",)


def test_source_trust_tracks_unknown_sources() -> None:
    """Unknown sources must not add score but must remain visible."""

    policy = SourceTrustPolicy({"manual": 80})

    result = policy.score(
        {
            "manual",
            "unknown",
        }
    )

    assert result.total == 80
    assert result.matched_sources == ("manual",)
    assert result.unknown_sources == ("unknown",)


def test_source_trust_returns_zero_without_known_sources() -> None:
    """No known source evidence must produce a zero score."""

    policy = SourceTrustPolicy({"manual": 80})

    result = policy.score({"unknown"})

    assert result.total == 0
    assert result.matched_sources == ()
    assert result.unknown_sources == ("unknown",)


def test_source_trust_get_and_values() -> None:
    """Configured values must be available without exposing internal state."""

    policy = SourceTrustPolicy({"Manual": 90})

    assert policy.get("manual") == 90
    assert policy.get("MANUAL") == 90
    assert policy.get("missing") is None

    values = policy.values()
    values["manual"] = 1

    assert policy.get("manual") == 90


@pytest.mark.parametrize(
    "value",
    [-1, 101],
)
def test_source_trust_rejects_out_of_range_values(
    value: int,
) -> None:
    """Trust values must remain between zero and one hundred."""

    with pytest.raises(
        ValueError,
        match="between 0 and 100",
    ):
        SourceTrustPolicy({"manual": value})


def test_source_trust_rejects_non_integer_value() -> None:
    """Trust values must be integers."""

    with pytest.raises(
        TypeError,
        match="must be an integer",
    ):
        SourceTrustPolicy(
            {"manual": 90.5}  # type: ignore[dict-item]
        )
