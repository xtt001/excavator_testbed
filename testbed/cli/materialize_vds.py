"""tb-materialize-vds — materialize HDF5 VDS episodes for faster training I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-materialize-vds",
        description=(
            "Copy HDF5 episode wrappers into regular HDF5 files, resolving VDS "
            "datasets and writing image datasets with frame-major chunks."
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
        "--image-batch-size",
        type=int,
        default=16,
        help="Number of image frames to materialize per HDF5 read/write batch.",
    )
    parser.add_argument(
        "--no-compress-images",
        action="store_true",
        help="Disable LZF compression for output image datasets.",
    )
    parser.add_argument(
        "--indices",
        type=int,
        nargs="+",
        default=None,
        help="Only materialize selected episode indices when --input is a directory.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively materialize primitive subdirectories and preserve layout.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of independent episode materialization worker processes.",
    )
    parser.add_argument(
        "--no-copy-json-sidecars",
        action="store_true",
        help="Do not copy *.json sidecars when materializing a directory.",
    )
    args = parser.parse_args()

    from testbed.data.materialize import materialize_dataset, materialize_episode

    if args.input.is_file():
        stats = [
            materialize_episode(
                args.input,
                args.output,
                overwrite=bool(args.overwrite),
                image_batch_size=int(args.image_batch_size),
                compress_images=not bool(args.no_compress_images),
            )
        ]
    else:
        stats = materialize_dataset(
            args.input,
            args.output,
            overwrite=bool(args.overwrite),
            image_batch_size=int(args.image_batch_size),
            compress_images=not bool(args.no_compress_images),
            episode_ids=args.indices,
            recursive=bool(args.recursive),
            workers=int(args.workers),
            copy_json_sidecars=not bool(args.no_copy_json_sidecars),
        )

    payload = {
        "input": str(args.input),
        "output": str(args.output),
        "episodes": len(stats),
        "datasets": sum(item.dataset_count for item in stats),
        "image_datasets": sum(item.image_dataset_count for item in stats),
        "logical_bytes": sum(item.logical_bytes for item in stats),
        "workers": int(args.workers),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
