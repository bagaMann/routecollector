"""
Repository layer for RouteCollector.
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


@dataclass(slots=True, frozen=True)
class Domain:
    """Domain model."""

    id: int
    service_id: int
    domain: str
    source: str
    active: bool


class Repository:
    """Application repository."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def upsert_service(
        self,
        name: str,
        description: str | None = None,
        enabled: bool = True,
    ) -> int:
        """Create or update service and return service ID."""

        with self._database.connection() as conn:
            conn.execute(
                """
                INSERT INTO services (name, enabled, description)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    enabled = excluded.enabled,
                    description = excluded.description
                """,
                (name, int(enabled), description),
            )

            row = conn.execute(
                "SELECT id FROM services WHERE name = ?",
                (name,),
            ).fetchone()

            if row is None:
                raise RuntimeError(f"Unable to obtain service id for '{name}'")

            return int(row["id"])

    def add_service(
        self,
        name: str,
        description: str | None = None,
        enabled: bool = True,
    ) -> int:
        """Backward-compatible alias for upsert_service."""

        return self.upsert_service(name, description, enabled)

    def get_service(self, name: str) -> Service | None:
        """Return service by name."""

        with self._database.connection() as conn:
            row = conn.execute(
                """
                SELECT id, name, enabled, description
                FROM services
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if row is None:
                return None

            return Service(
                id=int(row["id"]),
                name=str(row["name"]),
                enabled=bool(row["enabled"]),
                description=row["description"],
            )

    def list_services(self) -> list[Service]:
        """Return all services."""

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, enabled, description
                FROM services
                ORDER BY name
                """
            ).fetchall()

            return [
                Service(
                    id=int(row["id"]),
                    name=str(row["name"]),
                    enabled=bool(row["enabled"]),
                    description=row["description"],
                )
                for row in rows
            ]

    def upsert_domain(
        self,
        service_id: int,
        domain: str,
        source: str,
        active: bool = True,
    ) -> int:
        """Create or update domain and return domain ID."""

        with self._database.connection() as conn:
            conn.execute(
                """
                INSERT INTO domains (service_id, domain, source, active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(service_id, domain, source) DO UPDATE SET
                    active = excluded.active,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (service_id, domain, source, int(active)),
            )

            row = conn.execute(
                """
                SELECT id
                FROM domains
                WHERE service_id = ? AND domain = ? AND source = ?
                """,
                (service_id, domain, source),
            ).fetchone()

            if row is None:
                raise RuntimeError(f"Unable to obtain domain id for '{domain}'")

            return int(row["id"])

    def list_domains(self, service_name: str | None = None) -> list[Domain]:
        """Return domains, optionally filtered by service name."""

        with self._database.connection() as conn:
            if service_name is None:
                rows = conn.execute(
                    """
                    SELECT id, service_id, domain, source, active
                    FROM domains
                    ORDER BY domain
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT d.id, d.service_id, d.domain, d.source, d.active
                    FROM domains d
                    JOIN services s ON s.id = d.service_id
                    WHERE s.name = ?
                    ORDER BY d.domain
                    """,
                    (service_name,),
                ).fetchall()

            return [
                Domain(
                    id=int(row["id"]),
                    service_id=int(row["service_id"]),
                    domain=str(row["domain"]),
                    source=str(row["source"]),
                    active=bool(row["active"]),
                )
                for row in rows
            ]
