"""
BIRD control helpers.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class BirdControlError(RuntimeError):
    """BIRD control command error."""


class BirdControl:
    """Run safe BIRD control commands."""

    def __init__(self, birdc_bin: str = "birdc") -> None:
        self._birdc_bin = birdc_bin

    def configure_check(self) -> str:
        """Check BIRD configuration without applying it."""

        result = subprocess.run(
            [self._birdc_bin, "configure", "check"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = (result.stdout + result.stderr).strip()

        if result.returncode != 0:
            raise BirdControlError(output)

        return output

    def configure(self) -> str:
        """Apply BIRD configuration."""

        result = subprocess.run(
            [self._birdc_bin, "configure"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = (result.stdout + result.stderr).strip()

        if result.returncode != 0:
            raise BirdControlError(output)

        return output


class BirdConfigInstaller:
    """Install generated RouteCollector BIRD config."""

    def __init__(
        self,
        source_file: Path,
        target_file: Path,
        main_config: Path,
    ) -> None:
        self._source_file = source_file
        self._target_file = target_file
        self._main_config = main_config

    def install(self) -> Path:
        """Copy generated config into BIRD config directory."""

        if not self._source_file.exists():
            raise BirdControlError(f"Source config not found: {self._source_file}")

        if not self._main_config.exists():
            raise BirdControlError(f"BIRD main config not found: {self._main_config}")

        self._target_file.parent.mkdir(parents=True, exist_ok=True)

        tmp_file = self._target_file.with_suffix(self._target_file.suffix + ".tmp")
        shutil.copyfile(self._source_file, tmp_file)
        tmp_file.replace(self._target_file)

        return self._target_file
