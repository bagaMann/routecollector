"""
Tests for service synchronization through SourceManager.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.sources.manager import (
    MergedDomain,
    SourceManagerResult,
)
from routecollector.sources.service_source_sync import ServiceSourceSync


class FakeRepository:
    """Repository stub used by source sync tests."""

    def __init__(self) -> None:
        self.services: list[dict[str, object]] = []
        self.domains: list[dict[str, object]] = []
        self._next_service_id = 1

    def upsert_service(
        self,
        name: str,
        description: str | None = None,
        enabled: bool = True,
    ) -> int:
        """Record service and return synthetic ID."""

        service_id = self._next_service_id
        self._next_service_id += 1

        self.services.append(
            {
                "id": service_id,
                "name": name,
                "description": description,
                "enabled": enabled,
            }
        )

        return service_id

    def upsert_domain(
        self,
        service_id: int,
        domain: str,
        source: str,
        active: bool = True,
    ) -> int:
        """Record domain provenance."""

        self.domains.append(
            {
                "service_id": service_id,
                "domain": domain,
                "source": source,
                "active": active,
            }
        )

        return len(self.domains)


class FakeManager:
    """SourceManager stub with predefined per-service results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def load(
        self,
        service_name: str,
        source_names: list[str] | tuple[str, ...],
        source_options: dict[str, dict[str, object]] | None = None,
    ) -> SourceManagerResult:
        """Return predefined merged domains."""

        self.calls.append(
            {
                "service_name": service_name,
                "source_names": list(source_names),
                "source_options": source_options or {},
            }
        )

        if service_name == "youtube":
            domains = (
                MergedDomain(
                    domain="googlevideo.com",
                    sources=frozenset(
                        {
                            "manual",
                            "domain-list-community",
                        }
                    ),
                ),
                MergedDomain(
                    domain="youtube.com",
                    sources=frozenset({"manual"}),
                ),
            )
        elif service_name == "discord":
            domains = (
                MergedDomain(
                    domain="discord.com",
                    sources=frozenset(
                        {
                            "manual",
                            "domain-list-community",
                        }
                    ),
                ),
                MergedDomain(
                    domain="discord.gg",
                    sources=frozenset({"domain-list-community"}),
                ),
            )
        else:
            domains = ()

        return SourceManagerResult(
            service_name=service_name,
            domains=domains,
            source_results=tuple(
                object()
                for _ in source_names
            ),  # type: ignore[arg-type]
        )


def write_service_configs(services_dir: Path) -> None:
    """Create YouTube and Discord YAML configs."""

    services_dir.mkdir()

    (services_dir / "youtube.yaml").write_text(
        """
name: youtube
description: YouTube video platform
enabled: true

sources:
  - manual
  - domain-list-community

domain_list_community:
  lists:
    - youtube

domains:
  - youtube.com
  - googlevideo.com
""".strip(),
        encoding="utf-8",
    )

    (services_dir / "discord.yaml").write_text(
        """
name: discord
description: Discord communication platform
enabled: true

sources:
  - manual
  - domain-list-community

domain_list_community:
  lists:
    - discord

domains:
  - discord.com
""".strip(),
        encoding="utf-8",
    )


def test_service_source_sync_processes_multiple_services(
    tmp_path: Path,
) -> None:
    """All service configs must be synchronized."""

    services_dir = tmp_path / "services"
    write_service_configs(services_dir)

    repository = FakeRepository()
    manager = FakeManager()

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=manager,  # type: ignore[arg-type]
    ).sync()

    assert result.service_count == 2
    assert result.domain_count == 4
    assert tuple(
        item.service_name
        for item in result.services
    ) == ("discord", "youtube")

    assert [service["name"] for service in repository.services] == [
        "discord",
        "youtube",
    ]


def test_service_source_sync_preserves_domain_provenance(
    tmp_path: Path,
) -> None:
    """Each merged domain must be stored once per source."""

    services_dir = tmp_path / "services"
    write_service_configs(services_dir)

    repository = FakeRepository()

    ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    stored = {
        (
            str(item["domain"]),
            str(item["source"]),
        )
        for item in repository.domains
    }

    assert ("discord.com", "manual") in stored
    assert ("discord.com", "domain-list-community") in stored
    assert ("discord.gg", "domain-list-community") in stored
    assert ("youtube.com", "manual") in stored
    assert ("googlevideo.com", "manual") in stored
    assert (
        "googlevideo.com",
        "domain-list-community",
    ) in stored


def test_service_source_sync_passes_plugin_options(
    tmp_path: Path,
) -> None:
    """Current YAML format must be translated into plugin options."""

    services_dir = tmp_path / "services"
    write_service_configs(services_dir)

    manager = FakeManager()

    ServiceSourceSync(
        repository=FakeRepository(),  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=manager,  # type: ignore[arg-type]
    ).sync()

    calls = {
        str(call["service_name"]): call
        for call in manager.calls
    }

    assert calls["youtube"]["source_names"] == [
        "manual",
        "domain-list-community",
    ]
    assert calls["youtube"]["source_options"] == {
        "manual": {
            "domains": [
                "youtube.com",
                "googlevideo.com",
            ],
        },
        "domain-list-community": {
            "list": "youtube",
        },
    }

    assert calls["discord"]["source_options"] == {
        "manual": {
            "domains": ["discord.com"],
        },
        "domain-list-community": {
            "list": "discord",
        },
    }


def test_service_source_sync_respects_disabled_service(
    tmp_path: Path,
) -> None:
    """Domains of disabled services must be stored inactive."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "disabled.yaml").write_text(
        """
name: disabled
description: Disabled service
enabled: false

sources:
  - manual

domains:
  - disabled.example
""".strip(),
        encoding="utf-8",
    )

    class DisabledManager(FakeManager):
        def load(
            self,
            service_name: str,
            source_names: list[str] | tuple[str, ...],
            source_options: dict[str, dict[str, object]] | None = None,
        ) -> SourceManagerResult:
            del source_names, source_options

            return SourceManagerResult(
                service_name=service_name,
                domains=(
                    MergedDomain(
                        domain="disabled.example",
                        sources=frozenset({"manual"}),
                    ),
                ),
                source_results=(),
            )

    repository = FakeRepository()

    ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=DisabledManager(),  # type: ignore[arg-type]
    ).sync()

    assert repository.services[0]["enabled"] is False
    assert repository.domains[0]["active"] is False
