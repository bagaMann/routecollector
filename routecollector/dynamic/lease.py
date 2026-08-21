"""
Persistent leases for routes published through the dynamic DNS fast path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Callable, Iterable, Protocol

from routecollector.dynamic.publisher import DynamicPublishResult
from routecollector.dynamic.route_cache import DynamicRouteCache


class DynamicLeaseError(RuntimeError):
    """Dynamic route lease state is invalid or cannot be persisted."""


@dataclass(slots=True, frozen=True)
class DynamicRouteLease:
    """One leased dynamic route prefix."""

    prefix: str
    expires_at: datetime


class DynamicLeasePublisher(Protocol):
    """Publisher interface used by lease reconciliation."""

    def publish(
        self,
        required_prefixes: Iterable[str] = (),
    ) -> DynamicPublishResult:
        """Publish the normal plan plus active dynamic prefixes."""


class DynamicRouteLeaseStore:
    """Persist dynamic fast-route leases in one JSON state file."""

    def __init__(
        self,
        path: Path,
        *,
        lease_seconds: int = 86400,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError(
                "Dynamic route lease must be greater than zero"
            )

        self._path = path
        self._lease_seconds = lease_seconds
        self._now = now or datetime.now
        self._lock = RLock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def lease_seconds(self) -> int:
        return self._lease_seconds

    def renew(
        self,
        prefixes: Iterable[str],
    ) -> tuple[DynamicRouteLease, ...]:
        """Create or extend leases for published dynamic prefixes."""

        normalized = tuple(
            sorted(
                {
                    self._normalize_prefix(prefix)
                    for prefix in prefixes
                }
            )
        )

        if not normalized:
            return ()

        with self._lock:
            data = self._load_unlocked()
            expires_at = (
                self._now()
                + timedelta(
                    seconds=self._lease_seconds
                )
            )

            for prefix in normalized:
                data[prefix] = expires_at.isoformat()

            self._save_unlocked(data)

        return tuple(
            DynamicRouteLease(
                prefix=prefix,
                expires_at=expires_at,
            )
            for prefix in normalized
        )

    def active_prefixes(
        self,
    ) -> tuple[str, ...]:
        """Return prefixes whose leases have not expired."""

        now = self._now()

        with self._lock:
            data = self._load_unlocked()

        return tuple(
            sorted(
                prefix
                for prefix, value in data.items()
                if self._parse_expiry(
                    prefix,
                    value,
                ) > now
            )
        )

    def expired_prefixes(
        self,
    ) -> tuple[str, ...]:
        """Return prefixes whose leases have expired."""

        now = self._now()

        with self._lock:
            data = self._load_unlocked()

        return tuple(
            sorted(
                prefix
                for prefix, value in data.items()
                if self._parse_expiry(
                    prefix,
                    value,
                ) <= now
            )
        )

    def leases(
        self,
    ) -> tuple[DynamicRouteLease, ...]:
        """Return all persisted leases."""

        with self._lock:
            data = self._load_unlocked()

        return tuple(
            sorted(
                (
                    DynamicRouteLease(
                        prefix=prefix,
                        expires_at=self._parse_expiry(
                            prefix,
                            value,
                        ),
                    )
                    for prefix, value in data.items()
                ),
                key=lambda lease: lease.prefix,
            )
        )

    def remove(
        self,
        prefixes: Iterable[str],
    ) -> int:
        """Remove leases and return the number actually deleted."""

        normalized = {
            self._normalize_prefix(prefix)
            for prefix in prefixes
        }

        if not normalized:
            return 0

        with self._lock:
            data = self._load_unlocked()
            before = len(data)

            for prefix in normalized:
                data.pop(prefix, None)

            removed = before - len(data)

            if removed:
                self._save_unlocked(data)

        return removed

    def remove_expired(
        self,
        prefixes: Iterable[str],
    ) -> tuple[str, ...]:
        """Remove only candidate leases that are still expired.

        A lease may be renewed by a DNS request while cleanup is publishing
        the reduced route plan. Rechecking expiry under the store lock avoids
        deleting that freshly renewed lease.
        """

        normalized = {
            self._normalize_prefix(prefix)
            for prefix in prefixes
        }

        if not normalized:
            return ()

        now = self._now()

        with self._lock:
            data = self._load_unlocked()
            removed: list[str] = []

            for prefix in sorted(normalized):
                value = data.get(prefix)

                if value is None:
                    continue

                if self._parse_expiry(prefix, value) <= now:
                    data.pop(prefix, None)
                    removed.append(prefix)

            if removed:
                self._save_unlocked(data)

        return tuple(removed)

    def _load_unlocked(self) -> dict[str, str]:
        if not self._path.exists():
            return {}

        try:
            payload = json.loads(
                self._path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise DynamicLeaseError(
                f"Cannot read dynamic route leases: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise DynamicLeaseError(
                "Dynamic route lease file must contain an object"
            )

        normalized: dict[str, str] = {}

        for prefix, value in payload.items():
            if not isinstance(prefix, str):
                raise DynamicLeaseError(
                    "Dynamic route lease prefix must be a string"
                )

            if not isinstance(value, str):
                raise DynamicLeaseError(
                    "Dynamic route lease expiry must be a string"
                )

            normalized[
                self._normalize_prefix(prefix)
            ] = value

            self._parse_expiry(
                prefix,
                value,
            )

        return normalized

    def _save_unlocked(
        self,
        data: dict[str, str],
    ) -> None:
        try:
            self._path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary = self._path.with_suffix(
                self._path.suffix + ".tmp"
            )

            temporary.write_text(
                json.dumps(
                    dict(sorted(data.items())),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            temporary.replace(self._path)

        except OSError as exc:
            raise DynamicLeaseError(
                f"Cannot write dynamic route leases: {exc}"
            ) from exc

    @staticmethod
    def _normalize_prefix(
        prefix: str,
    ) -> str:
        from ipaddress import ip_network

        return str(
            ip_network(
                prefix,
                strict=False,
            )
        )

    @staticmethod
    def _parse_expiry(
        prefix: str,
        value: str,
    ) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise DynamicLeaseError(
                "Invalid dynamic route lease expiry "
                f"for {prefix}: {value}"
            ) from exc


class DynamicLeaseManager:
    """Remove expired fast routes while retaining active leases."""

    def __init__(
        self,
        *,
        store: DynamicRouteLeaseStore,
        publisher: DynamicLeasePublisher,
        route_cache: DynamicRouteCache,
        interval_seconds: float = 60.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError(
                "Dynamic lease check interval must be positive"
            )

        self._store = store
        self._publisher = publisher
        self._route_cache = route_cache
        self._interval_seconds = interval_seconds
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
        )

    def start(self) -> None:
        """Start lease expiry checks."""

        if self.running:
            return

        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="routecollector-dynamic-leases",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop lease expiry checks."""

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(
                timeout=max(
                    self._interval_seconds * 2,
                    1.0,
                )
            )

        self._thread = None

    def reconcile_once(
        self,
    ) -> DynamicPublishResult | None:
        """Republish active leases when at least one lease expired."""

        expired = self._store.expired_prefixes()

        if not expired:
            return None

        active = self._store.active_prefixes()

        result = self._publisher.publish(
            active
        )

        # Remove candidates from the cache before the final expiry check.
        # If DNS renews one concurrently, remove_expired() will preserve its
        # lease and the prefix is added back to the cache below.
        self._route_cache.discard(expired)

        removed_expired = set(
            self._store.remove_expired(expired)
        )
        renewed_during_cleanup = (
            set(expired) - removed_expired
        )

        self._route_cache.add(
            renewed_during_cleanup
        )

        self._store.remove(
            result.dynamic_rejected_prefixes
        )
        self._route_cache.discard(
            result.dynamic_rejected_prefixes
        )
        self._route_cache.add(
            result.dynamic_published_prefixes
        )

        return result

    def _run(self) -> None:
        while not self._stop_event.wait(
            self._interval_seconds
        ):
            self.reconcile_once()
