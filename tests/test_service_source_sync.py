"""
Tests for service synchronization through SourceManager.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from routecollector.sources.manager import (
    MergedDomain,
    SourceManagerResult,
)
from routecollector.sources.service_source_sync import (
    ServiceSourceSync,
)


class FakeRepository:
    """Repository stub used by source sync tests."""

    def __init__(self) -> None:
        self.services: list[dict[str, object]] = []
        self.domains: list[dict[str, object]] = []
        self.deactivated_service_ids: list[int] = []
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

    def deactivate_service_domains(
        self,
        service_id: int,
    ) -> int:
        """Record service deactivation."""

        self.deactivated_service_ids.append(service_id)
        return 4

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
    """SourceManager stub with predefined results."""

    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail = fail

    def load(
        self,
        service_name: str,
        source_names: list[str] | tuple[str, ...],
        source_options: (
            dict[str, dict[str, object]] | None
        ) = None,
    ) -> SourceManagerResult:
        """Record generic plugin input and return domains."""

        self.calls.append(
            {
                "service_name": service_name,
                "source_names": list(source_names),
                "source_options": source_options or {},
            }
        )

        if self.fail:
            raise RuntimeError("Source loading failed")

        domains = (
            MergedDomain(
                domain=f"{service_name}.example",
                sources=frozenset(source_names),
            ),
        )

        return SourceManagerResult(
            service_name=service_name,
            domains=domains,
            source_results=tuple(
                object()
                for _ in source_names
            ),  # type: ignore[arg-type]
        )


def test_sync_passes_plugin_options_unchanged(
    tmp_path: Path,
) -> None:
    """Sync must not know plugin-specific option names."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "example.yaml").write_text(
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
    repository = FakeRepository()

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=manager,  # type: ignore[arg-type]
    ).sync()

    assert result.service_count == 1
    assert result.domain_count == 1
    assert result.deactivated_count == 4

    assert manager.calls == [
        {
            "service_name": "example",
            "source_names": [
                "manual",
                "future-http-source",
            ],
            "source_options": {
                "manual": {
                    "domains": ["example.com"],
                },
                "future-http-source": {
                    "url": (
                        "https://example.test/"
                        "domains.txt"
                    ),
                    "timeout": 7,
                },
            },
        }
    ]


def test_sync_deactivates_before_reactivating_current_rows(
    tmp_path: Path,
) -> None:
    """Successful sync must deactivate old rows then upsert current rows."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "example.yaml").write_text(
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

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert repository.deactivated_service_ids == [1]
    assert result.services[0].deactivated_count == 4

    stored = {
        (
            str(item["domain"]),
            str(item["source"]),
            bool(item["active"]),
        )
        for item in repository.domains
    }

    assert stored == {
        ("example.example", "manual", True),
        ("example.example", "custom", True),
    }


def test_sync_preserves_provenance(
    tmp_path: Path,
) -> None:
    """Merged domains must be stored once per source."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "example.yaml").write_text(
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

    assert stored == {
        ("example.example", "manual"),
        ("example.example", "custom"),
    }


def test_sync_respects_disabled_service(
    tmp_path: Path,
) -> None:
    """Domains of disabled services must remain inactive."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "disabled.yaml").write_text(
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
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert repository.services[0]["enabled"] is False
    assert repository.domains[0]["active"] is False


def test_source_failure_does_not_deactivate_existing_rows(
    tmp_path: Path,
) -> None:
    """Plugin failure must leave the previous active set untouched."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "example.yaml").write_text(
        """
name: example
sources:
  - type: manual
    domains:
      - example.com
""".strip(),
        encoding="utf-8",
    )

    repository = FakeRepository()

    with pytest.raises(
        RuntimeError,
        match="Source loading failed",
    ):
        ServiceSourceSync(
            repository=repository,  # type: ignore[arg-type]
            services_dir=services_dir,
            manager=FakeManager(
                fail=True
            ),  # type: ignore[arg-type]
        ).sync()

    assert repository.services == []
    assert repository.deactivated_service_ids == []
    assert repository.domains == []
