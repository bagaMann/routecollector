"""
Tests for dynamic DNS YAML configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from routecollector.dynamic import (
    DynamicConfigError,
    DynamicConfigLoader,
)


def write_service(
    services_dir: Path,
    filename: str,
    content: str,
) -> None:
    services_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    (services_dir / filename).write_text(
        content.strip(),
        encoding="utf-8",
    )


def test_loads_dynamic_rule(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "youtube.yaml",
        """
name: youtube
enabled: true

dynamic:
  enabled: true
  match:
    domains:
      - youtube.com
      - googlevideo.com
      - YTIMG.COM.
    include_subdomains: true
""",
    )

    rules = DynamicConfigLoader(
        services_dir
    ).load_rules()

    assert len(rules) == 1
    assert rules[0].service_name == "youtube"
    assert rules[0].domains == (
        "youtube.com",
        "googlevideo.com",
        "ytimg.com",
    )
    assert rules[0].include_subdomains is True


def test_skips_service_without_dynamic_block(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "youtube.yaml",
        """
name: youtube
enabled: true
sources:
  - type: manual
    domains:
      - youtube.com
""",
    )

    assert (
        DynamicConfigLoader(
            services_dir
        ).load_rules()
        == ()
    )


def test_skips_disabled_service(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "youtube.yaml",
        """
name: youtube
enabled: false

dynamic:
  match:
    domains:
      - youtube.com
""",
    )

    assert (
        DynamicConfigLoader(
            services_dir
        ).load_rules()
        == ()
    )


def test_skips_disabled_dynamic_rule(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "youtube.yaml",
        """
name: youtube
enabled: true

dynamic:
  enabled: false
  match:
    domains:
      - youtube.com
""",
    )

    assert (
        DynamicConfigLoader(
            services_dir
        ).load_rules()
        == ()
    )


def test_defaults_to_matching_subdomains(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "youtube.yaml",
        """
name: youtube
dynamic:
  match:
    domains:
      - googlevideo.com
""",
    )

    matcher = DynamicConfigLoader(
        services_dir
    ).build_matcher()

    assert matcher.matches(
        "rr1---sn-test.googlevideo.com"
    )


def test_respects_include_subdomains_false(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "example.yaml",
        """
name: example
dynamic:
  match:
    domains:
      - example.com
    include_subdomains: false
""",
    )

    matcher = DynamicConfigLoader(
        services_dir
    ).build_matcher()

    assert matcher.matches("example.com")
    assert not matcher.matches(
        "www.example.com"
    )


@pytest.mark.parametrize(
    "content",
    [
        """
enabled: true
dynamic:
  match:
    domains:
      - example.com
""",
        """
name: example
dynamic: true
""",
        """
name: example
dynamic:
  match: true
""",
        """
name: example
dynamic:
  match:
    domains: example.com
""",
        """
name: example
dynamic:
  match:
    domains: []
""",
        """
name: example
dynamic:
  match:
    domains:
      - example.com
    include_subdomains: "yes"
""",
    ],
)
def test_rejects_invalid_dynamic_configuration(
    tmp_path: Path,
    content: str,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "invalid.yaml",
        content,
    )

    with pytest.raises(
        DynamicConfigError
    ):
        DynamicConfigLoader(
            services_dir
        ).load_rules()


def test_loads_multiple_services(
    tmp_path: Path,
) -> None:
    services_dir = tmp_path / "services"

    write_service(
        services_dir,
        "youtube.yaml",
        """
name: youtube
dynamic:
  match:
    domains:
      - googlevideo.com
""",
    )

    write_service(
        services_dir,
        "telegram.yaml",
        """
name: telegram
dynamic:
  match:
    domains:
      - telegram.org
      - t.me
""",
    )

    rules = DynamicConfigLoader(
        services_dir
    ).load_rules()

    assert {
        rule.service_name
        for rule in rules
    } == {
        "youtube",
        "telegram",
    }


def test_missing_directory_returns_empty(
    tmp_path: Path,
) -> None:
    rules = DynamicConfigLoader(
        tmp_path / "missing"
    ).load_rules()

    assert rules == ()
