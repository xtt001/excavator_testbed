"""Typed planner observation snapshots for primitive scheduler services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)


@dataclass(frozen=True)
class PlannerObservationView:
    obs: Mapping[str, Any]
    env_state: NDArray[np.float32]
    qpos: NDArray[np.float32]
    qvel: NDArray[np.float32]
    task_metrics: Mapping[str, Any]
    action_dim: int
    mass_in_bucket_kg: float
    deposited_mass_kg: float
    min_distance_to_dig_area_m: float
    bucket_depth_below_dig_area_plane_m: float
    bucket_depth_below_local_surface_m: float
    bucket_dig_area_contact: bool
    bucket_dig_area_pose: tuple[float, float, float] | None
    bucket_tip_dig_area_pose: tuple[float, float, float] | None


@dataclass(frozen=True)
class PlannerSnapshot:
    view: PlannerObservationView
    active_skill: str
    cycle_index: int
    prev_action: NDArray[np.float32] | None
    boundary_event: object | None


@dataclass(frozen=True)
class BoundaryDetectorUpdateFacts:
    env_state: object
    action: object
    qpos: object
    reward_phase: object | None
    task_step_successes: object | None
    task_metrics: object | None


def build_planner_snapshot(
    obs: Mapping[str, Any],
    *,
    active_skill: str,
    cycle_index: int,
    prev_action: Any | None,
    boundary_event: object | None,
    action_dim: int,
) -> PlannerSnapshot:
    """Parse observation facts without making scheduler decisions."""

    dim = int(action_dim)
    env_state = np.asarray(obs.get("env_state", []), dtype=np.float32).reshape(-1)
    qpos = _state_vector(obs.get("qpos"), dim)
    qvel = _state_vector(obs.get("qvel"), dim)
    task_metrics = obs.get("task_metrics", {}) or {}
    if not isinstance(task_metrics, Mapping):
        task_metrics = {}
    prev = None
    if prev_action is not None:
        prev = np.asarray(prev_action, dtype=np.float32).reshape(-1).copy()

    view = PlannerObservationView(
        obs=obs,
        env_state=env_state,
        qpos=qpos,
        qvel=qvel,
        task_metrics=task_metrics,
        action_dim=dim,
        mass_in_bucket_kg=_metric_float(
            task_metrics,
            "mass_in_bucket_kg",
            _env_state_value(env_state, ENV_STATE_MASS_IN_BUCKET_IDX),
        ),
        deposited_mass_kg=_metric_float(
            task_metrics,
            "deposited_mass_in_target_box_kg",
            _env_state_value(env_state, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX),
        ),
        min_distance_to_dig_area_m=_metric_float(
            task_metrics,
            "min_distance_to_dig_area_m",
            _env_state_value(env_state, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX),
        ),
        bucket_depth_below_dig_area_plane_m=_metric_float(
            task_metrics,
            "bucket_depth_below_dig_area_plane_m",
            _env_state_value(env_state, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX),
        ),
        bucket_depth_below_local_surface_m=_metric_float(
            task_metrics,
            "bucket_depth_below_local_surface_m",
            _env_state_value(env_state, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX),
        ),
        bucket_dig_area_contact=_contact(task_metrics, env_state),
        bucket_dig_area_pose=_bucket_pose(env_state),
        bucket_tip_dig_area_pose=_bucket_tip_pose(env_state),
    )
    return PlannerSnapshot(
        view=view,
        active_skill=str(active_skill),
        cycle_index=int(cycle_index),
        prev_action=prev,
        boundary_event=boundary_event,
    )


def boundary_detector_update_facts_from_obs(
    obs: Mapping[str, Any],
    *,
    action: Any,
    action_dim: int,
    env_state_default_dim: int = 13,
) -> BoundaryDetectorUpdateFacts:
    """Project raw observation fields for the boundary detector update call."""

    return BoundaryDetectorUpdateFacts(
        env_state=obs.get(
            "env_state",
            np.zeros(int(env_state_default_dim), dtype=np.float32),
        ),
        action=action,
        qpos=obs.get("qpos", np.zeros(int(action_dim), dtype=np.float32)),
        reward_phase=obs.get("reward_phase"),
        task_step_successes=obs.get("task_step_successes"),
        task_metrics=obs.get("task_metrics"),
    )


def env_state_from_obs(
    obs: Mapping[str, Any],
    *,
    default_dim: int = 13,
) -> NDArray[np.float32]:
    return np.asarray(
        obs.get("env_state", np.zeros(int(default_dim), dtype=np.float32)),
        dtype=np.float32,
    ).reshape(-1)


def target_geometry_from_obs(obs: Mapping[str, Any]) -> dict[str, float]:
    task_metrics = _legacy_task_metrics(obs)
    env_state = env_state_from_obs(obs)

    def metric(name: str, index: int) -> float:
        if name in task_metrics:
            value = float(task_metrics[name])
            if np.isfinite(value):
                return value
        if len(env_state) <= index:
            raise RuntimeError(
                "primitive carry->dump switch requires Unity target geometry "
                f"field {name!r}; no legacy fallback is used."
            )
        value = float(env_state[index])
        if not np.isfinite(value):
            raise RuntimeError(
                "primitive carry->dump switch received non-finite target geometry "
                f"field {name!r}."
            )
        return value

    def optional_metric(name: str, index: int) -> float:
        if name in task_metrics:
            value = float(task_metrics[name])
            return value if np.isfinite(value) else float("nan")
        if len(env_state) <= index:
            return float("nan")
        value = float(env_state[index])
        return value if np.isfinite(value) else float("nan")

    available = task_metrics.get("target_geometry_available")
    if available is not None and float(available) <= 0.5:
        raise RuntimeError(
            "primitive carry->dump switch requires target_geometry_available=1."
        )

    return {
        "target_horizontal_distance_m": metric(
            "target_horizontal_distance_m",
            ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
        ),
        "bucket_height_above_target_rim_m": metric(
            "bucket_height_above_target_rim_m",
            ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        ),
        "bucket_over_target_footprint_mask": metric(
            "bucket_over_target_footprint_mask",
            ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        ),
        "dump_clearance_ok_mask": metric(
            "dump_clearance_ok_mask",
            ENV_STATE_DUMP_CLEARANCE_OK_IDX,
        ),
        "bucket_dump_area_relative_x_m": optional_metric(
            "bucket_dump_area_relative_x_m",
            ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
        ),
        "bucket_dump_area_relative_z_m": optional_metric(
            "bucket_dump_area_relative_z_m",
            ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
        ),
        "bucket_dump_area_footprint_outside_distance_m": optional_metric(
            "bucket_dump_area_footprint_outside_distance_m",
            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
        ),
    }


def mass_in_bucket_from_obs(obs: Mapping[str, Any]) -> float:
    return _legacy_metric_or_env(
        obs,
        "mass_in_bucket_kg",
        ENV_STATE_MASS_IN_BUCKET_IDX,
        missing_default=0.0,
    )


def deposited_mass_from_obs(obs: Mapping[str, Any]) -> float:
    return _legacy_metric_or_env(
        obs,
        "deposited_mass_in_target_box_kg",
        ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
        missing_default=0.0,
    )


def min_distance_to_dig_area_from_obs(obs: Mapping[str, Any]) -> float:
    return _legacy_metric_or_env(
        obs,
        "min_distance_to_dig_area_m",
        ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
        missing_default=0.0,
    )


def bucket_depth_below_dig_area_plane_from_obs(obs: Mapping[str, Any]) -> float:
    return _legacy_metric_or_env(
        obs,
        "bucket_depth_below_dig_area_plane_m",
        ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
        missing_default=0.0,
    )


def bucket_depth_below_local_surface_from_obs(obs: Mapping[str, Any]) -> float:
    return _legacy_metric_or_env(
        obs,
        "bucket_depth_below_local_surface_m",
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        missing_default=float("nan"),
    )


def bucket_dig_area_contact_mask_from_obs(obs: Mapping[str, Any]) -> bool:
    task_metrics = _legacy_task_metrics(obs)
    if "bucket_dig_area_penetration_contact_mask" in task_metrics:
        return bool(float(task_metrics["bucket_dig_area_penetration_contact_mask"]) > 0.5)
    if "bucket_contact_dig_area_mask" in task_metrics:
        return bool(float(task_metrics["bucket_contact_dig_area_mask"]) > 0.5)
    env_state = env_state_from_obs(obs)
    return bool(
        len(env_state) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX
        and float(env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX]) > 0.5
    )


def bucket_dig_area_cell_in_bounds_mask_from_obs(obs: Mapping[str, Any]) -> bool:
    env_state = env_state_from_obs(obs)
    return bool(
        len(env_state) > ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX
        and float(env_state[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX]) > 0.5
    )


def dig_cell_id_from_obs(obs: Mapping[str, Any]) -> int:
    env_state = env_state_from_obs(obs)
    if len(env_state) <= ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
        return -1
    value = float(env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX])
    if not np.isfinite(value):
        return -1
    return int(round(value))


def bucket_dig_area_pose_from_obs(
    obs: Mapping[str, Any],
) -> tuple[float, float, float] | None:
    return _bucket_pose(env_state_from_obs(obs))


def bucket_tip_dig_area_pose_from_obs(
    obs: Mapping[str, Any],
) -> tuple[float, float, float] | None:
    return _bucket_tip_pose(env_state_from_obs(obs))


def _legacy_task_metrics(obs: Mapping[str, Any]) -> dict[str, Any]:
    return dict(obs.get("task_metrics", {}) or {})


def _legacy_metric_or_env(
    obs: Mapping[str, Any],
    key: str,
    index: int,
    *,
    missing_default: float,
) -> float:
    task_metrics = _legacy_task_metrics(obs)
    if key in task_metrics:
        return float(task_metrics[key])
    env_state = env_state_from_obs(obs)
    return float(env_state[index]) if len(env_state) > index else float(missing_default)


def _env_state_value(env_state: NDArray[np.float32], index: int) -> float:
    if len(env_state) <= int(index):
        return float("nan")
    return float(env_state[int(index)])


def _state_vector(value: Any | None, action_dim: int) -> NDArray[np.float32]:
    if value is None:
        value = np.zeros(int(action_dim), dtype=np.float32)
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    if arr.size >= int(action_dim):
        return arr
    padded = np.zeros(int(action_dim), dtype=np.float32)
    padded[: arr.size] = arr
    return padded


def _metric_float(
    task_metrics: Mapping[str, Any],
    key: str,
    fallback: float,
) -> float:
    try:
        return float(task_metrics.get(key, fallback))
    except (TypeError, ValueError):
        return float(fallback)


def _contact(task_metrics: Mapping[str, Any], env_state: NDArray[np.float32]) -> bool:
    for key in (
        "bucket_dig_area_penetration_contact_mask",
        "bucket_contact_dig_area_mask",
    ):
        if key in task_metrics:
            try:
                return bool(float(task_metrics[key]) > 0.5)
            except (TypeError, ValueError):
                return False
    return bool(
        len(env_state) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX
        and float(env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX]) > 0.5
    )


def _bucket_pose(env_state: NDArray[np.float32]) -> tuple[float, float, float] | None:
    indices = (
        ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
        ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
        ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    )
    if len(env_state) <= max(indices):
        return None
    pose = tuple(float(env_state[index]) for index in indices)
    if not all(np.isfinite(pose)):
        return None
    return pose


def _bucket_tip_pose(
    env_state: NDArray[np.float32],
) -> tuple[float, float, float] | None:
    tip_indices = (
        ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
        ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
        ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    )
    if len(env_state) > max(tip_indices):
        pose = tuple(float(env_state[index]) for index in tip_indices)
        if all(np.isfinite(pose)):
            return pose
    return _bucket_pose(env_state)
