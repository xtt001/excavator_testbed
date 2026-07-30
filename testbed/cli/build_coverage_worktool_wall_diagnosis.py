"""Build a frozen 2D-guard versus typed-wall root-cause report."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_worktool_wall_diagnosis import (
    build_coverage_worktool_wall_diagnosis,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bounded-validation", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    artifact = build_coverage_worktool_wall_diagnosis(
        bounded_validation_path=args.bounded_validation,
        output_dir=args.output_dir,
    )
    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
