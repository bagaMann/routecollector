#!/usr/bin/env python3
"""Add special-use IP filtering to RouteStatisticsBuilder."""

from __future__ import annotations

from pathlib import Path


TARGET = Path("routecollector/policy/statistics.py")

OLD = """            try:
                address = ipaddress.ip_address(observation.ip)
                first_seen = datetime.fromisoformat(observation.first_seen)
                last_seen = datetime.fromisoformat(observation.last_seen)
            except ValueError:
                continue

            prefix_length = (
"""

NEW = """            try:
                address = ipaddress.ip_address(observation.ip)
                first_seen = datetime.fromisoformat(observation.first_seen)
                last_seen = datetime.fromisoformat(observation.last_seen)
            except ValueError:
                continue

            # Never publish loopback, private, link-local, multicast,
            # reserved, unspecified or other non-globally-routable addresses.
            if not address.is_global:
                continue

            prefix_length = (
"""


def main() -> int:
    content = TARGET.read_text(encoding="utf-8")

    if "if not address.is_global:" in content:
        print("Special-use IP filtering is already installed")
        return 0

    if OLD not in content:
        raise RuntimeError("Expected statistics builder block was not found")

    backup = TARGET.with_suffix(".py.before-global-filter")
    backup.write_text(content, encoding="utf-8")

    TARGET.write_text(
        content.replace(OLD, NEW, 1),
        encoding="utf-8",
    )

    print(f"Patched: {TARGET}")
    print(f"Backup:  {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
