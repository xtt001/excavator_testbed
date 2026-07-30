"""CLI for the Strict-18 return-handoff owner diagnostic."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.return_handoff_owner_diagnostic import (
    TARGET_COMPLETED_DUMPS,
)
from testbed.eval.return_handoff_owner_probe import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_SOURCE_MANIFEST,
    DEFAULT_SOURCE_REPORT,
    DEFAULT_SOURCE_ROLLOUT,
    DEFAULT_SOURCE_SUMMARY,
    collect_return_handoff_owner_probe,
    prepare_return_handoff_owner_probe,
    reanalyze_return_handoff_owner_probe,
    run_return_handoff_owner_probe,
    validate_return_handoff_owner_probe,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-return-handoff-owner-probe",
        description=(
            "Replay v7 handoff owners and run one request-local "
            "bounded multi-shovel diagnostic."
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
        "--source-rollout",
        type=Path,
        default=DEFAULT_SOURCE_ROLLOUT,
    )
    prepare.add_argument(
        "--source-summary",
        type=Path,
        default=DEFAULT_SOURCE_SUMMARY,
    )
    prepare.add_argument(
        "--source-report",
        type=Path,
        default=DEFAULT_SOURCE_REPORT,
    )
    prepare.add_argument(
        "--source-manifest",
        type=Path,
        default=DEFAULT_SOURCE_MANIFEST,
    )
    prepare.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    prepare.add_argument(
        "--target-completed-dumps",
        type=int,
        default=TARGET_COMPLETED_DUMPS,
    )
    for name in ("validate", "run-once", "collect", "reanalyze"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        if name == "run-once":
            command.add_argument("--cwd", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        result = prepare_return_handoff_owner_probe(
            source_config_path=args.source_config,
            source_rollout_path=args.source_rollout,
            source_summary_path=args.source_summary,
            source_report_path=args.source_report,
            source_manifest_path=args.source_manifest,
            output_root=args.output_root,
            target_completed_dumps=args.target_completed_dumps,
        )
    elif args.command == "validate":
        result = validate_return_handoff_owner_probe(args.manifest)
    elif args.command == "run-once":
        result = run_return_handoff_owner_probe(
            manifest_path=args.manifest,
            cwd=args.cwd,
        )
    elif args.command == "collect":
        result = collect_return_handoff_owner_probe(
            manifest_path=args.manifest,
        )
    else:
        result = reanalyze_return_handoff_owner_probe(
            manifest_path=args.manifest,
        )
    bounded = result.get("bounded_rollout", {})
    print(
        json.dumps(
            {
                "schema": result.get("schema", ""),
                "status": result.get("status", ""),
                "attempt_id": result.get("attempt_id", ""),
                "completed_dump_count": bounded.get(
                    "completed_dump_count"
                ),
                "termination_category": bounded.get(
                    "termination_category",
                    "",
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
