"""Build the combined cycle-6 hard-bottom root-cause gate artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.hard_bottom_diagnosis_gate import (
    build_hard_bottom_diagnosis_gate,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-hard-bottom-diagnosis-gate",
        description=(
            "Combine frozen cycle-6 execution reconstruction, production "
            "coverage replan, and M0/E1/W1 teacher-forced evidence. This "
            "command never starts Unity."
        ),
    )
    parser.add_argument("--execution-diagnosis", type=Path, required=True)
    parser.add_argument("--coverage-replan", type=Path, required=True)
    parser.add_argument("--goal-comparison", type=Path, required=True)
    parser.add_argument("--policy-replay", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = build_hard_bottom_diagnosis_gate(
        execution_diagnosis_path=args.execution_diagnosis,
        coverage_replan_path=args.coverage_replan,
        goal_comparison_path=args.goal_comparison,
        policy_replay_path=args.policy_replay,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "status": report["status"],
                "primary_cause": report["root_cause"]["primary"],
                "formal_a0_1x10_allowed": report["gate"][
                    "formal_a0_1x10_allowed"
                ],
                "output": str(
                    (
                        args.output_dir
                        / (
                            "root_cause_report.json"
                            if args.policy_replay is None
                            else "root_cause_report_v2.json"
                        )
                    ).resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
