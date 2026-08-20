"""Run the pre-registered local complete-state Dig support validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import (
    DEFAULT_DIG_TRAINING_CONFIG,
    DEFAULT_SOURCE_RESULTS_ROOT,
)
from testbed.eval.dig_local_state_support_validation_runner import (
    run_dig_local_state_support_validation_from_file,
)

DEFAULT_OUTPUT_ROOT = DEFAULT_SOURCE_RESULTS_ROOT.parent / "dig_local_state_support_validation_v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-dig-local-state-support-validation",
        description=(
            "Select a pre-registered local complete-state Dig support candidate "
            "from strict training and held validation only. This command never "
            "reads Stage-A target results, trains, runs Unity, or changes runtime."
        ),
    )
    parser.add_argument(
        "--dig-training-config", type=Path, default=DEFAULT_DIG_TRAINING_CONFIG
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_dig_local_state_support_validation_from_file(
        dig_training_config_path=args.dig_training_config,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
