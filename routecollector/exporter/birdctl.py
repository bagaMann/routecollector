"""
BIRD configuration installation and control helpers.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class BirdControlError(RuntimeError):
    """BIRD control or configuration installation error."""


@dataclass(slots=True, frozen=True)
class BirdInstallResult:
    """Result of installing a generated BIRD configuration."""

    path: Path
    backup_path: Path | None
    changed: bool


class BirdControl:
    """Run BIRD control commands."""

    def __init__(
        self,
        birdc_bin: str = "birdc",
        timeout: float = 10.0,
    ) -> None:
        self._birdc_bin = birdc_bin
        self._timeout = timeout

    def configure_check(self) -> str:
        """Check the current BIRD configuration."""

        return self._run(["configure", "check"])

    def configure(self) -> str:
        """Apply the current BIRD configuration."""

        return self._run(["configure"])

    def _run(self, arguments: list[str]) -> str:
        """Execute birdc and return combined output."""

        try:
            result = subprocess.run(
                [self._birdc_bin, *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise BirdControlError(
                f"BIRD client not found: {self._birdc_bin}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise BirdControlError(
                f"BIRD command timed out after {self._timeout} seconds"
            ) from exc

        output = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part.strip()
        )

        if result.returncode != 0:
            raise BirdControlError(
                output or f"birdc exited with status {result.returncode}"
            )

        return output


class BirdConfigInstaller:
    """Install and roll back RouteCollector BIRD configuration."""

    def __init__(
        self,
        source_file: Path,
        target_file: Path,
        main_config: Path,
    ) -> None:
        self._source_file = source_file
        self._target_file = target_file
        self._main_config = main_config

    def install(self) -> BirdInstallResult:
        """Install config only when source and target differ."""

        self._validate_paths()

        if self._files_are_equal():
            return BirdInstallResult(
                path=self._target_file,
                backup_path=None,
                changed=False,
            )

        self._target_file.parent.mkdir(parents=True, exist_ok=True)

        backup_path = self._create_backup()
        temporary_file = self._target_file.with_suffix(
            self._target_file.suffix + ".tmp"
        )

        try:
            shutil.copyfile(self._source_file, temporary_file)
            temporary_file.replace(self._target_file)
        except OSError as exc:
            temporary_file.unlink(missing_ok=True)
            self.rollback(backup_path)

            raise BirdControlError(
                f"Unable to install BIRD configuration: {exc}"
            ) from exc

        return BirdInstallResult(
            path=self._target_file,
            backup_path=backup_path,
            changed=True,
        )

    def rollback(self, backup_path: Path | None) -> None:
        """Restore previously installed configuration."""

        if backup_path is None:
            self._target_file.unlink(missing_ok=True)
            return

        if not backup_path.is_file():
            raise BirdControlError(
                f"BIRD configuration backup not found: {backup_path}"
            )

        temporary_file = self._target_file.with_suffix(
            self._target_file.suffix + ".rollback.tmp"
        )

        try:
            shutil.copyfile(backup_path, temporary_file)
            temporary_file.replace(self._target_file)
        except OSError as exc:
            temporary_file.unlink(missing_ok=True)

            raise BirdControlError(
                f"Unable to restore BIRD configuration: {exc}"
            ) from exc

    def remove_backup(self, backup_path: Path | None) -> None:
        """Remove backup after successful configuration reload."""

        if backup_path is not None:
            backup_path.unlink(missing_ok=True)

    def _create_backup(self) -> Path | None:
        """Create backup of the currently installed configuration."""

        if not self._target_file.is_file():
            return None

        backup_path = self._target_file.with_suffix(
            self._target_file.suffix + ".bak"
        )

        try:
            shutil.copyfile(self._target_file, backup_path)
        except OSError as exc:
            raise BirdControlError(
                f"Unable to back up BIRD configuration: {exc}"
            ) from exc

        return backup_path

    def _validate_paths(self) -> None:
        """Validate source and main BIRD configuration paths."""

        if not self._source_file.is_file():
            raise BirdControlError(
                f"Generated BIRD config not found: {self._source_file}"
            )

        if not self._main_config.is_file():
            raise BirdControlError(
                f"BIRD main config not found: {self._main_config}"
            )

    def _files_are_equal(self) -> bool:
        """Return whether generated and installed files are identical."""

        if not self._target_file.is_file():
            return False

        try:
            return (
                self._source_file.read_bytes()
                == self._target_file.read_bytes()
            )
        except OSError as exc:
            raise BirdControlError(
                f"Unable to compare BIRD configurations: {exc}"
            ) from exc
