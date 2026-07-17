"""Tests for source plugin diagnostics and CLI output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import routecollector.cli as cli_module
from routecollector.sources.status import (
    ConfiguredSourceUsage,
    SourceStatus,
    collect_source_status,
)


def test_collect_source_status_lists_plugins_and_usage(tmp_path: Path) -> None:
    """Status collector must report registry and YAML usage."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    (services_dir / "youtube.yaml").write_text(
        """
name: youtube
enabled: true
sources:
  - type: manual
    domains:
      - youtube.com
  - type: http-text
    url: https://example.test/youtube.txt
""".strip(),
        encoding="utf-8",
    )
    (services_dir / "disabled.yaml").write_text(
        """
name: disabled
enabled: false
sources:
  - type: manual
    domains:
      - disabled.example
""".strip(),
        encoding="utf-8",
    )

    status = collect_source_status(services_dir)

    assert status.built_in_sources == (
        "domain-list-community",
        "http-text",
        "manual",
    )
    assert status.configured_usage == (
        ConfiguredSourceUsage("disabled", False, ("manual",)),
        ConfiguredSourceUsage("youtube", True, ("manual", "http-text")),
    )


def test_command_sources_prints_builtins_and_usage(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """CLI must show built-in plugins and configured services."""

    monkeypatch.setattr(
        cli_module,
        "collect_source_status",
        lambda _: SourceStatus(
            built_in_sources=(
                "domain-list-community",
                "http-text",
                "manual",
            ),
            configured_usage=(
                ConfiguredSourceUsage(
                    "youtube",
                    True,
                    ("manual", "domain-list-community"),
                ),
                ConfiguredSourceUsage(
                    "old-service",
                    False,
                    ("http-text",),
                ),
            ),
        ),
    )

    result = cli_module.command_sources()
    output = capsys.readouterr().out

    assert result == 0
    assert "Built-in sources" in output
    assert "domain-list-community" in output
    assert "http-text" in output
    assert "manual" in output
    assert "Configured usage" in output
    assert "youtube" in output
    assert "manual, domain-list-community" in output
    assert "old-service" in output
    assert "disabled" in output


def test_command_sources_handles_empty_configuration(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    """CLI must explain when no service YAML is configured."""

    monkeypatch.setattr(
        cli_module,
        "collect_source_status",
        lambda _: SourceStatus(
            built_in_sources=("manual",),
            configured_usage=(),
        ),
    )

    result = cli_module.command_sources()
    output = capsys.readouterr().out

    assert result == 0
    assert "manual" in output
    assert "No service sources are configured." in output


def test_parser_accepts_sources_command() -> None:
    """Argument parser must expose the sources command."""

    args = cli_module.build_parser().parse_args(["sources"])
    assert args.command == "sources"
