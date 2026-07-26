"""
Tests for dynamic DNS domain matching.
"""

from __future__ import annotations

import pytest

from routecollector.dynamic import (
    DomainMatcher,
    DomainMatchRule,
)


def build_matcher() -> DomainMatcher:
    return DomainMatcher(
        [
            DomainMatchRule(
                service_name="youtube",
                domains=(
                    "youtube.com",
                    "googlevideo.com",
                    "ytimg.com",
                    "ggpht.com",
                ),
            ),
            DomainMatchRule(
                service_name="telegram",
                domains=(
                    "telegram.org",
                    "t.me",
                ),
            ),
        ]
    )


def test_matches_exact_domain() -> None:
    matcher = build_matcher()

    matches = matcher.match("youtube.com")

    assert len(matches) == 1
    assert matches[0].service_name == "youtube"
    assert matches[0].matched_domain == "youtube.com"


def test_matches_dynamic_googlevideo_subdomain() -> None:
    matcher = build_matcher()

    matches = matcher.match(
        "rr2---sn-5hne6nzd.googlevideo.com"
    )

    assert len(matches) == 1
    assert matches[0].service_name == "youtube"
    assert matches[0].matched_domain == "googlevideo.com"


def test_matches_trailing_dot_and_case() -> None:
    matcher = build_matcher()

    matches = matcher.match(
        "YT3.GGPHT.COM."
    )

    assert len(matches) == 1
    assert matches[0].service_name == "youtube"
    assert matches[0].query_name == "yt3.ggpht.com"


def test_does_not_match_similar_suffix() -> None:
    matcher = build_matcher()

    assert matcher.match(
        "fakegooglevideo.com"
    ) == ()


def test_can_disable_subdomain_matching() -> None:
    matcher = DomainMatcher(
        [
            DomainMatchRule(
                service_name="example",
                domains=("example.com",),
                include_subdomains=False,
            )
        ]
    )

    assert matcher.matches("example.com") is True
    assert matcher.matches("www.example.com") is False


def test_one_service_is_returned_once() -> None:
    matcher = DomainMatcher(
        [
            DomainMatchRule(
                service_name="youtube",
                domains=(
                    "googlevideo.com",
                    "sn.googlevideo.com",
                ),
            )
        ]
    )

    matches = matcher.match(
        "test.sn.googlevideo.com"
    )

    assert len(matches) == 1
    assert matches[0].matched_domain == (
        "sn.googlevideo.com"
    )


def test_domain_can_match_multiple_services() -> None:
    matcher = DomainMatcher(
        [
            DomainMatchRule(
                service_name="google",
                domains=("googleusercontent.com",),
            ),
            DomainMatchRule(
                service_name="youtube",
                domains=("googleusercontent.com",),
            ),
        ]
    )

    matches = matcher.match(
        "lh3.googleusercontent.com"
    )

    assert {
        match.service_name
        for match in matches
    } == {
        "google",
        "youtube",
    }


@pytest.mark.parametrize(
    "domain",
    [
        "",
        ".",
        "example..com",
        "a" * 64 + ".example.com",
    ],
)
def test_rejects_invalid_domain(
    domain: str,
) -> None:
    with pytest.raises(ValueError):
        DomainMatcher.normalize_domain(domain)


def test_rule_requires_domains() -> None:
    with pytest.raises(
        ValueError,
        match="at least one domain",
    ):
        DomainMatchRule(
            service_name="youtube",
            domains=(),
        )
