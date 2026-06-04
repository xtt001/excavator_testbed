"""Typed planner observation snapshots for primitive scheduler services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from numpy.typing import NDArray

from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
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
