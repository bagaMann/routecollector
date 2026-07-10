"""
Tests for BIRD configuration installation and rollback.
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
) -> tuple[BirdConfigInstaller, Path, Path]:
    """Create test installer and return installer, source and target paths."""

    source_file = tmp_path / "generated.conf"
    target_file = tmp_path / "etc" / "routecollector.conf"
    main_config = tmp_path / "bird.conf"

    source_file.write_text(source_content, encoding="utf-8")
    main_config.write_text("# main BIRD config\n", encoding="utf-8")

    if target_content is not None:
        target_file.parent.mkdir(parents=True)
        target_file.write_text(target_content, encoding="utf-8")

    installer = BirdConfigInstaller(
        source_file=source_file,
        target_file=target_file,
        main_config=main_config,
    )

    return installer, source_file, target_file


def test_installer_installs_new_configuration(tmp_path: Path) -> None:
    """Missing target file must be installed without backup."""

    installer, _, target_file = create_installer(
        tmp_path,
        source_content="new configuration\n",
    )

    result = installer.install()

    assert result.changed is True
    assert result.backup_path is None
    assert result.path == target_file
    assert target_file.read_text(encoding="utf-8") == "new configuration\n"


def test_installer_skips_identical_configuration(tmp_path: Path) -> None:
    """Identical target configuration must not be replaced."""

    installer, _, target_file = create_installer(
        tmp_path,
        source_content="same configuration\n",
        target_content="same configuration\n",
    )

    result = installer.install()

    assert result.changed is False
    assert result.backup_path is None
    assert result.path == target_file
    assert target_file.read_text(encoding="utf-8") == "same configuration\n"


def test_installer_replaces_changed_configuration_and_creates_backup(
    tmp_path: Path,
) -> None:
    """Changed target configuration must be backed up and replaced."""

    installer, _, target_file = create_installer(
        tmp_path,
        source_content="new configuration\n",
        target_content="old configuration\n",
    )

    result = installer.install()

    assert result.changed is True
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.read_text(encoding="utf-8") == (
        "old configuration\n"
    )
    assert target_file.read_text(encoding="utf-8") == "new configuration\n"


def test_installer_rolls_back_existing_configuration(tmp_path: Path) -> None:
    """Rollback must restore the previous target content."""

    installer, _, target_file = create_installer(
        tmp_path,
        source_content="new configuration\n",
        target_content="old configuration\n",
    )

    result = installer.install()

    assert result.backup_path is not None
    assert target_file.read_text(encoding="utf-8") == "new configuration\n"

    installer.rollback(result.backup_path)

    assert target_file.read_text(encoding="utf-8") == "old configuration\n"


def test_installer_rolls_back_new_file_by_removing_it(
    tmp_path: Path,
) -> None:
    """Rollback without backup must remove a newly installed target."""

    installer, _, target_file = create_installer(
        tmp_path,
        source_content="new configuration\n",
    )

    result = installer.install()

    assert result.backup_path is None
    assert target_file.exists()

    installer.rollback(result.backup_path)

    assert not target_file.exists()


def test_installer_removes_backup_after_success(tmp_path: Path) -> None:
    """Successful reload cleanup must remove backup file."""

    installer, _, _ = create_installer(
        tmp_path,
        source_content="new configuration\n",
        target_content="old configuration\n",
    )

    result = installer.install()

    assert result.backup_path is not None
    assert result.backup_path.exists()

    installer.remove_backup(result.backup_path)

    assert not result.backup_path.exists()


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


def test_installer_rejects_missing_backup_on_rollback(
    tmp_path: Path,
) -> None:
    """Rollback must fail when the requested backup does not exist."""

    installer, _, _ = create_installer(
        tmp_path,
        source_content="new configuration\n",
    )

    missing_backup = tmp_path / "missing.bak"

    with pytest.raises(
        BirdControlError,
        match="BIRD configuration backup not found",
    ):
        installer.rollback(missing_backup)
