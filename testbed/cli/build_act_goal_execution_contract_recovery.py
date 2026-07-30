"""Build the offline planner-to-ACT goal execution contract audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_goal_execution_contract_recovery import (
    MANIFEST_FILENAME,
    build_act_goal_execution_contract_recovery,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-act-goal-execution-contract-recovery",
        description=(
            "Combine frozen cycle-six, teacher-forced ACT, and strict-train "
            "execution evidence. This command never starts Unity."
        ),
    )
    parser.add_argument("--cycle6-diagnosis", type=Path, required=True)
    parser.add_argument("--goal-comparison", type=Path, required=True)
    parser.add_argument("--policy-replay", type=Path, required=True)
    parser.add_argument("--strict-execution-library", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--production-replan-pre", type=Path)
    parser.add_argument("--production-replan-post", type=Path)
    args = parser.parse_args()

    artifact = build_act_goal_execution_contract_recovery(
        cycle6_diagnosis_path=args.cycle6_diagnosis,
        goal_comparison_path=args.goal_comparison,
        policy_replay_path=args.policy_replay,
        strict_execution_library_path=args.strict_execution_library,
        production_replan_pre_path=args.production_replan_pre,
        production_replan_post_path=args.production_replan_post,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "primary": artifact["classification"]["primary"],
                "formal_a0_1x10_allowed": artifact["gate"][
                    "formal_a0_1x10_allowed"
                ],
                "output": str(
                    (args.output_dir / MANIFEST_FILENAME).resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
