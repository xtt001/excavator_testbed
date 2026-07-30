"""CLI for the independent exactly-once seed-2 wall-contact B2 probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.wall_contact_session_gap_probe import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_ATTEMPT,
    DEFAULT_SOURCE_CONFIG,
    collect_wall_contact_session_gap_probe,
    prepare_wall_contact_session_gap_probe,
    run_wall_contact_session_gap_probe,
    validate_wall_contact_session_gap_probe,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-wall-contact-session-gap-probe",
        description=(
            "Prepare, run exactly once, or collect the diagnostic seed-2 "
            "B2 session-gap probe without retries or HDF5."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument(
        "--source-config",
        type=Path,
        default=DEFAULT_SOURCE_CONFIG,
    )
    prepare.add_argument(
        "--source-attempt",
        type=Path,
        default=DEFAULT_SOURCE_ATTEMPT,
    )
    prepare.add_argument("--expected-reset-state", type=Path)
    prepare.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )

    for name in ("validate", "run-once", "collect"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        if name == "run-once":
            command.add_argument("--cwd", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        result = prepare_wall_contact_session_gap_probe(
            source_config_path=args.source_config,
            source_attempt_path=args.source_attempt,
            expected_reset_state_path=args.expected_reset_state,
            output_root=args.output_root,
        )
    elif args.command == "validate":
        result = validate_wall_contact_session_gap_probe(args.manifest)
    elif args.command == "run-once":
        result = run_wall_contact_session_gap_probe(
            manifest_path=args.manifest,
            cwd=args.cwd,
        )
    else:
        result = collect_wall_contact_session_gap_probe(
            manifest_path=args.manifest,
        )
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "status": result["status"],
                "attempt_id": result["attempt_id"],
                "outcome": result.get("outcome", ""),
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"prepared", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
