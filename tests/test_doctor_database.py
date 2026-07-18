"""
Tests for read-only SQLite doctor checks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from routecollector.core.database import Database
from routecollector.doctor.database_checks import (
    REQUIRED_DATABASE_TABLES,
    _count_rows,
    check_database,
)
from routecollector.doctor.models import DoctorStatus


def test_check_database_reports_missing_file(
    tmp_path: Path,
) -> None:
    """Missing database must be an error and must not be created."""

    database_path = tmp_path / "missing.db"

    checks = check_database(database_path)

    assert len(checks) == 1
    assert checks[0].name == "SQLite"
    assert checks[0].status is DoctorStatus.ERROR
    assert "missing:" in checks[0].message
    assert database_path.exists() is False


def test_check_database_reports_schema_and_counts(
    tmp_path: Path,
) -> None:
    """Initialized database must expose required tables and counts."""

    database_path = tmp_path / "state.db"
    database = Database(database_path)
    database.initialize()

    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO services (
                name,
                enabled
            )
            VALUES ('youtube', 1)
            """
        )
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
                planned_routes
            )
            VALUES (
                '2026-07-18T10:00:00',
                '2026-07-18T10:00:10',
                10.0,
                1,
                0,
                0,
                0,
                0,
                0
            )
            """
        )

    checks = check_database(database_path)
    by_name = {
        check.name: check
        for check in checks
    }

    assert by_name["SQLite"].status is DoctorStatus.OK
    assert by_name["Schema"].status is DoctorStatus.OK
    assert by_name["Schema"].message == "5 required tables"
    assert by_name["services"].message == "1"
    assert by_name["domains"].message == "0"
    assert by_name["observations"].message == "0"
    assert by_name["route_stats"].message == "0"
    assert by_name["cycle_history"].message == "1"


def test_check_database_reports_missing_tables(
    tmp_path: Path,
) -> None:
    """Incomplete schema must produce an explicit error."""

    database_path = tmp_path / "incomplete.db"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE services (id INTEGER PRIMARY KEY)"
        )

    checks = check_database(database_path)

    assert checks[0].status is DoctorStatus.OK
    assert checks[1].name == "Schema"
    assert checks[1].status is DoctorStatus.ERROR
    assert "domains" in checks[1].message
    assert "cycle_history" in checks[1].message


def test_check_database_reports_invalid_sqlite_file(
    tmp_path: Path,
) -> None:
    """Non-SQLite content must produce an SQLite error."""

    database_path = tmp_path / "invalid.db"
    database_path.write_text(
        "this is not sqlite",
        encoding="utf-8",
    )

    checks = check_database(database_path)

    assert len(checks) == 1
    assert checks[0].name == "SQLite"
    assert checks[0].status is DoctorStatus.ERROR


def test_count_rows_rejects_untrusted_table(
    tmp_path: Path,
) -> None:
    """Count helper must reject arbitrary SQL identifiers."""

    database_path = tmp_path / "state.db"
    Database(database_path).initialize()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row

        try:
            _count_rows(
                connection,
                "services; DROP TABLE services",
            )
        except ValueError as exc:
            assert "Unsupported doctor table" in str(exc)
        else:
            raise AssertionError(
                "Untrusted table name was accepted"
            )


def test_required_database_tables_match_current_schema() -> None:
    """Doctor must use the current RouteCollector table names."""

    assert REQUIRED_DATABASE_TABLES == (
        "services",
        "domains",
        "observations",
        "route_stats",
        "cycle_history",
    )
