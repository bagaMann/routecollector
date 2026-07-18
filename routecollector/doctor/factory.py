"""
Factory for the default RouteCollector doctor runner.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.doctor.checks import (
    check_directories,
    check_environment,
)
from routecollector.doctor.runner import DoctorRunner


DEFAULT_DOCTOR_DIRECTORIES = (
    Path("config/services"),
    Path("state"),
    Path("logs"),
    Path("cache"),
    Path("bird"),
)


def build_doctor_runner(
    config_path: Path,
    directories: tuple[Path, ...] = DEFAULT_DOCTOR_DIRECTORIES,
) -> DoctorRunner:
    """Create the default read-only diagnostic runner."""

    runner = DoctorRunner()

    runner.register(
        lambda: check_environment(config_path)
    )
    runner.register(
        lambda: check_directories(directories)
    )

    return runner
