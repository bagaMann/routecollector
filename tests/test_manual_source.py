"""
Tests for manual domain source.
"""

from __future__ import annotations

import pytest

from routecollector.sources.base import DomainSourceError, DomainSourceRequest
from routecollector.sources.manual import ManualDomainSource


def test_manual_source_normalizes_domains() -> None:
    source = ManualDomainSource()

    result = source.load(
        DomainSourceRequest(
            service_name="discord",
            source_name=source.name,
            source_options={
                "domains": [
                    "Discord.COM",
                    "*.cdn.discordapp.com",
                    "discord.gg",
                    "discord.com",
                ]
            },
        )
    )

    assert result.domains == frozenset(
        {
            "discord.com",
            "cdn.discordapp.com",
            "discord.gg",
        }
    )
    assert result.metadata["input_count"] == 4
    assert result.metadata["domain_count"] == 3


@pytest.mark.parametrize("value", [123, {"a": 1}, object()])
def test_manual_source_rejects_invalid_domains_option(value: object) -> None:
    source = ManualDomainSource()

    with pytest.raises(DomainSourceError):
        source.load(
            DomainSourceRequest(
                service_name="x",
                source_name=source.name,
                source_options={"domains": value},
            )
        )


def test_manual_source_rejects_non_string_entries() -> None:
    source = ManualDomainSource()

    with pytest.raises(DomainSourceError):
        source.load(
            DomainSourceRequest(
                service_name="x",
                source_name=source.name,
                source_options={"domains": ["ok.example", 1]},
            )
        )
