"""
Tests for route confidence scoring policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from routecollector.policy.scoring import RouteScoreInput, RouteScorer


NOW = datetime(2026, 7, 11, 8, 0, 0)


def test_route_scorer_calculates_all_components() -> None:
    scorer = RouteScorer()
    result = scorer.calculate(
        RouteScoreInput(
            unique_ips=5,
            unique_domains=4,
            unique_resolvers=2,
            first_seen=NOW - timedelta(days=7),
            last_seen=NOW,
            source_trust=50,
        )
    )

    assert result.ip_score == 15
    assert result.domain_score == 8
    assert result.resolver_score == 15
    assert result.history_score == 7
    assert result.source_score == 10
    assert result.source_trust == 50
    assert result.total == 55


def test_route_scorer_caps_components_and_total() -> None:
    scorer = RouteScorer()
    result = scorer.calculate(
        RouteScoreInput(
            unique_ips=100,
            unique_domains=100,
            unique_resolvers=10,
            first_seen=NOW - timedelta(days=100),
            last_seen=NOW,
            source_trust=100,
        )
    )

    assert result.ip_score == 30
    assert result.domain_score == 25
    assert result.resolver_score == 15
    assert result.history_score == 10
    assert result.source_score == 20
    assert result.total == 100


def test_route_scorer_handles_zero_values() -> None:
    result = RouteScorer().calculate(
        RouteScoreInput(
            unique_ips=0,
            unique_domains=0,
            unique_resolvers=0,
            first_seen=NOW,
            last_seen=NOW,
            source_trust=0,
        )
    )
    assert result.total == 0
    assert result.source_score == 0


def test_route_scorer_scales_source_trust_to_twenty_points() -> None:
    scorer = RouteScorer()

    low = scorer.calculate(
        RouteScoreInput(
            unique_ips=0,
            unique_domains=0,
            unique_resolvers=0,
            first_seen=NOW,
            last_seen=NOW,
            source_trust=50,
        )
    )
    high = scorer.calculate(
        RouteScoreInput(
            unique_ips=0,
            unique_domains=0,
            unique_resolvers=0,
            first_seen=NOW,
            last_seen=NOW,
            source_trust=100,
        )
    )

    assert low.source_score == 10
    assert low.total == 10
    assert high.source_score == 20
    assert high.total == 20


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
    values = {
        "unique_ips": 1,
        "unique_domains": 1,
        "unique_resolvers": 1,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=message):
        RouteScorer().calculate(
            RouteScoreInput(
                unique_ips=values["unique_ips"],
                unique_domains=values["unique_domains"],
                unique_resolvers=values["unique_resolvers"],
                first_seen=NOW,
                last_seen=NOW,
                source_trust=0,
            )
        )


@pytest.mark.parametrize("source_trust", [-1, 101])
def test_route_scorer_rejects_invalid_source_trust(
    source_trust: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="Source trust must be between 0 and 100",
    ):
        RouteScorer().calculate(
            RouteScoreInput(
                unique_ips=1,
                unique_domains=1,
                unique_resolvers=1,
                first_seen=NOW,
                last_seen=NOW,
                source_trust=source_trust,
            )
        )


def test_route_scorer_rejects_reversed_dates() -> None:
    with pytest.raises(
        ValueError,
        match="last_seen cannot be earlier than first_seen",
    ):
        RouteScorer().calculate(
            RouteScoreInput(
                unique_ips=1,
                unique_domains=1,
                unique_resolvers=1,
                first_seen=NOW,
                last_seen=NOW - timedelta(days=1),
                source_trust=0,
            )
        )
