"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    _build_dig_cut_token,
    build_live_dig_cut_tokens_from_pose,
)
from testbed.data.v2_1 import build_goal_tokens
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.boundary_detector import BoundaryDetector
from testbed.planner.cell_entry import (
    CELL_ENTRY_TOKEN_DIM,
    CellEntryGoal,
    CellEntryPlanner,
    CellGridSpec,
    PlannerDecisionAudit,
    PlannerDecisionAuditor,
    PrimitiveCycleOutcome,
    build_cell_entry_tokens,
)
from testbed.policies.base import Policy, register_policy
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK


PRIMITIVE_SKILL_NAMES = ("dig", "carry", "dump", "return")
PRIMITIVE_SKILL_IDS = {name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES)}
PRIMITIVE_SKILL_NAMES_5P = ("dig", "carry", "approach_dump", "dump_release", "return")
PRIMITIVE_SKILL_IDS_5P = {
    name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES_5P)
}
TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY = "v2_2_primitive_return_policy"
TRANSITION_POLICY_MODE_PRIMITIVE = "primitive_return_policy"
BOOTSTRAP_SKILL_NAME = "bootstrap"
PRIMITIVE_GOAL_SECTOR_IDS = {"left": 0, "mid": 1, "right": 2}


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
    approach_ready_hold_count: int = 0
    dump_release_ready_hold_count: int = 0


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
        dump_ready_position_mode: str = "footprint_or_dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m: float | None = 0.05,
        dump_ready_min_dump_area_relative_x_m: float | None = None,
        dump_ready_max_dump_area_relative_x_m: float | None = None,
        dump_ready_min_dump_area_relative_z_m: float | None = None,
        dump_ready_max_dump_area_relative_z_m: float | None = None,
        dump_ready_hold_steps: int = 3,
        dump_done_max_bucket_mass_kg: float = 100.0,
        dump_done_min_deposit_delta_kg: float = 10.0,
        dump_done_hold_steps: int = 2,
        dump_done_use_boundary_event: bool = True,
        return_max_steps: int = 420,
        action_dim: int = 4,
        primitive_checkpoint_paths: dict[str, str] | None = None,
        goal_sequence: list[str] | tuple[str, ...] | None = None,
        goal_scenario_id: str = "s0_truck",
        goal_depth_norm: float = 1.0,
        goal_dump_target_norm: float = 1.0,
        cell_entry_enabled: bool = False,
        cell_entry_grid: dict[str, Any] | None = None,
        cell_entry_low_productivity_payload_gain_kg: float = 100.0,
        dig_cut_planner: dict[str, Any] | None = None,
        scripted_bootstrap_target_qpos: list[float] | tuple[float, ...] | np.ndarray | None = None,
        scripted_bootstrap_kp: float = 2.0,
        scripted_bootstrap_kd: float = 0.25,
        scripted_bootstrap_action_clip: float | list[float] | tuple[float, ...] = 0.35,
        scripted_bootstrap_action_signs: list[float] | tuple[float, ...] | np.ndarray | None = None,
        scripted_bootstrap_qpos_tolerance: float = 0.02,
        scripted_bootstrap_qvel_abs_max: float = 0.08,
        scripted_bootstrap_hold_steps: int = 5,
        scripted_bootstrap_max_steps: int = 240,
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
        self.dump_ready_position_mode = str(dump_ready_position_mode)
        self.dump_ready_max_dump_area_footprint_outside_distance_m = (
            None
            if dump_ready_max_dump_area_footprint_outside_distance_m is None
            else float(dump_ready_max_dump_area_footprint_outside_distance_m)
        )
        self.dump_ready_min_dump_area_relative_x_m = (
            None
            if dump_ready_min_dump_area_relative_x_m is None
            else float(dump_ready_min_dump_area_relative_x_m)
        )
        self.dump_ready_max_dump_area_relative_x_m = (
            None
            if dump_ready_max_dump_area_relative_x_m is None
            else float(dump_ready_max_dump_area_relative_x_m)
        )
        self.dump_ready_min_dump_area_relative_z_m = (
            None
            if dump_ready_min_dump_area_relative_z_m is None
            else float(dump_ready_min_dump_area_relative_z_m)
        )
        self.dump_ready_max_dump_area_relative_z_m = (
            None
            if dump_ready_max_dump_area_relative_z_m is None
            else float(dump_ready_max_dump_area_relative_z_m)
        )
        self.dump_ready_hold_steps = max(1, int(dump_ready_hold_steps))
        self.dump_done_max_bucket_mass_kg = float(dump_done_max_bucket_mass_kg)
        self.dump_done_min_deposit_delta_kg = float(dump_done_min_deposit_delta_kg)
        self.dump_done_hold_steps = max(1, int(dump_done_hold_steps))
        self.dump_done_use_boundary_event = bool(dump_done_use_boundary_event)
        self.return_max_steps = int(return_max_steps)
        self.action_dim = int(action_dim)
        self.primitive_checkpoint_paths = {
            str(name): str(path)
            for name, path in dict(primitive_checkpoint_paths or {}).items()
        }
        self.goal_sequence = self._normalize_goal_sequence(goal_sequence)
        self.goal_scenario_id = str(goal_scenario_id)
        self.goal_depth_norm = float(goal_depth_norm)
        self.goal_dump_target_norm = float(goal_dump_target_norm)
        self.cell_entry_enabled = bool(cell_entry_enabled)
        self.cell_entry_grid = CellGridSpec(**dict(cell_entry_grid or {}))
        self.cell_entry_grid.validate()
        self.cell_entry_planner = CellEntryPlanner(grid=self.cell_entry_grid)
        self.cell_entry_auditor = PlannerDecisionAuditor(
            grid=self.cell_entry_grid,
            low_productivity_payload_gain_kg=(
                cell_entry_low_productivity_payload_gain_kg
            ),
        )
        self.dig_cut_planner_cfg = dict(dig_cut_planner or {})
        self.dig_cut_planner_enabled = bool(
            self.dig_cut_planner_cfg.get("enabled", True)
        )
        self.dig_cut_planner_mode = str(
            self.dig_cut_planner_cfg.get("mode", "conservative_pose")
        )
        self.dig_cut_planner_fallback_mode = str(
            self.dig_cut_planner_cfg.get("fallback_mode", "conservative_pose")
        )
        self.dig_cut_hold_token_until_skill_exit = bool(
            self.dig_cut_planner_cfg.get(
                "hold_token_until_skill_exit",
                self.dig_cut_planner_mode == "operator_prior",
            )
        )
        self.dig_cut_prior_path = str(self.dig_cut_planner_cfg.get("prior_path", ""))
        self.dig_cut_prior = self._load_dig_cut_prior(self.dig_cut_prior_path)
        self.dig_cut_prior_id = str(self.dig_cut_prior.get("prior_id", ""))
        self._validate_dig_cut_planner_config()
        self.scripted_bootstrap_target_qpos = (
            None
            if scripted_bootstrap_target_qpos is None
            else np.asarray(scripted_bootstrap_target_qpos, dtype=np.float32).reshape(
                self.action_dim
            )
        )
        self.scripted_bootstrap_kp = float(scripted_bootstrap_kp)
        self.scripted_bootstrap_kd = float(scripted_bootstrap_kd)
        self.scripted_bootstrap_action_clip = scripted_bootstrap_action_clip
        self.scripted_bootstrap_action_signs = (
            np.ones(self.action_dim, dtype=np.float32)
            if scripted_bootstrap_action_signs is None
            else np.asarray(scripted_bootstrap_action_signs, dtype=np.float32).reshape(
                self.action_dim
            )
        )
        self.scripted_bootstrap_qpos_tolerance = float(scripted_bootstrap_qpos_tolerance)
        self.scripted_bootstrap_qvel_abs_max = float(scripted_bootstrap_qvel_abs_max)
        self.scripted_bootstrap_hold_steps = max(1, int(scripted_bootstrap_hold_steps))
        self.scripted_bootstrap_max_steps = max(1, int(scripted_bootstrap_max_steps))
        self.reset()

    def reset(self) -> None:
        for policy in self._all_policies():
            policy.reset()
        self.boundary_detector.reset()
        self._skill_name = (
            BOOTSTRAP_SKILL_NAME
            if (
                self.bootstrap_end_mode != "disabled"
                and (
                    self.bootstrap_policy is not None
                    or self._scripted_bootstrap_enabled()
                )
            )
            else "dig"
        )
        self._prev_action: np.ndarray | None = None
        self._switch_reason = "reset"
        self._dump_ready_hold_count = 0
        self._dump_done_hold_count = 0
        self._return_step_count = 0
        self._scripted_bootstrap_step_count = 0
        self._scripted_bootstrap_hold_count = 0
        self._scripted_bootstrap_timeout_count = 0
        self._completed_transition_count = 0
        self._transition_timeout_count = 0
        self._cycle_index = 0
        self._dump_start_deposited_mass_kg = 0.0
        self.cell_entry_planner.reset()
        self._cell_entry_goal: CellEntryGoal | None = None
        self._cell_entry_goal_cycle_id = -1
        self._cell_entry_audit: PlannerDecisionAudit | None = None
        self._cell_entry_tokens = np.zeros(CELL_ENTRY_TOKEN_DIM, dtype=np.float32)
        self._cell_entry_token_injected = False
        self._dig_cut_tokens = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        self._dig_cut_token_injected = False
        self._cell_entry_seen_cell_id = -1
        self._cell_entry_trace: list[dict[str, Any]] = []
        self._dig_cut_planned_cycle_id = -1
        self._dig_cut_token_source = "none"
        self._dig_cut_fallback_reason = ""
        self._dig_cut_token_in_prior_p10_p90 = False
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

        if self._skill_name == BOOTSTRAP_SKILL_NAME and self._scripted_bootstrap_enabled():
            action = self._scripted_bootstrap_action(obs)
        else:
            policy = self._active_policy()
            policy_obs = self._policy_obs(obs)
            action = np.asarray(policy.predict(policy_obs), dtype=np.float32).reshape(
                self.action_dim
            )
        self._prev_action = action.copy()

        if self._switch_reason == "return_to_dig_qualified_dig_start":
            transition_completed = True

        self._debug_state = self._make_debug_state(
            transition_timeout=transition_timeout,
            transition_completed=transition_completed,
        )
        return action

    def debug_state(self) -> dict[str, Any]:
        cell_goal = self._cell_entry_goal
        cell_audit = self._cell_entry_audit
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
            "approach_ready_hold_count": int(
                self._debug_state.approach_ready_hold_count
            ),
            "dump_release_ready_hold_count": int(
                self._debug_state.dump_release_ready_hold_count
            ),
            "primitive_cycle_index": int(self._debug_state.primitive_cycle_index),
            "primitive_goal_curr_sector_id": int(self._goal_sector_id(self._cycle_index)),
            "primitive_goal_next_sector_id": int(self._next_goal_sector_id()),
            "cell_entry_enabled": bool(self.cell_entry_enabled),
            "cell_entry_token_injected": bool(self._cell_entry_token_injected),
            "cell_entry_token_dim": int(CELL_ENTRY_TOKEN_DIM),
            "dig_cut_token_injected": bool(self._dig_cut_token_injected),
            "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_token_source": str(self._dig_cut_token_source),
            "dig_cut_tokens": self._dig_cut_tokens.astype(float).tolist(),
            "token_in_prior_p10_p90": bool(self._dig_cut_token_in_prior_p10_p90),
            "dig_cut_token_in_prior_p10_p90": bool(
                self._dig_cut_token_in_prior_p10_p90
            ),
            "fallback_reason": str(self._dig_cut_fallback_reason),
            "dig_cut_fallback_reason": str(self._dig_cut_fallback_reason),
            "cell_entry_selected_cell_id": int(
                -1 if cell_goal is None else cell_goal.selected_cell_id
            ),
            "cell_entry_selected_long_index": int(
                -1 if cell_goal is None else cell_goal.selected_long_index
            ),
            "cell_entry_selected_short_index": int(
                -1 if cell_goal is None else cell_goal.selected_short_index
            ),
            "cell_entry_planned_entry_x_m": float(
                np.nan if cell_goal is None else cell_goal.planned_entry_x_m
            ),
            "cell_entry_planned_entry_y_m": float(
                np.nan if cell_goal is None else cell_goal.planned_entry_y_m
            ),
            "cell_entry_planned_entry_z_m": float(
                np.nan if cell_goal is None else cell_goal.planned_entry_z_m
            ),
            "cell_entry_planner_ok": bool(
                False if cell_audit is None else cell_audit.planner_ok
            ),
            "cell_entry_audit_reason_code": int(
                -1 if cell_audit is None else cell_audit.reason_code
            ),
            "cell_entry_audit_reason": str(
                "" if cell_audit is None else cell_audit.reason
            ),
            "cell_entry_audit_risk_flags": int(
                0 if cell_audit is None else cell_audit.risk_flags
            ),
            "cell_entry_inside_entry_envelope": bool(
                False if cell_audit is None else cell_audit.inside_entry_envelope
            ),
            "cell_entry_distance_to_entry_envelope_m": float(
                np.nan
                if cell_audit is None
                else cell_audit.distance_to_entry_envelope_m
            ),
            "cell_entry_seen_cell_id": int(self._cell_entry_seen_cell_id),
            "scripted_bootstrap_step_count": int(self._scripted_bootstrap_step_count),
            "scripted_bootstrap_hold_count": int(self._scripted_bootstrap_hold_count),
            "scripted_bootstrap_timeout_count": int(
                self._scripted_bootstrap_timeout_count
            ),
        }

    def rollout_summary(self) -> dict[str, float | int | str | list[str]]:
        return {
            "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
            "transition_fallback_count": 0,
            "transition_fallback_reason": "",
            "transition_timeout_count": int(self._transition_timeout_count),
            "completed_transition_count": int(self._completed_transition_count),
            "dump_done_use_boundary_event": int(self.dump_done_use_boundary_event),
            "primitive_final_skill": str(self._skill_name),
            "primitive_cycle_index": int(self._cycle_index),
            "cell_entry_enabled": int(self.cell_entry_enabled),
            "cell_entry_trace_count": int(len(self._cell_entry_trace)),
            "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
            "dig_cut_token_injected": int(self._dig_cut_token_injected),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_token_source": str(self._dig_cut_token_source),
            "dig_cut_token_in_prior_p10_p90": int(
                self._dig_cut_token_in_prior_p10_p90
            ),
            "dig_cut_fallback_reason": str(self._dig_cut_fallback_reason),
            "scripted_bootstrap_timeout_count": int(
                self._scripted_bootstrap_timeout_count
            ),
        }

    def planner_trace(self) -> dict[str, object]:
        return {
            "cell_entry_trace": list(self._cell_entry_trace),
            "dig_cut_token_contract": (
                "entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,length,depth,payload,valid"
            ),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_prior_path": str(self.dig_cut_prior_path),
        }

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self._should_end_bootstrap(obs=obs, boundary_event=boundary_event):
                next_skill = (
                    "dig"
                    if self.bootstrap_end_mode
                    in {"first_qualified_dig_start", "scripted_qpos"}
                    else "carry"
                )
                self._set_skill(next_skill, f"bootstrap_to_{next_skill}")
            return

        if self._skill_name == "dig":
            if self._dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
                self._complete_cell_entry_dig(obs)
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
            if (
                self.dump_done_use_boundary_event
                and boundary_event is not None
                and bool(getattr(boundary_event, "dump_end", False))
            ):
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
        if skill_name != "dig":
            self._clear_dig_cut_plan()

    def _should_end_bootstrap(self, *, obs: dict, boundary_event: Any | None) -> bool:
        if self._scripted_bootstrap_enabled():
            if self._scripted_bootstrap_target_reached(obs):
                return True
            if self._scripted_bootstrap_step_count >= self.scripted_bootstrap_max_steps:
                self._scripted_bootstrap_timeout_count += 1
                return True
            return False
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

    def _scripted_bootstrap_enabled(self) -> bool:
        return bool(
            self.bootstrap_end_mode == "scripted_qpos"
            and self.scripted_bootstrap_target_qpos is not None
        )

    def _scripted_bootstrap_target_reached(self, obs: dict) -> bool:
        if self.scripted_bootstrap_target_qpos is None:
            return False
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        qvel = np.asarray(
            obs.get("qvel", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        qpos_close = bool(
            np.all(np.abs(qpos - self.scripted_bootstrap_target_qpos) <= self.scripted_bootstrap_qpos_tolerance)
        )
        qvel_small = bool(np.all(np.abs(qvel) <= self.scripted_bootstrap_qvel_abs_max))
        if qpos_close and qvel_small:
            self._scripted_bootstrap_hold_count += 1
        else:
            self._scripted_bootstrap_hold_count = 0
        return bool(self._scripted_bootstrap_hold_count >= self.scripted_bootstrap_hold_steps)

    def _scripted_bootstrap_action(self, obs: dict) -> np.ndarray:
        if self.scripted_bootstrap_target_qpos is None:
            raise RuntimeError("scripted bootstrap is active without target qpos.")
        self._scripted_bootstrap_step_count += 1
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        qvel = np.asarray(
            obs.get("qvel", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        return _pd_servo_action(
            qpos=qpos,
            qvel=qvel,
            target_qpos=self.scripted_bootstrap_target_qpos,
            kp=self.scripted_bootstrap_kp,
            kd=self.scripted_bootstrap_kd,
            action_clip=self.scripted_bootstrap_action_clip,
            action_signs=self.scripted_bootstrap_action_signs,
        )

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
        dump_area_relative_ok = self._dump_area_relative_dump_position_ok(geometry)
        position_ok = self._dump_ready_position_ok(
            over_footprint=over_footprint,
            dump_area_relative_ok=dump_area_relative_ok,
            horizontal_ok=horizontal_ok,
        )
        return bool(
            height_ok
            and position_ok
            and (clearance_ok or not self.dump_ready_require_clearance)
        )

    def _dump_area_relative_dump_position_ok(self, geometry: dict[str, float]) -> bool:
        if self.dump_ready_max_dump_area_footprint_outside_distance_m is None:
            return False
        outside_distance = float(
            geometry.get("bucket_dump_area_footprint_outside_distance_m", np.nan)
        )
        outside_ok = bool(
            np.isfinite(outside_distance)
            and outside_distance >= 0.0
            and outside_distance
            <= self.dump_ready_max_dump_area_footprint_outside_distance_m + 1.0e-6
        )
        if not outside_ok:
            return False
        return bool(
            self._optional_range_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_x_m",
                min_value=self.dump_ready_min_dump_area_relative_x_m,
                max_value=self.dump_ready_max_dump_area_relative_x_m,
            )
            and self._optional_range_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_z_m",
                min_value=self.dump_ready_min_dump_area_relative_z_m,
                max_value=self.dump_ready_max_dump_area_relative_z_m,
            )
        )

    @staticmethod
    def _optional_range_ok(
        *,
        geometry: dict[str, float],
        name: str,
        min_value: float | None,
        max_value: float | None,
    ) -> bool:
        if min_value is None and max_value is None:
            return True
        value = float(geometry.get(name, np.nan))
        if not np.isfinite(value):
            return False
        if min_value is not None and value < min_value - 1.0e-6:
            return False
        if max_value is not None and value > max_value + 1.0e-6:
            return False
        return True

    def _dump_ready_position_ok(
        self,
        *,
        over_footprint: bool,
        dump_area_relative_ok: bool,
        horizontal_ok: bool,
    ) -> bool:
        # `dump_ready_require_over_footprint=False` relaxes the footprint mask
        # only; it must not disable the selected target-relative position rule.
        mode = self.dump_ready_position_mode
        if mode == "footprint_or_dump_area_relative":
            return bool(
                dump_area_relative_ok
                or (over_footprint and self.dump_ready_require_over_footprint)
            )
        if mode == "dump_area_relative":
            return bool(dump_area_relative_ok)
        if mode == "footprint":
            return bool(over_footprint or not self.dump_ready_require_over_footprint)
        if mode == "footprint_or_horizontal":
            return bool(
                horizontal_ok
                or (over_footprint and self.dump_ready_require_over_footprint)
            )
        raise ValueError(
            f"Unsupported dump_ready_position_mode {mode!r}. Expected one of "
            "footprint_or_dump_area_relative, dump_area_relative, footprint, "
            "footprint_or_horizontal."
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

        def _optional_metric(name: str, index: int) -> float:
            if name in task_metrics:
                value = float(task_metrics[name])
                return value if np.isfinite(value) else float("nan")
            env_state = self._env_state(obs)
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
            "bucket_dump_area_relative_x_m": _optional_metric(
                "bucket_dump_area_relative_x_m",
                ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
            ),
            "bucket_dump_area_relative_z_m": _optional_metric(
                "bucket_dump_area_relative_z_m",
                ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
            ),
            "bucket_dump_area_footprint_outside_distance_m": _optional_metric(
                "bucket_dump_area_footprint_outside_distance_m",
                ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
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

    def _policy_obs(self, obs: dict) -> dict:
        self._cell_entry_token_injected = False
        self._dig_cut_token_injected = False
        goal_tokens = self._goal_tokens()
        cell_entry_tokens = self._cell_entry_tokens_for_obs(obs)
        dig_cut_tokens = self._dig_cut_tokens_for_obs(obs)
        if goal_tokens is None and cell_entry_tokens is None and dig_cut_tokens is None:
            return obs
        policy_obs = dict(obs)
        if goal_tokens is not None:
            policy_obs["goal_tokens"] = goal_tokens
        if cell_entry_tokens is not None:
            policy_obs["cell_entry_tokens"] = cell_entry_tokens
            self._cell_entry_token_injected = True
        if dig_cut_tokens is not None:
            policy_obs["dig_cut_tokens"] = dig_cut_tokens
            self._dig_cut_token_injected = True
        return policy_obs

    def _dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "dig" or not self.dig_cut_planner_enabled:
            return None
        if (
            self.dig_cut_hold_token_until_skill_exit
            and self._dig_cut_planned_cycle_id == int(self._cycle_index)
        ):
            return self._dig_cut_tokens.copy()
        self._dig_cut_tokens = self._build_dig_cut_tokens_for_obs(obs)
        self._dig_cut_planned_cycle_id = int(self._cycle_index)
        return self._dig_cut_tokens.copy()

    def _build_dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray:
        self._dig_cut_fallback_reason = ""
        if self.dig_cut_planner_mode == "conservative_pose":
            self._dig_cut_token_source = "conservative_pose"
            token = build_live_dig_cut_tokens_from_pose(self._bucket_dig_area_pose(obs))
            self._dig_cut_token_in_prior_p10_p90 = False
            return token
        if self.dig_cut_planner_mode == "operator_prior":
            try:
                token, raw_fields, source, fallback_reason = (
                    self._build_operator_prior_dig_cut_tokens(obs)
                )
                self._dig_cut_token_source = source
                self._dig_cut_fallback_reason = fallback_reason
                self._dig_cut_token_in_prior_p10_p90 = self._raw_fields_in_prior_range(
                    raw_fields
                )
                return token
            except Exception as exc:
                if self.dig_cut_planner_fallback_mode != "conservative_pose":
                    raise
                self._dig_cut_token_source = "fallback_conservative_pose"
                self._dig_cut_fallback_reason = str(exc)
                token = build_live_dig_cut_tokens_from_pose(
                    self._bucket_dig_area_pose(obs)
                )
                self._dig_cut_token_in_prior_p10_p90 = False
                return token
        raise ValueError(f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}.")

    def _build_operator_prior_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        if not self.dig_cut_prior:
            raise ValueError("operator_prior mode requires a dig cut prior JSON.")
        fields = dict(self.dig_cut_prior.get("fields", {}))
        pose = self._bucket_dig_area_pose(obs)
        fallback_reason = ""
        if pose is None:
            entry_x = self._prior_percentile(fields, "entry_x_m", "p50")
            entry_y = 0.0
            entry_z = self._prior_percentile(fields, "entry_z_m", "p50")
            source = "operator_prior_median_pose_fallback"
            fallback_reason = "missing_bucket_dig_area_pose"
        else:
            entry_x = self._clamp_to_prior(fields, "entry_x_m", float(pose[0]))
            entry_y = float(pose[1])
            entry_z = self._clamp_to_prior(fields, "entry_z_m", float(pose[2]))
            source = "operator_prior_pose_clamped"

        dir_x = self._prior_percentile(fields, "cut_direction_x", "p50")
        dir_z = self._prior_percentile(fields, "cut_direction_z", "p50")
        norm = float(np.hypot(dir_x, dir_z))
        if norm <= 1.0e-6:
            dir_x, dir_z = -1.0, 0.0
        else:
            dir_x, dir_z = dir_x / norm, dir_z / norm
        length = self._prior_percentile(fields, "cut_length_m", "p50")
        exit_x = self._clamp_to_prior(fields, "exit_x_m", entry_x + dir_x * length)
        exit_z = self._clamp_to_prior(fields, "exit_z_m", entry_z + dir_z * length)

        delta_x = exit_x - entry_x
        delta_z = exit_z - entry_z
        generated_length = float(np.hypot(delta_x, delta_z))
        if generated_length > 1.0e-6:
            dir_x = delta_x / generated_length
            dir_z = delta_z / generated_length
            length = generated_length

        raw_fields = {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": float(entry_y),
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": float(entry_y),
            "operator_exit_z_m": float(exit_z),
            "operator_cut_direction_x": float(
                self._clamp_to_prior(fields, "cut_direction_x", dir_x)
            ),
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": float(
                self._clamp_to_prior(fields, "cut_direction_z", dir_z)
            ),
            "operator_cut_length_m": float(
                self._clamp_to_prior(fields, "cut_length_m", length)
            ),
            "operator_cut_depth_peak_m": float(
                self._prior_percentile(fields, "cut_depth_peak_m", "p50")
            ),
            "operator_cut_payload_gain_kg": float(
                self._prior_percentile(fields, "payload_gain_kg", "p50")
            ),
            "operator_cut_valid": 1,
        }
        return _build_dig_cut_token(raw_fields), raw_fields, source, fallback_reason

    def _clear_dig_cut_plan(self) -> None:
        self._dig_cut_planned_cycle_id = -1
        self._dig_cut_tokens = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        self._dig_cut_token_source = "none"
        self._dig_cut_fallback_reason = ""
        self._dig_cut_token_in_prior_p10_p90 = False

    def _validate_dig_cut_planner_config(self) -> None:
        if not self.dig_cut_planner_enabled:
            return
        supported_modes = {"conservative_pose", "operator_prior"}
        if self.dig_cut_planner_mode not in supported_modes:
            raise ValueError(
                f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}; "
                f"expected one of {sorted(supported_modes)}."
            )
        if (
            self.dig_cut_planner_mode == "operator_prior"
            and not self.dig_cut_prior_path
        ):
            raise ValueError("operator_prior dig_cut_planner requires prior_path.")

    @staticmethod
    def _load_dig_cut_prior(path: str) -> dict[str, Any]:
        if not path:
            return {}
        prior_path = Path(path).expanduser()
        if not prior_path.is_absolute():
            prior_path = Path.cwd() / prior_path
        with prior_path.open("r", encoding="utf-8") as handle:
            prior = json.load(handle)
        if int(len(prior.get("token_order", []))) != DIG_CUT_TOKEN_DIM:
            raise ValueError(
                f"dig cut prior {prior_path} has invalid token_order length."
            )
        return dict(prior)

    @staticmethod
    def _prior_percentile(
        fields: dict[str, Any], field_name: str, percentile: str
    ) -> float:
        try:
            return float(fields[field_name][percentile])
        except KeyError as exc:
            raise KeyError(f"Missing prior field {field_name}.{percentile}") from exc

    def _clamp_to_prior(
        self, fields: dict[str, Any], field_name: str, value: float
    ) -> float:
        lo = self._prior_percentile(fields, field_name, "p10")
        hi = self._prior_percentile(fields, field_name, "p90")
        return float(np.clip(float(value), lo, hi))

    def _raw_fields_in_prior_range(self, raw_fields: dict[str, float | int]) -> bool:
        if not self.dig_cut_prior:
            return False
        fields = dict(self.dig_cut_prior.get("fields", {}))
        mapping = {
            "operator_entry_x_m": "entry_x_m",
            "operator_entry_z_m": "entry_z_m",
            "operator_exit_x_m": "exit_x_m",
            "operator_exit_z_m": "exit_z_m",
            "operator_cut_direction_x": "cut_direction_x",
            "operator_cut_direction_z": "cut_direction_z",
            "operator_cut_length_m": "cut_length_m",
            "operator_cut_depth_peak_m": "cut_depth_peak_m",
            "operator_cut_payload_gain_kg": "payload_gain_kg",
        }
        for raw_name, prior_name in mapping.items():
            value = float(raw_fields.get(raw_name, np.nan))
            lo = self._prior_percentile(fields, prior_name, "p10")
            hi = self._prior_percentile(fields, prior_name, "p90")
            if not np.isfinite(value) or value < lo - 1.0e-6 or value > hi + 1.0e-6:
                return False
        return True

    def _cell_entry_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if not self.cell_entry_enabled or self._skill_name != "dig":
            return None
        if (
            self._cell_entry_goal is None
            or self._cell_entry_goal_cycle_id != int(self._cycle_index)
        ):
            self._cell_entry_goal = self.cell_entry_planner.plan(
                cycle_id=int(self._cycle_index)
            )
            self._cell_entry_goal_cycle_id = int(self._cycle_index)
            self._cell_entry_seen_cell_id = -1

        cell_id = self._dig_cell_id(obs)
        if cell_id >= 0 and self._cell_entry_seen_cell_id < 0:
            self._cell_entry_seen_cell_id = int(cell_id)
        outcome = PrimitiveCycleOutcome(
            cycle_id=int(self._cycle_index),
            actual_start_step=-1,
            actual_bite_step=-1,
            actual_removal_step=-1,
            actual_start_cell_id=int(cell_id),
            actual_bite_cell_id=int(cell_id),
            actual_removal_cell_id=int(cell_id),
            payload_gain_kg=float(self.cell_entry_auditor.low_productivity_payload_gain_kg),
            deposit_delta_kg=0.0,
            collision_count_delta=0,
            return_miss=False,
        )
        self._cell_entry_audit = self.cell_entry_auditor.audit(
            goal=self._cell_entry_goal,
            outcome=outcome,
            current_bucket_pose=self._bucket_dig_area_pose(obs),
            geometry_available=self._dig_area_geometry_available(obs),
        )
        self._cell_entry_tokens = build_cell_entry_tokens(
            grid=self.cell_entry_grid,
            goal=self._cell_entry_goal,
            audit=self._cell_entry_audit,
        )
        return self._cell_entry_tokens.copy()

    def _complete_cell_entry_dig(self, obs: dict) -> None:
        if not self.cell_entry_enabled or self._cell_entry_goal is None:
            return
        cell_id = self._dig_cell_id(obs)
        if cell_id < 0:
            cell_id = int(self._cell_entry_seen_cell_id)
        outcome = PrimitiveCycleOutcome(
            cycle_id=int(self._cycle_index),
            actual_start_step=-1,
            actual_bite_step=-1,
            actual_removal_step=-1,
            actual_start_cell_id=int(cell_id),
            actual_bite_cell_id=int(cell_id),
            actual_removal_cell_id=int(cell_id),
            payload_gain_kg=float(self._mass_in_bucket(obs)),
            deposit_delta_kg=0.0,
            collision_count_delta=0,
            return_miss=False,
        )
        self.cell_entry_planner.update(outcome)
        self._cell_entry_trace.append(
            {
                "cycle_id": int(self._cycle_index),
                "selected_cell_id": int(self._cell_entry_goal.selected_cell_id),
                "actual_cell_id": int(cell_id),
                "payload_gain_kg": float(outcome.payload_gain_kg),
                "audit_reason_code": int(
                    -1
                    if self._cell_entry_audit is None
                    else self._cell_entry_audit.reason_code
                ),
                "audit_reason": str(
                    ""
                    if self._cell_entry_audit is None
                    else self._cell_entry_audit.reason
                ),
            }
        )

    def _dig_area_geometry_available(self, obs: dict) -> bool:
        env_state = self._env_state(obs)
        return bool(
            len(env_state) > ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX
            and float(env_state[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX]) > 0.5
        )

    def _dig_cell_id(self, obs: dict) -> int:
        env_state = self._env_state(obs)
        if len(env_state) <= ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
            return -1
        value = float(env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX])
        if not np.isfinite(value):
            return -1
        return int(round(value))

    def _bucket_dig_area_pose(self, obs: dict) -> tuple[float, float, float] | None:
        env_state = self._env_state(obs)
        if len(env_state) <= ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX:
            return None
        values = (
            float(env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX]),
            float(env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX]),
            float(env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX]),
        )
        if not all(np.isfinite(value) for value in values):
            return None
        return values

    def _goal_tokens(self) -> np.ndarray | None:
        if not self.goal_sequence:
            return None
        curr_sector_id = self._goal_sector_id(self._cycle_index)
        next_sector_id = self._next_goal_sector_id()
        return build_goal_tokens(
            self.goal_scenario_id,
            curr_sector_id=curr_sector_id,
            curr_cut_depth_norm=self.goal_depth_norm,
            next_sector_id=next_sector_id,
            next_cut_depth_norm=self.goal_depth_norm,
            dst_target_norm=self.goal_dump_target_norm,
            has_lookahead=next_sector_id >= 0,
        )

    def _goal_sector_id(self, cycle_index: int) -> int:
        if not self.goal_sequence:
            return -1
        index = max(0, min(int(cycle_index), len(self.goal_sequence) - 1))
        return int(self.goal_sequence[index])

    def _next_goal_sector_id(self) -> int:
        if not self.goal_sequence:
            return -1
        next_index = int(self._cycle_index) + 1
        if next_index >= len(self.goal_sequence):
            return -1
        return int(self.goal_sequence[next_index])

    @staticmethod
    def _normalize_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | None,
    ) -> tuple[int, ...]:
        if not goal_sequence:
            return ()
        normalized: list[int] = []
        for item in goal_sequence:
            if isinstance(item, str):
                key = item.strip().lower()
                if key not in PRIMITIVE_GOAL_SECTOR_IDS:
                    raise ValueError(
                        f"Unknown primitive goal sector {item!r}. Expected left, mid, or right."
                    )
                normalized.append(PRIMITIVE_GOAL_SECTOR_IDS[key])
            else:
                value = int(item)
                if value < 0 or value > 2:
                    raise ValueError(
                        f"Primitive goal sector id must be 0, 1, or 2, got {item!r}."
                    )
                normalized.append(value)
        return tuple(normalized)

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


def _pd_servo_action(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    target_qpos: np.ndarray,
    kp: float,
    kd: float,
    action_clip: float | np.ndarray | list[float] | tuple[float, ...],
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None = None,
) -> np.ndarray:
    action = float(kp) * (target_qpos - qpos) - float(kd) * qvel
    if action_signs is not None:
        action = np.asarray(action_signs, dtype=np.float32).reshape(action.shape) * action
    action_clip_arr = np.asarray(action_clip, dtype=np.float32)
    if action_clip_arr.ndim == 0:
        action_clip_arr = np.full_like(action, float(action_clip_arr))
    return np.clip(action, -action_clip_arr, action_clip_arr).astype(np.float32)


@register_policy("primitive_planner_act_5p")
class PrimitivePlannerACT5PPolicy(PrimitivePlannerACTPolicy):
    """Scripted V2.2 planner over dig/carry/approach_dump/dump_release/return.

    The upper model should provide low-frequency task intent only. This planner
    owns high-frequency primitive boundary decisions from relative geometry,
    bucket mass, clearance, and V2.1 boundary events.
    """

    def __init__(
        self,
        *,
        dig_policy: Policy,
        carry_policy: Policy,
        approach_dump_policy: Policy,
        dump_release_policy: Policy,
        return_policy: Policy,
        boundary_detector: BoundaryDetector,
        bootstrap_policy: Policy | None = None,
        bootstrap_end_mode: str = "disabled",
        bootstrap_end_min_bucket_mass_kg: float = 300.0,
        bootstrap_end_min_distance_to_dig_area_m: float = 0.25,
        dig_to_carry_min_bucket_mass_kg: float = 300.0,
        dig_to_carry_min_distance_to_dig_area_m: float = 0.0,
        approach_ready_min_bucket_mass_kg: float = 150.0,
        approach_ready_max_horizontal_distance_m: float | None = 1.25,
        approach_ready_min_height_above_rim_m: float = -0.20,
        approach_ready_require_clearance: bool = True,
        approach_ready_hold_steps: int = 3,
        dump_release_ready_min_bucket_mass_kg: float = 150.0,
        dump_release_ready_min_height_above_rim_m: float = 0.45,
        dump_release_ready_require_over_footprint: bool = True,
        dump_release_ready_require_clearance: bool = True,
        dump_release_ready_max_horizontal_distance_m: float | None = 0.60,
        dump_release_ready_position_mode: str = "footprint_or_dump_area_relative",
        dump_release_ready_max_dump_area_footprint_outside_distance_m: float | None = 0.05,
        dump_release_ready_min_dump_area_relative_x_m: float | None = None,
        dump_release_ready_max_dump_area_relative_x_m: float | None = None,
        dump_release_ready_min_dump_area_relative_z_m: float | None = None,
        dump_release_ready_max_dump_area_relative_z_m: float | None = None,
        dump_release_ready_hold_steps: int = 3,
        dump_done_max_bucket_mass_kg: float = 100.0,
        dump_done_min_deposit_delta_kg: float = 10.0,
        dump_done_hold_steps: int = 30,
        dump_done_use_boundary_event: bool = True,
        return_max_steps: int = 420,
        action_dim: int = 4,
        primitive_checkpoint_paths: dict[str, str] | None = None,
        goal_sequence: list[str] | tuple[str, ...] | None = None,
        goal_scenario_id: str = "s0_truck",
        goal_depth_norm: float = 1.0,
        goal_dump_target_norm: float = 1.0,
        cell_entry_enabled: bool = False,
        cell_entry_grid: dict[str, Any] | None = None,
        cell_entry_low_productivity_payload_gain_kg: float = 100.0,
        dig_cut_planner: dict[str, Any] | None = None,
    ) -> None:
        self.approach_dump_policy = approach_dump_policy
        self.dump_release_policy = dump_release_policy
        self.approach_ready_min_bucket_mass_kg = float(approach_ready_min_bucket_mass_kg)
        self.approach_ready_max_horizontal_distance_m = (
            None
            if approach_ready_max_horizontal_distance_m is None
            else float(approach_ready_max_horizontal_distance_m)
        )
        self.approach_ready_min_height_above_rim_m = float(
            approach_ready_min_height_above_rim_m
        )
        self.approach_ready_require_clearance = bool(approach_ready_require_clearance)
        self.approach_ready_hold_steps = max(1, int(approach_ready_hold_steps))
        self._approach_ready_hold_count = 0
        self._dump_release_ready_hold_count = 0
        super().__init__(
            dig_policy=dig_policy,
            carry_policy=carry_policy,
            dump_policy=dump_release_policy,
            return_policy=return_policy,
            boundary_detector=boundary_detector,
            bootstrap_policy=bootstrap_policy,
            bootstrap_end_mode=bootstrap_end_mode,
            bootstrap_end_min_bucket_mass_kg=bootstrap_end_min_bucket_mass_kg,
            bootstrap_end_min_distance_to_dig_area_m=(
                bootstrap_end_min_distance_to_dig_area_m
            ),
            dig_to_carry_min_bucket_mass_kg=dig_to_carry_min_bucket_mass_kg,
            dig_to_carry_min_distance_to_dig_area_m=(
                dig_to_carry_min_distance_to_dig_area_m
            ),
            dump_ready_min_bucket_mass_kg=dump_release_ready_min_bucket_mass_kg,
            dump_ready_min_height_above_rim_m=(
                dump_release_ready_min_height_above_rim_m
            ),
            dump_ready_require_over_footprint=(
                dump_release_ready_require_over_footprint
            ),
            dump_ready_require_clearance=dump_release_ready_require_clearance,
            dump_ready_max_horizontal_distance_m=(
                dump_release_ready_max_horizontal_distance_m
            ),
            dump_ready_position_mode=dump_release_ready_position_mode,
            dump_ready_max_dump_area_footprint_outside_distance_m=(
                dump_release_ready_max_dump_area_footprint_outside_distance_m
            ),
            dump_ready_min_dump_area_relative_x_m=(
                dump_release_ready_min_dump_area_relative_x_m
            ),
            dump_ready_max_dump_area_relative_x_m=(
                dump_release_ready_max_dump_area_relative_x_m
            ),
            dump_ready_min_dump_area_relative_z_m=(
                dump_release_ready_min_dump_area_relative_z_m
            ),
            dump_ready_max_dump_area_relative_z_m=(
                dump_release_ready_max_dump_area_relative_z_m
            ),
            dump_ready_hold_steps=dump_release_ready_hold_steps,
            dump_done_max_bucket_mass_kg=dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=dump_done_min_deposit_delta_kg,
            dump_done_hold_steps=dump_done_hold_steps,
            dump_done_use_boundary_event=dump_done_use_boundary_event,
            return_max_steps=return_max_steps,
            action_dim=action_dim,
            primitive_checkpoint_paths=primitive_checkpoint_paths,
            goal_sequence=goal_sequence,
            goal_scenario_id=goal_scenario_id,
            goal_depth_norm=goal_depth_norm,
            goal_dump_target_norm=goal_dump_target_norm,
            cell_entry_enabled=cell_entry_enabled,
            cell_entry_grid=cell_entry_grid,
            cell_entry_low_productivity_payload_gain_kg=(
                cell_entry_low_productivity_payload_gain_kg
            ),
            dig_cut_planner=dig_cut_planner,
        )
        self.dump_release_ready_hold_steps = self.dump_ready_hold_steps

    def reset(self) -> None:
        self._approach_ready_hold_count = 0
        self._dump_release_ready_hold_count = 0
        super().reset()
        self._approach_ready_hold_count = 0
        self._dump_release_ready_hold_count = 0
        self._debug_state = self._make_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self._should_end_bootstrap(obs=obs, boundary_event=boundary_event):
                next_skill = (
                    "dig"
                    if self.bootstrap_end_mode
                    in {"first_qualified_dig_start", "scripted_qpos"}
                    else "carry"
                )
                self._set_skill(next_skill, f"bootstrap_to_{next_skill}")
            return

        if self._skill_name == "dig":
            if self._dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
                self._set_skill("carry", "dig_to_carry_loaded")
            return

        if self._skill_name == "carry":
            if self._approach_ready(obs):
                self._approach_ready_hold_count += 1
            else:
                self._approach_ready_hold_count = 0
            if self._approach_ready_hold_count >= self.approach_ready_hold_steps:
                self._set_skill("approach_dump", "carry_to_approach_dump_region_ready")
            return

        if self._skill_name == "approach_dump":
            if self._dump_ready(obs):
                self._dump_release_ready_hold_count += 1
            else:
                self._dump_release_ready_hold_count = 0
            if self._dump_release_ready_hold_count >= self.dump_ready_hold_steps:
                self._dump_start_deposited_mass_kg = self._deposited_mass(obs)
                self._set_skill("dump_release", "approach_dump_to_dump_release_ready")
            return

        if self._skill_name == "dump_release":
            if (
                self.dump_done_use_boundary_event
                and boundary_event is not None
                and bool(getattr(boundary_event, "dump_end", False))
            ):
                self._set_skill("return", "dump_release_to_return_dump_end")
                return
            if self._dump_done(obs):
                self._dump_done_hold_count += 1
            else:
                self._dump_done_hold_count = 0
            if self._dump_done_hold_count >= self.dump_done_hold_steps:
                self._set_skill("return", "dump_release_to_return_mass_low")
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
            self._approach_ready_hold_count = 0
        elif skill_name == "approach_dump":
            self._dump_release_ready_hold_count = 0
        elif skill_name == "dump_release":
            self._dump_done_hold_count = 0
        elif skill_name == "return":
            self._return_step_count = 0
        elif skill_name == "dig":
            self._approach_ready_hold_count = 0
            self._dump_release_ready_hold_count = 0
            self._dump_done_hold_count = 0
        if skill_name != "dig":
            self._clear_dig_cut_plan()

    def _approach_ready(self, obs: dict) -> bool:
        if self._mass_in_bucket(obs) < self.approach_ready_min_bucket_mass_kg:
            return False
        geometry = self._target_geometry(obs)
        horizontal_ok = True
        if self.approach_ready_max_horizontal_distance_m is not None:
            horizontal_ok = (
                geometry["target_horizontal_distance_m"]
                <= self.approach_ready_max_horizontal_distance_m + 1.0e-6
            )
        height_ok = (
            geometry["bucket_height_above_target_rim_m"]
            >= self.approach_ready_min_height_above_rim_m - 1.0e-6
        )
        clearance_ok = geometry["dump_clearance_ok_mask"] > 0.5
        return bool(
            horizontal_ok
            and height_ok
            and (clearance_ok or not self.approach_ready_require_clearance)
        )

    def _active_policy(self) -> Policy:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self.bootstrap_policy is None:
                raise RuntimeError("bootstrap skill is active but bootstrap_policy is None.")
            return self.bootstrap_policy
        if self._skill_name == "dig":
            return self.dig_policy
        if self._skill_name == "carry":
            return self.carry_policy
        if self._skill_name == "approach_dump":
            return self.approach_dump_policy
        if self._skill_name == "dump_release":
            return self.dump_release_policy
        if self._skill_name == "return":
            return self.return_policy
        raise RuntimeError(f"Unknown primitive skill {self._skill_name!r}.")

    def _all_policies(self) -> list[Policy]:
        policies = [
            self.dig_policy,
            self.carry_policy,
            self.approach_dump_policy,
            self.dump_release_policy,
            self.return_policy,
        ]
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
        skill_id = PRIMITIVE_SKILL_IDS_5P.get(skill_name, -1)
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
            dump_ready_hold_count=int(self._dump_release_ready_hold_count),
            dump_done_hold_count=int(self._dump_done_hold_count),
            primitive_cycle_index=int(self._cycle_index),
            approach_ready_hold_count=int(self._approach_ready_hold_count),
            dump_release_ready_hold_count=int(self._dump_release_ready_hold_count),
        )
