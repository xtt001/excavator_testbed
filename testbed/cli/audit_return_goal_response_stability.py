"""Run the offline audit for immutable invalid Return Stage-A v2 pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import DEFAULT_SOURCE_RESULTS_ROOT
from testbed.eval.return_goal_response_stability_audit import (
    OUTPUT_ROOT_NAME,
    run_return_goal_response_stability_audit,
)

DEFAULT_STAGE_A_V2_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "act_goal_condition_sensitivity_v2_return"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_SOURCE_RESULTS_ROOT.parent / OUTPUT_ROOT_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-return-goal-response-stability",
        description=(
            "Audit the two immutable Return goal_response_invalid Stage-A v2 pairs. "
            "This command is teacher-forced and diagnostic-only: it never changes "
            "the 80 percent gate, runtime policy, Unity, training, or machine control."
        ),
    )
    parser.add_argument(
        "--stage-a-v2-output-root",
        type=Path,
        default=DEFAULT_STAGE_A_V2_OUTPUT_ROOT,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_return_goal_response_stability_audit(
        stage_a_v2_output_root=args.stage_a_v2_output_root,
        output_root=args.output_root,
        device=str(args.device),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
