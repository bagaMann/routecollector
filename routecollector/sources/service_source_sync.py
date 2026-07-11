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
from routecollector.sources.default_registry import create_default_registry
from routecollector.sources.manager import SourceManager


@dataclass(slots=True, frozen=True)
class ServiceSourceSyncResult:
    """Synchronization result for one service."""

    service_name: str
    source_count: int
    domain_count: int


@dataclass(slots=True, frozen=True)
class SourceSyncResult:
    """Synchronization result for all configured services."""

    service_count: int
    domain_count: int
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
        """Load all service configs and synchronize their domains."""

        configs = ServiceConfigLoader(
            self._services_dir
        ).load_all()

        service_results: list[ServiceSourceSyncResult] = []
        total_domains = 0

        for config in configs:
            result = self._sync_service(config)
            service_results.append(result)
            total_domains += result.domain_count

        return SourceSyncResult(
            service_count=len(service_results),
            domain_count=total_domains,
            services=tuple(service_results),
        )

    def _sync_service(
        self,
        config: ServiceConfig,
    ) -> ServiceSourceSyncResult:
        """Synchronize one service configuration."""

        service_id = self._repository.upsert_service(
            name=config.name,
            description=config.description,
            enabled=config.enabled,
        )

        source_names = self._resolve_source_names(config)
        source_options = self._build_source_options(config)

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

    @staticmethod
    def _resolve_source_names(
        config: ServiceConfig,
    ) -> list[str]:
        """Return normalized source names from service config."""

        source_names = [
            source.strip().lower()
            for source in config.sources
            if source.strip()
        ]

        return list(dict.fromkeys(source_names))

    @staticmethod
    def _build_source_options(
        config: ServiceConfig,
    ) -> dict[str, dict[str, object]]:
        """Translate current service config into plugin options."""

        options: dict[str, dict[str, object]] = {}

        if "manual" in config.sources:
            options["manual"] = {
                "domains": list(config.domains),
            }

        if "domain-list-community" in config.sources:
            lists = list(config.domain_list_community_lists)

            if lists:
                options["domain-list-community"] = {
                    "list": lists[0],
                }
            else:
                options["domain-list-community"] = {
                    "list": config.name,
                }

        return options
