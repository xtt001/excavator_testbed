"""CLI for the strict-train normalized qpos path companion artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.coverage_pose_paths import (
    build_coverage_pose_path_library,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-coverage-pose-paths",
        description=(
            "Build the no-overwrite 374-record strict-train dig qpos path "
            "artifact consumed by Unity's conservative 3D worktool sweep."
        ),
    )
    parser.add_argument("--dig-primitives-dir", required=True)
    parser.add_argument("--split-path", required=True)
    parser.add_argument("--execution-library-path", required=True)
    parser.add_argument("--normalization-path", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    output = build_coverage_pose_path_library(
        dig_primitives_dir=Path(args.dig_primitives_dir),
        split_path=Path(args.split_path),
        execution_library_path=Path(args.execution_library_path),
        normalization_path=Path(args.normalization_path),
        output_path=Path(args.output_path),
    )
    artifact = json.loads(output.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "output_path": str(output),
                "schema": str(artifact["schema"]),
                "sample_count": int(artifact["sample_count"]),
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
