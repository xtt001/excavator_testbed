"""CLI for building rollout-review evidence reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from testbed.eval.rollout_review import write_rollout_review


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-rollout-review",
        description="Build a rollout review JSON report from an eval results directory.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        required=True,
        help="Eval results directory containing rollout_manifest.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to <results-dir>/rollout_review.json.",
    )
    args = parser.parse_args()

    output_path = write_rollout_review(
        results_dir=args.results_dir,
        output=args.output,
    )
    print(output_path)


if __name__ == "__main__":
    main()
