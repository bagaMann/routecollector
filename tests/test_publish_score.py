"""
Tests for route publication scoring policy.
"""

from __future__ import annotations

import pytest

from routecollector.policy.publish_score import (
    PublishScoreInput,
    PublishScorePolicy,
)


def test_publish_score_calculates_all_components() -> None:
    """Publication score must include confidence, trust and source bonuses."""

    result = PublishScorePolicy().calculate(
        PublishScoreInput(
            confidence=50,
            source_trust=80,
            source_count=2,
        )
    )

    assert result.confidence_score == 50
    assert result.trust_bonus == 16
    assert result.source_bonus == 6
    assert result.total == 72


def test_publish_score_is_capped_at_one_hundred() -> None:
    """Publication score must never exceed one hundred."""

    result = PublishScorePolicy().calculate(
        PublishScoreInput(
            confidence=100,
            source_trust=100,
            source_count=10,
        )
    )

    assert result.confidence_score == 100
    assert result.trust_bonus == 20
    assert result.source_bonus == 15
    assert result.total == 100


def test_publish_score_accepts_zero_values() -> None:
    """No evidence must produce a zero publication score."""

    result = PublishScorePolicy().calculate(
        PublishScoreInput(
            confidence=0,
            source_trust=0,
            source_count=0,
        )
    )

    assert result.total == 0


def test_publish_score_caps_source_bonus() -> None:
    """Source count bonus must be bounded."""

    result = PublishScorePolicy().calculate(
        PublishScoreInput(
            confidence=0,
            source_trust=0,
            source_count=100,
        )
    )

    assert result.source_bonus == 15
    assert result.total == 15


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("confidence", -1, "Confidence must be between 0 and 100"),
        ("confidence", 101, "Confidence must be between 0 and 100"),
        ("source_trust", -1, "Source trust must be between 0 and 100"),
        ("source_trust", 101, "Source trust must be between 0 and 100"),
        ("source_count", -1, "Source count cannot be negative"),
    ],
)
def test_publish_score_rejects_invalid_input(
    field_name: str,
    value: int,
    message: str,
) -> None:
    """Invalid publication evidence must be rejected."""

    values = {
        "confidence": 50,
        "source_trust": 80,
        "source_count": 2,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=message):
        PublishScorePolicy().calculate(
            PublishScoreInput(
                confidence=values["confidence"],
                source_trust=values["source_trust"],
                source_count=values["source_count"],
            )
        )
