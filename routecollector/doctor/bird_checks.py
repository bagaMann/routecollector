"""
Read-only BIRD checks for RouteCollector doctor.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from routecollector.doctor.models import (
    DoctorCheck,
    DoctorStatus,
)


CommandRunner = Callable[
    [Sequence[str]],
    subprocess.CompletedProcess[str],
]


def check_bird(
    main_config: Path,
    generated_config: Path,
    installed_config: Path,
    runner: CommandRunner | None = None,
) -> tuple[DoctorCheck, ...]:
    """Check BIRD binaries, config files and parse validation."""

    command_runner = runner or _run_command
    checks: list[DoctorCheck] = []

    bird_path = shutil.which("bird")
    birdc_path = shutil.which("birdc")

    checks.append(
        _check_binary(
            name="bird",
            binary_path=bird_path,
        )
    )
    checks.append(
        _check_binary(
            name="birdc",
            binary_path=birdc_path,
        )
    )

    checks.extend(
        (
            _check_config_file(
                name="Main configuration",
                path=main_config,
                missing_status=DoctorStatus.ERROR,
            ),
            _check_config_file(
                name="Generated configuration",
                path=generated_config,
                missing_status=DoctorStatus.WARNING,
            ),
            _check_config_file(
                name="Installed configuration",
                path=installed_config,
                missing_status=DoctorStatus.ERROR,
            ),
        )
    )

    if bird_path is None:
        checks.append(
            DoctorCheck(
                category="BIRD",
                name="Configuration parse",
                status=DoctorStatus.ERROR,
                message="bird is unavailable",
            )
        )
        return tuple(checks)

    if not main_config.is_file():
        checks.append(
            DoctorCheck(
                category="BIRD",
                name="Configuration parse",
                status=DoctorStatus.ERROR,
                message=f"main config unavailable: {main_config}",
            )
        )
        return tuple(checks)

    try:
        result = command_runner(
            (
                bird_path,
                "-p",
                "-c",
                str(main_config),
            )
        )
    except OSError as exc:
        checks.append(
            DoctorCheck(
                category="BIRD",
                name="Configuration parse",
                status=DoctorStatus.ERROR,
                message=str(exc),
            )
        )
        return tuple(checks)

    output = _command_output(result)

    if result.returncode == 0:
        checks.append(
            DoctorCheck(
                category="BIRD",
                name="Configuration parse",
                status=DoctorStatus.OK,
                message=output or "configuration accepted",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                category="BIRD",
                name="Configuration parse",
                status=DoctorStatus.ERROR,
                message=output or (
                    f"bird exited with code {result.returncode}"
                ),
            )
        )

    return tuple(checks)


def _check_binary(
    *,
    name: str,
    binary_path: str | None,
) -> DoctorCheck:
    """Check one executable available through PATH."""

    if binary_path is None:
        return DoctorCheck(
            category="BIRD",
            name=name,
            status=DoctorStatus.ERROR,
            message="not found in PATH",
        )

    return DoctorCheck(
        category="BIRD",
        name=name,
        status=DoctorStatus.OK,
        message=binary_path,
    )


def _check_config_file(
    *,
    name: str,
    path: Path,
    missing_status: DoctorStatus,
) -> DoctorCheck:
    """Check one BIRD configuration file."""

    if not path.exists():
        return DoctorCheck(
            category="BIRD",
            name=name,
            status=missing_status,
            message=f"missing: {path}",
        )

    if not path.is_file():
        return DoctorCheck(
            category="BIRD",
            name=name,
            status=DoctorStatus.ERROR,
            message=f"not a file: {path}",
        )

    return DoctorCheck(
        category="BIRD",
        name=name,
        status=DoctorStatus.OK,
        message=str(path),
    )


def _run_command(
    command: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    """Run one read-only BIRD configuration parse."""

    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def _command_output(
    result: subprocess.CompletedProcess[str],
) -> str:
    """Return compact stdout/stderr text."""

    output = result.stdout.strip() or result.stderr.strip()
    return " ".join(output.split())
