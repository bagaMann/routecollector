#!/usr/bin/env python3
from pathlib import Path
import re
import sys

path = Path('routecollector/core/repository.py')
if not path.is_file():
    print(f'File not found: {path}', file=sys.stderr)
    raise SystemExit(1)

text = path.read_text(encoding='utf-8')
backup = path.with_suffix('.py.before-unique-evidence')
backup.write_text(text, encoding='utf-8')

old_route_stat = '''@dataclass(slots=True, frozen=True)
class RouteStat:
    """Route statistics model."""

    prefix: str
    family: int
    source_ips: int
    total_hits: int
    confidence: int
    first_seen: str | None
    last_seen: str | None'''

new_route_stat = '''@dataclass(slots=True, frozen=True)
class RouteStat:
    """Route statistics model."""

    prefix: str
    family: int
    source_ips: int
    unique_domains: int
    unique_resolvers: int
    total_hits: int
    confidence: int
    first_seen: str | None
    last_seen: str | None'''

if old_route_stat not in text:
    print('RouteStat block not found or already patched', file=sys.stderr)
    raise SystemExit(2)
text = text.replace(old_route_stat, new_route_stat, 1)

pattern_rebuild = re.compile(r"    def rebuild_route_stats\(.*?^        return len\(calculated_stats\)\n", re.M | re.S)
replacement_rebuild = '''    def rebuild_route_stats(
        self,
        ipv4_prefix: int = 24,
        ipv6_prefix: int = 48,
    ) -> int:
        """Rebuild normalized route statistics from observations."""

        calculated_stats = RouteStatisticsBuilder(
            ipv4_prefix=ipv4_prefix,
            ipv6_prefix=ipv6_prefix,
        ).build(self.list_observations())

        with self._database.connection() as conn:
            conn.execute("DELETE FROM route_stats")

            conn.executemany(
                """
                INSERT INTO route_stats
                    (
                        prefix,
                        family,
                        source_ips,
                        unique_domains,
                        unique_resolvers,
                        total_hits,
                        confidence,
                        first_seen,
                        last_seen
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        stat.prefix,
                        stat.family,
                        stat.source_ips,
                        stat.unique_domains,
                        stat.unique_resolvers,
                        stat.total_hits,
                        stat.confidence,
                        stat.first_seen,
                        stat.last_seen,
                    )
                    for stat in calculated_stats
                ],
            )

        return len(calculated_stats)
'''
text, count = pattern_rebuild.subn(replacement_rebuild, text, count=1)
if count != 1:
    print(f'rebuild_route_stats patch failed: {count} matches', file=sys.stderr)
    raise SystemExit(3)

pattern_list = re.compile(r"    def list_route_stats\(self\) -> list\[RouteStat\]:.*?^            \]\n", re.M | re.S)
replacement_list = '''    def list_route_stats(self) -> list[RouteStat]:
        """Return route statistics."""

        with self._database.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    prefix,
                    family,
                    source_ips,
                    unique_domains,
                    unique_resolvers,
                    total_hits,
                    confidence,
                    first_seen,
                    last_seen
                FROM route_stats
                ORDER BY family, prefix
                """
            ).fetchall()

            return [
                RouteStat(
                    prefix=str(row["prefix"]),
                    family=int(row["family"]),
                    source_ips=int(row["source_ips"]),
                    unique_domains=int(row["unique_domains"]),
                    unique_resolvers=int(row["unique_resolvers"]),
                    total_hits=int(row["total_hits"]),
                    confidence=int(row["confidence"]),
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                )
                for row in rows
            ]
'''
text, count = pattern_list.subn(replacement_list, text, count=1)
if count != 1:
    print(f'list_route_stats patch failed: {count} matches', file=sys.stderr)
    raise SystemExit(4)

path.write_text(text, encoding='utf-8')
print(f'Patched: {path}')
print(f'Backup:  {backup}')
