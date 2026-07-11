#!/usr/bin/env python3
"""
Finalize RouteCollector CLI publication defaults and plan output.
"""

from __future__ import annotations

from pathlib import Path


TARGET = Path("routecollector/cli.py")


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if old not in content:
        raise RuntimeError(f"Unable to patch {label}: expected block not found")
    return content.replace(old, new, 1)


def main() -> int:
    content = TARGET.read_text(encoding="utf-8")

    if "DEFAULT_MIN_PUBLISH_SCORE_IPV4 = 50" not in content:
        anchor = "DEFAULT_MAX_AGE_DAYS = 30\n"
        replacement = (
            "DEFAULT_MAX_AGE_DAYS = 30\n"
            "DEFAULT_MIN_PUBLISH_SCORE_IPV4 = 50\n"
            "DEFAULT_MIN_PUBLISH_SCORE_IPV6 = 50\n"
        )
        content = replace_once(
            content,
            anchor,
            replacement,
            "publication constants",
        )

    content = content.replace(
        'default=10,\n        help="Minimum confidence for IPv4 routes",',
        'default=DEFAULT_MIN_PUBLISH_SCORE_IPV4,\n'
        '        help="Minimum publish score for IPv4 routes",',
        1,
    )
    content = content.replace(
        'default=10,\n        help="Minimum confidence for IPv6 routes",',
        'default=DEFAULT_MIN_PUBLISH_SCORE_IPV6,\n'
        '        help="Minimum publish score for IPv6 routes",',
        1,
    )

    old_output = '''        print(
            f"{route.prefix:<24} "
            f"family=IPv{route.family} "
            f"source_ips={route.source_ips:<4} "
            f"confidence={route.confidence}"
        )
'''

    new_output = '''        print(
            f"{route.prefix:<24} "
            f"family=IPv{route.family} "
            f"source_ips={route.source_ips:<4} "
            f"confidence={route.confidence:<3} "
            f"publish_score={route.publish_score:<3} "
            f"trust={route.source_trust:<3} "
            f"sources={route.source_count}"
        )
'''

    if "publish_score={route.publish_score" not in content:
        content = replace_once(
            content,
            old_output,
            new_output,
            "plan output",
        )

    backup = TARGET.with_suffix(".py.before-release-cli")
    backup.write_text(
        TARGET.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    TARGET.write_text(content, encoding="utf-8")

    print(f"Patched: {TARGET}")
    print(f"Backup:  {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
