"""
Source trust scoring policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_SOURCE_TRUST: dict[str, int] = {
    "manual": 100,
    "domain-list-community": 95,
}


@dataclass(slots=True, frozen=True)
class SourceTrustScore:
    """Calculated source trust score."""

    total: int
    matched_sources: tuple[str, ...]
    unknown_sources: tuple[str, ...]
    source_values: dict[str, int] = field(default_factory=dict)


class SourceTrustPolicy:
    """Calculate bounded trust from independent domain sources."""

    MAX_SCORE = 100

    def __init__(
        self,
        trust_values: dict[str, int] | None = None,
    ) -> None:
        values = trust_values or DEFAULT_SOURCE_TRUST

        self._trust_values = {
            self._normalize_name(name): self._validate_value(
                name,
                value,
            )
            for name, value in values.items()
        }

    def score(
        self,
        sources: set[str] | frozenset[str] | list[str] | tuple[str, ...],
    ) -> SourceTrustScore:
        """Calculate source trust without double-counting duplicates.

        The strongest source contributes its full normalized value.
        Every additional independent source contributes 25% of its value.
        The result is capped at 100.
        """

        normalized_sources = {
            self._normalize_name(source)
            for source in sources
            if source.strip()
        }

        matched = sorted(
            source
            for source in normalized_sources
            if source in self._trust_values
        )
        unknown = sorted(
            source
            for source in normalized_sources
            if source not in self._trust_values
        )

        source_values = {
            source: self._trust_values[source]
            for source in matched
        }

        ordered_values = sorted(
            source_values.values(),
            reverse=True,
        )

        if not ordered_values:
            total = 0
        else:
            total = ordered_values[0]

            for value in ordered_values[1:]:
                total += round(value * 0.25)

            total = min(total, self.MAX_SCORE)

        return SourceTrustScore(
            total=total,
            matched_sources=tuple(matched),
            unknown_sources=tuple(unknown),
            source_values=source_values,
        )

    def get(self, source_name: str) -> int | None:
        """Return configured trust value for one source."""

        return self._trust_values.get(
            self._normalize_name(source_name)
        )

    def values(self) -> dict[str, int]:
        """Return a copy of configured source trust values."""

        return dict(self._trust_values)

    @staticmethod
    def _normalize_name(source_name: str) -> str:
        """Normalize source name."""

        return source_name.strip().lower()

    @classmethod
    def _validate_value(
        cls,
        source_name: str,
        value: int,
    ) -> int:
        """Validate one trust value."""

        if not isinstance(value, int):
            raise TypeError(
                f"Source trust value must be an integer: {source_name}"
            )

        if not 0 <= value <= cls.MAX_SCORE:
            raise ValueError(
                "Source trust value must be between 0 and 100: "
                f"{source_name}"
            )

        return value
