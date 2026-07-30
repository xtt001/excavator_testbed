"""Build the frozen-start episode_168 Unity 3D sweep preflight."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_worktool_sweep_validation import (
    build_coverage_worktool_sweep_preflight,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep-artifact", required=True)
    parser.add_argument("--sweep-artifact-sha256", required=True)
    parser.add_argument("--execution-library", required=True)
    parser.add_argument("--execution-library-sha256", required=True)
    parser.add_argument("--pose-library", required=True)
    parser.add_argument("--pose-library-sha256", required=True)
    parser.add_argument("--frozen-rollout-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-cycle-index", type=int, default=1)
    args = parser.parse_args()

    artifact = build_coverage_worktool_sweep_preflight(
        sweep_artifact_path=args.sweep_artifact,
        sweep_artifact_sha256=args.sweep_artifact_sha256,
        execution_library_path=args.execution_library,
        execution_library_sha256=args.execution_library_sha256,
        pose_library_path=args.pose_library,
        pose_library_sha256=args.pose_library_sha256,
        frozen_rollout_dir=args.frozen_rollout_dir,
        output_dir=args.output_dir,
        target_cycle_index=args.target_cycle_index,
    )
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "episode_168_rejected_count": artifact[
                    "episode_168_rejected_count"
                ],
                "production_replan_allowed": artifact[
                    "production_replan_allowed"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
