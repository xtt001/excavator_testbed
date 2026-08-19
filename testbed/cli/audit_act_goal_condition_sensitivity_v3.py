"""Run Strict-18 Stage-A v3 only after its immutable A.2 audit prerequisites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import (
    DEFAULT_DIG_TRAINING_CONFIG,
    DEFAULT_RETURN_TRAINING_CONFIG,
    DEFAULT_SOURCE_RESULTS_ROOT,
)
from testbed.eval.act_goal_condition_sensitivity_prerequisite_binding import (
    run_stage_a_v3_after_prerequisite_audits,
)

DEFAULT_STAGE_A_V1_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v1"
)
DEFAULT_SUPPORT_AUDIT_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "support_contract_v2_audit"
)
DEFAULT_STAGE_A_V2_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v2_return"
)
DEFAULT_RETURN_STABILITY_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "return_goal_response_stability_audit_v1"
)
DEFAULT_DIG_JOINT_VALIDATION_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "dig_joint_support_validation_v1"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-act-goal-condition-sensitivity-v3",
        description=(
            "Rerun Strict-18 Stage A only after SHA-verifying the frozen v1, "
            "support-contract v2, Return stability and independent Dig joint "
            "validation evidence. This remains teacher-forced and diagnostic-only: "
            "it never lowers the 80 percent gate, changes runtime support, runs "
            "Unity, trains, or controls a machine."
        ),
    )
    parser.add_argument("--source-results-root", type=Path, default=DEFAULT_SOURCE_RESULTS_ROOT)
    parser.add_argument("--stage-a-v1-output-root", type=Path, default=DEFAULT_STAGE_A_V1_OUTPUT_ROOT)
    parser.add_argument("--support-audit-output-root", type=Path, default=DEFAULT_SUPPORT_AUDIT_OUTPUT_ROOT)
    parser.add_argument("--stage-a-v2-output-root", type=Path, default=DEFAULT_STAGE_A_V2_OUTPUT_ROOT)
    parser.add_argument(
        "--return-stability-output-root",
        type=Path,
        default=DEFAULT_RETURN_STABILITY_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--dig-joint-validation-output-root",
        type=Path,
        default=DEFAULT_DIG_JOINT_VALIDATION_OUTPUT_ROOT,
    )
    parser.add_argument("--dig-training-config", type=Path, default=DEFAULT_DIG_TRAINING_CONFIG)
    parser.add_argument("--return-training-config", type=Path, default=DEFAULT_RETURN_TRAINING_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_stage_a_v3_after_prerequisite_audits(
        source_results_root=args.source_results_root,
        stage_a_v1_output_root=args.stage_a_v1_output_root,
        support_audit_output_root=args.support_audit_output_root,
        stage_a_v2_output_root=args.stage_a_v2_output_root,
        return_stability_output_root=args.return_stability_output_root,
        dig_joint_validation_output_root=args.dig_joint_validation_output_root,
        dig_training_config_path=args.dig_training_config,
        return_training_config_path=args.return_training_config,
        output_root=args.output_root,
        device=str(args.device),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
