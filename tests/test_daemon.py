"""
Tests for RouteCollector daemon workflow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from routecollector.workflow.daemon import (
    DaemonConfig,
    DaemonError,
    RouteCollectorDaemon,
)


class FakeWorkflow:
    """Workflow stub used by daemon tests."""

    def __init__(
        self,
        results: list[Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls = 0

    def run(self, service_name: str | None = None) -> Any:
        """Return predefined result or raise predefined error."""

        self.calls += 1

        if self.error is not None:
            raise self.error

        if self.results:
            return self.results.pop(0)

        return SimpleNamespace(
            services_synced=1,
            domains_synced=10,
            domains_resolved=10,
            observations_stored=100,
            route_stats_built=5,
            planned_routes=4,
            generated_changed=False,
            installed_changed=False,
            bird_reloaded=False,
            rollback_performed=False,
        )


def build_logger() -> logging.Logger:
    """Create isolated test logger."""

    logger = logging.getLogger("routecollector.tests.daemon")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(logging.NullHandler())

    return logger


def test_daemon_rejects_non_positive_interval(tmp_path: Path) -> None:
    """Daemon interval must be greater than zero."""

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        RouteCollectorDaemon(
            workflow=FakeWorkflow(),  # type: ignore[arg-type]
            config=DaemonConfig(
                interval_seconds=0,
                lock_file=tmp_path / "daemon.lock",
            ),
            logger=build_logger(),
        )


def test_daemon_runs_cycle_and_can_stop(tmp_path: Path) -> None:
    """Daemon must execute a cycle and stop cleanly."""

    workflow = FakeWorkflow()
    daemon: RouteCollectorDaemon

    def fake_sleep(_: float) -> None:
        daemon.stop()

    daemon = RouteCollectorDaemon(
        workflow=workflow,  # type: ignore[arg-type]
        config=DaemonConfig(
            interval_seconds=10,
            lock_file=tmp_path / "daemon.lock",
            service_name="youtube",
        ),
        logger=build_logger(),
        sleep_function=fake_sleep,
    )

    daemon.run()

    assert workflow.calls == 1
    assert not (tmp_path / "daemon.lock").exists()


def test_daemon_continues_after_cycle_failure(tmp_path: Path) -> None:
    """A failed workflow cycle must not crash the daemon loop."""

    workflow = FakeWorkflow(error=RuntimeError("cycle failed"))
    daemon: RouteCollectorDaemon
    sleep_calls = 0

    def fake_sleep(_: float) -> None:
        nonlocal sleep_calls

        sleep_calls += 1
        daemon.stop()

    daemon = RouteCollectorDaemon(
        workflow=workflow,  # type: ignore[arg-type]
        config=DaemonConfig(
            interval_seconds=5,
            lock_file=tmp_path / "daemon.lock",
        ),
        logger=build_logger(),
        sleep_function=fake_sleep,
    )

    daemon.run()

    assert workflow.calls == 1
    assert sleep_calls == 1
    assert not (tmp_path / "daemon.lock").exists()


def test_daemon_prevents_second_instance(tmp_path: Path) -> None:
    """Second daemon instance must fail to acquire the same lock."""

    lock_file = tmp_path / "daemon.lock"

    first = RouteCollectorDaemon(
        workflow=FakeWorkflow(),  # type: ignore[arg-type]
        config=DaemonConfig(
            interval_seconds=10,
            lock_file=lock_file,
        ),
        logger=build_logger(),
    )

    second = RouteCollectorDaemon(
        workflow=FakeWorkflow(),  # type: ignore[arg-type]
        config=DaemonConfig(
            interval_seconds=10,
            lock_file=lock_file,
        ),
        logger=build_logger(),
    )

    first._acquire_lock()

    try:
        with pytest.raises(
            DaemonError,
            match="already running",
        ):
            second._acquire_lock()
    finally:
        first._release_lock()

    assert not lock_file.exists()


def test_daemon_stop_sets_shutdown_flag(tmp_path: Path) -> None:
    """stop() must request daemon shutdown."""

    daemon = RouteCollectorDaemon(
        workflow=FakeWorkflow(),  # type: ignore[arg-type]
        config=DaemonConfig(
            interval_seconds=10,
            lock_file=tmp_path / "daemon.lock",
        ),
        logger=build_logger(),
    )

    assert daemon._stopping is False

    daemon.stop()

    assert daemon._stopping is True
