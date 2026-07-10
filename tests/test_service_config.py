"""
Tests for service configuration loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from routecollector.parser.service_config import (
    ServiceConfigError,
    ServiceConfigLoader,
)


def test_service_config_loader_reads_yaml(tmp_path: Path) -> None:
    """Loader must parse a valid service configuration."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    config_file = services_dir / "youtube.yaml"
    config_file.write_text(
        """
name: youtube
description: YouTube video platform
enabled: true

sources:
  - manual
  - domain-list-community

domain_list_community:
  lists:
    - youtube

domains:
  - youtube.com
  - googlevideo.com
""".strip(),
        encoding="utf-8",
    )

    loader = ServiceConfigLoader(services_dir)
    configs = loader.load_all()

    assert len(configs) == 1

    config = configs[0]

    assert config.name == "youtube"
    assert config.enabled is True
    assert config.description == "YouTube video platform"
    assert config.sources == ["manual", "domain-list-community"]
    assert config.domain_list_community_lists == ["youtube"]
    assert config.domains == ["youtube.com", "googlevideo.com"]


def test_service_config_loader_rejects_missing_name(
    tmp_path: Path,
) -> None:
    """Loader must reject a service configuration without a name."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    config_file = services_dir / "invalid.yaml"
    config_file.write_text(
        """
enabled: true
domains:
  - example.com
""".strip(),
        encoding="utf-8",
    )

    loader = ServiceConfigLoader(services_dir)

    with pytest.raises(ServiceConfigError, match="Missing service name"):
        loader.load_all()


def test_service_config_loader_returns_empty_list_for_missing_directory(
    tmp_path: Path,
) -> None:
    """Missing services directory must produce an empty result."""

    services_dir = tmp_path / "missing"

    loader = ServiceConfigLoader(services_dir)

    assert loader.load_all() == []
