"""Frozen recorded-execution diagnosis for a hard-bottom dig event.

The evaluator understands the rollout recorder's post-observation layout:
HDF5 row ``i`` contains the action at backend ``step_id=i`` and the
observation produced by that action.  A policy action therefore consumes the
observation at the preceding HDF5 row.  This distinction is essential at a
contact edge: the zero-action safety row consumes the first contact
observation, while the preceding policy action produced it.

This module is read-only with respect to rollout inputs.  Its builder freezes
source evidence by path, size, and SHA256; it never copies or modifies the
failed rollout.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_DEPTH_SCALE_M
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
)
from testbed.planner.primitive.coverage.swept_cells import (
    CoverageSweptFootprint,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallGeometry,
)

DIAGNOSTIC_SCHEMA = "act_hard_bottom_cycle6_diagnosis_v1"
SOURCE_MANIFEST_SCHEMA = "frozen_failure_artifact_sha256_manifest_v1"
DIAGNOSIS_FILENAME = "cycle6_execution_diagnosis.json"
SOURCE_MANIFEST_FILENAME = "source_lock_manifest.json"
EVIDENCE_SCOPE = "frozen_recorded_closed_loop"
DEFAULT_HARD_BOTTOM_MARGIN_M = 0.02
DEFAULT_WORKTOOL_WIDTH_M = 0.70
_FLOAT_TOLERANCE = 1.0e-7


class HardBottomExecutionDiagnosticError(RuntimeError):
    """Raised when frozen evidence cannot satisfy the diagnostic contract."""


def physical_cell_id(
    env_state: Any,
    *,
    x_m: float,
    z_m: float,
) -> int:
    """Map one local DigArea X/Z point to its physical 3x2 Unity cell."""

    geometry = _coverage_geometry(env_state)
    x = _finite_float(x_m, "x_m")
    z = _finite_float(z_m, "z_m")
    if geometry.long_axis == 0:
        long_value, short_value = x, z
    else:
        long_value, short_value = z, x
    long_index = _axis_index(
        long_value,
        count=geometry.grid_long_count,
        cell_size=geometry.cell_long_size_m,
    )
    short_index = _axis_index(
        short_value,
        count=geometry.grid_short_count,
        cell_size=geometry.cell_short_size_m,
    )
    if long_index < 0 or short_index < 0:
        return -1
    return int(long_index * geometry.grid_short_count + short_index)


def swept_cell_ids(
    env_state: Any,
    *,
    entry_x_m: float,
    entry_z_m: float,
    exit_x_m: float,
    exit_z_m: float,
    worktool_width_m: float,
) -> tuple[int, ...]:
    """Return cells intersected by a full segment and its lateral footprint."""

    width = _positive_float(worktool_width_m, "worktool_width_m")
    footprint = CoverageSweptFootprint.from_segment(
        geometry=_coverage_geometry(env_state),
        entry_x_m=_finite_float(entry_x_m, "entry_x_m"),
        entry_z_m=_finite_float(entry_z_m, "entry_z_m"),
        exit_x_m=_finite_float(exit_x_m, "exit_x_m"),
        exit_z_m=_finite_float(exit_z_m, "exit_z_m"),
        worktool_width_m=width,
    )
    return tuple(footprint.swept_cell_ids)


def classify_hard_bottom_source(
    *,
    planned_minimum_clearance_m: float,
    planned_depth_m: float,
    actual_peak_penetration_m: float,
    contact_bucket_tip_clearance_m: float,
    hard_bottom_margin_m: float,
    typed_bottom_contact: bool,
    logical_cell_id: int,
    centerline_physical_cell_ids: Sequence[int],
    swept_physical_cell_ids: Sequence[int],
) -> dict[str, Any]:
    """Apply the locked planner/ACT/collision-envelope cause ordering."""

    planned_clearance = _finite_float(
        planned_minimum_clearance_m,
        "planned_minimum_clearance_m",
    )
    planned_depth = _finite_float(planned_depth_m, "planned_depth_m")
    peak = _finite_float(
        actual_peak_penetration_m,
        "actual_peak_penetration_m",
    )
    tip_clearance = _finite_float(
        contact_bucket_tip_clearance_m,
        "contact_bucket_tip_clearance_m",
    )
    margin = _positive_float(hard_bottom_margin_m, "hard_bottom_margin_m")
    overshoot = float(peak - planned_depth)
    if planned_clearance < margin - _FLOAT_TOLERANCE:
        primary = "planner_depth_geometry_primary"
    elif bool(typed_bottom_contact) and (
        tip_clearance >= margin - _FLOAT_TOLERANCE
    ):
        primary = "bucket_collision_envelope_incomplete_primary"
    elif (
        overshoot > margin + _FLOAT_TOLERANCE
        or tip_clearance < margin - _FLOAT_TOLERANCE
    ):
        primary = "act_execution_capability_primary"
    else:
        primary = "hard_bottom_source_indeterminate"

    physical = {
        int(value)
        for value in (
            *centerline_physical_cell_ids,
            *swept_physical_cell_ids,
        )
        if int(value) >= 0
    }
    additional: list[str] = []
    if int(logical_cell_id) not in physical:
        additional.append("data_scene_cell_semantic_mismatch")
    return {
        "primary_cause": primary,
        "additional_findings": additional,
        "facts": {
            "hard_bottom_margin_m": margin,
            "planned_minimum_clearance_m": planned_clearance,
            "planned_depth_m": planned_depth,
            "actual_peak_penetration_m": peak,
            "actual_penetration_overshoot_m": overshoot,
            "contact_bucket_tip_clearance_m": tip_clearance,
            "typed_bottom_contact": bool(typed_bottom_contact),
            "logical_cell_id": int(logical_cell_id),
            "centerline_physical_cell_ids": sorted(
                {int(value) for value in centerline_physical_cell_ids}
            ),
            "swept_physical_cell_ids": sorted(
                {int(value) for value in swept_physical_cell_ids}
            ),
        },
    }


def analyze_hard_bottom_execution(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    cycle_index: int = 5,
    hard_bottom_margin_m: float = DEFAULT_HARD_BOTTOM_MARGIN_M,
    worktool_width_m: float = DEFAULT_WORKTOOL_WIDTH_M,
) -> dict[str, Any]:
    """Reconstruct one dig from its first pre-action observation to contact."""

    margin = _positive_float(hard_bottom_margin_m, "hard_bottom_margin_m")
    width = _positive_float(worktool_width_m, "worktool_width_m")
    target_cycle = _integer(cycle_index, "cycle_index")
    if target_cycle < 0:
        raise HardBottomExecutionDiagnosticError(
            "cycle_index_must_be_nonnegative"
        )
    hdf5_path = _require_file(rollout_hdf5_path, "rollout_hdf5")
    jsonl_path = _require_file(rollout_jsonl_path, "rollout_jsonl")
    rows = _load_jsonl_rows(jsonl_path)

    with h5py.File(hdf5_path, "r") as handle:
        step_ids = np.asarray(
            handle["timestamps/step_id"][:],
            dtype=np.int64,
        ).reshape(-1)
        env_states = np.asarray(
            handle["observations/env_state"][:],
            dtype=np.float64,
        )
        qpos = np.asarray(handle["observations/qpos"][:], dtype=np.float64)
        qvel = np.asarray(handle["observations/qvel"][:], dtype=np.float64)
        actions = np.asarray(handle["action"][:], dtype=np.float64)
    _validate_hdf5_arrays(
        step_ids=step_ids,
        env_states=env_states,
        qpos=qpos,
        qvel=qvel,
        actions=actions,
    )
    index_by_step = {int(step_id): index for index, step_id in enumerate(step_ids)}
    target_rows = [
        row
        for row in rows
        if _integer(row.get("primitive_cycle_index", -1), "primitive_cycle_index")
        == target_cycle
        and str(row.get("skill_name", "")) == "dig"
    ]
    if not target_rows:
        raise HardBottomExecutionDiagnosticError(
            f"cycle_{target_cycle}_dig_rows_missing"
        )
    indexed_rows = [
        (row, _action_index(row, index_by_step=index_by_step))
        for row in target_rows
    ]
    first_row, first_action_index = indexed_rows[0]
    if first_action_index <= 0:
        raise HardBottomExecutionDiagnosticError(
            "first_dig_action_has_no_pre_action_observation"
        )
    contact_row: Mapping[str, Any] | None = None
    trigger_action_index = -1
    for row, action_index in indexed_rows:
        pre_index = action_index - 1
        contact = _bottom_mask(env_states[pre_index])
        preceding = (
            _bottom_mask(env_states[pre_index - 1])
            if pre_index > 0
            else False
        )
        if contact and not preceding:
            contact_row = row
            trigger_action_index = action_index
            break
    if contact_row is None:
        raise HardBottomExecutionDiagnosticError(
            f"cycle_{target_cycle}_typed_bottom_rising_edge_missing"
        )
    if not bool(contact_row.get("box_safety_hard_bottom_contact", False)):
        raise HardBottomExecutionDiagnosticError(
            "typed_bottom_rising_edge_lacks_hard_bottom_safety_trigger"
        )

    contact_observation_index = trigger_action_index - 1
    contact_observation_step_id = int(step_ids[contact_observation_index])
    cut_rows = [
        (row, action_index)
        for row, action_index in indexed_rows
        if first_action_index <= action_index <= contact_observation_index
    ]
    if not cut_rows:
        raise HardBottomExecutionDiagnosticError(
            "hard_bottom_cut_action_window_empty"
        )
    expected_action_indices = list(
        range(first_action_index, contact_observation_index + 1)
    )
    actual_action_indices = [index for _, index in cut_rows]
    if actual_action_indices != expected_action_indices:
        raise HardBottomExecutionDiagnosticError(
            "dig_action_window_not_contiguous_before_contact"
        )
    aligned_actions = _aligned_actions(
        cut_rows=cut_rows,
        actions=actions,
        step_ids=step_ids,
    )
    plan = _plan_contract(
        first_row=first_row,
        cut_rows=cut_rows,
        env_state=env_states[first_action_index - 1],
        worktool_width_m=width,
    )
    trajectory_indices = list(
        range(first_action_index - 1, contact_observation_index + 1)
    )
    trajectory = _trajectory_records(
        indices=trajectory_indices,
        step_ids=step_ids,
        env_states=env_states,
        qpos=qpos,
        qvel=qvel,
        plan=plan,
    )
    actual_peak = max(
        float(item["env_state_local_penetration_m"])
        for item in trajectory
    )
    actual_plane_peak = max(
        float(item["bucket_tip_plane_depth_m"])
        for item in trajectory
    )
    contact_env = env_states[contact_observation_index]
    hard_bottom = float(contact_env[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX])
    contact_plane_depth = float(
        contact_env[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
    )
    contact_tip_clearance = float(hard_bottom - contact_plane_depth)
    contact_tip = contact_env[
        ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
        ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
    ].astype(float)
    actual_centerline_cells = sorted(
        {
            int(item["physical_cell_id"])
            for item in trajectory
            if int(item["physical_cell_id"]) >= 0
        }
    )
    actual_swept_cells: set[int] = set()
    for left, right in zip(trajectory, trajectory[1:]):
        actual_swept_cells.update(
            swept_cell_ids(
                env_states[first_action_index - 1],
                entry_x_m=float(left["bucket_tip_xyz_m"][0]),
                entry_z_m=float(left["bucket_tip_xyz_m"][2]),
                exit_x_m=float(right["bucket_tip_xyz_m"][0]),
                exit_z_m=float(right["bucket_tip_xyz_m"][2]),
                worktool_width_m=width,
            )
        )
    classification = classify_hard_bottom_source(
        planned_minimum_clearance_m=float(
            plan["planned_minimum_hard_bottom_clearance_m"]
        ),
        planned_depth_m=float(plan["planned_depth_m"]),
        actual_peak_penetration_m=actual_peak,
        contact_bucket_tip_clearance_m=contact_tip_clearance,
        hard_bottom_margin_m=margin,
        typed_bottom_contact=_bottom_mask(contact_env),
        logical_cell_id=int(plan["logical_cell_id"]),
        centerline_physical_cell_ids=plan["centerline_physical_cell_ids"],
        swept_physical_cell_ids=plan["swept_physical_cell_ids"],
    )
    clearance_count = sum(
        1
        for row, action_index in indexed_rows
        if action_index > trigger_action_index
        and (
            bool(row.get("box_safety_clearance_active", False))
            or "clearance" in str(row.get("box_safety_reason", ""))
        )
    )
    return {
        "schema": DIAGNOSTIC_SCHEMA,
        "status": "completed",
        "evidence_scope": EVIDENCE_SCOPE,
        "cycle_index": target_cycle,
        "contracts": {
            "rollout_storage_alignment": "action_with_post_observation",
            "cut_window_end": "first_typed_bottom_rising_edge_observation",
            "clearance_excluded": True,
            "hard_bottom_margin_m": margin,
            "worktool_width_m": width,
        },
        "cut_window": {
            "first_action_step_id": int(step_ids[first_action_index]),
            "first_pre_action_observation_step_id": int(
                step_ids[first_action_index - 1]
            ),
            "contact_observation_step_id": contact_observation_step_id,
            "safety_trigger_action_step_id": int(
                step_ids[trigger_action_index]
            ),
            "last_cut_action_step_id": int(
                step_ids[contact_observation_index]
            ),
            "trajectory_observation_step_ids": [
                int(step_ids[index]) for index in trajectory_indices
            ],
            "cut_action_count": len(cut_rows),
            "clearance_rows_excluded": int(clearance_count),
        },
        "plan": plan,
        "execution": {
            "actual_peak_penetration_m": actual_peak,
            "actual_plane_depth_peak_m": actual_plane_peak,
            "actual_penetration_overshoot_m": float(
                actual_peak - float(plan["planned_depth_m"])
            ),
            "contact_endpoint_xyz_m": contact_tip.tolist(),
            "contact_bucket_tip_clearance_m": contact_tip_clearance,
            "contact_local_surface_depth_m": trajectory[-1][
                "local_surface_depth_m"
            ],
            "contact_local_remaining_depth_m": trajectory[-1][
                "local_remaining_depth_m"
            ],
            "contact_planned_clearance_from_local_surface_m": trajectory[-1][
                "planned_clearance_from_local_surface_m"
            ],
            "contact_force_n": float(
                contact_env[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX
                ]
            ),
            "contact_session_count": int(
                round(
                    float(
                        contact_env[
                            ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                        ]
                    )
                )
            ),
            "actual_centerline_physical_cell_ids": actual_centerline_cells,
            "actual_swept_physical_cell_ids": sorted(actual_swept_cells),
            "max_point_to_planned_segment_error_m": max(
                float(item["point_to_planned_segment_error_m"])
                for item in trajectory
            ),
            "contact_point_to_planned_segment_error_m": float(
                trajectory[-1]["point_to_planned_segment_error_m"]
            ),
        },
        "classification": classification,
        "aligned_actions": aligned_actions,
        "trajectory": trajectory,
    }


def build_hard_bottom_execution_diagnostic(
    *,
    results_dir: str | Path,
    video_path: str | Path,
    prior_path: str | Path,
    unity_scene_path: str | Path,
    output_dir: str | Path,
    cycle_index: int = 5,
    hard_bottom_margin_m: float = DEFAULT_HARD_BOTTOM_MARGIN_M,
    worktool_width_m: float = DEFAULT_WORKTOOL_WIDTH_M,
) -> dict[str, Any]:
    """Compatibility facade for the CLI-owned artifact orchestration."""

    from testbed.cli.build_hard_bottom_execution_diagnostic import (
        build_hard_bottom_execution_diagnostic as build_artifact,
    )

    return build_artifact(
        results_dir=results_dir,
        video_path=video_path,
        prior_path=prior_path,
        unity_scene_path=unity_scene_path,
        output_dir=output_dir,
        cycle_index=cycle_index,
        hard_bottom_margin_m=hard_bottom_margin_m,
        worktool_width_m=worktool_width_m,
    )


def _plan_contract(
    *,
    first_row: Mapping[str, Any],
    cut_rows: Sequence[tuple[Mapping[str, Any], int]],
    env_state: np.ndarray,
    worktool_width_m: float,
) -> dict[str, Any]:
    token = np.asarray(first_row.get("dig_cut_tokens", []), dtype=np.float64)
    if token.shape != (10,) or not np.isfinite(token).all():
        raise HardBottomExecutionDiagnosticError(
            "dig_cut_tokens_must_be_finite_10d"
        )
    plan_values = np.asarray(
        [
            first_row.get("coverage_entry_x_m"),
            first_row.get("coverage_entry_z_m"),
            first_row.get("coverage_exit_x_m"),
            first_row.get("coverage_exit_z_m"),
        ],
        dtype=np.float64,
    )
    if plan_values.shape != (4,) or not np.isfinite(plan_values).all():
        raise HardBottomExecutionDiagnosticError(
            "coverage_plan_geometry_invalid"
        )
    entry_x, entry_z, exit_x, exit_z = (
        float(value) for value in plan_values
    )
    planned_depth = float(token[7] * DIG_CUT_DEPTH_SCALE_M)
    if planned_depth < 0.0:
        raise HardBottomExecutionDiagnosticError(
            "planned_depth_must_be_nonnegative"
        )
    logical_cell = _integer(
        first_row.get("planned_cut_cell_id", -1),
        "planned_cut_cell_id",
    )
    corridor = _integer(
        first_row.get("coverage_corridor_id", -1),
        "coverage_corridor_id",
    )
    for row, _ in cut_rows[1:]:
        row_token = np.asarray(row.get("dig_cut_tokens", []), dtype=np.float64)
        row_geometry = np.asarray(
            [
                row.get("coverage_entry_x_m"),
                row.get("coverage_entry_z_m"),
                row.get("coverage_exit_x_m"),
                row.get("coverage_exit_z_m"),
            ],
            dtype=np.float64,
        )
        if (
            row_token.shape != (10,)
            or not np.allclose(
                row_token,
                token,
                rtol=0.0,
                atol=1.0e-6,
            )
            or row_geometry.shape != (4,)
            or not np.allclose(
                row_geometry,
                plan_values,
                rtol=0.0,
                atol=1.0e-6,
            )
            or _integer(
                row.get("planned_cut_cell_id", -1),
                "planned_cut_cell_id",
            )
            != logical_cell
        ):
            raise HardBottomExecutionDiagnosticError(
                "cut_plan_changed_inside_continuous_dig"
            )
    footprint = CoverageSweptFootprint.from_segment(
        geometry=_coverage_geometry(env_state),
        entry_x_m=entry_x,
        entry_z_m=entry_z,
        exit_x_m=exit_x,
        exit_z_m=exit_z,
        worktool_width_m=worktool_width_m,
    )
    centerline = footprint.centerline_cell_ids
    swept = footprint.swept_cell_ids
    if not swept:
        raise HardBottomExecutionDiagnosticError(
            "planned_swept_footprint_outside_grid"
        )
    hard_bottom = float(env_state[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX])
    surface = np.asarray(
        env_state[
            ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
            ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
        ],
        dtype=np.float64,
    )
    if not math.isfinite(hard_bottom) or hard_bottom <= 0.0:
        raise HardBottomExecutionDiagnosticError(
            "hard_bottom_depth_invalid"
        )
    if surface.shape != (6,) or not np.isfinite(surface).all():
        raise HardBottomExecutionDiagnosticError(
            "surface_depth_grid_invalid"
        )
    remaining_by_cell = {
        str(cell_id): float(hard_bottom - float(surface[cell_id]))
        for cell_id in range(6)
    }
    clearance_by_cell = {
        str(cell_id): remaining_by_cell[str(cell_id)] - planned_depth
        for cell_id in swept
    }
    centerline_clearance = {
        str(cell_id): remaining_by_cell[str(cell_id)] - planned_depth
        for cell_id in centerline
    }
    direction = np.asarray(
        [exit_x - entry_x, exit_z - entry_z],
        dtype=np.float64,
    )
    length = float(np.linalg.norm(direction))
    if length <= 1.0e-9:
        raise HardBottomExecutionDiagnosticError(
            "planned_cut_segment_zero_length"
        )
    direction /= length
    return {
        "logical_cell_id": logical_cell,
        "corridor_id": corridor,
        "entry_x_m": entry_x,
        "entry_z_m": entry_z,
        "exit_x_m": exit_x,
        "exit_z_m": exit_z,
        "direction_x": float(direction[0]),
        "direction_z": float(direction[1]),
        "length_m": length,
        "planned_depth_m": planned_depth,
        "depth_token": float(token[7]),
        "depth_token_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
        "dig_cut_tokens": token.astype(float).tolist(),
        "hard_bottom_depth_m": hard_bottom,
        "surface_depth_m": surface.astype(float).tolist(),
        "local_remaining_depth_by_cell_m": remaining_by_cell,
        "centerline_physical_cell_ids": list(centerline),
        "swept_physical_cell_ids": list(swept),
        "planned_centerline_hard_bottom_clearance_by_cell_m": centerline_clearance,
        "planned_centerline_minimum_hard_bottom_clearance_m": min(
            centerline_clearance.values()
        ),
        "planned_hard_bottom_clearance_by_cell_m": clearance_by_cell,
        "planned_minimum_hard_bottom_clearance_m": min(
            clearance_by_cell.values()
        ),
    }


def _trajectory_records(
    *,
    indices: Sequence[int],
    step_ids: np.ndarray,
    env_states: np.ndarray,
    qpos: np.ndarray,
    qvel: np.ndarray,
    plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    entry = np.asarray(
        [plan["entry_x_m"], plan["entry_z_m"]],
        dtype=np.float64,
    )
    exit_ = np.asarray(
        [plan["exit_x_m"], plan["exit_z_m"]],
        dtype=np.float64,
    )
    records: list[dict[str, Any]] = []
    for index in indices:
        env = env_states[index]
        tip = env[
            ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
            ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
        ].astype(float)
        hard_bottom = float(
            env[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX]
        )
        plane_depth = float(
            env[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
        )
        cell_id = physical_cell_id(
            env, x_m=float(tip[0]), z_m=float(tip[2])
        )
        surface_depth = (
            float(env[ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + cell_id])
            if cell_id >= 0
            else None
        )
        remaining_depth = (
            float(hard_bottom - surface_depth)
            if surface_depth is not None
            else None
        )
        records.append(
            {
                "observation_step_id": int(step_ids[index]),
                "hdf5_index": int(index),
                "qpos": qpos[index].astype(float).tolist(),
                "qvel": qvel[index].astype(float).tolist(),
                "bucket_tip_xyz_m": tip.tolist(),
                "physical_cell_id": cell_id,
                "local_surface_depth_m": surface_depth,
                "local_remaining_depth_m": remaining_depth,
                "planned_clearance_from_local_surface_m": (
                    float(remaining_depth - float(plan["planned_depth_m"]))
                    if remaining_depth is not None
                    else None
                ),
                "env_state_local_penetration_m": float(
                    env[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX]
                ),
                "bucket_tip_plane_depth_m": plane_depth,
                "bucket_tip_hard_bottom_clearance_m": float(
                    hard_bottom - plane_depth
                ),
                "typed_bottom_contact": _bottom_mask(env),
                "point_to_planned_segment_error_m": _point_segment_distance(
                    np.asarray([tip[0], tip[2]], dtype=np.float64),
                    entry,
                    exit_,
                ),
            }
        )
    return records


def _aligned_actions(
    *,
    cut_rows: Sequence[tuple[Mapping[str, Any], int]],
    actions: np.ndarray,
    step_ids: np.ndarray,
) -> list[dict[str, Any]]:
    aligned: list[dict[str, Any]] = []
    for row, action_index in cut_rows:
        json_action = np.asarray(row.get("action", []), dtype=np.float64)
        hdf5_action = actions[action_index]
        if (
            json_action.shape != (4,)
            or not np.isfinite(json_action).all()
            or not np.allclose(
                json_action,
                hdf5_action,
                rtol=0.0,
                atol=1.0e-6,
            )
        ):
            raise HardBottomExecutionDiagnosticError(
                f"action_alignment_mismatch:step={int(step_ids[action_index])}"
            )
        aligned.append(
            {
                "action_step_id": int(step_ids[action_index]),
                "pre_action_observation_step_id": int(
                    step_ids[action_index - 1]
                ),
                "post_action_observation_step_id": int(
                    step_ids[action_index]
                ),
                "action": hdf5_action.astype(float).tolist(),
            }
        )
    return aligned


def _coverage_geometry(env_state: Any) -> CoverageWallGeometry:
    try:
        return CoverageWallGeometry.from_env_state(env_state)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HardBottomExecutionDiagnosticError(
            f"env_state_geometry_invalid:{exc}"
        ) from exc


def _axis_index(value: float, *, count: int, cell_size: float) -> int:
    half = 0.5 * count * cell_size
    if value < -half - _FLOAT_TOLERANCE or value > half + _FLOAT_TOLERANCE:
        return -1
    if math.isclose(value, half, rel_tol=0.0, abs_tol=_FLOAT_TOLERANCE):
        return count - 1
    index = int(math.floor((value + half) / cell_size))
    return index if 0 <= index < count else -1


def _point_segment_distance(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> float:
    delta = end - start
    denominator = float(np.dot(delta, delta))
    if denominator <= 1.0e-18:
        return float(np.linalg.norm(point - start))
    parameter = float(np.dot(point - start, delta) / denominator)
    projection = start + np.clip(parameter, 0.0, 1.0) * delta
    return float(np.linalg.norm(point - projection))


def _bottom_mask(env_state: np.ndarray) -> bool:
    return bool(
        float(
            env_state[
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX
            ]
        )
        >= 0.5
    )


def _action_index(
    row: Mapping[str, Any],
    *,
    index_by_step: Mapping[int, int],
) -> int:
    step_id = _integer(row.get("step_id"), "step_id")
    if step_id not in index_by_step:
        raise HardBottomExecutionDiagnosticError(
            f"jsonl_step_missing_from_hdf5:{step_id}"
        )
    return int(index_by_step[step_id])


def _validate_hdf5_arrays(
    *,
    step_ids: np.ndarray,
    env_states: np.ndarray,
    qpos: np.ndarray,
    qvel: np.ndarray,
    actions: np.ndarray,
) -> None:
    count = int(step_ids.size)
    if (
        count < 2
        or len(set(int(value) for value in step_ids)) != count
        or np.any(np.diff(step_ids) <= 0)
    ):
        raise HardBottomExecutionDiagnosticError(
            "hdf5_step_id_inventory_invalid"
        )
    required_env_dim = (
        ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX + 1
    )
    if (
        env_states.ndim != 2
        or env_states.shape[0] != count
        or env_states.shape[1] < required_env_dim
        or qpos.shape != (count, 4)
        or qvel.shape != (count, 4)
        or actions.shape != (count, 4)
    ):
        raise HardBottomExecutionDiagnosticError(
            "hdf5_rollout_shape_contract_invalid"
        )
    if not (
        np.isfinite(env_states).all()
        and np.isfinite(qpos).all()
        and np.isfinite(qvel).all()
        and np.isfinite(actions).all()
    ):
        raise HardBottomExecutionDiagnosticError(
            "hdf5_rollout_contains_non_finite_values"
        )


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(
            path.open(encoding="utf-8"),
            start=1,
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise HardBottomExecutionDiagnosticError(
                    f"jsonl_row_must_be_mapping:line={line_number}"
                )
            rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise HardBottomExecutionDiagnosticError(
            f"rollout_jsonl_invalid:{path}"
        ) from exc
    if not rows:
        raise HardBottomExecutionDiagnosticError("rollout_jsonl_empty")
    step_ids = [_integer(row.get("step_id"), "step_id") for row in rows]
    if len(set(step_ids)) != len(step_ids) or any(
        right <= left for left, right in zip(step_ids, step_ids[1:])
    ):
        raise HardBottomExecutionDiagnosticError(
            "jsonl_step_id_inventory_invalid"
        )
    return rows


def _require_file(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise HardBottomExecutionDiagnosticError(
            f"{label}_missing:{candidate}"
        )
    return candidate


def _finite_float(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise HardBottomExecutionDiagnosticError(
            f"{name}_must_be_finite"
        ) from exc
    if not math.isfinite(parsed):
        raise HardBottomExecutionDiagnosticError(
            f"{name}_must_be_finite"
        )
    return parsed


def _positive_float(value: Any, name: str) -> float:
    parsed = _finite_float(value, name)
    if parsed <= 0.0:
        raise HardBottomExecutionDiagnosticError(
            f"{name}_must_be_positive"
        )
    return parsed


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise HardBottomExecutionDiagnosticError(
            f"{name}_must_be_integer"
        )
    try:
        parsed = int(value)
        exact = float(value)
    except (TypeError, ValueError) as exc:
        raise HardBottomExecutionDiagnosticError(
            f"{name}_must_be_integer"
        ) from exc
    if not math.isfinite(exact) or not math.isclose(exact, float(parsed)):
        raise HardBottomExecutionDiagnosticError(
            f"{name}_must_be_integer"
        )
    return parsed


__all__ = [
    "DEFAULT_HARD_BOTTOM_MARGIN_M",
    "DEFAULT_WORKTOOL_WIDTH_M",
    "DIAGNOSIS_FILENAME",
    "DIAGNOSTIC_SCHEMA",
    "EVIDENCE_SCOPE",
    "HardBottomExecutionDiagnosticError",
    "SOURCE_MANIFEST_SCHEMA",
    "SOURCE_MANIFEST_FILENAME",
    "analyze_hard_bottom_execution",
    "build_hard_bottom_execution_diagnostic",
    "classify_hard_bottom_source",
    "physical_cell_id",
    "swept_cell_ids",
]
