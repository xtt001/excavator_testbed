"""Build the no-overwrite tuple-start/paired-return diagnosis."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_return_alignment import (
    build_tuple_start_alignment_diagnosis,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-results-dir", required=True)
    parser.add_argument("--original-eval-config", required=True)
    parser.add_argument("--production-preflight-config", required=True)
    parser.add_argument("--return-transition-artifact", required=True)
    parser.add_argument("--execution-library", required=True)
    parser.add_argument("--worktool-sweep-artifact", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    artifact = build_tuple_start_alignment_diagnosis(
        rollout_results_dir=args.rollout_results_dir,
        original_eval_config_path=args.original_eval_config,
        production_preflight_config_path=(args.production_preflight_config),
        return_transition_artifact_path=(args.return_transition_artifact),
        execution_library_path=args.execution_library,
        worktool_sweep_artifact_path=args.worktool_sweep_artifact,
        output_dir=args.output_dir,
        device=args.device,
    )
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "blocker": artifact["gate_decision"]["blocker"],
                "bounded_live_allowed": artifact["gate_decision"][
                    "bounded_live_allowed"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
