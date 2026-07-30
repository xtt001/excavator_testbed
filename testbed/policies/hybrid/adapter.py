"""Hybrid deploy wrapper: ACT for work, scripted servo for transition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_CONTACT_MAX_NORMAL_FORCE_N_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.boundary_detector import BoundaryDetector
from testbed.planner.corridor_servo import (
    TRANSITION_SUBMODE_WAIT_NEXT_DIG,
    TransitionController,
)
from testbed.planner.fixed_sequence_planner import FixedSequencePlanner
from testbed.planner.rule_planner import RuleTaskPlanner
from testbed.planner.types import CycleSummary, PlannerGoal, sector_name_from_id
from testbed.policies.base import Policy, register_policy

HYBRID_MODE_WORK = "WORK"
HYBRID_MODE_TRANSITION = "TRANSITION"
TRANSITION_SOURCE_SCRIPTED_BAND_SERVO = "scripted_band_servo"
TRANSITION_SOURCE_LEARNED_WAIT_NEXT_DIG_POLICY = "learned_wait_next_dig_policy"
TRANSITION_POLICY_MODE_SCRIPTED = "scripted"
TRANSITION_POLICY_MODE_LEARNED = "learned"
TRANSITION_POLICY_MODE_LEARNED_FALLBACK_TO_SCRIPTED = "learned_fallback_to_scripted"
BOOTSTRAP_END_MODE_FIRST_QUALIFIED_DIG_START = "first_qualified_dig_start"
BOOTSTRAP_END_MODE_LOADED_AND_CLEAR = "loaded_and_clear"


@dataclass(frozen=True)
class HybridDebugState:
    hybrid_mode: str
    transition_submode: str
    planner_cycle_index: int
    planner_curr_sector_id: int
    planner_next_sector_id: int
    planner_current_depth_class: int
    planner_next_depth_class: int
    planner_plan_source: str
    planner_replan_mask: bool
    transition_timeout: bool
    transition_collision_delta: int
    corridor_align_steps: int
    wait_next_dig_steps: int
    transition_completed: bool
    transition_source: str
    transition_policy_mode: str
    transition_fallback_count: int
    transition_fallback_reason: str
    work_target_guard_active: bool
    work_target_guard_count: int


@dataclass
class _ActiveCycleRuntime:
    cycle_id: int
    start_step: int
    current_goal: PlannerGoal | None
    next_goal: PlannerGoal | None
    deposited_mass_start: float
    collision_count_start: int
    fill_peak_kg: float
    peak_bucket_depth_m: float
    target_contact_max_force_n: float
    qualified_dig: bool


@register_policy("hybrid_planner_act")
class HybridPlannerACTPolicy(Policy):
    """Stage-2/4 hybrid deploy wrapper."""

    def __init__(
        self,
        *,
        work_policy: Policy,
        transition_policy: Policy | None = None,
        bootstrap_policy: Policy | None = None,
        bootstrap_end_mode: str = BOOTSTRAP_END_MODE_FIRST_QUALIFIED_DIG_START,
        bootstrap_end_min_bucket_mass_kg: float = 300.0,
        bootstrap_end_min_distance_to_dig_area_m: float = 0.25,
        transition_enable_fallback: bool = False,
        transition_fallback_local_budget_steps: int = 180,
        transition_fallback_no_progress_steps: int = 120,
        transition_fallback_progress_mass_kg: float = 40.0,
        transition_fallback_progress_distance_to_dig_area_m: float = 0.05,
        transition_fallback_progress_bucket_depth_m: float = 0.02,
        work_target_guard_enabled: bool = False,
        work_target_guard_distance_m: float = 0.45,
        work_target_guard_min_bucket_mass_kg: float = 300.0,
        work_target_guard_bucket_action_floor: float = -0.15,
        work_target_guard_boom_action_min: float = 0.08,
        work_target_guard_approach_distance_m: float | None = None,
        work_target_guard_approach_bucket_action_floor: float | None = None,
        work_target_guard_approach_boom_action_min: float | None = None,
        planner: FixedSequencePlanner | RuleTaskPlanner,
        transition_controller: TransitionController,
        boundary_detector: BoundaryDetector,
        action_dim: int = 4,
        scenario_id: str | None = None,
    ) -> None:
        self.work_policy = work_policy
        self.transition_policy = transition_policy
        self.bootstrap_policy = bootstrap_policy
        self.bootstrap_end_mode = str(bootstrap_end_mode)
        self.bootstrap_end_min_bucket_mass_kg = float(bootstrap_end_min_bucket_mass_kg)
        self.bootstrap_end_min_distance_to_dig_area_m = float(
            bootstrap_end_min_distance_to_dig_area_m
        )
        self.transition_enable_fallback = bool(transition_enable_fallback)
        self.transition_fallback_local_budget_steps = int(
            transition_fallback_local_budget_steps
        )
        self.transition_fallback_no_progress_steps = int(
            transition_fallback_no_progress_steps
        )
        self.transition_fallback_progress_mass_kg = float(
            transition_fallback_progress_mass_kg
        )
        self.transition_fallback_progress_distance_to_dig_area_m = float(
            transition_fallback_progress_distance_to_dig_area_m
        )
        self.transition_fallback_progress_bucket_depth_m = float(
            transition_fallback_progress_bucket_depth_m
        )
        self.work_target_guard_enabled = bool(work_target_guard_enabled)
        self.work_target_guard_distance_m = float(work_target_guard_distance_m)
        self.work_target_guard_min_bucket_mass_kg = float(
            work_target_guard_min_bucket_mass_kg
        )
        self.work_target_guard_bucket_action_floor = float(
            work_target_guard_bucket_action_floor
        )
        self.work_target_guard_boom_action_min = float(work_target_guard_boom_action_min)
        self.work_target_guard_approach_distance_m = (
            self.work_target_guard_distance_m
            if work_target_guard_approach_distance_m is None
            else float(work_target_guard_approach_distance_m)
        )
        self.work_target_guard_approach_bucket_action_floor = (
            self.work_target_guard_bucket_action_floor
            if work_target_guard_approach_bucket_action_floor is None
            else float(work_target_guard_approach_bucket_action_floor)
        )
        self.work_target_guard_approach_boom_action_min = (
            self.work_target_guard_boom_action_min
            if work_target_guard_approach_boom_action_min is None
            else float(work_target_guard_approach_boom_action_min)
        )
        self.planner = planner
        self.transition_controller = transition_controller
        self.boundary_detector = boundary_detector
        self.action_dim = int(action_dim)
        self.scenario_id = None if scenario_id in (None, "") else str(scenario_id)
        self.reset()

    def reset(self) -> None:
        self.work_policy.reset()
        if self.transition_policy is not None:
            self.transition_policy.reset()
        if self.bootstrap_policy is not None:
            self.bootstrap_policy.reset()
        self.boundary_detector.reset()
        self.transition_controller.reset()
        self._mode = HYBRID_MODE_WORK
        self._cycle_index = 0
        self._entered_work_window = False
        self._prev_action: np.ndarray | None = None
        self._transition_source = (
            TRANSITION_SOURCE_LEARNED_WAIT_NEXT_DIG_POLICY
            if self.transition_policy is not None
            else TRANSITION_SOURCE_SCRIPTED_BAND_SERVO
        )
        self._transition_timeout_count = 0
        self._completed_transition_count = 0
        self._transition_step_count_total = 0
        self._transition_collision_delta_total = 0
        self._corridor_align_steps_history: list[int] = []
        self._wait_next_dig_steps_history: list[int] = []
        self._planner_replan_count = 0
        self._planner_replan_mask = False
        self._active_cycle: _ActiveCycleRuntime | None = None
        self._pending_cycle_summary: CycleSummary | None = None
        self._transition_policy_mode = TRANSITION_POLICY_MODE_SCRIPTED
        self._transition_fallback_count = 0
        self._transition_fallback_reasons: list[str] = []
        self._active_transition_use_learned = False
        self._active_transition_progress_seen = False
        self._active_transition_fallback_reason = ""
        self._work_target_guard_count = 0
        self._work_target_guard_active = False
        self._reset_active_transition_runtime()

        self._current_goal: PlannerGoal | None = None
        self._next_goal: PlannerGoal | None = None
        if self._is_rule_planner():
            self.planner.reset(self.scenario_id or self.planner.manifest.scenario_id)
            self._current_goal = self.planner.bootstrap_first_goal()
            self._next_goal = self._current_goal

        self._debug_state = HybridDebugState(
            hybrid_mode=HYBRID_MODE_WORK,
            transition_submode="",
            planner_cycle_index=0,
            planner_curr_sector_id=self._planner_curr_sector_id(),
            planner_next_sector_id=self._planner_next_sector_id(),
            planner_current_depth_class=self._planner_current_depth_class(),
            planner_next_depth_class=self._planner_next_depth_class(),
            planner_plan_source=self._planner_plan_source(),
            planner_replan_mask=False,
            transition_timeout=False,
            transition_collision_delta=0,
            corridor_align_steps=0,
            wait_next_dig_steps=0,
            transition_completed=False,
            transition_source=self._transition_source,
            transition_policy_mode=self._transition_policy_mode,
            transition_fallback_count=int(self._transition_fallback_count),
            transition_fallback_reason="",
            work_target_guard_active=False,
            work_target_guard_count=0,
        )

    def _is_rule_planner(self) -> bool:
        return isinstance(self.planner, RuleTaskPlanner)

    def _planner_curr_sector_id(self) -> int:
        if self._current_goal is not None:
            return int(self._current_goal.curr_src_sector_id)
        return int(self.planner.sector_id_for_cycle(self._cycle_index))

    def _planner_next_sector_id(self) -> int:
        if self._next_goal is not None:
            return int(self._next_goal.next_src_sector_id)
        return int(self.planner.sector_id_for_cycle(self._cycle_index + 1))

    def _planner_current_depth_class(self) -> int:
        if self._current_goal is not None:
            return int(self._current_goal.curr_cut_depth_class)
        return -1

    def _planner_next_depth_class(self) -> int:
        if self._next_goal is not None:
            return int(self._next_goal.next_cut_depth_class)
        return -1

    def _planner_plan_source(self) -> str:
        if self._next_goal is not None:
            return str(self._next_goal.plan_source)
        return "fixed"

    def _transition_target_sector_name(self) -> str:
        if self._next_goal is not None:
            return sector_name_from_id(int(self._next_goal.next_entry_corridor_id))
        return self.planner.sector_name_for_cycle(self._cycle_index + 1)

    def _reset_active_transition_runtime(self) -> None:
        self._active_transition_use_learned = self.transition_policy is not None
        self._active_transition_progress_seen = False
        self._active_transition_fallback_reason = ""
        self._transition_policy_mode = (
            TRANSITION_POLICY_MODE_LEARNED
            if self._active_transition_use_learned
            else TRANSITION_POLICY_MODE_SCRIPTED
        )

    def _transition_progress_seen(self, obs: dict[str, Any]) -> bool:
        task_step_successes = {
            str(item)
            for item in list(obs.get("task_step_successes", []))
        }
        reward_phase = str(obs.get("reward_phase", ""))
        if {"load_progress", "good_dig_start"} & task_step_successes:
            return True
        if reward_phase in {"load_progress", "good_dig_start"}:
            return True

        env_state = np.asarray(
            obs.get("env_state", np.zeros(9, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)
        mass_in_bucket = (
            float(env_state[ENV_STATE_MASS_IN_BUCKET_IDX])
            if len(env_state) > ENV_STATE_MASS_IN_BUCKET_IDX
            else 0.0
        )
        min_distance_to_dig_area = (
            float(env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX])
            if len(env_state) > ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX
            else np.inf
        )
        bucket_depth = (
            float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX])
            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
            else 0.0
        )
        return bool(
            mass_in_bucket >= self.transition_fallback_progress_mass_kg
            or (
                min_distance_to_dig_area
                <= self.transition_fallback_progress_distance_to_dig_area_m
                and bucket_depth >= self.transition_fallback_progress_bucket_depth_m
            )
        )

    def _activate_transition_fallback(self, *, reason: str) -> None:
        if not self._active_transition_use_learned:
            return
        self._active_transition_use_learned = False
        self._active_transition_progress_seen = False
        self._active_transition_fallback_reason = str(reason)
        self._transition_policy_mode = TRANSITION_POLICY_MODE_LEARNED_FALLBACK_TO_SCRIPTED
        self._transition_fallback_count += 1
        self._transition_fallback_reasons.append(str(reason))
        self.transition_controller.reset_wait_next_dig_timeout_budget()

    def _work_target_guard_limits(
        self,
        obs: dict[str, Any],
        action: np.ndarray,
    ) -> tuple[float, float] | None:
        if not self.work_target_guard_enabled or action.shape[0] < 4:
            return None
        env_state = np.asarray(
            obs.get("env_state", np.zeros(9, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if len(env_state) <= ENV_STATE_MASS_IN_BUCKET_IDX and "mass_in_bucket_kg" not in task_metrics:
            return None
        mass_in_bucket = float(
            task_metrics.get(
                "mass_in_bucket_kg",
                env_state[ENV_STATE_MASS_IN_BUCKET_IDX]
                if len(env_state) > ENV_STATE_MASS_IN_BUCKET_IDX
                else 0.0,
            )
        )
        if not np.isfinite(mass_in_bucket):
            return None
        if mass_in_bucket < self.work_target_guard_min_bucket_mass_kg:
            return None

        def _target_metric(name: str, index: int) -> tuple[float, bool]:
            if name in task_metrics:
                value = float(task_metrics[name])
                return value, bool(np.isfinite(value))
            if len(env_state) <= index:
                return 0.0, False
            value = float(env_state[index])
            return value, bool(np.isfinite(value))

        target_horizontal_distance, has_target_horizontal_distance = _target_metric(
            "target_horizontal_distance_m",
            ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
        )
        bucket_height_above_target_rim, has_target_height = _target_metric(
            "bucket_height_above_target_rim_m",
            ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        )
        bucket_over_target_footprint, has_target_footprint = _target_metric(
            "bucket_over_target_footprint_mask",
            ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        )
        dump_clearance_ok_mask, has_dump_clearance = _target_metric(
            "dump_clearance_ok_mask",
            ENV_STATE_DUMP_CLEARANCE_OK_IDX,
        )
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
        if not target_geometry_available:
            raise RuntimeError(
                "work_target_guard requires target geometry fields "
                "(target_horizontal_distance_m, bucket_height_above_target_rim_m, "
                "bucket_over_target_footprint_mask, dump_clearance_ok_mask). "
                "Scalar min_distance_to_target_m is not used as a fallback."
            )
        if not np.isfinite(target_horizontal_distance):
            return None
        dump_clearance_ok = bool(
            dump_clearance_ok_mask > 0.5
        )
        if dump_clearance_ok:
            return None

        bucket_action = float(action[3])
        if (
            target_horizontal_distance < self.work_target_guard_distance_m
            and bucket_action < self.work_target_guard_bucket_action_floor
        ):
            return (
                float(self.work_target_guard_bucket_action_floor),
                float(self.work_target_guard_boom_action_min),
            )
        if (
            target_horizontal_distance < self.work_target_guard_approach_distance_m
            and bucket_action < self.work_target_guard_approach_bucket_action_floor
        ):
            return (
                float(self.work_target_guard_approach_bucket_action_floor),
                float(self.work_target_guard_approach_boom_action_min),
            )
        return None

    def _work_target_guard_should_activate(self, obs: dict[str, Any], action: np.ndarray) -> bool:
        return self._work_target_guard_limits(obs, action) is not None

    def _apply_work_target_guard(self, action: np.ndarray, obs: dict[str, Any]) -> np.ndarray:
        guarded_action = np.asarray(action, dtype=np.float32).reshape(self.action_dim).copy()
        guard_limits = self._work_target_guard_limits(
            obs,
            guarded_action,
        )
        self._work_target_guard_active = guard_limits is not None
        if not self._work_target_guard_active:
            return guarded_action
        bucket_action_floor, boom_action_min = guard_limits
        guarded_action[3] = max(
            float(guarded_action[3]),
            bucket_action_floor,
        )
        guarded_action[1] = max(
            float(guarded_action[1]),
            boom_action_min,
        )
        self._work_target_guard_count += 1
        return guarded_action

    def _should_end_bootstrap(self, boundary_event) -> bool:
        if self.bootstrap_policy is None or self._entered_work_window:
            return False
        if boundary_event is None:
            return False
        if self.bootstrap_end_mode == BOOTSTRAP_END_MODE_FIRST_QUALIFIED_DIG_START:
            return bool(boundary_event.qualified_dig_start)
        if self.bootstrap_end_mode == BOOTSTRAP_END_MODE_LOADED_AND_CLEAR:
            metrics = dict(boundary_event.metrics or {})
            return bool(
                boundary_event.cycle_id >= 0
                and metrics.get("mass_in_bucket_kg", 0.0)
                >= self.bootstrap_end_min_bucket_mass_kg
                and metrics.get("min_distance_to_dig_area_m", 0.0)
                >= self.bootstrap_end_min_distance_to_dig_area_m
            )
        raise ValueError(
            f"Unsupported bootstrap_end_mode {self.bootstrap_end_mode!r}."
        )

    def _start_cycle_tracking(self, *, boundary_event, obs: dict[str, Any]) -> None:
        env_state = np.asarray(
            obs.get("env_state", np.zeros(9, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)
        deposited_mass_start = (
            float(env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX])
            if len(env_state) > ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
            else 0.0
        )
        collision_count_start = (
            int(round(float(env_state[ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX])))
            if len(env_state) > ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX
            else 0
        )
        self._active_cycle = _ActiveCycleRuntime(
            cycle_id=int(boundary_event.cycle_id),
            start_step=int(boundary_event.step_index),
            current_goal=self._current_goal,
            next_goal=self._next_goal,
            deposited_mass_start=deposited_mass_start,
            collision_count_start=collision_count_start,
            fill_peak_kg=0.0,
            peak_bucket_depth_m=0.0,
            target_contact_max_force_n=0.0,
            qualified_dig=bool(boundary_event.qualified_dig_start),
        )
        self._update_cycle_tracking(obs)

    def _update_cycle_tracking(self, obs: dict[str, Any]) -> None:
        if self._active_cycle is None:
            return
        env_state = np.asarray(
            obs.get("env_state", np.zeros(9, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)
        fill_peak = (
            float(env_state[ENV_STATE_MASS_IN_BUCKET_IDX])
            if len(env_state) > ENV_STATE_MASS_IN_BUCKET_IDX
            else 0.0
        )
        peak_depth = (
            float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX])
            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
            else 0.0
        )
        target_force = (
            float(env_state[ENV_STATE_TARGET_CONTACT_MAX_NORMAL_FORCE_N_IDX])
            if len(env_state) > ENV_STATE_TARGET_CONTACT_MAX_NORMAL_FORCE_N_IDX
            else 0.0
        )
        self._active_cycle.fill_peak_kg = max(self._active_cycle.fill_peak_kg, fill_peak)
        self._active_cycle.peak_bucket_depth_m = max(
            self._active_cycle.peak_bucket_depth_m,
            peak_depth,
        )
        self._active_cycle.target_contact_max_force_n = max(
            self._active_cycle.target_contact_max_force_n,
            target_force,
        )

    def _close_cycle_summary(self, *, obs: dict[str, Any]) -> CycleSummary | None:
        if self._active_cycle is None:
            return None
        env_state = np.asarray(
            obs.get("env_state", np.zeros(9, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)
        deposited_mass = (
            float(env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX])
            if len(env_state) > ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
            else 0.0
        )
        collision_count = (
            int(round(float(env_state[ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX])))
            if len(env_state) > ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX
            else 0
        )
        current_goal = self._active_cycle.current_goal
        next_goal = self._active_cycle.next_goal
        curr_sector_id = (
            int(current_goal.curr_src_sector_id)
            if current_goal is not None
            else self._planner_curr_sector_id()
        )
        next_sector_id = (
            int(next_goal.next_src_sector_id)
            if next_goal is not None
            else self._planner_next_sector_id()
        )
        deposit_delta = float(deposited_mass - self._active_cycle.deposited_mass_start)
        summary = CycleSummary(
            cycle_id=int(self._active_cycle.cycle_id),
            curr_src_sector_id=curr_sector_id,
            next_src_sector_id=next_sector_id,
            fill_peak_kg=float(self._active_cycle.fill_peak_kg),
            deposit_delta_kg=float(deposit_delta),
            peak_bucket_depth_m=float(self._active_cycle.peak_bucket_depth_m),
            collision_count_delta=int(
                max(0, collision_count - self._active_cycle.collision_count_start)
            ),
            target_contact_max_force_n=float(self._active_cycle.target_contact_max_force_n),
            qualified_dig=bool(self._active_cycle.qualified_dig),
            cycle_success=bool(deposit_delta > 0.0),
        )
        self._active_cycle = None
        return summary

    def predict(self, obs: dict) -> np.ndarray:
        boundary_event = None
        if self._prev_action is not None:
            boundary_event = self.boundary_detector.update(
                env_state=obs.get("env_state", np.zeros(9, dtype=np.float32)),
                action=self._prev_action,
                qpos=obs.get("qpos", np.zeros(4, dtype=np.float32)),
                reward_phase=obs.get("reward_phase"),
                task_step_successes=obs.get("task_step_successes"),
                task_metrics=obs.get("task_metrics"),
            )

        self._planner_replan_mask = False
        transition_timeout = False
        transition_completed = False
        transition_collision_delta = 0
        corridor_align_steps = 0
        wait_next_dig_steps = 0
        transition_submode = ""
        self._work_target_guard_active = False

        if boundary_event is not None and boundary_event.qualified_dig_start:
            if self._active_cycle is None or self._active_cycle.cycle_id != int(boundary_event.cycle_id):
                self._start_cycle_tracking(boundary_event=boundary_event, obs=obs)

        if self._mode == HYBRID_MODE_WORK:
            if self._active_cycle is not None:
                self._update_cycle_tracking(obs)

            if self._should_end_bootstrap(boundary_event):
                self._entered_work_window = True
                self.work_policy.reset()

            if boundary_event is not None and boundary_event.dump_end:
                self._pending_cycle_summary = self._close_cycle_summary(obs=obs)
                if self._is_rule_planner() and self._pending_cycle_summary is not None:
                    self._next_goal = self.planner.replan_at_cycle_boundary(
                        self._pending_cycle_summary
                    )
                    self._planner_replan_mask = True
                    self._planner_replan_count += 1
                    self._pending_cycle_summary = None
                self.transition_controller.start_transition(
                    target_sector_name=self._transition_target_sector_name(),
                    env_state=obs.get("env_state"),
                )
                if self.transition_policy is not None:
                    self.transition_policy.reset()
                self.work_policy.reset()
                self._reset_active_transition_runtime()
                self._mode = HYBRID_MODE_TRANSITION
                transition_output = self.transition_controller.step(
                    obs=obs,
                    qualified_dig_start=False,
                )
                action = transition_output.action
                transition_submode = transition_output.submode
                transition_timeout = transition_output.transition_timeout
                transition_collision_delta = transition_output.transition_collision_delta
                corridor_align_steps = transition_output.corridor_align_steps
                wait_next_dig_steps = transition_output.wait_next_dig_steps
            else:
                active_work_policy = (
                    self.work_policy
                    if self._entered_work_window or self.bootstrap_policy is None
                    else self.bootstrap_policy
                )
                action = np.asarray(
                    active_work_policy.predict(obs),
                    dtype=np.float32,
                )
                action = self._apply_work_target_guard(action, obs)
        else:
            qualified_dig_start = bool(
                boundary_event is not None and boundary_event.qualified_dig_start
            )
            transition_output = self.transition_controller.step(
                obs=obs,
                qualified_dig_start=qualified_dig_start,
            )
            self._transition_step_count_total += 1
            transition_submode = transition_output.submode
            transition_timeout = transition_output.transition_timeout
            transition_completed = transition_output.transition_completed
            transition_collision_delta = transition_output.transition_collision_delta
            corridor_align_steps = transition_output.corridor_align_steps
            wait_next_dig_steps = transition_output.wait_next_dig_steps

            if transition_submode == TRANSITION_SUBMODE_WAIT_NEXT_DIG and not transition_timeout:
                self._active_transition_progress_seen = (
                    self._active_transition_progress_seen or self._transition_progress_seen(obs)
                )
                if self.transition_policy is not None and self.transition_enable_fallback:
                    if (
                        self._active_transition_use_learned
                        and self.transition_fallback_no_progress_steps > 0
                        and wait_next_dig_steps >= self.transition_fallback_no_progress_steps
                        and not self._active_transition_progress_seen
                    ):
                        self._activate_transition_fallback(reason="no_progress")
                    elif (
                        self._active_transition_use_learned
                        and self.transition_fallback_local_budget_steps > 0
                        and wait_next_dig_steps >= self.transition_fallback_local_budget_steps
                    ):
                        self._activate_transition_fallback(reason="local_budget_exhausted")

            if (
                transition_submode == TRANSITION_SUBMODE_WAIT_NEXT_DIG
                and not transition_timeout
                and self.transition_policy is not None
                and self._active_transition_use_learned
            ):
                action = np.asarray(self.transition_policy.predict(obs), dtype=np.float32)
            elif (
                transition_submode == TRANSITION_SUBMODE_WAIT_NEXT_DIG
                and not transition_timeout
                and self.transition_controller.should_handoff_to_work_policy()
            ):
                action = np.asarray(
                    self.work_policy.predict(obs),
                    dtype=np.float32,
                )
            else:
                action = transition_output.action

            if transition_completed:
                self._mode = HYBRID_MODE_WORK
                self._cycle_index += 1
                self._entered_work_window = True
                self._completed_transition_count += 1
                self._transition_collision_delta_total += int(transition_collision_delta)
                self._corridor_align_steps_history.append(int(corridor_align_steps))
                self._wait_next_dig_steps_history.append(int(wait_next_dig_steps))
                if self._is_rule_planner():
                    self._current_goal = self._next_goal or self._current_goal
                self._pending_cycle_summary = None
                self.work_policy.reset()
                transition_submode = ""
                self._transition_policy_mode = TRANSITION_POLICY_MODE_SCRIPTED
                if qualified_dig_start and boundary_event is not None:
                    self._start_cycle_tracking(boundary_event=boundary_event, obs=obs)
            elif transition_timeout:
                self._transition_timeout_count += 1
                self._transition_collision_delta_total += int(transition_collision_delta)

        action = np.asarray(action, dtype=np.float32).reshape(self.action_dim)
        self._prev_action = action.copy()

        self._debug_state = HybridDebugState(
            hybrid_mode=self._mode,
            transition_submode=transition_submode,
            planner_cycle_index=int(self._cycle_index),
            planner_curr_sector_id=self._planner_curr_sector_id(),
            planner_next_sector_id=self._planner_next_sector_id(),
            planner_current_depth_class=self._planner_current_depth_class(),
            planner_next_depth_class=self._planner_next_depth_class(),
            planner_plan_source=self._planner_plan_source(),
            planner_replan_mask=bool(self._planner_replan_mask),
            transition_timeout=bool(transition_timeout),
            transition_collision_delta=int(transition_collision_delta),
            corridor_align_steps=int(corridor_align_steps),
            wait_next_dig_steps=int(wait_next_dig_steps),
            transition_completed=bool(transition_completed),
            transition_source=self._transition_source,
            transition_policy_mode=self._transition_policy_mode,
            transition_fallback_count=int(self._transition_fallback_count),
            transition_fallback_reason=str(self._active_transition_fallback_reason),
            work_target_guard_active=bool(self._work_target_guard_active),
            work_target_guard_count=int(self._work_target_guard_count),
        )
        return action

    def debug_state(self) -> dict[str, Any]:
        return {
            "hybrid_mode": self._debug_state.hybrid_mode,
            "transition_submode": self._debug_state.transition_submode,
            "planner_cycle_index": int(self._debug_state.planner_cycle_index),
            "planner_curr_sector_id": int(self._debug_state.planner_curr_sector_id),
            "planner_next_sector_id": int(self._debug_state.planner_next_sector_id),
            "planner_current_sector_id": int(self._debug_state.planner_curr_sector_id),
            "planner_current_depth_class": int(self._debug_state.planner_current_depth_class),
            "planner_next_depth_class": int(self._debug_state.planner_next_depth_class),
            "planner_plan_source": self._debug_state.planner_plan_source,
            "planner_replan_mask": bool(self._debug_state.planner_replan_mask),
            "transition_timeout": bool(self._debug_state.transition_timeout),
            "transition_collision_delta": int(self._debug_state.transition_collision_delta),
            "corridor_align_steps": int(self._debug_state.corridor_align_steps),
            "wait_next_dig_steps": int(self._debug_state.wait_next_dig_steps),
            "transition_completed": bool(self._debug_state.transition_completed),
            "transition_source": self._debug_state.transition_source,
            "transition_policy_mode": self._debug_state.transition_policy_mode,
            "transition_fallback_count": int(self._debug_state.transition_fallback_count),
            "transition_fallback_reason": self._debug_state.transition_fallback_reason,
            "work_target_guard_active": bool(self._debug_state.work_target_guard_active),
            "work_target_guard_count": int(self._debug_state.work_target_guard_count),
        }

    def planner_trace(self) -> dict[str, Any]:
        if self._is_rule_planner():
            return self.planner.planner_trace()
        return {
            "planner_kind": "fixed_sequence",
            "sequence": list(self.planner.sequence),
        }

    def rollout_summary(self) -> dict[str, float | int | str | list[str]]:
        transition_step_count = int(self._transition_step_count_total)
        transition_collision_rate = (
            float(self._transition_collision_delta_total) / float(transition_step_count)
            if transition_step_count > 0
            else 0.0
        )
        summary: dict[str, float | int | str | list[str]] = {
            "transition_source": self._transition_source,
            "transition_timeout_count": int(self._transition_timeout_count),
            "transition_collision_rate": float(transition_collision_rate),
            "avg_corridor_align_steps": (
                float(np.mean(self._corridor_align_steps_history))
                if self._corridor_align_steps_history else 0.0
            ),
            "avg_wait_next_dig_steps": (
                float(np.mean(self._wait_next_dig_steps_history))
                if self._wait_next_dig_steps_history else 0.0
            ),
            "completed_transition_count": int(self._completed_transition_count),
            "transition_policy_mode": self._transition_policy_mode,
            "transition_fallback_count": int(self._transition_fallback_count),
            "transition_fallback_reason": (
                self._transition_fallback_reasons[-1]
                if self._transition_fallback_reasons else ""
            ),
            "work_target_guard_count": int(self._work_target_guard_count),
        }
        if self._is_rule_planner():
            belief = self.planner.current_belief()
            sector_sequence = [
                sector_name_from_id(int(item["selected_next_goal"]["curr_src_sector_id"]))
                for item in self.planner.planner_trace().get("replans", [])
            ]
            if not sector_sequence:
                sector_sequence = [sector_name_from_id(self._planner_curr_sector_id())]
            summary.update(
                {
                    "planner_replan_count": int(self._planner_replan_count),
                    "planner_sector_sequence": sector_sequence,
                    "planner_blocked_sector_count": int(
                        sum(int(sector.state) == 4 for sector in belief.sectors)
                    ),
                    "planner_done_sector_count": int(
                        sum(int(sector.state) == 3 for sector in belief.sectors)
                    ),
                }
            )
        return summary
