"""
Tests for read-only BIRD doctor checks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import routecollector.doctor.bird_checks as bird_checks_module
from routecollector.doctor.bird_checks import check_bird
from routecollector.doctor.models import DoctorStatus


def write_configs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create three valid BIRD config files."""

    main = tmp_path / "bird.conf"
    generated = tmp_path / "generated.conf"
    installed = tmp_path / "installed.conf"

    for path in (main, generated, installed):
        path.write_text("# config\n", encoding="utf-8")

    return main, generated, installed


def test_check_bird_reports_healthy_state(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """All BIRD checks must pass for a healthy installation."""

    main, generated, installed = write_configs(tmp_path)

    monkeypatch.setattr(
        bird_checks_module.shutil,
        "which",
        lambda name: f"/usr/sbin/{name}",
    )

    commands: list[tuple[str, ...]] = []

    def runner(
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    checks = check_bird(
        main,
        generated,
        installed,
        runner=runner,
    )
    by_name = {check.name: check for check in checks}

    assert by_name["bird"].status is DoctorStatus.OK
    assert by_name["birdc"].status is DoctorStatus.OK
    assert by_name["Main configuration"].status is DoctorStatus.OK
    assert by_name["Generated configuration"].status is DoctorStatus.OK
    assert by_name["Installed configuration"].status is DoctorStatus.OK
    assert by_name["Configuration parse"].status is DoctorStatus.OK
    assert by_name["Configuration parse"].message == (
        "configuration accepted"
    )
    assert commands == [
        (
            "/usr/sbin/bird",
            "-p",
            "-c",
            str(main),
        )
    ]


def test_check_bird_reports_missing_binaries(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Missing BIRD executables must be errors."""

    main, generated, installed = write_configs(tmp_path)

    monkeypatch.setattr(
        bird_checks_module.shutil,
        "which",
        lambda _: None,
    )

    checks = check_bird(
        main,
        generated,
        installed,
    )
    by_name = {check.name: check for check in checks}

    assert by_name["bird"].status is DoctorStatus.ERROR
    assert by_name["birdc"].status is DoctorStatus.ERROR
    assert by_name["Configuration parse"].status is DoctorStatus.ERROR
    assert "bird is unavailable" in by_name["Configuration parse"].message


def test_check_bird_warns_for_missing_generated_config(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Missing local generated config is a warning."""

    main = tmp_path / "bird.conf"
    installed = tmp_path / "installed.conf"
    generated = tmp_path / "missing.conf"

    main.write_text("# config\n", encoding="utf-8")
    installed.write_text("# config\n", encoding="utf-8")

    monkeypatch.setattr(
        bird_checks_module.shutil,
        "which",
        lambda name: f"/usr/sbin/{name}",
    )

    checks = check_bird(
        main,
        generated,
        installed,
        runner=lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        ),
    )
    by_name = {check.name: check for check in checks}

    assert (
        by_name["Generated configuration"].status
        is DoctorStatus.WARNING
    )
    assert by_name["Configuration parse"].status is DoctorStatus.OK


def test_check_bird_reports_rejected_configuration(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Rejected configuration parse must be an error."""

    main, generated, installed = write_configs(tmp_path)

    monkeypatch.setattr(
        bird_checks_module.shutil,
        "which",
        lambda name: f"/usr/sbin/{name}",
    )

    checks = check_bird(
        main,
        generated,
        installed,
        runner=lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr="syntax error",
        ),
    )
    by_name = {check.name: check for check in checks}

    assert by_name["Configuration parse"].status is DoctorStatus.ERROR
    assert by_name["Configuration parse"].message == "syntax error"


def test_check_bird_skips_command_when_main_config_missing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Missing main config must prevent bird invocation."""

    main = tmp_path / "missing.conf"
    generated = tmp_path / "generated.conf"
    installed = tmp_path / "installed.conf"
    generated.write_text("# config\n", encoding="utf-8")
    installed.write_text("# config\n", encoding="utf-8")

    monkeypatch.setattr(
        bird_checks_module.shutil,
        "which",
        lambda name: f"/usr/sbin/{name}",
    )

    called = False

    def runner(
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        raise AssertionError("runner must not be called")

    checks = check_bird(
        main,
        generated,
        installed,
        runner=runner,
    )
    by_name = {check.name: check for check in checks}

    assert called is False
    assert by_name["Main configuration"].status is DoctorStatus.ERROR
    assert by_name["Configuration parse"].status is DoctorStatus.ERROR
