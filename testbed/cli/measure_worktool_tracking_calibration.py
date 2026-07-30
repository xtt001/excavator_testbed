"""Run or finalize the bounded expert/ACT worktool tracking experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.worktool_tracking_calibration import (
    build_margin_recommendation,
    collect_live_measurement,
    write_json_exclusive,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect")
    collect.add_argument("--source-episode", required=True)
    collect.add_argument("--primitive", required=True)
    collect.add_argument("--eval-config", required=True)
    collect.add_argument("--output-dir", required=True)
    collect.add_argument(
        "--control-compatibility-profile",
        default="production",
    )

    recommend = subparsers.add_parser("recommend")
    recommend.add_argument("--live-manifest", required=True)
    recommend.add_argument("--geometry-measurement", required=True)
    recommend.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "collect":
        artifact = collect_live_measurement(
            source_episode_path=args.source_episode,
            primitive_path=args.primitive,
            eval_config_path=args.eval_config,
            output_dir=args.output_dir,
            control_compatibility_profile=(
                None
                if args.control_compatibility_profile in {"", "none"}
                else args.control_compatibility_profile
            ),
        )
    else:
        live = json.loads(
            Path(args.live_manifest).read_text(encoding="utf-8")
        )
        geometry = json.loads(
            Path(args.geometry_measurement).read_text(encoding="utf-8")
        )
        artifact = build_margin_recommendation(
            live_manifest=live,
            geometry_measurement=geometry,
        )
        write_json_exclusive(args.output, artifact)

    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
