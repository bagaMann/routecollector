"""
Tests for dynamic BIRD route publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from routecollector.dynamic import (
    DynamicPublishError,
    DynamicPublisher,
)
from routecollector.exporter.birdctl import (
    BirdControlError,
)
from routecollector.planner.planner import PlannedRoute


def make_route(
    prefix: str = "142.250.74.0/24",
) -> PlannedRoute:
    return PlannedRoute(
        prefix=prefix,
        family=4,
        source_ips=1,
        unique_domains=1,
        unique_resolvers=1,
        source_count=1,
        source_trust=100,
        confidence=100,
        publish_score=100,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def rebuild_route_stats(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> int:
        self.calls.append(
            (
                ipv4_prefix,
                ipv6_prefix,
            )
        )
        return 91

    def list_route_stats(self) -> list[object]:
        return []


class FakePlanner:
    def __init__(
        self,
        routes: list[PlannedRoute] | None = None,
    ) -> None:
        self.routes = (
            routes
            if routes is not None
            else [make_route()]
        )
        self.calls = 0

    def build_plan(self) -> list[PlannedRoute]:
        self.calls += 1
        return self.routes


@dataclass(slots=True)
class FakeExportResult:
    path: Path
    changed: bool


class FakeExporter:
    def __init__(
        self,
        *,
        changed: bool = True,
    ) -> None:
        self.changed = changed
        self.routes: list[PlannedRoute] = []

    def export(
        self,
        routes: list[PlannedRoute],
    ) -> FakeExportResult:
        self.routes = routes
        return FakeExportResult(
            path=Path("bird/routecollector.conf"),
            changed=self.changed,
        )


@dataclass(slots=True)
class FakeInstallResult:
    path: Path
    backup_path: Path | None
    changed: bool


class FakeInstaller:
    def __init__(
        self,
        *,
        changed: bool = True,
    ) -> None:
        self.changed = changed
        self.rollback_calls: list[Path | None] = []
        self.removed_backups: list[Path | None] = []

    def install(self) -> FakeInstallResult:
        return FakeInstallResult(
            path=Path(
                "/etc/bird/routecollector.conf"
            ),
            backup_path=(
                Path(
                    "/etc/bird/routecollector.conf.bak"
                )
                if self.changed
                else None
            ),
            changed=self.changed,
        )

    def rollback(
        self,
        backup_path: Path | None,
    ) -> None:
        self.rollback_calls.append(
            backup_path
        )

    def remove_backup(
        self,
        backup_path: Path | None,
    ) -> None:
        self.removed_backups.append(
            backup_path
        )


class FakeBird:
    def __init__(
        self,
        *,
        fail_check: bool = False,
        fail_reload: bool = False,
        fail_rollback_check: bool = False,
    ) -> None:
        self.fail_check = fail_check
        self.fail_reload = fail_reload
        self.fail_rollback_check = (
            fail_rollback_check
        )
        self.check_calls = 0
        self.reload_calls = 0

    def configure_check(self) -> str:
        self.check_calls += 1

        if (
            self.check_calls > 1
            and self.fail_rollback_check
        ):
            raise BirdControlError(
                "rollback check failed"
            )

        if self.check_calls == 1 and self.fail_check:
            raise BirdControlError(
                "configuration rejected"
            )

        return "Configuration OK"

    def configure(self) -> str:
        self.reload_calls += 1

        if self.reload_calls == 1 and self.fail_reload:
            raise BirdControlError(
                "reload failed"
            )

        return "Reconfigured"


def build_publisher(
    *,
    repository: FakeRepository | None = None,
    planner: FakePlanner | None = None,
    exporter: FakeExporter | None = None,
    installer: FakeInstaller | None = None,
    bird: FakeBird | None = None,
) -> tuple[
    DynamicPublisher,
    FakeRepository,
    FakePlanner,
    FakeExporter,
    FakeInstaller,
    FakeBird,
]:
    repository = repository or FakeRepository()
    planner = planner or FakePlanner()
    exporter = exporter or FakeExporter()
    installer = installer or FakeInstaller()
    bird = bird or FakeBird()

    publisher = DynamicPublisher(
        repository,
        generated_config=Path(
            "bird/routecollector.conf"
        ),
        installed_config=Path(
            "/etc/bird/routecollector.conf"
        ),
        main_bird_config=Path(
            "/etc/bird/bird.conf"
        ),
        planner=planner,
        exporter=exporter,
        installer=installer,
        bird=bird,
    )

    return (
        publisher,
        repository,
        planner,
        exporter,
        installer,
        bird,
    )


def test_publish_rebuilds_and_reloads_changed_config() -> None:
    (
        publisher,
        repository,
        planner,
        exporter,
        installer,
        bird,
    ) = build_publisher()

    result = publisher.publish()

    assert repository.calls == [(24, 48)]
    assert planner.calls == 1
    assert exporter.routes == [make_route()]
    assert bird.check_calls == 1
    assert bird.reload_calls == 1

    assert result.route_stats_built == 91
    assert result.planned_routes == 1
    assert result.generated_changed is True
    assert result.installed_changed is True
    assert result.bird_checked is True
    assert result.bird_reloaded is True
    assert result.rollback_performed is False

    assert installer.removed_backups == [
        Path(
            "/etc/bird/routecollector.conf.bak"
        )
    ]


def test_publish_skips_reload_when_config_unchanged() -> None:
    installer = FakeInstaller(
        changed=False
    )

    (
        publisher,
        _,
        _,
        _,
        _,
        bird,
    ) = build_publisher(
        installer=installer
    )

    result = publisher.publish()

    assert bird.check_calls == 1
    assert bird.reload_calls == 0
    assert result.installed_changed is False
    assert result.bird_reloaded is False
    assert installer.removed_backups == [None]


def test_publish_rejects_empty_route_plan() -> None:
    planner = FakePlanner(routes=[])

    publisher, *_ = build_publisher(
        planner=planner
    )

    with pytest.raises(
        DynamicPublishError,
        match="route plan is empty",
    ):
        publisher.publish()


def test_publish_rolls_back_rejected_configuration() -> None:
    installer = FakeInstaller(
        changed=True
    )
    bird = FakeBird(
        fail_check=True
    )

    publisher, *_ = build_publisher(
        installer=installer,
        bird=bird,
    )

    with pytest.raises(
        DynamicPublishError,
        match="rollback completed",
    ):
        publisher.publish()

    assert installer.rollback_calls == [
        Path(
            "/etc/bird/routecollector.conf.bak"
        )
    ]
    assert bird.check_calls == 2
    assert bird.reload_calls == 1


def test_publish_rolls_back_failed_reload() -> None:
    installer = FakeInstaller(
        changed=True
    )
    bird = FakeBird(
        fail_reload=True
    )

    publisher, *_ = build_publisher(
        installer=installer,
        bird=bird,
    )

    with pytest.raises(
        DynamicPublishError,
        match="rollback completed",
    ):
        publisher.publish()

    assert len(
        installer.rollback_calls
    ) == 1
    assert bird.check_calls == 2
    assert bird.reload_calls == 2


def test_publish_reports_failed_rollback() -> None:
    installer = FakeInstaller(
        changed=True
    )
    bird = FakeBird(
        fail_check=True,
        fail_rollback_check=True,
    )

    publisher, *_ = build_publisher(
        installer=installer,
        bird=bird,
    )

    with pytest.raises(
        DynamicPublishError,
        match="rollback could not be applied",
    ):
        publisher.publish()


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("min_confidence_ipv4", -1),
        ("min_confidence_ipv4", 101),
        ("min_confidence_ipv6", -1),
        ("min_confidence_ipv6", 101),
        ("max_age_days", 0),
        ("ipv4_prefix", 33),
        ("ipv6_prefix", 129),
    ],
)
def test_publisher_rejects_invalid_options(
    keyword: str,
    value: int,
) -> None:
    arguments: dict[str, Any] = {
        "generated_config": Path(
            "bird/routecollector.conf"
        ),
        "installed_config": Path(
            "/etc/bird/routecollector.conf"
        ),
        "main_bird_config": Path(
            "/etc/bird/bird.conf"
        ),
        keyword: value,
    }

    with pytest.raises(ValueError):
        DynamicPublisher(
            FakeRepository(),
            **arguments,
        )
