"""Core models for RouteCollector diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class DoctorStatus(IntEnum):
    """Severity of one diagnostic check."""

    OK = 0
    WARNING = 1
    ERROR = 2

    @property
    def label(self) -> str:
        """Return stable human-readable status label."""

        return self.name


@dataclass(slots=True, frozen=True)
class DoctorCheck:
    """Result of one read-only diagnostic check."""

    category: str
    name: str
    status: DoctorStatus
    message: str = ""

    def __post_init__(self) -> None:
        """Reject incomplete checks."""

        if not self.category.strip():
            raise ValueError("Doctor check category cannot be empty")

        if not self.name.strip():
            raise ValueError("Doctor check name cannot be empty")


@dataclass(slots=True, frozen=True)
class DoctorResult:
    """Aggregated RouteCollector diagnostics."""

    checks: tuple[DoctorCheck, ...]

    @classmethod
    def from_checks(
        cls,
        checks: Iterable[DoctorCheck],
    ) -> "DoctorResult":
        """Create an immutable result."""

        return cls(checks=tuple(checks))

    @property
    def check_count(self) -> int:
        return len(self.checks)

    @property
    def ok_count(self) -> int:
        return self._count_status(DoctorStatus.OK)

    @property
    def warning_count(self) -> int:
        return self._count_status(DoctorStatus.WARNING)

    @property
    def error_count(self) -> int:
        return self._count_status(DoctorStatus.ERROR)

    @property
    def overall_status(self) -> DoctorStatus:
        if not self.checks:
            return DoctorStatus.OK

        return max(check.status for check in self.checks)

    @property
    def exit_code(self) -> int:
        return int(self.overall_status)

    @property
    def overall_label(self) -> str:
        if self.overall_status is DoctorStatus.ERROR:
            return "FAILED"

        if self.overall_status is DoctorStatus.WARNING:
            return "WARNING"

        return "HEALTHY"

    def by_category(
        self,
    ) -> tuple[tuple[str, tuple[DoctorCheck, ...]], ...]:
        """Group checks while preserving category order."""

        grouped: dict[str, list[DoctorCheck]] = {}

        for check in self.checks:
            grouped.setdefault(check.category, []).append(check)

        return tuple(
            (category, tuple(category_checks))
            for category, category_checks in grouped.items()
        )

    def _count_status(self, status: DoctorStatus) -> int:
        return sum(check.status is status for check in self.checks)
