"""Tests for source plugin diagnostics and CLI output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import routecollector.cli as cli_module
from routecollector.sources.status import (
    ConfiguredSourceUsage,
    SourcePluginInfo,
    SourceStatus,
    collect_source_status,
)


def example_status() -> SourceStatus:
    return SourceStatus(
        plugins=(
            SourcePluginInfo(
                name="manual",
                origin="built-in",
                package_name="routecollector",
                package_version="core",
                entry_point=None,
            ),
            SourcePluginInfo(
                name="example",
                origin="external",
                package_name="routecollector-source-example",
                package_version="0.1.0",
                entry_point="routecollector_source_example:ExampleSource",
            ),
        ),
        configured_usage=(
            ConfiguredSourceUsage(
                service_name="youtube",
                enabled=True,
                source_names=("manual",),
            ),
        ),
    )


def test_collect_source_status_lists_plugins_and_usage(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
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
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "routecollector.sources.status.discover_external_plugins",
        lambda: (),
    )

    status = collect_source_status(services_dir)

    assert any(
        plugin.name == "manual" and plugin.origin == "built-in"
        for plugin in status.plugins
    )
    assert status.configured_usage == (
        ConfiguredSourceUsage("youtube", True, ("manual",)),
    )


def test_command_sources_prints_available_plugins(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "collect_source_status",
        lambda _: example_status(),
    )

    result = cli_module.command_sources()
    output = capsys.readouterr().out

    assert result == 0
    assert "Available sources" in output
    assert "manual" in output
    assert "built-in" in output
    assert "example" in output
    assert "external" in output
    assert "Configured usage" in output


def test_command_plugin_info_prints_metadata(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "collect_source_status",
        lambda _: example_status(),
    )

    result = cli_module.command_plugin_info()
    output = capsys.readouterr().out

    assert result == 0
    assert "Source plugin information" in output
    assert "routecollector-source-example" in output
    assert "0.1.0" in output
    assert "routecollector_source_example:ExampleSource" in output


def test_parser_accepts_plugin_info_command() -> None:
    args = cli_module.build_parser().parse_args(["plugin-info"])
    assert args.command == "plugin-info"
