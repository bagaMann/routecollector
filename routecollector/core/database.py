"""
SQLite database layer for RouteCollector.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(service_id, domain, source),
    FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER,
    ip TEXT NOT NULL,
    source TEXT NOT NULL,
    dns_server TEXT,
    first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hits INTEGER NOT NULL DEFAULT 1,
    ttl INTEGER,
    confidence INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS route_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix TEXT NOT NULL UNIQUE,
    family INTEGER NOT NULL,
    source_ips INTEGER NOT NULL,
    unique_domains INTEGER NOT NULL DEFAULT 0,
    unique_resolvers INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    source_trust INTEGER NOT NULL DEFAULT 0,
    total_hits INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    first_seen TEXT,
    last_seen TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_domains_service_id
    ON domains(service_id);

CREATE INDEX IF NOT EXISTS idx_observations_ip
    ON observations(ip);

CREATE INDEX IF NOT EXISTS idx_observations_last_seen
    ON observations(last_seen);

CREATE INDEX IF NOT EXISTS idx_observations_source
    ON observations(source);

CREATE INDEX IF NOT EXISTS idx_route_stats_family
    ON route_stats(family);

CREATE INDEX IF NOT EXISTS idx_route_stats_confidence
    ON route_stats(confidence);

CREATE INDEX IF NOT EXISTS idx_route_stats_last_seen
    ON route_stats(last_seen);
"""


ROUTE_STATS_MIGRATIONS = {
    "unique_domains": (
        "ALTER TABLE route_stats "
        "ADD COLUMN unique_domains INTEGER NOT NULL DEFAULT 0"
    ),
    "unique_resolvers": (
        "ALTER TABLE route_stats "
        "ADD COLUMN unique_resolvers INTEGER NOT NULL DEFAULT 0"
    ),
    "source_count": (
        "ALTER TABLE route_stats "
        "ADD COLUMN source_count INTEGER NOT NULL DEFAULT 0"
    ),
    "source_trust": (
        "ALTER TABLE route_stats "
        "ADD COLUMN source_trust INTEGER NOT NULL DEFAULT 0"
    ),
}


POST_MIGRATION_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_route_stats_source_trust
    ON route_stats(source_trust);
"""


class DatabaseError(RuntimeError):
    """Database error."""


class Database:
    """SQLite database wrapper."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create database directory, schema and required migrations."""

        self.path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self.connection() as conn:
                conn.executescript(SCHEMA_SQL)
                self._migrate_route_stats(conn)
                conn.executescript(POST_MIGRATION_INDEXES_SQL)
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to initialize database: {exc}"
            ) from exc

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open SQLite connection with transaction handling."""

        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _migrate_route_stats(conn: sqlite3.Connection) -> None:
        """Add missing route_stats columns to an existing database."""

        columns = {
            str(row["name"])
            for row in conn.execute(
                "PRAGMA table_info(route_stats)"
            ).fetchall()
        }

        for column_name, migration_sql in ROUTE_STATS_MIGRATIONS.items():
            if column_name not in columns:
                conn.execute(migration_sql)
