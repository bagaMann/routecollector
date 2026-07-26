"""
Thread-safe cache of currently published route prefixes.
"""

from __future__ import annotations

from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from threading import RLock
from typing import Iterable


IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network


class DynamicRouteCache:
    """Track prefixes already present in the published route plan."""

    def __init__(
        self,
        prefixes: Iterable[str | IPNetwork] = (),
    ) -> None:
        self._lock = RLock()
        self._prefixes: set[IPNetwork] = set()
        self.replace(prefixes)

    def replace(
        self,
        prefixes: Iterable[str | IPNetwork],
    ) -> None:
        """Replace the complete cached prefix set."""

        normalized = {
            self._normalize_prefix(prefix)
            for prefix in prefixes
        }

        with self._lock:
            self._prefixes = normalized

    def add(
        self,
        prefixes: Iterable[str | IPNetwork],
    ) -> None:
        """Add successfully published prefixes."""

        normalized = {
            self._normalize_prefix(prefix)
            for prefix in prefixes
        }

        with self._lock:
            self._prefixes.update(normalized)

    def contains(
        self,
        prefix: str | IPNetwork,
    ) -> bool:
        """Return whether a prefix is already cached."""

        normalized = self._normalize_prefix(prefix)

        with self._lock:
            return normalized in self._prefixes

    def contains_ip(
        self,
        address: str | IPAddress,
    ) -> bool:
        """Return whether an address belongs to any cached prefix."""

        normalized_address = (
            address
            if isinstance(
                address,
                (IPv4Address, IPv6Address),
            )
            else ip_address(address)
        )

        with self._lock:
            return any(
                normalized_address in prefix
                for prefix in self._prefixes
                if prefix.version == normalized_address.version
            )

    def missing(
        self,
        prefixes: Iterable[str | IPNetwork],
    ) -> tuple[IPNetwork, ...]:
        """Return normalized prefixes absent from the cache."""

        normalized = {
            self._normalize_prefix(prefix)
            for prefix in prefixes
        }

        with self._lock:
            missing = normalized.difference(
                self._prefixes
            )

        return tuple(
            sorted(
                missing,
                key=lambda item: (
                    item.version,
                    int(item.network_address),
                    item.prefixlen,
                ),
            )
        )

    def snapshot(self) -> tuple[IPNetwork, ...]:
        """Return an immutable sorted cache snapshot."""

        with self._lock:
            prefixes = tuple(self._prefixes)

        return tuple(
            sorted(
                prefixes,
                key=lambda item: (
                    item.version,
                    int(item.network_address),
                    item.prefixlen,
                ),
            )
        )

    def __len__(self) -> int:
        with self._lock:
            return len(self._prefixes)

    @staticmethod
    def _normalize_prefix(
        prefix: str | IPNetwork,
    ) -> IPNetwork:
        if isinstance(
            prefix,
            (IPv4Network, IPv6Network),
        ):
            return prefix

        return ip_network(
            prefix,
            strict=False,
        )
