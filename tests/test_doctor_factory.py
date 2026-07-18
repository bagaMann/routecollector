"""Tests for the default doctor runner factory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import routecollector.doctor.bird_checks as bird_checks_module
import routecollector.doctor.runtime_checks as runtime_checks_module
from routecollector.core.database import Database
from routecollector.doctor.factory import build_doctor_runner


def test_build_doctor_runner_runs_all_current_checks(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
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

    snapshots_dir = state_dir / "plans"
    snapshots_dir.mkdir()
    (snapshots_dir / "20260718T100000_1.json").write_text(
        json.dumps(
            {
                "created_at": "2026-07-18T10:00:00",
                "route_count": 50,
                "routes": [],
            }
        ),
        encoding="utf-8",
    )

    configs = [
        tmp_path / "bird.conf",
        tmp_path / "generated.conf",
        tmp_path / "installed.conf",
    ]
    for path in configs:
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
            command, 0, "", ""
        ),
    )
    monkeypatch.setattr(
        runtime_checks_module,
        "_run_command",
        lambda command: subprocess.CompletedProcess(
            command,
            0,
            "enabled" if "is-enabled" in command else "active",
            "",
        ),
    )

    result = build_doctor_runner(
        config_path=config_path,
        directories=(state_dir, services_dir),
        database_path=database_path,
        services_dir=services_dir,
        snapshots_dir=snapshots_dir,
        bird_main_config=configs[0],
        bird_generated_config=configs[1],
        bird_installed_config=configs[2],
    ).run()

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
        "Service",
        "Snapshots",
        "History",
    ]
