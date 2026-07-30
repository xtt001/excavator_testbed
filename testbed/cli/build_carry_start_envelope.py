"""Build the strict-18 carry-start handoff envelope artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.handoff_envelope import (
    CARRY_START_ENVELOPE_SCHEMA,
    build_carry_start_envelope,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-carry-start-envelope",
        description=(
            "Build carry_start_envelope_v1 from the strict-18 carry train "
            "partition. Existing output is never overwritten."
        ),
    )
    parser.add_argument(
        "--split-path",
        type=Path,
        required=True,
        help="Path to carry_source_split.yaml.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        required=True,
        help="New carry_start_envelope_v1 JSON path.",
    )
    args = parser.parse_args()
    artifact_path = build_carry_start_envelope(
        split_path=args.split_path,
        output_path=args.output_path,
    )
    print(
        json.dumps(
            {
                "artifact_path": str(artifact_path),
                "schema": CARRY_START_ENVELOPE_SCHEMA,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
