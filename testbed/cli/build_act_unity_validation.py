"""Build per-reset ACT Unity validation records from one eval results root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_unity_validation import (
    build_act_unity_validation_records,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive no-overwrite act_unity_closed_loop_validation_v1 records "
            "from real 107D Unity rollout JSONL/HDF5 artifacts."
        )
    )
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-rollout-count", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=1000)
    args = parser.parse_args()

    records = build_act_unity_validation_records(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        expected_rollout_count=args.expected_rollout_count,
        seed_base=args.seed_base,
    )
    print(
        json.dumps(
            {
                "status": "built",
                "record_count": len(records),
                "output_dir": str(args.output_dir.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
