"""Diagnostic runner abstraction."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from routecollector.doctor.models import DoctorCheck, DoctorResult


DoctorCheckFunction = Callable[[], DoctorCheck | Iterable[DoctorCheck]]


class DoctorRunner:
    """Execute registered read-only diagnostic checks."""

    def __init__(
        self,
        checks: Iterable[DoctorCheckFunction] = (),
    ) -> None:
        self._checks = list(checks)

    def register(self, check: DoctorCheckFunction) -> None:
        self._checks.append(check)

    def run(self) -> DoctorResult:
        results: list[DoctorCheck] = []

        for check_function in self._checks:
            value = check_function()

            if isinstance(value, DoctorCheck):
                results.append(value)
            else:
                results.extend(value)

        return DoctorResult.from_checks(results)
