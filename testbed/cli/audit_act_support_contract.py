"""Run the offline Strict-18 support_contract_v2 audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_support_contract_audit_runner import (
    run_support_contract_audit_from_files,
)

DEFAULT_SOURCE_RESULTS_ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0/"
    "carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/"
    "run/results"
)
DEFAULT_STAGE_A_OUTPUT_ROOT = DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v1"
DEFAULT_OUTPUT_ROOT = DEFAULT_SOURCE_RESULTS_ROOT.parent / "support_contract_v2_audit"
DEFAULT_DIG_TRAINING_CONFIG = Path(
    "testbed/configs/act_yulong_strict_replay18_four_camera_dig_qvel.yaml"
)
DEFAULT_RETURN_TRAINING_CONFIG = Path(
    "testbed/configs/act_yulong_strict_replay18_four_camera_return_envelope_qvel.yaml"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-act-support-contract",
        description=(
            "Audit frozen ACT numeric support candidates using strict train and "
            "held validation sources. This command never changes a runtime gate, "
            "runs Unity, trains, or controls a machine."
        ),
    )
    parser.add_argument("--source-results-root", type=Path, default=DEFAULT_SOURCE_RESULTS_ROOT)
    parser.add_argument("--stage-a-output-root", type=Path, default=DEFAULT_STAGE_A_OUTPUT_ROOT)
    parser.add_argument("--dig-training-config", type=Path, default=DEFAULT_DIG_TRAINING_CONFIG)
    parser.add_argument("--return-training-config", type=Path, default=DEFAULT_RETURN_TRAINING_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_support_contract_audit_from_files(
        source_results_root=args.source_results_root,
        stage_a_output_root=args.stage_a_output_root,
        dig_training_config_path=args.dig_training_config,
        return_training_config_path=args.return_training_config,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
