"""Tests for the RouteCollector doctor runner."""

from routecollector.doctor.models import DoctorCheck, DoctorStatus
from routecollector.doctor.runner import DoctorRunner


def test_runner_executes_single_and_multiple_checks() -> None:
    runner = DoctorRunner()

    runner.register(
        lambda: DoctorCheck("Environment", "Python", DoctorStatus.OK)
    )
    runner.register(
        lambda: (
            DoctorCheck("Database", "SQLite", DoctorStatus.OK),
            DoctorCheck("Database", "Schema", DoctorStatus.WARNING),
        )
    )

    result = runner.run()

    assert [
        (check.category, check.name)
        for check in result.checks
    ] == [
        ("Environment", "Python"),
        ("Database", "SQLite"),
        ("Database", "Schema"),
    ]
    assert result.ok_count == 2
    assert result.warning_count == 1
    assert result.exit_code == 1


def test_runner_accepts_initial_check_functions() -> None:
    runner = DoctorRunner(
        [
            lambda: DoctorCheck(
                "BIRD",
                "binary",
                DoctorStatus.ERROR,
            ),
        ]
    )

    result = runner.run()

    assert result.error_count == 1
    assert result.overall_label == "FAILED"
