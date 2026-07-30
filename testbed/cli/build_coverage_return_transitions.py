"""CLI for the strict-train exact tuple return-transition artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.coverage_return_transitions import (
    build_coverage_return_transition_library,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-coverage-return-transitions",
        description=(
            "Build the no-overwrite strict-train gold return transition "
            "library paired to immutable coverage dig tuples."
        ),
    )
    parser.add_argument("--return-primitives-dir", required=True)
    parser.add_argument("--return-split-path", required=True)
    parser.add_argument("--dig-primitives-dir", required=True)
    parser.add_argument("--dig-split-path", required=True)
    parser.add_argument("--execution-library-path", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    output = build_coverage_return_transition_library(
        return_primitives_dir=Path(args.return_primitives_dir),
        return_split_path=Path(args.return_split_path),
        dig_primitives_dir=Path(args.dig_primitives_dir),
        dig_split_path=Path(args.dig_split_path),
        execution_library_path=Path(args.execution_library_path),
        output_path=Path(args.output_path),
    )
    artifact = json.loads(output.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "output_path": str(output),
                "schema": str(artifact["schema"]),
                "gold_return_sample_count": int(
                    artifact["gold_return_sample_count"]
                ),
                "paired_post_return_tuple_count": int(
                    artifact["paired_post_return_tuple_count"]
                ),
                "input_sha256": str(
                    artifact["source_lock"]["input_sha256"]
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
