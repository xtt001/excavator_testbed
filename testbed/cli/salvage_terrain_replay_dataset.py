"""CLI for layered salvage of the fixed seven failed terrain replays."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.terrain_replay_run_contract import DEFAULT_REPLAY_CONFIG
from testbed.eval.terrain_replay_salvage_runner import (
    DEFAULT_PARENT_RUN_ROOT,
    DEFAULT_SALVAGE_OUTPUT_ROOT,
    build_salvage_preflight,
    build_terrain_replay_salvage_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tb-salvage-terrain-replay-dataset")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_SALVAGE_OUTPUT_ROOT,
        help=f"No-overwrite salvage output root (default: {DEFAULT_SALVAGE_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--parent-root",
        type=Path,
        default=DEFAULT_PARENT_RUN_ROOT,
        help="Immutable parent replay run containing the fixed 17 strict passes.",
    )
    parser.add_argument(
        "--replay-config",
        type=Path,
        default=DEFAULT_REPLAY_CONFIG,
        help="Recording-compatible replay and label configuration.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run read-only source, parent, runtime, protocol, and disk checks.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume only when the complete stored run contract matches.",
    )
    parser.add_argument(
        "--stop-after-strict",
        action="store_true",
        help="Finish fixed-budget strict attempts but defer corrected/local salvage.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.preflight_only:
        result = build_salvage_preflight(
            replay_config=args.replay_config,
            parent_root=args.parent_root,
            verify_parent_checksums=True,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["pass"] else 2
    result = build_terrain_replay_salvage_dataset(
        output_root=args.output_root,
        replay_config=args.replay_config,
        parent_root=args.parent_root,
        resume=bool(args.resume),
        stop_after_strict=bool(args.stop_after_strict),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {
        "complete_24_of_24",
        "partial",
        "strict_phase_complete",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
