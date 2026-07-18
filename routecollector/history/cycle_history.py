"""
Persistent history of successful RouteCollector cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from routecollector.core.database import Database


@dataclass(slots=True, frozen=True)
class CycleHistoryEntry:
    """One successfully completed RouteCollector cycle."""

    id: int
    started_at: str
    completed_at: str
    duration_seconds: float
    service_name: str | None
    services_synced: int
    domains_synced: int
    domains_resolved: int
    observations_stored: int
    route_stats_built: int
    planned_routes: int
    routes_added: int
    routes_removed: int
    generated_changed: bool
    installed_changed: bool
    bird_reloaded: bool


@dataclass(slots=True, frozen=True)
class NewCycleHistoryEntry:
    """Cycle information waiting to be persisted."""

    started_at: datetime
    completed_at: datetime
    service_name: str | None
    services_synced: int
    domains_synced: int
    domains_resolved: int
    observations_stored: int
    route_stats_built: int
    planned_routes: int
    routes_added: int
    routes_removed: int
    generated_changed: bool
    installed_changed: bool
    bird_reloaded: bool

    @property
    def duration_seconds(self) -> float:
        """Return cycle duration in seconds."""

        return max(
            0.0,
            (
                self.completed_at
                - self.started_at
            ).total_seconds(),
        )


class CycleHistoryStore:
    """Read and write successful cycle history."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(
        self,
        entry: NewCycleHistoryEntry,
    ) -> int:
        """Persist one cycle and return its database ID."""

        with self._database.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO cycle_history
                    (
                        started_at,
                        completed_at,
                        duration_seconds,
                        service_name,
                        services_synced,
                        domains_synced,
                        domains_resolved,
                        observations_stored,
                        route_stats_built,
                        planned_routes,
                        routes_added,
                        routes_removed,
                        generated_changed,
                        installed_changed,
                        bird_reloaded
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.started_at.isoformat(
                        timespec="seconds"
                    ),
                    entry.completed_at.isoformat(
                        timespec="seconds"
                    ),
                    entry.duration_seconds,
                    entry.service_name,
                    entry.services_synced,
                    entry.domains_synced,
                    entry.domains_resolved,
                    entry.observations_stored,
                    entry.route_stats_built,
                    entry.planned_routes,
                    entry.routes_added,
                    entry.routes_removed,
                    int(entry.generated_changed),
                    int(entry.installed_changed),
                    int(entry.bird_reloaded),
                ),
            )

            return int(cursor.lastrowid)

    def list_recent(
        self,
        limit: int = 20,
    ) -> list[CycleHistoryEntry]:
        """Return newest successful cycles first."""

        if limit <= 0:
            raise ValueError(
                "History limit must be greater than zero"
            )

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    started_at,
                    completed_at,
                    duration_seconds,
                    service_name,
                    services_synced,
                    domains_synced,
                    domains_resolved,
                    observations_stored,
                    route_stats_built,
                    planned_routes,
                    routes_added,
                    routes_removed,
                    generated_changed,
                    installed_changed,
                    bird_reloaded
                FROM cycle_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            CycleHistoryEntry(
                id=int(row["id"]),
                started_at=str(row["started_at"]),
                completed_at=str(row["completed_at"]),
                duration_seconds=float(
                    row["duration_seconds"]
                ),
                service_name=row["service_name"],
                services_synced=int(
                    row["services_synced"]
                ),
                domains_synced=int(
                    row["domains_synced"]
                ),
                domains_resolved=int(
                    row["domains_resolved"]
                ),
                observations_stored=int(
                    row["observations_stored"]
                ),
                route_stats_built=int(
                    row["route_stats_built"]
                ),
                planned_routes=int(
                    row["planned_routes"]
                ),
                routes_added=int(row["routes_added"]),
                routes_removed=int(
                    row["routes_removed"]
                ),
                generated_changed=bool(
                    row["generated_changed"]
                ),
                installed_changed=bool(
                    row["installed_changed"]
                ),
                bird_reloaded=bool(
                    row["bird_reloaded"]
                ),
            )
            for row in rows
        ]

    def latest(
        self,
    ) -> CycleHistoryEntry | None:
        """Return the most recent successful cycle."""

        entries = self.list_recent(limit=1)

        if not entries:
            return None

        return entries[0]

    def count(self) -> int:
        """Return number of stored successful cycles."""

        with self._database.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM cycle_history"
            ).fetchone()

        return int(row["count"]) if row else 0
