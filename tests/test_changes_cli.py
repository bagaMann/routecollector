"""
Tests for the route plan changes CLI command.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from routecollector.cli import command_changes
from routecollector.history.plan_snapshot import PlanSnapshotStore


def make_route(
    prefix: str,
    *,
    family: int = 4,
    publish_score: int = 80,
) -> SimpleNamespace:
    """Create a route compatible with plan snapshots."""

    return SimpleNamespace(
        prefix=prefix,
        family=family,
        source_ips=2,
        unique_domains=3,
        unique_resolvers=2,
        source_count=2,
        source_trust=100,
        confidence=70,
        publish_score=publish_score,
    )


def test_changes_reports_missing_snapshots(
    tmp_path: Path,
    capsys: object,
) -> None:
    """Command must explain that no snapshots exist."""

    result = command_changes(tmp_path)

    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert result == 0
    assert "No route plan snapshots are available." in output
    assert "run-once" in output


def test_changes_requires_two_snapshots(
    tmp_path: Path,
    capsys: object,
) -> None:
    """One snapshot must not be presented as a comparison."""

    store = PlanSnapshotStore(tmp_path)
    store.save(
        [make_route("192.0.2.0/24")],
        created_at=datetime(2026, 7, 14, 12, 0, 0),
    )

    result = command_changes(tmp_path)

    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert result == 0
    assert "Only one route plan snapshot is available." in output
    assert "At least two snapshots" in output


def test_changes_reports_no_membership_changes(
    tmp_path: Path,
    capsys: object,
) -> None:
    """Statistic changes alone must not appear as route changes."""

    store = PlanSnapshotStore(tmp_path)
    store.save(
        [make_route("192.0.2.0/24", publish_score=70)],
        created_at=datetime(2026, 7, 14, 12, 0, 0),
    )
    store.save(
        [make_route("192.0.2.0/24", publish_score=95)],
        created_at=datetime(2026, 7, 14, 12, 30, 0),
    )

    result = command_changes(tmp_path)

    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert result == 0
    assert "Routes before: 1" in output
    assert "Routes now:    1" in output
    assert "Added:         0" in output
    assert "Removed:       0" in output
    assert "No route membership changes detected." in output


def test_changes_reports_added_and_removed_routes(
    tmp_path: Path,
    capsys: object,
) -> None:
    """Command must print added and removed route membership."""

    store = PlanSnapshotStore(tmp_path)
    store.save(
        [
            make_route("192.0.2.0/24"),
            make_route("198.51.100.0/24"),
        ],
        created_at=datetime(2026, 7, 14, 12, 0, 0),
    )
    store.save(
        [
            make_route("198.51.100.0/24"),
            make_route("203.0.113.0/24"),
        ],
        created_at=datetime(2026, 7, 14, 12, 30, 0),
    )

    result = command_changes(tmp_path)

    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert result == 0
    assert "Routes before: 2" in output
    assert "Routes now:    2" in output
    assert "Added:         1" in output
    assert "Removed:       1" in output
    assert "+ 203.0.113.0/24" in output
    assert "- 192.0.2.0/24" in output
    assert "publish_score=80" in output
