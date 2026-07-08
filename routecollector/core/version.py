"""
RouteCollector version information.

This module contains application version metadata and helper functions.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass


from routecollector import __version__


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """Application version information."""

    version: str
    python: str
    platform: str


def get_version() -> VersionInfo:
    """
    Return current application version information.

    Returns:
        VersionInfo: Collected version information.
    """
    return VersionInfo(
        version=__version__,
        python=sys.version.split()[0],
        platform=platform.system(),
    )
