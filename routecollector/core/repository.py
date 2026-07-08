"""
Repository layer for RouteCollector.

This module contains all SQL queries used by the application.
"""

from __future__ import annotations

from dataclasses import dataclass

from routecollector.core.database import Database


@dataclass(slots=True, frozen=True)
class Service:
    """Service model."""

    id: int
    name: str
    enabled: bool
    description: str | None


class Repository:
    """Application repository."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add_service(
        self,
        name: str,
        description: str | None = None,
        enabled: bool = True,
    ) -> int:
        """
        Create service if it does not exist.

        Returns:
            int: Service ID.
        """

        with self._database.connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO services
                    (name, enabled, description)
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    int(enabled),
                    description,
                ),
            )

            if cursor.lastrowid:
                return int(cursor.lastrowid)

            cursor = conn.execute(
                """
                SELECT id
                FROM services
                WHERE name = ?
                """,
                (name,),
            )

            row = cursor.fetchone()

            if row is None:
                raise RuntimeError(
                    f"Unable to obtain service id for '{name}'"
                )

            return int(row["id"])

    def get_service(self, name: str) -> Service | None:
        """Return service by name."""

        with self._database.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    id,
                    name,
                    enabled,
                    description
                FROM services
                WHERE name = ?
                """,
                (name,),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return Service(
                id=row["id"],
                name=row["name"],
                enabled=bool(row["enabled"]),
                description=row["description"],
            )

    def list_services(self) -> list[Service]:
        """Return all services."""

        with self._database.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    id,
                    name,
                    enabled,
                    description
                FROM services
                ORDER BY name
                """
            )

            return [
                Service(
                    id=row["id"],
                    name=row["name"],
                    enabled=bool(row["enabled"]),
                    description=row["description"],
                )
                for row in cursor.fetchall()
            ]
