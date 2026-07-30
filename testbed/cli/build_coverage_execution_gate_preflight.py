"""Build the calibrated full-gate exact-tuple production preflight."""

from __future__ import annotations

import argparse
import json

from testbed.eval.coverage_execution_gate_preflight import (
    build_coverage_execution_gate_preflight,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved-config", required=True)
    parser.add_argument("--functional-results-dir", required=True)
    parser.add_argument("--bounded-results-dir", required=True)
    parser.add_argument(
        "--tuple-start-alignment-artifact",
        required=True,
    )
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
    artifact = build_coverage_execution_gate_preflight(
        resolved_config_path=args.resolved_config,
        functional_results_dir=args.functional_results_dir,
        bounded_results_dir=args.bounded_results_dir,
        tuple_start_alignment_artifact_path=(
            args.tuple_start_alignment_artifact
        ),
        output_dir=args.output_dir,
        initial_dig_step_id=args.initial_dig_step_id,
        pre_contact_step_id=args.pre_contact_step_id,
        replan_step_id=args.replan_step_id,
        depth_exhausted_physical_cell_id=(
            args.depth_exhausted_physical_cell_id
        ),
    )
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "output_dir": args.output_dir,
                "gate_decision": artifact["gate_decision"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
