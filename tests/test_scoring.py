"""
Tests for route confidence scoring policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from routecollector.policy.scoring import (
    RouteScoreInput,
    RouteScorer,
)


NOW = datetime(2026, 7, 11, 8, 0, 0)


def test_route_scorer_calculates_all_components() -> None:
    """Score must include IP, domain, resolver and history components."""

    scorer = RouteScorer()

    result = scorer.calculate(
        RouteScoreInput(
            unique_ips=5,
            unique_domains=4,
            unique_resolvers=2,
            first_seen=NOW - timedelta(days=7),
            last_seen=NOW,
        )
    )

    assert result.ip_score == 15
    assert result.domain_score == 8
    assert result.resolver_score == 20
    assert result.history_score == 7
    assert result.total == 50


def test_route_scorer_caps_total_at_one_hundred() -> None:
    """Total confidence must never exceed 100."""

    scorer = RouteScorer()

    result = scorer.calculate(
        RouteScoreInput(
            unique_ips=100,
            unique_domains=100,
            unique_resolvers=10,
            first_seen=NOW - timedelta(days=100),
            last_seen=NOW,
        )
    )

    assert result.ip_score == 40
    assert result.domain_score == 30
    assert result.resolver_score == 20
    assert result.history_score == 10
    assert result.total == 100


def test_route_scorer_handles_zero_values() -> None:
    """Empty evidence must produce a zero score."""

    scorer = RouteScorer()

    result = scorer.calculate(
        RouteScoreInput(
            unique_ips=0,
            unique_domains=0,
            unique_resolvers=0,
            first_seen=NOW,
            last_seen=NOW,
        )
    )

    assert result.total == 0


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("unique_ips", -1, "Unique IP count cannot be negative"),
        ("unique_domains", -1, "Unique domain count cannot be negative"),
        ("unique_resolvers", -1, "Unique resolver count cannot be negative"),
    ],
)
def test_route_scorer_rejects_negative_counts(
    field_name: str,
    value: int,
    message: str,
) -> None:
    """Negative evidence counters must be rejected."""

    values = {
        "unique_ips": 1,
        "unique_domains": 1,
        "unique_resolvers": 1,
    }
    values[field_name] = value

    scorer = RouteScorer()

    with pytest.raises(ValueError, match=message):
        scorer.calculate(
            RouteScoreInput(
                unique_ips=values["unique_ips"],
                unique_domains=values["unique_domains"],
                unique_resolvers=values["unique_resolvers"],
                first_seen=NOW,
                last_seen=NOW,
            )
        )


def test_route_scorer_rejects_reversed_dates() -> None:
    """last_seen earlier than first_seen must be rejected."""

    scorer = RouteScorer()

    with pytest.raises(
        ValueError,
        match="last_seen cannot be earlier than first_seen",
    ):
        scorer.calculate(
            RouteScoreInput(
                unique_ips=1,
                unique_domains=1,
                unique_resolvers=1,
                first_seen=NOW,
                last_seen=NOW - timedelta(days=1),
            )
        )
