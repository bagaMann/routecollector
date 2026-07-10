"""
Tests for BIRD configuration exporter.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.exporter.bird import BirdExporter
from routecollector.planner.planner import PlannedRoute


def test_bird_exporter_generates_ipv4_and_ipv6_protocols(
    tmp_path: Path,
) -> None:
    """Exporter must generate valid static protocol sections."""

    output_file = tmp_path / "routecollector.conf"

    routes = [
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

    exporter = BirdExporter(output_file)
    result = exporter.export(routes)

    assert result == output_file
    assert output_file.exists()

    content = output_file.read_text(encoding="utf-8")

    assert "protocol static routecollector_static {" in content
    assert "protocol static routecollector_static6 {" in content
    assert "route 192.0.2.0/24 blackhole;" in content
    assert "route 2001:db8::/48 blackhole;" in content
    assert "confidence=25" in content
    assert "confidence=50" in content


def test_bird_exporter_replaces_existing_file_atomically(
    tmp_path: Path,
) -> None:
    """Exporter must replace an existing file with new content."""

    output_file = tmp_path / "routecollector.conf"
    output_file.write_text("old configuration", encoding="utf-8")

    exporter = BirdExporter(output_file)

    exporter.export(
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

    assert "old configuration" not in content
    assert "route 198.51.100.0/24 blackhole;" in content
    assert not (tmp_path / "routecollector.conf.tmp").exists()
