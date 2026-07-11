"""
Base interfaces and models for RouteCollector domain sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class DomainSourceError(RuntimeError):
    """Domain source loading error."""


@dataclass(slots=True, frozen=True)
class DomainSourceRequest:
    """Request passed to a domain source."""

    service_name: str
    source_name: str
    source_options: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DomainSourceResult:
    """Normalized result returned by a domain source."""

    source_name: str
    service_name: str
    domains: frozenset[str]
    metadata: dict[str, object] = field(default_factory=dict)


class DomainSource(ABC):
    """Base interface for all domain sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return unique source name."""

    @abstractmethod
    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        """Load and normalize domains for one service."""

    @staticmethod
    def normalize_domain(value: str) -> str | None:
        """Normalize one domain value.

        Returns None when the input is empty or unsupported.
        """

        domain = value.strip().lower().rstrip(".")

        if not domain:
            return None

        if domain.startswith("*."):
            domain = domain[2:]

        if domain.startswith("."):
            domain = domain[1:]

        if not domain:
            return None

        if "://" in domain:
            return None

        if "/" in domain:
            return None

        if " " in domain or "	" in domain:
            return None

        if domain.startswith("regexp:"):
            return None

        if domain.startswith("keyword:"):
            return None

        if domain.startswith("full:"):
            domain = domain[5:]

        if domain.startswith("domain:"):
            domain = domain[7:]

        domain = domain.strip().lower().rstrip(".")

        if not domain:
            return None

        labels = domain.split(".")

        if len(labels) < 2:
            return None

        for label in labels:
            if not label:
                return None

            if len(label) > 63:
                return None

            if label.startswith("-") or label.endswith("-"):
                return None

            for character in label:
                if not (
                    character.isalnum()
                    or character == "-"
                    or ord(character) > 127
                ):
                    return None

        return domain

    @classmethod
    def normalize_domains(
        cls,
        values: set[str] | list[str] | tuple[str, ...],
    ) -> frozenset[str]:
        """Normalize and deduplicate domain values."""

        normalized: set[str] = set()

        for value in values:
            domain = cls.normalize_domain(value)

            if domain is not None:
                normalized.add(domain)

        return frozenset(normalized)
