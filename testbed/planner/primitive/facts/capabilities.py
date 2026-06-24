"""Read-only primitive planner capability facts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
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
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)


@dataclass(frozen=True)
class PrimitiveObservationFacts:
    """Typed read-only facts projected from a primitive planner observation."""

    qpos: np.ndarray
    qvel: np.ndarray
    env_state: np.ndarray
    task_metrics: MappingProxyType[str, Any]
    reward_phase: Any | None
    task_step_successes: Any | None

    @classmethod
    def from_obs(
        cls,
        obs: dict[str, Any],
        *,
        action_dim: int,
    ) -> "PrimitiveObservationFacts":
        return cls(
            qpos=_readonly_array(
                obs.get("qpos", np.zeros(int(action_dim), dtype=np.float32))
            ),
            qvel=_readonly_array(
                obs.get("qvel", np.zeros(int(action_dim), dtype=np.float32))
            ),
            env_state=_readonly_array(
                obs.get("env_state", np.zeros(13, dtype=np.float32))
            ),
            task_metrics=MappingProxyType(dict(obs.get("task_metrics", {}) or {})),
            reward_phase=obs.get("reward_phase"),
            task_step_successes=obs.get("task_step_successes"),
        )

    @property
    def mass_in_bucket_kg(self) -> float:
        if "mass_in_bucket_kg" in self.task_metrics:
            return float(self.task_metrics["mass_in_bucket_kg"])
        return self.env_state_value(ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)

    @property
    def deposited_mass_in_target_box_kg(self) -> float:
        if "deposited_mass_in_target_box_kg" in self.task_metrics:
            return float(self.task_metrics["deposited_mass_in_target_box_kg"])
        return self.env_state_value(
            ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
            default=0.0,
        )

    @property
    def min_distance_to_dig_area_m(self) -> float:
        if "min_distance_to_dig_area_m" in self.task_metrics:
            return float(self.task_metrics["min_distance_to_dig_area_m"])
        return self.env_state_value(ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX, default=0.0)

    @property
    def bucket_depth_below_dig_area_plane_m(self) -> float:
        if "bucket_depth_below_dig_area_plane_m" in self.task_metrics:
            return float(self.task_metrics["bucket_depth_below_dig_area_plane_m"])
        return self.env_state_value(
            ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
            default=0.0,
        )

    def target_geometry(self) -> dict[str, float]:
        available = self.task_metrics.get("target_geometry_available")
        if available is not None and float(available) <= 0.5:
            raise RuntimeError(
                "primitive carry->dump switch requires target_geometry_available=1."
            )

        return {
            "target_horizontal_distance_m": self._metric(
                "target_horizontal_distance_m",
                ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
            ),
            "bucket_height_above_target_rim_m": self._metric(
                "bucket_height_above_target_rim_m",
                ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
            ),
            "bucket_over_target_footprint_mask": self._metric(
                "bucket_over_target_footprint_mask",
                ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
            ),
            "dump_clearance_ok_mask": self._metric(
                "dump_clearance_ok_mask",
                ENV_STATE_DUMP_CLEARANCE_OK_IDX,
            ),
            "bucket_dump_area_relative_x_m": self._optional_metric(
                "bucket_dump_area_relative_x_m",
                ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
            ),
            "bucket_dump_area_relative_z_m": self._optional_metric(
                "bucket_dump_area_relative_z_m",
                ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
            ),
            "bucket_dump_area_footprint_outside_distance_m": self._optional_metric(
                "bucket_dump_area_footprint_outside_distance_m",
                ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
            ),
        }

    def bucket_dig_area_pose(self) -> tuple[float, float, float] | None:
        if len(self.env_state) <= ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX:
            return None
        pose = (
            float(self.env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX]),
            float(self.env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX]),
            float(self.env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX]),
        )
        if not all(np.isfinite(value) for value in pose):
            return None
        return pose

    def bucket_tip_dig_area_pose(self) -> tuple[float, float, float] | None:
        if len(self.env_state) > ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX:
            pose = (
                float(self.env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX]),
                float(self.env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX]),
                float(self.env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX]),
            )
            if all(np.isfinite(value) for value in pose):
                return pose
        return self.bucket_dig_area_pose()

    def env_state_value(self, index: int, *, default: float = float("nan")) -> float:
        if len(self.env_state) <= int(index):
            return float(default)
        return float(self.env_state[int(index)])

    def _metric(self, name: str, index: int) -> float:
        if name in self.task_metrics:
            value = float(self.task_metrics[name])
            if np.isfinite(value):
                return value
        if len(self.env_state) <= int(index):
            raise RuntimeError(
                "primitive carry->dump switch requires Unity target geometry "
                f"field {name!r}; no legacy fallback is used."
            )
        value = float(self.env_state[int(index)])
        if not np.isfinite(value):
            raise RuntimeError(
                "primitive carry->dump switch received non-finite target geometry "
                f"field {name!r}."
            )
        return value

    def _optional_metric(self, name: str, index: int) -> float:
        if name in self.task_metrics:
            value = float(self.task_metrics[name])
            return value if np.isfinite(value) else float("nan")
        return self.env_state_value(index, default=float("nan"))


def _readonly_array(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1).copy()
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class BootstrapStatus:
    """Read-only bootstrap transition facts for the legacy FSM."""

    bootstrap_end_mode: str
    bootstrap_policy_present: bool
    scripted_bootstrap_enabled: bool
    scripted_qpos_close: bool
    scripted_qvel_small: bool
    scripted_next_hold_count: int
    scripted_target_reached: bool
    scripted_timeout_reached: bool
    qualified_dig_start: bool
    mass_in_bucket_kg: float
    min_distance_to_dig_area_m: float
    loaded_and_clear_ready: bool
    should_end: bool

    @classmethod
    def from_inputs(
        cls,
        *,
        observation: PrimitiveObservationFacts,
        boundary_event: Any | None,
        bootstrap_policy_present: bool,
        bootstrap_end_mode: str,
        bootstrap_end_min_bucket_mass_kg: float = 0.0,
        bootstrap_end_min_distance_to_dig_area_m: float = 0.0,
        scripted_bootstrap_target_qpos: Any | None = None,
        scripted_bootstrap_qpos_tolerance: float = 0.0,
        scripted_bootstrap_qvel_abs_max: float = 0.0,
        scripted_bootstrap_hold_count: int = 0,
        scripted_bootstrap_hold_steps: int = 1,
        scripted_bootstrap_step_count: int = 0,
        scripted_bootstrap_max_steps: int = 1,
    ) -> "BootstrapStatus":
        mode = str(bootstrap_end_mode)
        scripted_enabled = bool(
            mode == "scripted_qpos" and scripted_bootstrap_target_qpos is not None
        )
        scripted_qpos_close = False
        scripted_qvel_small = False
        if scripted_enabled:
            target_qpos = np.asarray(
                scripted_bootstrap_target_qpos,
                dtype=np.float32,
            ).reshape(len(observation.qpos))
            scripted_qpos_close = bool(
                np.all(
                    np.abs(observation.qpos - target_qpos)
                    <= float(scripted_bootstrap_qpos_tolerance)
                )
            )
            scripted_qvel_small = bool(
                np.all(np.abs(observation.qvel) <= float(scripted_bootstrap_qvel_abs_max))
            )
        next_hold_count = (
            int(scripted_bootstrap_hold_count) + 1
            if scripted_qpos_close and scripted_qvel_small
            else 0
        )
        hold_steps = max(1, int(scripted_bootstrap_hold_steps))
        max_steps = max(1, int(scripted_bootstrap_max_steps))
        scripted_target_reached = bool(scripted_enabled and next_hold_count >= hold_steps)
        scripted_timeout_reached = bool(
            scripted_enabled and int(scripted_bootstrap_step_count) >= max_steps
        )
        qualified_dig_start = bool(
            boundary_event is not None
            and getattr(boundary_event, "qualified_dig_start", False)
        )
        mass = observation.mass_in_bucket_kg
        min_distance = observation.min_distance_to_dig_area_m
        loaded_and_clear_ready = bool(
            mass >= float(bootstrap_end_min_bucket_mass_kg)
            and min_distance >= float(bootstrap_end_min_distance_to_dig_area_m)
        )

        if scripted_enabled:
            should_end = bool(scripted_target_reached or scripted_timeout_reached)
        elif not bootstrap_policy_present:
            should_end = False
        elif mode == "first_qualified_dig_start":
            should_end = qualified_dig_start
        elif mode == "loaded_and_clear":
            should_end = loaded_and_clear_ready
        elif mode == "disabled":
            should_end = False
        else:
            raise ValueError(f"Unsupported bootstrap_end_mode {mode!r}.")

        return cls(
            bootstrap_end_mode=mode,
            bootstrap_policy_present=bool(bootstrap_policy_present),
            scripted_bootstrap_enabled=scripted_enabled,
            scripted_qpos_close=scripted_qpos_close,
            scripted_qvel_small=scripted_qvel_small,
            scripted_next_hold_count=next_hold_count,
            scripted_target_reached=scripted_target_reached,
            scripted_timeout_reached=scripted_timeout_reached,
            qualified_dig_start=qualified_dig_start,
            mass_in_bucket_kg=mass,
            min_distance_to_dig_area_m=min_distance,
            loaded_and_clear_ready=loaded_and_clear_ready,
            should_end=should_end,
        )


@dataclass(frozen=True)
class DigTransitionStatus:
    """Read-only dig transition facts for the legacy FSM."""

    dig_step_count: int
    mass_in_bucket_kg: float
    min_distance_to_dig_area_m: float
    transition_mass_in_bucket_kg: float
    transition_min_distance_to_dig_area_m: float
    distance_ready: bool
    semantic_boundary_profile_active: bool
    coverage_terminal_stop_requested: bool
    dig_complete_boundary: bool
    dig_complete_boundary_low_payload: bool
    dig_bad_replan_ready: bool
    dig_exit_guard_ready: bool
    dig_mass_plateau_ready: bool
    dig_to_carry_ready: bool
    dig_to_carry_reason: str

    @classmethod
    def from_inputs(
        cls,
        *,
        observation: PrimitiveObservationFacts,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool = False,
        coverage_terminal_stop_requested: bool = False,
        dig_step_count: int = 0,
        dig_mass_plateau_count: int = 0,
        dig_to_carry_min_distance_to_dig_area_m: float = 0.0,
        dig_to_carry_min_bucket_mass_kg: float = 0.0,
        dig_to_carry_target_bucket_mass_kg: float = 0.0,
        dig_to_carry_mass_plateau_enabled: bool = False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg: float = 0.0,
        dig_to_carry_mass_plateau_hold_steps: int = 1,
        dig_to_carry_mass_plateau_min_steps: int = 1,
        dump_ready_min_bucket_mass_kg: float = 0.0,
        dig_bad_replan_enabled: bool = False,
        dig_bad_replan_max_steps: int = 1,
        dig_bad_replan_min_bucket_mass_kg: float = 0.0,
        dig_exit_guard_enabled: bool = False,
        dig_exit_guard_min_steps: int = 1,
        dig_exit_guard_min_bucket_mass_kg: float = 0.0,
        dig_exit_guard_overshoot_m: float = 0.0,
        dig_exit_overshoot_m: float = float("nan"),
    ) -> "DigTransitionStatus":
        step_count = int(dig_step_count)
        mass = observation.mass_in_bucket_kg
        min_distance = observation.min_distance_to_dig_area_m
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        transition_mass = float(metrics.get("mass_in_bucket_kg", mass))
        transition_min_distance = float(
            metrics.get("min_distance_to_dig_area_m", min_distance)
        )
        distance_ready = bool(
            transition_min_distance >= float(dig_to_carry_min_distance_to_dig_area_m)
        )
        terminal_stop = bool(coverage_terminal_stop_requested)
        dig_complete_boundary = bool(
            boundary_event is not None and getattr(boundary_event, "dig_complete", False)
        )
        dig_bad_replan_ready = bool(
            dig_bad_replan_enabled
            and not terminal_stop
            and step_count >= max(1, int(dig_bad_replan_max_steps))
            and mass < float(dig_bad_replan_min_bucket_mass_kg)
        )
        dig_exit_guard_ready = bool(
            dig_exit_guard_enabled
            and not terminal_stop
            and step_count >= max(1, int(dig_exit_guard_min_steps))
            and mass < float(dig_exit_guard_min_bucket_mass_kg)
            and np.isfinite(float(dig_exit_overshoot_m))
            and float(dig_exit_overshoot_m) >= float(dig_exit_guard_overshoot_m)
        )
        low_payload_threshold = max(
            float(dig_to_carry_min_bucket_mass_kg),
            float(dump_ready_min_bucket_mass_kg),
        )
        dig_complete_boundary_low_payload = bool(
            semantic_boundary_profile_active
            and dig_complete_boundary
            and mass < low_payload_threshold
        )
        plateau_ready = bool(
            dig_to_carry_mass_plateau_enabled
            and step_count >= max(1, int(dig_to_carry_mass_plateau_min_steps))
            and transition_mass >= float(dig_to_carry_mass_plateau_min_bucket_mass_kg)
            and int(dig_mass_plateau_count)
            >= max(1, int(dig_to_carry_mass_plateau_hold_steps))
            and distance_ready
        )
        dig_to_carry_ready = False
        dig_to_carry_reason = ""
        if dig_complete_boundary:
            dig_to_carry_ready = True
            dig_to_carry_reason = "dig_complete_boundary"
        elif semantic_boundary_profile_active:
            if transition_mass >= float(dig_to_carry_target_bucket_mass_kg) and distance_ready:
                dig_to_carry_ready = True
                dig_to_carry_reason = "semantic_material_loaded"
            elif plateau_ready:
                dig_to_carry_ready = True
                dig_to_carry_reason = "semantic_material_plateau"
        elif transition_mass >= float(dig_to_carry_target_bucket_mass_kg) and distance_ready:
            dig_to_carry_ready = True
            if (
                abs(
                    float(dig_to_carry_target_bucket_mass_kg)
                    - float(dig_to_carry_min_bucket_mass_kg)
                )
                <= 1.0e-6
            ):
                dig_to_carry_reason = "loaded"
            else:
                dig_to_carry_reason = "target_payload_loaded"
        elif plateau_ready:
            dig_to_carry_ready = True
            dig_to_carry_reason = "mass_plateau"

        return cls(
            dig_step_count=step_count,
            mass_in_bucket_kg=mass,
            min_distance_to_dig_area_m=min_distance,
            transition_mass_in_bucket_kg=transition_mass,
            transition_min_distance_to_dig_area_m=transition_min_distance,
            distance_ready=distance_ready,
            semantic_boundary_profile_active=bool(semantic_boundary_profile_active),
            coverage_terminal_stop_requested=terminal_stop,
            dig_complete_boundary=dig_complete_boundary,
            dig_complete_boundary_low_payload=dig_complete_boundary_low_payload,
            dig_bad_replan_ready=dig_bad_replan_ready,
            dig_exit_guard_ready=dig_exit_guard_ready,
            dig_mass_plateau_ready=plateau_ready,
            dig_to_carry_ready=dig_to_carry_ready,
            dig_to_carry_reason=dig_to_carry_reason,
        )


@dataclass(frozen=True)
class CarryTransitionStatus:
    """Read-only carry transition facts for the legacy FSM."""

    mass_in_bucket_kg: float
    deposited_mass_in_target_box_kg: float
    deposit_delta_since_cycle_start_kg: float
    semantic_boundary_profile_active: bool
    dump_committed_event: bool
    release_onset_event: bool
    dump_complete_event: bool
    legacy_dump_start_event: bool
    carry_release_safety_done: bool
    dump_ready: bool
    next_dump_ready_hold_count: int
    ready_to_dump: bool
    carry_to_dump_reason: str
    carry_to_return_reason: str

    @classmethod
    def from_inputs(
        cls,
        *,
        observation: PrimitiveObservationFacts,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool = False,
        coverage_cycle_start_deposit_kg: float = 0.0,
        dump_ready_hold_count: int = 0,
        dump_ready_hold_steps: int = 1,
        dump_ready_min_bucket_mass_kg: float = 0.0,
        dump_ready_min_height_above_rim_m: float = 0.0,
        dump_ready_require_over_footprint: bool = True,
        dump_ready_require_clearance: bool = True,
        dump_ready_max_horizontal_distance_m: float | None = None,
        dump_ready_position_mode: str = "footprint_or_dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m: float | None = None,
        dump_ready_min_dump_area_relative_x_m: float | None = None,
        dump_ready_max_dump_area_relative_x_m: float | None = None,
        dump_ready_min_dump_area_relative_z_m: float | None = None,
        dump_ready_max_dump_area_relative_z_m: float | None = None,
        dump_ready_near_window_enabled: bool = False,
        dump_ready_near_window_x_tolerance_m: float = 0.0,
        dump_ready_near_window_z_tolerance_m: float = 0.0,
        dump_ready_near_window_outside_tolerance_m: float = 0.0,
        dump_ready_near_window_require_over_footprint: bool = True,
        dump_done_max_bucket_mass_kg: float = 0.0,
        dump_done_min_deposit_delta_kg: float = 0.0,
    ) -> "CarryTransitionStatus":
        semantic = bool(semantic_boundary_profile_active)
        mass = observation.mass_in_bucket_kg
        deposited = observation.deposited_mass_in_target_box_kg
        deposit_delta = deposited - float(coverage_cycle_start_deposit_kg)
        dump_committed_event = bool(
            boundary_event is not None
            and getattr(boundary_event, "dump_committed_start", False)
        )
        release_onset_event = bool(
            boundary_event is not None and getattr(boundary_event, "release_onset", False)
        )
        dump_complete_event = bool(
            boundary_event is not None and getattr(boundary_event, "dump_complete", False)
        )
        legacy_dump_start_event = bool(
            boundary_event is not None
            and getattr(boundary_event, "dump_start", False)
            and not semantic
        )
        carry_release_safety_done = bool(
            semantic
            and mass <= float(dump_done_max_bucket_mass_kg)
            and deposit_delta >= float(dump_done_min_deposit_delta_kg)
        )
        dump_ready = False
        if (
            not semantic
            and not dump_committed_event
            and not release_onset_event
            and not legacy_dump_start_event
        ):
            dump_ready = _dump_ready_from_observation(
                observation=observation,
                dump_ready_min_bucket_mass_kg=dump_ready_min_bucket_mass_kg,
                dump_ready_min_height_above_rim_m=dump_ready_min_height_above_rim_m,
                dump_ready_require_over_footprint=dump_ready_require_over_footprint,
                dump_ready_require_clearance=dump_ready_require_clearance,
                dump_ready_max_horizontal_distance_m=(
                    dump_ready_max_horizontal_distance_m
                ),
                dump_ready_position_mode=dump_ready_position_mode,
                dump_ready_max_dump_area_footprint_outside_distance_m=(
                    dump_ready_max_dump_area_footprint_outside_distance_m
                ),
                dump_ready_min_dump_area_relative_x_m=(
                    dump_ready_min_dump_area_relative_x_m
                ),
                dump_ready_max_dump_area_relative_x_m=(
                    dump_ready_max_dump_area_relative_x_m
                ),
                dump_ready_min_dump_area_relative_z_m=(
                    dump_ready_min_dump_area_relative_z_m
                ),
                dump_ready_max_dump_area_relative_z_m=(
                    dump_ready_max_dump_area_relative_z_m
                ),
                dump_ready_near_window_enabled=dump_ready_near_window_enabled,
                dump_ready_near_window_x_tolerance_m=(
                    dump_ready_near_window_x_tolerance_m
                ),
                dump_ready_near_window_z_tolerance_m=(
                    dump_ready_near_window_z_tolerance_m
                ),
                dump_ready_near_window_outside_tolerance_m=(
                    dump_ready_near_window_outside_tolerance_m
                ),
                dump_ready_near_window_require_over_footprint=(
                    dump_ready_near_window_require_over_footprint
                ),
            )
        hold_steps = max(1, int(dump_ready_hold_steps))
        if dump_committed_event or release_onset_event or legacy_dump_start_event:
            next_hold_count = hold_steps
        elif not semantic and dump_ready:
            next_hold_count = int(dump_ready_hold_count) + 1
        else:
            next_hold_count = 0
        ready_to_dump = bool(next_hold_count >= hold_steps)
        if not ready_to_dump:
            carry_to_dump_reason = ""
        elif dump_committed_event:
            carry_to_dump_reason = "dump_committed_boundary"
        elif release_onset_event:
            carry_to_dump_reason = "release_onset_boundary"
        elif legacy_dump_start_event:
            carry_to_dump_reason = "dump_start_boundary"
        else:
            carry_to_dump_reason = "target_ready"

        carry_to_return_reason = ""
        if carry_release_safety_done:
            carry_to_return_reason = "carry_to_return_release_safety"
        elif dump_complete_event:
            carry_to_return_reason = "carry_to_return_dump_complete_boundary"

        return cls(
            mass_in_bucket_kg=mass,
            deposited_mass_in_target_box_kg=deposited,
            deposit_delta_since_cycle_start_kg=deposit_delta,
            semantic_boundary_profile_active=semantic,
            dump_committed_event=dump_committed_event,
            release_onset_event=release_onset_event,
            dump_complete_event=dump_complete_event,
            legacy_dump_start_event=legacy_dump_start_event,
            carry_release_safety_done=carry_release_safety_done,
            dump_ready=dump_ready,
            next_dump_ready_hold_count=next_hold_count,
            ready_to_dump=ready_to_dump,
            carry_to_dump_reason=carry_to_dump_reason,
            carry_to_return_reason=carry_to_return_reason,
        )


@dataclass(frozen=True)
class DumpTransitionStatus:
    """Read-only dump transition facts for the legacy FSM."""

    mass_in_bucket_kg: float
    deposited_mass_in_target_box_kg: float
    deposit_delta_since_dump_start_kg: float
    semantic_boundary_profile_active: bool
    dump_complete_event: bool
    legacy_dump_end_event: bool
    boundary_dump_done: bool
    dump_done_mass_low: bool
    next_dump_done_hold_count: int
    ready_to_return: bool
    coverage_completion_reason: str
    dump_to_return_reason: str

    @classmethod
    def from_inputs(
        cls,
        *,
        observation: PrimitiveObservationFacts,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool = False,
        dump_done_use_boundary_event: bool = True,
        dump_start_deposited_mass_kg: float = 0.0,
        dump_done_hold_count: int = 0,
        dump_done_hold_steps: int = 1,
        dump_done_max_bucket_mass_kg: float = 0.0,
        dump_done_min_deposit_delta_kg: float = 0.0,
    ) -> "DumpTransitionStatus":
        semantic = bool(semantic_boundary_profile_active)
        mass = observation.mass_in_bucket_kg
        deposited = observation.deposited_mass_in_target_box_kg
        deposit_delta = deposited - float(dump_start_deposited_mass_kg)
        dump_complete_event = bool(
            boundary_event is not None and getattr(boundary_event, "dump_complete", False)
        )
        legacy_dump_end_event = bool(
            boundary_event is not None
            and getattr(boundary_event, "dump_end", False)
            and not semantic
        )
        boundary_dump_done = bool(
            dump_done_use_boundary_event
            and (dump_complete_event or legacy_dump_end_event)
        )
        dump_done_mass_low = bool(
            not semantic
            and mass <= float(dump_done_max_bucket_mass_kg)
            and deposit_delta >= float(dump_done_min_deposit_delta_kg)
        )
        hold_steps = max(1, int(dump_done_hold_steps))
        if boundary_dump_done:
            next_hold_count = int(dump_done_hold_count)
        elif dump_done_mass_low:
            next_hold_count = int(dump_done_hold_count) + 1
        else:
            next_hold_count = 0
        mass_low_ready = bool(not boundary_dump_done and next_hold_count >= hold_steps)
        ready_to_return = bool(boundary_dump_done or mass_low_ready)

        coverage_completion_reason = ""
        dump_to_return_reason = ""
        if boundary_dump_done:
            if dump_complete_event:
                coverage_completion_reason = "dump_complete_boundary"
                dump_to_return_reason = "dump_to_return_dump_complete_boundary"
            else:
                coverage_completion_reason = "dump_end_boundary"
                dump_to_return_reason = "dump_to_return_dump_end"
        elif mass_low_ready:
            coverage_completion_reason = "dump_mass_low"
            dump_to_return_reason = "dump_to_return_mass_low"

        return cls(
            mass_in_bucket_kg=mass,
            deposited_mass_in_target_box_kg=deposited,
            deposit_delta_since_dump_start_kg=deposit_delta,
            semantic_boundary_profile_active=semantic,
            dump_complete_event=dump_complete_event,
            legacy_dump_end_event=legacy_dump_end_event,
            boundary_dump_done=boundary_dump_done,
            dump_done_mass_low=dump_done_mass_low,
            next_dump_done_hold_count=next_hold_count,
            ready_to_return=ready_to_return,
            coverage_completion_reason=coverage_completion_reason,
            dump_to_return_reason=dump_to_return_reason,
        )


@dataclass(frozen=True)
class ReturnTransitionStatus:
    """Read-only return transition facts for the legacy FSM."""

    mass_in_bucket_kg: float
    min_distance_to_dig_area_m: float
    bucket_depth_below_dig_area_plane_m: float
    semantic_boundary_profile_active: bool
    next_dig_event: bool
    next_or_seen_dig_event: bool
    entry_close: bool
    start_envelope_ready: bool
    handoff_ready: bool
    direct_handoff_ready: bool
    shallow_guard_ready: bool
    shallow_guard_allowed: bool
    completed_transition: bool
    next_skill: str
    switch_reason: str

    @classmethod
    def from_inputs(
        cls,
        *,
        observation: PrimitiveObservationFacts,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool = False,
        return_next_dig_event_seen: bool = False,
        entry_close: bool = False,
        start_envelope_ready: bool = False,
        return_to_dig_start_envelope_direct_handoff_enabled: bool = False,
        return_to_dig_start_envelope_gate_enabled: bool = False,
        return_to_dig_shallow_guard_enabled: bool = False,
        return_to_dig_max_bucket_mass_kg: float = 0.0,
        return_to_dig_touch_tolerance_m: float = 0.0,
        return_to_dig_min_depth_m: float = 0.0,
        return_to_dig_max_depth_m: float = 0.0,
        return_to_dig_max_entry_error_m: float | None = None,
    ) -> "ReturnTransitionStatus":
        semantic = bool(semantic_boundary_profile_active)
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        mass = float(metrics.get("mass_in_bucket_kg", observation.mass_in_bucket_kg))
        distance = float(
            metrics.get(
                "min_distance_to_dig_area_m",
                observation.min_distance_to_dig_area_m,
            )
        )
        depth = float(
            metrics.get(
                "bucket_depth_below_dig_area_plane_m",
                observation.bucket_depth_below_dig_area_plane_m,
            )
        )
        next_dig_event = bool(
            boundary_event is not None
            and (
                getattr(boundary_event, "next_dig_entry_ready", False)
                or getattr(boundary_event, "qualified_dig_start", False)
            )
        )
        next_or_seen = bool(next_dig_event or return_next_dig_event_seen)
        handoff_ready = bool(entry_close and start_envelope_ready)
        direct_handoff_ready = bool(
            return_to_dig_start_envelope_direct_handoff_enabled
            and return_to_dig_start_envelope_gate_enabled
            and handoff_ready
            and mass <= float(return_to_dig_max_bucket_mass_kg)
        )
        entry_guard_ready = bool(
            return_to_dig_max_entry_error_m is not None and bool(entry_close)
        )
        depth_below_max = bool(depth <= float(return_to_dig_max_depth_m))
        shallow_guard_ready = bool(
            return_to_dig_shallow_guard_enabled
            and mass <= float(return_to_dig_max_bucket_mass_kg)
            and distance <= float(return_to_dig_touch_tolerance_m)
            and depth >= float(return_to_dig_min_depth_m)
            and (depth_below_max or entry_guard_ready)
        )
        shallow_guard_allowed = bool(not semantic and shallow_guard_ready and handoff_ready)
        next_skill = "dig"
        reason_suffix = ""
        if next_or_seen and handoff_ready:
            reason_suffix = "next_dig_entry_ready"
        elif direct_handoff_ready:
            reason_suffix = "start_envelope_ready"
        elif shallow_guard_allowed:
            reason_suffix = "shallow_entry_guard"
        completed = bool(reason_suffix)
        switch_reason = (
            f"return_to_{next_skill}_{reason_suffix}" if completed else ""
        )

        return cls(
            mass_in_bucket_kg=mass,
            min_distance_to_dig_area_m=distance,
            bucket_depth_below_dig_area_plane_m=depth,
            semantic_boundary_profile_active=semantic,
            next_dig_event=next_dig_event,
            next_or_seen_dig_event=next_or_seen,
            entry_close=bool(entry_close),
            start_envelope_ready=bool(start_envelope_ready),
            handoff_ready=handoff_ready,
            direct_handoff_ready=direct_handoff_ready,
            shallow_guard_ready=shallow_guard_ready,
            shallow_guard_allowed=shallow_guard_allowed,
            completed_transition=completed,
            next_skill=next_skill if completed else "",
            switch_reason=switch_reason,
        )


def _dump_ready_from_observation(
    *,
    observation: PrimitiveObservationFacts,
    dump_ready_min_bucket_mass_kg: float,
    dump_ready_min_height_above_rim_m: float,
    dump_ready_require_over_footprint: bool,
    dump_ready_require_clearance: bool,
    dump_ready_max_horizontal_distance_m: float | None,
    dump_ready_position_mode: str,
    dump_ready_max_dump_area_footprint_outside_distance_m: float | None,
    dump_ready_min_dump_area_relative_x_m: float | None,
    dump_ready_max_dump_area_relative_x_m: float | None,
    dump_ready_min_dump_area_relative_z_m: float | None,
    dump_ready_max_dump_area_relative_z_m: float | None,
    dump_ready_near_window_enabled: bool,
    dump_ready_near_window_x_tolerance_m: float,
    dump_ready_near_window_z_tolerance_m: float,
    dump_ready_near_window_outside_tolerance_m: float,
    dump_ready_near_window_require_over_footprint: bool,
) -> bool:
    if observation.mass_in_bucket_kg < float(dump_ready_min_bucket_mass_kg):
        return False
    geometry = observation.target_geometry()
    over_footprint = geometry["bucket_over_target_footprint_mask"] > 0.5
    height_ok = bool(
        geometry["bucket_height_above_target_rim_m"]
        >= float(dump_ready_min_height_above_rim_m) - 1.0e-6
    )
    clearance_ok = geometry["dump_clearance_ok_mask"] > 0.5
    horizontal_ok = False
    if dump_ready_max_horizontal_distance_m is not None:
        horizontal_ok = bool(
            geometry["target_horizontal_distance_m"]
            <= float(dump_ready_max_horizontal_distance_m) + 1.0e-6
        )
    dump_area_relative_ok = _dump_area_relative_position_ok(
        geometry=geometry,
        max_outside_distance=dump_ready_max_dump_area_footprint_outside_distance_m,
        min_x=dump_ready_min_dump_area_relative_x_m,
        max_x=dump_ready_max_dump_area_relative_x_m,
        min_z=dump_ready_min_dump_area_relative_z_m,
        max_z=dump_ready_max_dump_area_relative_z_m,
    )
    position_ok = _dump_ready_position_ok(
        mode=dump_ready_position_mode,
        over_footprint=over_footprint,
        dump_area_relative_ok=dump_area_relative_ok,
        horizontal_ok=horizontal_ok,
        require_over_footprint=bool(dump_ready_require_over_footprint),
    )
    if not position_ok:
        position_ok = _dump_area_relative_near_window_ok(
            geometry=geometry,
            over_footprint=over_footprint,
            enabled=dump_ready_near_window_enabled,
            require_over_footprint=dump_ready_near_window_require_over_footprint,
            max_outside_distance=dump_ready_max_dump_area_footprint_outside_distance_m,
            outside_tolerance=dump_ready_near_window_outside_tolerance_m,
            min_x=dump_ready_min_dump_area_relative_x_m,
            max_x=dump_ready_max_dump_area_relative_x_m,
            x_tolerance=dump_ready_near_window_x_tolerance_m,
            min_z=dump_ready_min_dump_area_relative_z_m,
            max_z=dump_ready_max_dump_area_relative_z_m,
            z_tolerance=dump_ready_near_window_z_tolerance_m,
        )
    return bool(
        height_ok
        and position_ok
        and (clearance_ok or not bool(dump_ready_require_clearance))
    )


def _dump_area_relative_position_ok(
    *,
    geometry: dict[str, float],
    max_outside_distance: float | None,
    min_x: float | None,
    max_x: float | None,
    min_z: float | None,
    max_z: float | None,
) -> bool:
    if max_outside_distance is None:
        return False
    outside_distance = float(
        geometry.get("bucket_dump_area_footprint_outside_distance_m", np.nan)
    )
    outside_ok = bool(
        np.isfinite(outside_distance)
        and outside_distance >= 0.0
        and outside_distance <= float(max_outside_distance) + 1.0e-6
    )
    if not outside_ok:
        return False
    return bool(
        _optional_range_ok(
            value=float(geometry.get("bucket_dump_area_relative_x_m", np.nan)),
            min_value=min_x,
            max_value=max_x,
        )
        and _optional_range_ok(
            value=float(geometry.get("bucket_dump_area_relative_z_m", np.nan)),
            min_value=min_z,
            max_value=max_z,
        )
    )


def _dump_area_relative_near_window_ok(
    *,
    geometry: dict[str, float],
    over_footprint: bool,
    enabled: bool,
    require_over_footprint: bool,
    max_outside_distance: float | None,
    outside_tolerance: float,
    min_x: float | None,
    max_x: float | None,
    x_tolerance: float,
    min_z: float | None,
    max_z: float | None,
    z_tolerance: float,
) -> bool:
    if not enabled:
        return False
    if require_over_footprint and not over_footprint:
        return False
    if max_outside_distance is None:
        return False
    outside_distance = float(
        geometry.get("bucket_dump_area_footprint_outside_distance_m", np.nan)
    )
    outside_limit = float(max_outside_distance) + float(outside_tolerance)
    outside_ok = bool(
        np.isfinite(outside_distance)
        and outside_distance >= 0.0
        and outside_distance <= outside_limit + 1.0e-6
    )
    if not outside_ok:
        return False
    return bool(
        _optional_range_near_ok(
            value=float(geometry.get("bucket_dump_area_relative_x_m", np.nan)),
            min_value=min_x,
            max_value=max_x,
            tolerance=x_tolerance,
        )
        and _optional_range_near_ok(
            value=float(geometry.get("bucket_dump_area_relative_z_m", np.nan)),
            min_value=min_z,
            max_value=max_z,
            tolerance=z_tolerance,
        )
    )


def _dump_ready_position_ok(
    *,
    mode: str,
    over_footprint: bool,
    dump_area_relative_ok: bool,
    horizontal_ok: bool,
    require_over_footprint: bool,
) -> bool:
    if mode == "footprint_or_dump_area_relative":
        return bool(dump_area_relative_ok or (over_footprint and require_over_footprint))
    if mode == "dump_area_relative":
        return bool(dump_area_relative_ok)
    if mode == "footprint":
        return bool(over_footprint or not require_over_footprint)
    if mode == "footprint_or_horizontal":
        return bool(horizontal_ok or (over_footprint and require_over_footprint))
    raise ValueError(
        f"Unsupported dump_ready_position_mode {mode!r}. Expected one of "
        "footprint_or_dump_area_relative, dump_area_relative, footprint, "
        "footprint_or_horizontal."
    )


def _optional_range_ok(
    *,
    value: float,
    min_value: float | None,
    max_value: float | None,
) -> bool:
    if min_value is None and max_value is None:
        return True
    if not np.isfinite(value):
        return False
    if min_value is not None and value < float(min_value) - 1.0e-6:
        return False
    if max_value is not None and value > float(max_value) + 1.0e-6:
        return False
    return True


def _optional_range_near_ok(
    *,
    value: float,
    min_value: float | None,
    max_value: float | None,
    tolerance: float,
) -> bool:
    if min_value is None and max_value is None:
        return True
    if not np.isfinite(value):
        return False
    tol = max(0.0, float(tolerance))
    if min_value is not None and value < float(min_value) - tol - 1.0e-6:
        return False
    if max_value is not None and value > float(max_value) + tol + 1.0e-6:
        return False
    return True


__all__ = [
    "BootstrapStatus",
    "CarryTransitionStatus",
    "DigTransitionStatus",
    "DumpTransitionStatus",
    "PrimitiveObservationFacts",
    "ReturnTransitionStatus",
]
