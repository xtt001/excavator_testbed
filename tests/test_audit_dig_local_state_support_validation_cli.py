from __future__ import annotations

from pathlib import Path

from testbed.cli import audit_dig_local_state_support_validation as cli


def test_defaults_use_canonical_dig_config_and_new_validation_root() -> None:
    args = cli.build_parser().parse_args([])

    assert args.dig_training_config == cli.DEFAULT_DIG_TRAINING_CONFIG
    assert args.output_root == cli.DEFAULT_OUTPUT_ROOT


def test_cli_accepts_explicit_paths() -> None:
    args = cli.build_parser().parse_args(
        ["--dig-training-config", "testbed/configs/dig.yaml", "--output-root", "/tmp/out"]
    )

    assert args.dig_training_config == Path("testbed/configs/dig.yaml")
    assert args.output_root == Path("/tmp/out")
