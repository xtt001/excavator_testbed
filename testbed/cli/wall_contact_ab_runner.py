"""CLI for the exactly-once Strict-18 paired wall-contact diagnostic."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.wall_contact_ab_runner import (
    collect_paired_ab_attempt_set,
    reextract_paired_ab_attempt_set,
    run_paired_ab_schedule,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-wall-contact-ab-runner",
        description=(
            "Run, collect, or postprocess-only reextract the six "
            "diagnostic wall-contact A/B attempts without retries or HDF5."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-schedule")
    run.add_argument("--schedule", type=Path, required=True)
    run.add_argument("--attempt-set-output", type=Path, required=True)
    run.add_argument("--cwd", type=Path)

    collect = commands.add_parser("collect")
    collect.add_argument("--schedule", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)

    reextract = commands.add_parser("reextract")
    reextract.add_argument("--schedule", type=Path, required=True)
    reextract.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-schedule":
        result = run_paired_ab_schedule(
            schedule_path=args.schedule,
            attempt_set_output_path=args.attempt_set_output,
            cwd=args.cwd,
        )
    elif args.command == "collect":
        result = collect_paired_ab_attempt_set(
            schedule_path=args.schedule,
            output_path=args.output,
        )
    else:
        result = reextract_paired_ab_attempt_set(
            schedule_path=args.schedule,
            output_dir=args.output_dir,
        )
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "status": result["status"],
                "attempt_count": result["attempt_count"],
                "failed_attempt_ids": result["failed_attempt_ids"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
