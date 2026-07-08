"""
Application bootstrap.

Responsible for initializing RouteCollector core services.
"""

from __future__ import annotations

import logging
from pathlib import Path

from routecollector.core.config import Config, ConfigLoader
from routecollector.core.database import Database
from routecollector.core.logger import LoggerFactory


class Application:
    """Main application."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

        self.config: Config | None = None
        self.logger: logging.Logger | None = None
        self.database: Database | None = None

    def initialize(self) -> None:
        """Initialize application without changing runtime state."""

        self.config = ConfigLoader(self._config_path).load()

        self.logger = LoggerFactory(
            self.config.logging,
            Path("logs"),
        ).create()

        self.database = Database(self.config.database.path)

        self.logger.info("Application initialized")

    def init_database(self) -> None:
        """Initialize application database."""

        if self.config is None or self.logger is None or self.database is None:
            self.initialize()

        assert self.database is not None
        assert self.logger is not None

        self.database.initialize()
        self.logger.info("Database initialized: %s", self.database.path)

    @property
    def initialized(self) -> bool:
        """Return initialization state."""

        return (
            self.config is not None
            and self.logger is not None
            and self.database is not None
        )

    def status(self) -> dict[str, str]:
        """Return application status."""

        database_status = "FAILED"

        if self.database is not None:
            database_status = "OK" if self.database.path.exists() else "NOT INITIALIZED"

        return {
            "configuration": "OK" if self.config else "FAILED",
            "logger": "OK" if self.logger else "FAILED",
            "database": database_status,
        }
