"""
Tests for service and source plugin doctor checks.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import routecollector.doctor.source_checks as source_checks_module
from routecollector.doctor.models import DoctorStatus
from routecollector.doctor.source_checks import (
    check_service_configuration,
    check_source_plugins,
)


def write_service(
    services_dir: Path,
    *,
    name: str,
    enabled: bool = True,
    source_type: str = "manual",
) -> None:
    """Write one service YAML for diagnostics tests."""

    services_dir.mkdir(parents=True, exist_ok=True)

    (services_dir / f"{name}.yaml").write_text(
        f"""
name: {name}
enabled: {str(enabled).lower()}
sources:
  - type: {source_type}
    domains:
      - {name}.example
""".strip(),
        encoding="utf-8",
    )


def test_service_configuration_reports_services_and_sources(
    tmp_path: Path,
) -> None:
    """Doctor must report YAML, definitions and service states."""

    services_dir = tmp_path / "services"
    write_service(
        services_dir,
        name="youtube",
    )
    write_service(
        services_dir,
        name="disabled",
        enabled=False,
    )

    checks = check_service_configuration(
        services_dir
    )
    by_name = {
        check.name: check
        for check in checks
    }

    assert by_name["YAML"].status is DoctorStatus.OK
    assert by_name["YAML"].message == "2 services"
    assert by_name["Source definitions"].message == "2"
    assert by_name["youtube"].status is DoctorStatus.OK
    assert by_name["disabled"].status is DoctorStatus.WARNING


def test_service_configuration_warns_when_empty(
    tmp_path: Path,
) -> None:
    """Empty services directory must produce a warning."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()

    checks = check_service_configuration(
        services_dir
    )

    assert checks[0].status is DoctorStatus.OK
    assert checks[1].status is DoctorStatus.WARNING
    assert checks[1].name == "Services"


def test_service_configuration_reports_invalid_yaml(
    tmp_path: Path,
) -> None:
    """Invalid service config must produce an error."""

    services_dir = tmp_path / "services"
    services_dir.mkdir()
    (services_dir / "broken.yaml").write_text(
        "enabled: true\n",
        encoding="utf-8",
    )

    checks = check_service_configuration(
        services_dir
    )

    assert len(checks) == 1
    assert checks[0].name == "YAML"
    assert checks[0].status is DoctorStatus.ERROR


def test_source_plugins_report_registry_and_usage(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Doctor must report built-in, external and configured types."""

    services_dir = tmp_path / "services"
    write_service(
        services_dir,
        name="youtube",
        source_type="manual",
    )

    class FakeRegistry:
        def names(self) -> tuple[str, ...]:
            return ("example", "manual")

        def contains(self, name: str) -> bool:
            return name in self.names()

    monkeypatch.setattr(
        source_checks_module,
        "create_default_registry",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        source_checks_module,
        "discover_external_plugins",
        lambda: (
            SimpleNamespace(
                source=SimpleNamespace(name="example"),
                package_name="routecollector-source-example",
                package_version="0.1.0",
            ),
        ),
    )

    checks = check_source_plugins(
        services_dir
    )
    by_name = {
        check.name: check
        for check in checks
    }

    assert by_name["Registry"].message == "2 available"
    assert by_name["manual"].message == "built-in"
    assert (
        by_name["example"].message
        == "external: routecollector-source-example 0.1.0"
    )
    assert by_name["Configured usage"].status is DoctorStatus.OK
    assert by_name["Configured usage"].message == "1 source types"


def test_source_plugins_report_unavailable_configured_type(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Unknown source type in YAML must be an error."""

    services_dir = tmp_path / "services"
    write_service(
        services_dir,
        name="example",
        source_type="missing-source",
    )

    class FakeRegistry:
        def names(self) -> tuple[str, ...]:
            return ("manual",)

        def contains(self, name: str) -> bool:
            return name == "manual"

    monkeypatch.setattr(
        source_checks_module,
        "create_default_registry",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        source_checks_module,
        "discover_external_plugins",
        lambda: (),
    )

    checks = check_source_plugins(
        services_dir
    )
    usage = next(
        check
        for check in checks
        if check.name == "Configured usage"
    )

    assert usage.status is DoctorStatus.ERROR
    assert "missing-source" in usage.message


def test_source_plugins_report_registry_failure(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Broken external plugin discovery must fail registry check."""

    def fail_registry() -> object:
        raise RuntimeError("broken plugin")

    monkeypatch.setattr(
        source_checks_module,
        "create_default_registry",
        fail_registry,
    )

    checks = check_source_plugins(
        tmp_path / "services"
    )

    assert len(checks) == 1
    assert checks[0].name == "Registry"
    assert checks[0].status is DoctorStatus.ERROR
    assert "broken plugin" in checks[0].message
