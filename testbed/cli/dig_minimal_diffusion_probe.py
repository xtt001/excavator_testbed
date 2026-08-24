"""CLI for the default-off, offline-only minimal Dig Diffusion Policy probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.dig_diffusion_probe_runtime import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_DISPATCH_MANIFEST,
    DEFAULT_IDENTIFIABILITY_DECISION,
    DEFAULT_TRAINING_UPDATES,
    run_minimal_dp_probe,
    run_minimal_dp_probe_dry_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-probe", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--dispatch-manifest", type=Path, default=DEFAULT_DISPATCH_MANIFEST
    )
    parser.add_argument(
        "--identifiability-decision",
        type=Path,
        default=DEFAULT_IDENTIFIABILITY_DECISION,
    )
    parser.add_argument(
        "--training-updates", type=int, default=DEFAULT_TRAINING_UPDATES
    )
    parser.add_argument(
        "--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES
    )
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    parser.add_argument("--device", default="cuda")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run:
        result = run_minimal_dp_probe_dry_run(training_updates=args.training_updates)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.execute_probe:
        parser.error(
            "minimal DP probe is default-off; pass --execute-probe or --dry-run"
        )
    if args.output_dir is None:
        parser.error("--output-dir is required for an executed probe")
    result = run_minimal_dp_probe(
        output_dir=args.output_dir,
        dispatch_manifest_path=args.dispatch_manifest,
        identifiability_decision_path=args.identifiability_decision,
        training_updates=args.training_updates,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_seed=args.bootstrap_seed,
        device=args.device,
    )
    print(json.dumps(result["decision"], indent=2, sort_keys=True))
    print(f"output_dir={result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
