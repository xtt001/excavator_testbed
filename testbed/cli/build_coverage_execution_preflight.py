"""Build the fresh-reset plus corrected-replan exact-tuple preflight."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_replan_replay import (
    build_coverage_execution_preflight,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-hdf5", required=True)
    parser.add_argument("--rollout-jsonl", required=True)
    parser.add_argument("--resolved-config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--initial-dig-step-id", type=int, default=137)
    parser.add_argument("--pre-contact-step-id", type=int, default=2935)
    parser.add_argument("--replan-step-id", type=int, default=2987)
    parser.add_argument(
        "--depth-exhausted-physical-cell-id",
        type=int,
        default=5,
    )
    args = parser.parse_args()
    artifact = build_coverage_execution_preflight(
        rollout_hdf5_path=args.rollout_hdf5,
        rollout_jsonl_path=args.rollout_jsonl,
        resolved_config_path=args.resolved_config,
        output_dir=args.output_dir,
        initial_dig_step_id=args.initial_dig_step_id,
        pre_contact_step_id=args.pre_contact_step_id,
        replan_step_id=args.replan_step_id,
        depth_exhausted_physical_cell_id=(
            args.depth_exhausted_physical_cell_id
        ),
    )
    print(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=True))


if __name__ == "__main__":
    main()
