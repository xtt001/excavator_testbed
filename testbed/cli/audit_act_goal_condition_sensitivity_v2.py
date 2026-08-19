"""Run the primitive-scoped Strict-18 Stage-A support-contract v2 replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import (
    DEFAULT_DIG_TRAINING_CONFIG,
    DEFAULT_RETURN_TRAINING_CONFIG,
    DEFAULT_SOURCE_RESULTS_ROOT,
)
from testbed.eval.act_goal_condition_sensitivity_support_contract import (
    run_primitive_scoped_stage_a_support_audit,
)

DEFAULT_STAGE_A_V1_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v1"
)
DEFAULT_SUPPORT_AUDIT_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "support_contract_v2_audit"
)
DEFAULT_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v2_return"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-act-goal-condition-sensitivity-v2",
        description=(
            "Rerun Strict-18 Stage A with Dig support_contract_v1 and only an "
            "independently selected frozen Return support_contract_v2 candidate. "
            "This command never changes runtime gates, runs Unity, trains, or "
            "controls a machine."
        ),
    )
    parser.add_argument("--source-results-root", type=Path, default=DEFAULT_SOURCE_RESULTS_ROOT)
    parser.add_argument("--stage-a-v1-output-root", type=Path, default=DEFAULT_STAGE_A_V1_OUTPUT_ROOT)
    parser.add_argument("--support-audit-output-root", type=Path, default=DEFAULT_SUPPORT_AUDIT_OUTPUT_ROOT)
    parser.add_argument("--dig-training-config", type=Path, default=DEFAULT_DIG_TRAINING_CONFIG)
    parser.add_argument("--return-training-config", type=Path, default=DEFAULT_RETURN_TRAINING_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_primitive_scoped_stage_a_support_audit(
        source_results_root=args.source_results_root,
        stage_a_v1_output_root=args.stage_a_v1_output_root,
        support_audit_output_root=args.support_audit_output_root,
        dig_training_config_path=args.dig_training_config,
        return_training_config_path=args.return_training_config,
        output_root=args.output_root,
        device=str(args.device),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
