"""
Tests for the single-run RouteCollector workflow.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import routecollector.workflow.run_once as workflow_module
from routecollector.core.database import Database
from routecollector.exporter.birdctl import BirdControlError
from routecollector.history.cycle_history import CycleHistoryStore
from routecollector.workflow.run_once import (
    RunOnceError,
    RunOnceWorkflow,
)


class FakeRepository:
    """Minimal repository used by workflow tests."""

    def rebuild_route_stats(self) -> int:
        """Return a predefined number of route statistics."""

        return 3


class FakeServiceSourceSync:
    """Fake service source synchronization."""

    def __init__(self, **_: Any) -> None:
        pass

    def sync(self) -> SimpleNamespace:
        """Return synchronized service and domain counts."""

        return SimpleNamespace(
            service_count=1,
            domain_count=189,
            services=(),
        )


class FakeDnsResolver:
    """Fake DNS resolver."""

    def __init__(
        self,
        _: Any,
        **kwargs: Any,
    ) -> None:
        assert kwargs.get("enable_ipv6") is False

    def resolve_all(
        self,
        service_name: str | None,
    ) -> tuple[int, int]:
        """Return resolved domain and observation counts."""

        assert service_name == "youtube"
        return 189, 2800


class FakeRoutePlanner:
    """Fake route planner."""

    def __init__(self, **_: Any) -> None:
        pass

    def build_plan(self) -> list[SimpleNamespace]:
        """Return a non-empty route plan."""

        return [
            SimpleNamespace(
                prefix="192.0.2.0/24",
                family=4,
                source_ips=5,
                unique_domains=4,
                unique_resolvers=2,
                source_count=2,
                source_trust=100,
                confidence=80,
                publish_score=95,
            )
        ]


def patch_common_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patch workflow components unrelated to BIRD state."""

    monkeypatch.setattr(
        workflow_module,
        "ServiceSourceSync",
        FakeServiceSourceSync,
    )
    monkeypatch.setattr(
        workflow_module,
        "DnsResolver",
        FakeDnsResolver,
    )
    monkeypatch.setattr(
        workflow_module,
        "RoutePlanner",
        FakeRoutePlanner,
    )


def build_workflow(
    tmp_path: Path,
) -> tuple[RunOnceWorkflow, Database]:
    """Create a workflow with temporary paths."""

    database = Database(tmp_path / "state.db")
    database.initialize()

    workflow = RunOnceWorkflow(
        repository=FakeRepository(),  # type: ignore[arg-type]
        database=database,
        services_dir=tmp_path / "services",
        generated_config=tmp_path / "generated.conf",
        installed_config=tmp_path / "installed.conf",
        main_bird_config=tmp_path / "bird.conf",
        snapshot_directory=tmp_path / "plans",
        dry_run_config=tmp_path / "dry-run" / "routecollector.conf",
    )

    return workflow, database


def snapshot_paths(
    tmp_path: Path,
) -> list[Path]:
    """Return all stored test snapshots."""

    return list(
        (tmp_path / "plans").glob("*.json")
    )


def test_run_once_skips_reload_when_config_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unchanged BIRD config must not trigger configure reload."""

    patch_common_components(monkeypatch)

    class FakeExporter:
        def __init__(self, output_file: Path) -> None:
            self._output_file = output_file

        def export(
            self,
            routes: list[Any],
        ) -> SimpleNamespace:
            assert len(routes) == 1

            return SimpleNamespace(
                path=self._output_file,
                changed=False,
            )

    class FakeInstaller:
        def __init__(self, **_: Any) -> None:
            pass

        def install(self) -> SimpleNamespace:
            return SimpleNamespace(
                path=tmp_path / "installed.conf",
                changed=False,
                backup_path=None,
            )

        def remove_backup(
            self,
            _: Path | None,
        ) -> None:
            pass

    class FakeBirdControl:
        configure_calls = 0

        def configure_check(self) -> str:
            return "Configuration OK"

        def configure(self) -> str:
            type(self).configure_calls += 1
            return "Reconfigured"

    monkeypatch.setattr(
        workflow_module,
        "BirdExporter",
        FakeExporter,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdConfigInstaller",
        FakeInstaller,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdControl",
        FakeBirdControl,
    )

    workflow, database = build_workflow(tmp_path)
    result = workflow.run("youtube")

    assert result.generated_changed is False
    assert result.installed_changed is False
    assert result.bird_reloaded is False
    assert result.rollback_performed is False
    assert result.bird_reload_output is None
    assert result.routes_added == 0
    assert result.routes_removed == 0
    assert result.duration_seconds >= 0
    assert FakeBirdControl.configure_calls == 0
    assert len(snapshot_paths(tmp_path)) == 1

    history = CycleHistoryStore(database).latest()
    assert history is not None
    assert history.service_name == "youtube"
    assert history.planned_routes == 1
    assert history.routes_added == 0
    assert history.routes_removed == 0
    assert history.bird_reloaded is False


def test_run_once_reloads_bird_when_config_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changed BIRD config must be checked and reloaded."""

    patch_common_components(monkeypatch)

    backup_path = tmp_path / "installed.conf.bak"

    class FakeExporter:
        def __init__(self, output_file: Path) -> None:
            self._output_file = output_file

        def export(
            self,
            routes: list[Any],
        ) -> SimpleNamespace:
            assert len(routes) == 1

            return SimpleNamespace(
                path=self._output_file,
                changed=True,
            )

    class FakeInstaller:
        backup_removed = False
        rollback_called = False

        def __init__(self, **_: Any) -> None:
            pass

        def install(self) -> SimpleNamespace:
            return SimpleNamespace(
                path=tmp_path / "installed.conf",
                changed=True,
                backup_path=backup_path,
            )

        def remove_backup(
            self,
            path: Path | None,
        ) -> None:
            assert path == backup_path
            type(self).backup_removed = True

        def rollback(
            self,
            _: Path | None,
        ) -> None:
            type(self).rollback_called = True

    class FakeBirdControl:
        def configure_check(self) -> str:
            return "Configuration OK"

        def configure(self) -> str:
            return "Reconfigured"

    monkeypatch.setattr(
        workflow_module,
        "BirdExporter",
        FakeExporter,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdConfigInstaller",
        FakeInstaller,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdControl",
        FakeBirdControl,
    )

    workflow, database = build_workflow(tmp_path)
    result = workflow.run("youtube")

    assert result.generated_changed is True
    assert result.installed_changed is True
    assert result.bird_reloaded is True
    assert result.rollback_performed is False
    assert result.bird_reload_output == "Reconfigured"
    assert FakeInstaller.backup_removed is True
    assert FakeInstaller.rollback_called is False
    assert len(snapshot_paths(tmp_path)) == 1

    history = CycleHistoryStore(database).latest()
    assert history is not None
    assert history.bird_reloaded is True
    assert history.generated_changed is True
    assert history.installed_changed is True


def test_run_once_rolls_back_when_bird_reload_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed BIRD reload must restore previous config."""

    patch_common_components(monkeypatch)

    backup_path = tmp_path / "installed.conf.bak"

    class FakeExporter:
        def __init__(self, output_file: Path) -> None:
            self._output_file = output_file

        def export(
            self,
            routes: list[Any],
        ) -> SimpleNamespace:
            return SimpleNamespace(
                path=self._output_file,
                changed=True,
            )

    class FakeInstaller:
        rollback_called = False
        backup_removed = False

        def __init__(self, **_: Any) -> None:
            pass

        def install(self) -> SimpleNamespace:
            return SimpleNamespace(
                path=tmp_path / "installed.conf",
                changed=True,
                backup_path=backup_path,
            )

        def rollback(
            self,
            path: Path | None,
        ) -> None:
            assert path == backup_path
            type(self).rollback_called = True

        def remove_backup(
            self,
            _: Path | None,
        ) -> None:
            type(self).backup_removed = True

    class FakeBirdControl:
        configure_calls = 0
        check_calls = 0

        def configure_check(self) -> str:
            type(self).check_calls += 1
            return "Configuration OK"

        def configure(self) -> str:
            type(self).configure_calls += 1

            if type(self).configure_calls == 1:
                raise BirdControlError("Reload failed")

            return "Rollback configuration applied"

    monkeypatch.setattr(
        workflow_module,
        "BirdExporter",
        FakeExporter,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdConfigInstaller",
        FakeInstaller,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdControl",
        FakeBirdControl,
    )

    workflow, database = build_workflow(tmp_path)

    with pytest.raises(
        RunOnceError,
        match="rollback completed",
    ):
        workflow.run("youtube")

    assert FakeInstaller.rollback_called is True
    assert FakeInstaller.backup_removed is False
    assert FakeBirdControl.configure_calls == 2
    assert FakeBirdControl.check_calls == 2
    assert snapshot_paths(tmp_path) == []
    assert CycleHistoryStore(database).count() == 0


def test_run_once_rejects_empty_route_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty plan must never replace active BIRD config."""

    patch_common_components(monkeypatch)

    class EmptyRoutePlanner:
        def __init__(self, **_: Any) -> None:
            pass

        def build_plan(self) -> list[Any]:
            return []

    monkeypatch.setattr(
        workflow_module,
        "RoutePlanner",
        EmptyRoutePlanner,
    )

    workflow, database = build_workflow(tmp_path)

    with pytest.raises(
        RunOnceError,
        match="Route plan is empty",
    ):
        workflow.run("youtube")

    assert snapshot_paths(tmp_path) == []
    assert CycleHistoryStore(database).count() == 0


def test_run_once_dry_run_does_not_publish_or_store_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry run must not install BIRD config or persist history."""

    patch_common_components(monkeypatch)

    class FakeExporter:
        def __init__(self, output_file: Path) -> None:
            self._output_file = output_file

        def export(
            self,
            routes: list[Any],
        ) -> SimpleNamespace:
            assert len(routes) == 1
            self._output_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            self._output_file.write_text(
                "preview",
                encoding="utf-8",
            )
            return SimpleNamespace(
                path=self._output_file,
                changed=True,
            )

    class ForbiddenInstaller:
        def __init__(self, **_: Any) -> None:
            raise AssertionError(
                "Dry run must not construct BirdConfigInstaller"
            )

    class ForbiddenBirdControl:
        def __init__(self) -> None:
            raise AssertionError(
                "Dry run must not construct BirdControl"
            )

    monkeypatch.setattr(
        workflow_module,
        "BirdExporter",
        FakeExporter,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdConfigInstaller",
        ForbiddenInstaller,
    )
    monkeypatch.setattr(
        workflow_module,
        "BirdControl",
        ForbiddenBirdControl,
    )

    workflow, database = build_workflow(tmp_path)
    result = workflow.run(
        "youtube",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.generated_config == (
        tmp_path / "dry-run" / "routecollector.conf"
    )
    assert result.generated_changed is True
    assert result.installed_config is None
    assert result.installed_changed is False
    assert result.bird_reloaded is False
    assert result.routes_added == 0
    assert result.routes_removed == 0
    assert snapshot_paths(tmp_path) == []
    assert CycleHistoryStore(database).count() == 0
