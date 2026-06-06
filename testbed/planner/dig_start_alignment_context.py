"""Pre-dig alignment config and facts projection contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from testbed.planner.snapshots import (
    bucket_depth_below_local_surface_from_obs,
    bucket_dig_area_contact_mask_from_obs,
    bucket_dig_area_pose_from_obs,
    bucket_tip_dig_area_pose_from_obs,
)

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView


@dataclass(frozen=True)
class DigStartAlignmentConfig:
    action_dim: int
    qpos_min: np.ndarray
    qpos_max: np.ndarray
    qpos_from_token_coefficients: np.ndarray
    controlled_dims: np.ndarray
    entry_intent_controlled_dims: np.ndarray | None
    bucket_target_qpos: float | None
    kp: float
    kd: float
    action_clip: float | np.ndarray | list[float] | tuple[float, ...]
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None = None
    enabled: bool = False
    qpos_tolerance: np.ndarray | None = None
    qvel_abs_max: float = 0.12
    hold_steps: int = 1
    max_entry_error_m: float | None = None
    timeout_accept_entry_error_m: float | None = None
    start_envelope_enabled: bool = False
    start_envelope_max_entry_error_m: float = 0.65
    first_dig_entry_close_handoff: bool = False
    first_dig_entry_close_handoff_qvel_abs_max: float | None = None
    entry_intent_handoff_enabled: bool = False
    surface_guard_enabled: bool = False
    surface_guard_max_penetration_m: float = 0.005
    surface_guard_handoff_entry_error_m: float | None = None
    surface_guard_use_contact_fallback: bool = True
    start_qpos_min: np.ndarray | None = None
    start_qpos_max: np.ndarray | None = None
    start_pose_min: np.ndarray | None = None
    start_pose_max: np.ndarray | None = None


DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("action_dim", "action_dim"),
    *(
        (key, f"pre_dig_align_{key}")
        for key in (
            "qpos_min", "qpos_max",
            "qpos_from_token_coefficients",
            "controlled_dims", "entry_intent_controlled_dims",
            "bucket_target_qpos", "kp", "kd",
            "action_clip", "action_signs", "enabled",
            "qpos_tolerance", "qvel_abs_max", "hold_steps",
            "max_entry_error_m",
            "timeout_accept_entry_error_m",
            "start_envelope_enabled", "start_envelope_max_entry_error_m",
            "first_dig_entry_close_handoff",
            "first_dig_entry_close_handoff_qvel_abs_max",
            "entry_intent_handoff_enabled",
            "surface_guard_enabled", "surface_guard_max_penetration_m",
            "surface_guard_handoff_entry_error_m",
            "surface_guard_use_contact_fallback",
            "start_qpos_min", "start_qpos_max",
            "start_pose_min", "start_pose_max",
        )
    ),
)


def build_dig_start_alignment_runtime_config(
    *,
    action_dim: int,
    qpos_min: np.ndarray,
    qpos_max: np.ndarray,
    qpos_from_token_coefficients: np.ndarray,
    controlled_dims: np.ndarray,
    entry_intent_controlled_dims: np.ndarray | None,
    bucket_target_qpos: float | None,
    kp: float,
    kd: float,
    action_clip: float | np.ndarray | list[float] | tuple[float, ...],
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None,
    enabled: bool,
    qpos_tolerance: np.ndarray | None,
    qvel_abs_max: float,
    hold_steps: int,
    max_entry_error_m: float | None,
    timeout_accept_entry_error_m: float | None,
    start_envelope_enabled: bool,
    start_envelope_max_entry_error_m: float,
    first_dig_entry_close_handoff: bool,
    first_dig_entry_close_handoff_qvel_abs_max: float | None,
    entry_intent_handoff_enabled: bool,
    surface_guard_enabled: bool,
    surface_guard_max_penetration_m: float,
    surface_guard_handoff_entry_error_m: float | None,
    surface_guard_use_contact_fallback: bool,
    start_qpos_min: np.ndarray | None,
    start_qpos_max: np.ndarray | None,
    start_pose_min: np.ndarray | None,
    start_pose_max: np.ndarray | None,
) -> DigStartAlignmentConfig:
    return DigStartAlignmentConfig(
        action_dim=int(action_dim),
        qpos_min=qpos_min,
        qpos_max=qpos_max,
        qpos_from_token_coefficients=qpos_from_token_coefficients,
        controlled_dims=controlled_dims,
        entry_intent_controlled_dims=(
            None
            if entry_intent_controlled_dims is None
            else entry_intent_controlled_dims
        ),
        bucket_target_qpos=bucket_target_qpos,
        kp=float(kp),
        kd=float(kd),
        action_clip=action_clip,
        action_signs=action_signs,
        enabled=bool(enabled),
        qpos_tolerance=qpos_tolerance,
        qvel_abs_max=float(qvel_abs_max),
        hold_steps=int(hold_steps),
        max_entry_error_m=max_entry_error_m,
        timeout_accept_entry_error_m=timeout_accept_entry_error_m,
        start_envelope_enabled=bool(start_envelope_enabled),
        start_envelope_max_entry_error_m=float(start_envelope_max_entry_error_m),
        first_dig_entry_close_handoff=bool(first_dig_entry_close_handoff),
        first_dig_entry_close_handoff_qvel_abs_max=(
            first_dig_entry_close_handoff_qvel_abs_max
        ),
        entry_intent_handoff_enabled=bool(entry_intent_handoff_enabled),
        surface_guard_enabled=bool(surface_guard_enabled),
        surface_guard_max_penetration_m=float(surface_guard_max_penetration_m),
        surface_guard_handoff_entry_error_m=surface_guard_handoff_entry_error_m,
        surface_guard_use_contact_fallback=bool(surface_guard_use_contact_fallback),
        start_qpos_min=start_qpos_min,
        start_qpos_max=start_qpos_max,
        start_pose_min=start_pose_min,
        start_pose_max=start_pose_max,
    )


def build_dig_start_alignment_runtime_config_from_mapping(
    values: Mapping[str, object],
) -> DigStartAlignmentConfig:
    kwargs = {key: values[key] for key, _ in DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS}
    return build_dig_start_alignment_runtime_config(**kwargs)


@dataclass(frozen=True)
class DigStartAlignmentFacts:
    qpos: np.ndarray
    qvel: np.ndarray
    target_qpos: np.ndarray | None = None
    entry_error_m: float = float("nan")
    bucket_pose: tuple[float, float, float] | None = None
    surface_depth_m: float = float("nan")
    contact_mask: bool = False
    cycle_index: int = 0
    hold_count: int = 0


@dataclass(frozen=True)
class DigStartAlignmentEntryErrorFacts:
    bucket_tip_dig_area_pose: tuple[float, float, float] | None
    active_corridor_entry_xz: tuple[float, float] | None


DIG_START_ALIGNMENT_FACT_FIELDS: tuple[str, ...] = (
    "action_dim",
    "qpos",
    "qvel",
    "target_qpos",
    "entry_error_m",
    "bucket_pose",
    "surface_depth_m",
    "contact_mask",
    "cycle_index",
    "hold_count",
)


def build_dig_start_alignment_facts(
    *,
    action_dim: int,
    qpos: np.ndarray | list[float] | tuple[float, ...] | None,
    qvel: np.ndarray | list[float] | tuple[float, ...] | None,
    target_qpos: np.ndarray | list[float] | tuple[float, ...] | None = None,
    entry_error_m: float = float("nan"),
    bucket_pose: tuple[float, float, float] | None = None,
    surface_depth_m: float = float("nan"),
    contact_mask: bool = False,
    cycle_index: int = 0,
    hold_count: int = 0,
) -> DigStartAlignmentFacts:
    dim = int(action_dim)
    qpos_arr = (
        np.zeros(dim, dtype=np.float32)
        if qpos is None
        else np.asarray(qpos, dtype=np.float32).reshape(dim)
    )
    qvel_arr = (
        np.zeros(dim, dtype=np.float32)
        if qvel is None
        else np.asarray(qvel, dtype=np.float32).reshape(dim)
    )
    target = (
        None
        if target_qpos is None
        else np.asarray(target_qpos, dtype=np.float32).reshape(dim)
    )
    return DigStartAlignmentFacts(
        qpos=qpos_arr,
        qvel=qvel_arr,
        target_qpos=target,
        entry_error_m=float(entry_error_m),
        bucket_pose=bucket_pose,
        surface_depth_m=float(surface_depth_m),
        contact_mask=bool(contact_mask),
        cycle_index=int(cycle_index),
        hold_count=int(hold_count),
    )


def build_dig_start_alignment_facts_from_mapping(
    values: Mapping[str, object],
) -> DigStartAlignmentFacts:
    return build_dig_start_alignment_facts(
        action_dim=int(values["action_dim"]),
        qpos=values["qpos"],
        qvel=values["qvel"],
        target_qpos=values["target_qpos"],
        entry_error_m=values["entry_error_m"],
        bucket_pose=values["bucket_pose"],
        surface_depth_m=values["surface_depth_m"],
        contact_mask=bool(values["contact_mask"]),
        cycle_index=int(values["cycle_index"]),
        hold_count=int(values["hold_count"]),
    )


def build_dig_start_alignment_facts_from_observation_view(
    *,
    view: PlannerObservationView,
    target_qpos: np.ndarray | None = None,
    entry_error_m: float = float("nan"),
    qpos: np.ndarray | None = None,
    qvel: np.ndarray | None = None,
    cycle_index: int = 0,
    hold_count: int = 0,
) -> DigStartAlignmentFacts:
    return build_dig_start_alignment_facts(
        action_dim=int(view.action_dim),
        qpos=(
            qpos
            if qpos is not None
            else view.obs.get(
                "qpos",
                np.zeros(int(view.action_dim), dtype=np.float32),
            )
        ),
        qvel=(
            qvel
            if qvel is not None
            else view.obs.get(
                "qvel",
                np.zeros(int(view.action_dim), dtype=np.float32),
            )
        ),
        target_qpos=target_qpos,
        entry_error_m=entry_error_m,
        bucket_pose=bucket_dig_area_pose_from_obs(view.obs),
        surface_depth_m=bucket_depth_below_local_surface_from_obs(view.obs),
        contact_mask=bucket_dig_area_contact_mask_from_obs(view.obs),
        cycle_index=cycle_index,
        hold_count=hold_count,
    )


def build_dig_start_alignment_entry_error_facts_from_observation_view(
    *,
    view: PlannerObservationView,
    active_corridor_entry_xz: tuple[float, float] | None,
) -> DigStartAlignmentEntryErrorFacts:
    return DigStartAlignmentEntryErrorFacts(
        bucket_tip_dig_area_pose=bucket_tip_dig_area_pose_from_obs(view.obs),
        active_corridor_entry_xz=active_corridor_entry_xz,
    )


def dig_start_alignment_entry_error(
    facts: DigStartAlignmentEntryErrorFacts,
) -> float:
    pose = facts.bucket_tip_dig_area_pose
    entry_xz = facts.active_corridor_entry_xz
    if pose is None or entry_xz is None:
        return float("nan")
    dx = float(pose[0]) - float(entry_xz[0])
    dz = float(pose[2]) - float(entry_xz[1])
    return float(np.hypot(dx, dz))
