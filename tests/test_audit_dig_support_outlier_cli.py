from __future__ import annotations

from pathlib import Path

from testbed.cli import audit_dig_support_outlier as cli


def test_defaults_point_to_frozen_stage_a_v3_and_new_output_root() -> None:
    args = cli.build_parser().parse_args([])

    assert args.stage_a_v3_output_root == cli.DEFAULT_STAGE_A_V3_OUTPUT_ROOT
    assert args.dig_training_config == cli.DEFAULT_DIG_TRAINING_CONFIG
    assert args.output_root == cli.DEFAULT_OUTPUT_ROOT


def test_cli_accepts_explicit_paths() -> None:
    args = cli.build_parser().parse_args(
        [
            "--stage-a-v3-output-root",
            "/tmp/stage",
            "--dig-training-config",
            "testbed/configs/dig.yaml",
            "--output-root",
            "/tmp/output",
        ]
    )

    assert args.stage_a_v3_output_root == Path("/tmp/stage")
    assert args.dig_training_config == Path("testbed/configs/dig.yaml")
    assert args.output_root == Path("/tmp/output")
