"""
BIRD control helpers.
"""

from __future__ import annotations

import subprocess


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
