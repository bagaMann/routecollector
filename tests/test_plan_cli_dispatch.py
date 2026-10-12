"""Regression test for the plan CLI argument dispatch."""

from unittest.mock import patch

from routecollector.cli import main


def test_plan_dispatch_does_not_require_dry_run() -> None:
    with patch("routecollector.cli.command_plan", return_value=0) as command:
        assert main(["plan"]) == 0

    command.assert_called_once()
    assert len(command.call_args.args) == 5
