"""
Environment and filesystem checks for RouteCollector doctor.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Iterable

from routecollector import __version__
from routecollector.doctor.models import (
    DoctorCheck,
    DoctorStatus,
)


def check_environment(
    config_path: Path,
) -> tuple[DoctorCheck, ...]:
    """Check Python, RouteCollector version and configuration file."""

    checks: list[DoctorCheck] = []

    checks.append(
        DoctorCheck(
            category="Environment",
            name="Python",
            status=DoctorStatus.OK,
            message=platform.python_version(),
        )
    )

    checks.append(
        DoctorCheck(
            category="Environment",
            name="RouteCollector",
            status=DoctorStatus.OK,
            message=__version__,
        )
    )

    checks.append(
        _check_file(
            category="Environment",
            name="Configuration",
            path=config_path,
            missing_status=DoctorStatus.ERROR,
        )
    )

    return tuple(checks)


def check_directories(
    directories: Iterable[Path],
) -> tuple[DoctorCheck, ...]:
    """Check required directories and their access rights."""

    checks: list[DoctorCheck] = []

    for directory in directories:
        checks.append(
            _check_directory(directory)
        )

    return tuple(checks)


def _check_file(
    *,
    category: str,
    name: str,
    path: Path,
    missing_status: DoctorStatus,
) -> DoctorCheck:
    """Check one required readable file."""

    if not path.exists():
        return DoctorCheck(
            category=category,
            name=name,
            status=missing_status,
            message=f"missing: {path}",
        )

    if not path.is_file():
        return DoctorCheck(
            category=category,
            name=name,
            status=DoctorStatus.ERROR,
            message=f"not a file: {path}",
        )

    if not os.access(path, os.R_OK):
        return DoctorCheck(
            category=category,
            name=name,
            status=DoctorStatus.ERROR,
            message=f"not readable: {path}",
        )

    return DoctorCheck(
        category=category,
        name=name,
        status=DoctorStatus.OK,
        message=str(path),
    )


def _check_directory(
    directory: Path,
) -> DoctorCheck:
    """Check one required readable and writable directory."""

    name = str(directory)

    if not directory.exists():
        return DoctorCheck(
            category="Directories",
            name=name,
            status=DoctorStatus.ERROR,
            message="missing",
        )

    if not directory.is_dir():
        return DoctorCheck(
            category="Directories",
            name=name,
            status=DoctorStatus.ERROR,
            message="not a directory",
        )

    readable = os.access(directory, os.R_OK)
    writable = os.access(directory, os.W_OK)
    executable = os.access(directory, os.X_OK)

    if not readable:
        return DoctorCheck(
            category="Directories",
            name=name,
            status=DoctorStatus.ERROR,
            message="not readable",
        )

    if not executable:
        return DoctorCheck(
            category="Directories",
            name=name,
            status=DoctorStatus.ERROR,
            message="not searchable",
        )

    if not writable:
        return DoctorCheck(
            category="Directories",
            name=name,
            status=DoctorStatus.WARNING,
            message="readable but not writable",
        )

    return DoctorCheck(
        category="Directories",
        name=name,
        status=DoctorStatus.OK,
        message="readable and writable",
    )
