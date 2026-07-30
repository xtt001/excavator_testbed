"""Build no-overwrite configs for the bounded ACT causal live matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_regression_live_matrix import (
    build_act_regression_live_configs,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-act-regression-live-matrix",
        description=(
            "Build the locked interleaved 3x4 F0/D1/C1/DC1 bounded-probe "
            "configs without changing the A0 source config."
        ),
    )
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--plan-matrix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_act_regression_live_configs(
        base_config_path=args.base_config,
        plan_matrix_path=args.plan_matrix,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "schema": manifest["schema"],
                "status": manifest["status"],
                "run_count": len(manifest["schedule"]),
                "manifest_path": manifest["manifest_path"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
