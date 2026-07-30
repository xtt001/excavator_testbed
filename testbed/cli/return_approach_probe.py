"""CLI for the Strict-18 return-approach single-factor diagnostic."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.return_approach_probe import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_QPOS_SUPPORT_AUDIT,
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_SOURCE_MANIFEST,
    DEFAULT_SOURCE_REPORT,
    DEFAULT_SOURCE_ROLLOUT,
    DEFAULT_SOURCE_SUMMARY,
    collect_return_approach_probe,
    prepare_return_approach_probe,
    run_return_approach_probe,
    validate_return_approach_probe,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-return-approach-probe",
        description=(
            "Audit v7, prepare, validate, run once, or collect the "
            "diagnostic boom-axis return approach probe."
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
        "--qpos-support-audit",
        type=Path,
        default=DEFAULT_QPOS_SUPPORT_AUDIT,
    )
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
        result = prepare_return_approach_probe(
            source_config_path=args.source_config,
            source_rollout_path=args.source_rollout,
            source_summary_path=args.source_summary,
            source_report_path=args.source_report,
            source_manifest_path=args.source_manifest,
            qpos_support_audit_path=args.qpos_support_audit,
            output_root=args.output_root,
        )
    elif args.command == "validate":
        result = validate_return_approach_probe(args.manifest)
    elif args.command == "run-once":
        result = run_return_approach_probe(
            manifest_path=args.manifest,
            cwd=args.cwd,
        )
    else:
        result = collect_return_approach_probe(
            manifest_path=args.manifest,
        )
    print(
        json.dumps(
            {
                "schema": result.get("schema", result.get("probe_schema")),
                "status": result["status"],
                "attempt_id": result["attempt_id"],
                "termination_category": result.get(
                    "termination_category",
                    "",
                ),
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"prepared", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
