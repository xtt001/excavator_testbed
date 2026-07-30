"""Run recorded-observation ACT regression diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_regression_policy_replay import (
    run_recorded_observation_diagnosis,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-act-regression-offline-diagnostic",
        description=(
            "Re-evaluate a saved cycle-1 dig stream with fresh and aggregated "
            "strict ACT actions plus train-only nearest-expert evidence."
        ),
    )
    parser.add_argument("--rollout-hdf5", type=Path, required=True)
    parser.add_argument("--rollout-jsonl", type=Path, required=True)
    parser.add_argument("--eval-config", type=Path, required=True)
    parser.add_argument("--dig-checkpoint", type=Path, required=True)
    parser.add_argument("--dig-stats", type=Path, required=True)
    parser.add_argument("--train-dataset-dir", type=Path, required=True)
    parser.add_argument("--train-split", type=Path, required=True)
    parser.add_argument("--token-variants-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    result = run_recorded_observation_diagnosis(
        rollout_hdf5_path=args.rollout_hdf5,
        rollout_jsonl_path=args.rollout_jsonl,
        eval_config_path=args.eval_config,
        dig_checkpoint_path=args.dig_checkpoint,
        dig_stats_path=args.dig_stats,
        train_dataset_dir=args.train_dataset_dir,
        train_split_path=args.train_split,
        token_variants_artifact_path=args.token_variants_json,
        output_path=args.output,
        device=args.device,
    )
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "status": result["status"],
                "frame_count": result["summary"]["count"],
                "output": str(args.output.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
if __name__ == "__main__":
    main()
