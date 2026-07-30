from __future__ import annotations

from pathlib import Path

import tomllib

from testbed.cli.goal_conditioned_recovery_experiment import build_parser


def test_goal_conditioned_recovery_cli_exposes_only_offline_artifact_commands() -> None:
    parser = build_parser()
    help_text = parser.format_help()

    assert "build-preflight" in help_text
    assert "collect-evidence" in help_text
    assert "build-functional-config" in help_text
    assert "validate-functional" in help_text
    assert "run-live" not in help_text


def test_goal_conditioned_recovery_cli_is_registered() -> None:
    pyproject = (
        Path(__file__).parents[1] / "pyproject.toml"
    ).read_bytes()
    scripts = tomllib.loads(pyproject.decode("utf-8"))["project"]["scripts"]

    assert scripts["tb-goal-conditioned-recovery-experiment"] == (
        "testbed.cli.goal_conditioned_recovery_experiment:main"
    )
