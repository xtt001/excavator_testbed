"""
Pure excavator phase-reward logic — no physics, no dm_control imports.

This module tracks the multi-stage excavation cycle and returns the
appropriate scalar reward. It is intentionally backend-agnostic so it
can be reused by:
  - MuJoCo task classes (called from get_reward)
  - Evaluator overlays (phase annotation without re-running physics)
  - Future Isaac / AGX backends

Reward table
------------
| Value | Condition                                     | Phase label     |
|-------|-----------------------------------------------|-----------------|
|  0.0  | default                                       | idle            |
|  1.0  | bucket touches target                         | contact         |
|  1.2  | touched but not yet loaded (anti-push reward) | contact_only    |
|  2.0  | loaded and box_z > LOAD_HEIGHT_THRESHOLD      | loaded          |
|  2.8  | loaded + |swing| > DUMP_SWING_THRESHOLD      | swinging        |
|  3.0  | in dump zone + bucket touches tray            | dump_approach   |
|  4.0  | box on tray, bucket clear, box_z < DUMP_Z_MAX | dump_complete   |
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable

import numpy as np


# ─── Thresholds ───────────────────────────────────────────────────────────────

LOAD_HEIGHT_THRESHOLD: float = 0.285   # m — box must be above this to count as loaded
DUMP_SWING_THRESHOLD: float = 1.0      # rad — |swing| must exceed this for dump zone
DUMP_Z_MAX: float = 0.35               # m — box must be below this after dump

# Geom names (must match MJCF)
BUCKET_GEOM = "excavator_bucket"
BOX_GEOM = "red_box"
TRAY_GEOM = "yellow_dump_tray"


# ─── Phase label (for overlays) ───────────────────────────────────────────────

PHASE_LABELS: dict[float, str] = {
    0.0: "idle",
    1.0: "contact",
    1.2: "contact_only",
    2.0: "loaded",
    2.8: "swinging",
    3.0: "dump_approach",
    4.0: "dump_complete",
}


@dataclass
class ExcavatorPhaseTracker:
    """
    Stateful phase tracker for one episode.

    Call reset() at the start of each episode, then update() each timestep.
    """

    _touched_box: bool = field(default=False, init=False)
    _loaded_box: bool = field(default=False, init=False)
    _reached_dump_zone: bool = field(default=False, init=False)
    _dumped_box: bool = field(default=False, init=False)

    def reset(self) -> None:
        self._touched_box = False
        self._loaded_box = False
        self._reached_dump_zone = False
        self._dumped_box = False

    @property
    def current_phase(self) -> str:
        """Human-readable label of the highest phase reached so far."""
        if self._dumped_box:
            return "dump_complete"
        if self._reached_dump_zone:
            return "swinging"
        if self._loaded_box:
            return "loaded"
        if self._touched_box:
            return "contact"
        return "idle"

    def update(
        self,
        contact_pairs: set[tuple[str, str]],
        box_xyz: np.ndarray,
        swing_q: float,
    ) -> float:
        """
        Advance state machine and return current reward.

        Parameters
        ----------
        contact_pairs:
            Set of (geom_a, geom_b) contact tuples for this timestep.
            Must include both orderings, i.e. (a,b) and (b,a).
        box_xyz:
            World-frame position of the box [x, y, z].
        swing_q:
            Current j1_swing joint angle in radians.
        """
        box_z = float(box_xyz[2])

        touch_bucket_box = (BUCKET_GEOM, BOX_GEOM) in contact_pairs
        touch_box_tray = (BOX_GEOM, TRAY_GEOM) in contact_pairs
        touch_bucket_tray = (BUCKET_GEOM, TRAY_GEOM) in contact_pairs

        reward = 0.0

        # Stage 1: Contact
        if touch_bucket_box:
            self._touched_box = True
            reward = max(reward, 1.0)

        # Stage 2: Loaded (box lifted)
        if self._touched_box and box_z > LOAD_HEIGHT_THRESHOLD:
            self._loaded_box = True
            reward = max(reward, 2.0)

        # Stage 3: Swinging to dump zone
        if self._loaded_box and abs(swing_q) > DUMP_SWING_THRESHOLD:
            self._reached_dump_zone = True
            reward = max(reward, 2.8)

        # Stage 4: Dump approach (bucket at tray)
        if self._reached_dump_zone and touch_bucket_tray:
            reward = max(reward, 3.0)

        # Stage 5: Dump complete (box on tray, bucket clear)
        if (
            self._reached_dump_zone
            and touch_box_tray
            and not touch_bucket_box
            and box_z < DUMP_Z_MAX
        ):
            self._dumped_box = True
            reward = max(reward, 4.0)

        # Anti-push: touched but not yet loaded
        if self._touched_box and not self._loaded_box:
            reward = max(reward, 1.2)

        return reward

    def phase_label(self, reward: float) -> str:
        return PHASE_LABELS.get(reward, f"reward_{reward:.1f}")


# ─── AGX excavation mission reward ───────────────────────────────────────────

AGX_MASS_IN_BUCKET = "mass_in_bucket_kg"
AGX_EXCAVATED_MASS = "excavated_mass_kg"
AGX_MASS_IN_TARGET_BOX = "mass_in_target_box_kg"
AGX_DEPOSITED_MASS_IN_TARGET_BOX = "deposited_mass_in_target_box_kg"
AGX_MIN_DISTANCE_TO_TARGET = "min_distance_to_target_m"
AGX_TARGET_HARD_COLLISION_COUNT = "target_hard_collision_count"
AGX_TARGET_CONTACT_MAX_NORMAL_FORCE_N = "target_contact_max_normal_force_n"
AGX_MIN_DISTANCE_TO_DIG_AREA = "min_distance_to_dig_area_m"
AGX_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE = "bucket_depth_below_dig_area_plane_m"

AGX_PHASE_LABELS: dict[float, str] = {
    0.0: "idle",
    1.0: "loading",
    2.0: "approaching_target",
    3.0: "depositing",
    4.0: "retained_success",
}


@dataclass(frozen=True)
class AgxExcavationMissionConfig:
    """
    Task-level mission definition for the Unity AGX excavation scene.

    The mission remains one continuous dig-dump-retain objective. Reward shaping
    is attached to observable sub-targets, but success is defined only by the
    retained mass signal inside the currently active target.
    """

    name: str
    success_mode: str = "final_hold"
    success_signal_name: str = AGX_DEPOSITED_MASS_IN_TARGET_BOX
    success_mass_thresh: float = 100.0
    success_hold_steps: int = 25
    residual_bucket_mass_thresh: float = 100.0
    load_mass_threshold_kg: float = 100.0
    target_approach_distance_m: float = 1.25
    deposit_started_threshold_kg: float = 10.0
    unsafe_distance_m: float = 0.20
    unsafe_distance_penalty: float = 0.25
    hard_collision_penalty: float = 0.75
    spill_penalty: float = 0.25
    bucket_mass_delta_tol_kg: float = 5.0
    target_mass_delta_tol_kg: float = 2.0
    distance_progress_delta_m: float = 0.02
    dig_area_touch_tolerance_m: float = 0.05
    dig_below_plane_depth_tolerance_m: float = 0.02
    max_reward: float = 4.0


@dataclass(frozen=True)
class AgxExcavationFieldIndices:
    mass_in_bucket_idx: int | None = None
    excavated_mass_idx: int | None = None
    mass_in_target_box_idx: int | None = None
    deposited_mass_in_target_box_idx: int | None = None
    min_distance_to_target_idx: int | None = None
    target_hard_collision_count_idx: int | None = None
    target_contact_max_normal_force_n_idx: int | None = None
    min_distance_to_dig_area_idx: int | None = None
    bucket_depth_below_dig_area_plane_idx: int | None = None


@dataclass(frozen=True)
class AgxExcavationObservation:
    mass_in_bucket_kg: float = 0.0
    excavated_mass_kg: float = 0.0
    mass_in_target_box_kg: float = 0.0
    deposited_mass_in_target_box_kg: float = 0.0
    min_distance_to_target_m: float = -1.0
    target_hard_collision_count: float = 0.0
    target_contact_max_normal_force_n: float = 0.0
    min_distance_to_dig_area_m: float = -1.0
    bucket_depth_below_dig_area_plane_m: float = 0.0

    def value_for(self, signal_name: str) -> float:
        if signal_name == AGX_MASS_IN_BUCKET:
            return self.mass_in_bucket_kg
        if signal_name == AGX_EXCAVATED_MASS:
            return self.excavated_mass_kg
        if signal_name == AGX_MASS_IN_TARGET_BOX:
            return self.mass_in_target_box_kg
        if signal_name == AGX_DEPOSITED_MASS_IN_TARGET_BOX:
            return self.deposited_mass_in_target_box_kg
        if signal_name == AGX_MIN_DISTANCE_TO_TARGET:
            return self.min_distance_to_target_m
        if signal_name == AGX_TARGET_HARD_COLLISION_COUNT:
            return self.target_hard_collision_count
        if signal_name == AGX_TARGET_CONTACT_MAX_NORMAL_FORCE_N:
            return self.target_contact_max_normal_force_n
        if signal_name == AGX_MIN_DISTANCE_TO_DIG_AREA:
            return self.min_distance_to_dig_area_m
        if signal_name == AGX_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE:
            return self.bucket_depth_below_dig_area_plane_m
        return 0.0


@dataclass
class AgxExcavationStepResult:
    reward: float
    phase_label: str
    success: bool
    step_successes: tuple[str, ...] = ()
    step_failures: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)


AGX_EXCAVATION_MISSIONS: dict[str, AgxExcavationMissionConfig] = {
    "agx_excavation_teleop": AgxExcavationMissionConfig(
        name="agx_excavation_teleop",
        success_signal_name=AGX_DEPOSITED_MASS_IN_TARGET_BOX,
        success_mass_thresh=100.0,
        success_hold_steps=25,
        load_mass_threshold_kg=100.0,
        target_approach_distance_m=1.25,
        deposit_started_threshold_kg=10.0,
        unsafe_distance_m=0.20,
        unsafe_distance_penalty=0.25,
        hard_collision_penalty=0.75,
        spill_penalty=0.25,
        bucket_mass_delta_tol_kg=5.0,
        target_mass_delta_tol_kg=2.0,
        distance_progress_delta_m=0.02,
        max_reward=4.0,
    ),
}


def get_agx_excavation_mission(
    name: str,
    **overrides: Any,
) -> AgxExcavationMissionConfig:
    if name not in AGX_EXCAVATION_MISSIONS:
        raise KeyError(
            f"Unknown AGX excavation mission {name!r}. "
            f"Available: {list(AGX_EXCAVATION_MISSIONS.keys())}"
        )

    mission = AGX_EXCAVATION_MISSIONS[name]
    if not overrides:
        return mission

    valid_fields = set(mission.__dataclass_fields__)
    unknown = sorted(set(overrides) - valid_fields)
    if unknown:
        raise KeyError(
            f"Unknown AGX excavation mission overrides {unknown!r}. "
            f"Valid keys: {sorted(valid_fields)!r}"
        )

    clean_overrides = {key: value for key, value in overrides.items() if value is not None}
    return replace(mission, **clean_overrides) if clean_overrides else mission


def build_agx_excavation_mission_overrides(
    success_cfg: dict[str, Any] | None = None,
    reward_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Merge YAML-style success/reward config sections into mission override kwargs.

    The return value is safe to pass into get_agx_excavation_mission(..., **overrides).
    """

    success_cfg = dict(success_cfg or {})
    reward_cfg = dict(reward_cfg or {})
    overrides: dict[str, Any] = {}

    if "mode" in success_cfg:
        overrides["success_mode"] = str(success_cfg["mode"])
    if "success_mode" in success_cfg:
        overrides["success_mode"] = str(success_cfg["success_mode"])
    if "signal_name" in success_cfg:
        overrides["success_signal_name"] = str(success_cfg["signal_name"])
    if "success_signal_name" in success_cfg:
        overrides["success_signal_name"] = str(success_cfg["success_signal_name"])
    if "mass_thresh" in success_cfg:
        overrides["success_mass_thresh"] = float(success_cfg["mass_thresh"])
    if "mass_thresh_kg" in success_cfg:
        overrides["success_mass_thresh"] = float(success_cfg["mass_thresh_kg"])
    if "success_mass_thresh" in success_cfg:
        overrides["success_mass_thresh"] = float(success_cfg["success_mass_thresh"])
    if "hold_steps" in success_cfg:
        overrides["success_hold_steps"] = int(success_cfg["hold_steps"])
    if "success_hold_steps" in success_cfg:
        overrides["success_hold_steps"] = int(success_cfg["success_hold_steps"])
    if "residual_bucket_mass_thresh" in success_cfg:
        overrides["residual_bucket_mass_thresh"] = float(
            success_cfg["residual_bucket_mass_thresh"]
        )
    if "bucket_residual_mass_thresh" in success_cfg:
        overrides["residual_bucket_mass_thresh"] = float(
            success_cfg["bucket_residual_mass_thresh"]
        )

    for key in (
        "load_mass_threshold_kg",
        "target_approach_distance_m",
        "deposit_started_threshold_kg",
        "unsafe_distance_m",
        "unsafe_distance_penalty",
        "hard_collision_penalty",
        "spill_penalty",
        "bucket_mass_delta_tol_kg",
        "target_mass_delta_tol_kg",
        "distance_progress_delta_m",
        "dig_area_touch_tolerance_m",
        "dig_below_plane_depth_tolerance_m",
    ):
        if key not in reward_cfg:
            continue
        value = reward_cfg[key]
        overrides[key] = float(value)

    return overrides


def resolve_agx_field_indices(env_state_order: Iterable[str]) -> AgxExcavationFieldIndices:
    env_state_order = tuple(env_state_order)

    def _lookup(signal_name: str) -> int | None:
        return env_state_order.index(signal_name) if signal_name in env_state_order else None

    return AgxExcavationFieldIndices(
        mass_in_bucket_idx=_lookup(AGX_MASS_IN_BUCKET),
        excavated_mass_idx=_lookup(AGX_EXCAVATED_MASS),
        mass_in_target_box_idx=_lookup(AGX_MASS_IN_TARGET_BOX),
        deposited_mass_in_target_box_idx=_lookup(AGX_DEPOSITED_MASS_IN_TARGET_BOX),
        min_distance_to_target_idx=_lookup(AGX_MIN_DISTANCE_TO_TARGET),
        target_hard_collision_count_idx=_lookup(AGX_TARGET_HARD_COLLISION_COUNT),
        target_contact_max_normal_force_n_idx=_lookup(AGX_TARGET_CONTACT_MAX_NORMAL_FORCE_N),
        min_distance_to_dig_area_idx=_lookup(AGX_MIN_DISTANCE_TO_DIG_AREA),
        bucket_depth_below_dig_area_plane_idx=_lookup(AGX_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE),
    )


def decode_agx_env_state(
    env_state: np.ndarray | Iterable[float],
    field_indices: AgxExcavationFieldIndices,
) -> AgxExcavationObservation:
    env_state = np.asarray(env_state, dtype=np.float32).reshape(-1)

    def _read(index: int | None, default: float) -> float:
        if index is None or index < 0 or index >= len(env_state):
            return default
        return float(env_state[index])

    return AgxExcavationObservation(
        mass_in_bucket_kg=max(0.0, _read(field_indices.mass_in_bucket_idx, 0.0)),
        excavated_mass_kg=max(0.0, _read(field_indices.excavated_mass_idx, 0.0)),
        mass_in_target_box_kg=max(0.0, _read(field_indices.mass_in_target_box_idx, 0.0)),
        deposited_mass_in_target_box_kg=max(
            0.0,
            _read(field_indices.deposited_mass_in_target_box_idx, 0.0),
        ),
        min_distance_to_target_m=_read(field_indices.min_distance_to_target_idx, -1.0),
        target_hard_collision_count=max(
            0.0,
            _read(field_indices.target_hard_collision_count_idx, 0.0),
        ),
        target_contact_max_normal_force_n=max(
            0.0,
            _read(field_indices.target_contact_max_normal_force_n_idx, 0.0),
        ),
        min_distance_to_dig_area_m=_read(field_indices.min_distance_to_dig_area_idx, -1.0),
        bucket_depth_below_dig_area_plane_m=max(
            0.0,
            _read(field_indices.bucket_depth_below_dig_area_plane_idx, 0.0),
        ),
    )


class AgxExcavationRewardTracker:
    """
    Reward tracker for the current Unity AGX excavation mission.

    This tracker does not enforce a hard stage machine. Instead, it attaches
    shaped reward to a set of observable sub-targets:
    - opening the mission with a qualified DigArea good start when available
    - loading soil into the bucket
    - moving a meaningful load toward the active target
    - increasing mass retained in the active target
    - holding retained target mass above the configured success threshold

    If the Unity server still exports the legacy shorter env_state layout, the
    DigArea gate is disabled automatically and the older reward behavior is
    preserved.
    """

    def __init__(
        self,
        mission: AgxExcavationMissionConfig,
        env_state_order: Iterable[str],
    ) -> None:
        self.mission = mission
        self._field_indices = resolve_agx_field_indices(env_state_order)
        self._last_observation = AgxExcavationObservation()
        self._success_consecutive_steps = 0
        self._success_latched = False
        self._last_phase = "idle"
        self._good_dig_started = False
        self._dig_area_gating_enabled = (
            self._field_indices.min_distance_to_dig_area_idx is not None
            and self._field_indices.bucket_depth_below_dig_area_plane_idx is not None
        )

    @property
    def field_indices(self) -> AgxExcavationFieldIndices:
        return self._field_indices

    @property
    def last_phase(self) -> str:
        return self._last_phase

    @property
    def success_latched(self) -> bool:
        return self._success_latched

    def reset(self) -> None:
        self._last_observation = AgxExcavationObservation()
        self._success_consecutive_steps = 0
        self._success_latched = False
        self._last_phase = "idle"
        self._good_dig_started = False

    def _success_condition_met(
        self,
        observation: AgxExcavationObservation,
    ) -> tuple[bool, float]:
        mission = self.mission
        success_signal_value = observation.value_for(mission.success_signal_name)
        if mission.success_mode == "final_hold":
            return success_signal_value >= mission.success_mass_thresh, success_signal_value
        if mission.success_mode == "dump_complete_final_hold":
            return (
                success_signal_value >= mission.success_mass_thresh
                and observation.mass_in_bucket_kg <= mission.residual_bucket_mass_thresh
            ), success_signal_value
        raise ValueError(
            f"Unsupported AGX excavation success_mode={mission.success_mode!r}. "
            "Supported modes: 'final_hold', 'dump_complete_final_hold'."
        )

    def update(
        self,
        env_state: np.ndarray | Iterable[float],
    ) -> AgxExcavationStepResult:
        observation = decode_agx_env_state(env_state, self._field_indices)
        previous = self._last_observation
        mission = self.mission

        delta_bucket = observation.mass_in_bucket_kg - previous.mass_in_bucket_kg
        delta_excavated = observation.excavated_mass_kg - previous.excavated_mass_kg
        delta_target = observation.mass_in_target_box_kg - previous.mass_in_target_box_kg
        delta_deposited = (
            observation.deposited_mass_in_target_box_kg
            - previous.deposited_mass_in_target_box_kg
        )
        delta_target_hard_collision_count = max(
            0.0,
            observation.target_hard_collision_count - previous.target_hard_collision_count,
        )

        raw_load_progress = (
            delta_bucket >= mission.bucket_mass_delta_tol_kg
            or delta_excavated >= mission.bucket_mass_delta_tol_kg
        )
        has_valid_dig_area_distance = observation.min_distance_to_dig_area_m >= 0.0
        touches_dig_area = (
            has_valid_dig_area_distance
            and observation.min_distance_to_dig_area_m <= mission.dig_area_touch_tolerance_m
        )
        digs_below_plane = (
            observation.bucket_depth_below_dig_area_plane_m
            >= mission.dig_below_plane_depth_tolerance_m
        )
        qualified_good_dig_step = (
            raw_load_progress
            and touches_dig_area
            and digs_below_plane
        )
        was_good_dig_started = self._good_dig_started
        if self._dig_area_gating_enabled and qualified_good_dig_step:
            self._good_dig_started = True

        good_dig_gate_open = (not self._dig_area_gating_enabled) or self._good_dig_started
        has_valid_distance = observation.min_distance_to_target_m >= 0.0
        previous_has_valid_distance = previous.min_distance_to_target_m >= 0.0
        distance_improvement = 0.0
        if has_valid_distance and previous_has_valid_distance:
            distance_improvement = (
                previous.min_distance_to_target_m - observation.min_distance_to_target_m
            )

        has_load_progress = raw_load_progress and good_dig_gate_open
        has_load = good_dig_gate_open and (
            observation.mass_in_bucket_kg >= mission.load_mass_threshold_kg
        )
        approach_progress = (
            has_load
            and has_valid_distance
            and previous_has_valid_distance
            and distance_improvement >= mission.distance_progress_delta_m
        )
        in_target_approach_zone = (
            has_load
            and has_valid_distance
            and observation.min_distance_to_target_m <= mission.target_approach_distance_m
        )
        deposit_progress = (
            good_dig_gate_open
            and (
                delta_target >= mission.target_mass_delta_tol_kg
                or delta_deposited >= mission.target_mass_delta_tol_kg
            )
        )
        has_retained_mass = (
            good_dig_gate_open
            and (
                observation.deposited_mass_in_target_box_kg >= mission.deposit_started_threshold_kg
                or observation.mass_in_target_box_kg >= mission.deposit_started_threshold_kg
            )
        )
        unsafe_distance = (
            has_valid_distance
            and observation.min_distance_to_target_m <= mission.unsafe_distance_m
        )
        hard_target_collision = delta_target_hard_collision_count > 0.0
        spill_detected = (
            good_dig_gate_open
            and previous.mass_in_bucket_kg >= mission.load_mass_threshold_kg * 0.5
            and (previous.mass_in_bucket_kg - observation.mass_in_bucket_kg)
            >= mission.bucket_mass_delta_tol_kg
            and not deposit_progress
        )

        success_condition_met, success_signal_value = self._success_condition_met(observation)
        if success_condition_met:
            self._success_consecutive_steps += 1
        else:
            self._success_consecutive_steps = 0

        success_held = self._success_consecutive_steps >= mission.success_hold_steps
        was_success_latched = self._success_latched
        if success_held:
            self._success_latched = True

        load_component = 0.0
        if good_dig_gate_open:
            load_component = float(
                np.clip(
                    observation.mass_in_bucket_kg / max(mission.load_mass_threshold_kg, 1.0),
                    0.0,
                    1.0,
                )
            )
            if has_load_progress:
                load_component = max(load_component, 0.25)

        approach_component = 0.0
        if has_load and has_valid_distance:
            approach_component = float(
                np.clip(
                    1.0
                    - (observation.min_distance_to_target_m / max(mission.target_approach_distance_m, 1.0e-6)),
                    0.0,
                    1.0,
                )
            )
            if approach_progress:
                approach_component = max(approach_component, 0.25)

        deposit_component = 0.0
        if good_dig_gate_open:
            deposit_component = float(
                np.clip(
                    observation.deposited_mass_in_target_box_kg
                    / max(mission.success_mass_thresh, 1.0),
                    0.0,
                    1.0,
                )
            )
            if deposit_progress:
                deposit_component = max(deposit_component, 0.25)
            if has_retained_mass:
                deposit_component = max(deposit_component, 0.10)

        hold_component = 0.0
        if mission.success_hold_steps > 0:
            hold_component = float(
                np.clip(
                    self._success_consecutive_steps / mission.success_hold_steps,
                    0.0,
                    1.0,
                )
            )

        reward = load_component + approach_component + deposit_component + hold_component
        if spill_detected:
            reward -= mission.spill_penalty
        if unsafe_distance and not self._success_latched:
            reward -= mission.unsafe_distance_penalty
        if self._success_latched:
            reward = mission.max_reward
        if hard_target_collision:
            reward -= mission.hard_collision_penalty
        reward = float(np.clip(reward, 0.0, mission.max_reward))

        phase_label = "idle"
        if load_component > 0.0:
            phase_label = AGX_PHASE_LABELS[1.0]
        if approach_component > 0.0:
            phase_label = AGX_PHASE_LABELS[2.0]
        if deposit_component > 0.0:
            phase_label = AGX_PHASE_LABELS[3.0]
        if self._success_latched:
            phase_label = AGX_PHASE_LABELS[mission.max_reward]

        step_successes: list[str] = []
        step_failures: list[str] = []

        if self._dig_area_gating_enabled and qualified_good_dig_step and not was_good_dig_started:
            step_successes.append("good_dig_start")
        if has_load_progress:
            step_successes.append("load_progress")
        if (
            has_load
            and previous.mass_in_bucket_kg < mission.load_mass_threshold_kg
        ):
            step_successes.append("load_ready")
        if approach_progress:
            step_successes.append("approach_progress")
        if (
            in_target_approach_zone
            and (
                not previous_has_valid_distance
                or previous.min_distance_to_target_m > mission.target_approach_distance_m
            )
        ):
            step_successes.append("entered_target_zone")
        if deposit_progress:
            step_successes.append("deposit_progress")
        if success_condition_met and self._success_consecutive_steps == 1:
            step_successes.append("success_threshold_reached")
        if self._success_latched and not was_success_latched:
            step_successes.append("mission_success")

        if (
            self._dig_area_gating_enabled
            and raw_load_progress
            and not was_good_dig_started
            and not qualified_good_dig_step
        ):
            step_failures.append("load_outside_dig_area")
        if spill_detected:
            step_failures.append("spill_before_target")
        if unsafe_distance:
            step_failures.append("unsafe_target_distance")
        if hard_target_collision:
            step_failures.append("hard_target_collision")

        self._last_observation = observation
        self._last_phase = phase_label

        return AgxExcavationStepResult(
            reward=reward,
            phase_label=phase_label,
            success=self._success_latched,
            step_successes=tuple(step_successes),
            step_failures=tuple(step_failures),
            metrics={
                "mass_in_bucket_kg": observation.mass_in_bucket_kg,
                "excavated_mass_kg": observation.excavated_mass_kg,
                "mass_in_target_box_kg": observation.mass_in_target_box_kg,
                "deposited_mass_in_target_box_kg": observation.deposited_mass_in_target_box_kg,
                "min_distance_to_target_m": observation.min_distance_to_target_m,
                "target_hard_collision_count": observation.target_hard_collision_count,
                "target_contact_max_normal_force_n": observation.target_contact_max_normal_force_n,
                "min_distance_to_dig_area_m": observation.min_distance_to_dig_area_m,
                "bucket_depth_below_dig_area_plane_m": observation.bucket_depth_below_dig_area_plane_m,
                "delta_target_hard_collision_count": delta_target_hard_collision_count,
                "delta_mass_in_bucket_kg": delta_bucket,
                "delta_excavated_mass_kg": delta_excavated,
                "delta_mass_in_target_box_kg": delta_target,
                "delta_deposited_mass_in_target_box_kg": delta_deposited,
                "distance_improvement_m": distance_improvement,
                "success_signal_value": success_signal_value,
                "success_condition_met": float(success_condition_met),
                "success_mode_is_dump_complete": float(
                    mission.success_mode == "dump_complete_final_hold"
                ),
                "residual_bucket_mass_thresh": mission.residual_bucket_mass_thresh,
                "success_hold_steps": float(self._success_consecutive_steps),
                "raw_load_progress": float(raw_load_progress),
                "good_dig_started": float(self._good_dig_started),
                "qualified_good_dig_step": float(qualified_good_dig_step),
                "load_component": load_component,
                "approach_component": approach_component,
                "deposit_component": deposit_component,
                "hold_component": hold_component,
            },
        )
