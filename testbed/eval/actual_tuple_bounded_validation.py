"""Validate three production bounded probes for exact coverage tuples."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)

ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA = (
    "act_actual_tuple_bounded_one_dig_validation_v1"
)
OUTPUT_FILENAME = f"{ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA}.json"
_TARGET_CYCLE_INDEX = 1
_DEPTH_CROSSING_TOLERANCE_M = 0.002
_TAIL_TOLERANCE_M = 0.02
_WALL_CLEARANCE_M = 0.30


def build_actual_tuple_bounded_validation(
    *,
    results_dir: str | Path,
    strict_execution_library_path: str | Path,
    strict_execution_library_sha256: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build a no-overwrite gate for three independent bounded rollouts."""

    results = Path(results_dir).expanduser().resolve(strict=True)
    library_path = Path(
        strict_execution_library_path
    ).expanduser().resolve(strict=True)
    destination = Path(output_dir).expanduser().resolve()
    output_path = destination / OUTPUT_FILENAME
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    payload = library_path.read_bytes()
    actual_library_sha = hashlib.sha256(payload).hexdigest()
    expected_library_sha = str(
        strict_execution_library_sha256
    ).strip().lower()
    if actual_library_sha != expected_library_sha:
        raise ValueError(
            "strict execution library SHA mismatch:"
            f"expected={expected_library_sha}:actual={actual_library_sha}"
        )
    library = json.loads(payload)
    records = _library_records(library)

    jsonl_paths = sorted(
        path
        for path in (results / "rollouts").glob("rollout_*.jsonl")
        if not path.name.endswith(".partial.jsonl")
    )
    hdf5_paths = sorted(
        (results / "hdf5_rollouts").glob("episode_*.hdf5")
    )
    planner_trace_paths = sorted(
        (results / "rollouts").glob(
            "rollout_*_planner_trace.json"
        )
    )
    if (
        len(jsonl_paths) != 3
        or len(hdf5_paths) != 3
        or len(planner_trace_paths) != 3
    ):
        raise ValueError(
            "bounded exact-tuple gate requires exactly three JSONL, "
            "three planner traces, and three HDF5 rollouts"
        )
    rollouts = [
        _validate_rollout(
            rollout_id=index,
            jsonl_path=jsonl_paths[index],
            hdf5_path=hdf5_paths[index],
            planner_trace_path=planner_trace_paths[index],
            library_records=records,
        )
        for index in range(3)
    ]
    passed = all(bool(item["passed"]) for item in rollouts)
    any_wall = any(bool(item["wall_contact"]) for item in rollouts)
    any_tail_excess = any(
        bool(item["actual_execution_tail_exceeded"])
        for item in rollouts
    )
    if passed:
        next_branch = "functional_1x10"
    elif any_wall:
        next_branch = "unity_3d_worktool_sweep"
    elif any_tail_excess:
        next_branch = "v2_4_6_cut_then_extract"
    else:
        next_branch = "stop_for_single_factor_diagnosis"
    artifact = {
        "schema": ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA,
        "status": "passed" if passed else "failed",
        "evidence_kind": "bounded_live_production_rollout",
        "target_cycle_index": _TARGET_CYCLE_INDEX,
        "rollout_count": len(rollouts),
        "source_lock": {
            "strict_execution_library": _source_record(library_path),
            "results_dir": str(results),
            "rollout_jsonl": [
                _source_record(path) for path in jsonl_paths
            ],
            "rollout_hdf5": [
                _source_record(path) for path in hdf5_paths
            ],
            "planner_trace": [
                _source_record(path) for path in planner_trace_paths
            ],
        },
        "contracts": {
            "planned_depth_crossing_tolerance_m": (
                _DEPTH_CROSSING_TOLERANCE_M
            ),
            "actual_tail_extra_tolerance_m": _TAIL_TOLERANCE_M,
            "minimum_wall_clearance_m": _WALL_CLEARANCE_M,
            "typed_safety_required": True,
            "neutral_ack_required": True,
        },
        "rollouts": rollouts,
        "functional_1x10_allowed": bool(passed),
        "next_branch": next_branch,
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


def _validate_rollout(
    *,
    rollout_id: int,
    jsonl_path: Path,
    hdf5_path: Path,
    planner_trace_path: Path,
    library_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"bounded rollout JSONL is empty: {jsonl_path}")
    with h5py.File(hdf5_path, "r") as handle:
        env = np.asarray(
            handle["observations/env_state"][:],
            dtype=np.float64,
        )
        actions = np.asarray(handle["action"][:], dtype=np.float64)
        step_ids = np.asarray(
            handle["timestamps/step_id"][:],
            dtype=np.int64,
        )
    if (
        env.ndim != 2
        or env.shape[1] < ENV_STATE_V2_4_DIM
        or actions.shape != (env.shape[0], 4)
        or step_ids.shape != (env.shape[0],)
    ):
        raise ValueError(
            f"bounded rollout HDF5 shape contract failed: {hdf5_path}"
        )

    planner_trace = json.loads(
        planner_trace_path.read_text(encoding="utf-8")
    )
    decision_trace = planner_trace.get(
        "coverage_decision_trace",
        (),
    )
    if not isinstance(decision_trace, list):
        raise ValueError(
            f"planner trace decision list is invalid: {planner_trace_path}"
        )
    plan_checks: list[dict[str, Any]] = []
    seen_plan_keys: set[tuple[int, str]] = set()
    for event in decision_trace:
        if (
            not isinstance(event, dict)
            or str(event.get("event", ""))
            != "select_actual_tuple_execution_candidate"
        ):
            continue
        exemplar_id = str(event.get("exemplar_id", ""))
        if not exemplar_id:
            continue
        event_cycle_index = int(event.get("cycle_index", -1))
        skill_name = str(event.get("skill_name", ""))
        target_cycle_index = (
            event_cycle_index + 1
            if skill_name == "return"
            else event_cycle_index
        )
        key = (target_cycle_index, exemplar_id)
        if key in seen_plan_keys:
            continue
        seen_plan_keys.add(key)
        expected = library_records.get(exemplar_id)
        raw_sha = str(event.get("raw_fields_sha256", ""))
        corridor_id = int(event.get("corridor_id", -1))
        tail_reserve = float(
            event.get(
                "execution_tail_plane_depth_reserve_m",
                float("nan"),
            )
        )
        exact = bool(
            expected is not None
            and raw_sha == str(expected["raw_fields_sha256"])
            and corridor_id == int(expected["corridor_id"])
            and math.isclose(
                tail_reserve,
                float(
                    expected[
                        "execution_tail_plane_depth_reserve_m"
                    ]
                ),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            )
        )
        plan_checks.append(
            {
                "event_cycle_index": event_cycle_index,
                "target_cycle_index": target_cycle_index,
                "planning_skill_name": skill_name,
                "exemplar_id": exemplar_id,
                "corridor_id": corridor_id,
                "raw_fields_sha256": raw_sha,
                "minimum_wall_clearance_m": _finite_or_none(
                    float(
                        event.get(
                            "wall_minimum_clearance_m",
                            float("nan"),
                        )
                    )
                ),
                "exact_library_tuple": exact,
            }
        )

    target_rows = [
        row
        for row in rows
        if str(row.get("skill_name", "")) == "dig"
        and int(row.get("primitive_cycle_index", -1))
        == _TARGET_CYCLE_INDEX
    ]
    target_with_plan = [
        item
        for item in plan_checks
        if int(item["target_cycle_index"]) == _TARGET_CYCLE_INDEX
    ]
    target_plan = target_with_plan[0] if target_with_plan else {}
    exemplar_id = str(
        target_plan.get("exemplar_id", "")
    )
    record = library_records.get(exemplar_id)
    planned_depth = (
        float("nan")
        if record is None
        else float(record["operator_cut_depth_peak_m"])
    )
    tail_reserve = (
        float("nan")
        if record is None
        else float(record["execution_tail_plane_depth_reserve_m"])
    )
    target_depth_rows: list[tuple[int, float, float]] = []
    for row in target_rows:
        env_state = np.asarray(
            row.get("env_state", ()),
            dtype=np.float64,
        ).reshape(-1)
        if env_state.size < ENV_STATE_V2_4_DIM:
            continue
        target_depth_rows.append(
            (
                int(row.get("step_id", -1)),
                float(
                    env_state[
                        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX
                    ]
                ),
                float(
                    env_state[
                        ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
                    ]
                ),
            )
        )
    crossing_index = next(
        (
            index
            for index, (_, local_depth, _) in enumerate(
                target_depth_rows
            )
            if math.isfinite(planned_depth)
            and local_depth
            >= planned_depth - _DEPTH_CROSSING_TOLERANCE_M
        ),
        -1,
    )
    if crossing_index >= 0:
        crossing_step, _, crossing_plane = target_depth_rows[
            crossing_index
        ]
        maximum_plane = max(
            item[2] for item in target_depth_rows[crossing_index:]
        )
        actual_tail = max(0.0, maximum_plane - crossing_plane)
    else:
        crossing_step = -1
        actual_tail = float("nan")
    tail_limit = (
        float("nan")
        if not math.isfinite(tail_reserve)
        else tail_reserve + _TAIL_TOLERANCE_M
    )
    tail_exceeded = bool(
        math.isfinite(actual_tail)
        and math.isfinite(tail_limit)
        and actual_tail > tail_limit + 1.0e-9
    )

    wall_contact = bool(
        np.any(
            env[
                :,
                ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
            ]
            >= 0.5
        )
        or np.max(
            env[
                :,
                ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
            ]
        )
        > 0.5
    )
    bottom_contact = bool(
        np.any(
            env[
                :,
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
            ]
            >= 0.5
        )
        or np.max(
            env[
                :,
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
            ]
        )
        > 0.5
    )
    safety_reasons = [
        str(row.get("box_safety_reason", ""))
        for row in rows
        if str(row.get("box_safety_reason", ""))
    ]
    stuck = any(reason.startswith("stuck") for reason in safety_reasons)
    timeout = bool(
        any(bool(row.get("transition_timeout", False)) for row in rows)
        or any(reason.endswith("_timeout") for reason in safety_reasons)
    )
    envelope_ready = any(
        bool(row.get("carry_start_envelope_ready", False))
        and int(row.get("carry_start_envelope_hold_count", 0)) >= 3
        for row in target_rows
    )
    trigger_rows = [
        row
        for row in rows
        if str(
            row.get("bounded_dig_probe_stop_trigger_kind", "")
        )
    ]
    trigger_kind = (
        ""
        if not trigger_rows
        else str(
            trigger_rows[0][
                "bounded_dig_probe_stop_trigger_kind"
            ]
        )
    )
    neutral_ack = any(
        bool(
            row.get(
                "bounded_dig_probe_stop_neutral_acknowledged",
                False,
            )
        )
        for row in rows
    )
    terminal = any(
        bool(
            row.get(
                "bounded_dig_probe_stop_terminal_requested",
                False,
            )
        )
        for row in rows
    )
    trigger_step = min(
        (
            int(row.get("step_id", -1))
            for row in trigger_rows
        ),
        default=-1,
    )
    zero_after_trigger = bool(
        trigger_step >= 0
        and any(
            int(step_id) >= trigger_step
            and np.allclose(action, 0.0, rtol=0.0, atol=1.0e-8)
            for step_id, action in zip(step_ids, actions, strict=True)
        )
    )
    target_clearances = [
        float(item["minimum_wall_clearance_m"])
        for item in target_with_plan
        if item.get("minimum_wall_clearance_m") is not None
    ]
    minimum_wall_clearance = min(
        target_clearances,
        default=float("nan"),
    )

    failures: list[str] = []
    if not plan_checks or not all(
        bool(item["exact_library_tuple"]) for item in plan_checks
    ):
        failures.append("non_library_or_mutated_goal")
    if not target_with_plan:
        failures.append("target_cycle_missing_exact_tuple")
    if crossing_index < 0:
        failures.append("planned_depth_not_reached")
    if tail_exceeded:
        failures.append("execution_tail_exceeded")
    if wall_contact:
        failures.append("wall_contact")
    if bottom_contact:
        failures.append("bottom_contact")
    if stuck:
        failures.append("stuck")
    if timeout:
        failures.append("timeout")
    if not envelope_ready:
        failures.append("carry_start_envelope_not_ready")
    if trigger_kind != "envelope_ready":
        failures.append("bounded_stop_not_envelope_ready")
    if not neutral_ack or not terminal or not zero_after_trigger:
        failures.append("terminal_neutral_contract_failed")
    if (
        not math.isfinite(minimum_wall_clearance)
        or minimum_wall_clearance < _WALL_CLEARANCE_M
    ):
        failures.append("wall_clearance_below_minimum")

    return {
        "rollout_id": int(rollout_id),
        "passed": not failures,
        "failures": failures,
        "plan_checks": plan_checks,
        "target_exemplar_id": exemplar_id,
        "planned_depth_m": _finite_or_none(planned_depth),
        "planned_depth_crossing_step_id": crossing_step,
        "execution_tail_plane_depth_reserve_m": _finite_or_none(
            tail_reserve
        ),
        "actual_execution_tail_plane_depth_m": _finite_or_none(
            actual_tail
        ),
        "execution_tail_limit_m": _finite_or_none(tail_limit),
        "actual_execution_tail_exceeded": tail_exceeded,
        "minimum_wall_clearance_m": _finite_or_none(
            minimum_wall_clearance
        ),
        "wall_contact": wall_contact,
        "bottom_contact": bottom_contact,
        "stuck": stuck,
        "timeout": timeout,
        "carry_start_envelope_ready_3step": envelope_ready,
        "bounded_trigger_kind": trigger_kind,
        "neutral_acknowledged": neutral_ack,
        "terminal_requested": terminal,
        "zero_action_after_trigger": zero_after_trigger,
    }


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _library_records(
    library: Any,
) -> dict[str, dict[str, Any]]:
    if (
        not isinstance(library, dict)
        or str(library.get("schema", ""))
        != "strict_train_coverage_execution_library_v1_1"
        or str(library.get("status", "")) != "completed"
    ):
        raise ValueError("invalid strict execution library contract")
    output: dict[str, dict[str, Any]] = {}
    for raw_record in library.get("records", ()):
        record = dict(raw_record)
        exemplar_id = str(record.get("exemplar_id", ""))
        raw_fields = dict(record.get("raw_fields", {}) or {})
        if not exemplar_id or not raw_fields:
            raise ValueError("strict execution library record is incomplete")
        output[exemplar_id] = {
            **record,
            "operator_cut_depth_peak_m": float(
                raw_fields["operator_cut_depth_peak_m"]
            ),
            "raw_fields_sha256": hashlib.sha256(
                json.dumps(
                    raw_fields,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
        }
    if not output:
        raise ValueError("strict execution library has no records")
    return output


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": int(path.stat().st_size),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


__all__ = [
    "ACTUAL_TUPLE_BOUNDED_VALIDATION_SCHEMA",
    "OUTPUT_FILENAME",
    "build_actual_tuple_bounded_validation",
]
