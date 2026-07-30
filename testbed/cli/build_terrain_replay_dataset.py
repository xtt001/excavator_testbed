"""CLI for the fixed calibrated first-passing terrain replay dataset."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.terrain_replay_dataset_builder import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_REPLAY_CONFIG,
    build_replay_preflight,
    build_selected_terrain_replay_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tb-build-terrain-replay-dataset")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Fixed no-overwrite output root (default: {DEFAULT_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--replay-config",
        type=Path,
        default=DEFAULT_REPLAY_CONFIG,
        help="Recording/replay YAML whose AGX and boundary contracts are reused.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume only when the complete stored run contract matches.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run readonly source/runtime/disk checks without creating output.",
    )
    parser.add_argument(
        "--stop-after-smokes",
        action="store_true",
        help="Run only episode_28, episode_1, and episode_19; resume for the batch.",
    )
    parser.add_argument(
        "--continue-after-smoke-semantic-failure",
        action="store_true",
        help=(
            "Resume a halted smoke run only when every exhausted smoke attempt "
            "passed its process/HDF5 contract and failed only the semantic gate."
        ),
    )
    parser.add_argument(
        "--skip-postprocess",
        action="store_true",
        help="Operational recovery option: defer label/clean VDS generation.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.preflight_only:
        result = build_replay_preflight(replay_config=args.replay_config)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["pass"] else 2
    result = build_selected_terrain_replay_dataset(
        output_root=args.output_root,
        replay_config=args.replay_config,
        resume=bool(args.resume),
        stop_after_smokes=bool(args.stop_after_smokes),
        continue_after_smoke_semantic_failure=bool(
            args.continue_after_smoke_semantic_failure
        ),
        run_postprocess=not bool(args.skip_postprocess),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"complete_24_of_24", "smokes_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
