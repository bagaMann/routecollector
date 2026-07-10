"""
Tests for BIRD configuration exporter.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.exporter.bird import BirdExporter
from routecollector.planner.planner import PlannedRoute


def build_test_routes() -> list[PlannedRoute]:
    """Return test IPv4 and IPv6 routes."""

    return [
        PlannedRoute(
            prefix="192.0.2.0/24",
            family=4,
            source_ips=4,
            confidence=25,
        ),
        PlannedRoute(
            prefix="2001:db8::/48",
            family=6,
            source_ips=8,
            confidence=50,
        ),
    ]


def test_bird_exporter_generates_ipv4_and_ipv6_protocols(
    tmp_path: Path,
) -> None:
    """Exporter must generate IPv4 and IPv6 protocol sections."""

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
    assert "confidence=25" in content
    assert "confidence=50" in content


def test_bird_exporter_reports_unchanged_content(
    tmp_path: Path,
) -> None:
    """Second identical export must report no change."""

    output_file = tmp_path / "routecollector.conf"
    exporter = BirdExporter(output_file)
    routes = build_test_routes()

    first_result = exporter.export(routes)
    first_mtime = output_file.stat().st_mtime_ns

    second_result = exporter.export(routes)
    second_mtime = output_file.stat().st_mtime_ns

    assert first_result.changed is True
    assert second_result.changed is False
    assert first_mtime == second_mtime


def test_bird_exporter_replaces_changed_content_atomically(
    tmp_path: Path,
) -> None:
    """Changed route plan must replace the existing file."""

    output_file = tmp_path / "routecollector.conf"
    exporter = BirdExporter(output_file)

    exporter.export(build_test_routes())

    result = exporter.export(
        [
            PlannedRoute(
                prefix="198.51.100.0/24",
                family=4,
                source_ips=2,
                confidence=12,
            )
        ]
    )

    content = output_file.read_text(encoding="utf-8")

    assert result.changed is True
    assert "route 198.51.100.0/24 blackhole;" in content
    assert "route 192.0.2.0/24 blackhole;" not in content
    assert not (tmp_path / "routecollector.conf.tmp").exists()
