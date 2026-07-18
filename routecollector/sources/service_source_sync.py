"""
Synchronize service configurations through the pluggable SourceManager.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from routecollector.core.repository import Repository
from routecollector.parser.service_config import (
    ServiceConfig,
    ServiceConfigLoader,
)
from routecollector.sources.base import DomainSourceResult
from routecollector.sources.default_registry import (
    create_default_registry,
)
from routecollector.sources.manager import SourceManager


@dataclass(slots=True, frozen=True)
class SourceExecutionResult:
    """Synchronization statistics for one executed source plugin."""

    source_name: str
    domain_count: int
    metadata: dict[str, object]


@dataclass(slots=True, frozen=True)
class ServiceSourceSyncResult:
    """Synchronization result for one configured service."""

    service_name: str
    enabled: bool
    source_count: int
    domain_count: int
    deactivated_count: int
    sources: tuple[SourceExecutionResult, ...]


@dataclass(slots=True, frozen=True)
class SourceSyncResult:
    """Synchronization result for all service configurations."""

    service_count: int
    source_count: int
    domain_count: int
    deactivated_count: int
    disabled_service_count: int
    services: tuple[ServiceSourceSyncResult, ...]


class ServiceSourceSync:
    """Synchronize service domains using registered source plugins."""

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
        """Synchronize configured services and disable removed ones."""

        configs = ServiceConfigLoader(
            self._services_dir
        ).load_all()

        service_results: list[
            ServiceSourceSyncResult
        ] = []
        total_sources = 0
        total_domains = 0
        total_deactivated = 0
        configured_names = {
            config.name
            for config in configs
        }

        for config in configs:
            result = self._sync_service(config)
            service_results.append(result)
            total_sources += result.source_count
            total_domains += result.domain_count
            total_deactivated += result.deactivated_count

        disabled_service_count, removed_domains = (
            self._disable_missing_services(
                configured_names
            )
        )
        total_deactivated += removed_domains

        return SourceSyncResult(
            service_count=len(service_results),
            source_count=total_sources,
            domain_count=total_domains,
            deactivated_count=total_deactivated,
            disabled_service_count=disabled_service_count,
            services=tuple(service_results),
        )

    def _sync_service(
        self,
        config: ServiceConfig,
    ) -> ServiceSourceSyncResult:
        """
        Synchronize one service configuration.

        Sources are loaded before existing rows are deactivated. Therefore,
        a plugin failure leaves the previously active domain set untouched.
        """

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

        service_id = self._repository.upsert_service(
            name=config.name,
            description=config.description,
            enabled=config.enabled,
        )

        deactivated_count = (
            self._repository.deactivate_service_domains(
                service_id
            )
        )

        for item in merged.domains:
            for source_name in sorted(item.sources):
                self._repository.upsert_domain(
                    service_id=service_id,
                    domain=item.domain,
                    source=source_name,
                    active=config.enabled,
                )

        source_results = tuple(
            self._build_source_execution_result(result)
            for result in merged.source_results
        )

        return ServiceSourceSyncResult(
            service_name=config.name,
            enabled=config.enabled,
            source_count=len(source_results),
            domain_count=len(merged.domains),
            deactivated_count=deactivated_count,
            sources=source_results,
        )

    @staticmethod
    def _build_source_execution_result(
        result: DomainSourceResult,
    ) -> SourceExecutionResult:
        """Convert one plugin result into stable sync statistics."""

        return SourceExecutionResult(
            source_name=result.source_name,
            domain_count=len(result.domains),
            metadata=dict(result.metadata),
        )

    def _disable_missing_services(
        self,
        configured_names: set[str],
    ) -> tuple[int, int]:
        """Disable services no longer represented by YAML files."""

        disabled_service_count = 0
        deactivated_domain_count = 0

        for service in self._repository.list_services():
            if service.name in configured_names:
                continue

            if service.enabled:
                self._repository.upsert_service(
                    name=service.name,
                    description=service.description,
                    enabled=False,
                )
                disabled_service_count += 1

            deactivated_domain_count += (
                self._repository.deactivate_service_domains(
                    service.id
                )
            )

        return (
            disabled_service_count,
            deactivated_domain_count,
        )
