"""
Service configuration parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from routecollector.core.repository import Repository
from routecollector.sources.domain_list_community import (
    DomainListCommunityClient,
    DomainListCommunityParser,
)


@dataclass(slots=True, frozen=True)
class ServiceConfig:
    """Service configuration model."""

    name: str
    enabled: bool
    description: str | None
    domains: list[str]
    sources: list[str]
    domain_list_community_lists: list[str]


class ServiceConfigError(RuntimeError):
    """Service configuration error."""


class ServiceConfigLoader:
    """Load service YAML files."""

    def __init__(self, services_dir: Path) -> None:
        self._services_dir = services_dir

    def load_all(self) -> list[ServiceConfig]:
        """Load all service configs from directory."""

        if not self._services_dir.exists():
            return []

        configs: list[ServiceConfig] = []

        for filename in sorted(self._services_dir.glob("*.yaml")):
            configs.append(self._load_file(filename))

        return configs

    def _load_file(self, filename: Path) -> ServiceConfig:
        with filename.open("r", encoding="utf-8") as file:
            data: dict[str, Any] | None = yaml.safe_load(file)

        if not data:
            raise ServiceConfigError(f"Empty service config: {filename}")

        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise ServiceConfigError(f"Missing service name: {filename}")

        enabled = bool(data.get("enabled", True))
        description = data.get("description")

        domains_raw = data.get("domains", [])
        if not isinstance(domains_raw, list):
            raise ServiceConfigError(f"'domains' must be list: {filename}")

        sources_raw = data.get("sources", ["manual"])
        if not isinstance(sources_raw, list):
            raise ServiceConfigError(f"'sources' must be list: {filename}")

        dlc_raw = data.get("domain_list_community", {})
        if dlc_raw is None:
            dlc_raw = {}

        if not isinstance(dlc_raw, dict):
            raise ServiceConfigError(
                f"'domain_list_community' must be mapping: {filename}"
            )

        dlc_lists_raw = dlc_raw.get("lists", [])
        if not isinstance(dlc_lists_raw, list):
            raise ServiceConfigError(
                f"'domain_list_community.lists' must be list: {filename}"
            )

        domains = [str(domain).strip() for domain in domains_raw if str(domain).strip()]
        sources = [str(source).strip() for source in sources_raw if str(source).strip()]
        dlc_lists = [
            str(list_name).strip()
            for list_name in dlc_lists_raw
            if str(list_name).strip()
        ]

        return ServiceConfig(
            name=name,
            enabled=enabled,
            description=description if isinstance(description, str) else None,
            domains=domains,
            sources=sources,
            domain_list_community_lists=dlc_lists,
        )


class ServiceConfigSync:
    """Synchronize service configs into repository."""

    def __init__(
        self,
        repository: Repository,
        services_dir: Path,
        cache_dir: Path = Path("cache/domain-list-community"),
    ) -> None:
        self._repository = repository
        self._loader = ServiceConfigLoader(services_dir)
        self._dlc_client = DomainListCommunityClient(cache_dir)
        self._dlc_parser = DomainListCommunityParser()

    def sync(self) -> tuple[int, int]:
        """Sync service configs.

        Returns:
            tuple[int, int]: Number of synced services and domains.
        """

        service_count = 0
        domain_count = 0

        for service in self._loader.load_all():
            service_id = self._repository.upsert_service(
                name=service.name,
                description=service.description,
                enabled=service.enabled,
            )
            service_count += 1

            for domain in service.domains:
                self._repository.upsert_domain(
                    service_id=service_id,
                    domain=domain,
                    source="manual",
                    active=True,
                )
                domain_count += 1

            for list_name in service.domain_list_community_lists:
                cached_file = self._dlc_client.fetch(list_name)
                entries = self._dlc_parser.parse_file(
                    cached_file,
                    source_name=f"domain-list-community:{list_name}",
                )

                for entry in entries:
                    self._repository.upsert_domain(
                        service_id=service_id,
                        domain=entry.domain,
                        source=entry.source,
                        active=True,
                    )
                    domain_count += 1

        return service_count, domain_count
