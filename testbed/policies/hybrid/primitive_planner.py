"""V2.2 scripted planner over four ACT primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.boundary_detector import BoundaryDetector
from testbed.policies.base import Policy, register_policy
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK


PRIMITIVE_SKILL_NAMES = ("dig", "carry", "dump", "return")
PRIMITIVE_SKILL_IDS = {name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES)}
TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY = "v2_2_primitive_return_policy"
TRANSITION_POLICY_MODE_PRIMITIVE = "primitive_return_policy"
BOOTSTRAP_SKILL_NAME = "bootstrap"


@dataclass(frozen=True)
class PrimitivePlannerDebugState:
    skill_name: str
    skill_id: int
    skill_switch_reason: str
    primitive_checkpoint_path: str
    hybrid_mode: str
    transition_timeout: bool
    transition_completed: bool
    completed_transition_count: int
    transition_timeout_count: int
    dump_ready_hold_count: int
    dump_done_hold_count: int
    primitive_cycle_index: int


@register_policy("primitive_planner_act")
class PrimitivePlannerACTPolicy(Policy):
    """Scripted V2.2 skill planner over dig/carry/dump/return ACT policies.

    The low-level ACT policies receive only their configured observation keys
    (qpos+qvel by default). Target geometry is used here as an oracle switch
    signal for simulation diagnostics, not as a low-dimensional policy input.
    """

    def __init__(
        self,
        *,
        dig_policy: Policy,
        carry_policy: Policy,
        dump_policy: Policy,
        return_policy: Policy,
        boundary_detector: BoundaryDetector,
        bootstrap_policy: Policy | None = None,
        bootstrap_end_mode: str = "disabled",
        bootstrap_end_min_bucket_mass_kg: float = 300.0,
        bootstrap_end_min_distance_to_dig_area_m: float = 0.25,
        dig_to_carry_min_bucket_mass_kg: float = 300.0,
        dig_to_carry_min_distance_to_dig_area_m: float = 0.0,
        dump_ready_min_bucket_mass_kg: float = 150.0,
        dump_ready_min_height_above_rim_m: float = 0.45,
        dump_ready_require_over_footprint: bool = True,
        dump_ready_require_clearance: bool = True,
        dump_ready_max_horizontal_distance_m: float | None = 0.60,
        dump_ready_hold_steps: int = 3,
        dump_done_max_bucket_mass_kg: float = 100.0,
        dump_done_min_deposit_delta_kg: float = 10.0,
        dump_done_hold_steps: int = 2,
        return_max_steps: int = 420,
        action_dim: int = 4,
        primitive_checkpoint_paths: dict[str, str] | None = None,
    ) -> None:
        self.dig_policy = dig_policy
        self.carry_policy = carry_policy
        self.dump_policy = dump_policy
        self.return_policy = return_policy
        self.bootstrap_policy = bootstrap_policy
        self.boundary_detector = boundary_detector
        self.bootstrap_end_mode = str(bootstrap_end_mode)
        self.bootstrap_end_min_bucket_mass_kg = float(bootstrap_end_min_bucket_mass_kg)
        self.bootstrap_end_min_distance_to_dig_area_m = float(
            bootstrap_end_min_distance_to_dig_area_m
        )
        self.dig_to_carry_min_bucket_mass_kg = float(dig_to_carry_min_bucket_mass_kg)
        self.dig_to_carry_min_distance_to_dig_area_m = float(
            dig_to_carry_min_distance_to_dig_area_m
        )
        self.dump_ready_min_bucket_mass_kg = float(dump_ready_min_bucket_mass_kg)
        self.dump_ready_min_height_above_rim_m = float(dump_ready_min_height_above_rim_m)
        self.dump_ready_require_over_footprint = bool(dump_ready_require_over_footprint)
        self.dump_ready_require_clearance = bool(dump_ready_require_clearance)
        self.dump_ready_max_horizontal_distance_m = (
            None
            if dump_ready_max_horizontal_distance_m is None
            else float(dump_ready_max_horizontal_distance_m)
        )
        self.dump_ready_hold_steps = max(1, int(dump_ready_hold_steps))
        self.dump_done_max_bucket_mass_kg = float(dump_done_max_bucket_mass_kg)
        self.dump_done_min_deposit_delta_kg = float(dump_done_min_deposit_delta_kg)
        self.dump_done_hold_steps = max(1, int(dump_done_hold_steps))
        self.return_max_steps = int(return_max_steps)
        self.action_dim = int(action_dim)
        self.primitive_checkpoint_paths = {
            str(name): str(path)
            for name, path in dict(primitive_checkpoint_paths or {}).items()
        }
        self.reset()

    def reset(self) -> None:
        for policy in self._all_policies():
            policy.reset()
        self.boundary_detector.reset()
        self._skill_name = (
            BOOTSTRAP_SKILL_NAME
            if self.bootstrap_policy is not None and self.bootstrap_end_mode != "disabled"
            else "dig"
        )
        self._prev_action: np.ndarray | None = None
        self._switch_reason = "reset"
        self._dump_ready_hold_count = 0
        self._dump_done_hold_count = 0
        self._return_step_count = 0
        self._completed_transition_count = 0
        self._transition_timeout_count = 0
        self._cycle_index = 0
        self._dump_start_deposited_mass_kg = 0.0
        self._debug_state = self._make_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )

    def predict(self, obs: dict) -> np.ndarray:
        boundary_event = None
        if self._prev_action is not None:
            boundary_event = self.boundary_detector.update(
                env_state=obs.get("env_state", np.zeros(13, dtype=np.float32)),
                action=self._prev_action,
                qpos=obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
                reward_phase=obs.get("reward_phase"),
                task_step_successes=obs.get("task_step_successes"),
                task_metrics=obs.get("task_metrics"),
            )

        self._switch_reason = ""
        transition_timeout = False
        transition_completed = False
        self._maybe_switch_skill(obs=obs, boundary_event=boundary_event)

        if self._skill_name == "return":
            self._return_step_count += 1
            if self.return_max_steps > 0 and self._return_step_count >= self.return_max_steps:
                transition_timeout = True
                self._transition_timeout_count += 1

        policy = self._active_policy()
        action = np.asarray(policy.predict(obs), dtype=np.float32).reshape(self.action_dim)
        self._prev_action = action.copy()

        if self._switch_reason == "return_to_dig_qualified_dig_start":
            transition_completed = True

        self._debug_state = self._make_debug_state(
            transition_timeout=transition_timeout,
            transition_completed=transition_completed,
        )
        return action

    def debug_state(self) -> dict[str, Any]:
        return {
            "skill_name": self._debug_state.skill_name,
            "skill_id": int(self._debug_state.skill_id),
            "skill_switch_reason": self._debug_state.skill_switch_reason,
            "primitive_checkpoint_path": self._debug_state.primitive_checkpoint_path,
            "hybrid_mode": self._debug_state.hybrid_mode,
            "transition_timeout": bool(self._debug_state.transition_timeout),
            "transition_completed": bool(self._debug_state.transition_completed),
            "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
            "transition_fallback_count": 0,
            "transition_fallback_reason": "",
            "completed_transition_count": int(
                self._debug_state.completed_transition_count
            ),
            "transition_timeout_count": int(self._debug_state.transition_timeout_count),
            "dump_ready_hold_count": int(self._debug_state.dump_ready_hold_count),
            "dump_done_hold_count": int(self._debug_state.dump_done_hold_count),
            "primitive_cycle_index": int(self._debug_state.primitive_cycle_index),
        }

    def rollout_summary(self) -> dict[str, float | int | str | list[str]]:
        return {
            "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
            "transition_fallback_count": 0,
            "transition_fallback_reason": "",
            "transition_timeout_count": int(self._transition_timeout_count),
            "completed_transition_count": int(self._completed_transition_count),
            "primitive_final_skill": str(self._skill_name),
            "primitive_cycle_index": int(self._cycle_index),
        }

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self._should_end_bootstrap(obs=obs, boundary_event=boundary_event):
                next_skill = (
                    "dig"
                    if self.bootstrap_end_mode == "first_qualified_dig_start"
                    else "carry"
                )
                self._set_skill(next_skill, f"bootstrap_to_{next_skill}")
            return

        if self._skill_name == "dig":
            if self._dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
                self._set_skill("carry", "dig_to_carry_loaded")
            return

        if self._skill_name == "carry":
            if self._dump_ready(obs):
                self._dump_ready_hold_count += 1
            else:
                self._dump_ready_hold_count = 0
            if self._dump_ready_hold_count >= self.dump_ready_hold_steps:
                self._dump_start_deposited_mass_kg = self._deposited_mass(obs)
                self._set_skill("dump", "carry_to_dump_target_ready")
            return

        if self._skill_name == "dump":
            if boundary_event is not None and bool(getattr(boundary_event, "dump_end", False)):
                self._set_skill("return", "dump_to_return_dump_end")
                return
            if self._dump_done(obs):
                self._dump_done_hold_count += 1
            else:
                self._dump_done_hold_count = 0
            if self._dump_done_hold_count >= self.dump_done_hold_steps:
                self._set_skill("return", "dump_to_return_mass_low")
            return

        if self._skill_name == "return":
            if boundary_event is not None and bool(
                getattr(boundary_event, "qualified_dig_start", False)
            ):
                self._completed_transition_count += 1
                self._cycle_index += 1
                self._set_skill("dig", "return_to_dig_qualified_dig_start")

    def _set_skill(self, skill_name: str, reason: str) -> None:
        if skill_name == self._skill_name:
            return
        self._skill_name = str(skill_name)
        self._switch_reason = str(reason)
        self._active_policy().reset()
        if skill_name == "carry":
            self._dump_ready_hold_count = 0
        elif skill_name == "dump":
            self._dump_done_hold_count = 0
        elif skill_name == "return":
            self._return_step_count = 0
        elif skill_name == "dig":
            self._dump_ready_hold_count = 0
            self._dump_done_hold_count = 0

    def _should_end_bootstrap(self, *, obs: dict, boundary_event: Any | None) -> bool:
        if self.bootstrap_policy is None:
            return False
        if self.bootstrap_end_mode == "first_qualified_dig_start":
            return bool(
                boundary_event is not None
                and getattr(boundary_event, "qualified_dig_start", False)
            )
        if self.bootstrap_end_mode == "loaded_and_clear":
            return self._mass_in_bucket(obs) >= self.bootstrap_end_min_bucket_mass_kg and (
                self._min_distance_to_dig_area(obs)
                >= self.bootstrap_end_min_distance_to_dig_area_m
            )
        if self.bootstrap_end_mode == "disabled":
            return False
        raise ValueError(f"Unsupported bootstrap_end_mode {self.bootstrap_end_mode!r}.")

    def _dig_to_carry_ready(self, *, obs: dict, boundary_event: Any | None) -> bool:
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        mass = float(metrics.get("mass_in_bucket_kg", self._mass_in_bucket(obs)))
        dig_distance = float(
            metrics.get("min_distance_to_dig_area_m", self._min_distance_to_dig_area(obs))
        )
        return bool(
            mass >= self.dig_to_carry_min_bucket_mass_kg
            and dig_distance >= self.dig_to_carry_min_distance_to_dig_area_m
        )

    def _dump_ready(self, obs: dict) -> bool:
        mass = self._mass_in_bucket(obs)
        if mass < self.dump_ready_min_bucket_mass_kg:
            return False
        geometry = self._target_geometry(obs)
        over_footprint = geometry["bucket_over_target_footprint_mask"] > 0.5
        height_ok = (
            geometry["bucket_height_above_target_rim_m"]
            >= self.dump_ready_min_height_above_rim_m - 1.0e-6
        )
        clearance_ok = geometry["dump_clearance_ok_mask"] > 0.5
        horizontal_ok = False
        if self.dump_ready_max_horizontal_distance_m is not None:
            horizontal_ok = (
                geometry["target_horizontal_distance_m"]
                <= self.dump_ready_max_horizontal_distance_m + 1.0e-6
            )
        position_ok = (
            over_footprint
            or horizontal_ok
            or not self.dump_ready_require_over_footprint
        )
        return bool(
            height_ok
            and position_ok
            and (clearance_ok or not self.dump_ready_require_clearance)
        )

    def _dump_done(self, obs: dict) -> bool:
        mass_low = self._mass_in_bucket(obs) <= self.dump_done_max_bucket_mass_kg
        deposit_delta = self._deposited_mass(obs) - self._dump_start_deposited_mass_kg
        return bool(mass_low and deposit_delta >= self.dump_done_min_deposit_delta_kg)

    def _target_geometry(self, obs: dict) -> dict[str, float]:
        task_metrics = dict(obs.get("task_metrics", {}) or {})

        def _metric(name: str, index: int) -> float:
            if name in task_metrics:
                value = float(task_metrics[name])
                if np.isfinite(value):
                    return value
            env_state = self._env_state(obs)
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

        available = task_metrics.get("target_geometry_available")
        if available is not None and float(available) <= 0.5:
            raise RuntimeError(
                "primitive carry->dump switch requires target_geometry_available=1."
            )

        return {
            "target_horizontal_distance_m": _metric(
                "target_horizontal_distance_m",
                ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
            ),
            "bucket_height_above_target_rim_m": _metric(
                "bucket_height_above_target_rim_m",
                ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
            ),
            "bucket_over_target_footprint_mask": _metric(
                "bucket_over_target_footprint_mask",
                ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
            ),
            "dump_clearance_ok_mask": _metric(
                "dump_clearance_ok_mask",
                ENV_STATE_DUMP_CLEARANCE_OK_IDX,
            ),
        }

    def _mass_in_bucket(self, obs: dict) -> float:
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if "mass_in_bucket_kg" in task_metrics:
            return float(task_metrics["mass_in_bucket_kg"])
        env_state = self._env_state(obs)
        return (
            float(env_state[ENV_STATE_MASS_IN_BUCKET_IDX])
            if len(env_state) > ENV_STATE_MASS_IN_BUCKET_IDX
            else 0.0
        )

    def _deposited_mass(self, obs: dict) -> float:
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if "deposited_mass_in_target_box_kg" in task_metrics:
            return float(task_metrics["deposited_mass_in_target_box_kg"])
        env_state = self._env_state(obs)
        return (
            float(env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX])
            if len(env_state) > ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
            else 0.0
        )

    def _min_distance_to_dig_area(self, obs: dict) -> float:
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if "min_distance_to_dig_area_m" in task_metrics:
            return float(task_metrics["min_distance_to_dig_area_m"])
        env_state = self._env_state(obs)
        return (
            float(env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX])
            if len(env_state) > ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX
            else 0.0
        )

    def _env_state(self, obs: dict) -> np.ndarray:
        return np.asarray(
            obs.get("env_state", np.zeros(13, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)

    def _active_policy(self) -> Policy:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self.bootstrap_policy is None:
                raise RuntimeError("bootstrap skill is active but bootstrap_policy is None.")
            return self.bootstrap_policy
        if self._skill_name == "dig":
            return self.dig_policy
        if self._skill_name == "carry":
            return self.carry_policy
        if self._skill_name == "dump":
            return self.dump_policy
        if self._skill_name == "return":
            return self.return_policy
        raise RuntimeError(f"Unknown primitive skill {self._skill_name!r}.")

    def _all_policies(self) -> list[Policy]:
        policies = [self.dig_policy, self.carry_policy, self.dump_policy, self.return_policy]
        if self.bootstrap_policy is not None:
            policies.append(self.bootstrap_policy)
        return policies

    def _make_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitivePlannerDebugState:
        skill_name = str(self._skill_name)
        skill_id = PRIMITIVE_SKILL_IDS.get(skill_name, -1)
        hybrid_mode = HYBRID_MODE_TRANSITION if skill_name == "return" else HYBRID_MODE_WORK
        return PrimitivePlannerDebugState(
            skill_name=skill_name,
            skill_id=int(skill_id),
            skill_switch_reason=str(self._switch_reason),
            primitive_checkpoint_path=str(self.primitive_checkpoint_paths.get(skill_name, "")),
            hybrid_mode=hybrid_mode,
            transition_timeout=bool(transition_timeout),
            transition_completed=bool(transition_completed),
            completed_transition_count=int(self._completed_transition_count),
            transition_timeout_count=int(self._transition_timeout_count),
            dump_ready_hold_count=int(self._dump_ready_hold_count),
            dump_done_hold_count=int(self._dump_done_hold_count),
            primitive_cycle_index=int(self._cycle_index),
        )
