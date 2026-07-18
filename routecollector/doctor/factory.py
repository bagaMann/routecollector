"""
Factory for the default RouteCollector doctor runner.
"""

from __future__ import annotations

from pathlib import Path

from routecollector.doctor.bird_checks import check_bird
from routecollector.doctor.checks import (
    check_directories,
    check_environment,
)
from routecollector.doctor.database_checks import (
    check_database,
)
from routecollector.doctor.runner import DoctorRunner
from routecollector.doctor.source_checks import (
    check_service_configuration,
    check_source_plugins,
)


DEFAULT_DOCTOR_DIRECTORIES = (
    Path("config/services"),
    Path("state"),
    Path("logs"),
    Path("cache"),
    Path("bird"),
)

DEFAULT_DOCTOR_DATABASE = Path("state/state.db")
DEFAULT_DOCTOR_SERVICES = Path("config/services")
DEFAULT_BIRD_MAIN_CONFIG = Path("/etc/bird/bird.conf")
DEFAULT_BIRD_GENERATED_CONFIG = Path("bird/routecollector.conf")
DEFAULT_BIRD_INSTALLED_CONFIG = Path(
    "/etc/bird/routecollector.conf"
)


def build_doctor_runner(
    config_path: Path,
    directories: tuple[Path, ...] = DEFAULT_DOCTOR_DIRECTORIES,
    database_path: Path = DEFAULT_DOCTOR_DATABASE,
    services_dir: Path = DEFAULT_DOCTOR_SERVICES,
    bird_main_config: Path = DEFAULT_BIRD_MAIN_CONFIG,
    bird_generated_config: Path = DEFAULT_BIRD_GENERATED_CONFIG,
    bird_installed_config: Path = DEFAULT_BIRD_INSTALLED_CONFIG,
) -> DoctorRunner:
    """Create the default read-only diagnostic runner."""

    runner = DoctorRunner()

    runner.register(
        lambda: check_environment(config_path)
    )
    runner.register(
        lambda: check_directories(directories)
    )
    runner.register(
        lambda: check_database(database_path)
    )
    runner.register(
        lambda: check_service_configuration(
            services_dir
        )
    )
    runner.register(
        lambda: check_source_plugins(
            services_dir
        )
    )
    runner.register(
        lambda: check_bird(
            main_config=bird_main_config,
            generated_config=bird_generated_config,
            installed_config=bird_installed_config,
        )
    )

    return runner
