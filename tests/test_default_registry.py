"""
Tests for the built-in source registry.
"""

from routecollector.sources.default_registry import (
    create_default_registry,
)


def test_default_registry_contains_builtin_sources() -> None:
    """All bundled source plugins must be registered."""

    registry = create_default_registry()

    assert registry.names() == (
        "domain-list-community",
        "http-text",
        "manual",
    )
