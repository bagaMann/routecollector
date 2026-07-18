"""
Tests for route plan snapshots.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from routecollector.history.plan_snapshot import (
    PlanSnapshotStore,
)
from routecollector.planner.planner import PlannedRoute


def make_route(
    prefix: str,
    family: int = 4,
    publish_score: int = 80,
) -> PlannedRoute:
    """Create a planned route for tests."""

    return PlannedRoute(
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


def test_snapshot_store_saves_and_loads_plan(
    tmp_path: Path,
) -> None:
    """Stored plan must be readable without data loss."""

    store = PlanSnapshotStore(tmp_path)

    path = store.save(
        [
            make_route("192.0.2.0/24"),
            make_route(
                "2001:db8::/48",
                family=6,
            ),
        ],
        created_at=datetime(
            2026,
            7,
            14,
            12,
            0,
            0,
        ),
    )

    snapshot = store.load(path)

    assert snapshot.created_at == "2026-07-14T12:00:00"
    assert snapshot.route_count == 2
    assert snapshot.routes[0].prefix == "192.0.2.0/24"
    assert snapshot.routes[1].prefix == "2001:db8::/48"


def test_snapshot_store_detects_added_and_removed_routes(
    tmp_path: Path,
) -> None:
    """Changes must compare route membership."""

    store = PlanSnapshotStore(tmp_path)

    store.save(
        [
            make_route("192.0.2.0/24"),
            make_route("198.51.100.0/24"),
        ],
        created_at=datetime(
            2026,
            7,
            14,
            12,
            0,
            0,
        ),
    )

    store.save(
        [
            make_route("198.51.100.0/24"),
            make_route("203.0.113.0/24"),
        ],
        created_at=datetime(
            2026,
            7,
            14,
            12,
            30,
            0,
        ),
    )

    changes = store.changes()

    assert changes is not None
    assert changes.previous_count == 2
    assert changes.current_count == 2
    assert changes.changed is True

    assert [
        route.prefix
        for route in changes.added
    ] == ["203.0.113.0/24"]

    assert [
        route.prefix
        for route in changes.removed
    ] == ["192.0.2.0/24"]


def test_snapshot_store_reports_no_membership_changes(
    tmp_path: Path,
) -> None:
    """Statistic changes alone must not add or remove routes."""

    store = PlanSnapshotStore(tmp_path)

    store.save(
        [
            make_route(
                "192.0.2.0/24",
                publish_score=70,
            )
        ],
        created_at=datetime(
            2026,
            7,
            14,
            12,
            0,
            0,
        ),
    )

    store.save(
        [
            make_route(
                "192.0.2.0/24",
                publish_score=95,
            )
        ],
        created_at=datetime(
            2026,
            7,
            14,
            12,
            30,
            0,
        ),
    )

    changes = store.changes()

    assert changes is not None
    assert changes.changed is False
    assert changes.added == ()
    assert changes.removed == ()


def test_snapshot_store_requires_two_snapshots_for_changes(
    tmp_path: Path,
) -> None:
    """One snapshot is insufficient for comparison."""

    store = PlanSnapshotStore(tmp_path)

    assert store.changes() is None

    store.save([make_route("192.0.2.0/24")])

    assert store.changes() is None


def test_snapshot_store_prunes_old_files(
    tmp_path: Path,
) -> None:
    """Snapshot retention must remove oldest files."""

    store = PlanSnapshotStore(
        tmp_path,
        keep=2,
    )

    for hour in range(3):
        store.save(
            [make_route(f"192.0.{hour}.0/24")],
            created_at=datetime(
                2026,
                7,
                14,
                hour,
                0,
                0,
            ),
        )

    paths = store.list_paths()

    assert len(paths) == 2
    assert paths[0].name.startswith(
        "20260714T010000"
    )
    assert paths[1].name.startswith(
        "20260714T020000"
    )


@pytest.mark.parametrize(
    "keep",
    [0, 1, -1],
)
def test_snapshot_store_rejects_small_retention(
    tmp_path: Path,
    keep: int,
) -> None:
    """At least two snapshots are required."""

    with pytest.raises(
        ValueError,
        match="At least two",
    ):
        PlanSnapshotStore(
            tmp_path,
            keep=keep,
        )
