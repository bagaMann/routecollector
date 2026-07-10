"""
Tests for the single-run RouteCollector workflow.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import routecollector.workflow.run_once as workflow_module
from routecollector.exporter.birdctl import BirdControlError
from routecollector.workflow.run_once import RunOnceError, RunOnceWorkflow


class FakeRepository:
    """Minimal repository used by workflow tests."""

    def rebuild_route_stats(self) -> int:
        """Return a predefined number of route statistics."""

        return 3


class FakeServiceConfigSync:
    """Fake service configuration synchronization."""

    def __init__(self, **_: Any) -> None:
        pass

    def sync(self) -> tuple[int, int]:
        """Return synchronized service and domain counts."""

        return 1, 189


class FakeDnsResolver:
    """Fake DNS resolver."""

    def __init__(self, _: Any) -> None:
        pass

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
                confidence=20,
            )
        ]


def patch_common_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patch workflow components unrelated to BIRD state."""

    monkeypatch.setattr(
        workflow_module,
        "ServiceConfigSync",
        FakeServiceConfigSync,
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


def build_workflow(tmp_path: Path) -> RunOnceWorkflow:
    """Create a workflow with temporary paths."""

    return RunOnceWorkflow(
        repository=FakeRepository(),  # type: ignore[arg-type]
        services_dir=tmp_path / "services",
        generated_config=tmp_path / "generated.conf",
        installed_config=tmp_path / "installed.conf",
        main_bird_config=tmp_path / "bird.conf",
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

        def export(self, routes: list[Any]) -> SimpleNamespace:
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

    class FakeBirdControl:
        configure_calls = 0

        def configure_check(self) -> str:
            return "Configuration OK"

        def configure(self) -> str:
            type(self).configure_calls += 1
            return "Reconfigured"

    monkeypatch.setattr(workflow_module, "BirdExporter", FakeExporter)
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

    result = build_workflow(tmp_path).run("youtube")

    assert result.generated_changed is False
    assert result.installed_changed is False
    assert result.bird_reloaded is False
    assert result.rollback_performed is False
    assert result.bird_reload_output is None
    assert FakeBirdControl.configure_calls == 0


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

        def export(self, routes: list[Any]) -> SimpleNamespace:
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

        def remove_backup(self, path: Path | None) -> None:
            assert path == backup_path
            type(self).backup_removed = True

        def rollback(self, _: Path | None) -> None:
            type(self).rollback_called = True

    class FakeBirdControl:
        def configure_check(self) -> str:
            return "Configuration OK"

        def configure(self) -> str:
            return "Reconfigured"

    monkeypatch.setattr(workflow_module, "BirdExporter", FakeExporter)
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

    result = build_workflow(tmp_path).run("youtube")

    assert result.generated_changed is True
    assert result.installed_changed is True
    assert result.bird_reloaded is True
    assert result.rollback_performed is False
    assert result.bird_reload_output == "Reconfigured"
    assert FakeInstaller.backup_removed is True
    assert FakeInstaller.rollback_called is False


def test_run_once_rolls_back_when_bird_reload_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed BIRD reload must restore and apply the previous config."""

    patch_common_components(monkeypatch)

    backup_path = tmp_path / "installed.conf.bak"

    class FakeExporter:
        def __init__(self, output_file: Path) -> None:
            self._output_file = output_file

        def export(self, routes: list[Any]) -> SimpleNamespace:
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

        def rollback(self, path: Path | None) -> None:
            assert path == backup_path
            type(self).rollback_called = True

        def remove_backup(self, _: Path | None) -> None:
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

    monkeypatch.setattr(workflow_module, "BirdExporter", FakeExporter)
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

    with pytest.raises(
        RunOnceError,
        match="rollback completed",
    ):
        build_workflow(tmp_path).run("youtube")

    assert FakeInstaller.rollback_called is True
    assert FakeInstaller.backup_removed is False
    assert FakeBirdControl.configure_calls == 2
    assert FakeBirdControl.check_calls == 2


def test_run_once_rejects_empty_route_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty plan must never replace the active BIRD config."""

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

    with pytest.raises(
        RunOnceError,
        match="Route plan is empty",
    ):
        build_workflow(tmp_path).run("youtube")
