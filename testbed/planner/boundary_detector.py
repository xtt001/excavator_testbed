"""Cycle-boundary and event detection for AGX multicycle excavation rollouts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_CONTACT_DUMP_AREA_MASK_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_EXCAVATED_MASS_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
)


MODE_WORK = 0
MODE_TRANSITION = 1

QUALIFIED_DIG_START_MODE_PROGRESS = "progress"
QUALIFIED_DIG_START_MODE_CONTACT_DEPTH = "contact_depth"
QUALIFIED_DIG_START_MODES = {
    QUALIFIED_DIG_START_MODE_PROGRESS,
    QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
}
BOUNDARY_PROFILE_LEGACY = "legacy"
BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS = "v2_4_5_spatial_mass"
BOUNDARY_PROFILES = {
    BOUNDARY_PROFILE_LEGACY,
    BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
}


@dataclass(frozen=True)
class BoundaryDetectorConfig:
    boundary_profile: str = BOUNDARY_PROFILE_LEGACY
    target_approach_distance_m: float = 1.25
    dig_area_touch_tolerance_m: float = 0.05
    dig_below_plane_depth_tolerance_m: float = 0.02
    qualified_dig_start_mode: str = QUALIFIED_DIG_START_MODE_PROGRESS
    delta_mass_start_kg: float = 5.0
    target_mass_delta_tol_kg: float = 2.0
    dump_start_min_cumulative_deposit_delta_kg: float = 5.0
    residual_bucket_mass_thresh: float = 100.0
    deposit_plateau_steps: int = 3
    pause_action_eps: float = 0.05
    dig_complete_min_bucket_mass_kg: float = 15.0
    dig_complete_mass_plateau_epsilon_kg: float = 1.0
    dig_complete_mass_plateau_hold_steps: int = 8
    dig_complete_departed_distance_m: float = 0.08
    dig_complete_departed_hold_steps: int = 3
    dump_committed_min_bucket_mass_kg: float = 15.0
    dump_committed_min_height_above_rim_m: float = 0.45
    dump_committed_max_outside_distance_m: float = 0.45
    dump_committed_min_relative_x_m: float = -0.4
    dump_committed_max_relative_x_m: float = 2.1
    dump_committed_min_relative_z_m: float = 0.3
    dump_committed_max_relative_z_m: float = 2.3
    dump_committed_require_clearance: bool = False
    dump_committed_hold_steps: int = 3
    release_onset_min_bucket_mass_drop_kg: float = 0.5
    release_onset_min_deposit_gain_kg: float = 0.5


@dataclass(frozen=True)
class BoundaryStepEvent:
    step_index: int
    cycle_id: int
    mode_id: int
    qualified_dig_start: bool
    dump_start: bool
    dump_end: bool
    boundary: bool
    pause: bool
    metrics: dict[str, float]
    dig_start: bool = False
    dig_complete: bool = False
    dump_committed_start: bool = False
    release_onset: bool = False
    dump_complete: bool = False
    next_dig_entry_ready: bool = False


def build_boundary_detector_from_config(
    *,
    reward_cfg: dict[str, Any] | None = None,
    success_cfg: dict[str, Any] | None = None,
    boundary_cfg: dict[str, Any] | None = None,
    pause_action_eps: float = 0.05,
) -> "BoundaryDetector":
    reward_cfg = dict(reward_cfg or {})
    success_cfg = dict(success_cfg or {})
    boundary_cfg = dict(boundary_cfg or {})
    qualified_dig_start_mode = str(
        reward_cfg.get(
            "qualified_dig_start_mode",
            QUALIFIED_DIG_START_MODE_PROGRESS,
        )
    )
    return BoundaryDetector(
        BoundaryDetectorConfig(
            boundary_profile=str(
                boundary_cfg.get(
                    "profile",
                    boundary_cfg.get(
                        "boundary_profile",
                        reward_cfg.get(
                            "boundary_profile",
                            success_cfg.get("boundary_profile", BOUNDARY_PROFILE_LEGACY),
                        ),
                    ),
                )
            ),
            target_approach_distance_m=float(
                reward_cfg.get("target_approach_distance_m", 1.25)
            ),
            dig_area_touch_tolerance_m=float(
                reward_cfg.get("dig_area_touch_tolerance_m", 0.05)
            ),
            dig_below_plane_depth_tolerance_m=float(
                reward_cfg.get("dig_below_plane_depth_tolerance_m", 0.02)
            ),
            qualified_dig_start_mode=qualified_dig_start_mode,
            delta_mass_start_kg=float(reward_cfg.get("delta_mass_start_kg", 5.0)),
            target_mass_delta_tol_kg=float(
                reward_cfg.get("target_mass_delta_tol_kg", 2.0)
            ),
            dump_start_min_cumulative_deposit_delta_kg=float(
                success_cfg.get(
                    "dump_start_min_cumulative_deposit_delta_kg",
                    reward_cfg.get("deposit_started_threshold_kg", 5.0),
                )
            ),
            residual_bucket_mass_thresh=float(
                success_cfg.get(
                    "residual_bucket_mass_thresh",
                    success_cfg.get("bucket_residual_mass_thresh", 100.0),
                )
            ),
            deposit_plateau_steps=int(
                success_cfg.get("deposit_plateau_steps", 3)
            ),
            pause_action_eps=float(pause_action_eps),
            dig_complete_min_bucket_mass_kg=float(
                boundary_cfg.get("dig_complete_min_bucket_mass_kg", 15.0)
            ),
            dig_complete_mass_plateau_epsilon_kg=float(
                boundary_cfg.get("dig_complete_mass_plateau_epsilon_kg", 1.0)
            ),
            dig_complete_mass_plateau_hold_steps=int(
                boundary_cfg.get("dig_complete_mass_plateau_hold_steps", 8)
            ),
            dig_complete_departed_distance_m=float(
                boundary_cfg.get("dig_complete_departed_distance_m", 0.08)
            ),
            dig_complete_departed_hold_steps=int(
                boundary_cfg.get("dig_complete_departed_hold_steps", 3)
            ),
            dump_committed_min_bucket_mass_kg=float(
                boundary_cfg.get("dump_committed_min_bucket_mass_kg", 15.0)
            ),
            dump_committed_min_height_above_rim_m=float(
                boundary_cfg.get("dump_committed_min_height_above_rim_m", 0.45)
            ),
            dump_committed_max_outside_distance_m=float(
                boundary_cfg.get("dump_committed_max_outside_distance_m", 0.45)
            ),
            dump_committed_min_relative_x_m=float(
                boundary_cfg.get("dump_committed_min_relative_x_m", -0.4)
            ),
            dump_committed_max_relative_x_m=float(
                boundary_cfg.get("dump_committed_max_relative_x_m", 2.1)
            ),
            dump_committed_min_relative_z_m=float(
                boundary_cfg.get("dump_committed_min_relative_z_m", 0.3)
            ),
            dump_committed_max_relative_z_m=float(
                boundary_cfg.get("dump_committed_max_relative_z_m", 2.3)
            ),
            dump_committed_require_clearance=bool(
                boundary_cfg.get("dump_committed_require_clearance", False)
            ),
            dump_committed_hold_steps=int(
                boundary_cfg.get("dump_committed_hold_steps", 3)
            ),
            release_onset_min_bucket_mass_drop_kg=float(
                boundary_cfg.get("release_onset_min_bucket_mass_drop_kg", 0.5)
            ),
            release_onset_min_deposit_gain_kg=float(
                boundary_cfg.get("release_onset_min_deposit_gain_kg", 0.5)
            ),
        )
    )


class BoundaryDetector:
    """Stateful detector for dig-start and dump-end events."""

    def __init__(self, config: BoundaryDetectorConfig | None = None) -> None:
        self.config = config or BoundaryDetectorConfig()
        if self.config.boundary_profile not in BOUNDARY_PROFILES:
            raise ValueError(
                "Unsupported boundary_profile "
                f"{self.config.boundary_profile!r}; expected one of "
                f"{sorted(BOUNDARY_PROFILES)}."
            )
        if self.config.qualified_dig_start_mode not in QUALIFIED_DIG_START_MODES:
            raise ValueError(
                "Unsupported qualified_dig_start_mode "
                f"{self.config.qualified_dig_start_mode!r}; expected one of "
                f"{sorted(QUALIFIED_DIG_START_MODES)}."
            )
        self.reset()

    def reset(self) -> None:
        self._step_index = -1
        self._current_cycle_id = -1
        self._awaiting_next_dig = True
        self._dump_started = False
        self._completed_dump_count = 0
        self._plateau_count = 0
        self._qualified_condition_active = False
        self._cycle_start_deposited_mass_kg = 0.0
        self._cycle_start_target_mass_kg = 0.0
        self._dig_complete_seen = False
        self._dig_best_mass_kg = 0.0
        self._dig_mass_plateau_count = 0
        self._dig_departed_hold_count = 0
        self._dump_committed_hold_count = 0
        self._release_onset_seen = False
        self._last_metrics: dict[str, float] | None = None

    @property
    def completed_dump_count(self) -> int:
        return int(self._completed_dump_count)

    def update(
        self,
        *,
        env_state: np.ndarray | list[float] | tuple[float, ...],
        action: np.ndarray | list[float] | tuple[float, ...] | None = None,
        qpos: np.ndarray | list[float] | tuple[float, ...] | None = None,
        reward_phase: str | None = None,
        task_step_successes: list[str] | tuple[str, ...] | None = None,
        task_metrics: dict[str, Any] | None = None,
    ) -> BoundaryStepEvent:
        self._step_index += 1
        env_state_arr = np.asarray(env_state, dtype=np.float32).reshape(-1)
        action_arr = (
            np.zeros(4, dtype=np.float32)
            if action is None
            else np.asarray(action, dtype=np.float32).reshape(-1)
        )
        qpos_arr = (
            None if qpos is None else np.asarray(qpos, dtype=np.float32).reshape(-1)
        )
        task_metrics = dict(task_metrics or {})
        task_step_successes = tuple(str(item) for item in (task_step_successes or ()))
        metrics = self._build_metrics_snapshot(
            env_state=env_state_arr,
            qpos=qpos_arr,
            reward_phase=reward_phase,
            task_step_successes=task_step_successes,
            task_metrics=task_metrics,
        )
        if self.config.boundary_profile == BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS:
            return self._update_v2_4_5_spatial_mass(
                metrics=metrics,
                action_arr=action_arr,
            )

        qualified_condition = self._is_qualified_dig_condition(metrics)
        qualified_dig_start = bool(
            qualified_condition
            and not self._qualified_condition_active
            and (self._current_cycle_id < 0 or self._awaiting_next_dig)
        )
        self._qualified_condition_active = bool(qualified_condition)
        if qualified_dig_start:
            self._current_cycle_id += 1
            self._awaiting_next_dig = False
            self._dump_started = False
            self._plateau_count = 0
            self._cycle_start_deposited_mass_kg = metrics[
                "deposited_mass_in_target_box_kg"
            ]
            self._cycle_start_target_mass_kg = metrics["mass_in_target_box_kg"]

        dump_start_condition = self._is_dump_start_condition(metrics)
        dump_start = bool(
            self._current_cycle_id >= 0
            and not self._awaiting_next_dig
            and not self._dump_started
            and dump_start_condition
        )
        if dump_start:
            self._dump_started = True
            self._plateau_count = 0

        dump_end = False
        if self._dump_started and not self._awaiting_next_dig:
            if abs(metrics["delta_deposited_mass_in_target_box_kg"]) < self.config.target_mass_delta_tol_kg:
                self._plateau_count += 1
            else:
                self._plateau_count = 0
            if (
                metrics["mass_in_bucket_kg"] <= self.config.residual_bucket_mass_thresh
                and self._plateau_count >= self.config.deposit_plateau_steps
            ):
                dump_end = True
                self._awaiting_next_dig = True
                self._dump_started = False
                self._plateau_count = 0
                self._completed_dump_count += 1

        pause = bool(np.sum(np.abs(action_arr)) < self.config.pause_action_eps)
        mode_id = (
            MODE_TRANSITION
            if (self._current_cycle_id < 0 or self._awaiting_next_dig)
            else MODE_WORK
        )
        boundary = bool(qualified_dig_start and self._current_cycle_id > 0)

        self._last_metrics = dict(metrics)
        return BoundaryStepEvent(
            step_index=int(self._step_index),
            cycle_id=int(self._current_cycle_id),
            mode_id=int(mode_id),
            qualified_dig_start=qualified_dig_start,
            dump_start=dump_start,
            dump_end=dump_end,
            boundary=boundary,
            pause=pause,
            metrics=metrics,
            dig_start=qualified_dig_start,
            dump_committed_start=dump_start,
            dump_complete=dump_end,
            next_dig_entry_ready=bool(
                qualified_dig_start and self._current_cycle_id > 0
            ),
        )

    def _update_v2_4_5_spatial_mass(
        self,
        *,
        metrics: dict[str, float],
        action_arr: np.ndarray,
    ) -> BoundaryStepEvent:
        qualified_condition = self._is_qualified_dig_condition(metrics)
        qualified_dig_start = bool(
            qualified_condition
            and not self._qualified_condition_active
            and (self._current_cycle_id < 0 or self._awaiting_next_dig)
        )
        self._qualified_condition_active = bool(qualified_condition)

        next_dig_entry_ready = False
        if qualified_dig_start:
            self._current_cycle_id += 1
            next_dig_entry_ready = bool(self._current_cycle_id > 0)
            self._awaiting_next_dig = False
            self._dump_started = False
            self._plateau_count = 0
            self._dig_complete_seen = False
            self._dig_best_mass_kg = max(0.0, metrics["mass_in_bucket_kg"])
            self._dig_mass_plateau_count = 0
            self._dig_departed_hold_count = 0
            self._dump_committed_hold_count = 0
            self._release_onset_seen = False
            self._cycle_start_deposited_mass_kg = metrics[
                "deposited_mass_in_target_box_kg"
            ]
            self._cycle_start_target_mass_kg = metrics["mass_in_target_box_kg"]

        dig_complete = False
        dump_committed_start = False
        release_onset = False
        dump_complete = False

        if self._current_cycle_id >= 0 and not self._awaiting_next_dig:
            dig_complete = self._update_dig_complete_state(metrics)
            committed_condition = self._is_dump_committed_condition(metrics)
            if (
                not self._dump_started
                and self._dig_complete_seen
                and committed_condition
            ):
                self._dump_committed_hold_count += 1
            elif not self._dump_started:
                self._dump_committed_hold_count = 0
            if (
                not self._dump_started
                and self._dump_committed_hold_count
                >= max(1, int(self.config.dump_committed_hold_steps))
            ):
                dump_committed_start = True
                self._dump_started = True
                self._plateau_count = 0

            if self._dump_started and not self._release_onset_seen:
                release_onset = self._is_release_onset_condition(metrics)
                if release_onset:
                    self._release_onset_seen = True
                    self._plateau_count = 0

            if self._release_onset_seen:
                if (
                    abs(metrics["delta_deposited_mass_in_target_box_kg"])
                    < self.config.target_mass_delta_tol_kg
                    and abs(metrics["delta_deposited_mass_in_dump_area_kg"])
                    < self.config.target_mass_delta_tol_kg
                ):
                    self._plateau_count += 1
                else:
                    self._plateau_count = 0
                if (
                    metrics["mass_in_bucket_kg"]
                    <= self.config.residual_bucket_mass_thresh
                    and self._plateau_count >= self.config.deposit_plateau_steps
                ):
                    dump_complete = True
                    self._awaiting_next_dig = True
                    self._dump_started = False
                    self._plateau_count = 0
                    self._dump_committed_hold_count = 0
                    self._completed_dump_count += 1

        pause = bool(np.sum(np.abs(action_arr)) < self.config.pause_action_eps)
        mode_id = (
            MODE_TRANSITION
            if (self._current_cycle_id < 0 or self._awaiting_next_dig)
            else MODE_WORK
        )
        boundary = bool(next_dig_entry_ready)
        self._last_metrics = dict(metrics)
        return BoundaryStepEvent(
            step_index=int(self._step_index),
            cycle_id=int(self._current_cycle_id),
            mode_id=int(mode_id),
            qualified_dig_start=qualified_dig_start,
            dump_start=dump_committed_start,
            dump_end=dump_complete,
            boundary=boundary,
            pause=pause,
            metrics=metrics,
            dig_start=qualified_dig_start,
            dig_complete=dig_complete,
            dump_committed_start=dump_committed_start,
            release_onset=release_onset,
            dump_complete=dump_complete,
            next_dig_entry_ready=next_dig_entry_ready,
        )

    def _build_metrics_snapshot(
        self,
        *,
        env_state: np.ndarray,
        qpos: np.ndarray | None,
        reward_phase: str | None,
        task_step_successes: tuple[str, ...],
        task_metrics: dict[str, Any],
    ) -> dict[str, float]:
        previous = self._last_metrics

        def _read_env(index: int) -> float:
            if index >= len(env_state):
                return 0.0
            return float(env_state[index])

        def _read_env_optional(index: int) -> tuple[float, bool]:
            if index < 0 or index >= len(env_state):
                return 0.0, False
            value = float(env_state[index])
            if not np.isfinite(value):
                return 0.0, False
            return value, True

        mass_in_bucket = float(
            task_metrics.get("mass_in_bucket_kg", _read_env(ENV_STATE_MASS_IN_BUCKET_IDX))
        )
        excavated_mass = float(
            task_metrics.get("excavated_mass_kg", _read_env(ENV_STATE_EXCAVATED_MASS_IDX))
        )
        mass_in_target_box = float(
            task_metrics.get(
                "mass_in_target_box_kg",
                _read_env(ENV_STATE_MASS_IN_TARGET_BOX_IDX),
            )
        )
        deposited_mass = float(
            task_metrics.get(
                "deposited_mass_in_target_box_kg",
                _read_env(ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX),
            )
        )
        min_distance_to_target = float(
            task_metrics.get(
                "min_distance_to_target_m",
                _read_env(ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX),
            )
        )
        target_horizontal_distance, has_target_horizontal_distance = _read_env_optional(
            ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX
        )
        bucket_height_above_target_rim, has_target_height = _read_env_optional(
            ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX
        )
        bucket_over_target_footprint, has_target_footprint = _read_env_optional(
            ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX
        )
        dump_clearance_ok_mask, has_dump_clearance = _read_env_optional(
            ENV_STATE_DUMP_CLEARANCE_OK_IDX
        )
        dump_area_relative_x, has_dump_area_relative_x = _read_env_optional(
            ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX
        )
        dump_area_relative_z, has_dump_area_relative_z = _read_env_optional(
            ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX
        )
        dump_area_outside_distance, has_dump_area_outside = _read_env_optional(
            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX
        )
        deposited_mass_in_dump_area = float(
            task_metrics.get(
                "deposited_mass_in_dump_area_kg",
                _read_env(ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX),
            )
        )
        bucket_contact_dig_area = float(
            task_metrics.get(
                "bucket_contact_dig_area_mask",
                _read_env(ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX),
            )
        )
        bucket_contact_dump_area = float(
            task_metrics.get(
                "bucket_contact_dump_area_mask",
                _read_env(ENV_STATE_BUCKET_CONTACT_DUMP_AREA_MASK_IDX),
            )
        )
        if "target_horizontal_distance_m" in task_metrics:
            target_horizontal_distance = float(task_metrics["target_horizontal_distance_m"])
            has_target_horizontal_distance = bool(np.isfinite(target_horizontal_distance))
        if "bucket_height_above_target_rim_m" in task_metrics:
            bucket_height_above_target_rim = float(
                task_metrics["bucket_height_above_target_rim_m"]
            )
            has_target_height = bool(np.isfinite(bucket_height_above_target_rim))
        if "bucket_over_target_footprint_mask" in task_metrics:
            bucket_over_target_footprint = float(
                task_metrics["bucket_over_target_footprint_mask"]
            )
            has_target_footprint = bool(np.isfinite(bucket_over_target_footprint))
        if "dump_clearance_ok_mask" in task_metrics:
            dump_clearance_ok_mask = float(task_metrics["dump_clearance_ok_mask"])
            has_dump_clearance = bool(np.isfinite(dump_clearance_ok_mask))
        if "bucket_dump_area_relative_x_m" in task_metrics:
            dump_area_relative_x = float(task_metrics["bucket_dump_area_relative_x_m"])
            has_dump_area_relative_x = bool(np.isfinite(dump_area_relative_x))
        if "bucket_dump_area_relative_z_m" in task_metrics:
            dump_area_relative_z = float(task_metrics["bucket_dump_area_relative_z_m"])
            has_dump_area_relative_z = bool(np.isfinite(dump_area_relative_z))
        if "bucket_dump_area_footprint_outside_distance_m" in task_metrics:
            dump_area_outside_distance = float(
                task_metrics["bucket_dump_area_footprint_outside_distance_m"]
            )
            has_dump_area_outside = bool(np.isfinite(dump_area_outside_distance))
        target_geometry_available = bool(
            task_metrics.get(
                "target_geometry_available",
                float(
                    has_target_horizontal_distance
                    and target_horizontal_distance >= 0.0
                    and has_target_height
                    and has_target_footprint
                    and has_dump_clearance
                ),
            )
        )
        dump_area_geometry_available = bool(
            task_metrics.get(
                "dump_area_geometry_available",
                float(
                    has_dump_area_relative_x
                    and has_dump_area_relative_z
                    and has_dump_area_outside
                ),
            )
        )
        dump_clearance_ok = bool(
            target_geometry_available
            and dump_clearance_ok_mask > 0.5
        )
        min_distance_to_dig_area = float(
            task_metrics.get(
                "min_distance_to_dig_area_m",
                _read_env(ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX),
            )
        )
        bucket_depth = float(
            task_metrics.get(
                "bucket_depth_below_dig_area_plane_m",
                _read_env(ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX),
            )
        )
        collision_count = float(
            task_metrics.get(
                "target_hard_collision_count",
                _read_env(ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX),
            )
        )

        def _delta(name: str, current: float) -> float:
            if name in task_metrics:
                return float(task_metrics[name])
            if previous is None:
                return 0.0
            return float(current - previous.get(name.replace("delta_", ""), 0.0))

        return {
            "mass_in_bucket_kg": mass_in_bucket,
            "excavated_mass_kg": excavated_mass,
            "mass_in_target_box_kg": mass_in_target_box,
            "deposited_mass_in_target_box_kg": deposited_mass,
            "min_distance_to_target_m": min_distance_to_target,
            "target_horizontal_distance_m": target_horizontal_distance,
            "bucket_height_above_target_rim_m": bucket_height_above_target_rim,
            "bucket_over_target_footprint_mask": bucket_over_target_footprint,
            "dump_clearance_ok_mask": dump_clearance_ok_mask,
            "bucket_dump_area_relative_x_m": dump_area_relative_x,
            "bucket_dump_area_relative_z_m": dump_area_relative_z,
            "bucket_dump_area_footprint_outside_distance_m": dump_area_outside_distance,
            "target_geometry_available": float(target_geometry_available),
            "dump_area_geometry_available": float(dump_area_geometry_available),
            "dump_clearance_ok": float(dump_clearance_ok),
            "min_distance_to_dig_area_m": min_distance_to_dig_area,
            "bucket_depth_below_dig_area_plane_m": bucket_depth,
            "bucket_contact_dig_area_mask": bucket_contact_dig_area,
            "bucket_contact_dump_area_mask": bucket_contact_dump_area,
            "target_hard_collision_count": collision_count,
            "delta_mass_in_bucket_kg": _delta("delta_mass_in_bucket_kg", mass_in_bucket),
            "delta_excavated_mass_kg": _delta("delta_excavated_mass_kg", excavated_mass),
            "delta_mass_in_target_box_kg": _delta(
                "delta_mass_in_target_box_kg", mass_in_target_box
            ),
            "delta_deposited_mass_in_target_box_kg": _delta(
                "delta_deposited_mass_in_target_box_kg", deposited_mass
            ),
            "deposited_mass_in_dump_area_kg": deposited_mass_in_dump_area,
            "delta_deposited_mass_in_dump_area_kg": _delta(
                "delta_deposited_mass_in_dump_area_kg",
                deposited_mass_in_dump_area,
            ),
            "reward_phase_is_good_dig": float(
                str(reward_phase or "") in {"good_dig_start", "load_progress"}
            ),
            "reward_phase_is_depositing": float(
                str(reward_phase or "") in {"depositing", "retained_success"}
            ),
            "step_success_good_dig": float(
                "good_dig_start" in task_step_successes
            ),
            "step_success_load_progress": float(
                "load_progress" in task_step_successes
            ),
            "success_condition_met": float(task_metrics.get("success_condition_met", 0.0)),
            "success_signal_value": float(task_metrics.get("success_signal_value", deposited_mass)),
            "swing_position_norm": float(qpos[0]) if qpos is not None and len(qpos) > 0 else 0.5,
        }

    def _is_qualified_dig_condition(self, metrics: dict[str, float]) -> bool:
        contact_depth_ready = bool(
            metrics["min_distance_to_dig_area_m"]
            <= self.config.dig_area_touch_tolerance_m
            and metrics["bucket_depth_below_dig_area_plane_m"]
            >= self.config.dig_below_plane_depth_tolerance_m
        )
        if self.config.qualified_dig_start_mode == QUALIFIED_DIG_START_MODE_CONTACT_DEPTH:
            return contact_depth_ready

        raw_load_progress = (
            metrics["delta_mass_in_bucket_kg"] > self.config.delta_mass_start_kg
            or metrics["delta_excavated_mass_kg"] > self.config.delta_mass_start_kg
        )
        good_dig_signal = (
            metrics["reward_phase_is_good_dig"] > 0.0
            or metrics["step_success_good_dig"] > 0.0
            or metrics["step_success_load_progress"] > 0.0
        )
        return bool(
            contact_depth_ready
            and (good_dig_signal or raw_load_progress)
        )

    def _update_dig_complete_state(self, metrics: dict[str, float]) -> bool:
        if self._dig_complete_seen:
            return False
        mass = float(metrics["mass_in_bucket_kg"])
        if mass > self._dig_best_mass_kg + self.config.dig_complete_mass_plateau_epsilon_kg:
            self._dig_best_mass_kg = float(mass)
            self._dig_mass_plateau_count = 0
        else:
            self._dig_best_mass_kg = max(float(self._dig_best_mass_kg), mass)
            self._dig_mass_plateau_count += 1

        departed = bool(
            metrics["min_distance_to_dig_area_m"]
            >= self.config.dig_complete_departed_distance_m
        )
        if departed:
            self._dig_departed_hold_count += 1
        else:
            self._dig_departed_hold_count = 0
        ready = bool(
            self._dig_best_mass_kg >= self.config.dig_complete_min_bucket_mass_kg
            and self._dig_mass_plateau_count
            >= max(1, int(self.config.dig_complete_mass_plateau_hold_steps))
            and self._dig_departed_hold_count
            >= max(1, int(self.config.dig_complete_departed_hold_steps))
        )
        if ready:
            self._dig_complete_seen = True
        return ready

    def _is_dump_committed_condition(self, metrics: dict[str, float]) -> bool:
        if metrics["mass_in_bucket_kg"] < self.config.dump_committed_min_bucket_mass_kg:
            return False
        if metrics["dump_area_geometry_available"] <= 0.0:
            return False
        outside = metrics["bucket_dump_area_footprint_outside_distance_m"]
        relative_x = metrics["bucket_dump_area_relative_x_m"]
        relative_z = metrics["bucket_dump_area_relative_z_m"]
        height = metrics["bucket_height_above_target_rim_m"]
        if not all(np.isfinite(value) for value in (outside, relative_x, relative_z, height)):
            return False
        if outside < 0.0 or outside > self.config.dump_committed_max_outside_distance_m:
            return False
        if (
            relative_x < self.config.dump_committed_min_relative_x_m
            or relative_x > self.config.dump_committed_max_relative_x_m
            or relative_z < self.config.dump_committed_min_relative_z_m
            or relative_z > self.config.dump_committed_max_relative_z_m
        ):
            return False
        if height < self.config.dump_committed_min_height_above_rim_m:
            return False
        if self.config.dump_committed_require_clearance and metrics["dump_clearance_ok"] <= 0.0:
            return False
        return True

    def _is_release_onset_condition(self, metrics: dict[str, float]) -> bool:
        if not self._is_dump_committed_condition(metrics):
            return False
        bucket_drop = -float(metrics["delta_mass_in_bucket_kg"])
        deposit_gain = max(
            float(metrics["delta_deposited_mass_in_target_box_kg"]),
            float(metrics["delta_deposited_mass_in_dump_area_kg"]),
        )
        return bool(
            bucket_drop >= self.config.release_onset_min_bucket_mass_drop_kg
            or deposit_gain >= self.config.release_onset_min_deposit_gain_kg
        )

    def _is_dump_start_condition(self, metrics: dict[str, float]) -> bool:
        cycle_deposit_delta = max(
            metrics["deposited_mass_in_target_box_kg"]
            - self._cycle_start_deposited_mass_kg,
            metrics["mass_in_target_box_kg"] - self._cycle_start_target_mass_kg,
        )
        deposit_progress = (
            metrics["delta_mass_in_target_box_kg"] >= self.config.target_mass_delta_tol_kg
            or metrics["delta_deposited_mass_in_target_box_kg"]
            >= self.config.target_mass_delta_tol_kg
            or cycle_deposit_delta
            >= self.config.dump_start_min_cumulative_deposit_delta_kg
        )
        valid_deposit_context = (
            (
                metrics["target_geometry_available"] > 0.0
                and metrics["target_horizontal_distance_m"]
                <= self.config.target_approach_distance_m
            )
            or metrics["reward_phase_is_depositing"] > 0.0
            or metrics["success_condition_met"] > 0.0
            or metrics["success_signal_value"] >= self.config.target_mass_delta_tol_kg
        )
        return bool(
            deposit_progress and valid_deposit_context
        )
