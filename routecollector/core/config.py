"""
Configuration loader for RouteCollector.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True, frozen=True)
class ProjectConfig:
    """Project configuration."""

    name: str
    version: str


@dataclass(slots=True, frozen=True)
class DatabaseConfig:
    """Database configuration."""

    path: Path


@dataclass(slots=True, frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str


@dataclass(slots=True, frozen=True)
class Config:
    """Application configuration."""

    project: ProjectConfig
    database: DatabaseConfig
    logging: LoggingConfig


class ConfigError(RuntimeError):
    """Configuration error."""


class ConfigLoader:
    """Load RouteCollector configuration."""

    def __init__(self, filename: Path) -> None:
        self.filename = filename

    def load(self) -> Config:
        """Load configuration from YAML."""

        if not self.filename.exists():
            raise ConfigError(f"Configuration file not found: {self.filename}")

        with self.filename.open("r", encoding="utf-8") as file:
            data: dict[str, Any] = yaml.safe_load(file)

        return Config(
            project=ProjectConfig(
                name=data["project"]["name"],
                version=data["project"]["version"],
            ),
            database=DatabaseConfig(
                path=Path(data["database"]["path"]),
            ),
            logging=LoggingConfig(
                level=data["logging"]["level"],
            ),
        )
