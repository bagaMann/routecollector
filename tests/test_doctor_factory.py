"""
Tests for the default doctor runner factory.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.core.database import Database
from routecollector.doctor.factory import (
    build_doctor_runner,
)


def test_build_doctor_runner_runs_all_current_checks(
    tmp_path: Path,
) -> None:
    """Factory must register all current read-only checks."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "project: {}",
        encoding="utf-8",
    )

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    services_dir = tmp_path / "services"
    services_dir.mkdir()
    (services_dir / "example.yaml").write_text(
        """
name: example
enabled: true
sources:
  - type: manual
    domains:
      - example.com
""".strip(),
        encoding="utf-8",
    )

    database_path = state_dir / "state.db"
    Database(database_path).initialize()

    result = build_doctor_runner(
        config_path=config_path,
        directories=(state_dir, services_dir),
        database_path=database_path,
        services_dir=services_dir,
    ).run()

    assert result.error_count == 0
    assert result.warning_count == 0
    assert result.overall_label == "HEALTHY"

    categories = [
        category
        for category, _ in result.by_category()
    ]

    assert categories == [
        "Environment",
        "Directories",
        "Database",
        "Service configuration",
        "Source plugins",
    ]
