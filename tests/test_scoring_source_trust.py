"""
Tests for source trust integration in route confidence scoring.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from routecollector.policy.scoring import RouteScoreInput, RouteScorer


def make_input(
    *,
    source_trust: int,
) -> RouteScoreInput:
    """Build a standard scoring input."""

    return RouteScoreInput(
        unique_ips=1,
        unique_domains=1,
        unique_resolvers=1,
        first_seen=datetime.fromisoformat("2026-07-01 00:00:00"),
        last_seen=datetime.fromisoformat("2026-07-11 00:00:00"),
        source_trust=source_trust,
    )


def test_source_trust_is_available_in_route_score() -> None:
    """Route score must retain the calculated source trust value."""

    score = RouteScorer().calculate(
        make_input(source_trust=95)
    )

    assert score.source_trust == 95
    assert score.source_score == 0


def test_source_trust_does_not_change_total_during_refactoring() -> None:
    """The first integration step must preserve existing confidence."""

    scorer = RouteScorer()

    without_trust = scorer.calculate(
        make_input(source_trust=0)
    )
    with_trust = scorer.calculate(
        make_input(source_trust=100)
    )

    assert without_trust.total == 25
    assert with_trust.total == 25
    assert with_trust.total == without_trust.total


@pytest.mark.parametrize(
    "source_trust",
    [-1, 101],
)
def test_source_trust_must_be_between_zero_and_one_hundred(
    source_trust: int,
) -> None:
    """Invalid source trust values must be rejected."""

    with pytest.raises(
        ValueError,
        match="Source trust must be between 0 and 100",
    ):
        RouteScorer().calculate(
            make_input(source_trust=source_trust)
        )
