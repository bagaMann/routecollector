"""
Tests for source trust integration in route confidence scoring.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from routecollector.policy.scoring import RouteScoreInput, RouteScorer


def make_input(*, source_trust: int) -> RouteScoreInput:
    return RouteScoreInput(
        unique_ips=1,
        unique_domains=1,
        unique_resolvers=1,
        first_seen=datetime.fromisoformat("2026-07-01 00:00:00"),
        last_seen=datetime.fromisoformat("2026-07-11 00:00:00"),
        source_trust=source_trust,
    )


def test_source_trust_is_available_in_route_score() -> None:
    score = RouteScorer().calculate(
        make_input(source_trust=95)
    )
    assert score.source_trust == 95
    assert score.source_score == 19


def test_source_trust_changes_total_score() -> None:
    scorer = RouteScorer()

    without_trust = scorer.calculate(
        make_input(source_trust=0)
    )
    dynamic_trust = scorer.calculate(
        make_input(source_trust=50)
    )
    full_trust = scorer.calculate(
        make_input(source_trust=100)
    )

    assert without_trust.total == 25
    assert dynamic_trust.total == 35
    assert full_trust.total == 45


@pytest.mark.parametrize("source_trust", [-1, 101])
def test_source_trust_must_be_between_zero_and_one_hundred(
    source_trust: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="Source trust must be between 0 and 100",
    ):
        RouteScorer().calculate(
            make_input(source_trust=source_trust)
        )
