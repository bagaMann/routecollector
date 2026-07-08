"""
Application bootstrap.

Responsible for initializing RouteCollector core services.
"""

from __future__ import annotations

from pathlib import Path
import logging

from routecollector.core.config import Config, ConfigLoader
from routecollector.core.logger import LoggerFactory


class Application:
    """Main application."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

        self.config: Config | None = None
        self.logger: logging.Logger | None = None

    def initialize(self) -> None:
        """Initialize application."""

        self.config = ConfigLoader(self._config_path).load()

        self.logger = LoggerFactory(
            self.config.logging,
            Path("logs"),
        ).create()

        self.logger.info("Application initialized")

    @property
    def initialized(self) -> bool:
        """Return initialization state."""

        return (
            self.config is not None
            and self.logger is not None
        )

    def status(self) -> dict[str, str]:
        """Return application status."""

        return {
            "configuration": "OK" if self.config else "FAILED",
            "logger": "OK" if self.logger else "FAILED",
        }
