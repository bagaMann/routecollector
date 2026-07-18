"""
Tests for the default doctor runner factory.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import routecollector.doctor.bird_checks as bird_checks_module
from routecollector.core.database import Database
from routecollector.doctor.factory import build_doctor_runner


def test_build_doctor_runner_runs_all_current_checks(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Factory must register all current read-only checks."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}", encoding="utf-8")

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

    main_config = tmp_path / "bird.conf"
    generated_config = tmp_path / "generated.conf"
    installed_config = tmp_path / "installed.conf"

    for path in (
        main_config,
        generated_config,
        installed_config,
    ):
        path.write_text("# config\n", encoding="utf-8")

    monkeypatch.setattr(
        bird_checks_module.shutil,
        "which",
        lambda name: f"/usr/sbin/{name}",
    )
    monkeypatch.setattr(
        bird_checks_module,
        "_run_command",
        lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="Configuration OK",
            stderr="",
        ),
    )

    result = build_doctor_runner(
        config_path=config_path,
        directories=(state_dir, services_dir),
        database_path=database_path,
        services_dir=services_dir,
        bird_main_config=main_config,
        bird_generated_config=generated_config,
        bird_installed_config=installed_config,
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
        "BIRD",
    ]
