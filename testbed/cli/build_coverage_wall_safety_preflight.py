"""Build the no-overwrite A0 coverage wall-safety preflight artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.coverage_wall_safety_preflight import (
    build_coverage_wall_safety_preflight,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-coverage-wall-safety-preflight",
        description=(
            "Validate the strict prior's six conservative 2D wall-clearance "
            "classes before an A0 Unity rollout."
        ),
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-state-hdf5", type=Path, required=True)
    parser.add_argument("--unity-scene", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    artifact = build_coverage_wall_safety_preflight(
        config_path=args.config,
        env_state_hdf5_path=args.env_state_hdf5,
        unity_scene_path=args.unity_scene,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "output": str(
                    (
                        args.output_dir
                        / "coverage_wall_safety_preflight_v1.json"
                    ).resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
