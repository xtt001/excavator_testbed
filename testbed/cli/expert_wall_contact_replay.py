"""CLI for the diagnostic Strict-18 expert wall-contact replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.expert_wall_contact_replay import (
    run_expert_wall_contact_replay,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m testbed.cli.expert_wall_contact_replay",
        description=(
            "Run the prepared 18-source recorded-action wall-contact audit "
            "exactly once per source."
        ),
    )
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--measurement", type=Path, required=True)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--tb-replay", default="tb-replay")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    result = run_expert_wall_contact_replay(
        schedule_path=args.schedule,
        measurement_path=args.measurement,
        attempt_root=args.attempt_root,
        config_path=args.config,
        tb_replay_executable=str(args.tb_replay),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
