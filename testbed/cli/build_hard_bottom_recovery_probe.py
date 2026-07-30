"""Build one hard-bottom recovery probe record from a live rollout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.hard_bottom_recovery_probe import (
    build_hard_bottom_recovery_probe,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-hard-bottom-recovery-probe",
        description=(
            "Validate contact, two neutral acknowledgements, ACT restart, "
            "scripted clearance, fresh replan, and exhausted-cell exclusion."
        ),
    )
    parser.add_argument("--rollout-jsonl", type=Path, required=True)
    parser.add_argument("--reset-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    record = build_hard_bottom_recovery_probe(
        rollout_jsonl_path=args.rollout_jsonl,
        reset_id=args.reset_id,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "schema": record["schema"],
                "status": record["status"],
                "hard_bottom_event_count": record[
                    "hard_bottom_event_count"
                ],
                "output": str(args.output.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
