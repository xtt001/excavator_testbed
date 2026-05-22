"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_CONTRACT,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
    _build_dig_cut_token,
    build_live_dig_cut_tokens_from_pose,
)
from testbed.data.v2_1 import build_goal_tokens
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
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
PRE_DIG_ALIGN_SKILL_NAME = "pre_dig_align"
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


@dataclass
class CoverageCorridorState:
    corridor_id: int
    entry_x_m: float
    entry_z_m: float
    exit_x_m: float
    exit_z_m: float
    cell_id: int = -1
    source_count: int = 0
    source_fraction: float = 0.0
    cut_depth_peak_m: float = float("nan")
    payload_gain_kg: float = float("nan")
    effective_deposit_delta_kg: float = float("nan")
    score: float = 0.0
    attempts: int = 0
    low_productivity_streak: int = 0
    depleted: bool = False
    belief_coverage: float = 0.0
    last_payload_gain_kg: float = 0.0
    last_effective_deposit_delta_kg: float = 0.0
    last_remaining_depth_m: float = float("nan")
    last_reason: str = ""


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
        first_dig_policy: Policy | None = None,
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
        dig_to_carry_target_bucket_mass_kg: float | None = None,
        dig_to_carry_mass_plateau_enabled: bool = False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg: float = 20.0,
        dig_to_carry_mass_plateau_epsilon_kg: float = 1.0,
        dig_to_carry_mass_plateau_hold_steps: int = 25,
        dig_to_carry_mass_plateau_min_steps: int = 80,
        dig_bad_replan_enabled: bool = False,
        dig_bad_replan_max_steps: int = 180,
        dig_bad_replan_min_bucket_mass_kg: float = 15.0,
        dig_exit_guard_enabled: bool = False,
        dig_exit_guard_min_steps: int = 80,
        dig_exit_guard_overshoot_m: float = 0.65,
        dig_exit_guard_min_bucket_mass_kg: float = 20.0,
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
        dump_ready_near_window_enabled: bool = False,
        dump_ready_near_window_x_tolerance_m: float = 0.05,
        dump_ready_near_window_z_tolerance_m: float = 0.05,
        dump_ready_near_window_outside_tolerance_m: float = 0.0,
        dump_ready_near_window_require_over_footprint: bool = True,
        dump_done_max_bucket_mass_kg: float = 100.0,
        dump_done_min_deposit_delta_kg: float = 10.0,
        dump_done_hold_steps: int = 2,
        dump_done_use_boundary_event: bool = True,
        return_to_dig_shallow_guard_enabled: bool = False,
        return_to_dig_max_bucket_mass_kg: float = 15.0,
        return_to_dig_touch_tolerance_m: float = 0.05,
        return_to_dig_min_depth_m: float = 0.02,
        return_to_dig_max_depth_m: float = 0.12,
        return_to_dig_max_entry_error_m: float | None = None,
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
        return_target_planner: dict[str, Any] | None = None,
        scripted_bootstrap_target_qpos: list[float] | tuple[float, ...] | np.ndarray | None = None,
        scripted_bootstrap_kp: float = 2.0,
        scripted_bootstrap_kd: float = 0.25,
        scripted_bootstrap_action_clip: float | list[float] | tuple[float, ...] = 0.35,
        scripted_bootstrap_action_signs: list[float] | tuple[float, ...] | np.ndarray | None = None,
        scripted_bootstrap_qpos_tolerance: float = 0.02,
        scripted_bootstrap_qvel_abs_max: float = 0.08,
        scripted_bootstrap_hold_steps: int = 5,
        scripted_bootstrap_max_steps: int = 240,
        pre_dig_align: dict[str, Any] | None = None,
    ) -> None:
        self.dig_policy = dig_policy
        self.first_dig_policy = first_dig_policy
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
        self.dig_to_carry_target_bucket_mass_kg = float(
            self.dig_to_carry_min_bucket_mass_kg
            if dig_to_carry_target_bucket_mass_kg is None
            else dig_to_carry_target_bucket_mass_kg
        )
        self.dig_to_carry_mass_plateau_enabled = bool(
            dig_to_carry_mass_plateau_enabled
        )
        self.dig_to_carry_mass_plateau_min_bucket_mass_kg = float(
            dig_to_carry_mass_plateau_min_bucket_mass_kg
        )
        self.dig_to_carry_mass_plateau_epsilon_kg = float(
            dig_to_carry_mass_plateau_epsilon_kg
        )
        self.dig_to_carry_mass_plateau_hold_steps = max(
            1, int(dig_to_carry_mass_plateau_hold_steps)
        )
        self.dig_to_carry_mass_plateau_min_steps = max(
            1, int(dig_to_carry_mass_plateau_min_steps)
        )
        self.dig_bad_replan_enabled = bool(dig_bad_replan_enabled)
        self.dig_bad_replan_max_steps = max(1, int(dig_bad_replan_max_steps))
        self.dig_bad_replan_min_bucket_mass_kg = float(
            dig_bad_replan_min_bucket_mass_kg
        )
        self.dig_exit_guard_enabled = bool(dig_exit_guard_enabled)
        self.dig_exit_guard_min_steps = max(1, int(dig_exit_guard_min_steps))
        self.dig_exit_guard_overshoot_m = float(dig_exit_guard_overshoot_m)
        self.dig_exit_guard_min_bucket_mass_kg = float(
            dig_exit_guard_min_bucket_mass_kg
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
        self.dump_ready_near_window_enabled = bool(dump_ready_near_window_enabled)
        self.dump_ready_near_window_x_tolerance_m = float(
            dump_ready_near_window_x_tolerance_m
        )
        self.dump_ready_near_window_z_tolerance_m = float(
            dump_ready_near_window_z_tolerance_m
        )
        self.dump_ready_near_window_outside_tolerance_m = float(
            dump_ready_near_window_outside_tolerance_m
        )
        self.dump_ready_near_window_require_over_footprint = bool(
            dump_ready_near_window_require_over_footprint
        )
        self.dump_done_max_bucket_mass_kg = float(dump_done_max_bucket_mass_kg)
        self.dump_done_min_deposit_delta_kg = float(dump_done_min_deposit_delta_kg)
        self.dump_done_hold_steps = max(1, int(dump_done_hold_steps))
        self.dump_done_use_boundary_event = bool(dump_done_use_boundary_event)
        self.return_to_dig_shallow_guard_enabled = bool(
            return_to_dig_shallow_guard_enabled
        )
        self.return_to_dig_max_bucket_mass_kg = float(return_to_dig_max_bucket_mass_kg)
        self.return_to_dig_touch_tolerance_m = float(return_to_dig_touch_tolerance_m)
        self.return_to_dig_min_depth_m = float(return_to_dig_min_depth_m)
        self.return_to_dig_max_depth_m = float(return_to_dig_max_depth_m)
        self.return_to_dig_max_entry_error_m = self._optional_float(
            return_to_dig_max_entry_error_m
        )
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
                self.dig_cut_planner_mode
                in {
                    "operator_prior",
                    "operator_prior_coverage",
                    "operator_prior_sweep_belief",
                },
            )
        )
        self.dig_cut_prior_path = str(self.dig_cut_planner_cfg.get("prior_path", ""))
        self.dig_cut_prior = self._load_dig_cut_prior(self.dig_cut_prior_path)
        self.dig_cut_prior_id = str(self.dig_cut_prior.get("prior_id", ""))
        self.return_target_planner_cfg = dict(return_target_planner or {})
        self.return_target_planner_enabled = bool(
            self.return_target_planner_cfg.get("enabled", False)
        )
        self.return_target_hold_token_until_skill_exit = bool(
            self.return_target_planner_cfg.get("hold_token_until_skill_exit", True)
        )
        self.return_target_token_source_prefix = str(
            self.return_target_planner_cfg.get("token_source_prefix", "return_target")
        )
        coverage_cfg = dict(self.dig_cut_planner_cfg.get("coverage", {}) or {})
        self.coverage_candidate_layout = str(
            coverage_cfg.get("candidate_layout", "percentile_grid")
        ).strip().lower()
        self.coverage_use_env_removed_depth = bool(
            coverage_cfg.get(
                "use_env_removed_depth",
                self.dig_cut_planner_mode == "operator_prior_coverage",
            )
        )
        self.coverage_belief_gain_scale = float(
            coverage_cfg.get("belief_gain_scale", 0.55)
        )
        self.coverage_belief_depleted_score = float(
            coverage_cfg.get("belief_depleted_score", 1.0)
        )
        self.coverage_low_productivity_payload_kg = float(
            coverage_cfg.get("low_productivity_payload_kg", 15.0)
        )
        self.coverage_low_productivity_deposit_kg = float(
            coverage_cfg.get("low_productivity_deposit_kg", 15.0)
        )
        self.coverage_deplete_after_low_streak = max(
            1, int(coverage_cfg.get("deplete_after_low_streak", 2))
        )
        self.coverage_min_remaining_depth_m = float(
            coverage_cfg.get("min_remaining_depth_m", 0.05)
        )
        self.coverage_global_low_productivity_stop = max(
            1, int(coverage_cfg.get("global_low_productivity_stop", 3))
        )
        self.coverage_max_attempts_per_corridor = max(
            1, int(coverage_cfg.get("max_attempts_per_corridor", 3))
        )
        self.coverage_unattempted_bonus = float(
            coverage_cfg.get("unattempted_bonus", 2.0)
        )
        self.coverage_attempt_penalty = float(
            coverage_cfg.get("attempt_penalty", 0.65)
        )
        self.coverage_recent_selection_penalty = float(
            coverage_cfg.get("recent_selection_penalty", 1.25)
        )
        self.coverage_recent_row_selection_penalty = float(
            coverage_cfg.get("recent_row_selection_penalty", 0.0)
        )
        self.coverage_rare_cell_source_fraction_threshold = float(
            coverage_cfg.get("rare_cell_source_fraction_threshold", 0.05)
        )
        self.coverage_rare_cell_max_attempts = max(
            1, int(coverage_cfg.get("rare_cell_max_attempts", 1))
        )
        self.coverage_cell_confidence_weight = float(
            coverage_cfg.get("cell_confidence_weight", 0.75)
        )
        self.coverage_first_dig_strategy = str(
            coverage_cfg.get("first_dig_strategy", "coverage_score")
        ).strip().lower()
        raw_first_dig_corridor = coverage_cfg.get("first_dig_preferred_corridor_id")
        self.coverage_first_dig_preferred_corridor_id = (
            None
            if raw_first_dig_corridor is None
            or str(raw_first_dig_corridor).strip().lower() in {"", "none", "null"}
            else int(raw_first_dig_corridor)
        )
        self.coverage_first_dig_preferred_bonus = float(
            coverage_cfg.get("first_dig_preferred_bonus", 10000.0)
        )
        self.coverage_first_dig_proximity_weight = float(
            coverage_cfg.get("first_dig_proximity_weight", 0.0)
        )
        self.coverage_first_dig_max_entry_distance_m = self._optional_float(
            coverage_cfg.get("first_dig_max_entry_distance_m")
        )
        self.coverage_first_dig_qpos_delta_weight = float(
            coverage_cfg.get("first_dig_qpos_delta_weight", 0.0)
        )
        self.coverage_first_dig_max_qpos_delta = self._optional_align_vector(
            coverage_cfg.get("first_dig_max_qpos_delta")
        )
        self.coverage_entry_x_percentiles = self._coverage_percentile_list(
            coverage_cfg.get("entry_x_percentiles", ["p10", "p50", "p90"]),
            default=("p10", "p50", "p90"),
        )
        self.coverage_entry_z_percentiles = self._coverage_percentile_list(
            coverage_cfg.get("entry_z_percentiles", ["p10", "p50", "p90"]),
            default=("p10", "p50", "p90"),
        )
        self.coverage_cut_direction_percentile = self._coverage_percentile_name(
            coverage_cfg.get("cut_direction_percentile", "p50"),
            default="p50",
        )
        self.coverage_cut_length_percentile = self._coverage_percentile_name(
            coverage_cfg.get("cut_length_percentile", "p50"),
            default="p50",
        )
        self.coverage_cut_depth_percentile = self._coverage_percentile_name(
            coverage_cfg.get("cut_depth_percentile", "p50"),
            default="p50",
        )
        self.coverage_payload_percentile = self._coverage_percentile_name(
            coverage_cfg.get("payload_percentile", "p50"),
            default="p50",
        )
        self.pre_dig_align_cfg = dict(pre_dig_align or {})
        self.pre_dig_align_enabled = bool(self.pre_dig_align_cfg.get("enabled", False))
        self.pre_dig_align_first_dig_only = bool(
            self.pre_dig_align_cfg.get("first_dig_only", False)
        )
        self.pre_dig_align_kp = float(self.pre_dig_align_cfg.get("kp", 2.0))
        self.pre_dig_align_kd = float(self.pre_dig_align_cfg.get("kd", 0.25))
        self.pre_dig_align_action_clip = self.pre_dig_align_cfg.get(
            "action_clip",
            [0.55, 0.35, 0.35, 0.35],
        )
        self.pre_dig_align_action_signs = np.asarray(
            self.pre_dig_align_cfg.get("action_signs", [1.0, -1.0, 1.0, 1.0]),
            dtype=np.float32,
        ).reshape(self.action_dim)
        self.pre_dig_align_controlled_dims = (
            np.asarray(
                self.pre_dig_align_cfg.get("controlled_dims", [1, 1, 1, 0]),
                dtype=np.float32,
            ).reshape(self.action_dim)
            > 0.5
        )
        self.pre_dig_align_bucket_target_qpos = self._optional_float(
            self.pre_dig_align_cfg.get("bucket_target_qpos")
        )
        self.pre_dig_align_qpos_tolerance = self._align_vector(
            self.pre_dig_align_cfg.get(
                "qpos_tolerance",
                [0.025, 0.04, 0.05, 0.06],
            ),
            default=[0.025, 0.04, 0.05, 0.06],
        )
        self.pre_dig_align_qvel_abs_max = float(
            self.pre_dig_align_cfg.get("qvel_abs_max", 0.12)
        )
        self.pre_dig_align_hold_steps = max(
            1, int(self.pre_dig_align_cfg.get("hold_steps", 3))
        )
        self.pre_dig_align_max_steps = max(
            1, int(self.pre_dig_align_cfg.get("max_steps", 140))
        )
        self.pre_dig_align_max_entry_error_m = self._optional_float(
            self.pre_dig_align_cfg.get("max_entry_error_m")
        )
        self.pre_dig_align_timeout_accept_entry_error_m = self._optional_float(
            self.pre_dig_align_cfg.get("timeout_accept_entry_error_m")
        )
        self.pre_dig_align_timeout_replan_entry_error_m = self._optional_float(
            self.pre_dig_align_cfg.get("timeout_replan_entry_error_m")
        )
        self.pre_dig_align_start_envelope_enabled = bool(
            self.pre_dig_align_cfg.get("start_envelope_enabled", False)
        )
        self.pre_dig_align_first_dig_entry_close_handoff = bool(
            self.pre_dig_align_cfg.get("first_dig_entry_close_handoff", False)
        )
        self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max = (
            self._optional_float(
                self.pre_dig_align_cfg.get(
                    "first_dig_entry_close_handoff_qvel_abs_max"
                )
            )
        )
        self.pre_dig_align_start_envelope_max_entry_error_m = float(
            self.pre_dig_align_cfg.get("start_envelope_max_entry_error_m", 0.65)
        )
        self.pre_dig_align_start_qpos_min = self._align_vector(
            self.pre_dig_align_cfg.get(
                "start_qpos_min",
                [0.45, 0.52, 0.0, 0.0],
            ),
            default=[0.45, 0.52, 0.0, 0.0],
        )
        self.pre_dig_align_start_qpos_max = self._align_vector(
            self.pre_dig_align_cfg.get(
                "start_qpos_max",
                [0.57, 0.78, 0.40, 0.12],
            ),
            default=[0.57, 0.78, 0.40, 0.12],
        )
        self.pre_dig_align_start_pose_min = np.asarray(
            self.pre_dig_align_cfg.get("start_pose_min", [-0.60, -0.30, -1.50]),
            dtype=np.float32,
        ).reshape(3)
        self.pre_dig_align_start_pose_max = np.asarray(
            self.pre_dig_align_cfg.get("start_pose_max", [1.65, 0.25, 1.20]),
            dtype=np.float32,
        ).reshape(3)
        self.pre_dig_align_qpos_min = self._align_vector(
            self.pre_dig_align_cfg.get(
                "qpos_min",
                [0.44, 0.50, 0.0, 0.0],
            ),
            default=[0.44, 0.50, 0.0, 0.0],
        )
        self.pre_dig_align_qpos_max = self._align_vector(
            self.pre_dig_align_cfg.get(
                "qpos_max",
                [0.56, 0.79, 0.42, 0.36],
            ),
            default=[0.56, 0.79, 0.42, 0.36],
        )
        self.pre_dig_align_qpos_from_token_coefficients = np.asarray(
            self.pre_dig_align_cfg.get(
                "qpos_from_token_coefficients",
                [
                    [0.49761536, -0.00324577, -0.07974796],
                    [0.48509995, 0.34124863, -0.02063946],
                    [0.39998216, -0.50266185, 0.04142020],
                    [0.21223230, -0.14153491, -0.01244724],
                ],
            ),
            dtype=np.float32,
        ).reshape(self.action_dim, 3)
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
        has_bootstrap = (
            self.bootstrap_end_mode != "disabled"
            and (
                self.bootstrap_policy is not None
                or self._scripted_bootstrap_enabled()
            )
        )
        self._skill_name = (
            BOOTSTRAP_SKILL_NAME
            if has_bootstrap
            else PRE_DIG_ALIGN_SKILL_NAME
            if self._should_pre_dig_align_before_dig()
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
        self._pre_dig_align_step_count = 0
        self._pre_dig_align_hold_count = 0
        self._pre_dig_align_timeout_count = 0
        self._pre_dig_align_completed_count = 0
        self._pre_dig_align_replan_count = 0
        self._pre_dig_align_target_qpos = np.zeros(self.action_dim, dtype=np.float32)
        self._pre_dig_align_error = np.zeros(self.action_dim, dtype=np.float32)
        self._pre_dig_align_entry_error_m = float("nan")
        self._pre_dig_align_start_envelope_ready = False
        self._pre_dig_align_entry_close_handoff_ready = False
        self._dig_step_count = 0
        self._dig_best_mass_kg = 0.0
        self._dig_mass_plateau_count = 0
        self._dig_to_carry_reason = ""
        self._dig_bad_replan_count = 0
        self._dig_exit_guard_replan_count = 0
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
        self._return_target_tokens = np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
        self._return_target_token_injected = False
        self._return_start_envelope_tokens = np.zeros(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float32,
        )
        self._return_start_envelope_token_injected = False
        self._return_target_planned_cycle_id = -1
        self._return_target_token_source = "none"
        self._return_target_fallback_reason = ""
        self._return_to_dig_entry_error_m = float("nan")
        self._return_to_dig_entry_close_state = True
        self._pending_dig_cut_cycle_id = -1
        self._pending_dig_cut_corridor_id = -1
        self._pending_dig_cut_raw_fields: dict[str, float | int] | None = None
        self._pending_dig_cut_tokens: np.ndarray | None = None
        self._cell_entry_seen_cell_id = -1
        self._cell_entry_trace: list[dict[str, Any]] = []
        self._dig_cut_planned_cycle_id = -1
        self._dig_cut_token_source = "none"
        self._dig_cut_fallback_reason = ""
        self._dig_cut_token_in_prior_p10_p90 = False
        self._coverage_corridors: list[CoverageCorridorState] = []
        self._coverage_active_corridor_id = -1
        self._coverage_last_selected_corridor_id = -1
        self._coverage_current_payload_gain_kg = 0.0
        self._coverage_cycle_start_deposit_kg = 0.0
        self._coverage_last_payload_gain_kg = 0.0
        self._coverage_last_effective_deposit_delta_kg = 0.0
        self._coverage_global_low_productivity_streak = 0
        self._coverage_completed_dump_count = 0
        self._coverage_terminal_stop_requested = False
        self._coverage_terminal_stop_reason = ""
        self._coverage_candidate_scores: list[dict[str, float | int | str]] = []
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
        if self._skill_name == "dig":
            self._update_dig_progress(obs)
        self._maybe_switch_skill(obs=obs, boundary_event=boundary_event)

        if self._skill_name == "return":
            self._return_step_count += 1
            if self.return_max_steps > 0 and self._return_step_count >= self.return_max_steps:
                transition_timeout = True
                self._transition_timeout_count += 1

        if self._skill_name == BOOTSTRAP_SKILL_NAME and self._scripted_bootstrap_enabled():
            action = self._scripted_bootstrap_action(obs)
        elif self._skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            action = self._pre_dig_align_action(obs)
        else:
            policy = self._active_policy()
            policy_obs = self._policy_obs(obs)
            action = np.asarray(policy.predict(policy_obs), dtype=np.float32).reshape(
                self.action_dim
            )
        self._prev_action = action.copy()

        if self._switch_reason.startswith(("return_to_dig_", "return_to_pre_dig_align_")):
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
            "return_target_token_injected": bool(self._return_target_token_injected),
            "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
            "return_target_token_source": str(self._return_target_token_source),
            "return_target_tokens": self._return_target_tokens.astype(float).tolist(),
            "return_target_fallback_reason": str(
                self._return_target_fallback_reason
            ),
            "return_start_envelope_token_injected": bool(
                self._return_start_envelope_token_injected
            ),
            "return_start_envelope_token_dim": int(RETURN_START_ENVELOPE_TOKEN_DIM),
            "return_start_envelope_tokens": (
                self._return_start_envelope_tokens.astype(float).tolist()
            ),
            "return_to_dig_entry_error_m": float(
                self._return_to_dig_entry_error_m
            ),
            "return_to_dig_entry_close": bool(self._return_to_dig_entry_close_state),
            "pending_dig_cut_cycle_id": int(self._pending_dig_cut_cycle_id),
            "pending_dig_cut_corridor_id": int(self._pending_dig_cut_corridor_id),
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
            "coverage_corridor_id": int(self._coverage_active_corridor_id),
            "coverage_selected_corridor_id": int(self._coverage_active_corridor_id),
            "coverage_entry_x_m": float(self._coverage_active_value("entry_x_m")),
            "coverage_entry_z_m": float(self._coverage_active_value("entry_z_m")),
            "coverage_exit_x_m": float(self._coverage_active_value("exit_x_m")),
            "coverage_exit_z_m": float(self._coverage_active_value("exit_z_m")),
            "coverage_corridor_score": float(self._coverage_active_corridor_score()),
            "coverage_depleted_count": int(self._coverage_depleted_count()),
            "coverage_last_payload_gain_kg": float(
                self._coverage_last_payload_gain_kg
            ),
            "coverage_last_effective_deposit_delta_kg": float(
                self._coverage_last_effective_deposit_delta_kg
            ),
            "coverage_global_low_productivity_streak": int(
                self._coverage_global_low_productivity_streak
            ),
            "coverage_use_env_removed_depth": bool(
                self.coverage_use_env_removed_depth
            ),
            "coverage_candidate_layout": str(self.coverage_candidate_layout),
            "coverage_first_dig_strategy": str(self.coverage_first_dig_strategy),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if self.coverage_first_dig_preferred_corridor_id is None
                else self.coverage_first_dig_preferred_corridor_id
            ),
            "coverage_first_dig_max_entry_distance_m": float(
                np.nan
                if self.coverage_first_dig_max_entry_distance_m is None
                else self.coverage_first_dig_max_entry_distance_m
            ),
            "coverage_first_dig_qpos_delta_weight": float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            "coverage_first_dig_max_qpos_delta": (
                None
                if self.coverage_first_dig_max_qpos_delta is None
                else self.coverage_first_dig_max_qpos_delta.astype(float).tolist()
            ),
            "coverage_terminal_stop_requested": bool(
                self._coverage_terminal_stop_requested
            ),
            "coverage_terminal_stop_reason": str(
                self._coverage_terminal_stop_reason
            ),
            "coverage_corridors": [
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ],
            "planner_terminal_stop_requested": bool(
                self._coverage_terminal_stop_requested
            ),
            "planner_terminal_stop_reason": str(
                self._coverage_terminal_stop_reason
            ),
            "coverage_candidate_scores": list(self._coverage_candidate_scores),
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
            "dig_step_count": int(self._dig_step_count),
            "dig_best_mass_kg": float(self._dig_best_mass_kg),
            "dig_mass_plateau_count": int(self._dig_mass_plateau_count),
            "dig_to_carry_reason": str(self._dig_to_carry_reason),
            "dig_bad_replan_count": int(self._dig_bad_replan_count),
            "dig_exit_guard_replan_count": int(self._dig_exit_guard_replan_count),
            "pre_dig_align_enabled": bool(self.pre_dig_align_enabled),
            "pre_dig_align_first_dig_only": bool(
                self.pre_dig_align_first_dig_only
            ),
            "pre_dig_align_active_for_next_dig": bool(
                self._should_pre_dig_align_before_dig()
            ),
            "pre_dig_align_step_count": int(self._pre_dig_align_step_count),
            "pre_dig_align_hold_count": int(self._pre_dig_align_hold_count),
            "pre_dig_align_timeout_count": int(self._pre_dig_align_timeout_count),
            "pre_dig_align_completed_count": int(self._pre_dig_align_completed_count),
            "pre_dig_align_replan_count": int(self._pre_dig_align_replan_count),
            "pre_dig_align_target_qpos": self._pre_dig_align_target_qpos.astype(float).tolist(),
            "pre_dig_align_error": self._pre_dig_align_error.astype(float).tolist(),
            "pre_dig_align_entry_error_m": float(self._pre_dig_align_entry_error_m),
            "pre_dig_align_start_envelope_ready": bool(
                self._pre_dig_align_start_envelope_ready
            ),
            "pre_dig_align_first_dig_entry_close_handoff": bool(
                self.pre_dig_align_first_dig_entry_close_handoff
            ),
            "pre_dig_align_entry_close_handoff_ready": bool(
                self._pre_dig_align_entry_close_handoff_ready
            ),
            "pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max": float(
                np.nan
                if self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
                is None
                else self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
            ),
            "pre_dig_align_controlled_dims": [
                int(value) for value in self.pre_dig_align_controlled_dims.tolist()
            ],
            "pre_dig_align_bucket_target_qpos": float(
                np.nan
                if self.pre_dig_align_bucket_target_qpos is None
                else self.pre_dig_align_bucket_target_qpos
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
            "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
            "return_target_token_source": str(self._return_target_token_source),
            "return_to_dig_max_entry_error_m": float(
                np.nan
                if self.return_to_dig_max_entry_error_m is None
                else self.return_to_dig_max_entry_error_m
            ),
            "return_to_dig_entry_error_m": float(self._return_to_dig_entry_error_m),
            "return_to_dig_entry_close": int(self._return_to_dig_entry_close_state),
            "pending_dig_cut_cycle_id": int(self._pending_dig_cut_cycle_id),
            "pending_dig_cut_corridor_id": int(self._pending_dig_cut_corridor_id),
            "dig_cut_token_injected": int(self._dig_cut_token_injected),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_token_source": str(self._dig_cut_token_source),
            "dig_cut_token_in_prior_p10_p90": int(
                self._dig_cut_token_in_prior_p10_p90
            ),
            "dig_cut_fallback_reason": str(self._dig_cut_fallback_reason),
            "coverage_selected_corridor_id": int(self._coverage_active_corridor_id),
            "coverage_depleted_count": int(self._coverage_depleted_count()),
            "coverage_completed_dump_count": int(self._coverage_completed_dump_count),
            "coverage_use_env_removed_depth": int(
                self.coverage_use_env_removed_depth
            ),
            "coverage_candidate_layout": str(self.coverage_candidate_layout),
            "coverage_first_dig_strategy": str(self.coverage_first_dig_strategy),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if self.coverage_first_dig_preferred_corridor_id is None
                else self.coverage_first_dig_preferred_corridor_id
            ),
            "coverage_first_dig_max_entry_distance_m": float(
                np.nan
                if self.coverage_first_dig_max_entry_distance_m is None
                else self.coverage_first_dig_max_entry_distance_m
            ),
            "coverage_first_dig_qpos_delta_weight": float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            "coverage_terminal_stop_requested": int(
                self._coverage_terminal_stop_requested
            ),
            "coverage_terminal_stop_reason": str(
                self._coverage_terminal_stop_reason
            ),
            "scripted_bootstrap_timeout_count": int(
                self._scripted_bootstrap_timeout_count
            ),
            "pre_dig_align_enabled": int(self.pre_dig_align_enabled),
            "pre_dig_align_first_dig_only": int(
                self.pre_dig_align_first_dig_only
            ),
            "pre_dig_align_timeout_count": int(self._pre_dig_align_timeout_count),
            "pre_dig_align_completed_count": int(self._pre_dig_align_completed_count),
            "pre_dig_align_replan_count": int(self._pre_dig_align_replan_count),
            "dig_bad_replan_count": int(self._dig_bad_replan_count),
            "dig_exit_guard_replan_count": int(self._dig_exit_guard_replan_count),
        }

    def planner_trace(self) -> dict[str, object]:
        return {
            "cell_entry_trace": list(self._cell_entry_trace),
            "dig_cut_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
            "dig_cut_token_contract": (
                "entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
                "length,actual_removed_depth_delta,payload,valid"
            ),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_prior_path": str(self.dig_cut_prior_path),
            "return_target_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
            "return_target_token_contract": (
                "next entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
                "length,actual_removed_depth_delta,payload,valid"
            ),
            "return_start_envelope_token_contract_version": "return_start_envelope_tokens_v1",
            "return_start_envelope_token_contract": (
                "dig-grid long_norm,short_norm,depth_center,tip_radius,"
                "depth_min,depth_max,contact_allowed,qpos_center[4],"
                "qpos_half_width[4],qvel_abs_max,valid,no_dump_contact_required"
            ),
            "return_target_planner_enabled": bool(
                self.return_target_planner_enabled
            ),
            "coverage_use_env_removed_depth": bool(
                self.coverage_use_env_removed_depth
            ),
            "coverage_candidate_layout": str(self.coverage_candidate_layout),
            "coverage_first_dig_strategy": str(self.coverage_first_dig_strategy),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if self.coverage_first_dig_preferred_corridor_id is None
                else self.coverage_first_dig_preferred_corridor_id
            ),
            "coverage_corridors": [
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ],
            "coverage_terminal_stop_requested": bool(
                self._coverage_terminal_stop_requested
            ),
            "coverage_terminal_stop_reason": str(
                self._coverage_terminal_stop_reason
            ),
        }

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self._should_end_bootstrap(obs=obs, boundary_event=boundary_event):
                if self.bootstrap_end_mode in {"first_qualified_dig_start", "scripted_qpos"}:
                    next_skill = (
                        PRE_DIG_ALIGN_SKILL_NAME
                        if self._should_pre_dig_align_before_dig()
                        else "dig"
                    )
                else:
                    next_skill = "carry"
                self._set_skill(next_skill, f"bootstrap_to_{next_skill}")
            return

        if self._skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            if self._pre_dig_align_ready(obs):
                self._pre_dig_align_completed_count += 1
                self._set_skill("dig", "pre_dig_align_to_dig_ready")
            elif self._pre_dig_align_step_count >= self.pre_dig_align_max_steps:
                self._pre_dig_align_timeout_count += 1
                if self._pre_dig_align_timeout_can_handoff(obs):
                    self._set_skill("dig", "pre_dig_align_to_dig_timeout_close_enough")
                else:
                    self._reject_active_coverage_corridor(
                        obs,
                        reason="align_entry_gap_timeout",
                    )
                    if not self._try_replan_pre_dig_align_handoff(obs):
                        self._restart_pre_dig_align("pre_dig_align_retry_entry_gap")
            return

        if self._skill_name == "dig":
            if self._dig_exit_guard_ready(obs):
                self._dig_exit_guard_replan_count += 1
                self._reject_active_coverage_corridor(
                    obs,
                    reason="exit_overshoot_low_payload",
                )
                if self._should_pre_dig_align_before_dig():
                    self._restart_pre_dig_align(
                        "dig_to_pre_dig_align_exit_overshoot_low_payload"
                    )
                else:
                    self._restart_dig_with_new_cut(
                        "dig_retry_exit_overshoot_low_payload"
                    )
                return
            if self._dig_bad_replan_ready(obs):
                self._dig_bad_replan_count += 1
                self._reject_active_coverage_corridor(
                    obs,
                    reason="bad_dig_low_payload",
                )
                if self._should_pre_dig_align_before_dig():
                    self._restart_pre_dig_align(
                        "dig_to_pre_dig_align_bad_dig_low_payload"
                    )
                else:
                    self._restart_dig_with_new_cut("dig_retry_bad_dig_low_payload")
                return
            if self._dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
                self._complete_cell_entry_dig(obs)
                self._complete_coverage_dig(obs)
                reason = self._dig_to_carry_reason or "loaded"
                self._set_skill("carry", f"dig_to_carry_{reason}")
            return

        if self._skill_name == "carry":
            dump_committed_event = bool(
                boundary_event is not None
                and getattr(boundary_event, "dump_committed_start", False)
            )
            legacy_dump_start_event = bool(
                boundary_event is not None
                and getattr(boundary_event, "dump_start", False)
                and not self._semantic_boundary_profile_active()
            )
            if dump_committed_event or legacy_dump_start_event:
                self._dump_ready_hold_count = self.dump_ready_hold_steps
            elif (
                not self._semantic_boundary_profile_active()
                and self._dump_ready(obs)
            ):
                self._dump_ready_hold_count += 1
            else:
                self._dump_ready_hold_count = 0
            if self._dump_ready_hold_count >= self.dump_ready_hold_steps:
                self._dump_start_deposited_mass_kg = self._deposited_mass(obs)
                reason = (
                    "dump_committed_boundary"
                    if dump_committed_event
                    else "dump_start_boundary"
                    if legacy_dump_start_event
                    else "target_ready"
                )
                self._set_skill("dump", f"carry_to_dump_{reason}")
            return

        if self._skill_name == "dump":
            if (
                self.dump_done_use_boundary_event
                and boundary_event is not None
                and bool(
                    getattr(boundary_event, "dump_complete", False)
                    or (
                        getattr(boundary_event, "dump_end", False)
                        and not self._semantic_boundary_profile_active()
                    )
                )
            ):
                reason = (
                    "dump_complete_boundary"
                    if bool(getattr(boundary_event, "dump_complete", False))
                    else "dump_end_boundary"
                )
                self._complete_coverage_dump(obs, reason=reason)
                self._set_skill(
                    "return",
                    "dump_to_return_dump_complete_boundary"
                    if reason == "dump_complete_boundary"
                    else "dump_to_return_dump_end",
                )
                return
            if not self._semantic_boundary_profile_active() and self._dump_done(obs):
                self._dump_done_hold_count += 1
            else:
                self._dump_done_hold_count = 0
            if self._dump_done_hold_count >= self.dump_done_hold_steps:
                self._complete_coverage_dump(obs, reason="dump_mass_low")
                self._set_skill("return", "dump_to_return_mass_low")
            return

        if self._skill_name == "return":
            self._return_to_dig_entry_close(obs)
            next_dig_event = bool(
                boundary_event is not None
                and (
                    getattr(boundary_event, "next_dig_entry_ready", False)
                    or getattr(boundary_event, "qualified_dig_start", False)
                )
            )
            if next_dig_event and self._return_to_dig_entry_close(obs):
                self._completed_transition_count += 1
                self._cycle_index += 1
                next_skill = (
                    PRE_DIG_ALIGN_SKILL_NAME
                    if self._should_pre_dig_align_before_dig()
                    else "dig"
                )
                self._set_skill(
                    next_skill,
                    f"return_to_{next_skill}_next_dig_entry_ready",
                )
                return
            if self._return_to_dig_shallow_guard_ready(
                obs=obs,
                boundary_event=boundary_event,
            ) and self._return_to_dig_entry_close(obs):
                self._completed_transition_count += 1
                self._cycle_index += 1
                next_skill = (
                    PRE_DIG_ALIGN_SKILL_NAME
                    if self._should_pre_dig_align_before_dig()
                    else "dig"
                )
                self._set_skill(
                    next_skill,
                    f"return_to_{next_skill}_shallow_entry_guard",
                )
                return

    def _set_skill(self, skill_name: str, reason: str) -> None:
        if skill_name == self._skill_name:
            return
        self._skill_name = str(skill_name)
        self._switch_reason = str(reason)
        if skill_name != PRE_DIG_ALIGN_SKILL_NAME:
            self._active_policy().reset()
        if skill_name == "carry":
            self._dump_ready_hold_count = 0
        elif skill_name == "dump":
            self._dump_done_hold_count = 0
        elif skill_name == "return":
            self._return_step_count = 0
        elif skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            self._pre_dig_align_step_count = 0
            self._pre_dig_align_hold_count = 0
            self._pre_dig_align_entry_close_handoff_ready = False
        elif skill_name == "dig":
            self._dump_ready_hold_count = 0
            self._dump_done_hold_count = 0
            self._coverage_current_payload_gain_kg = 0.0
            self._dig_step_count = 0
            self._dig_best_mass_kg = 0.0
            self._dig_mass_plateau_count = 0
            self._dig_to_carry_reason = ""
        if skill_name not in {"dig", PRE_DIG_ALIGN_SKILL_NAME}:
            self._clear_dig_cut_plan()

    def _restart_pre_dig_align(self, reason: str) -> None:
        self._skill_name = PRE_DIG_ALIGN_SKILL_NAME
        self._switch_reason = str(reason)
        self._pre_dig_align_step_count = 0
        self._pre_dig_align_hold_count = 0
        self._pre_dig_align_replan_count += 1
        self._dig_step_count = 0
        self._dig_best_mass_kg = 0.0
        self._dig_mass_plateau_count = 0
        self._dig_to_carry_reason = ""
        self._coverage_current_payload_gain_kg = 0.0
        self._coverage_active_corridor_id = -1
        self._clear_dig_cut_plan()

    def _try_replan_pre_dig_align_handoff(self, obs: dict) -> bool:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return False
        self._coverage_active_corridor_id = -1
        self._clear_dig_cut_plan()
        try:
            token, raw_fields, source, fallback_reason = (
                self._build_operator_prior_coverage_dig_cut_tokens(obs)
            )
        except Exception:
            return False
        self._dig_cut_tokens = np.asarray(token, dtype=np.float32).copy()
        self._dig_cut_planned_cycle_id = int(self._cycle_index)
        self._dig_cut_token_source = str(source)
        self._dig_cut_fallback_reason = str(fallback_reason)
        self._dig_cut_token_in_prior_p10_p90 = self._raw_fields_in_prior_range(
            raw_fields
        )
        self._pre_dig_align_entry_error_m = float(self._pre_dig_align_entry_error(obs))
        if not self._pre_dig_align_timeout_can_handoff(obs):
            return False
        self._pre_dig_align_replan_count += 1
        self._pre_dig_align_completed_count += 1
        self._pre_dig_align_step_count = 0
        self._pre_dig_align_hold_count = 0
        self._set_skill("dig", "pre_dig_align_replan_to_dig_entry_close")
        return True

    def _restart_dig_with_new_cut(self, reason: str) -> None:
        self._skill_name = "dig"
        self._switch_reason = str(reason)
        self._active_policy().reset()
        self._dig_step_count = 0
        self._dig_best_mass_kg = 0.0
        self._dig_mass_plateau_count = 0
        self._dig_to_carry_reason = ""
        self._coverage_current_payload_gain_kg = 0.0
        self._coverage_active_corridor_id = -1
        self._clear_dig_cut_plan()

    def _should_pre_dig_align_before_dig(self) -> bool:
        if not self.pre_dig_align_enabled:
            return False
        if not self.pre_dig_align_first_dig_only:
            return True
        return int(getattr(self, "_cycle_index", 0)) == 0

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

    def _pre_dig_align_ready(self, obs: dict) -> bool:
        if not self.pre_dig_align_enabled:
            return True
        target_qpos = self._pre_dig_align_target(obs)
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        qvel = np.asarray(
            obs.get("qvel", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        self._pre_dig_align_error = (target_qpos - qpos).astype(np.float32)
        entry_error = self._pre_dig_align_entry_error(obs)
        self._pre_dig_align_entry_error_m = float(entry_error)
        controlled = self.pre_dig_align_controlled_dims
        qpos_close = bool(
            np.all(
                np.abs(self._pre_dig_align_error[controlled])
                <= self.pre_dig_align_qpos_tolerance[controlled]
            )
            if np.any(controlled)
            else True
        )
        qvel_small = bool(
            np.all(np.abs(qvel[controlled]) <= self.pre_dig_align_qvel_abs_max)
            if np.any(controlled)
            else True
        )
        entry_close = self._pre_dig_align_entry_close(
            entry_error,
            threshold=self.pre_dig_align_max_entry_error_m,
        )
        start_envelope_ready = self._pre_dig_align_start_envelope_ready_for_state(
            obs=obs,
            qpos=qpos,
            entry_error=entry_error,
        )
        self._pre_dig_align_start_envelope_ready = bool(start_envelope_ready)
        entry_close_handoff_ready = (
            self._pre_dig_align_entry_close_handoff_ready_for_state(
                entry_error=entry_error,
                qvel=qvel,
                start_envelope_ready=start_envelope_ready,
            )
        )
        self._pre_dig_align_entry_close_handoff_ready = bool(
            entry_close_handoff_ready
        )
        if entry_close_handoff_ready or (
            qpos_close and qvel_small and (entry_close or start_envelope_ready)
        ):
            self._pre_dig_align_hold_count += 1
        else:
            self._pre_dig_align_hold_count = 0
        return bool(self._pre_dig_align_hold_count >= self.pre_dig_align_hold_steps)

    def _pre_dig_align_entry_close(
        self,
        entry_error: float,
        *,
        threshold: float | None,
    ) -> bool:
        if threshold is None:
            return True
        return bool(np.isfinite(entry_error) and float(entry_error) <= float(threshold))

    def _pre_dig_align_entry_close_handoff_ready_for_state(
        self,
        *,
        entry_error: float,
        qvel: np.ndarray,
        start_envelope_ready: bool,
    ) -> bool:
        if not self.pre_dig_align_first_dig_entry_close_handoff:
            return False
        if int(getattr(self, "_cycle_index", 0)) != 0:
            return False
        if (
            self.pre_dig_align_start_envelope_enabled
            and not bool(start_envelope_ready)
        ):
            return False
        if not self._pre_dig_align_entry_close(
            entry_error,
            threshold=self.pre_dig_align_max_entry_error_m,
        ):
            return False
        qvel_abs_max = self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
        if qvel_abs_max is None:
            qvel_abs_max = self.pre_dig_align_qvel_abs_max
        controlled = self.pre_dig_align_controlled_dims
        if not np.any(controlled):
            return True
        return bool(np.all(np.abs(qvel[controlled]) <= float(qvel_abs_max)))

    def _pre_dig_align_timeout_can_handoff(self, obs: dict) -> bool:
        threshold = self.pre_dig_align_timeout_accept_entry_error_m
        if threshold is None:
            threshold = self.pre_dig_align_max_entry_error_m
        if threshold is None:
            return True
        entry_error = self._pre_dig_align_entry_error(obs)
        self._pre_dig_align_entry_error_m = float(entry_error)
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        start_envelope_ready = self._pre_dig_align_start_envelope_ready_for_state(
            obs=obs,
            qpos=qpos,
            entry_error=entry_error,
        )
        self._pre_dig_align_start_envelope_ready = bool(start_envelope_ready)
        return bool(
            self._pre_dig_align_entry_close(entry_error, threshold=threshold)
            or start_envelope_ready
        )

    def _pre_dig_align_start_envelope_ready_for_state(
        self,
        *,
        obs: dict,
        qpos: np.ndarray,
        entry_error: float,
    ) -> bool:
        if not self.pre_dig_align_start_envelope_enabled:
            return False
        if (
            not np.isfinite(entry_error)
            or float(entry_error) > self.pre_dig_align_start_envelope_max_entry_error_m
        ):
            return False
        if not np.all(qpos >= self.pre_dig_align_start_qpos_min):
            return False
        if not np.all(qpos <= self.pre_dig_align_start_qpos_max):
            return False
        pose = self._bucket_dig_area_pose(obs)
        if pose is None:
            return False
        pose_arr = np.asarray(pose, dtype=np.float32).reshape(3)
        return bool(
            np.all(pose_arr >= self.pre_dig_align_start_pose_min)
            and np.all(pose_arr <= self.pre_dig_align_start_pose_max)
        )

    def _pre_dig_align_action(self, obs: dict) -> np.ndarray:
        if not self.pre_dig_align_enabled:
            raise RuntimeError("pre-dig align action requested while disabled.")
        self._pre_dig_align_step_count += 1
        target_qpos = self._pre_dig_align_target(obs)
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        qvel = np.asarray(
            obs.get("qvel", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        self._pre_dig_align_error = (target_qpos - qpos).astype(np.float32)
        self._pre_dig_align_entry_error_m = float(
            self._pre_dig_align_entry_error(obs)
        )
        action = _pd_servo_action(
            qpos=qpos,
            qvel=qvel,
            target_qpos=target_qpos,
            kp=self.pre_dig_align_kp,
            kd=self.pre_dig_align_kd,
            action_clip=self.pre_dig_align_action_clip,
            action_signs=self.pre_dig_align_action_signs,
        )
        action[~self.pre_dig_align_controlled_dims] = 0.0
        return action

    def _pre_dig_align_target(self, obs: dict) -> np.ndarray:
        self._ensure_dig_cut_plan_for_cycle(obs)
        token = np.asarray(self._dig_cut_tokens, dtype=np.float32).reshape(-1)
        return self._pre_dig_align_target_from_token(
            token=token,
            obs=obs,
            update_state=True,
        )

    def _pre_dig_align_target_from_token(
        self,
        *,
        token: np.ndarray,
        obs: dict,
        update_state: bool,
    ) -> np.ndarray:
        token = np.asarray(token, dtype=np.float32).reshape(-1)
        if len(token) < 2:
            token = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        features = np.asarray([1.0, float(token[0]), float(token[1])], dtype=np.float32)
        target = self.pre_dig_align_qpos_from_token_coefficients @ features
        target = np.clip(target, self.pre_dig_align_qpos_min, self.pre_dig_align_qpos_max)
        if self.pre_dig_align_bucket_target_qpos is not None and self.action_dim >= 4:
            target[3] = float(
                np.clip(
                    self.pre_dig_align_bucket_target_qpos,
                    self.pre_dig_align_qpos_min[3],
                    self.pre_dig_align_qpos_max[3],
                )
            )
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        target[~self.pre_dig_align_controlled_dims] = qpos[
            ~self.pre_dig_align_controlled_dims
        ]
        target = target.astype(np.float32)
        if update_state:
            self._pre_dig_align_target_qpos = target.copy()
        return target.copy()

    def _pre_dig_align_entry_error(self, obs: dict) -> float:
        pose = self._bucket_tip_dig_area_pose(obs)
        corridor = self._coverage_active_corridor()
        if pose is None or corridor is None:
            return float("nan")
        dx = float(pose[0]) - float(corridor.entry_x_m)
        dz = float(pose[2]) - float(corridor.entry_z_m)
        return float(np.hypot(dx, dz))

    def _update_dig_progress(self, obs: dict) -> None:
        self._dig_step_count += 1
        mass = self._mass_in_bucket(obs)
        previous_best = float(self._dig_best_mass_kg)
        if mass > previous_best + self.dig_to_carry_mass_plateau_epsilon_kg:
            self._dig_best_mass_kg = float(mass)
            self._dig_mass_plateau_count = 0
        else:
            self._dig_best_mass_kg = max(previous_best, float(mass))
            self._dig_mass_plateau_count += 1
        self._coverage_current_payload_gain_kg = max(
            float(self._coverage_current_payload_gain_kg),
            float(mass),
        )

    def _dig_bad_replan_ready(self, obs: dict) -> bool:
        if not self.dig_bad_replan_enabled:
            return False
        if self._coverage_terminal_stop_requested:
            return False
        if self._dig_step_count < self.dig_bad_replan_max_steps:
            return False
        return bool(self._mass_in_bucket(obs) < self.dig_bad_replan_min_bucket_mass_kg)

    def _dig_exit_guard_ready(self, obs: dict) -> bool:
        if not self.dig_exit_guard_enabled:
            return False
        if self._coverage_terminal_stop_requested:
            return False
        if self._dig_step_count < self.dig_exit_guard_min_steps:
            return False
        if self._mass_in_bucket(obs) >= self.dig_exit_guard_min_bucket_mass_kg:
            return False
        overshoot = self._dig_exit_overshoot_m(obs)
        return bool(
            np.isfinite(overshoot)
            and overshoot >= self.dig_exit_guard_overshoot_m
        )

    def _dig_exit_overshoot_m(self, obs: dict) -> float:
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return float("nan")
        pose = self._bucket_tip_dig_area_pose(obs)
        if pose is None:
            return float("nan")
        entry = np.asarray(
            [float(corridor.entry_x_m), float(corridor.entry_z_m)],
            dtype=np.float32,
        )
        exit_point = np.asarray(
            [float(corridor.exit_x_m), float(corridor.exit_z_m)],
            dtype=np.float32,
        )
        tip = np.asarray([float(pose[0]), float(pose[2])], dtype=np.float32)
        direction = exit_point - entry
        length = float(np.linalg.norm(direction))
        if length <= 1.0e-6 or not np.all(np.isfinite(tip)):
            return float("nan")
        unit = direction / length
        progress = float(np.dot(tip - entry, unit))
        return float(progress - length)

    def _dig_to_carry_ready(self, *, obs: dict, boundary_event: Any | None) -> bool:
        if boundary_event is not None and bool(
            getattr(boundary_event, "dig_complete", False)
        ):
            self._dig_to_carry_reason = "dig_complete_boundary"
            return True
        if self._semantic_boundary_profile_active():
            self._dig_to_carry_reason = ""
            return False
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        mass = float(metrics.get("mass_in_bucket_kg", self._mass_in_bucket(obs)))
        dig_distance = float(
            metrics.get("min_distance_to_dig_area_m", self._min_distance_to_dig_area(obs))
        )
        distance_ready = bool(
            dig_distance >= self.dig_to_carry_min_distance_to_dig_area_m
        )
        if mass >= self.dig_to_carry_target_bucket_mass_kg and distance_ready:
            if (
                abs(
                    self.dig_to_carry_target_bucket_mass_kg
                    - self.dig_to_carry_min_bucket_mass_kg
                )
                <= 1.0e-6
            ):
                self._dig_to_carry_reason = "loaded"
            else:
                self._dig_to_carry_reason = "target_payload_loaded"
            return True
        if (
            self.dig_to_carry_mass_plateau_enabled
            and self._dig_step_count >= self.dig_to_carry_mass_plateau_min_steps
            and mass >= self.dig_to_carry_mass_plateau_min_bucket_mass_kg
            and self._dig_mass_plateau_count
            >= self.dig_to_carry_mass_plateau_hold_steps
            and distance_ready
        ):
            self._dig_to_carry_reason = "mass_plateau"
            return True
        self._dig_to_carry_reason = ""
        return False

    def _semantic_boundary_profile_active(self) -> bool:
        config = getattr(self.boundary_detector, "config", None)
        profile = str(getattr(config, "boundary_profile", "legacy"))
        return profile == "v2_4_5_spatial_mass"

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
        if not position_ok:
            position_ok = self._dump_area_relative_near_window_ok(
                geometry=geometry,
                over_footprint=over_footprint,
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

    def _dump_area_relative_near_window_ok(
        self,
        *,
        geometry: dict[str, float],
        over_footprint: bool,
    ) -> bool:
        if not self.dump_ready_near_window_enabled:
            return False
        if self.dump_ready_near_window_require_over_footprint and not over_footprint:
            return False
        if self.dump_ready_max_dump_area_footprint_outside_distance_m is None:
            return False
        outside_distance = float(
            geometry.get("bucket_dump_area_footprint_outside_distance_m", np.nan)
        )
        outside_limit = (
            self.dump_ready_max_dump_area_footprint_outside_distance_m
            + self.dump_ready_near_window_outside_tolerance_m
        )
        outside_ok = bool(
            np.isfinite(outside_distance)
            and outside_distance >= 0.0
            and outside_distance <= outside_limit + 1.0e-6
        )
        if not outside_ok:
            return False
        return bool(
            self._optional_range_near_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_x_m",
                min_value=self.dump_ready_min_dump_area_relative_x_m,
                max_value=self.dump_ready_max_dump_area_relative_x_m,
                tolerance=self.dump_ready_near_window_x_tolerance_m,
            )
            and self._optional_range_near_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_z_m",
                min_value=self.dump_ready_min_dump_area_relative_z_m,
                max_value=self.dump_ready_max_dump_area_relative_z_m,
                tolerance=self.dump_ready_near_window_z_tolerance_m,
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

    @staticmethod
    def _optional_range_near_ok(
        *,
        geometry: dict[str, float],
        name: str,
        min_value: float | None,
        max_value: float | None,
        tolerance: float,
    ) -> bool:
        if min_value is None and max_value is None:
            return True
        value = float(geometry.get(name, np.nan))
        if not np.isfinite(value):
            return False
        tol = max(0.0, float(tolerance))
        if min_value is not None and value < min_value - tol - 1.0e-6:
            return False
        if max_value is not None and value > max_value + tol + 1.0e-6:
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

    def _return_to_dig_shallow_guard_ready(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        if not self.return_to_dig_shallow_guard_enabled:
            return False
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        mass = float(metrics.get("mass_in_bucket_kg", self._mass_in_bucket(obs)))
        distance = float(
            metrics.get("min_distance_to_dig_area_m", self._min_distance_to_dig_area(obs))
        )
        depth = float(
            metrics.get(
                "bucket_depth_below_dig_area_plane_m",
                self._bucket_depth_below_dig_area_plane(obs),
            )
        )
        entry_guard_ready = bool(
            self.return_to_dig_max_entry_error_m is not None
            and self._return_to_dig_entry_close(obs)
        )
        depth_below_max = bool(depth <= self.return_to_dig_max_depth_m)
        return bool(
            mass <= self.return_to_dig_max_bucket_mass_kg
            and distance <= self.return_to_dig_touch_tolerance_m
            and depth >= self.return_to_dig_min_depth_m
            and (depth_below_max or entry_guard_ready)
        )

    def _return_to_dig_entry_close(self, obs: dict) -> bool:
        if self._skill_name == "return" and self.return_target_planner_enabled:
            self._ensure_return_target_plan_for_cycle(obs)
        entry_error = self._return_to_dig_entry_error_for_obs(obs)
        self._return_to_dig_entry_error_m = float(entry_error)
        if self.return_to_dig_max_entry_error_m is None:
            self._return_to_dig_entry_close_state = True
            return True
        if not np.isfinite(entry_error):
            self._return_to_dig_entry_close_state = True
            return True
        close = bool(float(entry_error) <= float(self.return_to_dig_max_entry_error_m))
        self._return_to_dig_entry_close_state = close
        return close

    def _return_to_dig_entry_error_for_obs(self, obs: dict) -> float:
        target = self._return_to_dig_entry_target()
        pose = self._bucket_dig_area_pose(obs)
        if target is None or pose is None:
            return float("nan")
        bucket_x, _, bucket_z = pose
        entry_x, entry_z = target
        if not all(np.isfinite(value) for value in (bucket_x, bucket_z, entry_x, entry_z)):
            return float("nan")
        return float(
            np.hypot(float(bucket_x) - float(entry_x), float(bucket_z) - float(entry_z))
        )

    def _return_to_dig_entry_target(self) -> tuple[float, float] | None:
        raw_fields = self._pending_dig_cut_raw_fields
        if (
            raw_fields is not None
            and int(self._pending_dig_cut_cycle_id) == int(self._cycle_index) + 1
        ):
            entry_x = float(raw_fields.get("operator_entry_x_m", float("nan")))
            entry_z = float(raw_fields.get("operator_entry_z_m", float("nan")))
            if np.isfinite(entry_x) and np.isfinite(entry_z):
                return entry_x, entry_z
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return None
        return float(corridor.entry_x_m), float(corridor.entry_z_m)

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

    def _bucket_depth_below_dig_area_plane(self, obs: dict) -> float:
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if "bucket_depth_below_dig_area_plane_m" in task_metrics:
            return float(task_metrics["bucket_depth_below_dig_area_plane_m"])
        env_state = self._env_state(obs)
        return (
            float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX])
            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
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
        self._return_target_token_injected = False
        self._return_start_envelope_token_injected = False
        goal_tokens = self._goal_tokens()
        cell_entry_tokens = self._cell_entry_tokens_for_obs(obs)
        dig_cut_tokens = self._dig_cut_tokens_for_obs(obs)
        return_target_tokens = self._return_target_tokens_for_obs(obs)
        return_start_envelope_tokens = (
            self._return_start_envelope_tokens_for_obs(obs)
        )
        if (
            goal_tokens is None
            and cell_entry_tokens is None
            and dig_cut_tokens is None
            and return_target_tokens is None
            and return_start_envelope_tokens is None
        ):
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
        if return_target_tokens is not None:
            policy_obs["return_target_tokens"] = return_target_tokens
            self._return_target_token_injected = True
        if return_start_envelope_tokens is not None:
            policy_obs["return_start_envelope_tokens_v1"] = return_start_envelope_tokens
            self._return_start_envelope_token_injected = True
        return policy_obs

    def _return_target_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self._return_target_tokens.copy()

    def _return_start_envelope_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self._return_start_envelope_tokens.copy()

    def _ensure_return_target_plan_for_cycle(self, obs: dict) -> None:
        if not self.return_target_planner_enabled:
            return
        if (
            self.return_target_hold_token_until_skill_exit
            and self._return_target_planned_cycle_id == int(self._cycle_index)
        ):
            return
        try:
            token, raw_fields, source, fallback_reason, corridor_id = (
                self._build_next_dig_cut_plan_for_return(obs)
            )
            self._return_target_tokens = token.astype(np.float32)
            self._return_start_envelope_tokens = (
                self._build_return_start_envelope_tokens_for_obs(obs, raw_fields)
            )
            self._return_target_token_source = str(source)
            self._return_target_fallback_reason = str(fallback_reason)
            self._return_target_planned_cycle_id = int(self._cycle_index)
            self._pending_dig_cut_cycle_id = int(self._cycle_index) + 1
            self._pending_dig_cut_raw_fields = dict(raw_fields)
            self._pending_dig_cut_tokens = token.astype(np.float32)
            self._pending_dig_cut_corridor_id = int(corridor_id)
        except Exception as exc:
            self._return_target_tokens = np.zeros(
                RETURN_TARGET_TOKEN_DIM,
                dtype=np.float32,
            )
            self._return_start_envelope_tokens = np.zeros(
                RETURN_START_ENVELOPE_TOKEN_DIM,
                dtype=np.float32,
            )
            self._return_target_token_source = "fallback_zero"
            self._return_target_fallback_reason = str(exc)
            self._return_target_planned_cycle_id = int(self._cycle_index)

    def _dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if not self.dig_cut_planner_enabled:
            return None
        if self._skill_name != "dig":
            if (
                self._skill_name != BOOTSTRAP_SKILL_NAME
                or self.bootstrap_policy is None
            ):
                return None
        self._ensure_dig_cut_plan_for_cycle(obs)
        return self._dig_cut_tokens.copy()

    def _ensure_dig_cut_plan_for_cycle(self, obs: dict) -> None:
        if not self.dig_cut_planner_enabled:
            return
        if (
            self.dig_cut_hold_token_until_skill_exit
            and self._dig_cut_planned_cycle_id == int(self._cycle_index)
        ):
            return
        self._dig_cut_tokens = self._build_dig_cut_tokens_for_obs(obs)
        self._dig_cut_planned_cycle_id = int(self._cycle_index)

    def _build_dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray:
        self._dig_cut_fallback_reason = ""
        if (
            self._pending_dig_cut_tokens is not None
            and self._pending_dig_cut_cycle_id == int(self._cycle_index)
        ):
            self._dig_cut_token_source = "pending_return_target"
            self._dig_cut_fallback_reason = ""
            self._dig_cut_token_in_prior_p10_p90 = (
                False
                if self._pending_dig_cut_raw_fields is None
                else self._raw_fields_in_prior_range(self._pending_dig_cut_raw_fields)
            )
            self._coverage_active_corridor_id = int(self._pending_dig_cut_corridor_id)
            self._coverage_last_selected_corridor_id = int(
                self._pending_dig_cut_corridor_id
            )
            self._coverage_current_payload_gain_kg = 0.0
            self._coverage_cycle_start_deposit_kg = self._deposited_mass(obs)
            return np.asarray(self._pending_dig_cut_tokens, dtype=np.float32).copy()
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
        if self.dig_cut_planner_mode == "operator_prior_coverage":
            try:
                token, raw_fields, source, fallback_reason = (
                    self._build_operator_prior_coverage_dig_cut_tokens(obs)
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
        if self.dig_cut_planner_mode == "operator_prior_sweep_belief":
            try:
                token, raw_fields, source, fallback_reason = (
                    self._build_operator_prior_coverage_dig_cut_tokens(obs)
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

    def _build_next_dig_cut_plan_for_return(
        self,
        obs: dict,
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        if self.dig_cut_planner_mode == "conservative_pose":
            raw_fields = self._raw_fields_from_live_pose(obs)
            return (
                _build_dig_cut_token(raw_fields),
                raw_fields,
                f"{self.return_target_token_source_prefix}_conservative_pose",
                "",
                -1,
            )
        if self.dig_cut_planner_mode == "operator_prior":
            token, raw_fields, source, fallback_reason = (
                self._build_operator_prior_dig_cut_tokens(obs)
            )
            return (
                token,
                raw_fields,
                f"{self.return_target_token_source_prefix}_{source}",
                fallback_reason,
                -1,
            )
        if self.dig_cut_planner_mode in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            corridor = self._select_next_coverage_corridor(obs)
            self._coverage_active_corridor_id = int(corridor.corridor_id)
            raw_fields = self._coverage_raw_fields(corridor)
            return (
                _build_dig_cut_token(raw_fields),
                raw_fields,
                f"{self.return_target_token_source_prefix}_{self.dig_cut_planner_mode}",
                "",
                int(corridor.corridor_id),
            )
        raise ValueError(f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}.")

    def _build_return_start_envelope_tokens_for_obs(
        self,
        obs: dict,
        raw_fields: dict[str, float | int],
    ) -> np.ndarray:
        token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
        env_state = self._env_state(obs)
        if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX:
            token[0] = float(env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX])
        if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
            token[1] = float(env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX])
        token[2] = float(
            max(0.0, float(raw_fields.get("operator_cut_depth_peak_m", 0.08)))
        )
        token[3] = 0.20
        token[4] = float(max(0.0, token[2] - 0.08))
        token[5] = float(token[2] + 0.08)
        token[6] = 0.0
        qpos = np.asarray(obs.get("qpos", np.zeros(self.action_dim)), dtype=np.float32).reshape(-1)
        qvel = np.asarray(obs.get("qvel", np.zeros(self.action_dim)), dtype=np.float32).reshape(-1)
        if qpos.size >= 4 and np.all(np.isfinite(qpos[:4])):
            token[7:11] = qpos[:4]
            token[11:15] = np.asarray([0.05, 0.05, 0.05, 0.05], dtype=np.float32)
            token[16] = 1.0
        if qvel.size >= 4:
            token[15] = float(np.max(np.abs(qvel[:4])))
        token[17] = 1.0
        return token.astype(np.float32)

    def _raw_fields_from_live_pose(self, obs: dict) -> dict[str, float | int]:
        pose = self._bucket_dig_area_pose(obs)
        if pose is None:
            return {
                "operator_entry_x_m": 0.0,
                "operator_entry_y_m": 0.0,
                "operator_entry_z_m": 0.0,
                "operator_exit_x_m": 0.0,
                "operator_exit_y_m": 0.0,
                "operator_exit_z_m": 0.0,
                "operator_cut_direction_x": 0.0,
                "operator_cut_direction_y": 0.0,
                "operator_cut_direction_z": 0.0,
                "operator_cut_length_m": 0.0,
                "operator_cut_depth_peak_m": 0.0,
                "operator_cut_payload_gain_kg": 0.0,
                "operator_cut_valid": 0,
            }
        entry_x, entry_y, entry_z = float(pose[0]), float(pose[1]), float(pose[2])
        exit_x = entry_x - 1.2
        exit_z = entry_z
        return {
            "operator_entry_x_m": entry_x,
            "operator_entry_y_m": entry_y,
            "operator_entry_z_m": entry_z,
            "operator_exit_x_m": exit_x,
            "operator_exit_y_m": entry_y,
            "operator_exit_z_m": exit_z,
            "operator_cut_direction_x": -1.0,
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": 0.0,
            "operator_cut_length_m": 1.2,
            "operator_cut_depth_peak_m": 0.08,
            "operator_cut_payload_gain_kg": 55.0,
            "operator_cut_valid": 1,
        }

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

    def _build_operator_prior_coverage_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        corridor = self._select_next_coverage_corridor(obs)
        self._coverage_current_payload_gain_kg = 0.0
        self._coverage_cycle_start_deposit_kg = self._deposited_mass(obs)
        raw_fields = self._coverage_raw_fields(corridor)
        return (
            _build_dig_cut_token(raw_fields),
            raw_fields,
            "operator_prior_coverage",
            "",
        )

    def _select_next_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        if not self.dig_cut_prior:
            raise ValueError(
                f"{self.dig_cut_planner_mode} mode requires a dig cut prior JSON."
            )
        self._ensure_coverage_corridors()
        if not self._coverage_corridors:
            raise ValueError(
                f"{self.dig_cut_planner_mode} could not build candidate corridors."
            )
        corridor = self._select_coverage_corridor(obs)
        self._coverage_active_corridor_id = int(corridor.corridor_id)
        self._coverage_last_selected_corridor_id = int(corridor.corridor_id)
        return corridor

    def _ensure_coverage_corridors(self) -> None:
        if self._coverage_corridors:
            return
        fields = dict(self.dig_cut_prior.get("fields", {}))
        if self.coverage_candidate_layout == "cell_weighted_3x2":
            self._coverage_corridors = self._build_cell_weighted_coverage_corridors(fields)
            return

        candidates: list[CoverageCorridorState] = []
        corridor_id = 0
        for z_index, z_percentile in enumerate(self.coverage_entry_z_percentiles):
            for x_index, x_percentile in enumerate(self.coverage_entry_x_percentiles):
                entry_x = self._prior_percentile(fields, "entry_x_m", x_percentile)
                entry_z = self._prior_percentile(fields, "entry_z_m", z_percentile)
                exit_x, exit_z = self._coverage_exit_from_entry(entry_x, entry_z)
                cell_id = self._coverage_cell_id_from_percentile_indices(
                    x_index=x_index,
                    x_count=len(self.coverage_entry_x_percentiles),
                    z_index=z_index,
                    z_count=len(self.coverage_entry_z_percentiles),
                )
                candidates.append(
                    CoverageCorridorState(
                        corridor_id=corridor_id,
                        entry_x_m=float(entry_x),
                        entry_z_m=float(entry_z),
                        exit_x_m=float(exit_x),
                        exit_z_m=float(exit_z),
                        cell_id=int(cell_id),
                    )
                )
                corridor_id += 1
        self._coverage_corridors = candidates

    def _build_cell_weighted_coverage_corridors(
        self,
        fields: dict[str, object],
    ) -> list[CoverageCorridorState]:
        raw_cells = self.dig_cut_prior.get("coverage_cells", [])
        if not isinstance(raw_cells, list) or not raw_cells:
            raise ValueError(
                "coverage.candidate_layout='cell_weighted_3x2' requires "
                "coverage_cells in the dig cut prior."
            )
        cells = [dict(item) for item in raw_cells if isinstance(item, dict)]
        if not cells:
            raise ValueError(
                "coverage.candidate_layout='cell_weighted_3x2' found no valid "
                "coverage_cells in the dig cut prior."
            )

        candidates: list[CoverageCorridorState] = []
        for corridor_id, cell in enumerate(
            sorted(cells, key=lambda item: int(item.get("cell_id", 999999)))
        ):
            entry = dict(cell.get("entry", {}) or {})
            exit_point = dict(cell.get("exit", {}) or {})
            entry_x = self._coverage_cell_float(
                entry,
                "x_m",
                self._prior_percentile(fields, "entry_x_m", "p50"),
            )
            entry_z = self._coverage_cell_float(
                entry,
                "z_m",
                self._prior_percentile(fields, "entry_z_m", "p50"),
            )
            if "x_m" in exit_point and "z_m" in exit_point:
                exit_x = self._coverage_cell_float(
                    exit_point,
                    "x_m",
                    self._prior_percentile(fields, "exit_x_m", "p50"),
                )
                exit_z = self._coverage_cell_float(
                    exit_point,
                    "z_m",
                    self._prior_percentile(fields, "exit_z_m", "p50"),
                )
            else:
                exit_x, exit_z = self._coverage_exit_from_entry(entry_x, entry_z)
            candidates.append(
                CoverageCorridorState(
                    corridor_id=int(corridor_id),
                    entry_x_m=float(entry_x),
                    entry_z_m=float(entry_z),
                    exit_x_m=float(exit_x),
                    exit_z_m=float(exit_z),
                    cell_id=int(cell.get("cell_id", corridor_id)),
                    source_count=max(0, int(cell.get("source_count", 0))),
                    source_fraction=max(0.0, float(cell.get("source_fraction", 0.0))),
                    cut_depth_peak_m=self._coverage_cell_float(
                        cell,
                        "cut_depth_peak_m",
                        self._prior_percentile(
                            fields,
                            "cut_depth_peak_m",
                            self.coverage_cut_depth_percentile,
                        ),
                    ),
                    payload_gain_kg=self._coverage_cell_float(
                        cell,
                        "payload_gain_kg",
                        self._prior_percentile(
                            fields,
                            "payload_gain_kg",
                            self.coverage_payload_percentile,
                        ),
                    ),
                    effective_deposit_delta_kg=self._coverage_cell_float(
                        cell,
                        "effective_deposit_delta_kg",
                        self._prior_percentile(
                            fields,
                            "effective_deposit_delta_kg",
                            "p50",
                        ),
                    ),
                )
            )
        return candidates

    @staticmethod
    def _coverage_cell_float(
        mapping: dict[str, object],
        name: str,
        default: float,
    ) -> float:
        try:
            value = float(mapping.get(name, default))
        except (TypeError, ValueError):
            value = float(default)
        return float(value if np.isfinite(value) else default)

    def _coverage_exit_from_entry(self, entry_x: float, entry_z: float) -> tuple[float, float]:
        fields = dict(self.dig_cut_prior.get("fields", {}))
        dir_x = self._prior_percentile(
            fields,
            "cut_direction_x",
            self.coverage_cut_direction_percentile,
        )
        dir_z = self._prior_percentile(
            fields,
            "cut_direction_z",
            self.coverage_cut_direction_percentile,
        )
        norm = float(np.hypot(dir_x, dir_z))
        if norm <= 1.0e-6:
            dir_x, dir_z = -1.0, 0.0
        else:
            dir_x, dir_z = dir_x / norm, dir_z / norm
        length = self._prior_percentile(
            fields,
            "cut_length_m",
            self.coverage_cut_length_percentile,
        )
        return (
            self._clamp_to_prior(fields, "exit_x_m", float(entry_x) + dir_x * length),
            self._clamp_to_prior(fields, "exit_z_m", float(entry_z) + dir_z * length),
        )

    def _select_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        best: CoverageCorridorState | None = None
        best_score = -float("inf")
        self._coverage_candidate_scores = []
        first_dig_gate_available = self._coverage_first_dig_gate_available(obs)
        for corridor in self._coverage_corridors:
            remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
            first_dig_bonus = self._coverage_first_dig_bonus(corridor, obs)
            first_dig_distance = self._coverage_entry_distance_m(corridor, obs)
            first_dig_entry_reachable = self._coverage_first_dig_entry_reachable(
                first_dig_distance
            )
            first_dig_qpos_delta = self._coverage_first_dig_qpos_delta(corridor, obs)
            first_dig_qpos_reachable = self._coverage_first_dig_qpos_reachable(
                first_dig_qpos_delta
            )
            first_dig_qpos_penalty = self._coverage_first_dig_qpos_delta_penalty(
                first_dig_qpos_delta
            )
            first_dig_reachable = bool(
                first_dig_entry_reachable and first_dig_qpos_reachable
            )
            first_dig_gated_out = bool(first_dig_gate_available and not first_dig_reachable)
            rare_first_dig_gated_out = self._coverage_rare_first_dig_gated_out(
                corridor
            )
            score = self._coverage_score(corridor, remaining_depth) + first_dig_bonus
            if first_dig_gated_out or rare_first_dig_gated_out:
                score = -1.0e12 + float(score)
            corridor.score = float(score)
            corridor.last_remaining_depth_m = float(remaining_depth)
            self._coverage_candidate_scores.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(self._coverage_cell_id(corridor)),
                    "score": float(score),
                    "attempts": int(corridor.attempts),
                    "attempt_limit": int(self._coverage_corridor_attempt_limit(corridor)),
                    "depleted": int(corridor.depleted),
                    "source_count": int(corridor.source_count),
                    "source_fraction": float(corridor.source_fraction),
                    "cell_confidence": float(self._coverage_cell_confidence(corridor)),
                    "belief_coverage": float(corridor.belief_coverage),
                    "remaining_depth_m": float(remaining_depth),
                    "first_dig_bonus": float(first_dig_bonus),
                    "recent_row_penalty": float(
                        self._coverage_recent_row_penalty(corridor)
                    ),
                    "first_dig_entry_distance_m": float(first_dig_distance),
                    "first_dig_entry_reachable": int(first_dig_entry_reachable),
                    "first_dig_qpos_delta_norm": float(first_dig_qpos_penalty),
                    "first_dig_qpos_reachable": int(first_dig_qpos_reachable),
                    "first_dig_qpos_delta": first_dig_qpos_delta.astype(float).tolist(),
                    "first_dig_max_qpos_delta": (
                        []
                        if self.coverage_first_dig_max_qpos_delta is None
                        else self.coverage_first_dig_max_qpos_delta.astype(float).tolist()
                    ),
                    "first_dig_reachable": int(first_dig_reachable),
                    "first_dig_gate_applied": int(first_dig_gate_available),
                    "first_dig_gated_out": int(first_dig_gated_out),
                    "rare_first_dig_gated_out": int(rare_first_dig_gated_out),
                    "first_dig_max_entry_distance_m": float(
                        np.nan
                        if self.coverage_first_dig_max_entry_distance_m is None
                        else self.coverage_first_dig_max_entry_distance_m
                    ),
                    "low_productivity_streak": int(corridor.low_productivity_streak),
                }
            )
            if first_dig_gated_out or rare_first_dig_gated_out:
                continue
            if score > best_score:
                best = corridor
                best_score = float(score)

        if best is None:
            raise ValueError("operator_prior_coverage has no selectable corridors.")
        if all(corridor.depleted for corridor in self._coverage_corridors):
            self._request_coverage_terminal_stop("dig_area_depleted")
        return best

    def _coverage_first_dig_active(self) -> bool:
        return bool(
            int(self._cycle_index) == 0
            and int(self._coverage_completed_dump_count) <= 0
            and self.coverage_first_dig_strategy
            not in {"", "none", "coverage_score"}
        )

    def _coverage_first_dig_gate_available(self, obs: dict) -> bool:
        if not self._coverage_first_dig_active():
            return False
        if (
            self.coverage_first_dig_max_entry_distance_m is None
            and self.coverage_first_dig_max_qpos_delta is None
        ):
            return False
        for corridor in self._coverage_corridors:
            if corridor.depleted:
                continue
            if corridor.attempts >= self._coverage_corridor_attempt_limit(corridor):
                continue
            if self._coverage_rare_first_dig_gated_out(corridor):
                continue
            distance = self._coverage_entry_distance_m(corridor, obs)
            qpos_delta = self._coverage_first_dig_qpos_delta(corridor, obs)
            if (
                self._coverage_first_dig_entry_reachable(distance)
                and self._coverage_first_dig_qpos_reachable(qpos_delta)
            ):
                return True
        return False

    def _coverage_first_dig_entry_reachable(self, distance: float) -> bool:
        if not self._coverage_first_dig_active():
            return True
        if self.coverage_first_dig_max_entry_distance_m is None:
            return True
        return bool(
            np.isfinite(distance)
            and float(distance) <= float(self.coverage_first_dig_max_entry_distance_m)
        )

    def _coverage_score(
        self,
        corridor: CoverageCorridorState,
        remaining_depth_m: float,
    ) -> float:
        if corridor.depleted:
            return -1.0e9 - float(corridor.attempts)
        if corridor.attempts >= self._coverage_corridor_attempt_limit(corridor):
            return -1.0e8 - float(corridor.attempts)
        fields = dict(self.dig_cut_prior.get("fields", {}))
        target_depth = (
            float(corridor.cut_depth_peak_m)
            if np.isfinite(corridor.cut_depth_peak_m)
            else self._prior_percentile(
                fields,
                "cut_depth_peak_m",
                self.coverage_cut_depth_percentile,
            )
        )
        if self.coverage_use_env_removed_depth:
            remaining_ratio = (
                1.0
                if not np.isfinite(remaining_depth_m) or target_depth <= 1.0e-6
                else float(np.clip(remaining_depth_m / target_depth, 0.0, 1.5))
            )
        else:
            remaining_ratio = float(
                np.clip(1.0 - float(corridor.belief_coverage), 0.0, 1.5)
            )
        deposit_p50 = max(
            self._prior_percentile(fields, "effective_deposit_delta_kg", "p50"),
            1.0,
        )
        productivity = (
            1.0
            if corridor.attempts <= 0
            else float(
                np.clip(
                    corridor.last_effective_deposit_delta_kg / deposit_p50,
                    0.0,
                    1.5,
                )
            )
        )
        repeat_penalty = (
            self.coverage_recent_selection_penalty
            if int(corridor.corridor_id) == int(self._coverage_last_selected_corridor_id)
            else 0.0
        )
        row_penalty = self._coverage_recent_row_penalty(corridor)
        unattempted_bonus = (
            self.coverage_unattempted_bonus if corridor.attempts <= 0 else 0.0
        )
        attempt_penalty = self.coverage_attempt_penalty * float(corridor.attempts)
        cell_confidence = self._coverage_cell_confidence(corridor)
        return (
            2.0 * remaining_ratio
            + productivity
            + self.coverage_cell_confidence_weight * cell_confidence
            + unattempted_bonus
            - repeat_penalty
            - row_penalty
            - attempt_penalty
            - 0.5 * float(corridor.low_productivity_streak)
        )

    def _coverage_cell_confidence(self, corridor: CoverageCorridorState) -> float:
        if self.coverage_candidate_layout != "cell_weighted_3x2":
            return 0.0
        fraction = float(corridor.source_fraction)
        if not np.isfinite(fraction) or fraction <= 0.0:
            return 0.0
        uniform_fraction = 1.0 / 6.0
        return float(np.clip(fraction / uniform_fraction, 0.0, 1.5))

    def _coverage_corridor_is_rare(self, corridor: CoverageCorridorState) -> bool:
        if self.coverage_candidate_layout != "cell_weighted_3x2":
            return False
        fraction = float(corridor.source_fraction)
        return bool(
            np.isfinite(fraction)
            and fraction > 0.0
            and fraction < self.coverage_rare_cell_source_fraction_threshold
        )

    def _coverage_corridor_attempt_limit(self, corridor: CoverageCorridorState) -> int:
        limit = int(self.coverage_max_attempts_per_corridor)
        if self._coverage_corridor_is_rare(corridor):
            limit = min(limit, int(self.coverage_rare_cell_max_attempts))
        return max(1, int(limit))

    def _coverage_rare_first_dig_gated_out(
        self,
        corridor: CoverageCorridorState,
    ) -> bool:
        if not self._coverage_first_dig_active():
            return False
        if not self._coverage_corridor_is_rare(corridor):
            return False
        for candidate in self._coverage_corridors:
            if candidate is corridor:
                continue
            if self._coverage_corridor_is_rare(candidate):
                continue
            if candidate.depleted:
                continue
            if candidate.attempts >= self._coverage_corridor_attempt_limit(candidate):
                continue
            return True
        return False

    def _coverage_recent_row_penalty(self, corridor: CoverageCorridorState) -> float:
        if self.coverage_recent_row_selection_penalty <= 0.0:
            return 0.0
        previous = self._coverage_corridor_by_id(self._coverage_last_selected_corridor_id)
        if previous is None:
            return 0.0
        if int(previous.corridor_id) == int(corridor.corridor_id):
            return 0.0
        same_row = bool(
            abs(float(previous.entry_z_m) - float(corridor.entry_z_m)) <= 1.0e-4
        )
        return float(self.coverage_recent_row_selection_penalty if same_row else 0.0)

    def _coverage_first_dig_bonus(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        if self.coverage_first_dig_strategy in {"", "none", "coverage_score"}:
            return 0.0
        if int(self._cycle_index) != 0 or int(self._coverage_completed_dump_count) > 0:
            return 0.0
        if corridor.depleted or corridor.attempts > 0:
            return 0.0
        if self.coverage_first_dig_strategy in {
            "nearest_entry",
            "bootstrap_nearest_entry",
        }:
            distance = self._coverage_entry_distance_m(corridor, obs)
            if not np.isfinite(distance):
                return 0.0
            qpos_penalty = self._coverage_first_dig_qpos_delta_penalty(
                self._coverage_first_dig_qpos_delta(corridor, obs)
            )
            return (
                -float(self.coverage_first_dig_proximity_weight) * float(distance)
                - float(self.coverage_first_dig_qpos_delta_weight) * qpos_penalty
            )
        if self.coverage_first_dig_strategy not in {
            "preferred_corridor",
            "bootstrap_friendly",
        }:
            return 0.0
        preferred_id = self.coverage_first_dig_preferred_corridor_id
        if preferred_id is None:
            return 0.0
        if int(corridor.corridor_id) != int(preferred_id):
            return 0.0
        return float(self.coverage_first_dig_preferred_bonus)

    def _coverage_entry_distance_m(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        pose = self._bucket_tip_dig_area_pose(obs)
        if pose is None:
            return float("nan")
        bucket_x, _, bucket_z = pose
        if not all(np.isfinite(value) for value in (bucket_x, bucket_z)):
            return float("nan")
        return float(
            np.hypot(
                float(bucket_x) - float(corridor.entry_x_m),
                float(bucket_z) - float(corridor.entry_z_m),
            )
        )

    def _coverage_first_dig_qpos_delta(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> np.ndarray:
        if not self._coverage_first_dig_active() or not self.pre_dig_align_enabled:
            return np.zeros(self.action_dim, dtype=np.float32)
        raw_fields = self._coverage_raw_fields(corridor)
        token = _build_dig_cut_token(raw_fields)
        target = self._pre_dig_align_target_from_token(
            token=token,
            obs=obs,
            update_state=False,
        )
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        delta = np.abs(target - qpos).astype(np.float32)
        delta[~self.pre_dig_align_controlled_dims] = 0.0
        return delta

    def _coverage_first_dig_qpos_reachable(self, delta: np.ndarray) -> bool:
        if not self._coverage_first_dig_active():
            return True
        if self.coverage_first_dig_max_qpos_delta is None:
            return True
        controlled = self.pre_dig_align_controlled_dims
        if not np.any(controlled):
            return True
        delta = np.asarray(delta, dtype=np.float32).reshape(self.action_dim)
        return bool(
            np.all(
                delta[controlled]
                <= self.coverage_first_dig_max_qpos_delta[controlled] + 1.0e-6
            )
        )

    def _coverage_first_dig_qpos_delta_penalty(self, delta: np.ndarray) -> float:
        if not self._coverage_first_dig_active():
            return 0.0
        controlled = self.pre_dig_align_controlled_dims
        if not np.any(controlled):
            return 0.0
        delta = np.asarray(delta, dtype=np.float32).reshape(self.action_dim)
        delta = delta[controlled]
        if self.coverage_first_dig_max_qpos_delta is not None:
            scale = np.maximum(
                self.coverage_first_dig_max_qpos_delta[controlled],
                1.0e-6,
            )
            delta = delta / scale
        return float(np.linalg.norm(delta))

    def _coverage_raw_fields(
        self, corridor: CoverageCorridorState
    ) -> dict[str, float | int]:
        fields = dict(self.dig_cut_prior.get("fields", {}))
        entry_x = self._clamp_to_prior(fields, "entry_x_m", corridor.entry_x_m)
        entry_z = self._clamp_to_prior(fields, "entry_z_m", corridor.entry_z_m)
        exit_x = self._clamp_to_prior(fields, "exit_x_m", corridor.exit_x_m)
        exit_z = self._clamp_to_prior(fields, "exit_z_m", corridor.exit_z_m)
        delta_x = exit_x - entry_x
        delta_z = exit_z - entry_z
        length = float(np.hypot(delta_x, delta_z))
        if length <= 1.0e-6:
            dir_x = self._prior_percentile(
                fields,
                "cut_direction_x",
                self.coverage_cut_direction_percentile,
            )
            dir_z = self._prior_percentile(
                fields,
                "cut_direction_z",
                self.coverage_cut_direction_percentile,
            )
            length = self._prior_percentile(
                fields,
                "cut_length_m",
                self.coverage_cut_length_percentile,
            )
        else:
            dir_x = delta_x / length
            dir_z = delta_z / length
        return {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": 0.0,
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
                self._clamp_to_prior(
                    fields,
                    "cut_depth_peak_m",
                    float(corridor.cut_depth_peak_m)
                    if np.isfinite(corridor.cut_depth_peak_m)
                    else self._prior_percentile(
                        fields,
                        "cut_depth_peak_m",
                        self.coverage_cut_depth_percentile,
                    ),
                )
            ),
            "operator_cut_payload_gain_kg": float(
                self._clamp_to_prior(
                    fields,
                    "payload_gain_kg",
                    float(corridor.payload_gain_kg)
                    if np.isfinite(corridor.payload_gain_kg)
                    else self._prior_percentile(
                        fields,
                        "payload_gain_kg",
                        self.coverage_payload_percentile,
                    ),
                )
            ),
            "operator_cut_valid": 1,
        }

    def _coverage_remaining_depth_for_corridor(
        self,
        obs: dict,
        corridor: CoverageCorridorState,
    ) -> float:
        env_state = self._env_state(obs)
        cell_id = self._coverage_cell_id(corridor)
        target_idx = ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + cell_id
        removed_idx = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + cell_id
        valid_idx = ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + cell_id
        if len(env_state) <= max(target_idx, removed_idx, valid_idx):
            return float("nan")
        if float(env_state[valid_idx]) <= 0.5:
            return float("nan")
        target_depth = float(env_state[target_idx])
        removed_depth = float(env_state[removed_idx])
        if not np.isfinite(target_depth) or not np.isfinite(removed_depth):
            return float("nan")
        return float(max(0.0, target_depth - removed_depth))

    @staticmethod
    def _coverage_cell_id(corridor: CoverageCorridorState) -> int:
        if corridor.cell_id >= 0:
            return max(0, min(5, int(corridor.cell_id)))
        corridor_id = max(0, min(5, int(corridor.corridor_id)))
        z_index = corridor_id // 2
        x_index = corridor_id % 2
        return int(z_index * 2 + x_index)

    @staticmethod
    def _coverage_cell_id_from_percentile_indices(
        *,
        x_index: int,
        x_count: int,
        z_index: int,
        z_count: int,
    ) -> int:
        long_index = int(round(np.interp(z_index, [0, max(1, z_count - 1)], [0, 2])))
        short_index = int(round(np.interp(x_index, [0, max(1, x_count - 1)], [0, 1])))
        return int(np.clip(long_index, 0, 2) * 2 + int(np.clip(short_index, 0, 1)))

    def _complete_coverage_dig(self, obs: dict) -> None:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return
        self._coverage_current_payload_gain_kg = max(
            float(self._coverage_current_payload_gain_kg),
            self._mass_in_bucket(obs),
        )

    def _complete_coverage_dump(self, obs: dict, *, reason: str) -> None:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return
        payload_gain = max(float(self._coverage_current_payload_gain_kg), 0.0)
        effective_deposit = max(
            0.0, self._deposited_mass(obs) - float(self._coverage_cycle_start_deposit_kg)
        )
        remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
        low_productivity = (
            payload_gain < self.coverage_low_productivity_payload_kg
            or effective_deposit < self.coverage_low_productivity_deposit_kg
        )
        corridor.attempts += 1
        corridor.last_payload_gain_kg = float(payload_gain)
        corridor.last_effective_deposit_delta_kg = float(effective_deposit)
        corridor.last_remaining_depth_m = float(remaining_depth)
        corridor.last_reason = str(reason)
        self._update_corridor_belief(
            corridor,
            payload_gain_kg=payload_gain,
            effective_deposit_delta_kg=effective_deposit,
        )
        self._coverage_last_payload_gain_kg = float(payload_gain)
        self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
        self._coverage_completed_dump_count += 1

        if low_productivity:
            corridor.low_productivity_streak += 1
            self._coverage_global_low_productivity_streak += 1
        else:
            corridor.low_productivity_streak = 0
            self._coverage_global_low_productivity_streak = 0

        if (
            corridor.low_productivity_streak
            >= self.coverage_deplete_after_low_streak
        ):
            corridor.depleted = True
            corridor.last_reason = "low_productivity_consecutive"
        if corridor.attempts >= self._coverage_corridor_attempt_limit(corridor):
            corridor.depleted = True
            corridor.last_reason = "attempt_limit_reached"
        if (
            np.isfinite(remaining_depth)
            and remaining_depth < self.coverage_min_remaining_depth_m
        ):
            corridor.depleted = True
            corridor.last_reason = "remaining_depth_below_threshold"
        if (
            not self.coverage_use_env_removed_depth
            and corridor.belief_coverage >= self.coverage_belief_depleted_score
        ):
            corridor.depleted = True
            corridor.last_reason = "belief_coverage_complete"

        if all(candidate.depleted for candidate in self._coverage_corridors):
            self._request_coverage_terminal_stop("dig_area_depleted")
        elif (
            self._coverage_global_low_productivity_streak
            >= self.coverage_global_low_productivity_stop
        ):
            self._request_coverage_terminal_stop("low_productivity_consecutive")
        if (
            low_productivity
            and payload_gain < self.coverage_low_productivity_payload_kg
            and effective_deposit >= self.coverage_low_productivity_deposit_kg
        ):
            self._request_coverage_terminal_stop("physics_artifact_suspected")

    def _reject_active_coverage_corridor(self, obs: dict, *, reason: str) -> None:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return
        payload_gain = max(
            float(self._coverage_current_payload_gain_kg),
            float(self._dig_best_mass_kg),
            self._mass_in_bucket(obs),
            0.0,
        )
        effective_deposit = max(
            0.0, self._deposited_mass(obs) - float(self._coverage_cycle_start_deposit_kg)
        )
        remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
        corridor.attempts += 1
        corridor.low_productivity_streak += 1
        corridor.last_payload_gain_kg = float(payload_gain)
        corridor.last_effective_deposit_delta_kg = float(effective_deposit)
        corridor.last_remaining_depth_m = float(remaining_depth)
        corridor.last_reason = str(reason)
        self._update_corridor_belief(
            corridor,
            payload_gain_kg=payload_gain,
            effective_deposit_delta_kg=effective_deposit,
        )
        self._coverage_last_payload_gain_kg = float(payload_gain)
        self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
        if str(reason) != "align_entry_gap_timeout":
            self._coverage_global_low_productivity_streak += 1
        if (
            corridor.low_productivity_streak
            >= self.coverage_deplete_after_low_streak
            or corridor.attempts >= self._coverage_corridor_attempt_limit(corridor)
        ):
            corridor.depleted = True
        if all(candidate.depleted for candidate in self._coverage_corridors):
            self._request_coverage_terminal_stop("dig_area_depleted")
        elif (
            self._coverage_global_low_productivity_streak
            >= self.coverage_global_low_productivity_stop
        ):
            self._request_coverage_terminal_stop("low_productivity_consecutive")

    def _update_corridor_belief(
        self,
        corridor: CoverageCorridorState,
        *,
        payload_gain_kg: float,
        effective_deposit_delta_kg: float,
    ) -> None:
        if self.coverage_use_env_removed_depth:
            return
        fields = dict(self.dig_cut_prior.get("fields", {}))
        payload_p50 = max(self._prior_percentile(fields, "payload_gain_kg", "p50"), 1.0)
        deposit_p50 = max(
            self._prior_percentile(fields, "effective_deposit_delta_kg", "p50"),
            1.0,
        )
        payload_score = float(np.clip(float(payload_gain_kg) / payload_p50, 0.0, 1.5))
        deposit_score = float(
            np.clip(float(effective_deposit_delta_kg) / deposit_p50, 0.0, 1.5)
        )
        gain = self.coverage_belief_gain_scale * max(payload_score, deposit_score)
        if gain <= 0.0:
            return
        corridor.belief_coverage = float(
            np.clip(float(corridor.belief_coverage) + gain, 0.0, 1.5)
        )

    def _request_coverage_terminal_stop(self, reason: str) -> None:
        if self._coverage_terminal_stop_requested:
            return
        self._coverage_terminal_stop_requested = True
        self._coverage_terminal_stop_reason = str(reason)

    def _coverage_active_corridor(self) -> CoverageCorridorState | None:
        return self._coverage_corridor_by_id(self._coverage_active_corridor_id)

    def _coverage_corridor_by_id(
        self,
        corridor_id: int,
    ) -> CoverageCorridorState | None:
        for corridor in self._coverage_corridors:
            if int(corridor.corridor_id) == int(corridor_id):
                return corridor
        return None

    def _coverage_active_corridor_score(self) -> float:
        corridor = self._coverage_active_corridor()
        return float("nan") if corridor is None else float(corridor.score)

    def _coverage_active_value(self, name: str) -> float:
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return float("nan")
        return float(getattr(corridor, name, float("nan")))

    def _coverage_depleted_count(self) -> int:
        return int(sum(1 for corridor in self._coverage_corridors if corridor.depleted))

    def _coverage_corridor_to_debug(
        self,
        corridor: CoverageCorridorState,
    ) -> dict[str, float | int | str]:
        return {
            "corridor_id": int(corridor.corridor_id),
            "entry_x_m": float(corridor.entry_x_m),
            "entry_z_m": float(corridor.entry_z_m),
            "exit_x_m": float(corridor.exit_x_m),
            "exit_z_m": float(corridor.exit_z_m),
            "cell_id": int(max(0, min(5, corridor.cell_id))),
            "source_count": int(corridor.source_count),
            "source_fraction": float(corridor.source_fraction),
            "attempt_limit": int(self._coverage_corridor_attempt_limit(corridor)),
            "cell_confidence": float(self._coverage_cell_confidence(corridor)),
            "score": float(corridor.score),
            "attempts": int(corridor.attempts),
            "low_productivity_streak": int(corridor.low_productivity_streak),
            "depleted": int(corridor.depleted),
            "belief_coverage": float(corridor.belief_coverage),
            "last_payload_gain_kg": float(corridor.last_payload_gain_kg),
            "last_effective_deposit_delta_kg": float(
                corridor.last_effective_deposit_delta_kg
            ),
            "last_remaining_depth_m": float(corridor.last_remaining_depth_m),
            "last_reason": str(corridor.last_reason),
        }

    def _clear_dig_cut_plan(self) -> None:
        self._dig_cut_planned_cycle_id = -1
        self._dig_cut_tokens = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        self._dig_cut_token_source = "none"
        self._dig_cut_fallback_reason = ""
        self._dig_cut_token_in_prior_p10_p90 = False

    def _validate_dig_cut_planner_config(self) -> None:
        if not self.dig_cut_planner_enabled:
            return
        supported_modes = {
            "conservative_pose",
            "operator_prior",
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }
        if self.dig_cut_planner_mode not in supported_modes:
            raise ValueError(
                f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}; "
                f"expected one of {sorted(supported_modes)}."
            )
        if (
            self.dig_cut_planner_mode
            in {"operator_prior", "operator_prior_coverage", "operator_prior_sweep_belief"}
            and not self.dig_cut_prior_path
        ):
            raise ValueError(
                f"{self.dig_cut_planner_mode} dig_cut_planner requires prior_path."
            )
        supported_layouts = {"percentile_grid", "cell_weighted_3x2"}
        if self.coverage_candidate_layout not in supported_layouts:
            raise ValueError(
                "Unsupported coverage.candidate_layout "
                f"{self.coverage_candidate_layout!r}; expected one of "
                f"{sorted(supported_layouts)}."
            )

    @staticmethod
    def _coverage_percentile_list(
        value: object,
        *,
        default: tuple[str, ...],
    ) -> tuple[str, ...]:
        allowed = {"p10", "p50", "p90"}
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value]
        else:
            items = list(default)
        cleaned = tuple(item for item in items if item in allowed)
        return cleaned or tuple(default)

    @staticmethod
    def _coverage_percentile_name(value: object, *, default: str) -> str:
        allowed = {"p10", "p50", "p90"}
        text = str(value).strip().lower()
        return text if text in allowed else default

    def _align_vector(
        self,
        value: object,
        *,
        default: list[float] | tuple[float, ...],
    ) -> np.ndarray:
        arr = np.asarray(default if value is None else value, dtype=np.float32)
        return arr.reshape(self.action_dim)

    def _optional_align_vector(self, value: object) -> np.ndarray | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"", "none", "null"}:
                return None
            value = [part.strip() for part in text.split(",") if part.strip()]
        return np.asarray(value, dtype=np.float32).reshape(self.action_dim)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"", "none", "null"}:
            return None
        return float(value)

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

    def _bucket_tip_dig_area_pose(self, obs: dict) -> tuple[float, float, float] | None:
        env_state = self._env_state(obs)
        if len(env_state) > ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX:
            values = (
                float(env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX]),
                float(env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX]),
                float(env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX]),
            )
            if all(np.isfinite(value) for value in values):
                return values
        return self._bucket_dig_area_pose(obs)

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
            if self._first_dig_policy_active():
                if self.first_dig_policy is None:
                    raise RuntimeError("first dig policy is active but missing.")
                return self.first_dig_policy
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
        if self.first_dig_policy is not None:
            policies.append(self.first_dig_policy)
        if self.bootstrap_policy is not None:
            policies.append(self.bootstrap_policy)
        return policies

    def _first_dig_policy_active(self) -> bool:
        return bool(
            self.first_dig_policy is not None
            and self._skill_name == "dig"
            and int(getattr(self, "_cycle_index", 0)) == 0
            and int(getattr(self, "_coverage_completed_dump_count", 0)) <= 0
        )

    def _make_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitivePlannerDebugState:
        skill_name = str(self._skill_name)
        skill_id = PRIMITIVE_SKILL_IDS.get(skill_name, -1)
        hybrid_mode = (
            HYBRID_MODE_TRANSITION
            if skill_name in {"return", PRE_DIG_ALIGN_SKILL_NAME}
            else HYBRID_MODE_WORK
        )
        return PrimitivePlannerDebugState(
            skill_name=skill_name,
            skill_id=int(skill_id),
            skill_switch_reason=str(self._switch_reason),
            primitive_checkpoint_path=str(
                self.primitive_checkpoint_paths.get(
                    "first_dig" if self._first_dig_policy_active() else skill_name,
                    "",
                )
            ),
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
        first_dig_policy: Policy | None = None,
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
        dig_to_carry_target_bucket_mass_kg: float | None = None,
        dig_to_carry_mass_plateau_enabled: bool = False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg: float = 20.0,
        dig_to_carry_mass_plateau_epsilon_kg: float = 1.0,
        dig_to_carry_mass_plateau_hold_steps: int = 25,
        dig_to_carry_mass_plateau_min_steps: int = 80,
        dig_bad_replan_enabled: bool = False,
        dig_bad_replan_max_steps: int = 180,
        dig_bad_replan_min_bucket_mass_kg: float = 15.0,
        dig_exit_guard_enabled: bool = False,
        dig_exit_guard_min_steps: int = 80,
        dig_exit_guard_overshoot_m: float = 0.65,
        dig_exit_guard_min_bucket_mass_kg: float = 20.0,
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
        dump_ready_near_window_enabled: bool = False,
        dump_ready_near_window_x_tolerance_m: float = 0.05,
        dump_ready_near_window_z_tolerance_m: float = 0.05,
        dump_ready_near_window_outside_tolerance_m: float = 0.0,
        dump_ready_near_window_require_over_footprint: bool = True,
        dump_done_max_bucket_mass_kg: float = 100.0,
        dump_done_min_deposit_delta_kg: float = 10.0,
        dump_done_hold_steps: int = 30,
        dump_done_use_boundary_event: bool = True,
        return_to_dig_shallow_guard_enabled: bool = False,
        return_to_dig_max_bucket_mass_kg: float = 15.0,
        return_to_dig_touch_tolerance_m: float = 0.05,
        return_to_dig_min_depth_m: float = 0.02,
        return_to_dig_max_depth_m: float = 0.12,
        return_to_dig_max_entry_error_m: float | None = None,
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
        return_target_planner: dict[str, Any] | None = None,
        pre_dig_align: dict[str, Any] | None = None,
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
            first_dig_policy=first_dig_policy,
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
            dig_to_carry_target_bucket_mass_kg=dig_to_carry_target_bucket_mass_kg,
            dig_to_carry_mass_plateau_enabled=dig_to_carry_mass_plateau_enabled,
            dig_to_carry_mass_plateau_min_bucket_mass_kg=(
                dig_to_carry_mass_plateau_min_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_epsilon_kg=(
                dig_to_carry_mass_plateau_epsilon_kg
            ),
            dig_to_carry_mass_plateau_hold_steps=(
                dig_to_carry_mass_plateau_hold_steps
            ),
            dig_to_carry_mass_plateau_min_steps=dig_to_carry_mass_plateau_min_steps,
            dig_bad_replan_enabled=dig_bad_replan_enabled,
            dig_bad_replan_max_steps=dig_bad_replan_max_steps,
            dig_bad_replan_min_bucket_mass_kg=dig_bad_replan_min_bucket_mass_kg,
            dig_exit_guard_enabled=dig_exit_guard_enabled,
            dig_exit_guard_min_steps=dig_exit_guard_min_steps,
            dig_exit_guard_overshoot_m=dig_exit_guard_overshoot_m,
            dig_exit_guard_min_bucket_mass_kg=dig_exit_guard_min_bucket_mass_kg,
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
            dump_done_max_bucket_mass_kg=dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=dump_done_min_deposit_delta_kg,
            dump_done_hold_steps=dump_done_hold_steps,
            dump_done_use_boundary_event=dump_done_use_boundary_event,
            return_to_dig_shallow_guard_enabled=(
                return_to_dig_shallow_guard_enabled
            ),
            return_to_dig_max_bucket_mass_kg=return_to_dig_max_bucket_mass_kg,
            return_to_dig_touch_tolerance_m=return_to_dig_touch_tolerance_m,
            return_to_dig_min_depth_m=return_to_dig_min_depth_m,
            return_to_dig_max_depth_m=return_to_dig_max_depth_m,
            return_to_dig_max_entry_error_m=return_to_dig_max_entry_error_m,
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
            return_target_planner=return_target_planner,
            pre_dig_align=pre_dig_align,
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
                return
            if self._return_to_dig_shallow_guard_ready(
                obs=obs,
                boundary_event=boundary_event,
            ):
                self._completed_transition_count += 1
                self._cycle_index += 1
                self._set_skill("dig", "return_to_dig_shallow_entry_guard")

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
            if self._first_dig_policy_active():
                if self.first_dig_policy is None:
                    raise RuntimeError("first dig policy is active but missing.")
                return self.first_dig_policy
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
        if self.first_dig_policy is not None:
            policies.append(self.first_dig_policy)
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
            primitive_checkpoint_path=str(
                self.primitive_checkpoint_paths.get(
                    "first_dig" if self._first_dig_policy_active() else skill_name,
                    "",
                )
            ),
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
