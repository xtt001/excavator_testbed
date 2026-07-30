"""Offline residual cut-intent adapter for existing dig-cut tokens."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner

SCHEMA = "residual_cut_intent_dig_cut_token_v1"
SOURCE = "explicit_residual_cut_intent_dig_cut_token"
DEFAULT_PROFILE = "explicit_residual_cut_intent_dig_cut_token"


def build_residual_cut_intent_dig_cut_token(
    cut_intent: Mapping[str, Any],
    *,
    cell_centers_m: Mapping[Any, Any],
    direction_vectors: Mapping[str, Any],
    bucket_length_m: Any,
    payload_kg: Any,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build existing dig-cut raw fields and tokens from explicit eval cut intent."""

    record, cut_intent_errors = _cut_intent_record(cut_intent)
    candidate_id = _candidate_id(record)
    anchor_cell_index = _parse_nonnegative_integer(record.get("anchor_cell_index"))
    direction = _direction(record)
    candidate_depth_m = _parse_positive_float(record.get("candidate_depth_m"))
    bucket_length = _parse_positive_float(bucket_length_m)
    payload = _parse_nonnegative_float(payload_kg)

    validation_errors = list(cut_intent_errors)
    if not candidate_id:
        validation_errors.append("cut_intent must include candidate_id")
    if anchor_cell_index is None:
        validation_errors.append(
            "cut_intent anchor_cell_index must be a non-negative integer"
        )
    if not direction:
        validation_errors.append("cut_intent must include direction")
    if candidate_depth_m is None:
        validation_errors.append(
            "cut_intent candidate_depth_m must be finite and positive"
        )
    if bucket_length is None:
        validation_errors.append("bucket_length_m must be finite and positive")
    if payload is None:
        validation_errors.append("payload_kg must be finite and non-negative")

    entry_x_z: tuple[float, float] | None = None
    direction_x_z: tuple[float, float] | None = None
    if anchor_cell_index is not None:
        entry_x_z, center_errors = _cell_center(cell_centers_m, anchor_cell_index)
        validation_errors.extend(center_errors)
    if direction:
        direction_x_z, direction_errors = _normalized_direction(
            direction_vectors,
            direction,
        )
        validation_errors.extend(direction_errors)

    if validation_errors:
        return _result(
            status="invalid",
            profile=profile,
            candidate_id=candidate_id,
            raw_fields={},
            dig_cut_tokens=[],
            validation_errors=validation_errors,
        )

    assert entry_x_z is not None
    assert direction_x_z is not None
    assert candidate_depth_m is not None
    assert bucket_length is not None
    assert payload is not None

    entry_x, entry_z = entry_x_z
    dir_x, dir_z = direction_x_z
    exit_x = entry_x + dir_x * bucket_length
    exit_z = entry_z + dir_z * bucket_length
    raw_fields: dict[str, float | int] = {
        "operator_entry_x_m": float(entry_x),
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": float(entry_z),
        "operator_exit_x_m": float(exit_x),
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": float(exit_z),
        "operator_cut_direction_x": float(dir_x),
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": float(dir_z),
        "operator_cut_length_m": float(bucket_length),
        "operator_cut_depth_peak_m": float(candidate_depth_m),
        "operator_cut_payload_gain_kg": float(payload),
        "operator_effective_deposit_delta_kg": float(payload),
        "operator_cut_valid": 1,
    }
    plan = DigCutTokenPlanner(prior={}).plan_from_raw_fields(
        raw_fields,
        source=SOURCE,
    )
    return _result(
        status="present",
        profile=profile,
        candidate_id=candidate_id,
        raw_fields=dict(plan.raw_fields),
        dig_cut_tokens=[float(value) for value in plan.token.tolist()],
        validation_errors=[],
    )


def _result(
    *,
    status: str,
    profile: str,
    candidate_id: str,
    raw_fields: Mapping[str, float | int],
    dig_cut_tokens: Sequence[float],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "candidate_id": str(candidate_id),
        "raw_fields": dict(raw_fields),
        "dig_cut_tokens": list(dig_cut_tokens),
        "validation_errors": list(validation_errors),
        "adapter_conventions": {
            "entry_y_m": "zero_height_offline_adapter_convention",
            "exit_y_m": "zero_height_offline_adapter_convention",
        },
        "dig_cut_token_contract": {
            "dim": int(DIG_CUT_TOKEN_DIM),
            "order": [
                "entry_x_norm",
                "entry_z_norm",
                "exit_x_norm",
                "exit_z_norm",
                "cut_direction_x",
                "cut_direction_z",
                "cut_length_norm",
                "cut_depth_peak_norm",
                "cut_payload_gain_norm",
                "cut_valid",
            ],
            "position_scale_m": float(DIG_CUT_POSITION_SCALE_M),
            "length_scale_m": float(DIG_CUT_LENGTH_SCALE_M),
            "depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
            "payload_scale_kg": float(DIG_CUT_PAYLOAD_SCALE_KG),
        },
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(status),
    }


def _cut_intent_record(cut_intent: Any) -> tuple[Mapping[str, Any], list[str]]:
    if not isinstance(cut_intent, Mapping):
        return {}, ["cut_intent must be a mapping"]
    nested = cut_intent.get("cut_intent")
    if isinstance(nested, Mapping):
        return nested, []
    return cut_intent, []


def _candidate_id(record: Mapping[str, Any]) -> str:
    value = record.get("cut_intent_candidate_id", record.get("candidate_id", ""))
    return str(value) if value is not None else ""


def _direction(record: Mapping[str, Any]) -> str:
    value = record.get("direction", "")
    return str(value) if value is not None else ""


def _cell_center(
    cell_centers_m: Any,
    anchor_cell_index: int,
) -> tuple[tuple[float, float] | None, list[str]]:
    if not isinstance(cell_centers_m, Mapping):
        return None, ["cell_centers_m must be a mapping"]
    if anchor_cell_index in cell_centers_m:
        raw_center = cell_centers_m[anchor_cell_index]
    elif str(anchor_cell_index) in cell_centers_m:
        raw_center = cell_centers_m[str(anchor_cell_index)]
    else:
        return None, [
            f"cell_centers_m must include anchor_cell_index {anchor_cell_index}"
        ]
    center = _parse_x_z(raw_center, x_key="x_m", z_key="z_m")
    if center is None:
        return None, [
            f"cell_centers_m[{anchor_cell_index!r}] must provide finite x_m/z_m"
        ]
    return center, []


def _normalized_direction(
    direction_vectors: Any,
    direction: str,
) -> tuple[tuple[float, float] | None, list[str]]:
    if not isinstance(direction_vectors, Mapping):
        return None, ["direction_vectors must be a mapping"]
    if direction not in direction_vectors:
        return None, [f"direction_vectors must include direction {direction!r}"]
    raw_vector = direction_vectors[direction]
    vector = _parse_x_z(raw_vector, x_key="x", z_key="z")
    if vector is None:
        return None, [
            f"direction_vectors[{direction!r}] must be a finite x/z vector"
        ]
    dir_x, dir_z = vector
    norm = math.hypot(dir_x, dir_z)
    if norm <= 1.0e-9:
        return None, [f"direction_vectors[{direction!r}] must be nonzero"]
    return (dir_x / norm, dir_z / norm), []


def _parse_x_z(
    value: Any,
    *,
    x_key: str,
    z_key: str,
) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        x_value = _parse_finite_float(value.get(x_key))
        z_value = _parse_finite_float(value.get(z_key))
    elif (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 2
    ):
        x_value = _parse_finite_float(value[0])
        z_value = _parse_finite_float(value[1])
    else:
        return None
    if x_value is None or z_value is None:
        return None
    return x_value, z_value


def _parse_finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _parse_positive_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


def _parse_nonnegative_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0:
        return None
    return parsed


def _parse_nonnegative_integer(value: Any) -> int | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0:
        return None
    integer = int(parsed)
    if not math.isclose(parsed, float(integer), abs_tol=1.0e-9):
        return None
    return integer


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run_by_adapter",
        "artifact_write_status": "not_written_by_adapter",
        "production_planner_integration_status": "not_integrated_by_adapter",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_planner_mode_status": "not_created",
        "command_space_control_status": "not_defined",
        "pass_fail_status": "not_defined",
        "eval_success_status": "not_defined",
        "planner_success_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses(status: str) -> dict[str, str]:
    return {
        "cut_intent_status": "validated" if status == "present" else "invalid",
        "cell_centers_m_status": "explicit_input",
        "direction_vectors_status": "explicit_input",
        "bucket_length_m_status": "explicit_input",
        "payload_kg_status": "explicit_input",
        "dig_cut_token_builder_status": (
            "existing_plan_from_raw_fields" if status == "present" else "not_called"
        ),
    }
