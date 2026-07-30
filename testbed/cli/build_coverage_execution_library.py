"""Build the strict-train coverage execution library."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.coverage_execution_library import (
    build_coverage_execution_library,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-coverage-execution-library",
        description=(
            "Build the immutable 374-row strict-train coverage execution "
            "library and supervision-tail audit."
        ),
    )
    parser.add_argument(
        "--dig-primitives-dir",
        required=True,
        help="Materialized strict primitives_copy/dig directory.",
    )
    parser.add_argument(
        "--split-path",
        required=True,
        help="Strict dig_source_split.yaml.",
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="No-overwrite output JSON path.",
    )
    parser.add_argument(
        "--coverage-prior-path",
        default="",
        help=(
            "Optional surface-depth planner prior used to map each raw entry "
            "to a return-envelope cell."
        ),
    )
    args = parser.parse_args()

    output = build_coverage_execution_library(
        dig_primitives_dir=Path(args.dig_primitives_dir),
        split_path=Path(args.split_path),
        output_path=Path(args.output_path),
        coverage_prior_path=(
            None
            if not str(args.coverage_prior_path).strip()
            else Path(args.coverage_prior_path)
        ),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "output_path": str(output),
                "schema": payload["schema"],
                "sample_count": int(payload["sample_count"]),
                "local_max_minus_token_gt_0_02_count": int(
                    payload["tail_audit"][
                        "local_max_minus_token_gt_0_02_count"
                    ]
                ),
                "execution_tail_plane_depth_reserve_p50_m": float(
                    payload["tail_audit"][
                        "execution_tail_plane_depth_reserve_m"
                    ]["p50"]
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
