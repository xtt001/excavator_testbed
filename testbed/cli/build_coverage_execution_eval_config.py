"""Build a no-overwrite exact-tuple A0 evaluation config."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_execution_eval_config import (
    SUPPORTED_PURPOSES,
    build_coverage_execution_eval_config,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--strict-execution-library", required=True)
    parser.add_argument("--strict-execution-library-sha256", required=True)
    parser.add_argument("--worktool-sweep-artifact", required=True)
    parser.add_argument("--worktool-sweep-artifact-sha256", required=True)
    parser.add_argument(
        "--worktool-sweep-pose-library-sha256",
        required=True,
    )
    parser.add_argument("--return-transition-artifact", required=True)
    parser.add_argument(
        "--return-transition-artifact-sha256",
        required=True,
    )
    parser.add_argument(
        "--purpose",
        required=True,
        choices=sorted(SUPPORTED_PURPOSES),
    )
    args = parser.parse_args()
    config = build_coverage_execution_eval_config(
        base_config_path=args.base_config,
        output_path=args.output_path,
        run_root=args.run_root,
        strict_execution_library_path=args.strict_execution_library,
        strict_execution_library_sha256=(
            args.strict_execution_library_sha256
        ),
        worktool_sweep_artifact_path=args.worktool_sweep_artifact,
        worktool_sweep_artifact_sha256=(
            args.worktool_sweep_artifact_sha256
        ),
        worktool_sweep_pose_library_sha256=(
            args.worktool_sweep_pose_library_sha256
        ),
        return_transition_artifact_path=(
            args.return_transition_artifact
        ),
        return_transition_artifact_sha256=(
            args.return_transition_artifact_sha256
        ),
        purpose=args.purpose,
    )
    print(
        json.dumps(
            {
                "output_path": args.output_path,
                "purpose": args.purpose,
                "num_rollouts": config["eval"]["num_rollouts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
