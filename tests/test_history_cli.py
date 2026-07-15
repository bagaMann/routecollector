"""
Tests for the RouteCollector history CLI command.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from routecollector.cli import command_history
from routecollector.core.database import Database
from routecollector.history.cycle_history import (
    CycleHistoryStore,
    NewCycleHistoryEntry,
)


def add_history_entry(
    database: Database,
    *,
    service_name: str | None = None,
    planned_routes: int = 44,
    routes_added: int = 2,
    routes_removed: int = 1,
    bird_reloaded: bool = True,
) -> None:
    """Insert one successful cycle for CLI tests."""

    CycleHistoryStore(database).add(
        NewCycleHistoryEntry(
            started_at=datetime(
                2026,
                7,
                15,
                12,
                0,
                0,
            ),
            completed_at=datetime(
                2026,
                7,
                15,
                12,
                0,
                40,
            ),
            service_name=service_name,
            services_synced=3,
            domains_synced=232,
            domains_resolved=233,
            observations_stored=3300,
            route_stats_built=87,
            planned_routes=planned_routes,
            routes_added=routes_added,
            routes_removed=routes_removed,
            generated_changed=True,
            installed_changed=True,
            bird_reloaded=bird_reloaded,
        )
    )


def write_config(
    tmp_path: Path,
) -> Path:
    """Create minimal application configuration."""

    config_path = tmp_path / "config.yaml"
    database_path = tmp_path / "state.db"
    log_path = tmp_path / "routecollector.log"

    config_path.write_text(
        "\n".join(
            [
                "project:",
                "  name: RouteCollector",
                "  version: 1.2.0",
                "database:",
                f"  path: {database_path}",
                "logging:",
                "  level: INFO",
                f"  file: {log_path}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return config_path


def test_history_reports_empty_database(
    tmp_path: Path,
    capsys: object,
) -> None:
    """History command must explain when no cycles exist."""

    config_path = write_config(tmp_path)
    database = Database(tmp_path / "state.db")
    database.initialize()

    result = command_history(config_path, limit=20)

    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert result == 0
    assert "RouteCollector cycle history" in output
    assert "No successful cycles are stored." in output


def test_history_prints_recent_cycles(
    tmp_path: Path,
    capsys: object,
) -> None:
    """History command must print stored cycle details."""

    config_path = write_config(tmp_path)
    database = Database(tmp_path / "state.db")
    database.initialize()

    add_history_entry(
        database,
        service_name="youtube",
        planned_routes=47,
        routes_added=1,
        routes_removed=0,
        bird_reloaded=True,
    )

    result = command_history(config_path, limit=20)

    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert result == 0
    assert "service=youtube" in output
    assert "routes=47" in output
    assert "added=1" in output
    assert "removed=0" in output
    assert "bird_reloaded=yes" in output
    assert "duration=40.0s" in output
