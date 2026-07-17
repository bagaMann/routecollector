"""
Tests for service synchronization through SourceManager.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from routecollector.core.repository import Service
from routecollector.sources.manager import MergedDomain, SourceManagerResult
from routecollector.sources.service_source_sync import ServiceSourceSync


class FakeRepository:
    """Repository stub used by source sync tests."""

    def __init__(
        self,
        existing_services: list[Service] | None = None,
    ) -> None:
        self.services: list[dict[str, object]] = []
        self.domains: list[dict[str, object]] = []
        self.deactivated_service_ids: list[int] = []
        self._existing_services = existing_services or []
        self._next_service_id = (
            max((service.id for service in self._existing_services), default=0)
            + 1
        )

    def list_services(self) -> list[Service]:
        """Return predefined existing services."""

        return list(self._existing_services)

    def upsert_service(
        self,
        name: str,
        description: str | None = None,
        enabled: bool = True,
    ) -> int:
        """Record service and return stable or synthetic ID."""

        existing = next(
            (
                service
                for service in self._existing_services
                if service.name == name
            ),
            None,
        )
        service_id = existing.id if existing is not None else self._next_service_id

        if existing is None:
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

    def deactivate_service_domains(self, service_id: int) -> int:
        """Record service domain deactivation."""

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

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail = fail

    def load(
        self,
        service_name: str,
        source_names: list[str] | tuple[str, ...],
        source_options: dict[str, dict[str, object]] | None = None,
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


def write_service(
    services_dir: Path,
    *,
    name: str = "example",
    enabled: bool = True,
) -> None:
    """Write one minimal declarative service config."""

    services_dir.mkdir(parents=True, exist_ok=True)
    (services_dir / f"{name}.yaml").write_text(
        f"""
name: {name}
enabled: {str(enabled).lower()}
sources:
  - type: manual
    domains:
      - {name}.com
""".strip(),
        encoding="utf-8",
    )


def test_sync_passes_plugin_options_unchanged(tmp_path: Path) -> None:
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
    assert result.disabled_service_count == 0
    assert manager.calls[0]["source_options"] == {
        "manual": {"domains": ["example.com"]},
        "future-http-source": {
            "url": "https://example.test/domains.txt",
            "timeout": 7,
        },
    }


def test_sync_deactivates_before_reactivating_current_rows(
    tmp_path: Path,
) -> None:
    """Successful sync must deactivate old rows then upsert current rows."""

    services_dir = tmp_path / "services"
    write_service(services_dir)
    repository = FakeRepository()

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert repository.deactivated_service_ids == [1]
    assert result.services[0].deactivated_count == 4
    assert repository.domains == [
        {
            "service_id": 1,
            "domain": "example.example",
            "source": "manual",
            "active": True,
        }
    ]


def test_sync_respects_disabled_service(tmp_path: Path) -> None:
    """Domains of disabled configured services must remain inactive."""

    services_dir = tmp_path / "services"
    write_service(services_dir, name="disabled", enabled=False)
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
    write_service(services_dir)
    repository = FakeRepository(
        [
            Service(
                id=5,
                name="example",
                enabled=True,
                description=None,
            )
        ]
    )

    with pytest.raises(RuntimeError, match="Source loading failed"):
        ServiceSourceSync(
            repository=repository,  # type: ignore[arg-type]
            services_dir=services_dir,
            manager=FakeManager(fail=True),  # type: ignore[arg-type]
        ).sync()

    assert repository.services == []
    assert repository.deactivated_service_ids == []
    assert repository.domains == []


def test_sync_disables_service_missing_from_yaml(tmp_path: Path) -> None:
    """Removed YAML must disable service and deactivate its domains."""

    services_dir = tmp_path / "services"
    write_service(services_dir, name="youtube")
    repository = FakeRepository(
        [
            Service(1, "youtube", True, "YouTube"),
            Service(2, "http-test", True, "Temporary service"),
        ]
    )

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert {
        "id": 2,
        "name": "http-test",
        "description": "Temporary service",
        "enabled": False,
    } in repository.services
    assert 2 in repository.deactivated_service_ids
    assert result.disabled_service_count == 1
    assert result.deactivated_count == 8


def test_sync_does_not_recount_already_disabled_missing_service(
    tmp_path: Path,
) -> None:
    """Already disabled missing service must stay disabled idempotently."""

    services_dir = tmp_path / "services"
    write_service(services_dir, name="youtube")
    repository = FakeRepository(
        [
            Service(2, "http-test", False, "Temporary service"),
        ]
    )

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert not any(item["name"] == "http-test" for item in repository.services)
    assert 2 in repository.deactivated_service_ids
    assert result.disabled_service_count == 0


def test_empty_config_directory_disables_all_services(
    tmp_path: Path,
) -> None:
    """No YAML files must disable all previously enabled services."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()
    repository = FakeRepository(
        [
            Service(1, "youtube", True, None),
            Service(2, "telegram", True, None),
        ]
    )

    result = ServiceSourceSync(
        repository=repository,  # type: ignore[arg-type]
        services_dir=services_dir,
        manager=FakeManager(),  # type: ignore[arg-type]
    ).sync()

    assert result.service_count == 0
    assert result.domain_count == 0
    assert result.disabled_service_count == 2
    assert repository.deactivated_service_ids == [1, 2]
