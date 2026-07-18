"""Tests for the routecollector doctor CLI command."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import routecollector.cli as cli_module
from routecollector.doctor.models import (
    DoctorCheck,
    DoctorResult,
    DoctorStatus,
)


def test_parser_accepts_doctor_command() -> None:
    args = cli_module.build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_command_doctor_prints_healthy_report(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    result = DoctorResult.from_checks(
        [
            DoctorCheck(
                "Environment",
                "Python",
                DoctorStatus.OK,
                "3.13.5",
            ),
            DoctorCheck(
                "BIRD",
                "Configuration parse",
                DoctorStatus.OK,
                "configuration accepted",
            ),
        ]
    )

    monkeypatch.setattr(
        cli_module,
        "build_doctor_runner",
        lambda config_path: SimpleNamespace(
            run=lambda: result
        ),
    )

    exit_code = cli_module.command_doctor(
        Path("config/config.yaml")
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "RouteCollector doctor" in output
    assert "Environment" in output
    assert "Python" in output
    assert "3.13.5" in output
    assert "BIRD" in output
    assert "Configuration parse" in output
    assert "Checks                 : 2" in output
    assert "OK                     : 2" in output
    assert "Warnings               : 0" in output
    assert "Errors                 : 0" in output
    assert "Overall                : HEALTHY" in output


def test_command_doctor_returns_warning_exit_code(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    result = DoctorResult.from_checks(
        [
            DoctorCheck(
                "Service",
                "Active",
                DoctorStatus.WARNING,
                "inactive",
            ),
        ]
    )

    monkeypatch.setattr(
        cli_module,
        "build_doctor_runner",
        lambda config_path: SimpleNamespace(
            run=lambda: result
        ),
    )

    exit_code = cli_module.command_doctor(
        Path("config/config.yaml")
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Overall                : WARNING" in output


def test_command_doctor_returns_error_exit_code(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    result = DoctorResult.from_checks(
        [
            DoctorCheck(
                "Database",
                "SQLite",
                DoctorStatus.ERROR,
                "database is missing",
            ),
        ]
    )

    monkeypatch.setattr(
        cli_module,
        "build_doctor_runner",
        lambda config_path: SimpleNamespace(
            run=lambda: result
        ),
    )

    exit_code = cli_module.command_doctor(
        Path("config/config.yaml")
    )
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "Overall                : FAILED" in output
