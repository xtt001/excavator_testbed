"""Write runner-facing residual B-branch eval request artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.terrain_residual_b_branch_eval_request import (
    write_residual_b_branch_eval_request,
)
from testbed.eval.terrain_residual_contract import official_contract_statuses

REQUIRED_REQUEST_FIELDS = [
    "current_eval_metadata_path",
    "predicted_ab_artifact_root",
    "runtime_source_path",
    "request_root",
    "planned_results_root",
    "protected_evidence_roots",
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tb-terrain-residual-b-branch-request",
        description=(
            "Write explicit runner-facing B-branch eval request artifacts."
        ),
    )
    parser.add_argument(
        "--request-json",
        type=Path,
        required=True,
        help="JSON object containing explicit B-branch request inputs.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for the request result JSON. Defaults to stdout.",
    )
    args = parser.parse_args(argv)

    request, request_errors = _read_request(args.request_json)
    if request_errors:
        result = _invalid_request_result(args.request_json, request_errors)
        _emit_result(result, args.output_json)
        return 2

    metadata, metadata_errors = _read_current_eval_metadata(
        Path(str(request["current_eval_metadata_path"]))
    )
    if metadata_errors:
        result = _invalid_request_result(args.request_json, metadata_errors)
        _emit_result(result, args.output_json)
        return 2

    result = write_residual_b_branch_eval_request(
        current_eval_metadata=metadata,
        predicted_ab_artifact_root=request["predicted_ab_artifact_root"],
        runtime_source_path=request["runtime_source_path"],
        request_root=request["request_root"],
        planned_results_root=request["planned_results_root"],
        protected_evidence_roots=request["protected_evidence_roots"],
        target_cycle_gate=request.get("target_cycle_gate"),
        profile=str(request.get("profile", "phase6g_f_residual_b_branch_eval_request")),
    )
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
    if not isinstance(request.get("protected_evidence_roots"), Sequence) or isinstance(
        request.get("protected_evidence_roots"),
        (str, bytes),
    ):
        return request, ["protected_evidence_roots must be a list"]
    return request, []


def _read_current_eval_metadata(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"current eval metadata read failed: {exc}"]
    if not isinstance(parsed, Mapping):
        return {}, ["current eval metadata must contain an object"]
    return {str(key): value for key, value in parsed.items()}, []


def _invalid_request_result(path: Path, errors: list[str]) -> dict[str, Any]:
    return {
        "schema": "terrain_residual_b_branch_eval_request_cli_v1",
        "source": "explicit_residual_b_branch_eval_request_cli",
        "status": "invalid_request",
        "offline_only": True,
        "request_json_path": str(path),
        "validation_errors": list(errors),
        "non_goal_statuses": {
            "simulation_status": "not_run",
            "branch_execution_artifact_status": "not_created",
            "production_planner_integration_status": "not_integrated",
            "rollout_review_schema_integration_status": "not_integrated",
            "runtime_action_status": "not_created",
            **official_contract_statuses(),
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
