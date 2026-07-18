"""
Tests for environment and filesystem doctor checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import routecollector.doctor.checks as checks_module
from routecollector.doctor.checks import (
    check_directories,
    check_environment,
)
from routecollector.doctor.models import DoctorStatus


def test_check_environment_reports_python_version_and_config(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Environment check must report stable runtime facts."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "project:\n  name: RouteCollector\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        checks_module.platform,
        "python_version",
        lambda: "3.13.5",
    )
    monkeypatch.setattr(
        checks_module,
        "__version__",
        "1.2.0",
    )

    checks = check_environment(config_path)

    assert [
        (
            check.category,
            check.name,
            check.status,
            check.message,
        )
        for check in checks
    ] == [
        (
            "Environment",
            "Python",
            DoctorStatus.OK,
            "3.13.5",
        ),
        (
            "Environment",
            "RouteCollector",
            DoctorStatus.OK,
            "1.2.0",
        ),
        (
            "Environment",
            "Configuration",
            DoctorStatus.OK,
            str(config_path),
        ),
    ]


def test_check_environment_reports_missing_config(
    tmp_path: Path,
) -> None:
    """Missing configuration must be an error."""

    checks = check_environment(
        tmp_path / "missing.yaml"
    )

    config_check = checks[-1]

    assert config_check.status is DoctorStatus.ERROR
    assert "missing:" in config_check.message


def test_check_directories_reports_healthy_directory(
    tmp_path: Path,
) -> None:
    """Existing writable directory must be healthy."""

    directory = tmp_path / "state"
    directory.mkdir()

    result = check_directories((directory,))

    assert result[0].status is DoctorStatus.OK
    assert result[0].message == "readable and writable"


def test_check_directories_reports_missing_directory(
    tmp_path: Path,
) -> None:
    """Missing required directory must be an error."""

    directory = tmp_path / "cache"

    result = check_directories((directory,))

    assert result[0].status is DoctorStatus.ERROR
    assert result[0].message == "missing"


def test_check_directories_reports_regular_file(
    tmp_path: Path,
) -> None:
    """A regular file cannot satisfy a directory check."""

    path = tmp_path / "logs"
    path.write_text("not a directory", encoding="utf-8")

    result = check_directories((path,))

    assert result[0].status is DoctorStatus.ERROR
    assert result[0].message == "not a directory"


def test_check_directories_warns_when_not_writable(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Read-only directory must produce a warning."""

    directory = tmp_path / "bird"
    directory.mkdir()

    def fake_access(
        path: Path,
        mode: int,
    ) -> bool:
        assert path == directory

        if mode == checks_module.os.W_OK:
            return False

        return True

    monkeypatch.setattr(
        checks_module.os,
        "access",
        fake_access,
    )

    result = check_directories((directory,))

    assert result[0].status is DoctorStatus.WARNING
    assert result[0].message == "readable but not writable"


def test_check_directories_reports_unsearchable_directory(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Directory without execute/search permission must fail."""

    directory = tmp_path / "config"
    directory.mkdir()

    def fake_access(
        path: Path,
        mode: int,
    ) -> bool:
        assert path == directory

        if mode == checks_module.os.X_OK:
            return False

        return True

    monkeypatch.setattr(
        checks_module.os,
        "access",
        fake_access,
    )

    result = check_directories((directory,))

    assert result[0].status is DoctorStatus.ERROR
    assert result[0].message == "not searchable"
