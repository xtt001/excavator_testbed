"""Write frozen Return temporal-dispatch contributor forensics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.cli.audit_act_goal_condition_sensitivity import DEFAULT_SOURCE_RESULTS_ROOT
from testbed.eval.return_temporal_dispatch_forensics_runner import (
    run_return_temporal_dispatch_forensics_artifact,
)

DEFAULT_RETURN_STABILITY_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "return_goal_response_stability_audit_v1"
)
DEFAULT_OUTPUT_ROOT = (
    DEFAULT_SOURCE_RESULTS_ROOT.parent / "return_temporal_dispatch_forensics_v2"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-audit-return-temporal-dispatch-forensics",
        description=(
            "Explain frozen Return temporal contributor suppression. This is "
            "diagnostic-only and never changes a dispatch strategy or runtime."
        ),
    )
    parser.add_argument(
        "--return-stability-output-root",
        type=Path,
        default=DEFAULT_RETURN_STABILITY_OUTPUT_ROOT,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_return_temporal_dispatch_forensics_artifact(
        return_stability_output_root=args.return_stability_output_root,
        output_root=args.output_root,
        device=str(args.device),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
