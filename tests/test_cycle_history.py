"""
Tests for persistent RouteCollector cycle history.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from routecollector.core.database import Database
from routecollector.history.cycle_history import (
    CycleHistoryStore,
    NewCycleHistoryEntry,
)


def make_entry(
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    service_name: str | None = None,
    planned_routes: int = 44,
    routes_added: int = 2,
    routes_removed: int = 1,
) -> NewCycleHistoryEntry:
    """Create one cycle history input."""

    return NewCycleHistoryEntry(
        started_at=started_at
        or datetime(2026, 7, 15, 12, 0, 0),
        completed_at=completed_at
        or datetime(2026, 7, 15, 12, 0, 40),
        service_name=service_name,
        services_synced=3,
        domains_synced=232,
        domains_resolved=233,
        observations_stored=3300,
        route_stats_built=87,
        planned_routes=planned_routes,
        routes_added=routes_added,
        routes_removed=routes_removed,
        generated_changed=True,
        installed_changed=True,
        bird_reloaded=True,
    )


def make_store(
    tmp_path: Path,
) -> CycleHistoryStore:
    """Create initialized temporary history store."""

    database = Database(tmp_path / "state.db")
    database.initialize()

    return CycleHistoryStore(database)


def test_database_initializes_cycle_history_table(
    tmp_path: Path,
) -> None:
    """Database initialization must create cycle history."""

    database = Database(tmp_path / "state.db")
    database.initialize()

    with database.connection() as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'cycle_history'
            """
        ).fetchone()

    assert row is not None
    assert row["name"] == "cycle_history"


def test_cycle_history_store_adds_and_reads_entry(
    tmp_path: Path,
) -> None:
    """Stored cycle information must remain intact."""

    store = make_store(tmp_path)

    entry_id = store.add(
        make_entry(service_name="youtube")
    )
    entry = store.latest()

    assert entry_id == 1
    assert entry is not None
    assert entry.id == 1
    assert entry.service_name == "youtube"
    assert entry.duration_seconds == 40.0
    assert entry.services_synced == 3
    assert entry.domains_synced == 232
    assert entry.domains_resolved == 233
    assert entry.observations_stored == 3300
    assert entry.route_stats_built == 87
    assert entry.planned_routes == 44
    assert entry.routes_added == 2
    assert entry.routes_removed == 1
    assert entry.generated_changed is True
    assert entry.installed_changed is True
    assert entry.bird_reloaded is True


def test_cycle_history_store_returns_newest_first(
    tmp_path: Path,
) -> None:
    """History listing must be newest first."""

    store = make_store(tmp_path)

    store.add(
        make_entry(
            completed_at=datetime(
                2026,
                7,
                15,
                12,
                0,
                40,
            ),
            planned_routes=44,
        )
    )
    store.add(
        make_entry(
            started_at=datetime(
                2026,
                7,
                15,
                12,
                30,
                0,
            ),
            completed_at=datetime(
                2026,
                7,
                15,
                12,
                30,
                42,
            ),
            planned_routes=45,
        )
    )

    entries = store.list_recent()

    assert [
        entry.planned_routes
        for entry in entries
    ] == [45, 44]


def test_cycle_history_store_honors_limit(
    tmp_path: Path,
) -> None:
    """History result size must obey requested limit."""

    store = make_store(tmp_path)

    for routes in (40, 41, 42):
        store.add(
            make_entry(planned_routes=routes)
        )

    entries = store.list_recent(limit=2)

    assert len(entries) == 2
    assert [
        entry.planned_routes
        for entry in entries
    ] == [42, 41]


def test_cycle_history_store_counts_entries(
    tmp_path: Path,
) -> None:
    """Store must report the number of saved cycles."""

    store = make_store(tmp_path)

    assert store.count() == 0

    store.add(make_entry())
    store.add(make_entry())

    assert store.count() == 2


def test_cycle_history_store_clamps_negative_duration(
    tmp_path: Path,
) -> None:
    """Clock anomalies must not create negative duration."""

    store = make_store(tmp_path)

    store.add(
        make_entry(
            started_at=datetime(
                2026,
                7,
                15,
                12,
                1,
                0,
            ),
            completed_at=datetime(
                2026,
                7,
                15,
                12,
                0,
                0,
            ),
        )
    )

    entry = store.latest()

    assert entry is not None
    assert entry.duration_seconds == 0.0


@pytest.mark.parametrize("limit", [0, -1])
def test_cycle_history_store_rejects_invalid_limit(
    tmp_path: Path,
    limit: int,
) -> None:
    """History listing limit must be positive."""

    store = make_store(tmp_path)

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        store.list_recent(limit=limit)
