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
    """Factory must register environment, directory and database checks."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "project: {}",
        encoding="utf-8",
    )

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    database_path = state_dir / "state.db"
    Database(database_path).initialize()

    result = build_doctor_runner(
        config_path=config_path,
        directories=(state_dir,),
        database_path=database_path,
    ).run()

    assert result.check_count == 11
    assert result.error_count == 0
    assert result.overall_label == "HEALTHY"
