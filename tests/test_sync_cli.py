"""Tests for the detailed service synchronization CLI report."""

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


def make_result() -> SourceSyncResult:
    """Build representative synchronization statistics."""

    return SourceSyncResult(
        service_count=3,
        source_count=6,
        domain_count=232,
        deactivated_count=258,
        disabled_service_count=1,
        services=(
            ServiceSourceSyncResult(
                service_name="discord",
                enabled=True,
                source_count=2,
                domain_count=31,
                deactivated_count=37,
                sources=(
                    SourceExecutionResult("manual", 9, {}),
                    SourceExecutionResult(
                        "domain-list-community",
                        28,
                        {},
                    ),
                ),
            ),
            ServiceSourceSyncResult(
                service_name="telegram",
                enabled=False,
                source_count=2,
                domain_count=21,
                deactivated_count=33,
                sources=(
                    SourceExecutionResult("manual", 12, {}),
                    SourceExecutionResult(
                        "domain-list-community",
                        21,
                        {},
                    ),
                ),
            ),
            ServiceSourceSyncResult(
                service_name="youtube",
                enabled=True,
                source_count=2,
                domain_count=180,
                deactivated_count=188,
                sources=(
                    SourceExecutionResult("manual", 11, {}),
                    SourceExecutionResult(
                        "domain-list-community",
                        177,
                        {},
                    ),
                ),
            ),
        ),
    )


def test_command_sync_prints_detailed_report(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """CLI sync must show services, sources, totals and duration."""

    repository = object()
    app = SimpleNamespace(repository=repository)

    class FakeServiceSourceSync:
        def __init__(
            self,
            *,
            repository: object,
            services_dir: Path,
        ) -> None:
            assert repository is app.repository
            assert services_dir == cli_module.DEFAULT_SERVICES_DIR

        def sync(self) -> SourceSyncResult:
            return make_result()

    times = iter((100.0, 100.42))

    monkeypatch.setattr(cli_module, "get_app", lambda _: app)
    monkeypatch.setattr(
        cli_module,
        "ServiceSourceSync",
        FakeServiceSourceSync,
    )
    monkeypatch.setattr(
        cli_module,
        "monotonic",
        lambda: next(times),
    )

    result = cli_module.command_sync(Path("config/config.yaml"))
    output = capsys.readouterr().out

    assert result == 0
    assert "Service synchronization completed" in output
    assert "discord [enabled]" in output
    assert "telegram [disabled]" in output
    assert "youtube [enabled]" in output
    assert "manual" in output
    assert "domain-list-community" in output
    assert "Merged domains" in output
    assert ": 31" in output
    assert ": 180" in output
    assert "Configured services   : 3" in output
    assert "Disabled services     : 1" in output
    assert "Source plugins        : 6" in output
    assert "Merged domains        : 232" in output
    assert "Rows deactivated      : 258" in output
    assert "Duration              : 0.42s" in output


def test_command_sync_handles_empty_result(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """CLI must produce a useful report with no configured services."""

    app = SimpleNamespace(repository=object())

    class EmptySync:
        def __init__(
            self,
            *,
            repository: object,
            services_dir: Path,
        ) -> None:
            pass

        def sync(self) -> SourceSyncResult:
            return SourceSyncResult(
                service_count=0,
                source_count=0,
                domain_count=0,
                deactivated_count=4,
                disabled_service_count=1,
                services=(),
            )

    times = iter((5.0, 5.01))

    monkeypatch.setattr(cli_module, "get_app", lambda _: app)
    monkeypatch.setattr(cli_module, "ServiceSourceSync", EmptySync)
    monkeypatch.setattr(
        cli_module,
        "monotonic",
        lambda: next(times),
    )

    result = cli_module.command_sync(Path("config/config.yaml"))
    output = capsys.readouterr().out

    assert result == 0
    assert "No configured services were synchronized." in output
    assert "Configured services   : 0" in output
    assert "Disabled services     : 1" in output
    assert "Rows deactivated      : 4" in output
