"""
Tests for base domain source normalization.
"""

from __future__ import annotations

from routecollector.sources.base import DomainSource


def test_normalize_domain_accepts_regular_domain() -> None:
    """Regular domains must be lowercased and stripped."""

    assert DomainSource.normalize_domain("  Discord.COM.  ") == "discord.com"


def test_normalize_domain_removes_supported_prefixes() -> None:
    """Supported geosite-style prefixes must be normalized."""

    assert DomainSource.normalize_domain("domain:discord.com") == "discord.com"
    assert DomainSource.normalize_domain("full:cdn.discordapp.com") == (
        "cdn.discordapp.com"
    )
    assert DomainSource.normalize_domain("*.discord.gg") == "discord.gg"
    assert DomainSource.normalize_domain(".discord.media") == "discord.media"


def test_normalize_domain_rejects_unsupported_values() -> None:
    """URLs, regexps, keywords and malformed domains must be rejected."""

    invalid_values = [
        "",
        "discord",
        "https://discord.com",
        "discord.com/path",
        "regexp:^discord",
        "keyword:discord",
        "discord com",
        "-discord.com",
        "discord-.com",
        "discord..com",
    ]

    for value in invalid_values:
        assert DomainSource.normalize_domain(value) is None


def test_normalize_domains_deduplicates_values() -> None:
    """Normalized domain collections must be deduplicated."""

    result = DomainSource.normalize_domains(
        [
            "Discord.COM",
            "discord.com.",
            "domain:discord.com",
            "*.discord.gg",
            "discord.gg",
            "https://invalid.example",
        ]
    )

    assert result == frozenset(
        {
            "discord.com",
            "discord.gg",
        }
    )


def test_normalize_domain_accepts_idn_labels() -> None:
    """Unicode domain labels must remain supported."""

    assert DomainSource.normalize_domain("пример.рф") == "пример.рф"
