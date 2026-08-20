"""Audit the frozen Strict-18 Dig support outlier without changing support."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import (
    DEFAULT_DIG_TRAINING_CONFIG,
    DEFAULT_SOURCE_RESULTS_ROOT,
)
from testbed.eval.dig_support_outlier_audit import run_dig_support_outlier_audit

DEFAULT_STAGE_A_V3_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v3"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_SOURCE_RESULTS_ROOT.parent / "dig_support_outlier_audit_v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-dig-support-outlier",
        description=(
            "Diagnose the frozen Strict-18 Dig numeric-support outlier using "
            "recorded alignment plus strict-train and held-validation evidence. "
            "It never widens support, trains, runs Unity, or controls a machine."
        ),
    )
    parser.add_argument(
        "--stage-a-v3-output-root",
        type=Path,
        default=DEFAULT_STAGE_A_V3_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--dig-training-config",
        type=Path,
        default=DEFAULT_DIG_TRAINING_CONFIG,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_dig_support_outlier_audit(
        stage_a_v3_output_root=args.stage_a_v3_output_root,
        dig_training_config_path=args.dig_training_config,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
