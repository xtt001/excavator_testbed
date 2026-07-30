"""Build V2.4 hindsight-goal relabel copy datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.hindsight_goal_v2_4 import build_hindsight_goal_dataset
from testbed.data.vds import (
    EPISODE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    update_current_symlink,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-hindsight-goal-v2_4",
        description=(
            "Materialize V2.4 hindsight outcome targets from an operator-first "
            "YuLong relabel root. The source HDF5 files are not modified."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Input operator-first relabel/copy root with episode_*.hdf5 files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output materialized copy root.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output root that already contains episode files.",
    )
    parser.add_argument(
        "--storage-mode",
        choices=EPISODE_STORAGE_MODES,
        default=STORAGE_MODE_COPY,
        help=(
            "copy writes full materialized relabel episodes; vds writes compact "
            "image-VDS wrappers with only hindsight fields materialized."
        ),
    )
    parser.add_argument(
        "--current-symlink",
        type=Path,
        default=None,
        help="Optional current-candidate symlink to update after a successful build.",
    )
    args = parser.parse_args()

    summary = build_hindsight_goal_dataset(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        overwrite=bool(args.overwrite),
        storage_mode=str(args.storage_mode),
    )
    if args.current_symlink is not None:
        update_current_symlink(
            symlink_path=args.current_symlink,
            target_path=args.output_dir,
        )
    print(
        json.dumps(
            {
                "output_dir": summary["output_dir"],
                "storage_mode": summary["storage_mode"],
                "episode_count": summary["episode_count"],
                "cycle_count": summary["cycle_count"],
                "dig_goal_valid_steps": summary["dig_goal_valid_steps"],
                "return_goal_valid_steps": summary["return_goal_valid_steps"],
                "depth_outcome_source_counts": summary[
                    "depth_outcome_source_counts"
                ],
                "training_tier_counts": summary["training_tier_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
