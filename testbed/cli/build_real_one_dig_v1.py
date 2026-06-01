"""tb-build-real-one-dig-v1 - build cropped real one-dig training windows."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from testbed.data.real_one_dig import REAL_ONE_DIG_SOURCE_EPISODE_IDS

log = logging.getLogger(__name__)


def _parse_episode_ids(values: list[str] | None) -> list[int]:
    if not values:
        return list(REAL_ONE_DIG_SOURCE_EPISODE_IDS)
    episode_ids: list[int] = []
    for value in values:
        if ":" in value:
            start_raw, end_raw = value.split(":", 1)
            start = int(start_raw)
            end = int(end_raw)
            if end < start:
                raise argparse.ArgumentTypeError(f"Invalid episode range: {value}")
            episode_ids.extend(range(start, end + 1))
        else:
            episode_ids.append(int(value))
    return episode_ids


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="tb-build-real-one-dig-v1",
        description=(
            "Convert successful real excavator one-dig recordings into cropped, "
            "training-compatible HDF5 windows with decoded raw RGB FPV images."
        ),
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("/media/pingfan/EXTERNAL_USB/real_teleop_v1"),
        help="Directory containing source real episode_*.hdf5 files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/real_one_dig_v1_windows"),
        help="Directory for converted episode_*.hdf5 windows.",
    )
    parser.add_argument(
        "--episode-ids",
        nargs="+",
        default=None,
        help="Source episode ids or inclusive ranges. Default: 13:21.",
    )
    parser.add_argument(
        "--camera",
        default="fpv",
        help="Encoded camera name to decode. Default: fpv.",
    )
    parser.add_argument(
        "--preserve-source-indices",
        action="store_true",
        help="Write output episode ids as 13..21 instead of reindexing to 0..8.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing converted output files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute crop windows and stats without writing converted files.",
    )
    parser.add_argument(
        "--compression",
        default="lzf",
        choices=("lzf", "gzip", "none"),
        help="Compression for decoded raw RGB image chunks. Default: lzf.",
    )
    parser.add_argument(
        "--pre-action-context-steps",
        type=int,
        default=25,
        help="Steps kept before the first nonzero raw_action row.",
    )
    parser.add_argument(
        "--go-home-margin-steps",
        type=int,
        default=25,
        help="Steps dropped before the first nonzero go_home_commanded_action row.",
    )
    parser.add_argument(
        "--active-eps",
        type=float,
        default=1e-6,
        help="Absolute action threshold used to detect nonzero rows.",
    )
    args = parser.parse_args()

    from testbed.data.real_one_dig import build_real_one_dig_dataset

    episode_ids = _parse_episode_ids(args.episode_ids)
    results = build_real_one_dig_dataset(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        episode_ids=episode_ids,
        camera_name=args.camera,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        reindex=not args.preserve_source_indices,
        compression=args.compression,
        pre_action_context_steps=args.pre_action_context_steps,
        go_home_margin_steps=args.go_home_margin_steps,
        active_eps=args.active_eps,
    )

    log.info("Processed %d real one-dig source episode(s).", len(results))
    for result in results:
        log.info(
            "source episode_%d -> episode_%d: T=%d, window=[%d,%d), %.2fs, wrote=%s",
            result.source_episode_id,
            result.output_episode_id,
            result.output_steps,
            result.start_index,
            result.end_index_exclusive,
            result.duration_s,
            result.wrote_file,
        )
    if not args.dry_run:
        log.info("Converted dataset written to %s", args.output_dir)
        log.info("Summary written to %s", args.output_dir / "conversion_summary.json")


if __name__ == "__main__":
    main()
