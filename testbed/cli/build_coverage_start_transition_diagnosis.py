"""Build and finalize the offline tuple-start transition geometry diagnosis."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_start_transition_diagnosis import (
    build_start_transition_geometry_diagnosis,
    build_start_transition_measurement_input,
)


def _prepare(args: argparse.Namespace) -> dict[str, object]:
    return build_start_transition_measurement_input(
        execution_library_path=args.execution_library,
        return_transition_artifact_path=args.return_transition_artifact,
        production_preflight_path=args.production_preflight,
        cycle0_source_episode_path=args.cycle0_source_episode,
        post_return_source_episode_path=args.post_return_source_episode,
        frozen_cycle0_rollout_path=args.frozen_cycle0_rollout,
        frozen_cycle0_observation_step=args.frozen_cycle0_observation_step,
        post_return_dig_end_step=args.post_return_dig_end_step,
        output_dir=args.output_dir,
    )


def _finalize(args: argparse.Namespace) -> dict[str, object]:
    return build_start_transition_geometry_diagnosis(
        measurement_input_path=args.measurement_input,
        unity_measurement_path=args.unity_measurement,
        output_dir=args.output_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--execution-library", required=True)
    prepare.add_argument("--return-transition-artifact", required=True)
    prepare.add_argument("--production-preflight", required=True)
    prepare.add_argument("--cycle0-source-episode", required=True)
    prepare.add_argument("--post-return-source-episode", required=True)
    prepare.add_argument("--frozen-cycle0-rollout", required=True)
    prepare.add_argument(
        "--frozen-cycle0-observation-step",
        type=int,
        required=True,
    )
    prepare.add_argument(
        "--post-return-dig-end-step",
        type=int,
        required=True,
    )
    prepare.add_argument("--output-dir", required=True)
    prepare.set_defaults(handler=_prepare)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--measurement-input", required=True)
    finalize.add_argument("--unity-measurement", required=True)
    finalize.add_argument("--output-dir", required=True)
    finalize.set_defaults(handler=_finalize)

    args = parser.parse_args()
    artifact = args.handler(args)
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "output_dir": args.output_dir,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
