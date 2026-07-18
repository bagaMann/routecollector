"""
Service configuration parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True, frozen=True)
class SourceConfig:
    """Normalized configuration for one source plugin."""

    type: str
    options: dict[str, object]


@dataclass(slots=True, frozen=True)
class ServiceConfig:
    """Service configuration model."""

    name: str
    enabled: bool
    description: str | None
    source_configs: tuple[SourceConfig, ...]

    # Compatibility fields retained for existing callers.
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

        for filename in sorted(
            self._services_dir.glob("*.yaml")
        ):
            configs.append(self._load_file(filename))

        return configs

    def _load_file(self, filename: Path) -> ServiceConfig:
        """Load and normalize one service YAML file."""

        with filename.open(
            "r",
            encoding="utf-8",
        ) as file:
            data: dict[str, Any] | None = yaml.safe_load(file)

        if not data:
            raise ServiceConfigError(
                f"Empty service config: {filename}"
            )

        name = data.get("name")

        if not isinstance(name, str) or not name.strip():
            raise ServiceConfigError(
                f"Missing service name: {filename}"
            )

        name = name.strip()
        enabled = bool(data.get("enabled", True))
        description = data.get("description")

        domains = self._parse_string_list(
            data.get("domains", []),
            field_name="domains",
            filename=filename,
        )

        dlc_raw = data.get(
            "domain_list_community",
            {},
        )

        if dlc_raw is None:
            dlc_raw = {}

        if not isinstance(dlc_raw, dict):
            raise ServiceConfigError(
                "'domain_list_community' must be mapping: "
                f"{filename}"
            )

        dlc_lists = self._parse_string_list(
            dlc_raw.get("lists", []),
            field_name="domain_list_community.lists",
            filename=filename,
        )

        source_configs = self._parse_sources(
            raw_sources=data.get("sources", ["manual"]),
            service_name=name,
            legacy_domains=domains,
            legacy_dlc_lists=dlc_lists,
            filename=filename,
        )

        source_names = [
            source.type
            for source in source_configs
        ]

        return ServiceConfig(
            name=name,
            enabled=enabled,
            description=(
                description
                if isinstance(description, str)
                else None
            ),
            source_configs=source_configs,
            domains=domains,
            sources=source_names,
            domain_list_community_lists=dlc_lists,
        )

    def _parse_sources(
        self,
        *,
        raw_sources: object,
        service_name: str,
        legacy_domains: list[str],
        legacy_dlc_lists: list[str],
        filename: Path,
    ) -> tuple[SourceConfig, ...]:
        """Parse legacy strings and declarative source mappings."""

        if not isinstance(raw_sources, list):
            raise ServiceConfigError(
                f"'sources' must be list: {filename}"
            )

        parsed: list[SourceConfig] = []
        seen: set[str] = set()

        for index, raw_source in enumerate(raw_sources):
            if isinstance(raw_source, str):
                source_type = raw_source.strip().lower()

                if not source_type:
                    continue

                options = self._legacy_source_options(
                    source_type=source_type,
                    service_name=service_name,
                    domains=legacy_domains,
                    dlc_lists=legacy_dlc_lists,
                )

            elif isinstance(raw_source, dict):
                source_type_raw = raw_source.get("type")

                if (
                    not isinstance(source_type_raw, str)
                    or not source_type_raw.strip()
                ):
                    raise ServiceConfigError(
                        "Source mapping requires non-empty "
                        f"'type' at index {index}: {filename}"
                    )

                source_type = (
                    source_type_raw.strip().lower()
                )

                options_raw = raw_source.get("options")

                if options_raw is None:
                    options = {
                        str(key): value
                        for key, value in raw_source.items()
                        if key != "type"
                    }
                elif isinstance(options_raw, dict):
                    extra_keys = {
                        key
                        for key in raw_source
                        if key not in {"type", "options"}
                    }

                    if extra_keys:
                        raise ServiceConfigError(
                            "Source mapping cannot mix 'options' "
                            "with direct option keys at index "
                            f"{index}: {filename}"
                        )

                    options = {
                        str(key): value
                        for key, value in options_raw.items()
                    }
                else:
                    raise ServiceConfigError(
                        "Source 'options' must be mapping at "
                        f"index {index}: {filename}"
                    )

            else:
                raise ServiceConfigError(
                    "Each source must be a string or mapping "
                    f"at index {index}: {filename}"
                )

            if source_type in seen:
                raise ServiceConfigError(
                    "Duplicate source type "
                    f"'{source_type}': {filename}"
                )

            seen.add(source_type)
            parsed.append(
                SourceConfig(
                    type=source_type,
                    options=options,
                )
            )

        return tuple(parsed)

    @staticmethod
    def _legacy_source_options(
        *,
        source_type: str,
        service_name: str,
        domains: list[str],
        dlc_lists: list[str],
    ) -> dict[str, object]:
        """Translate the old YAML layout into plugin options."""

        if source_type == "manual":
            return {
                "domains": list(domains),
            }

        if source_type == "domain-list-community":
            return {
                "list": (
                    dlc_lists[0]
                    if dlc_lists
                    else service_name
                ),
            }

        return {}

    @staticmethod
    def _parse_string_list(
        raw_value: object,
        *,
        field_name: str,
        filename: Path,
    ) -> list[str]:
        """Validate and normalize a list of strings."""

        if not isinstance(raw_value, list):
            raise ServiceConfigError(
                f"'{field_name}' must be list: {filename}"
            )

        values: list[str] = []

        for item in raw_value:
            if not isinstance(item, str):
                raise ServiceConfigError(
                    f"'{field_name}' must contain only "
                    f"strings: {filename}"
                )

            value = item.strip()

            if value:
                values.append(value)

        return values
