"""Validate the three-reset exact-tuple bounded live gate."""

from __future__ import annotations

import argparse
import json

from testbed.eval.actual_tuple_bounded_validation import (
    build_actual_tuple_bounded_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--strict-execution-library", required=True)
    parser.add_argument("--strict-execution-library-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    artifact = build_actual_tuple_bounded_validation(
        results_dir=args.results_dir,
        strict_execution_library_path=args.strict_execution_library,
        strict_execution_library_sha256=(
            args.strict_execution_library_sha256
        ),
        output_dir=args.output_dir,
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
