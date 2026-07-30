"""CLI for the immutable 2026-07-17 terrain cleaning pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.terrain_clean_dataset import build_terrain_clean_dataset
from testbed.data.terrain_cycle_cleaning import APPROVED_TERRAIN_DATASET_ROOT

DEFAULT_OUTPUT_ROOT = APPROVED_TERRAIN_DATASET_ROOT.with_name(
    f"{APPROVED_TERRAIN_DATASET_ROOT.name}_cycle_clean_v1"
)
DEFAULT_LABEL_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "teleop_yulong_v2_2_pro_full_task_four_camera_jpeg.yaml"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-terrain-clean-dataset",
        description=(
            "Build the no-overwrite V2.1 -> operator-first -> hindsight -> "
            "terrain-clean VDS chain for the approved 36-episode batch."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=APPROVED_TERRAIN_DATASET_ROOT,
        help=f"Hard-locked source root (default: {APPROVED_TERRAIN_DATASET_ROOT}).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"New no-overwrite output root (default: {DEFAULT_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--label-config",
        type=Path,
        default=DEFAULT_LABEL_CONFIG,
        help="V2.1 success/reward config used for contact-depth boundaries.",
    )
    parser.add_argument(
        "--episode-id",
        type=int,
        action="append",
        default=None,
        help=(
            "Optional repeatable pilot selector. The source inventory is still "
            "validated as exactly episode_0..35."
        ),
    )
    args = parser.parse_args()
    summary = build_terrain_clean_dataset(
        dataset_dir=args.dataset_dir,
        output_root=args.output_root,
        label_config_path=args.label_config,
        episode_ids=args.episode_id,
        qualified_dig_start_mode="contact_depth",
        validate_jpeg_decode=True,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
