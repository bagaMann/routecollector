"""Tests for structured run-once CLI output."""
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
    return SourceSyncResult(
        service_count=1,
        source_count=2,
        domain_count=180,
        deactivated_count=188,
        disabled_service_count=0,
        services=(
            ServiceSourceSyncResult(
                service_name='youtube',
                enabled=True,
                source_count=2,
                domain_count=180,
                deactivated_count=188,
                sources=(
                    SourceExecutionResult('manual', 11, {}),
                    SourceExecutionResult('domain-list-community', 177, {}),
                ),
            ),
        ),
    )

def make_result(*, dry_run: bool) -> SimpleNamespace:
    return SimpleNamespace(
        sync_result=make_sync_result(),
        services_synced=1,
        domains_synced=180,
        domains_resolved=180,
        observations_stored=1758,
        route_stats_built=123,
        planned_routes=49,
        routes_added=2,
        routes_removed=1,
        duration_seconds=14.5,
        generated_config=Path('state/dry-run/routecollector.conf' if dry_run else 'bird/routecollector.conf'),
        generated_changed=True,
        installed_config=None if dry_run else Path('/etc/bird/routecollector.conf'),
        installed_changed=not dry_run,
        bird_check_output=None if dry_run else 'Configuration OK',
        bird_reload_output=None,
        bird_reloaded=not dry_run,
        rollback_performed=False,
        dry_run=dry_run,
    )

def patch_workflow(monkeypatch: Any, *, expected_dry_run: bool) -> None:
    class FakeWorkflow:
        def run(self, service_name: str | None, dry_run: bool = False) -> SimpleNamespace:
            assert service_name is None
            assert dry_run is expected_dry_run
            return make_result(dry_run=dry_run)
    monkeypatch.setattr(cli_module, 'get_app', lambda _: SimpleNamespace())
    monkeypatch.setattr(cli_module, 'build_workflow', lambda *args, **kwargs: FakeWorkflow())

def call_command(*, dry_run: bool) -> int:
    return cli_module.command_run_once(
        config_path=Path('config/config.yaml'),
        service_name=None,
        min_confidence_ipv4=60,
        min_confidence_ipv6=60,
        max_age_days=30,
        enable_ipv6=False,
        dry_run=dry_run,
    )

def test_command_run_once_prints_structured_cycle(monkeypatch: Any, capsys: Any) -> None:
    patch_workflow(monkeypatch, expected_dry_run=False)
    assert call_command(dry_run=False) == 0
    output = capsys.readouterr().out
    assert 'RouteCollector cycle completed' in output
    assert 'Synchronization' in output
    assert 'Source plugins        : 2' in output
    assert 'youtube [enabled]' in output
    assert 'domain-list-community' in output
    assert 'Resolved domains      : 180' in output
    assert 'Planned routes        : 49' in output
    assert 'Reload                : completed' in output
    assert 'Snapshot              : stored' in output
    assert 'Duration              : 14.5s' in output

def test_command_run_once_prints_structured_dry_run(monkeypatch: Any, capsys: Any) -> None:
    patch_workflow(monkeypatch, expected_dry_run=True)
    assert call_command(dry_run=True) == 0
    output = capsys.readouterr().out
    assert 'RouteCollector dry run completed' in output
    assert 'Installed config      : not modified' in output
    assert 'Configuration check   : skipped' in output
    assert 'Reload                : skipped' in output
    assert 'Snapshot              : not stored' in output
    assert 'Cycle history         : not stored' in output
