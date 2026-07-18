"""Runtime service, snapshot and history checks."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from routecollector.doctor.models import DoctorCheck, DoctorStatus

CommandRunner = Callable[
    [Sequence[str]],
    subprocess.CompletedProcess[str],
]


def check_systemd_service(
    service_name: str = "routecollector.service",
    runner: CommandRunner | None = None,
) -> tuple[DoctorCheck, ...]:
    """Check whether the service is enabled and active."""

    command_runner = runner or _run_command

    try:
        enabled = command_runner(
            ("systemctl", "is-enabled", service_name)
        )
        active = command_runner(
            ("systemctl", "is-active", service_name)
        )
    except OSError as exc:
        return (
            DoctorCheck(
                "Service",
                "systemd",
                DoctorStatus.WARNING,
                str(exc),
            ),
        )

    return (
        DoctorCheck(
            "Service",
            "Enabled",
            (
                DoctorStatus.OK
                if enabled.returncode == 0
                else DoctorStatus.WARNING
            ),
            _command_output(enabled) or "unknown",
        ),
        DoctorCheck(
            "Service",
            "Active",
            (
                DoctorStatus.OK
                if active.returncode == 0
                else DoctorStatus.WARNING
            ),
            _command_output(active) or "unknown",
        ),
    )


def check_snapshots(
    snapshots_dir: Path,
) -> tuple[DoctorCheck, ...]:
    """Check stored plan snapshots and latest metadata."""

    if not snapshots_dir.exists():
        return (
            DoctorCheck(
                "Snapshots",
                "Directory",
                DoctorStatus.WARNING,
                f"missing: {snapshots_dir}",
            ),
        )

    if not snapshots_dir.is_dir():
        return (
            DoctorCheck(
                "Snapshots",
                "Directory",
                DoctorStatus.ERROR,
                f"not a directory: {snapshots_dir}",
            ),
        )

    files = sorted(snapshots_dir.glob("*.json"))
    checks = [
        DoctorCheck(
            "Snapshots",
            "Stored",
            DoctorStatus.OK,
            str(len(files)),
        )
    ]

    if not files:
        checks.append(
            DoctorCheck(
                "Snapshots",
                "Latest",
                DoctorStatus.WARNING,
                "no snapshots stored",
            )
        )
        return tuple(checks)

    latest = files[-1]

    try:
        payload = json.loads(
            latest.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(
            DoctorCheck(
                "Snapshots",
                "Latest",
                DoctorStatus.ERROR,
                f"{latest.name}: {exc}",
            )
        )
        return tuple(checks)

    created_at = payload.get("created_at")
    route_count = payload.get("route_count")

    if not isinstance(created_at, str):
        checks.append(
            DoctorCheck(
                "Snapshots",
                "Latest",
                DoctorStatus.ERROR,
                f"{latest.name}: missing created_at",
            )
        )
        return tuple(checks)

    checks.append(
        DoctorCheck(
            "Snapshots",
            "Latest",
            DoctorStatus.OK,
            (
                f"{created_at}, routes={route_count}, "
                f"file={latest.name}"
            ),
        )
    )
    return tuple(checks)


def check_cycle_history(
    database_path: Path,
) -> tuple[DoctorCheck, ...]:
    """Check stored successful cycles in read-only SQLite mode."""

    if not database_path.is_file():
        return (
            DoctorCheck(
                "History",
                "Database",
                DoctorStatus.ERROR,
                f"missing: {database_path}",
            ),
        )

    try:
        with _read_only_connection(database_path) as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM cycle_history"
                ).fetchone()[0]
            )

            checks = [
                DoctorCheck(
                    "History",
                    "Stored cycles",
                    DoctorStatus.OK,
                    str(count),
                )
            ]

            if count == 0:
                checks.append(
                    DoctorCheck(
                        "History",
                        "Latest cycle",
                        DoctorStatus.WARNING,
                        "no successful cycles stored",
                    )
                )
                return tuple(checks)

            row = connection.execute(
                """
                SELECT
                    completed_at,
                    duration_seconds,
                    planned_routes,
                    routes_added,
                    routes_removed,
                    bird_reloaded
                FROM cycle_history
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            checks.append(
                DoctorCheck(
                    "History",
                    "Latest cycle",
                    DoctorStatus.OK,
                    (
                        f"{row['completed_at']}, "
                        f"duration={float(row['duration_seconds']):.1f}s, "
                        f"routes={int(row['planned_routes'])}, "
                        f"added={int(row['routes_added'])}, "
                        f"removed={int(row['routes_removed'])}, "
                        f"bird_reloaded="
                        f"{'yes' if bool(row['bird_reloaded']) else 'no'}"
                    ),
                )
            )
            return tuple(checks)

    except sqlite3.Error as exc:
        return (
            DoctorCheck(
                "History",
                "Database",
                DoctorStatus.ERROR,
                str(exc),
            ),
        )


def _read_only_connection(
    database_path: Path,
) -> sqlite3.Connection:
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _run_command(
    command: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def _command_output(
    result: subprocess.CompletedProcess[str],
) -> str:
    output = result.stdout.strip() or result.stderr.strip()
    return " ".join(output.split())
