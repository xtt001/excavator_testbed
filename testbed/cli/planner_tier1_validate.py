"""Validate Tier 1 decision-structure research packages."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from testbed.planner.decision_structure.tier1_validation import (
    Tier1ValidationError,
    validate_tier1_package,
    write_report_json,
    write_report_markdown,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tb-planner-tier1-validate",
        description="Validate offline Tier 1 decision-structure research packages.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a Tier 1 package and optional gold example assumptions.",
    )
    validate_parser.add_argument(
        "--package",
        type=Path,
        required=True,
        help="Tier 1 validation package directory.",
    )
    validate_parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Write machine-readable validation report JSON.",
    )
    validate_parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Write Markdown validation report.",
    )

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _validate(args: argparse.Namespace) -> int:
    try:
        report = validate_tier1_package(args.package)
    except Tier1ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.output_json is not None:
        write_report_json(args.output_json, report)
    if args.output_md is not None:
        write_report_markdown(args.output_md, report)
    if args.output_json is None and args.output_md is None:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
