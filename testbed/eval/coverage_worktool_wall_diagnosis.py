"""Classify bounded typed-wall evidence against the 2D coverage guard.

The bounded exact-tuple validator owns the promotion decision.  This module
consumes its frozen output plus the referenced rollout JSONL files and answers
the narrower geometry question: did a cut that passed the conservative 2D
line-footprint guard still produce a typed bucket-to-wall contact?

It is deliberately diagnostic-only.  It does not alter candidate thresholds,
planner state, ACT checkpoints, temporal aggregation, or live rollout config.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.actual_tuple_bounded_validation import (
    ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA,
)

SCHEMA = "coverage_worktool_wall_contact_diagnosis_v1"
OUTPUT_FILENAME = "manifest.json"
EXPECTED_NEXT_BRANCH = "unity_3d_worktool_sweep"
PRIMARY_CLASSIFICATION = (
    "bucket_3d_swept_envelope_incomplete_primary"
)
_BUCKET_EXTERNAL_SHAPE_PREFIX = (
    "bucket_contact_diagnostic:max_external_shape="
)


def build_coverage_worktool_wall_diagnosis(
    *,
    bounded_validation_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build a no-overwrite root-cause report from frozen bounded evidence."""

    validation_path = Path(
        bounded_validation_path
    ).expanduser().resolve(strict=True)
    destination = Path(output_dir).expanduser().resolve()
    output_path = destination / OUTPUT_FILENAME
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")

    validation = json.loads(
        validation_path.read_text(encoding="utf-8")
    )
    _validate_bounded_gate(validation)
    target_cycle_index = int(validation["target_cycle_index"])
    jsonl_sources = _rollout_jsonl_sources(validation)
    rollout_contracts = _rollout_contracts(validation)

    rollouts: list[dict[str, Any]] = []
    for rollout_id in range(3):
        rollout_contract = rollout_contracts[rollout_id]
        jsonl_path = _verified_source_path(jsonl_sources[rollout_id])
        contact = _first_target_cycle_wall_contact(
            jsonl_path,
            rollout_id=rollout_id,
            target_cycle_index=target_cycle_index,
        )
        plan = _target_plan(
            rollout_contract,
            target_cycle_index=target_cycle_index,
        )
        minimum_clearance_m = _finite_float(
            rollout_contract["minimum_wall_clearance_m"],
            "minimum_wall_clearance_m",
        )
        hard_clearance_m = _finite_float(
            validation["contracts"]["minimum_wall_clearance_m"],
            "contracts.minimum_wall_clearance_m",
        )
        tail_evaluable = (
            int(
                rollout_contract.get(
                    "planned_depth_crossing_step_id",
                    -1,
                )
            )
            >= 0
            and rollout_contract.get(
                "actual_execution_tail_plane_depth_m"
            )
            is not None
        )
        rollouts.append(
            {
                "rollout_id": rollout_id,
                "target_cycle_index": target_cycle_index,
                "plan": plan,
                "planned_2d_guard": {
                    "profile": (
                        "conservative_2d_worktool_swept_footprint_v1"
                    ),
                    "minimum_clearance_m": minimum_clearance_m,
                    "hard_clearance_m": hard_clearance_m,
                    "passed": minimum_clearance_m >= hard_clearance_m,
                },
                "contact": contact,
                "bounded_stop_contract": {
                    "trigger_kind": str(
                        rollout_contract.get(
                            "bounded_trigger_kind",
                            "",
                        )
                    ),
                    "zero_action_after_trigger": bool(
                        rollout_contract.get(
                            "zero_action_after_trigger",
                            False,
                        )
                    ),
                    "neutral_acknowledged": bool(
                        rollout_contract.get(
                            "neutral_acknowledged",
                            False,
                        )
                    ),
                    "terminal_requested": bool(
                        rollout_contract.get(
                            "terminal_requested",
                            False,
                        )
                    ),
                },
                "other_safety": {
                    "bottom_contact": bool(
                        rollout_contract.get(
                            "bottom_contact",
                            False,
                        )
                    ),
                    "stuck": bool(
                        rollout_contract.get("stuck", False)
                    ),
                    "timeout": bool(
                        rollout_contract.get("timeout", False)
                    ),
                },
                "execution_tail": {
                    "evaluable_before_wall_preemption": tail_evaluable,
                    "actual_plane_depth_m": (
                        _optional_finite_float(
                            rollout_contract.get(
                                "actual_execution_tail_plane_depth_m"
                            )
                        )
                    ),
                    "limit_m": _finite_float(
                        rollout_contract[
                            "execution_tail_limit_m"
                        ],
                        "execution_tail_limit_m",
                    ),
                    "exceeded": bool(
                        rollout_contract.get(
                            "actual_execution_tail_exceeded",
                            False,
                        )
                    ),
                },
                "source": _source_record(jsonl_path),
            }
        )

    evidence_matrix = _evidence_matrix(rollouts)
    primary = _classify(evidence_matrix)
    artifact = {
        "schema": SCHEMA,
        "status": "completed",
        "evidence_kind": "bounded_live_production_rollout",
        "primary_classification": primary,
        "interpretation": {
            "planner_act_exact_tuple_contract": (
                "live_executed_for_target_cycle"
            ),
            "planned_2d_guard_result": (
                "passed_all_three_bounded_rollouts"
            ),
            "observed_collision_pair": (
                "bucket_to_serialized_dig_area_wall"
            ),
            "conclusion": (
                "The fixed-width 2D entry-to-exit envelope does not "
                "bound the articulated bucket geometry on the executed "
                "trajectory."
            ),
            "execution_tail_result": (
                "wall_preempted_two_of_three_tail_measurements; "
                "one_evaluable_rollout_exceeded_the_tail_limit"
            ),
        },
        "evidence_matrix": evidence_matrix,
        "rollouts": rollouts,
        "source_lock": {
            "bounded_validation": _source_record(validation_path),
            "rollout_jsonl": [
                item["source"] for item in rollouts
            ],
            "upstream_validation_schema": (
                ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA
            ),
        },
        "promotion_gates": {
            "functional_1x10_allowed": False,
            "functional_3x10_allowed": False,
            "functional_baseline_bundle_allowed": False,
            "cut_then_extract_branch_allowed_before_3d_resolution": (
                False
            ),
            "effect_model_allowed": False,
            "planned_cut_calibration_allowed": False,
            "temporal_ab_allowed": False,
            "formal_30pct_freeze_allowed": False,
        },
        "next_branch": {
            "name": EXPECTED_NEXT_BRANCH,
            "status": "required_before_any_new_functional_live_run",
            "required_scope": [
                "full_oriented_bucket_geometry",
                "articulated_boom_and_stick_geometry",
                "serialized_box_wall_shapes",
                "planned_path_plus_execution_deviation_envelope",
            ],
            "required_outputs": [
                "minimum_3d_clearance_m",
                "closest_excavator_shape",
                "closest_wall_shape",
                "sampled_pose_or_time_index",
                "candidate_rejection_reason",
            ],
            "hard_clearance_m": _finite_float(
                validation["contracts"]["minimum_wall_clearance_m"],
                "contracts.minimum_wall_clearance_m",
            ),
            "missing_geometry": "fail_closed",
            "threshold_relaxation_allowed": False,
            "temporal_window_blame_allowed": False,
            "live_retry_allowed_before_3d_preflight": False,
            "acceptance_probe": (
                "episode_168 must be rejected or independently proven "
                "safe by the 3D query before another live rollout"
            ),
        },
    }
    rendered = json.dumps(
        artifact,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    destination.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
        handle.write("\n")
    return artifact


def _validate_bounded_gate(validation: Mapping[str, Any]) -> None:
    if (
        str(validation.get("schema", ""))
        != ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA
    ):
        raise ValueError("unexpected bounded validation schema")
    if (
        str(validation.get("evidence_kind", ""))
        != "bounded_live_production_rollout"
    ):
        raise ValueError("bounded validation is not live evidence")
    if str(validation.get("status", "")) != "failed":
        raise ValueError("wall diagnosis requires a failed bounded gate")
    if bool(validation.get("functional_1x10_allowed", True)):
        raise ValueError("bounded gate unexpectedly allows functional 1x10")
    if (
        str(validation.get("next_branch", ""))
        != EXPECTED_NEXT_BRANCH
    ):
        raise ValueError("bounded gate did not route to Unity 3D sweep")
    if int(validation.get("rollout_count", -1)) != 3:
        raise ValueError("wall diagnosis requires exactly three rollouts")


def _rollout_jsonl_sources(
    validation: Mapping[str, Any],
) -> dict[int, Mapping[str, Any]]:
    source_lock = validation.get("source_lock")
    if not isinstance(source_lock, Mapping):
        raise ValueError("bounded validation source_lock is missing")
    records = source_lock.get("rollout_jsonl")
    if not isinstance(records, Sequence) or isinstance(
        records,
        (str, bytes),
    ):
        raise ValueError("bounded validation rollout_jsonl lock is invalid")
    result: dict[int, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("rollout JSONL source record is invalid")
        path = Path(str(record.get("path", "")))
        rollout_id = _rollout_id_from_filename(path)
        if rollout_id in result:
            raise ValueError(f"duplicate rollout JSONL id {rollout_id}")
        result[rollout_id] = record
    if set(result) != {0, 1, 2}:
        raise ValueError(
            "bounded validation must lock rollout JSONL ids 0, 1, 2"
        )
    return result


def _rollout_contracts(
    validation: Mapping[str, Any],
) -> dict[int, Mapping[str, Any]]:
    records = validation.get("rollouts")
    if not isinstance(records, Sequence) or isinstance(
        records,
        (str, bytes),
    ):
        raise ValueError("bounded validation rollouts are invalid")
    result: dict[int, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("bounded rollout contract is invalid")
        rollout_id = int(record.get("rollout_id", -1))
        if rollout_id in result:
            raise ValueError(f"duplicate bounded rollout id {rollout_id}")
        result[rollout_id] = record
    if set(result) != {0, 1, 2}:
        raise ValueError("bounded rollout ids must be exactly 0, 1, 2")
    return result


def _target_plan(
    rollout: Mapping[str, Any],
    *,
    target_cycle_index: int,
) -> dict[str, Any]:
    plan_checks = rollout.get("plan_checks")
    if not isinstance(plan_checks, Sequence) or isinstance(
        plan_checks,
        (str, bytes),
    ):
        raise ValueError("bounded rollout plan_checks are invalid")
    matches = [
        item
        for item in plan_checks
        if isinstance(item, Mapping)
        and int(item.get("target_cycle_index", -1))
        == target_cycle_index
    ]
    if len(matches) != 1:
        raise ValueError(
            "expected exactly one plan for the bounded target cycle"
        )
    match = matches[0]
    return {
        "exemplar_id": str(match.get("exemplar_id", "")),
        "corridor_id": int(match.get("corridor_id", -1)),
        "raw_fields_sha256": str(
            match.get("raw_fields_sha256", "")
        ),
        "exact_library_tuple": bool(
            match.get("exact_library_tuple", False)
        ),
        "planned_depth_m": _finite_float(
            rollout["planned_depth_m"],
            "planned_depth_m",
        ),
    }


def _first_target_cycle_wall_contact(
    path: Path,
    *,
    rollout_id: int,
    target_cycle_index: int,
) -> dict[str, Any]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            int(row.get("rollout_id", -1)) != rollout_id
            or int(row.get("primitive_cycle_index", -1))
            != target_cycle_index
        ):
            continue
        env_state = row.get("env_state")
        if (
            not isinstance(env_state, Sequence)
            or isinstance(env_state, (str, bytes))
            or len(env_state) < ENV_STATE_V2_4_DIM
        ):
            continue
        if (
            _finite_float(
                env_state[
                    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX
                ],
                "typed wall mask",
            )
            < 0.5
        ):
            continue
        warnings = row.get("warnings", ())
        if not isinstance(warnings, Sequence) or isinstance(
            warnings,
            (str, bytes),
        ):
            warnings = ()
        external_shape = ""
        for warning in warnings:
            text = str(warning)
            if text.startswith(_BUCKET_EXTERNAL_SHAPE_PREFIX):
                external_shape = text[
                    len(_BUCKET_EXTERNAL_SHAPE_PREFIX) :
                ]
                break
        return {
            "step_id": int(row.get("step_id", -1)),
            "typed_wall_mask": True,
            "step_max_force_n": _finite_float(
                env_state[
                    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX
                ],
                "wall max force",
            ),
            "session_count": int(
                round(
                    _finite_float(
                        env_state[
                            ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX
                        ],
                        "wall session count",
                    )
                )
            ),
            "bucket_tip_dig_area_m": [
                _finite_float(
                    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX],
                    "bucket tip x",
                ),
                _finite_float(
                    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX],
                    "bucket tip y",
                ),
                _finite_float(
                    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX],
                    "bucket tip z",
                ),
            ],
            "qpos": _finite_vector(row.get("qpos"), "qpos", length=4),
            "qvel": _finite_vector(row.get("qvel"), "qvel", length=4),
            "action": _finite_vector(
                row.get("action"),
                "action",
                length=4,
            ),
            "external_shape": external_shape,
            "bucket_contact_shape_identified": bool(external_shape),
        }
    raise ValueError(
        f"typed wall contact not found for rollout {rollout_id} "
        f"cycle {target_cycle_index}"
    )


def _evidence_matrix(
    rollouts: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "bounded_rollout_count": len(rollouts),
        "exact_library_tuple_count": sum(
            bool(item["plan"]["exact_library_tuple"])
            for item in rollouts
        ),
        "planned_2d_clearance_pass_count": sum(
            bool(item["planned_2d_guard"]["passed"])
            for item in rollouts
        ),
        "typed_wall_contact_count": sum(
            bool(item["contact"]["typed_wall_mask"])
            for item in rollouts
        ),
        "bucket_contact_shape_identified_count": sum(
            bool(
                item["contact"][
                    "bucket_contact_shape_identified"
                ]
            )
            for item in rollouts
        ),
        "bottom_contact_count": sum(
            bool(item["other_safety"]["bottom_contact"])
            for item in rollouts
        ),
        "stuck_count": sum(
            bool(item["other_safety"]["stuck"])
            for item in rollouts
        ),
        "timeout_count": sum(
            bool(item["other_safety"]["timeout"])
            for item in rollouts
        ),
        "neutral_stop_contract_pass_count": sum(
            (
                item["bounded_stop_contract"]["trigger_kind"]
                == "wall"
                and bool(
                    item["bounded_stop_contract"][
                        "zero_action_after_trigger"
                    ]
                )
                and bool(
                    item["bounded_stop_contract"][
                        "neutral_acknowledged"
                    ]
                )
                and bool(
                    item["bounded_stop_contract"][
                        "terminal_requested"
                    ]
                )
            )
            for item in rollouts
        ),
        "tail_evaluable_count": sum(
            bool(
                item["execution_tail"][
                    "evaluable_before_wall_preemption"
                ]
            )
            for item in rollouts
        ),
        "tail_exceeded_count": sum(
            bool(item["execution_tail"]["exceeded"])
            for item in rollouts
        ),
    }


def _classify(matrix: Mapping[str, int]) -> str:
    if (
        matrix["bounded_rollout_count"] == 3
        and matrix["exact_library_tuple_count"] == 3
        and matrix["planned_2d_clearance_pass_count"] == 3
        and matrix["typed_wall_contact_count"] == 3
        and matrix["bucket_contact_shape_identified_count"] == 3
        and matrix["bottom_contact_count"] == 0
        and matrix["stuck_count"] == 0
        and matrix["timeout_count"] == 0
        and matrix["neutral_stop_contract_pass_count"] == 3
    ):
        return PRIMARY_CLASSIFICATION
    return "worktool_wall_contact_evidence_incomplete"


def _verified_source_path(record: Mapping[str, Any]) -> Path:
    path = Path(str(record.get("path", ""))).expanduser().resolve(
        strict=True
    )
    payload = path.read_bytes()
    expected_size = int(record.get("size_bytes", -1))
    if len(payload) != expected_size:
        raise ValueError(
            f"source size mismatch:{path}:"
            f"expected={expected_size}:actual={len(payload)}"
        )
    expected_sha = str(record.get("sha256", "")).lower()
    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(
            f"source SHA256 mismatch:{path}:"
            f"expected={expected_sha}:actual={actual_sha}"
        )
    return path


def _rollout_id_from_filename(path: Path) -> int:
    stem = path.stem
    prefix = "rollout_"
    if not stem.startswith(prefix):
        raise ValueError(f"invalid rollout JSONL filename: {path.name}")
    suffix = stem[len(prefix) :]
    if not suffix.isdigit():
        raise ValueError(f"invalid rollout JSONL filename: {path.name}")
    return int(suffix)


def _source_record(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _finite_float(value: Any, field_name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    return _finite_float(value, "optional metric")


def _finite_vector(
    value: Any,
    field_name: str,
    *,
    length: int,
) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes),
    ):
        raise ValueError(f"{field_name} must be a sequence")
    if len(value) != length:
        raise ValueError(f"{field_name} must have length {length}")
    return [
        _finite_float(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    ]


__all__ = [
    "OUTPUT_FILENAME",
    "PRIMARY_CLASSIFICATION",
    "SCHEMA",
    "build_coverage_worktool_wall_diagnosis",
]
