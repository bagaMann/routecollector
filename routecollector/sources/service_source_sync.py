"""Synchronize service configurations through SourceManager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from routecollector.core.repository import Repository
from routecollector.parser.service_config import (
    ServiceConfig,
    ServiceConfigLoader,
)
from routecollector.sources.default_registry import (
    create_default_registry,
)
from routecollector.sources.manager import SourceManager


@dataclass(slots=True, frozen=True)
class ServiceSourceSyncResult:
    service_name: str
    source_count: int
    domain_count: int


@dataclass(slots=True, frozen=True)
class SourceSyncResult:
    service_count: int
    domain_count: int
    services: tuple[ServiceSourceSyncResult, ...]


class ServiceSourceSync:
    """Synchronize service domains using registered plugins."""

    def __init__(
        self,
        repository: Repository,
        services_dir: Path,
        manager: SourceManager | None = None,
    ) -> None:
        self._repository = repository
        self._services_dir = services_dir
        self._manager = manager or SourceManager(
            create_default_registry()
        )

    def sync(self) -> SourceSyncResult:
        configs = ServiceConfigLoader(
            self._services_dir
        ).load_all()

        results: list[ServiceSourceSyncResult] = []
        total_domains = 0

        for config in configs:
            result = self._sync_service(config)
            results.append(result)
            total_domains += result.domain_count

        return SourceSyncResult(
            service_count=len(results),
            domain_count=total_domains,
            services=tuple(results),
        )

    def _sync_service(
        self,
        config: ServiceConfig,
    ) -> ServiceSourceSyncResult:
        service_id = self._repository.upsert_service(
            name=config.name,
            description=config.description,
            enabled=config.enabled,
        )

        source_names = [
            source.type
            for source in config.source_configs
        ]
        source_options = {
            source.type: dict(source.options)
            for source in config.source_configs
        }

        merged = self._manager.load(
            service_name=config.name,
            source_names=source_names,
            source_options=source_options,
        )

        for item in merged.domains:
            for source_name in sorted(item.sources):
                self._repository.upsert_domain(
                    service_id=service_id,
                    domain=item.domain,
                    source=source_name,
                    active=config.enabled,
                )

        return ServiceSourceSyncResult(
            service_name=config.name,
            source_count=len(merged.source_results),
            domain_count=len(merged.domains),
        )
