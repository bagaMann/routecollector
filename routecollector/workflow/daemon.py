"""
RouteCollector daemon workflow.
"""

from __future__ import annotations

import fcntl
import logging
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Callable

from routecollector.workflow.run_once import RunOnceResult, RunOnceWorkflow


class DaemonError(RuntimeError):
    """RouteCollector daemon error."""


@dataclass(slots=True, frozen=True)
class DaemonConfig:
    """Daemon runtime configuration."""

    interval_seconds: int
    lock_file: Path
    service_name: str | None = None


class RouteCollectorDaemon:
    """Run RouteCollector workflow periodically."""

    def __init__(
        self,
        workflow: RunOnceWorkflow,
        config: DaemonConfig,
        logger: logging.Logger,
        sleep_function: Callable[[float], None] = time.sleep,
    ) -> None:
        if config.interval_seconds <= 0:
            raise ValueError("Daemon interval must be greater than zero")

        self._workflow = workflow
        self._config = config
        self._logger = logger
        self._sleep = sleep_function
        self._stopping = False
        self._lock_handle: object | None = None

    def run(self) -> None:
        """Run daemon until SIGTERM or SIGINT is received."""

        self._acquire_lock()
        self._install_signal_handlers()

        self._logger.info(
            "RouteCollector daemon started with interval=%s seconds",
            self._config.interval_seconds,
        )

        try:
            while not self._stopping:
                self._run_cycle()

                if self._stopping:
                    break

                self._sleep_interruptibly(self._config.interval_seconds)
        finally:
            self._release_lock()
            self._logger.info("RouteCollector daemon stopped")

    def stop(self) -> None:
        """Request graceful daemon shutdown."""

        self._stopping = True

    def _run_cycle(self) -> None:
        """Execute one workflow cycle and log its result."""

        try:
            result = self._workflow.run(self._config.service_name)
        except Exception:
            self._logger.exception("RouteCollector cycle failed")
            return

        self._log_result(result)

    def _log_result(self, result: RunOnceResult) -> None:
        """Log workflow result."""

        self._logger.info(
            (
                "Cycle completed: services=%s domains=%s resolved=%s "
                "observations=%s route_stats=%s routes=%s "
                "generated_changed=%s installed_changed=%s "
                "bird_reloaded=%s rollback=%s"
            ),
            result.services_synced,
            result.domains_synced,
            result.domains_resolved,
            result.observations_stored,
            result.route_stats_built,
            result.planned_routes,
            result.generated_changed,
            result.installed_changed,
            result.bird_reloaded,
            result.rollback_performed,
        )

    def _sleep_interruptibly(self, seconds: int) -> None:
        """Sleep in short intervals so shutdown remains responsive."""

        remaining = seconds

        while remaining > 0 and not self._stopping:
            sleep_time = min(remaining, 1)
            self._sleep(sleep_time)
            remaining -= sleep_time

    def _install_signal_handlers(self) -> None:
        """Install graceful shutdown signal handlers."""

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(
        self,
        signum: int,
        frame: FrameType | None,
    ) -> None:
        """Handle process termination signal."""

        del frame

        self._logger.info("Received signal %s, stopping daemon", signum)
        self.stop()

    def _acquire_lock(self) -> None:
        """Acquire exclusive daemon process lock."""

        self._config.lock_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        lock_handle = self._config.lock_file.open(
            "a+",
            encoding="utf-8",
        )

        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            lock_handle.close()

            raise DaemonError(
                "Another RouteCollector daemon instance is already running"
            ) from exc

        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write(f"{self._get_process_id()}\n")
        lock_handle.flush()

        self._lock_handle = lock_handle

    def _release_lock(self) -> None:
        """Release daemon process lock."""

        if self._lock_handle is None:
            return

        lock_handle = self._lock_handle

        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_UN,
            )
        finally:
            lock_handle.close()
            self._lock_handle = None
            self._config.lock_file.unlink(missing_ok=True)

    @staticmethod
    def _get_process_id() -> int:
        """Return current process ID."""

        import os

        return os.getpid()
