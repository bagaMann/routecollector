"""
Tests for domain-list-community source plugin.
"""

from __future__ import annotations

import pytest

from routecollector.sources.base import (
    DomainSourceError,
    DomainSourceRequest,
)
from routecollector.sources.domain_list_community_source import (
    DomainListCommunitySource,
)


def test_domain_list_source_loads_domains_and_includes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source must load root list and recursively included lists."""

    files = {
        "discord": """
            # root list
            domain:discord.com
            full:cdn.discordapp.com
            include:discord-cdn
            discord.gg @cn
        """,
        "discord-cdn": """
            *.discord.media
            media.discordapp.net
            include:discord-shared
        """,
        "discord-shared": """
            discordapp.com
            domain:discord.com
        """,
    }

    def fake_download(
        *,
        list_name: str,
        base_url: str,
        timeout: float,
    ) -> str:
        assert base_url == "https://example.test/data"
        assert timeout == 5.0
        return files[list_name]

    monkeypatch.setattr(
        DomainListCommunitySource,
        "_download",
        staticmethod(fake_download),
    )

    source = DomainListCommunitySource()

    result = source.load(
        DomainSourceRequest(
            service_name="discord",
            source_name=source.name,
            source_options={
                "list": "discord",
                "base_url": "https://example.test/data",
                "timeout": 5,
            },
        )
    )

    assert result.source_name == "domain-list-community"
    assert result.service_name == "discord"
    assert result.domains == frozenset(
        {
            "discord.com",
            "cdn.discordapp.com",
            "discord.gg",
            "discord.media",
            "media.discordapp.net",
            "discordapp.com",
        }
    )

    assert result.metadata["root_list"] == "discord"
    assert result.metadata["list_count"] == 3
    assert result.metadata["domain_count"] == 6
    assert result.metadata["loaded_lists"] == (
        "discord",
        "discord-cdn",
        "discord-shared",
    )


def test_domain_list_source_avoids_recursive_include_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Already loaded lists must not be downloaded repeatedly."""

    files = {
        "alpha": "include:beta\nalpha.example\n",
        "beta": "include:alpha\nbeta.example\n",
    }
    calls: list[str] = []

    def fake_download(
        *,
        list_name: str,
        base_url: str,
        timeout: float,
    ) -> str:
        del base_url, timeout
        calls.append(list_name)
        return files[list_name]

    monkeypatch.setattr(
        DomainListCommunitySource,
        "_download",
        staticmethod(fake_download),
    )

    source = DomainListCommunitySource()

    result = source.load(
        DomainSourceRequest(
            service_name="test",
            source_name=source.name,
            source_options={"list": "alpha"},
        )
    )

    assert result.domains == frozenset(
        {
            "alpha.example",
            "beta.example",
        }
    )
    assert calls == ["alpha", "beta"]


def test_domain_list_source_uses_service_name_as_default_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service name must be used when list option is omitted."""

    requested_lists: list[str] = []

    def fake_download(
        *,
        list_name: str,
        base_url: str,
        timeout: float,
    ) -> str:
        del base_url, timeout
        requested_lists.append(list_name)
        return "discord.com\n"

    monkeypatch.setattr(
        DomainListCommunitySource,
        "_download",
        staticmethod(fake_download),
    )

    source = DomainListCommunitySource()

    result = source.load(
        DomainSourceRequest(
            service_name="discord",
            source_name=source.name,
        )
    )

    assert requested_lists == ["discord"]
    assert result.domains == frozenset({"discord.com"})


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"list": ""}, "list name cannot be empty"),
        ({"base_url": ""}, "base_url cannot be empty"),
        ({"timeout": 0}, "timeout must be greater than zero"),
        ({"timeout": "bad"}, "timeout must be numeric"),
        ({"max_depth": -1}, "max_depth cannot be negative"),
        ({"max_depth": "bad"}, "max_depth must be an integer"),
    ],
)
def test_domain_list_source_rejects_invalid_options(
    options: dict[str, object],
    message: str,
) -> None:
    """Invalid plugin options must raise clear errors."""

    source = DomainListCommunitySource()

    with pytest.raises(DomainSourceError, match=message):
        source.load(
            DomainSourceRequest(
                service_name="discord",
                source_name=source.name,
                source_options=options,
            )
        )


def test_domain_list_source_rejects_excessive_include_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Include chains deeper than max_depth must be rejected."""

    def fake_download(
        *,
        list_name: str,
        base_url: str,
        timeout: float,
    ) -> str:
        del base_url, timeout

        if list_name == "one":
            return "include:two\n"

        if list_name == "two":
            return "include:three\n"

        return "three.example\n"

    monkeypatch.setattr(
        DomainListCommunitySource,
        "_download",
        staticmethod(fake_download),
    )

    source = DomainListCommunitySource()

    with pytest.raises(
        DomainSourceError,
        match="include depth exceeded",
    ):
        source.load(
            DomainSourceRequest(
                service_name="test",
                source_name=source.name,
                source_options={
                    "list": "one",
                    "max_depth": 1,
                },
            )
        )
