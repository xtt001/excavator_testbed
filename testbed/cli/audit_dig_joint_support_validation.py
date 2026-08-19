"""Run the independent, validation-only Dig joint support audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import (
    DEFAULT_DIG_TRAINING_CONFIG,
    DEFAULT_SOURCE_RESULTS_ROOT,
)
from testbed.eval.dig_joint_support_validation_audit_runner import (
    run_dig_joint_support_validation_audit_from_file,
)

DEFAULT_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "dig_joint_support_validation_v1"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-dig-joint-support-validation",
        description=(
            "Select a pre-registered Dig joint numeric support candidate using "
            "strict training and held validation only. This command never reads "
            "Stage-A target results, changes runtime support, trains, runs Unity, "
            "or controls a machine."
        ),
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
    result = run_dig_joint_support_validation_audit_from_file(
        dig_training_config_path=args.dig_training_config,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
