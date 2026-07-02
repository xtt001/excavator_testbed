"""Run the eval-only predicted residual A/B artifact pipeline from JSON."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.terrain_residual_ab_artifact_pipeline import (
    build_and_write_predicted_residual_ab_artifacts,
)


REQUIRED_REQUEST_FIELDS = [
    "source_rollout_path",
    "results_root",
    "target_spec",
    "cycle_budget",
    "candidate_generation_options",
    "candidate_constraint_options",
    "scoring_weights",
    "effect_geometry",
    "payload_capacity_m3",
    "residual_cut_intent_runtime_source_inputs",
    "selection_policy",
    "protected_evidence_roots",
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tb-terrain-residual-ab-artifacts",
        description=(
            "Run the explicit eval-only predicted residual A/B artifact pipeline."
        ),
    )
    parser.add_argument(
        "--request-json",
        type=Path,
        required=True,
        help="JSON object containing explicit pipeline inputs.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for the pipeline result JSON. Defaults to stdout.",
    )
    args = parser.parse_args(argv)

    request, request_errors = _read_request(args.request_json)
    if request_errors:
        result = _invalid_request_result(args.request_json, request_errors)
        _emit_result(result, args.output_json)
        return 2

    result = build_and_write_predicted_residual_ab_artifacts(**request)
    _emit_result(result, args.output_json)
    return 0 if result.get("status") == "present" else 1


def _read_request(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"request JSON read failed: {exc}"]
    if not isinstance(parsed, Mapping):
        return {}, ["request JSON must contain an object"]

    request = {str(key): value for key, value in parsed.items()}
    missing = [field for field in REQUIRED_REQUEST_FIELDS if field not in request]
    if missing:
        return request, [f"request JSON missing required fields: {missing}"]
    return request, []


def _invalid_request_result(path: Path, errors: list[str]) -> dict[str, Any]:
    return {
        "schema": "terrain_residual_predicted_ab_artifact_pipeline_cli_v1",
        "source": "explicit_predicted_residual_ab_artifact_pipeline_cli",
        "status": "invalid_request",
        "offline_only": True,
        "request_json_path": str(path),
        "validation_errors": list(errors),
        "non_goal_statuses": {
            "simulation_status": "not_run",
            "production_planner_integration_status": "not_integrated",
            "rollout_review_schema_integration_status": "not_integrated",
            "runtime_action_status": "not_created",
            "official_success_semantics_status": "not_defined",
            "official_threshold_status": "not_defined",
            "calibrated_model_fallback_status": "not_invented",
        },
    }


def _emit_result(result: Mapping[str, Any], output_json: Path | None) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output_json is None:
        print(payload, end="")
        return
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
