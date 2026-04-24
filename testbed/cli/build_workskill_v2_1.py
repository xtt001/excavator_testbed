"""Build a sibling cropped Stage-3 workskill dataset from relabeled V2.1 data."""

from __future__ import annotations

import argparse
from pathlib import Path

from testbed.data.workskill_v2_1 import (
    CLEAN_PROFILE_STAGE5,
    CLEAN_PROFILE_STAGE5_BALANCED,
    CLEAN_PROFILE_STAGE5_CLEANEST,
    CLEAN_PROFILE_STAGE5_STRICT,
    build_workskill_dataset,
)


def _default_workskill_name(dataset_name: str, *, clean_profile: str | None = None) -> str:
    if clean_profile == CLEAN_PROFILE_STAGE5_CLEANEST:
        if dataset_name.endswith("_v2_1_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v4"
        if dataset_name.endswith("_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v4"
        return f"{dataset_name}_workskill_clean_v4"
    if clean_profile == CLEAN_PROFILE_STAGE5_BALANCED:
        if dataset_name.endswith("_v2_1_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v3b"
        if dataset_name.endswith("_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v3b"
        return f"{dataset_name}_workskill_clean_v3b"
    if clean_profile == CLEAN_PROFILE_STAGE5_STRICT:
        if dataset_name.endswith("_v2_1_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v3"
        if dataset_name.endswith("_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v3"
        return f"{dataset_name}_workskill_clean_v3"
    if clean_profile == CLEAN_PROFILE_STAGE5:
        if dataset_name.endswith("_v2_1_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v2"
        if dataset_name.endswith("_relabeled"):
            return f"{dataset_name[:-len('_relabeled')]}_workskill_clean_v2"
        return f"{dataset_name}_workskill_clean_v2"
    if dataset_name.endswith("_v2_1_relabeled"):
        return f"{dataset_name[:-len('_relabeled')]}_workskill"
    if dataset_name.endswith("_relabeled"):
        return f"{dataset_name[:-len('_relabeled')]}_workskill"
    return f"{dataset_name}_workskill"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-workskill-v2_1",
        description=(
            "Build a sibling cropped workskill dataset by extracting "
            "qualified_dig_start -> dump_end windows from a relabeled V2.1 dataset."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing relabeled episode_*.hdf5 files with /v2 data.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory for cropped workskill episodes. "
            "Default: <dataset-dir>_workskill sibling directory."
        ),
    )
    parser.add_argument(
        "--clean-profile",
        type=str,
        default=None,
        choices=[
            CLEAN_PROFILE_STAGE5,
            CLEAN_PROFILE_STAGE5_STRICT,
            CLEAN_PROFILE_STAGE5_BALANCED,
            CLEAN_PROFILE_STAGE5_CLEANEST,
        ],
        help=(
            "Optional quality-gated workskill build profile. "
            f"Use {CLEAN_PROFILE_STAGE5!r}, {CLEAN_PROFILE_STAGE5_STRICT!r}, "
            f"{CLEAN_PROFILE_STAGE5_BALANCED!r} or {CLEAN_PROFILE_STAGE5_CLEANEST!r} "
            "to keep only high-quality cycles."
        ),
    )
    args = parser.parse_args()

    dataset_dir = args.dataset_dir
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else dataset_dir.parent / _default_workskill_name(
            dataset_dir.name,
            clean_profile=args.clean_profile,
        )
    )

    written = build_workskill_dataset(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        clean_profile=args.clean_profile,
    )
    print(
        f"Built {written} workskill episode(s) from {dataset_dir} into sibling dataset {output_dir}"
    )


if __name__ == "__main__":
    main()
