"""
Repository layer for RouteCollector.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress

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


@dataclass(slots=True, frozen=True)
class Observation:
    """DNS observation model."""

    id: int
    domain_id: int | None
    ip: str
    source: str
    dns_server: str | None
    hits: int
    ttl: int | None
    confidence: int


@dataclass(slots=True, frozen=True)
class RouteStat:
    """Route statistics model."""

    prefix: str
    family: int
    source_ips: int
    total_hits: int
    confidence: int
    first_seen: str | None
    last_seen: str | None


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
        """Insert or update DNS observation."""

        with self._database.connection() as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM observations
                WHERE domain_id IS ? AND ip = ? AND source = ? AND dns_server IS ?
                """,
                (domain_id, ip, source, dns_server),
            ).fetchone()

            if existing is not None:
                conn.execute(
                    """
                    UPDATE observations
                    SET
                        last_seen = CURRENT_TIMESTAMP,
                        hits = hits + 1,
                        ttl = ?,
                        confidence = confidence + ?
                    WHERE id = ?
                    """,
                    (ttl, confidence, int(existing["id"])),
                )
                return int(existing["id"])

            cursor = conn.execute(
                """
                INSERT INTO observations
                    (domain_id, ip, source, dns_server, ttl, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (domain_id, ip, source, dns_server, ttl, confidence),
            )

            return int(cursor.lastrowid)

    def list_observations(self) -> list[Observation]:
        """Return all observations."""

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    domain_id,
                    ip,
                    source,
                    dns_server,
                    hits,
                    ttl,
                    confidence
                FROM observations
                ORDER BY last_seen DESC
                """
            ).fetchall()

            return [
                Observation(
                    id=int(row["id"]),
                    domain_id=row["domain_id"],
                    ip=str(row["ip"]),
                    source=str(row["source"]),
                    dns_server=row["dns_server"],
                    hits=int(row["hits"]),
                    ttl=row["ttl"],
                    confidence=int(row["confidence"]),
                )
                for row in rows
            ]

    def rebuild_route_stats(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> int:
        """Rebuild route statistics from observations."""

        observations = self.list_observations()
        stats: dict[str, dict[str, object]] = {}

        for observation in observations:
            ip = ipaddress.ip_address(observation.ip)

            if ip.version == 4:
                network = ipaddress.ip_network(f"{ip}/{ipv4_prefix}", strict=False)
            else:
                network = ipaddress.ip_network(f"{ip}/{ipv6_prefix}", strict=False)

            prefix = str(network)

            if prefix not in stats:
                stats[prefix] = {
                    "family": ip.version,
                    "source_ips": set(),
                    "total_hits": 0,
                    "confidence": 0,
                    "first_seen": None,
                    "last_seen": None,
                }

            stat = stats[prefix]
            source_ips = stat["source_ips"]
            if not isinstance(source_ips, set):
                raise RuntimeError("Invalid route statistics state")

            source_ips.add(str(ip))
            stat["total_hits"] = int(stat["total_hits"]) + observation.hits
            stat["confidence"] = int(stat["confidence"]) + observation.confidence

        with self._database.connection() as conn:
            conn.execute("DELETE FROM route_stats")

            for prefix, stat in stats.items():
                source_ips = stat["source_ips"]
                if not isinstance(source_ips, set):
                    raise RuntimeError("Invalid route statistics state")

                conn.execute(
                    """
                    INSERT INTO route_stats
                        (
                            prefix,
                            family,
                            source_ips,
                            total_hits,
                            confidence,
                            first_seen,
                            last_seen
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prefix,
                        int(stat["family"]),
                        len(source_ips),
                        int(stat["total_hits"]),
                        int(stat["confidence"]),
                        stat["first_seen"],
                        stat["last_seen"],
                    ),
                )

        return len(stats)

    def list_route_stats(self) -> list[RouteStat]:
        """Return route statistics."""

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    prefix,
                    family,
                    source_ips,
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
                    total_hits=int(row["total_hits"]),
                    confidence=int(row["confidence"]),
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                )
                for row in rows
            ]
