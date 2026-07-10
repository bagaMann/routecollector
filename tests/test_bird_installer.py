"""
Tests for BIRD configuration installation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from routecollector.exporter.birdctl import (
    BirdConfigInstaller,
    BirdControlError,
)


def create_installer(
    tmp_path: Path,
    source_content: str,
    target_content: str | None = None,
) -> BirdConfigInstaller:
    """Create test installer with temporary files."""

    source_file = tmp_path / "generated.conf"
    target_file = tmp_path / "etc" / "routecollector.conf"
    main_config = tmp_path / "bird.conf"

    source_file.write_text(source_content, encoding="utf-8")
    main_config.write_text("# main BIRD config\n", encoding="utf-8")

    if target_content is not None:
        target_file.parent.mkdir(parents=True)
        target_file.write_text(target_content, encoding="utf-8")

    return BirdConfigInstaller(
        source_file=source_file,
        target_file=target_file,
        main_config=main_config,
    )


def test_installer_installs_new_configuration(tmp_path: Path) -> None:
    """Missing target file must be installed."""

    installer = create_installer(
        tmp_path,
        source_content="new configuration\n",
    )

    result = installer.install()

    assert result.changed is True
    assert result.path.read_text(encoding="utf-8") == "new configuration\n"


def test_installer_skips_identical_configuration(tmp_path: Path) -> None:
    """Identical target configuration must not be replaced."""

    installer = create_installer(
        tmp_path,
        source_content="same configuration\n",
        target_content="same configuration\n",
    )

    result = installer.install()

    assert result.changed is False
    assert result.path.read_text(encoding="utf-8") == "same configuration\n"


def test_installer_replaces_changed_configuration(tmp_path: Path) -> None:
    """Different target configuration must be replaced."""

    installer = create_installer(
        tmp_path,
        source_content="new configuration\n",
        target_content="old configuration\n",
    )

    result = installer.install()

    assert result.changed is True
    assert result.path.read_text(encoding="utf-8") == "new configuration\n"
    assert not result.path.with_suffix(".conf.tmp").exists()


def test_installer_rejects_missing_source(tmp_path: Path) -> None:
    """Missing generated configuration must raise an error."""

    source_file = tmp_path / "missing.conf"
    target_file = tmp_path / "routecollector.conf"
    main_config = tmp_path / "bird.conf"
    main_config.write_text("# config\n", encoding="utf-8")

    installer = BirdConfigInstaller(
        source_file=source_file,
        target_file=target_file,
        main_config=main_config,
    )

    with pytest.raises(
        BirdControlError,
        match="Generated BIRD config not found",
    ):
        installer.install()
