"""
Tests for the default doctor runner factory.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.doctor.factory import (
    build_doctor_runner,
)


def test_build_doctor_runner_runs_environment_and_directories(
    tmp_path: Path,
) -> None:
    """Factory must register first read-only checks."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}", encoding="utf-8")

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    result = build_doctor_runner(
        config_path=config_path,
        directories=(state_dir,),
    ).run()

    assert result.check_count == 4
    assert result.error_count == 0
    assert result.overall_label == "HEALTHY"
