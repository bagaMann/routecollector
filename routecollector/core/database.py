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

CREATE INDEX IF NOT EXISTS idx_domains_service_id ON domains(service_id);
CREATE INDEX IF NOT EXISTS idx_observations_ip ON observations(ip);
CREATE INDEX IF NOT EXISTS idx_observations_last_seen ON observations(last_seen);
CREATE INDEX IF NOT EXISTS idx_observations_source ON observations(source);
"""


class DatabaseError(RuntimeError):
    """Database error."""


class Database:
    """SQLite database wrapper."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create database directory and schema."""

        self.path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self.connection() as conn:
                conn.executescript(SCHEMA_SQL)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to initialize database: {exc}") from exc

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
