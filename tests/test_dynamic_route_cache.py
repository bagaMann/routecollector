"""
Tests for the dynamic published-prefix cache.
"""

from routecollector.dynamic import DynamicRouteCache


def test_cache_detects_existing_prefixes() -> None:
    cache = DynamicRouteCache(
        [
            "142.250.74.0/24",
            "2001:4860::/48",
        ]
    )

    assert cache.contains(
        "142.250.74.0/24"
    )
    assert cache.contains_ip(
        "142.250.74.238"
    )
    assert cache.contains_ip(
        "2001:4860::1"
    )
    assert not cache.contains_ip(
        "8.8.8.8"
    )


def test_cache_returns_missing_prefixes() -> None:
    cache = DynamicRouteCache(
        ["142.250.74.0/24"]
    )

    missing = cache.missing(
        [
            "142.250.74.238/24",
            "8.8.8.8/24",
        ]
    )

    assert tuple(
        str(prefix)
        for prefix in missing
    ) == ("8.8.8.0/24",)


def test_cache_add_discard_and_replace() -> None:
    cache = DynamicRouteCache()

    cache.add(
        [
            "8.8.8.0/24",
            "1.1.1.0/24",
        ]
    )

    cache.discard(
        ["8.8.8.8/24"]
    )

    assert not cache.contains(
        "8.8.8.0/24"
    )
    assert cache.contains(
        "1.1.1.0/24"
    )

    cache.replace(
        ["9.9.9.0/24"]
    )

    assert cache.contains(
        "9.9.9.0/24"
    )
    assert not cache.contains(
        "1.1.1.0/24"
    )
