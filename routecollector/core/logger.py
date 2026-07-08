"""
Logging configuration for RouteCollector.
"""

from __future__ import annotations

import logging
from pathlib import Path

from routecollector.core.config import LoggingConfig


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)


class LoggerFactory:
    """Create and configure application loggers."""

    def __init__(self, config: LoggingConfig, log_dir: Path) -> None:
        self._config = config
        self._log_dir = log_dir

    def create(self) -> logging.Logger:
        """Create configured logger."""

        self._log_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("routecollector")
        logger.setLevel(getattr(logging, self._config.level.upper()))

        # Если логгер уже настроен — не добавляем обработчики повторно
        if logger.handlers:
            return logger

        formatter = logging.Formatter(LOG_FORMAT)

        console = logging.StreamHandler()
        console.setFormatter(formatter)

        logfile = logging.FileHandler(
            self._log_dir / "routecollector.log",
            encoding="utf-8",
        )
        logfile.setFormatter(formatter)

        logger.addHandler(console)
        logger.addHandler(logfile)

        return logger
