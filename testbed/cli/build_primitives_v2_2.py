"""Build V2.2 dig/carry/dump/return primitive datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.primitives_v2_2 import build_primitive_datasets
from testbed.data.transition_v2_1 import CLEAN_PROFILE_STAGE5


def _default_output_root(workskill_name: str) -> str:
    if workskill_name.endswith("_workskill"):
        return f"{workskill_name[:-len('_workskill')]}_primitives_v2_2"
    return f"{workskill_name}_primitives_v2_2"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-primitives-v2_2",
        description=(
            "Build V2.2 primitive datasets by splitting a V2.1 workskill dataset "
            "into dig/carry/dump and full V2.1 raw datasets into return."
        ),
    )
    parser.add_argument(
        "--workskill-dir",
        type=Path,
        required=True,
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
    args = parser.parse_args()

    output_root = (
        args.output_root
        if args.output_root is not None
        else args.workskill_dir.parent / _default_output_root(args.workskill_dir.name)
    )
    summary = build_primitive_datasets(
        workskill_dir=args.workskill_dir,
        raw_dirs=args.raw_dir,
        output_root=output_root,
        require_return=not args.skip_return,
        return_max_transition_len=args.return_max_transition_len,
        return_clean_profile=args.return_clean_profile,
    )

    print(
        json.dumps(
            {
                "output_root": summary["output_root"],
                "primitives": summary["primitives"],
                "reject_counts": summary["reject_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
