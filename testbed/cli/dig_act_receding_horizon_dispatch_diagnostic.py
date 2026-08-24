"""CLI for the opt-in offline Dig ACT dispatch diagnostic."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.dig_receding_horizon_runtime import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_COMPARISON_ARTIFACT,
    DEFAULT_REANCHOR_DECISION,
    DEFAULT_STRUCTURE_DECISION,
    DEFAULT_VARIANT_COUNT,
    run_diagnostic_dry_run,
    run_offline_dispatch_diagnostic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare frozen legacy ACT temporal aggregation with an opt-in "
            "latest-chunk first-action Dig diagnostic. No backend is called."
        )
    )
    parser.add_argument(
        "--execute-offline-diagnostic",
        action="store_true",
        help="explicitly opt in to frozen offline inference; default is off",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the immutable contract without loading ACT or any backend",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--reanchor-decision",
        type=Path,
        default=DEFAULT_REANCHOR_DECISION,
    )
    parser.add_argument(
        "--structure-decision",
        type=Path,
        default=DEFAULT_STRUCTURE_DECISION,
    )
    parser.add_argument(
        "--comparison-artifact",
        type=Path,
        default=DEFAULT_COMPARISON_ARTIFACT,
    )
    parser.add_argument("--variant-count", type=int, default=DEFAULT_VARIANT_COUNT)
    parser.add_argument(
        "--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES
    )
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--projection-device", default="cpu")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run:
        result = run_diagnostic_dry_run(
            variant_count=args.variant_count,
            bootstrap_resamples=args.bootstrap_resamples,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.execute_offline_diagnostic:
        parser.error(
            "diagnostic is default-off; pass --execute-offline-diagnostic or --dry-run"
        )
    if args.output_dir is None:
        parser.error("--output-dir is required for an executed diagnostic")
    result = run_offline_dispatch_diagnostic(
        output_dir=args.output_dir,
        reanchor_decision_path=args.reanchor_decision,
        structure_decision_path=args.structure_decision,
        comparison_artifact_path=args.comparison_artifact,
        variant_count=args.variant_count,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_seed=args.bootstrap_seed,
        device=args.device,
        projection_device=args.projection_device,
    )
    print(json.dumps(result["decision"], indent=2, sort_keys=True))
    print(f"output_dir={result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
