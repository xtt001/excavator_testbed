"""Build the offline M0/E1/W1 hard-bottom goal comparison artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.hard_bottom_goal_comparison import (
    DEFAULT_EXPECTED_EXEMPLAR_ID,
    DEFAULT_EXPECTED_SOURCE_EPISODE_ID,
    DEFAULT_TARGET_CELL_ID,
    build_hard_bottom_goal_comparison,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-hard-bottom-goal-comparison",
        description=(
            "Compare the failed cycle-6 median target, the nearest strict-train "
            "real exemplar, and the immutable C1 wall-safe target on recorded "
            "observations. This command never starts Unity."
        ),
    )
    parser.add_argument("--rollout-hdf5", type=Path, required=True)
    parser.add_argument("--rollout-jsonl", type=Path, required=True)
    parser.add_argument("--planner-trace", type=Path, required=True)
    parser.add_argument("--state-exemplars", type=Path, required=True)
    parser.add_argument("--dig-source-split", type=Path, required=True)
    parser.add_argument("--dig-dataset-dir", type=Path, required=True)
    parser.add_argument("--wall-safe-goal", type=Path, required=True)
    parser.add_argument("--wall-safe-goal-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cycle-index", type=int, default=5)
    parser.add_argument(
        "--target-cell-id",
        type=int,
        default=DEFAULT_TARGET_CELL_ID,
    )
    parser.add_argument(
        "--expected-exemplar-id",
        default=DEFAULT_EXPECTED_EXEMPLAR_ID,
    )
    parser.add_argument(
        "--expected-source-episode-id",
        type=int,
        default=DEFAULT_EXPECTED_SOURCE_EPISODE_ID,
    )
    parser.add_argument(
        "--skip-train-support",
        action="store_true",
        help=(
            "Skip train-only nearest-expert/OOD analysis and record an explicit "
            "blocked_not_requested status."
        ),
    )
    args = parser.parse_args()

    result = build_hard_bottom_goal_comparison(
        rollout_hdf5_path=args.rollout_hdf5,
        rollout_jsonl_path=args.rollout_jsonl,
        planner_trace_path=args.planner_trace,
        exemplar_path=args.state_exemplars,
        dig_split_path=args.dig_source_split,
        dig_dataset_dir=args.dig_dataset_dir,
        wall_safe_goal_path=args.wall_safe_goal,
        wall_safe_goal_sha256=args.wall_safe_goal_sha256,
        output_dir=args.output_dir,
        cycle_index=args.cycle_index,
        target_cell_id=args.target_cell_id,
        expected_exemplar_id=args.expected_exemplar_id,
        expected_source_episode_id=args.expected_source_episode_id,
        compute_train_support=not args.skip_train_support,
    )
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "status": result["status"],
                "evidence_scope": result["evidence_scope"],
                "target_order": result["target_order"],
                "output": str(
                    (args.output_dir / "manifest.json").resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
