"""
Route plan snapshot storage and comparison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Iterable

from routecollector.planner.planner import PlannedRoute


class PlanSnapshotError(RuntimeError):
    """Route plan snapshot error."""


@dataclass(slots=True, frozen=True)
class SnapshotRoute:
    """Serializable route stored in a plan snapshot."""

    prefix: str
    family: int
    source_ips: int
    unique_domains: int
    unique_resolvers: int
    source_count: int
    source_trust: int
    confidence: int
    publish_score: int

    @classmethod
    def from_planned_route(
        cls,
        route: PlannedRoute,
    ) -> SnapshotRoute:
        """Build snapshot route from planner output."""

        return cls(
            prefix=route.prefix,
            family=route.family,
            source_ips=route.source_ips,
            unique_domains=route.unique_domains,
            unique_resolvers=route.unique_resolvers,
            source_count=route.source_count,
            source_trust=route.source_trust,
            confidence=route.confidence,
            publish_score=route.publish_score,
        )


@dataclass(slots=True, frozen=True)
class PlanSnapshot:
    """Stored route plan state."""

    created_at: str
    routes: tuple[SnapshotRoute, ...]

    @property
    def route_count(self) -> int:
        """Return number of routes in snapshot."""

        return len(self.routes)


@dataclass(slots=True, frozen=True)
class PlanChanges:
    """Difference between two route plan snapshots."""

    previous_count: int
    current_count: int
    added: tuple[SnapshotRoute, ...]
    removed: tuple[SnapshotRoute, ...]

    @property
    def changed(self) -> bool:
        """Return whether route membership changed."""

        return bool(self.added or self.removed)


class PlanSnapshotStore:
    """Store and compare route plan snapshots as JSON files."""

    def __init__(
        self,
        directory: Path,
        keep: int = 100,
    ) -> None:
        if keep < 2:
            raise ValueError(
                "At least two plan snapshots must be retained"
            )

        self._directory = directory
        self._keep = keep

    def save(
        self,
        routes: Iterable[PlannedRoute],
        created_at: datetime | None = None,
    ) -> Path:
        """Save route plan snapshot and return its path."""

        timestamp = created_at or datetime.now()
        snapshot_routes = tuple(
            sorted(
                (
                    SnapshotRoute.from_planned_route(route)
                    for route in routes
                ),
                key=lambda route: (
                    route.family,
                    route.prefix,
                ),
            )
        )

        snapshot = PlanSnapshot(
            created_at=timestamp.isoformat(timespec="seconds"),
            routes=snapshot_routes,
        )

        self._directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = (
            timestamp.strftime("%Y%m%dT%H%M%S_%f")
            + ".json"
        )
        path = self._directory / filename
        temporary_path = path.with_suffix(".json.tmp")

        payload = {
            "created_at": snapshot.created_at,
            "route_count": snapshot.route_count,
            "routes": [
                asdict(route)
                for route in snapshot.routes
            ],
        }

        try:
            temporary_path.write_text(
                json.dumps(
                    payload,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(path)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise PlanSnapshotError(
                f"Unable to save route plan snapshot: {exc}"
            ) from exc

        self._prune()
        return path

    def list_paths(self) -> list[Path]:
        """Return snapshots ordered from oldest to newest."""

        if not self._directory.exists():
            return []

        return sorted(
            path
            for path in self._directory.glob("*.json")
            if path.is_file()
        )

    def load(self, path: Path) -> PlanSnapshot:
        """Load one snapshot from disk."""

        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise PlanSnapshotError(
                f"Unable to read plan snapshot {path}: {exc}"
            ) from exc

        try:
            routes = tuple(
                SnapshotRoute(
                    prefix=str(item["prefix"]),
                    family=int(item["family"]),
                    source_ips=int(item["source_ips"]),
                    unique_domains=int(
                        item["unique_domains"]
                    ),
                    unique_resolvers=int(
                        item["unique_resolvers"]
                    ),
                    source_count=int(item["source_count"]),
                    source_trust=int(item["source_trust"]),
                    confidence=int(item["confidence"]),
                    publish_score=int(
                        item["publish_score"]
                    ),
                )
                for item in payload["routes"]
            )

            return PlanSnapshot(
                created_at=str(payload["created_at"]),
                routes=routes,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise PlanSnapshotError(
                f"Invalid plan snapshot {path}: {exc}"
            ) from exc

    def latest(self) -> PlanSnapshot | None:
        """Return latest snapshot, if available."""

        paths = self.list_paths()

        if not paths:
            return None

        return self.load(paths[-1])

    def previous_and_current(
        self,
    ) -> tuple[PlanSnapshot, PlanSnapshot] | None:
        """Return the last two snapshots."""

        paths = self.list_paths()

        if len(paths) < 2:
            return None

        return (
            self.load(paths[-2]),
            self.load(paths[-1]),
        )

    def changes(self) -> PlanChanges | None:
        """Compare the last two stored route plans."""

        snapshots = self.previous_and_current()

        if snapshots is None:
            return None

        previous, current = snapshots

        previous_by_key = {
            (route.family, route.prefix): route
            for route in previous.routes
        }
        current_by_key = {
            (route.family, route.prefix): route
            for route in current.routes
        }

        added_keys = (
            current_by_key.keys()
            - previous_by_key.keys()
        )
        removed_keys = (
            previous_by_key.keys()
            - current_by_key.keys()
        )

        added = tuple(
            sorted(
                (
                    current_by_key[key]
                    for key in added_keys
                ),
                key=lambda route: (
                    route.family,
                    route.prefix,
                ),
            )
        )

        removed = tuple(
            sorted(
                (
                    previous_by_key[key]
                    for key in removed_keys
                ),
                key=lambda route: (
                    route.family,
                    route.prefix,
                ),
            )
        )

        return PlanChanges(
            previous_count=previous.route_count,
            current_count=current.route_count,
            added=added,
            removed=removed,
        )

    def _prune(self) -> None:
        """Remove snapshots exceeding retention limit."""

        paths = self.list_paths()

        for path in paths[:-self._keep]:
            try:
                path.unlink()
            except OSError as exc:
                raise PlanSnapshotError(
                    f"Unable to remove old snapshot {path}: {exc}"
                ) from exc
