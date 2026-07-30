"""Thin CLI for the approved YuLong action-contract calibration build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.action_contract_calibration import (
    APPROVED_CLEAN_DATASET_ROOT,
    DEFAULT_CALIBRATED_OUTPUT_ROOT,
    build_action_calibrated_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-action-calibrated-dataset",
        description=(
            "Build no-overwrite current-controller-equivalent action views for "
            "the approved July 2026 YuLong clean dataset."
        ),
    )
    parser.add_argument(
        "--clean-root",
        type=Path,
        default=APPROVED_CLEAN_DATASET_ROOT,
        help=f"Approved clean input root (default: {APPROVED_CLEAN_DATASET_ROOT}).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_CALIBRATED_OUTPUT_ROOT,
        help=f"New no-overwrite output root (default: {DEFAULT_CALIBRATED_OUTPUT_ROOT}).",
    )
    args = parser.parse_args()
    if args.clean_root.expanduser().resolve() != APPROVED_CLEAN_DATASET_ROOT.resolve():
        raise ValueError(
            "CLI clean-root is hard-locked to the approved July 2026 clean dataset."
        )
    summary = build_action_calibrated_dataset(
        clean_root=args.clean_root,
        output_root=args.output_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
