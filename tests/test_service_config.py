"""Tests for service configuration loader."""

from pathlib import Path

import pytest

from routecollector.parser.service_config import (
    ServiceConfigError,
    ServiceConfigLoader,
)


def test_loader_translates_legacy_yaml(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "youtube.yaml").write_text(
        """
name: youtube
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

    config = ServiceConfigLoader(services).load_all()[0]

    assert config.sources == [
        "manual",
        "domain-list-community",
    ]
    assert config.source_configs[0].options == {
        "domains": ["youtube.com", "googlevideo.com"]
    }
    assert config.source_configs[1].options == {
        "list": "youtube"
    }


def test_loader_reads_declarative_sources(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "youtube.yaml").write_text(
        """
name: youtube
sources:
  - type: manual
    domains:
      - youtube.com
  - type: domain-list-community
    options:
      list: youtube
      timeout: 15
      max_depth: 5
""".strip(),
        encoding="utf-8",
    )

    config = ServiceConfigLoader(services).load_all()[0]

    assert config.sources == [
        "manual",
        "domain-list-community",
    ]
    assert config.source_configs[0].options == {
        "domains": ["youtube.com"]
    }
    assert config.source_configs[1].options == {
        "list": "youtube",
        "timeout": 15,
        "max_depth": 5,
    }


def test_loader_defaults_to_manual(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "example.yaml").write_text(
        "name: example\ndomains:\n  - example.com\n",
        encoding="utf-8",
    )

    config = ServiceConfigLoader(services).load_all()[0]
    assert config.sources == ["manual"]
    assert config.source_configs[0].options == {
        "domains": ["example.com"]
    }


def test_loader_rejects_missing_name(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "invalid.yaml").write_text(
        "domains:\n  - example.com\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ServiceConfigError,
        match="Missing service name",
    ):
        ServiceConfigLoader(services).load_all()


def test_loader_rejects_duplicate_sources(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "invalid.yaml").write_text(
        """
name: invalid
sources:
  - manual
  - type: manual
    domains:
      - example.com
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ServiceConfigError,
        match="Duplicate source type",
    ):
        ServiceConfigLoader(services).load_all()


def test_loader_rejects_source_without_type(
    tmp_path: Path,
) -> None:
    services = tmp_path / "services"
    services.mkdir()
    (services / "invalid.yaml").write_text(
        """
name: invalid
sources:
  - options:
      domains:
        - example.com
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ServiceConfigError,
        match="requires non-empty 'type'",
    ):
        ServiceConfigLoader(services).load_all()


def test_loader_returns_empty_for_missing_dir(
    tmp_path: Path,
) -> None:
    assert ServiceConfigLoader(
        tmp_path / "missing"
    ).load_all() == []
