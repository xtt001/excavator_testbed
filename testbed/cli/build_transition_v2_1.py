"""Build a sibling cropped transition-skill dataset from relabeled V2.1 data."""

from __future__ import annotations

import argparse
from pathlib import Path

from testbed.data.transition_v2_1 import CLEAN_PROFILE_STAGE5, build_transition_dataset


def _default_transition_name(
    dataset_name: str,
    *,
    max_transition_len: int | None = None,
    clean_profile: str | None = None,
) -> str:
    if dataset_name.endswith("_v2_1_relabeled"):
        base = f"{dataset_name[:-len('_relabeled')]}_transition"
    elif dataset_name.endswith("_relabeled"):
        base = f"{dataset_name[:-len('_relabeled')]}_transition"
    else:
        base = f"{dataset_name}_transition"
    if clean_profile == CLEAN_PROFILE_STAGE5:
        return f"{base}_clean_v2"
    if max_transition_len is not None:
        return f"{base}_clean_l{int(max_transition_len)}"
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-transition-v2_1",
        description=(
            "Build a sibling cropped transition dataset by extracting "
            "dump_end -> next qualified_dig_start windows from a relabeled V2.1 dataset."
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
            "Output directory for cropped transition episodes. "
            "Default: <dataset-dir>_transition sibling directory."
        ),
    )
    parser.add_argument(
        "--max-transition-len",
        type=int,
        default=None,
        help=(
            "Optional hard cap on transition window length. "
            "Windows longer than this are skipped. "
            "Default: keep all transition windows."
        ),
    )
    parser.add_argument(
        "--clean-profile",
        type=str,
        choices=[CLEAN_PROFILE_STAGE5],
        default=None,
        help=(
            "Optional named cleaning profile. "
            f"Current supported value: {CLEAN_PROFILE_STAGE5!r}. "
            "When enabled, the builder applies Stage-5 behavior filters "
            "and uses the default sibling name *_transition_clean_v2."
        ),
    )
    args = parser.parse_args()

    dataset_dir = args.dataset_dir
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else dataset_dir.parent / _default_transition_name(
            dataset_dir.name,
            max_transition_len=args.max_transition_len,
            clean_profile=args.clean_profile,
        )
    )

    written = build_transition_dataset(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        max_transition_len=args.max_transition_len,
        clean_profile=args.clean_profile,
    )
    print(
        f"Built {written} transition episode(s) from {dataset_dir} into sibling dataset {output_dir}"
    )


if __name__ == "__main__":
    main()
