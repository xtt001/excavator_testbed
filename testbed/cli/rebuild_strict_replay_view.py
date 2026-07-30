"""Rebuild an exact-allowlist strict replay VDS with canonical text encoding."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.terrain_replay_salvage_views import (
    rebuild_strict_composite_clean_vds,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild a strict composite replay view from its manifest. The source "
            "inventory must exactly match --strict-episode-ids."
        )
    )
    parser.add_argument("--source-view-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--strict-episode-ids",
        type=int,
        nargs="+",
        required=True,
        help="Exact source episode identity allowlist; no extras or omissions allowed.",
    )
    args = parser.parse_args()
    report = rebuild_strict_composite_clean_vds(
        source_view_dir=args.source_view_dir,
        output_dir=args.output_dir,
        strict_episode_ids=args.strict_episode_ids,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
