"""Tests for RouteCollector doctor core models."""

from __future__ import annotations

import pytest

from routecollector.doctor.models import DoctorCheck, DoctorResult, DoctorStatus


def test_doctor_status_labels() -> None:
    assert DoctorStatus.OK.label == "OK"
    assert DoctorStatus.WARNING.label == "WARNING"
    assert DoctorStatus.ERROR.label == "ERROR"


@pytest.mark.parametrize(
    ("category", "name", "message"),
    [
        ("", "SQLite", "category"),
        ("   ", "SQLite", "category"),
        ("Database", "", "name"),
        ("Database", "   ", "name"),
    ],
)
def test_doctor_check_rejects_empty_fields(
    category: str,
    name: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DoctorCheck(
            category=category,
            name=name,
            status=DoctorStatus.OK,
        )


def test_doctor_result_counts_and_overall_status() -> None:
    result = DoctorResult.from_checks(
        [
            DoctorCheck("Environment", "Python", DoctorStatus.OK),
            DoctorCheck("Directories", "cache", DoctorStatus.WARNING),
            DoctorCheck("BIRD", "configuration", DoctorStatus.ERROR),
        ]
    )

    assert result.check_count == 3
    assert result.ok_count == 1
    assert result.warning_count == 1
    assert result.error_count == 1
    assert result.overall_status is DoctorStatus.ERROR
    assert result.overall_label == "FAILED"
    assert result.exit_code == 2


def test_doctor_result_warning_exit_code() -> None:
    result = DoctorResult.from_checks(
        [
            DoctorCheck("Environment", "Python", DoctorStatus.OK),
            DoctorCheck("Service", "systemd", DoctorStatus.WARNING),
        ]
    )

    assert result.overall_status is DoctorStatus.WARNING
    assert result.overall_label == "WARNING"
    assert result.exit_code == 1


def test_empty_doctor_result_is_healthy() -> None:
    result = DoctorResult.from_checks([])

    assert result.check_count == 0
    assert result.overall_status is DoctorStatus.OK
    assert result.overall_label == "HEALTHY"
    assert result.exit_code == 0


def test_doctor_result_groups_categories_in_order() -> None:
    result = DoctorResult.from_checks(
        [
            DoctorCheck("Environment", "Python", DoctorStatus.OK),
            DoctorCheck("Database", "SQLite", DoctorStatus.OK),
            DoctorCheck("Environment", "Version", DoctorStatus.OK),
        ]
    )

    grouped = result.by_category()

    assert [item[0] for item in grouped] == ["Environment", "Database"]
    assert [check.name for check in grouped[0][1]] == ["Python", "Version"]
