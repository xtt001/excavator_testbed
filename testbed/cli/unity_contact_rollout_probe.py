"""CLI for the exactly-once Unity wall-and-floor contact diagnostic."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.unity_contact_rollout_probe import (
    DEFAULT_ENVIRONMENT_MANIFEST,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_SOURCE_RESET_VALIDATION,
    DEFAULT_SOURCE_ROLLOUT,
    DEFAULT_SOURCE_SUMMARY,
    collect_unity_contact_rollout_probe,
    prepare_unity_contact_rollout_probe,
    run_unity_contact_rollout_probe,
    validate_unity_contact_rollout_probe,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-unity-contact-rollout-probe",
        description=(
            "Prepare, validate, run exactly once, or collect the Strict-18 "
            "Unity-only bucket wall/FactoryFloor contact diagnostic."
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
        "--source-reset-validation",
        type=Path,
        default=DEFAULT_SOURCE_RESET_VALIDATION,
    )
    prepare.add_argument(
        "--environment-manifest",
        type=Path,
        default=DEFAULT_ENVIRONMENT_MANIFEST,
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
        result = prepare_unity_contact_rollout_probe(
            source_config_path=args.source_config,
            source_rollout_path=args.source_rollout,
            source_summary_path=args.source_summary,
            source_reset_validation_path=args.source_reset_validation,
            environment_manifest_path=args.environment_manifest,
            output_root=args.output_root,
        )
    elif args.command == "validate":
        result = validate_unity_contact_rollout_probe(args.manifest)
    elif args.command == "run-once":
        result = run_unity_contact_rollout_probe(
            manifest_path=args.manifest,
            cwd=args.cwd,
        )
    else:
        result = collect_unity_contact_rollout_probe(
            manifest_path=args.manifest
        )
    print(
        json.dumps(
            {
                "schema": result["schema"],
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
