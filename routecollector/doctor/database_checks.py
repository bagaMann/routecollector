"""
Read-only SQLite checks for RouteCollector doctor.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from routecollector.doctor.models import (
    DoctorCheck,
    DoctorStatus,
)


REQUIRED_DATABASE_TABLES = (
    "services",
    "domains",
    "observations",
    "route_stats",
    "cycle_history",
)


def check_database(
    database_path: Path,
) -> tuple[DoctorCheck, ...]:
    """Check SQLite availability, schema and table row counts."""

    if not database_path.exists():
        return (
            DoctorCheck(
                category="Database",
                name="SQLite",
                status=DoctorStatus.ERROR,
                message=f"missing: {database_path}",
            ),
        )

    if not database_path.is_file():
        return (
            DoctorCheck(
                category="Database",
                name="SQLite",
                status=DoctorStatus.ERROR,
                message=f"not a file: {database_path}",
            ),
        )

    try:
        with _read_only_connection(database_path) as connection:
            connection.execute("PRAGMA quick_check").fetchone()
            tables = _list_tables(connection)

            checks: list[DoctorCheck] = [
                DoctorCheck(
                    category="Database",
                    name="SQLite",
                    status=DoctorStatus.OK,
                    message=str(database_path),
                )
            ]

            missing_tables = tuple(
                table
                for table in REQUIRED_DATABASE_TABLES
                if table not in tables
            )

            if missing_tables:
                checks.append(
                    DoctorCheck(
                        category="Database",
                        name="Schema",
                        status=DoctorStatus.ERROR,
                        message=(
                            "missing tables: "
                            + ", ".join(missing_tables)
                        ),
                    )
                )
                return tuple(checks)

            checks.append(
                DoctorCheck(
                    category="Database",
                    name="Schema",
                    status=DoctorStatus.OK,
                    message=(
                        f"{len(REQUIRED_DATABASE_TABLES)} "
                        "required tables"
                    ),
                )
            )

            for table in REQUIRED_DATABASE_TABLES:
                checks.append(
                    DoctorCheck(
                        category="Database",
                        name=table,
                        status=DoctorStatus.OK,
                        message=str(
                            _count_rows(
                                connection,
                                table,
                            )
                        ),
                    )
                )

            return tuple(checks)

    except sqlite3.Error as exc:
        return (
            DoctorCheck(
                category="Database",
                name="SQLite",
                status=DoctorStatus.ERROR,
                message=str(exc),
            ),
        )


def _read_only_connection(
    database_path: Path,
) -> sqlite3.Connection:
    """Open an existing SQLite database without write access."""

    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(
        uri,
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _list_tables(
    connection: sqlite3.Connection,
) -> frozenset[str]:
    """Return all user table names."""

    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()

    return frozenset(
        str(row["name"])
        for row in rows
    )


def _count_rows(
    connection: sqlite3.Connection,
    table: str,
) -> int:
    """Count rows in a trusted required table."""

    if table not in REQUIRED_DATABASE_TABLES:
        raise ValueError(
            f"Unsupported doctor table: {table}"
        )

    row = connection.execute(
        f'SELECT COUNT(*) AS count FROM "{table}"'
    ).fetchone()

    if row is None:
        return 0

    return int(row["count"])
