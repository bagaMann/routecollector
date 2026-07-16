"""
Tests for the RouteCollector repository.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.core.database import Database
from routecollector.core.repository import Repository


def make_repository(
    tmp_path: Path,
) -> tuple[Repository, Database]:
    """Create initialized temporary repository."""

    database = Database(tmp_path / "state.db")
    database.initialize()

    return Repository(database), database


def test_upsert_service_creates_and_updates_service(
    tmp_path: Path,
) -> None:
    """Service upsert must preserve ID and update fields."""

    repository, _ = make_repository(tmp_path)

    first_id = repository.upsert_service(
        name="youtube",
        description="Old description",
        enabled=True,
    )
    second_id = repository.upsert_service(
        name="youtube",
        description="New description",
        enabled=False,
    )

    service = repository.get_service("youtube")

    assert first_id == second_id
    assert service is not None
    assert service.id == first_id
    assert service.description == "New description"
    assert service.enabled is False


def test_upsert_domain_preserves_id_and_reactivates(
    tmp_path: Path,
) -> None:
    """Domain upsert must update active state without duplication."""

    repository, database = make_repository(tmp_path)
    service_id = repository.upsert_service("youtube")

    first_id = repository.upsert_domain(
        service_id=service_id,
        domain="youtube.com",
        source="manual",
        active=False,
    )
    second_id = repository.upsert_domain(
        service_id=service_id,
        domain="youtube.com",
        source="manual",
        active=True,
    )

    with database.connection() as conn:
        rows = conn.execute(
            """
            SELECT id, active
            FROM domains
            WHERE service_id = ?
              AND domain = ?
              AND source = ?
            """,
            (
                service_id,
                "youtube.com",
                "manual",
            ),
        ).fetchall()

    assert first_id == second_id
    assert len(rows) == 1
    assert int(rows[0]["active"]) == 1


def test_deactivate_service_domains_only_affects_one_service(
    tmp_path: Path,
) -> None:
    """Bulk deactivation must be scoped to one service."""

    repository, database = make_repository(tmp_path)

    youtube_id = repository.upsert_service("youtube")
    telegram_id = repository.upsert_service("telegram")

    repository.upsert_domain(
        youtube_id,
        "youtube.com",
        "manual",
    )
    repository.upsert_domain(
        youtube_id,
        "googlevideo.com",
        "manual",
    )
    repository.upsert_domain(
        telegram_id,
        "telegram.org",
        "manual",
    )

    changed = repository.deactivate_service_domains(
        youtube_id
    )

    assert changed == 2

    with database.connection() as conn:
        rows = conn.execute(
            """
            SELECT service_id, domain, active
            FROM domains
            ORDER BY domain
            """
        ).fetchall()

    states = {
        (
            int(row["service_id"]),
            str(row["domain"]),
        ): int(row["active"])
        for row in rows
    }

    assert states[
        (youtube_id, "youtube.com")
    ] == 0
    assert states[
        (youtube_id, "googlevideo.com")
    ] == 0
    assert states[
        (telegram_id, "telegram.org")
    ] == 1


def test_deactivate_service_domains_counts_only_active_rows(
    tmp_path: Path,
) -> None:
    """Repeated deactivation must return zero after first call."""

    repository, _ = make_repository(tmp_path)
    service_id = repository.upsert_service("youtube")

    repository.upsert_domain(
        service_id,
        "youtube.com",
        "manual",
        active=True,
    )
    repository.upsert_domain(
        service_id,
        "inactive.example",
        "manual",
        active=False,
    )

    assert repository.deactivate_service_domains(
        service_id
    ) == 1
    assert repository.deactivate_service_domains(
        service_id
    ) == 0


def test_list_domains_returns_only_active_rows(
    tmp_path: Path,
) -> None:
    """Inactive domain provenance must not be returned."""

    repository, _ = make_repository(tmp_path)
    service_id = repository.upsert_service("youtube")

    repository.upsert_domain(
        service_id,
        "youtube.com",
        "manual",
        active=True,
    )
    repository.upsert_domain(
        service_id,
        "old.example",
        "legacy",
        active=False,
    )

    domains = repository.list_domains("youtube")

    assert [
        (domain.domain, domain.source)
        for domain in domains
    ] == [
        ("youtube.com", "manual")
    ]


def test_list_domains_can_filter_by_service(
    tmp_path: Path,
) -> None:
    """Service filter must exclude other active services."""

    repository, _ = make_repository(tmp_path)

    youtube_id = repository.upsert_service("youtube")
    telegram_id = repository.upsert_service("telegram")

    repository.upsert_domain(
        youtube_id,
        "youtube.com",
        "manual",
    )
    repository.upsert_domain(
        telegram_id,
        "telegram.org",
        "manual",
    )

    youtube_domains = repository.list_domains("youtube")

    assert len(youtube_domains) == 1
    assert youtube_domains[0].domain == "youtube.com"
