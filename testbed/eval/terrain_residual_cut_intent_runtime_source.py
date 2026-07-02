"""Build explicit residual cut-intent runtime source payloads."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.planner.primitive.token.residual_cut_intent import (
    build_residual_cut_intent_dig_cut_token,
)
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE,
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
)


DEFAULT_PROFILE = "phase6g_residual_cut_intent_runtime_source"
REQUIRED_SOURCE_INPUT_FIELDS = [
    "cell_centers_m",
    "direction_vectors",
    "bucket_length_m",
    "payload_kg",
]


def build_residual_cut_intent_runtime_source(
    *,
    predicted_b_rollout: Mapping[str, Any],
    runtime_source_inputs: Mapping[str, Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build a cycle-indexed runtime source from predicted B rollout evidence."""

    validation_errors: list[str] = []
    if not isinstance(predicted_b_rollout, Mapping):
        validation_errors.append("predicted_b_rollout must be a mapping")
        return _result(
            status="invalid",
            profile=profile,
            plans=[],
            validation_errors=validation_errors,
        )
    if predicted_b_rollout.get("status") != "present":
        validation_errors.append("predicted_b_rollout status must be present")

    if not isinstance(runtime_source_inputs, Mapping):
        validation_errors.append(
            "residual_cut_intent_runtime_source_inputs must be a mapping"
        )
        return _result(
            status="invalid",
            profile=profile,
            plans=[],
            validation_errors=validation_errors,
        )
    missing = [
        field
        for field in REQUIRED_SOURCE_INPUT_FIELDS
        if field not in runtime_source_inputs
    ]
    if missing:
        validation_errors.append(
            "residual_cut_intent_runtime_source_inputs missing required fields: "
            f"{missing}"
        )

    step_records = predicted_b_rollout.get("per_step_records")
    if not _is_sequence(step_records):
        validation_errors.append(
            "predicted_b_rollout per_step_records must be a sequence"
        )
        step_records = []
    elif not step_records:
        validation_errors.append(
            "predicted_b_rollout per_step_records must be non-empty"
        )

    plans: list[dict[str, Any]] = []
    seen_cycles: set[int] = set()
    if not validation_errors:
        for index, step_record in enumerate(step_records):
            plan, plan_errors = _build_plan_record(
                step_record,
                index=index,
                runtime_source_inputs=runtime_source_inputs,
            )
            validation_errors.extend(plan_errors)
            if plan is None:
                continue
            cycle_index = int(plan["cycle_index"])
            if cycle_index in seen_cycles:
                validation_errors.append(
                    f"per_step_records[{index}] cycle_index "
                    f"{cycle_index} is duplicated"
                )
                continue
            seen_cycles.add(cycle_index)
            plans.append(plan)

    if validation_errors:
        return _result(
            status="invalid",
            profile=profile,
            plans=[],
            validation_errors=validation_errors,
        )
    return _result(
        status="present",
        profile=profile,
        plans=plans,
        validation_errors=[],
    )


def _build_plan_record(
    step_record: Any,
    *,
    index: int,
    runtime_source_inputs: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    prefix = f"per_step_records[{index}]"
    if not isinstance(step_record, Mapping):
        return None, [f"{prefix} must be a mapping"]
    if step_record.get("status") != "present":
        return None, [f"{prefix} status must be present"]

    cycle_index = _parse_nonnegative_integer(step_record.get("step_index"))
    errors: list[str] = []
    if cycle_index is None:
        errors.append(f"{prefix} step_index must be a non-negative integer")

    cut_intent = step_record.get("cut_intent")
    if not isinstance(cut_intent, Mapping):
        errors.append(f"{prefix} cut_intent must be a mapping")
        return None, errors

    adapter_output = build_residual_cut_intent_dig_cut_token(
        cut_intent,
        cell_centers_m=runtime_source_inputs.get("cell_centers_m"),
        direction_vectors=runtime_source_inputs.get("direction_vectors"),
        bucket_length_m=runtime_source_inputs.get("bucket_length_m"),
        payload_kg=runtime_source_inputs.get("payload_kg"),
    )
    if adapter_output.get("status") != "present":
        adapter_errors = adapter_output.get("validation_errors", [])
        if _is_sequence(adapter_errors):
            errors.extend(f"{prefix}: {error}" for error in adapter_errors)
        else:
            errors.append(f"{prefix}: adapter status must be present")
        return None, errors

    candidate_id = str(adapter_output.get("candidate_id", ""))
    plan: dict[str, Any] = {
        "cycle_index": cycle_index,
        "cut_intent_candidate_id": candidate_id,
        "source": adapter_output.get("source"),
        "plan": dict(adapter_output),
    }
    fallback_reason = _fallback_reason(runtime_source_inputs, cycle_index)
    if fallback_reason:
        plan["fallback_reason"] = fallback_reason
    return plan, []


def _fallback_reason(
    runtime_source_inputs: Mapping[str, Any],
    cycle_index: int,
) -> str:
    reasons_by_cycle = runtime_source_inputs.get("fallback_reasons_by_cycle")
    if isinstance(reasons_by_cycle, Mapping):
        for key in (cycle_index, str(cycle_index)):
            if key in reasons_by_cycle:
                value = reasons_by_cycle[key]
                return str(value) if value is not None else ""
    value = runtime_source_inputs.get("fallback_reason", "")
    return str(value) if value is not None else ""


def _result(
    *,
    status: str,
    profile: str,
    plans: list[dict[str, Any]],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
        "source": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "plans": list(plans),
        "plan_count": len(plans),
        "validation_errors": list(validation_errors),
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(status),
    }


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_status": "not_created",
        "command_space_control_status": "not_created",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses(status: str) -> dict[str, str]:
    return {
        "predicted_b_rollout_source": "explicit_input",
        "cell_centers_m_source": "explicit_input",
        "direction_vectors_source": "explicit_input",
        "bucket_length_m_source": "explicit_input",
        "payload_kg_source": "explicit_input",
        "adapter_source": "explicit_residual_cut_intent_dig_cut_token",
        "runtime_source_build_status": (
            "built" if status == "present" else "invalid"
        ),
    }


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _parse_nonnegative_integer(value: Any) -> int | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0.0:
        return None
    integer = int(parsed)
    if not math.isclose(parsed, float(integer), abs_tol=1.0e-9):
        return None
    return integer


__all__ = [
    "DEFAULT_PROFILE",
    "REQUIRED_SOURCE_INPUT_FIELDS",
    "build_residual_cut_intent_runtime_source",
]
