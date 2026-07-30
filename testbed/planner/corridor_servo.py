"""Scripted corridor servo for the Stage-2 hybrid transition controller."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from testbed.data.schema import (
    ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
)

TRANSITION_SUBMODE_CLEAR_TARGET = "clear_target"
TRANSITION_SUBMODE_CORRIDOR_ALIGN = "corridor_align"
TRANSITION_SUBMODE_WAIT_NEXT_DIG = "wait_next_dig"

WAIT_NEXT_DIG_MODE_WORK_POLICY_HANDOFF = "work_policy_handoff"
WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE = "servo_reentry_pose"


@dataclass(frozen=True)
class EntryCorridorBand:
    name: str
    sector_id: int
    qpos_lo: np.ndarray
    qpos_hi: np.ndarray

    @property
    def center(self) -> np.ndarray:
        return (self.qpos_lo + self.qpos_hi) * 0.5


@dataclass(frozen=True)
class TransitionControlOutput:
    action: np.ndarray
    submode: str
    transition_completed: bool
    transition_timeout: bool
    transition_collision_delta: int
    corridor_align_steps: int
    wait_next_dig_steps: int


def build_default_entry_corridor_bands() -> dict[str, EntryCorridorBand]:
    centers = {
        "left": np.asarray([0.32, 0.634, 0.523, 0.690], dtype=np.float32),
        "mid": np.asarray([0.50, 0.634, 0.523, 0.690], dtype=np.float32),
        "right": np.asarray([0.68, 0.634, 0.523, 0.690], dtype=np.float32),
    }
    half_width = np.asarray([0.08, 0.06, 0.06, 0.08], dtype=np.float32)
    bands: dict[str, EntryCorridorBand] = {}
    for sector_id, name in enumerate(("left", "mid", "right")):
        center = centers[name]
        bands[name] = EntryCorridorBand(
            name=name,
            sector_id=sector_id,
            qpos_lo=np.asarray(center - half_width, dtype=np.float32),
            qpos_hi=np.asarray(center + half_width, dtype=np.float32),
        )
    return bands


def normalize_named_entry_corridor_bands(
    bands: dict[str, EntryCorridorBand],
) -> dict[str, EntryCorridorBand]:
    """Ensure band names match the physical swing direction.

    Historically some configs used a mirrored convention where the higher-swing
    corridor was named ``left`` and the lower-swing corridor was named
    ``right``. Work-skill relabeling now uses the physically intuitive mapping:
    lower swing -> left, higher swing -> right. This helper keeps legacy eval
    configs usable by swapping only the *named* bands when needed while
    preserving the canonical sector ids:

    - left  -> sector_id 0 -> lower swing
    - mid   -> sector_id 1
    - right -> sector_id 2 -> higher swing
    """

    left = bands.get("left")
    mid = bands.get("mid")
    right = bands.get("right")
    if left is None or mid is None or right is None:
        return bands
    if float(left.center[0]) <= float(right.center[0]):
        return bands
    return {
        "left": EntryCorridorBand(
            name="left",
            sector_id=0,
            qpos_lo=np.asarray(right.qpos_lo, dtype=np.float32),
            qpos_hi=np.asarray(right.qpos_hi, dtype=np.float32),
        ),
        "mid": EntryCorridorBand(
            name="mid",
            sector_id=1,
            qpos_lo=np.asarray(mid.qpos_lo, dtype=np.float32),
            qpos_hi=np.asarray(mid.qpos_hi, dtype=np.float32),
        ),
        "right": EntryCorridorBand(
            name="right",
            sector_id=2,
            qpos_lo=np.asarray(left.qpos_lo, dtype=np.float32),
            qpos_hi=np.asarray(left.qpos_hi, dtype=np.float32),
        ),
    }


class TransitionController:
    """Stateful scripted controller for the Stage-2 transition segment."""

    def __init__(
        self,
        *,
        bands: dict[str, EntryCorridorBand],
        kp: float = 2.0,
        kd: float = 0.25,
        action_clip: float = 0.35,
        action_clip_by_joint: np.ndarray | list[float] | tuple[float, ...] | None = None,
        target_approach_distance_m: float = 1.25,
        clear_target_extra_distance_m: float = 0.25,
        clear_target_min_steps: int = 0,
        clear_target_max_steps: int = 60,
        corridor_align_max_steps: int = 100,
        corridor_align_qvel_abs_max: float = 0.15,
        corridor_align_hold_steps: int = 5,
        wait_next_dig_max_steps: int = 120,
        wait_next_dig_mode: str = WAIT_NEXT_DIG_MODE_WORK_POLICY_HANDOFF,
        wait_next_dig_reentry_template_qpos: np.ndarray | list[float] | tuple[float, ...] | None = None,
        scripted_bucket_qpos_target: float | None = None,
        scripted_bucket_qpos_tolerance: float = 0.03,
    ) -> None:
        if not bands:
            raise ValueError("TransitionController requires at least one corridor band.")
        self.bands = {str(name): band for name, band in bands.items()}
        self.kp = float(kp)
        self.kd = float(kd)
        self.action_clip = float(action_clip)
        if action_clip_by_joint is None:
            self.action_clip_by_joint = np.full(4, self.action_clip, dtype=np.float32)
        else:
            self.action_clip_by_joint = np.asarray(
                action_clip_by_joint,
                dtype=np.float32,
            ).reshape(4)
        self.target_approach_distance_m = float(target_approach_distance_m)
        self.clear_target_extra_distance_m = float(clear_target_extra_distance_m)
        self.clear_target_min_steps = int(clear_target_min_steps)
        self.clear_target_max_steps = int(clear_target_max_steps)
        self.corridor_align_max_steps = int(corridor_align_max_steps)
        self.corridor_align_qvel_abs_max = float(corridor_align_qvel_abs_max)
        self.corridor_align_hold_steps = int(corridor_align_hold_steps)
        self.wait_next_dig_max_steps = int(wait_next_dig_max_steps)
        self.wait_next_dig_mode = str(wait_next_dig_mode)
        self.scripted_bucket_qpos_target = (
            None
            if scripted_bucket_qpos_target is None
            else float(scripted_bucket_qpos_target)
        )
        self.scripted_bucket_qpos_tolerance = float(scripted_bucket_qpos_tolerance)
        if wait_next_dig_reentry_template_qpos is None:
            self.wait_next_dig_reentry_template_qpos = np.asarray(
                [0.50, 0.255, 0.520, 0.0002],
                dtype=np.float32,
            )
        else:
            self.wait_next_dig_reentry_template_qpos = np.asarray(
                wait_next_dig_reentry_template_qpos,
                dtype=np.float32,
            ).reshape(4)
        if self.wait_next_dig_mode not in {
            WAIT_NEXT_DIG_MODE_WORK_POLICY_HANDOFF,
            WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE,
        }:
            raise ValueError(
                "Unsupported wait_next_dig_mode "
                f"{self.wait_next_dig_mode!r}. Expected "
                f"{WAIT_NEXT_DIG_MODE_WORK_POLICY_HANDOFF!r} or "
                f"{WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE!r}."
            )
        self.reset()

    def reset(self) -> None:
        self._band: EntryCorridorBand | None = None
        self._submode: str = TRANSITION_SUBMODE_CLEAR_TARGET
        self._submode_steps = 0
        self._align_hold_steps = 0
        self._corridor_align_steps = 0
        self._wait_next_dig_steps = 0
        self._transition_collision_delta = 0
        self._last_collision_count: int | None = None

    @property
    def current_submode(self) -> str:
        return str(self._submode)

    def should_handoff_to_work_policy(self) -> bool:
        return self.wait_next_dig_mode == WAIT_NEXT_DIG_MODE_WORK_POLICY_HANDOFF

    def reset_wait_next_dig_timeout_budget(self) -> None:
        """Restart the timeout budget for the active wait_next_dig submode."""
        if self._submode == TRANSITION_SUBMODE_WAIT_NEXT_DIG:
            self._submode_steps = 0

    def start_transition(
        self,
        *,
        target_sector_name: str,
        env_state: np.ndarray | list[float] | tuple[float, ...] | None = None,
    ) -> None:
        try:
            self._band = self.bands[str(target_sector_name)]
        except KeyError as exc:
            raise KeyError(
                f"Unknown corridor band {target_sector_name!r}. Available: {sorted(self.bands)}."
            ) from exc
        self._submode = TRANSITION_SUBMODE_CLEAR_TARGET
        self._submode_steps = 0
        self._align_hold_steps = 0
        self._corridor_align_steps = 0
        self._wait_next_dig_steps = 0
        self._transition_collision_delta = 0
        env_state_arr = None if env_state is None else np.asarray(env_state, dtype=np.float32)
        if env_state_arr is None or len(env_state_arr) <= ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX:
            self._last_collision_count = 0
        else:
            self._last_collision_count = int(
                round(float(env_state_arr[ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX]))
            )

    def step(
        self,
        *,
        obs: dict,
        qualified_dig_start: bool,
    ) -> TransitionControlOutput:
        if self._band is None:
            raise RuntimeError("TransitionController.step() called before start_transition().")

        qpos = np.asarray(obs.get("qpos", np.zeros(4, dtype=np.float32)), dtype=np.float32)
        qvel = np.asarray(obs.get("qvel", np.zeros(4, dtype=np.float32)), dtype=np.float32)
        env_state = np.asarray(
            obs.get("env_state", np.zeros(9, dtype=np.float32)),
            dtype=np.float32,
        )
        self._update_collision_delta(env_state)

        transition_completed = False
        transition_timeout = False

        if self._submode == TRANSITION_SUBMODE_CLEAR_TARGET:
            self._submode_steps += 1
            target_qpos = np.asarray(
                [self._band.center[0], 0.72, 0.46, 0.78],
                dtype=np.float32,
            )
            target_qpos = self._scripted_target_qpos(target_qpos)
            action = _pd_servo(
                qpos=qpos,
                qvel=qvel,
                target_qpos=target_qpos,
                kp=self.kp,
                kd=self.kd,
                action_clip=self.action_clip_by_joint,
            )
            min_distance_to_target = (
                float(env_state[ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX])
                if len(env_state) > ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX
                else 0.0
            )
            if (
                self._submode_steps >= self.clear_target_min_steps
                and (
                    min_distance_to_target
                    >= self.target_approach_distance_m + self.clear_target_extra_distance_m
                )
            ) or self._submode_steps >= self.clear_target_max_steps:
                self._submode = TRANSITION_SUBMODE_CORRIDOR_ALIGN
                self._submode_steps = 0
                self._align_hold_steps = 0

        elif self._submode == TRANSITION_SUBMODE_CORRIDOR_ALIGN:
            self._submode_steps += 1
            self._corridor_align_steps += 1
            target_qpos = self._scripted_target_qpos(self._band.center)
            action = _pd_servo(
                qpos=qpos,
                qvel=qvel,
                target_qpos=target_qpos,
                kp=self.kp,
                kd=self.kd,
                action_clip=self.action_clip_by_joint,
            )
            in_band = self._corridor_in_band(qpos)
            qvel_small = bool(np.all(np.abs(qvel) <= self.corridor_align_qvel_abs_max))
            if in_band and qvel_small:
                self._align_hold_steps += 1
            else:
                self._align_hold_steps = 0
            if self._align_hold_steps >= self.corridor_align_hold_steps:
                self._submode = TRANSITION_SUBMODE_WAIT_NEXT_DIG
                self._submode_steps = 0
            elif self._submode_steps >= self.corridor_align_max_steps:
                transition_timeout = True

        elif self._submode == TRANSITION_SUBMODE_WAIT_NEXT_DIG:
            self._submode_steps += 1
            self._wait_next_dig_steps += 1
            if self.wait_next_dig_mode == WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE:
                target_qpos = self.wait_next_dig_reentry_target_qpos(self._band.name)
            else:
                target_qpos = self._scripted_target_qpos(self._band.center)
            action = _pd_servo(
                qpos=qpos,
                qvel=qvel,
                target_qpos=target_qpos,
                kp=self.kp,
                kd=self.kd,
                action_clip=self.action_clip_by_joint,
            )
            if qualified_dig_start:
                transition_completed = True
            elif self._submode_steps >= self.wait_next_dig_max_steps:
                transition_timeout = True

        else:
            raise RuntimeError(f"Unknown transition submode {self._submode!r}.")

        return TransitionControlOutput(
            action=action,
            submode=str(self._submode),
            transition_completed=bool(transition_completed),
            transition_timeout=bool(transition_timeout),
            transition_collision_delta=int(self._transition_collision_delta),
            corridor_align_steps=int(self._corridor_align_steps),
            wait_next_dig_steps=int(self._wait_next_dig_steps),
        )

    def _update_collision_delta(self, env_state: np.ndarray) -> None:
        if len(env_state) <= ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX:
            return
        current = int(round(float(env_state[ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX])))
        if self._last_collision_count is None:
            self._last_collision_count = current
            return
        if current > self._last_collision_count:
            self._transition_collision_delta += int(current - self._last_collision_count)
        self._last_collision_count = current

    def wait_next_dig_reentry_target_qpos(self, sector_name: str) -> np.ndarray:
        band = self.bands[str(sector_name)]
        target = self.wait_next_dig_reentry_template_qpos.copy()
        target[0] = float(band.center[0])
        target = self._scripted_target_qpos(target)
        return target.astype(np.float32)

    def _scripted_target_qpos(self, target_qpos: np.ndarray) -> np.ndarray:
        target = np.asarray(target_qpos, dtype=np.float32).copy()
        if self.scripted_bucket_qpos_target is not None:
            target[3] = float(self.scripted_bucket_qpos_target)
        return target

    def _corridor_in_band(self, qpos: np.ndarray) -> bool:
        if self._band is None:
            return False
        qpos_arr = np.asarray(qpos, dtype=np.float32).reshape(4)
        qpos_lo = np.asarray(self._band.qpos_lo, dtype=np.float32).copy()
        qpos_hi = np.asarray(self._band.qpos_hi, dtype=np.float32).copy()
        if self.scripted_bucket_qpos_target is not None:
            bucket_target = float(self.scripted_bucket_qpos_target)
            bucket_tol = max(0.0, float(self.scripted_bucket_qpos_tolerance))
            qpos_lo[3] = bucket_target - bucket_tol
            qpos_hi[3] = bucket_target + bucket_tol
        return bool(np.all(qpos_arr >= qpos_lo) and np.all(qpos_arr <= qpos_hi))


def _pd_servo(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    target_qpos: np.ndarray,
    kp: float,
    kd: float,
    action_clip: float | np.ndarray | list[float] | tuple[float, ...],
) -> np.ndarray:
    action = kp * (target_qpos - qpos) - kd * qvel
    action_clip_arr = np.asarray(action_clip, dtype=np.float32)
    if action_clip_arr.ndim == 0:
        action_clip_arr = np.full_like(action, float(action_clip_arr))
    return np.clip(action, -action_clip_arr, action_clip_arr).astype(np.float32)
