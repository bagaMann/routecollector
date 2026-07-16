"""Tests for dry-run CLI behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import routecollector.cli as cli_module


def test_run_once_parser_accepts_dry_run() -> None:
    """The run-once command must expose --dry-run."""

    args = cli_module.build_parser().parse_args(
        ["run-once", "--dry-run"]
    )

    assert args.command == "run-once"
    assert args.dry_run is True


def test_command_run_once_prints_dry_run_summary(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """Dry-run output must clearly state that BIRD was untouched."""

    class FakeWorkflow:
        def run(
            self,
            service_name: str | None,
            dry_run: bool = False,
        ) -> SimpleNamespace:
            assert service_name is None
            assert dry_run is True
            return SimpleNamespace(
                services_synced=3,
                domains_synced=232,
                domains_resolved=233,
                observations_stored=3300,
                route_stats_built=87,
                planned_routes=47,
                routes_added=2,
                routes_removed=1,
                duration_seconds=20.0,
                generated_config=Path(
                    "state/dry-run/routecollector.conf"
                ),
                generated_changed=True,
                installed_config=None,
                installed_changed=False,
                bird_check_output=None,
                bird_reload_output=None,
                bird_reloaded=False,
                rollback_performed=False,
                dry_run=True,
            )

    monkeypatch.setattr(
        cli_module,
        "get_app",
        lambda _: SimpleNamespace(),
    )
    monkeypatch.setattr(
        cli_module,
        "build_workflow",
        lambda *args, **kwargs: FakeWorkflow(),
    )

    result = cli_module.command_run_once(
        config_path=Path("config/config.yaml"),
        service_name=None,
        min_confidence_ipv4=60,
        min_confidence_ipv6=60,
        max_age_days=30,
        enable_ipv6=False,
        dry_run=True,
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "RouteCollector dry run completed" in output
    assert "Routes added:        2" in output
    assert "Routes removed:      1" in output
    assert "BIRD configuration was not installed." in output
    assert "Snapshot and cycle history were not modified." in output
