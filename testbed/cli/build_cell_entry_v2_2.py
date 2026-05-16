"""Build V2.2 Cell Entry enriched raw datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.cell_entry_v2_2 import build_cell_entry_dataset
from testbed.data.vds import (
    EPISODE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    update_current_symlink,
)
from testbed.planner.cell_entry import LONG_AXIS_X, LONG_AXIS_Z, CellGridSpec


def _default_output_dir(dataset_dir: Path) -> Path:
    return dataset_dir.parent / f"{dataset_dir.name}_cell_entry_v2_2"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-cell-entry-v2_2",
        description=(
            "Copy a raw dataset and attach scripted 3x2 Cell Entry "
            "planned/actual/audit fields under /v2. Use --storage-mode vds "
            "for the YuLong mainline so images stay in immutable raw roots."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing raw episode_*.hdf5 files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output dataset directory. Default: <dataset-dir>_cell_entry_v2_2 sibling.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory that already contains episodes.",
    )
    parser.add_argument(
        "--storage-mode",
        type=str,
        choices=EPISODE_STORAGE_MODES,
        default=STORAGE_MODE_COPY,
        help="copy writes full episodes; vds writes lightweight HDF5 wrappers.",
    )
    parser.add_argument(
        "--current-symlink",
        type=Path,
        default=None,
        help=(
            "Optional symlink to update after a successful build, e.g. "
            "data/yulong_v2_2_current_cell_entry. Existing real directories "
            "are never replaced."
        ),
    )
    parser.add_argument(
        "--half-long-m",
        type=float,
        default=CellGridSpec.half_long_m,
        help="DigArea half extent along the long axis, used for planner envelopes.",
    )
    parser.add_argument(
        "--half-short-m",
        type=float,
        default=CellGridSpec.half_short_m,
        help="DigArea half extent along the short axis, used for planner envelopes.",
    )
    parser.add_argument(
        "--long-axis",
        type=int,
        choices=[LONG_AXIS_X, LONG_AXIS_Z],
        default=CellGridSpec.long_axis,
        help="DigArea local long axis: 0 for x, 2 for z.",
    )
    parser.add_argument(
        "--entry-margin-m",
        type=float,
        default=CellGridSpec.entry_margin_m,
        help="Extra footprint margin around the selected cell entry envelope.",
    )
    args = parser.parse_args()

    grid = CellGridSpec(
        half_long_m=float(args.half_long_m),
        half_short_m=float(args.half_short_m),
        long_axis=int(args.long_axis),
        entry_margin_m=float(args.entry_margin_m),
    )
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else _default_output_dir(args.dataset_dir)
    )
    summary = build_cell_entry_dataset(
        dataset_dir=args.dataset_dir,
        output_dir=output_dir,
        grid=grid,
        overwrite=bool(args.overwrite),
        storage_mode=str(args.storage_mode),
    )
    if args.current_symlink is not None:
        update_current_symlink(
            symlink_path=args.current_symlink,
            target_path=output_dir,
        )
    print(
        json.dumps(
            {
                "output_dir": summary["output_dir"],
                "version": summary["version"],
                "episode_count": summary["episode_count"],
                "storage_mode": summary["storage_mode"],
                "cycle_count": summary["cycle_count"],
                "planner_ok_rate": summary["planner_ok_rate"],
                "geometry_available_cycle_rate": summary[
                    "geometry_available_cycle_rate"
                ],
                "target_cell_match_rate": summary["target_cell_match_rate"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
