"""
Tests for matched dynamic-DNS fast publication policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from routecollector.dynamic import DynamicFastPublishPolicy
from routecollector.planner.planner import PlannedRoute


@dataclass(slots=True)
class FakeStat:
    prefix: str
    family: int = 4
    source_ips: int = 1
    unique_domains: int = 1
    unique_resolvers: int = 1
    source_count: int = 1
    source_trust: int = 50
    confidence: int = 25


def make_route(
    prefix: str = "8.8.8.0/24",
) -> PlannedRoute:
    return PlannedRoute(
        prefix=prefix,
        family=4,
        source_ips=1,
        unique_domains=1,
        unique_resolvers=1,
        source_count=1,
        source_trust=100,
        confidence=70,
        publish_score=93,
    )


def test_fast_policy_adds_eligible_requested_prefix() -> None:
    result = DynamicFastPublishPolicy().augment(
        base_routes=[make_route()],
        route_stats=[
            FakeStat(
                prefix="85.249.244.0/24",
            )
        ],
        required_prefixes=[
            "85.249.244.44/24",
        ],
    )

    assert tuple(
        route.prefix
        for route in result.routes
    ) == (
        "8.8.8.0/24",
        "85.249.244.0/24",
    )
    assert result.accepted_prefixes == (
        "85.249.244.0/24",
    )
    assert result.rejected_prefixes == ()


def test_fast_policy_does_not_add_unrequested_low_route() -> None:
    result = DynamicFastPublishPolicy().augment(
        base_routes=[make_route()],
        route_stats=[
            FakeStat(
                prefix="85.249.244.0/24",
            )
        ],
        required_prefixes=[],
    )

    assert tuple(
        route.prefix
        for route in result.routes
    ) == ("8.8.8.0/24",)


def test_fast_policy_rejects_low_confidence() -> None:
    result = DynamicFastPublishPolicy().augment(
        base_routes=[make_route()],
        route_stats=[
            FakeStat(
                prefix="85.249.244.0/24",
                confidence=24,
            )
        ],
        required_prefixes=[
            "85.249.244.0/24",
        ],
    )

    assert result.accepted_prefixes == ()
    assert result.rejected_prefixes == (
        "85.249.244.0/24",
    )


def test_fast_policy_rejects_low_source_trust() -> None:
    result = DynamicFastPublishPolicy().augment(
        base_routes=[make_route()],
        route_stats=[
            FakeStat(
                prefix="85.249.244.0/24",
                source_trust=49,
            )
        ],
        required_prefixes=[
            "85.249.244.0/24",
        ],
    )

    assert result.accepted_prefixes == ()
    assert result.rejected_prefixes == (
        "85.249.244.0/24",
    )


def test_existing_normal_route_is_accepted() -> None:
    result = DynamicFastPublishPolicy().augment(
        base_routes=[
            make_route(
                "85.249.244.0/24"
            )
        ],
        route_stats=[],
        required_prefixes=[
            "85.249.244.44/24",
        ],
    )

    assert result.accepted_prefixes == (
        "85.249.244.0/24",
    )
    assert result.rejected_prefixes == ()
