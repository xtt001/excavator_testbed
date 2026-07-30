"""Build the fixed four-condition ACT regression cut-plan matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_regression_plan_matrix import (
    build_act_regression_plan_matrix,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-act-regression-plan-matrix",
        description=(
            "Build no-overwrite F0/D1/C1/DC1 cycle-0/1 "
            "residual-cut-intent runtime sources from an A0 rollout."
        ),
    )
    parser.add_argument(
        "--a0-rollout-artifact",
        type=Path,
        required=True,
        help="A0 run/results directory or complete rollout JSONL.",
    )
    parser.add_argument(
        "--planner-prior",
        type=Path,
        help=(
            "Planner prior JSON. If omitted, use dig_cut_prior_path from "
            "the rollout planner trace."
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = build_act_regression_plan_matrix(
        a0_rollout_artifact_path=args.a0_rollout_artifact,
        planner_prior_path=args.planner_prior,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "schema": manifest["schema"],
                "status": manifest["status"],
                "condition_count": len(manifest["conditions"]),
                "manifest_path": manifest["manifest_path"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
