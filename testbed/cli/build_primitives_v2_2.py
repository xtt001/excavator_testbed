"""Build V2.2 dig/carry/dump/return primitive datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.primitives_v2_2 import build_primitive_datasets
from testbed.data.primitives_v2_2 import (
    PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
    PRIMITIVE_BOUNDARY_PROFILES,
)
from testbed.data.transition_v2_1 import CLEAN_PROFILE_STAGE5
from testbed.data.vds import (
    PRIMITIVE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    update_current_symlink,
)


def _default_output_root(workskill_name: str) -> str:
    if workskill_name.endswith("_workskill"):
        return f"{workskill_name[:-len('_workskill')]}_primitives_v2_2"
    return f"{workskill_name}_primitives_v2_2"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-primitives-v2_2",
        description=(
            "Build V2.2 primitive datasets by splitting a V2.1 workskill dataset "
            "into dig/carry/dump and full V2.1 raw datasets into return. "
            "In --storage-mode vds/manifest, --workskill-dir may be omitted so "
            "Cell Entry enriched raw episodes are split directly."
        ),
    )
    parser.add_argument(
        "--workskill-dir",
        type=Path,
        required=False,
        default=None,
        help="Directory containing cropped V2.1 workskill episode_*.hdf5 files.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        action="append",
        default=[],
        help=(
            "Full refreshed V2.1 raw dataset used for return windows. "
            "Repeat this flag for multiple source roots."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=(
            "Output root containing dig/carry/dump/return subdirectories. "
            "Default: <workskill-dir>_primitives_v2_2 sibling directory."
        ),
    )
    parser.add_argument(
        "--storage-mode",
        type=str,
        choices=PRIMITIVE_STORAGE_MODES,
        default=STORAGE_MODE_COPY,
        help=(
            "copy writes full primitive episodes from --workskill-dir; vds writes "
            "wrapper episodes; manifest writes only window_manifest.json/summary.json."
        ),
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
    parser.add_argument(
        "--skip-return",
        action="store_true",
        help="Build only dig/carry/dump. Intended for unit tests or partial diagnostics.",
    )
    parser.add_argument(
        "--return-max-transition-len",
        type=int,
        default=None,
        help="Optional hard cap for return windows, forwarded to V2.1 transition logic.",
    )
    parser.add_argument(
        "--return-clean-profile",
        type=str,
        choices=[CLEAN_PROFILE_STAGE5],
        default=None,
        help="Optional V2.1 transition clean profile for return windows.",
    )
    parser.add_argument(
        "--boundary-profile",
        type=str,
        choices=PRIMITIVE_BOUNDARY_PROFILES,
        default=PRIMITIVE_BOUNDARY_PROFILE_DEFAULT,
        help=(
            "Primitive ownership boundary profile. The default keeps the strict "
            "middle-handoff rule; v2_2_effect_release_fallback can be used for "
            "new-env pilots where no approach_dump label is emitted but a stable "
            "release onset and good final dump are present; v2_4_5_spatial_mass "
            "uses material-cycle mass/geometry ownership and emits return envelopes."
        ),
    )
    args = parser.parse_args()
    if args.workskill_dir is None and not args.raw_dir:
        parser.error("Either --workskill-dir or at least one --raw-dir is required.")
    output_root = (
        args.output_root
        if args.output_root is not None
        else (
            args.workskill_dir.parent / _default_output_root(args.workskill_dir.name)
            if args.workskill_dir is not None
            else args.raw_dir[0].parent / f"{args.raw_dir[0].name}_primitives_v2_2"
        )
    )
    summary = build_primitive_datasets(
        workskill_dir=args.workskill_dir,
        raw_dirs=args.raw_dir,
        output_root=output_root,
        require_return=not args.skip_return,
        return_max_transition_len=args.return_max_transition_len,
        return_clean_profile=args.return_clean_profile,
        boundary_profile=args.boundary_profile,
        storage_mode=str(args.storage_mode),
        overwrite=bool(args.overwrite),
    )
    if args.current_symlink is not None:
        update_current_symlink(
            symlink_path=args.current_symlink,
            target_path=output_root,
        )

    print(
        json.dumps(
            {
                "output_root": summary["output_root"],
                "storage_mode": summary["storage_mode"],
                "primitives": summary["primitives"],
                "window_manifest_path": summary.get("window_manifest_path"),
                "carry_qc": summary.get("carry_qc", {}),
                "dump_qc": summary.get("dump_qc", {}),
                "return_qc": summary.get("return_qc", {}),
                "training_tier_counts": summary.get("training_tier_counts", {}),
                "reject_counts": summary["reject_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
