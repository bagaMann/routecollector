"""
Tests for BIRD route exporter.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.exporter.bird import BirdExporter
from routecollector.planner.planner import PlannedRoute


def make_route(
    *,
    prefix: str,
    family: int,
    source_ips: int,
    confidence: int,
    publish_score: int,
    unique_domains: int = 10,
    unique_resolvers: int = 2,
    source_count: int = 2,
    source_trust: int = 100,
) -> PlannedRoute:
    """Build a planned route for exporter tests."""

    return PlannedRoute(
        prefix=prefix,
        family=family,
        source_ips=source_ips,
        unique_domains=unique_domains,
        unique_resolvers=unique_resolvers,
        source_count=source_count,
        source_trust=source_trust,
        confidence=confidence,
        publish_score=publish_score,
    )


def build_test_routes() -> list[PlannedRoute]:
    """Return test IPv4 and IPv6 routes."""

    return [
        make_route(
            prefix="192.0.2.0/24",
            family=4,
            source_ips=4,
            confidence=25,
            publish_score=51,
        ),
        make_route(
            prefix="2001:db8::/48",
            family=6,
            source_ips=8,
            confidence=50,
            publish_score=76,
        ),
    ]


def test_bird_exporter_generates_ipv4_and_ipv6_protocols(
    tmp_path: Path,
) -> None:
    """Exporter must generate stable IPv4 and IPv6 protocol sections."""

    output_file = tmp_path / "routecollector.conf"
    exporter = BirdExporter(output_file)

    result = exporter.export(build_test_routes())

    assert result.path == output_file
    assert result.changed is True
    assert result.route_count == 2
    assert output_file.exists()

    content = output_file.read_text(encoding="utf-8")

    assert "protocol static routecollector_static {" in content
    assert "protocol static routecollector_static6 {" in content
    assert "route 192.0.2.0/24 blackhole;" in content
    assert "route 2001:db8::/48 blackhole;" in content

    assert "confidence=" not in content
    assert "publish_score=" not in content
    assert "source_ips=" not in content


def test_bird_exporter_reports_unchanged_content(
    tmp_path: Path,
) -> None:
    """Second identical export must report no change."""

    output_file = tmp_path / "routecollector.conf"
    exporter = BirdExporter(output_file)
    routes = build_test_routes()

    first_result = exporter.export(routes)
    second_result = exporter.export(routes)

    assert first_result.changed is True
    assert second_result.changed is False
    assert second_result.route_count == 2


def test_bird_exporter_ignores_statistic_changes(
    tmp_path: Path,
) -> None:
    """Changing route statistics must not change BIRD config."""

    output_file = tmp_path / "routecollector.conf"
    exporter = BirdExporter(output_file)

    first_result = exporter.export(
        [
            make_route(
                prefix="192.0.2.0/24",
                family=4,
                source_ips=1,
                unique_domains=1,
                unique_resolvers=1,
                source_count=1,
                source_trust=50,
                confidence=10,
                publish_score=23,
            )
        ]
    )

    second_result = exporter.export(
        [
            make_route(
                prefix="192.0.2.0/24",
                family=4,
                source_ips=200,
                unique_domains=150,
                unique_resolvers=10,
                source_count=5,
                source_trust=100,
                confidence=100,
                publish_score=100,
            )
        ]
    )

    assert first_result.changed is True
    assert second_result.changed is False


def test_bird_exporter_replaces_changed_content_atomically(
    tmp_path: Path,
) -> None:
    """Changed route prefix set must replace the existing file."""

    output_file = tmp_path / "routecollector.conf"
    exporter = BirdExporter(output_file)

    exporter.export(build_test_routes())

    changed_result = exporter.export(
        [
            make_route(
                prefix="198.51.100.0/24",
                family=4,
                source_ips=3,
                confidence=40,
                publish_score=66,
            )
        ]
    )

    content = output_file.read_text(encoding="utf-8")

    assert changed_result.changed is True
    assert changed_result.route_count == 1
    assert "route 198.51.100.0/24 blackhole;" in content
    assert "route 192.0.2.0/24 blackhole;" not in content
    assert "route 2001:db8::/48 blackhole;" not in content
