"""tb-virtualize-images — compact HDF5 archives by VDS-linking images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-virtualize-images",
        description=(
            "Create compact HDF5 copies that keep low-dimensional datasets "
            "local while replacing /observations/images/* with VDS links back "
            "to the canonical source episodes."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input episode_N.hdf5 file or directory containing episode_*.hdf5.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output HDF5 file or dataset directory.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output episode files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively process primitive subdirectories and preserve layout.",
    )
    parser.add_argument(
        "--indices",
        type=int,
        nargs="+",
        default=None,
        help="Only virtualize selected episode indices when --input is a directory.",
    )
    parser.add_argument(
        "--absolute-source-paths",
        action="store_true",
        help="Write absolute VDS source paths instead of relative paths.",
    )
    parser.add_argument(
        "--source-prefix",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help=(
            "Rewrite provenance source paths before creating VDS links. Repeat "
            "for multiple prefixes, e.g. /data/archive=/fastdata/archive."
        ),
    )
    parser.add_argument(
        "--fallback-source-dir",
        type=Path,
        default=None,
        help=(
            "Use this source directory for full-episode inputs that do not "
            "carry provenance metadata. Episode filenames are matched by id."
        ),
    )
    parser.add_argument(
        "--no-copy-json-sidecars",
        action="store_true",
        help="Do not copy *.json sidecars when processing a directory.",
    )
    args = parser.parse_args()

    from testbed.data.virtualize_images import (
        virtualize_dataset_images,
        virtualize_episode_images,
    )

    rewrites = [_parse_rewrite(value) for value in args.source_prefix]

    if args.input.is_file():
        stats = [
            virtualize_episode_images(
                args.input,
                args.output,
                overwrite=bool(args.overwrite),
                source_prefix_rewrites=rewrites,
                fallback_source_dir=args.fallback_source_dir,
                relative_paths=not bool(args.absolute_source_paths),
            )
        ]
    else:
        stats = virtualize_dataset_images(
            args.input,
            args.output,
            overwrite=bool(args.overwrite),
            source_prefix_rewrites=rewrites,
            fallback_source_dir=args.fallback_source_dir,
            relative_paths=not bool(args.absolute_source_paths),
            episode_ids=args.indices,
            recursive=bool(args.recursive),
            copy_json_sidecars=not bool(args.no_copy_json_sidecars),
        )

    payload = {
        "input": str(args.input),
        "output": str(args.output),
        "episodes": len(stats),
        "datasets": sum(item.dataset_count for item in stats),
        "image_datasets": sum(item.image_dataset_count for item in stats),
        "virtualized_image_bytes": sum(item.virtualized_image_bytes for item in stats),
        "copied_logical_bytes": sum(item.copied_logical_bytes for item in stats),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def _parse_rewrite(value: str):
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source-prefix must be OLD=NEW")
    old, new = value.split("=", 1)
    if not old or not new:
        raise argparse.ArgumentTypeError("--source-prefix must be OLD=NEW")
    from testbed.data.virtualize_images import SourcePrefixRewrite

    return SourcePrefixRewrite(old=Path(old), new=Path(new))


if __name__ == "__main__":
    main()
