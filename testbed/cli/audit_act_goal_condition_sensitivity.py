"""Run the fail-closed Strict-18 Stage-A ACT condition sensitivity audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_goal_condition_sensitivity import (
    OUTPUT_ROOT_NAME,
    run_act_goal_condition_sensitivity_audit,
)

DEFAULT_SOURCE_RESULTS_ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0/"
    "carry_dump_ownership_priority_10cycle_four_camera_reproduction_20260731_v1/"
    "run/results"
)
DEFAULT_DIG_TRAINING_CONFIG = Path(
    "testbed/configs/act_yulong_strict_replay18_four_camera_dig_qvel.yaml"
)
DEFAULT_RETURN_TRAINING_CONFIG = Path(
    "testbed/configs/act_yulong_strict_replay18_four_camera_return_envelope_qvel.yaml"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-act-goal-condition-sensitivity",
        description=(
            "Run the Strict-18 Stage-A teacher-forced ACT condition sensitivity "
            "audit. This command never runs Unity, live control, training, or 1x10."
        ),
    )
    parser.add_argument(
        "--source-results-root",
        type=Path,
        default=DEFAULT_SOURCE_RESULTS_ROOT,
        help="Immutable recorded results root containing config, JSONL, and HDF5.",
    )
    parser.add_argument(
        "--dig-training-config",
        type=Path,
        default=DEFAULT_DIG_TRAINING_CONFIG,
        help="Canonical strict-train Dig ACT config used for numeric support.",
    )
    parser.add_argument(
        "--return-training-config",
        type=Path,
        default=DEFAULT_RETURN_TRAINING_CONFIG,
        help="Canonical strict-train Return ACT config used for numeric support.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_SOURCE_RESULTS_ROOT.parent / OUTPUT_ROOT_NAME,
        help="Exclusive Stage-A evidence root; an existing path is never overwritten.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="Frozen ACT inference device (default: cuda).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_act_goal_condition_sensitivity_audit(
        source_results_root=args.source_results_root,
        dig_training_config_path=args.dig_training_config,
        return_training_config_path=args.return_training_config,
        output_root=args.output_root,
        device=str(args.device),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_root": result["output_root"],
                "manifest": result["manifest"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
