"""Tests for dry-run CLI behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import routecollector.cli as cli_module
from routecollector.sources.service_source_sync import (
    ServiceSourceSyncResult,
    SourceExecutionResult,
    SourceSyncResult,
)


def make_sync_result() -> SourceSyncResult:
    """Return representative source synchronization statistics."""

    return SourceSyncResult(
        service_count=3,
        source_count=6,
        domain_count=232,
        deactivated_count=258,
        disabled_service_count=0,
        services=(
            ServiceSourceSyncResult(
                service_name="youtube",
                enabled=True,
                source_count=2,
                domain_count=180,
                deactivated_count=188,
                sources=(
                    SourceExecutionResult(
                        source_name="manual",
                        domain_count=11,
                        metadata={},
                    ),
                    SourceExecutionResult(
                        source_name="domain-list-community",
                        domain_count=177,
                        metadata={},
                    ),
                ),
            ),
        ),
    )


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
                sync_result=make_sync_result(),
                services_synced=3,
                domains_synced=232,
                domains_resolved=232,
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
    assert "Synchronization" in output
    assert "Configured services   : 3" in output
    assert "Source plugins        : 6" in output
    assert "Merged domains        : 232" in output
    assert "Routes added          : 2" in output
    assert "Routes removed        : 1" in output
    assert "Installed config      : not modified" in output
    assert "Configuration check   : skipped" in output
    assert "Reload                : skipped" in output
    assert "Snapshot              : not stored" in output
    assert "Cycle history         : not stored" in output
