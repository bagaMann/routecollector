"""
Route publication scoring policy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PublishScoreInput:
    """Input values used to calculate route publication score."""

    confidence: int
    source_trust: int
    source_count: int


@dataclass(slots=True, frozen=True)
class PublishScore:
    """Calculated publication score and its components."""

    total: int
    confidence_score: int
    trust_bonus: int
    source_bonus: int


class PublishScorePolicy:
    """Calculate a bounded route publication score."""

    MAX_SCORE = 100
    TRUST_DIVISOR = 5
    SOURCE_BONUS_PER_SOURCE = 3
    MAX_SOURCE_BONUS = 15

    def calculate(self, data: PublishScoreInput) -> PublishScore:
        """Calculate publication score in the range from 0 to 100."""

        self._validate(data)

        confidence_score = min(
            data.confidence,
            self.MAX_SCORE,
        )

        trust_bonus = data.source_trust // self.TRUST_DIVISOR

        source_bonus = min(
            data.source_count * self.SOURCE_BONUS_PER_SOURCE,
            self.MAX_SOURCE_BONUS,
        )

        total = min(
            confidence_score + trust_bonus + source_bonus,
            self.MAX_SCORE,
        )

        return PublishScore(
            total=total,
            confidence_score=confidence_score,
            trust_bonus=trust_bonus,
            source_bonus=source_bonus,
        )

    @classmethod
    def _validate(cls, data: PublishScoreInput) -> None:
        """Validate publication score input."""

        if not 0 <= data.confidence <= cls.MAX_SCORE:
            raise ValueError(
                "Confidence must be between 0 and 100"
            )

        if not 0 <= data.source_trust <= cls.MAX_SCORE:
            raise ValueError(
                "Source trust must be between 0 and 100"
            )

        if data.source_count < 0:
            raise ValueError(
                "Source count cannot be negative"
            )
