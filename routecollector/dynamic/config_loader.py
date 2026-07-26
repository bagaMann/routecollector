"""
Load dynamic DNS matching rules from service YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from routecollector.dynamic.domain_matcher import (
    DomainMatchRule,
    DomainMatcher,
)


class DynamicConfigError(ValueError):
    """Invalid dynamic DNS service configuration."""


class DynamicConfigLoader:
    """Load dynamic DNS match rules from service YAML files."""

    def __init__(
        self,
        services_dir: Path,
    ) -> None:
        self._services_dir = services_dir

    def load_rules(
        self,
    ) -> tuple[DomainMatchRule, ...]:
        """Load enabled dynamic matching rules."""

        if not self._services_dir.exists():
            return ()

        if not self._services_dir.is_dir():
            raise DynamicConfigError(
                f"Services path is not a directory: "
                f"{self._services_dir}"
            )

        rules: list[DomainMatchRule] = []

        for path in sorted(
            self._services_dir.glob("*.yaml")
        ):
            rule = self._load_file(path)

            if rule is not None:
                rules.append(rule)

        return tuple(rules)

    def build_matcher(
        self,
    ) -> DomainMatcher:
        """Build matcher from all configured dynamic rules."""

        return DomainMatcher(
            self.load_rules()
        )

    def _load_file(
        self,
        path: Path,
    ) -> DomainMatchRule | None:
        try:
            payload = yaml.safe_load(
                path.read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError) as exc:
            raise DynamicConfigError(
                f"Unable to read {path}: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise DynamicConfigError(
                f"Service configuration must be a mapping: "
                f"{path}"
            )

        service_name = payload.get("name")

        if not isinstance(service_name, str):
            raise DynamicConfigError(
                f"Service name is missing in {path}"
            )

        if payload.get("enabled", True) is False:
            return None

        dynamic = payload.get("dynamic")

        if dynamic is None:
            return None

        if not isinstance(dynamic, dict):
            raise DynamicConfigError(
                f"dynamic must be a mapping in {path}"
            )

        if dynamic.get("enabled", True) is False:
            return None

        match = dynamic.get("match")

        if not isinstance(match, dict):
            raise DynamicConfigError(
                f"dynamic.match must be a mapping in {path}"
            )

        domains = match.get("domains")

        if not isinstance(domains, list):
            raise DynamicConfigError(
                f"dynamic.match.domains must be a list "
                f"in {path}"
            )

        normalized_domains = self._load_domains(
            domains,
            path,
        )

        include_subdomains = match.get(
            "include_subdomains",
            True,
        )

        if not isinstance(include_subdomains, bool):
            raise DynamicConfigError(
                f"dynamic.match.include_subdomains must "
                f"be boolean in {path}"
            )

        return DomainMatchRule(
            service_name=service_name,
            domains=normalized_domains,
            include_subdomains=include_subdomains,
        )

    @staticmethod
    def _load_domains(
        raw_domains: list[Any],
        path: Path,
    ) -> tuple[str, ...]:
        domains: list[str] = []

        for item in raw_domains:
            if not isinstance(item, str):
                raise DynamicConfigError(
                    f"Dynamic domain must be a string "
                    f"in {path}"
                )

            domains.append(
                DomainMatcher.normalize_domain(item)
            )

        if not domains:
            raise DynamicConfigError(
                f"dynamic.match.domains cannot be empty "
                f"in {path}"
            )

        return tuple(
            dict.fromkeys(domains)
        )
