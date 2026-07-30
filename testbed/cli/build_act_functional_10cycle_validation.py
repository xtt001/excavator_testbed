"""Build offline ACT ten-cycle functional validation artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_functional_10cycle_validation import (
    MANIFEST_SCHEMA,
    build_act_functional_10cycle_records,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-act-functional-10cycle-validation",
        description=(
            "Build no-overwrite act_functional_10cycle_validation_v1 records "
            "from rollout JSONL artifacts. This does not run Unity and does "
            "not evaluate the formal ACT freeze gate."
        ),
    )
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-rollout-count", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=1000)
    args = parser.parse_args()

    records = build_act_functional_10cycle_records(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        expected_rollout_count=args.expected_rollout_count,
        seed_base=args.seed_base,
    )
    print(
        json.dumps(
            {
                "schema": MANIFEST_SCHEMA,
                "status": "built",
                "record_count": len(records),
                "manifest_path": str(
                    (args.output_dir / "validation_manifest.json").resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
