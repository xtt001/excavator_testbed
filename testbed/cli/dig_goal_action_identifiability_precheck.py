"""CLI for the default-off Dig goal/action data-identifiability precheck."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.dig_goal_action_identifiability_runtime import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_DISPATCH_MANIFEST,
    run_goal_action_identifiability_precheck,
    run_identifiability_dry_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-precheck",
        action="store_true",
        help="explicitly opt in; the precheck is default-off",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the contract without reading datasets or starting training",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--dispatch-manifest", type=Path, default=DEFAULT_DISPATCH_MANIFEST
    )
    parser.add_argument(
        "--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES
    )
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run:
        result = run_identifiability_dry_run(
            bootstrap_resamples=args.bootstrap_resamples
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.execute_precheck:
        parser.error("precheck is default-off; pass --execute-precheck or --dry-run")
    if args.output_dir is None:
        parser.error("--output-dir is required for an executed precheck")
    result = run_goal_action_identifiability_precheck(
        output_dir=args.output_dir,
        dispatch_manifest_path=args.dispatch_manifest,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_seed=args.bootstrap_seed,
    )
    print(json.dumps(result["decision"], indent=2, sort_keys=True))
    print(f"output_dir={result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
