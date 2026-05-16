"""Build V2.2 operator-first enriched raw wrappers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.operator_first_v2_2 import build_operator_first_dataset
from testbed.data.vds import (
    EPISODE_STORAGE_MODES,
    STORAGE_MODE_VDS,
    update_current_symlink,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-operator-first-v2_2",
        description=(
            "Add operator-first cut-corridor fields and dig_cut_tokens to an "
            "existing V2.2 relabeled dataset without modifying the source HDF5."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Input relabeled dataset containing episode_*.hdf5 and /v2 labels.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output root for operator-first enriched wrapper episodes.",
    )
    parser.add_argument(
        "--storage-mode",
        type=str,
        choices=EPISODE_STORAGE_MODES,
        default=STORAGE_MODE_VDS,
        help="vds keeps large tensors virtual; copy materializes a full dataset.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output root that already contains episode files.",
    )
    parser.add_argument(
        "--current-symlink",
        type=Path,
        default=None,
        help=(
            "Optional current-candidate symlink to update after a successful build. "
            "Existing real directories are never replaced."
        ),
    )
    args = parser.parse_args()

    summary = build_operator_first_dataset(
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
                "dig_cut_token_dim": summary["dig_cut_token_dim"],
                "training_tier_counts": summary["training_tier_counts"],
                "effective_deposit_delta_kg": summary[
                    "effective_deposit_delta_kg"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
