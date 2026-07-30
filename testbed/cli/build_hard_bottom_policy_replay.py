"""Replay M0/E1/W1 with independent checkpoint-identical ACT instances."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.hard_bottom_policy_replay import (
    build_hard_bottom_policy_replay,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-hard-bottom-policy-replay",
        description=(
            "Run teacher-forced M0/E1/W1 replay with one independently reset "
            "ACT instance per target. This command never starts Unity."
        ),
    )
    parser.add_argument("--rollout-hdf5", type=Path, required=True)
    parser.add_argument("--rollout-jsonl", type=Path, required=True)
    parser.add_argument("--goal-comparison", type=Path, required=True)
    parser.add_argument("--eval-config", type=Path, required=True)
    parser.add_argument("--dig-checkpoint", type=Path, required=True)
    parser.add_argument("--dig-stats", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    replay = build_hard_bottom_policy_replay(
        rollout_hdf5_path=args.rollout_hdf5,
        rollout_jsonl_path=args.rollout_jsonl,
        goal_comparison_path=args.goal_comparison,
        eval_config_path=args.eval_config,
        dig_checkpoint_path=args.dig_checkpoint,
        dig_stats_path=args.dig_stats,
        output_dir=args.output_dir,
        device=args.device,
    )
    print(
        json.dumps(
            {
                "schema": replay["schema"],
                "status": replay["status"],
                "target_order": replay["target_order"],
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
