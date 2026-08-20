"""Validate pre-registered Return temporal dispatch strategies offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import (
    DEFAULT_RETURN_TRAINING_CONFIG,
    DEFAULT_SOURCE_RESULTS_ROOT,
)
from testbed.eval.return_temporal_dispatch_validation_runner import (
    run_return_temporal_dispatch_validation_from_file,
)

DEFAULT_CHECKPOINT_LINEAGE_MANIFEST = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent
    / "return_goal_response_stability_audit_v1"
    / "manifest.json"
)
DEFAULT_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "return_temporal_dispatch_validation_v1"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-return-temporal-dispatch-validation",
        description=(
            "Select a pre-registered Return temporal dispatch shadow candidate "
            "using source-disjoint held data only. This never changes runtime."
        ),
    )
    parser.add_argument(
        "--return-training-config", type=Path, default=DEFAULT_RETURN_TRAINING_CONFIG
    )
    parser.add_argument(
        "--checkpoint-lineage-manifest",
        type=Path,
        default=DEFAULT_CHECKPOINT_LINEAGE_MANIFEST,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_return_temporal_dispatch_validation_from_file(
        return_training_config_path=args.return_training_config,
        checkpoint_lineage_manifest_path=args.checkpoint_lineage_manifest,
        output_root=args.output_root,
        device=str(args.device),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
