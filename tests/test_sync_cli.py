"""
Tests for the service synchronization CLI command.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import routecollector.cli as cli_module


def test_command_sync_uses_service_source_sync(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """CLI sync must use the pluggable source synchronizer."""

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

        def sync(self) -> SimpleNamespace:
            return SimpleNamespace(
                service_count=3,
                domain_count=232,
            )

    monkeypatch.setattr(
        cli_module,
        "get_app",
        lambda _: app,
    )
    monkeypatch.setattr(
        cli_module,
        "ServiceSourceSync",
        FakeServiceSourceSync,
    )

    result = cli_module.command_sync(
        Path("config/config.yaml")
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Service configuration synced" in output
    assert "Services: 3" in output
    assert "Domains: 232" in output
