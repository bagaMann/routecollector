"""Tests for generic service source synchronization."""

from pathlib import Path

from routecollector.sources.manager import (
    MergedDomain,
    SourceManagerResult,
)
from routecollector.sources.service_source_sync import (
    ServiceSourceSync,
)


class FakeRepository:
    def __init__(self) -> None:
        self.services: list[dict[str, object]] = []
        self.domains: list[dict[str, object]] = []

    def upsert_service(
        self,
        name: str,
        description: str | None = None,
        enabled: bool = True,
    ) -> int:
        self.services.append(
            {
                "name": name,
                "description": description,
                "enabled": enabled,
            }
        )
        return len(self.services)

    def upsert_domain(
        self,
        service_id: int,
        domain: str,
        source: str,
        active: bool = True,
    ) -> int:
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
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def load(
        self,
        service_name: str,
        source_names: list[str] | tuple[str, ...],
        source_options: dict[str, dict[str, object]] | None = None,
    ) -> SourceManagerResult:
        self.calls.append(
            {
                "service_name": service_name,
                "source_names": list(source_names),
                "source_options": source_options or {},
            }
        )
        return SourceManagerResult(
            service_name=service_name,
            domains=(
                MergedDomain(
                    domain=f"{service_name}.example",
                    sources=frozenset(source_names),
                ),
            ),
            source_results=tuple(
                object() for _ in source_names
            ),  # type: ignore[arg-type]
        )


def test_sync_passes_plugin_options_unchanged(
    tmp_path: Path,
) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "example.yaml").write_text(
        """
name: example
sources:
  - type: manual
    domains:
      - example.com
  - type: future-http-source
    url: https://example.test/domains.txt
    timeout: 7
""".strip(),
        encoding="utf-8",
    )

    manager = FakeManager()
    result = ServiceSourceSync(
        repository=FakeRepository(),  # type: ignore[arg-type]
        services_dir=services,
        manager=manager,  # type: ignore[arg-type]
    ).sync()

    assert result.service_count == 1
    assert manager.calls == [
        {
            "service_name": "example",
            "source_names": [
                "manual",
                "future-http-source",
            ],
            "source_options": {
                "manual": {
                    "domains": ["example.com"]
                },
                "future-http-source": {
                    "url": (
                        "https://example.test/domains.txt"
                    ),
                    "timeout": 7,
                },
            },
        }
    ]


def test_sync_preserves_provenance(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "example.yaml").write_text(
        """
name: example
sources:
  - type: manual
    domains:
      - example.com
  - type: custom
    token: test
""".strip(),
        encoding="utf-8",
    )

    repository = FakeRepository()
    ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    stored = {
        (str(item["domain"]), str(item["source"]))
        for item in repository.domains
    }
    assert stored == {
        ("example.example", "manual"),
        ("example.example", "custom"),
    }


def test_sync_respects_disabled_service(
    tmp_path: Path,
) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "disabled.yaml").write_text(
        """
name: disabled
enabled: false
sources:
  - type: manual
    domains:
      - disabled.example
""".strip(),
        encoding="utf-8",
    )

    repository = FakeRepository()
    ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert repository.services[0]["enabled"] is False
    assert repository.domains[0]["active"] is False
