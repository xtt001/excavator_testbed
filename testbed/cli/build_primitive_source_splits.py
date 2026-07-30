"""Build train/validation split files from primitive source identities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.primitive_source_split import write_primitive_source_splits


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split primitive windows by immutable source episode identity. The "
            "train/val source union is enforced as an exact allowlist."
        )
    )
    parser.add_argument("--primitive-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-source-ids", type=int, nargs="+", required=True)
    parser.add_argument("--val-source-ids", type=int, nargs="+", required=True)
    parser.add_argument(
        "--training-tier",
        default="gold",
        help="Only include primitive windows with this training tier (default: gold).",
    )
    args = parser.parse_args()
    paths = write_primitive_source_splits(
        primitive_root=args.primitive_root,
        output_dir=args.output_dir,
        train_source_episode_ids=args.train_source_ids,
        val_source_episode_ids=args.val_source_ids,
        required_training_tier=args.training_tier,
    )
    print(
        json.dumps(
            {name: str(path) for name, path in paths.items()},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
