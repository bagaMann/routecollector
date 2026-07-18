"""Tests for runtime doctor checks."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from routecollector.core.database import Database
from routecollector.doctor.models import DoctorStatus
from routecollector.doctor.runtime_checks import (
    check_cycle_history,
    check_snapshots,
    check_systemd_service,
)


def test_systemd_service_reports_enabled_and_active() -> None:
    def runner(
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        output = "enabled" if "is-enabled" in command else "active"
        return subprocess.CompletedProcess(
            command, 0, output, ""
        )

    checks = check_systemd_service(runner=runner)
    assert all(
        check.status is DoctorStatus.OK
        for check in checks
    )


def test_systemd_service_warns_when_inactive() -> None:
    def runner(
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        output = "disabled" if "is-enabled" in command else "inactive"
        return subprocess.CompletedProcess(
            command, 1, output, ""
        )

    checks = check_systemd_service(runner=runner)
    assert all(
        check.status is DoctorStatus.WARNING
        for check in checks
    )


def test_snapshots_report_count_and_latest(
    tmp_path: Path,
) -> None:
    snapshots = tmp_path / "plans"
    snapshots.mkdir()

    for name, created, routes in (
        ("20260718T100000_1.json", "2026-07-18T10:00:00", 49),
        ("20260718T103000_2.json", "2026-07-18T10:30:00", 50),
    ):
        (snapshots / name).write_text(
            json.dumps(
                {
                    "created_at": created,
                    "route_count": routes,
                    "routes": [],
                }
            ),
            encoding="utf-8",
        )

    checks = check_snapshots(snapshots)
    by_name = {check.name: check for check in checks}

    assert by_name["Stored"].message == "2"
    assert "routes=50" in by_name["Latest"].message


def test_snapshots_warn_when_empty(
    tmp_path: Path,
) -> None:
    snapshots = tmp_path / "plans"
    snapshots.mkdir()

    checks = check_snapshots(snapshots)

    assert checks[1].status is DoctorStatus.WARNING


def test_cycle_history_reports_latest_cycle(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "state.db"
    database = Database(database_path)
    database.initialize()

    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO cycle_history (
                started_at,
                completed_at,
                duration_seconds,
                services_synced,
                domains_synced,
                domains_resolved,
                observations_stored,
                route_stats_built,
                planned_routes,
                routes_added,
                routes_removed,
                bird_reloaded
            )
            VALUES (
                '2026-07-18T10:00:00',
                '2026-07-18T10:00:14',
                14.5,
                3,
                232,
                232,
                1758,
                123,
                50,
                2,
                1,
                1
            )
            """
        )

    checks = check_cycle_history(database_path)
    by_name = {check.name: check for check in checks}

    assert by_name["Stored cycles"].message == "1"
    assert "routes=50" in by_name["Latest cycle"].message
    assert "bird_reloaded=yes" in by_name["Latest cycle"].message


def test_cycle_history_warns_when_empty(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "state.db"
    Database(database_path).initialize()

    checks = check_cycle_history(database_path)

    assert checks[1].status is DoctorStatus.WARNING


def test_cycle_history_reports_missing_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "state.db"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE services (id INTEGER PRIMARY KEY)"
        )

    checks = check_cycle_history(database_path)

    assert checks[0].status is DoctorStatus.ERROR
