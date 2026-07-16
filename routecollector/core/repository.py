"""
Repository layer for RouteCollector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from routecollector.core.database import Database
from routecollector.policy.statistics import RouteStatisticsBuilder


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


@dataclass(slots=True, frozen=True)
class ObservationInput:
    """Pending DNS observation for batch persistence."""

    domain_id: int | None
    ip: str
    source: str
    dns_server: str | None
    ttl: int | None
    confidence: int = 1


@dataclass(slots=True, frozen=True)
class Observation:
    """DNS observation model."""

    id: int
    domain_id: int | None
    domain_source: str | None
    ip: str
    source: str
    dns_server: str | None
    hits: int
    ttl: int | None
    confidence: int
    first_seen: str
    last_seen: str


@dataclass(slots=True, frozen=True)
class RouteStat:
    """Route statistics model."""

    prefix: str
    family: int
    source_ips: int
    unique_domains: int
    unique_resolvers: int
    source_count: int
    source_trust: int
    total_hits: int
    confidence: int
    first_seen: str | None
    last_seen: str | None


class Repository:
    """Application repository."""

    CONFIDENCE_INTERVAL_SECONDS = 3600

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
                raise RuntimeError(
                    f"Unable to obtain service id for '{name}'"
                )

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
                raise RuntimeError(
                    f"Unable to obtain domain id for '{domain}'"
                )

            return int(row["id"])

    def deactivate_service_domains(
        self,
        service_id: int,
    ) -> int:
        """Deactivate every active domain row for one service."""

        with self._database.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE domains
                SET
                    active = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE service_id = ?
                  AND active = 1
                """,
                (service_id,),
            )

            return int(cursor.rowcount)

    def list_domains(
        self,
        service_name: str | None = None,
    ) -> list[Domain]:
        """Return active domains, optionally filtered by service name."""

        with self._database.connection() as conn:
            if service_name is None:
                rows = conn.execute(
                    """
                    SELECT id, service_id, domain, source, active
                    FROM domains
                    WHERE active = 1
                    ORDER BY domain
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT d.id, d.service_id, d.domain, d.source, d.active
                    FROM domains d
                    JOIN services s ON s.id = d.service_id
                    WHERE s.name = ? AND d.active = 1
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

    def add_observation(
        self,
        domain_id: int | None,
        ip: str,
        source: str,
        dns_server: str | None,
        ttl: int | None,
        confidence: int = 1,
    ) -> int:
        """Insert or update one DNS observation."""

        observation = ObservationInput(
            domain_id=domain_id,
            ip=ip,
            source=source,
            dns_server=dns_server,
            ttl=ttl,
            confidence=confidence,
        )

        with self._database.connection() as conn:
            return self._upsert_observation(conn, observation)

    def add_observations(
        self,
        observations: list[ObservationInput],
    ) -> int:
        """Insert or update observations in one SQLite transaction."""

        if not observations:
            return 0

        with self._database.connection() as conn:
            for observation in observations:
                self._upsert_observation(conn, observation)

        return len(observations)

    def _upsert_observation(
        self,
        conn: object,
        observation: ObservationInput,
    ) -> int:
        """Insert or update one observation using an existing connection."""

        existing = conn.execute(  # type: ignore[attr-defined]
            """
            SELECT id, last_seen
            FROM observations
            WHERE domain_id IS ?
              AND ip = ?
              AND source = ?
              AND dns_server IS ?
            """,
            (
                observation.domain_id,
                observation.ip,
                observation.source,
                observation.dns_server,
            ),
        ).fetchone()

        if existing is None:
            cursor = conn.execute(  # type: ignore[attr-defined]
                """
                INSERT INTO observations
                    (
                        domain_id,
                        ip,
                        source,
                        dns_server,
                        ttl,
                        confidence
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.domain_id,
                    observation.ip,
                    observation.source,
                    observation.dns_server,
                    observation.ttl,
                    observation.confidence,
                ),
            )
            return int(cursor.lastrowid)

        last_seen = datetime.fromisoformat(str(existing["last_seen"]))
        elapsed_seconds = (
            datetime.now() - last_seen
        ).total_seconds()

        confidence_increment = (
            observation.confidence
            if elapsed_seconds >= self.CONFIDENCE_INTERVAL_SECONDS
            else 0
        )

        conn.execute(  # type: ignore[attr-defined]
            """
            UPDATE observations
            SET
                last_seen = CURRENT_TIMESTAMP,
                hits = hits + 1,
                ttl = ?,
                confidence = confidence + ?
            WHERE id = ?
            """,
            (
                observation.ttl,
                confidence_increment,
                int(existing["id"]),
            ),
        )

        return int(existing["id"])

    def list_observations(self) -> list[Observation]:
        """Return all observations with domain source provenance."""

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    o.id,
                    o.domain_id,
                    d.source AS domain_source,
                    o.ip,
                    o.source,
                    o.dns_server,
                    o.hits,
                    o.ttl,
                    o.confidence,
                    o.first_seen,
                    o.last_seen
                FROM observations o
                LEFT JOIN domains d ON d.id = o.domain_id
                ORDER BY o.last_seen DESC
                """
            ).fetchall()

            return [
                Observation(
                    id=int(row["id"]),
                    domain_id=row["domain_id"],
                    domain_source=row["domain_source"],
                    ip=str(row["ip"]),
                    source=str(row["source"]),
                    dns_server=row["dns_server"],
                    hits=int(row["hits"]),
                    ttl=row["ttl"],
                    confidence=int(row["confidence"]),
                    first_seen=str(row["first_seen"]),
                    last_seen=str(row["last_seen"]),
                )
                for row in rows
            ]

    def rebuild_route_stats(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> int:
        """Rebuild normalized route statistics from observations."""

        calculated_stats = RouteStatisticsBuilder(
            ipv4_prefix=ipv4_prefix,
            ipv6_prefix=ipv6_prefix,
        ).build(self.list_observations())

        with self._database.connection() as conn:
            conn.execute("DELETE FROM route_stats")

            conn.executemany(
                """
                INSERT INTO route_stats
                    (
                        prefix,
                        family,
                        source_ips,
                        unique_domains,
                        unique_resolvers,
                        source_count,
                        source_trust,
                        total_hits,
                        confidence,
                        first_seen,
                        last_seen
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        stat.prefix,
                        stat.family,
                        stat.source_ips,
                        stat.unique_domains,
                        stat.unique_resolvers,
                        stat.source_count,
                        stat.source_trust,
                        stat.total_hits,
                        stat.confidence,
                        stat.first_seen,
                        stat.last_seen,
                    )
                    for stat in calculated_stats
                ],
            )

        return len(calculated_stats)

    def list_route_stats(self) -> list[RouteStat]:
        """Return route statistics."""

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    prefix,
                    family,
                    source_ips,
                    unique_domains,
                    unique_resolvers,
                    source_count,
                    source_trust,
                    total_hits,
                    confidence,
                    first_seen,
                    last_seen
                FROM route_stats
                ORDER BY family, prefix
                """
            ).fetchall()

            return [
                RouteStat(
                    prefix=str(row["prefix"]),
                    family=int(row["family"]),
                    source_ips=int(row["source_ips"]),
                    unique_domains=int(row["unique_domains"]),
                    unique_resolvers=int(row["unique_resolvers"]),
                    source_count=int(row["source_count"]),
                    source_trust=int(row["source_trust"]),
                    total_hits=int(row["total_hits"]),
                    confidence=int(row["confidence"]),
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                )
                for row in rows
            ]
