"""
Route confidence scoring policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class RouteScoreInput:
    """Input data used to calculate route confidence."""

    unique_ips: int
    unique_domains: int
    unique_resolvers: int
    first_seen: datetime
    last_seen: datetime
    source_trust: int = 0


@dataclass(slots=True, frozen=True)
class RouteScore:
    """Calculated confidence score and its components."""

    total: int
    ip_score: int
    domain_score: int
    resolver_score: int
    history_score: int
    source_score: int = 0
    source_trust: int = 0


class RouteScorer:
    """Calculate a bounded and explainable route confidence score."""

    MAX_IP_SCORE = 40
    MAX_DOMAIN_SCORE = 30
    MAX_RESOLVER_SCORE = 20
    MAX_HISTORY_SCORE = 10

    # Source trust is passed into the scorer, but deliberately does not
    # affect the total score yet. It will be enabled by a separate policy
    # change after this refactoring is verified.
    MAX_SOURCE_SCORE = 0

    MAX_TOTAL_SCORE = 100

    def calculate(self, data: RouteScoreInput) -> RouteScore:
        """Calculate route confidence in the range from 0 to 100."""

        self._validate(data)

        age_days = max(
            0,
            (data.last_seen.date() - data.first_seen.date()).days,
        )

        ip_score = min(
            data.unique_ips * 3,
            self.MAX_IP_SCORE,
        )

        domain_score = min(
            data.unique_domains * 2,
            self.MAX_DOMAIN_SCORE,
        )

        resolver_score = min(
            data.unique_resolvers * 10,
            self.MAX_RESOLVER_SCORE,
        )

        history_score = min(
            age_days,
            self.MAX_HISTORY_SCORE,
        )

        # The source trust value is now part of RouteScoreInput and is
        # available for diagnostics. For this refactoring commit its
        # contribution intentionally remains zero.
        source_score = min(
            data.source_trust,
            self.MAX_SOURCE_SCORE,
        )

        total = min(
            ip_score
            + domain_score
            + resolver_score
            + history_score
            + source_score,
            self.MAX_TOTAL_SCORE,
        )

        return RouteScore(
            total=total,
            ip_score=ip_score,
            domain_score=domain_score,
            resolver_score=resolver_score,
            history_score=history_score,
            source_score=source_score,
            source_trust=data.source_trust,
        )

    @staticmethod
    def _validate(data: RouteScoreInput) -> None:
        """Validate scoring input."""

        if data.unique_ips < 0:
            raise ValueError("Unique IP count cannot be negative")

        if data.unique_domains < 0:
            raise ValueError("Unique domain count cannot be negative")

        if data.unique_resolvers < 0:
            raise ValueError("Unique resolver count cannot be negative")

        if not 0 <= data.source_trust <= 100:
            raise ValueError("Source trust must be between 0 and 100")

        if data.last_seen < data.first_seen:
            raise ValueError("last_seen cannot be earlier than first_seen")
