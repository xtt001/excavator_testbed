"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_TOKEN_DIM,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_CONTRACT,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
    _build_dig_cut_token,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
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
from testbed.planner.primitive_execution import (
    PrimitiveTickCallbacks,
    PrimitiveTickPreparation,
    run_primitive_tick,
)
from testbed.planner.primitive_decision import PrimitiveDecisionResult
from testbed.planner.primitive_tokens import (
    DigDepthProfileTokenPlan,
    DigDepthProfileTokenPlanner,
    DigDepthProfileTokenPlanningError,
    DigCutTokenPlan,
    DigCutTokenPlanner,
    GoalTokenProvider,
    ReturnRelocateTokenPlanner,
    ReturnStartEnvelopeConditioningConfig,
    ReturnStartEnvelopeTokenPlan,
    ReturnStartEnvelopeTokenPlanner,
    ReturnTargetTokenPlan,
    ReturnTargetTokenPlanner,
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
    entry_x_p05_m: float = float("nan")
    entry_x_p50_m: float = float("nan")
    entry_x_p95_m: float = float("nan")
    entry_z_p05_m: float = float("nan")
    entry_z_p50_m: float = float("nan")
    entry_z_p95_m: float = float("nan")
    entry_radial_p75_m: float = float("nan")
    entry_radial_p95_m: float = float("nan")
    exit_x_p05_m: float = float("nan")
    exit_x_p50_m: float = float("nan")
    exit_x_p95_m: float = float("nan")
    exit_z_p05_m: float = float("nan")
    exit_z_p50_m: float = float("nan")
    exit_z_p95_m: float = float("nan")
    exit_radial_p75_m: float = float("nan")
    exit_radial_p95_m: float = float("nan")
    cut_depth_peak_p05_m: float = float("nan")
    cut_depth_peak_p50_m: float = float("nan")
    cut_depth_peak_p95_m: float = float("nan")
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
    state_exemplar_id: str = ""
    state_exemplar_distance: float = float("nan")


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
        dig_failed_replan_next_skill: str = "dig",
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
        return_to_dig_start_envelope_gate_enabled: bool = False,
        return_to_dig_start_envelope_spatial_tolerance: float = 0.10,
        return_to_dig_start_envelope_depth_tolerance_m: float = 0.08,
        return_to_dig_start_envelope_local_depth_tolerance_m: float = 0.005,
        return_to_dig_start_envelope_plane_depth_tolerance_m: float = 0.05,
        return_to_dig_start_envelope_plane_depth_mode: str = "range",
        return_to_dig_start_envelope_qpos_tolerance: float = 0.04,
        return_to_dig_start_envelope_require_contact: bool = True,
        return_to_dig_start_envelope_direct_handoff_enabled: bool = False,
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
        self.dig_failed_replan_next_skill = self._normalize_failed_dig_replan_skill(
            dig_failed_replan_next_skill
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
        self.return_to_dig_start_envelope_gate_enabled = bool(
            return_to_dig_start_envelope_gate_enabled
        )
        self.return_to_dig_start_envelope_spatial_tolerance = float(
            return_to_dig_start_envelope_spatial_tolerance
        )
        self.return_to_dig_start_envelope_depth_tolerance_m = float(
            return_to_dig_start_envelope_depth_tolerance_m
        )
        self.return_to_dig_start_envelope_local_depth_tolerance_m = float(
            return_to_dig_start_envelope_local_depth_tolerance_m
        )
        self.return_to_dig_start_envelope_plane_depth_tolerance_m = float(
            return_to_dig_start_envelope_plane_depth_tolerance_m
        )
        self.return_to_dig_start_envelope_plane_depth_mode = (
            self._normalize_plane_depth_mode(
                return_to_dig_start_envelope_plane_depth_mode
            )
        )
        self.return_to_dig_start_envelope_qpos_tolerance = float(
            return_to_dig_start_envelope_qpos_tolerance
        )
        self.return_to_dig_start_envelope_require_contact = bool(
            return_to_dig_start_envelope_require_contact
        )
        self.return_to_dig_start_envelope_direct_handoff_enabled = bool(
            return_to_dig_start_envelope_direct_handoff_enabled
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
        return_start_envelope_cfg = dict(
            self.dig_cut_planner_cfg.get("return_start_envelope", {}) or {}
        )
        self.return_start_envelope_use_cell_prior = bool(
            return_start_envelope_cfg.get("use_cell_prior", False)
        )
        self.return_start_envelope_min_source_count = max(
            1, int(return_start_envelope_cfg.get("min_source_count", 1))
        )
        self.return_start_envelope_min_source_fraction = max(
            0.0,
            float(return_start_envelope_cfg.get("min_source_fraction", 0.0)),
        )
        qpos_from_relocate_cfg = dict(
            return_start_envelope_cfg.get("qpos_from_relocate", {}) or {}
        )
        self.return_start_envelope_qpos_from_relocate_enabled = bool(
            qpos_from_relocate_cfg.get("enabled", False)
        )
        raw_relocate_coefficients = qpos_from_relocate_cfg.get("coefficients")
        self.return_start_envelope_qpos_from_relocate_coefficients = (
            None
            if raw_relocate_coefficients is None
            else np.asarray(raw_relocate_coefficients, dtype=np.float32).reshape(4, 8)
        )
        self.return_start_envelope_qpos_from_relocate_min = self._align_vector(
            qpos_from_relocate_cfg.get("qpos_min", [0.44, 0.50, 0.0, 0.0]),
            default=[0.44, 0.50, 0.0, 0.0],
        )
        self.return_start_envelope_qpos_from_relocate_max = self._align_vector(
            qpos_from_relocate_cfg.get("qpos_max", [0.56, 0.80, 0.56, 0.48]),
            default=[0.56, 0.80, 0.56, 0.48],
        )
        self.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds = bool(
            qpos_from_relocate_cfg.get("use_prior_qpos_bounds", False)
        )
        spatial_from_relocate_cfg = dict(
            return_start_envelope_cfg.get("spatial_from_relocate", {}) or {}
        )
        self.return_start_envelope_spatial_from_relocate_enabled = bool(
            spatial_from_relocate_cfg.get("enabled", False)
        )
        raw_spatial_coefficients = spatial_from_relocate_cfg.get("coefficients")
        self.return_start_envelope_spatial_from_relocate_coefficients = (
            None
            if raw_spatial_coefficients is None
            else np.asarray(raw_spatial_coefficients, dtype=np.float32).reshape(2, 8)
        )
        self.return_start_envelope_spatial_from_relocate_min = np.asarray(
            spatial_from_relocate_cfg.get("spatial_min", [-1.0, -0.10]),
            dtype=np.float32,
        ).reshape(2)
        self.return_start_envelope_spatial_from_relocate_max = np.asarray(
            spatial_from_relocate_cfg.get("spatial_max", [1.0, 1.0]),
            dtype=np.float32,
        ).reshape(2)
        self.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds = bool(
            spatial_from_relocate_cfg.get("use_prior_spatial_bounds", False)
        )
        dig_depth_profile_cfg = dict(
            self.dig_cut_planner_cfg.get("dig_depth_profile", {}) or {}
        )
        self.dig_depth_profile_source = str(
            dig_depth_profile_cfg.get("source", "live_plan")
        ).strip().lower()
        self.dig_depth_profile_required = bool(
            dig_depth_profile_cfg.get("required", False)
        )
        self.dig_depth_profile_allow_live_fallback = bool(
            dig_depth_profile_cfg.get(
                "allow_live_fallback",
                self.dig_depth_profile_source != "prior_profile",
            )
        )
        self.dig_depth_profile_allow_global_fallback = bool(
            dig_depth_profile_cfg.get("allow_global_fallback", True)
        )
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
        self.coverage_multi_pass_enabled = bool(
            coverage_cfg.get("multi_pass_enabled", False)
        )
        self.coverage_multi_pass_max_passes = max(
            1, int(coverage_cfg.get("multi_pass_max_passes", 1))
        )
        self.coverage_multi_pass_min_remaining_depth_m = float(
            coverage_cfg.get(
                "multi_pass_min_remaining_depth_m",
                self.coverage_min_remaining_depth_m,
            )
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
        state_exemplar_cfg = dict(
            coverage_cfg.get("state_conditioned_exemplars", {}) or {}
        )
        self.coverage_state_exemplars_enabled = bool(
            state_exemplar_cfg.get("enabled", False)
        )
        self.coverage_state_exemplar_path = str(
            state_exemplar_cfg.get(
                "path",
                self.dig_cut_prior.get("coverage_state_exemplars_path", ""),
            )
        )
        self.coverage_state_exemplar_k = max(
            1, int(state_exemplar_cfg.get("k", 5))
        )
        self.coverage_state_exemplar_removed_depth_scale_m = max(
            1.0e-6,
            float(state_exemplar_cfg.get("removed_depth_scale_m", 0.12)),
        )
        self.coverage_state_exemplar_target_cell_weight = max(
            0.0,
            float(state_exemplar_cfg.get("target_cell_weight", 2.0)),
        )
        self.coverage_state_exemplar_score_weight = float(
            state_exemplar_cfg.get("score_weight", 0.75)
        )
        self.coverage_state_exemplar_temperature = max(
            1.0e-6,
            float(state_exemplar_cfg.get("temperature", 0.35)),
        )
        self.coverage_state_exemplar_skip_rejected = bool(
            state_exemplar_cfg.get("skip_rejected", True)
        )
        self.coverage_state_exemplars_by_cell = (
            self._load_coverage_state_exemplars()
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
        self.pre_dig_align_replan_after_failed_dig = bool(
            self.pre_dig_align_cfg.get("replan_after_failed_dig", False)
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
        raw_entry_intent_dims = self.pre_dig_align_cfg.get(
            "entry_intent_controlled_dims"
        )
        self.pre_dig_align_entry_intent_controlled_dims = (
            None
            if raw_entry_intent_dims is None
            else (
                np.asarray(raw_entry_intent_dims, dtype=np.float32).reshape(
                    self.action_dim
                )
                > 0.5
            )
        )
        self.pre_dig_align_entry_intent_handoff_enabled = bool(
            self.pre_dig_align_cfg.get(
                "entry_intent_handoff_enabled",
                self.pre_dig_align_entry_intent_controlled_dims is not None,
            )
        )
        self.pre_dig_align_surface_guard_enabled = bool(
            self.pre_dig_align_cfg.get("surface_guard_enabled", False)
        )
        self.pre_dig_align_surface_guard_max_penetration_m = float(
            self.pre_dig_align_cfg.get("surface_guard_max_penetration_m", 0.005)
        )
        self.pre_dig_align_surface_guard_handoff_entry_error_m = self._optional_float(
            self.pre_dig_align_cfg.get("surface_guard_handoff_entry_error_m")
        )
        self.pre_dig_align_surface_guard_use_contact_fallback = bool(
            self.pre_dig_align_cfg.get("surface_guard_use_contact_fallback", True)
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
        self._pre_dig_align_entry_intent_handoff_ready = False
        self._pre_dig_align_timeout_handoff_reason = ""
        self._pre_dig_align_surface_depth_m = float("nan")
        self._pre_dig_align_surface_guard_triggered = False
        self._pre_dig_align_surface_guard_count = 0
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
        self._dig_depth_profile_tokens = np.zeros(
            DIG_DEPTH_PROFILE_TOKEN_DIM,
            dtype=np.float32,
        )
        self._dig_depth_profile_token_injected = False
        self._dig_depth_profile_token_source = "none"
        self._dig_depth_profile_fallback_reason = ""
        self._return_target_tokens = np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
        self._return_target_token_injected = False
        self._return_relocate_tokens = np.zeros(
            RETURN_TARGET_TOKEN_DIM,
            dtype=np.float32,
        )
        self._return_relocate_token_injected = False
        self._return_start_envelope_tokens = np.zeros(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float32,
        )
        self._return_start_envelope_token_injected = False
        self._return_start_envelope_token_source = "none"
        self._return_start_envelope_use_prior_spatial_bounds = True
        self._return_start_envelope_use_prior_qpos_bounds = True
        self._return_target_planned_cycle_id = -1
        self._return_target_token_source = "none"
        self._return_target_fallback_reason = ""
        self._return_to_dig_entry_error_m = float("nan")
        self._return_to_dig_entry_close_state = True
        self._return_next_dig_event_seen = False
        self._return_to_dig_start_envelope_ready_state = True
        self._return_to_dig_start_envelope_error = float("nan")
        self._return_to_dig_start_envelope_checks: dict[str, Any] = {}
        self._pending_dig_cut_cycle_id = -1
        self._pending_dig_cut_corridor_id = -1
        self._pending_dig_cut_raw_fields: dict[str, float | int] | None = None
        self._pending_dig_cut_tokens: np.ndarray | None = None
        self._pending_dig_depth_profile_tokens: np.ndarray | None = None
        self._pending_dig_state_exemplar_ids: list[str] = []
        self._pending_dig_state_exemplar_distance = float("nan")
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
        self._coverage_pass_index = 0
        self._coverage_terminal_stop_requested = False
        self._coverage_terminal_stop_reason = ""
        self._coverage_candidate_scores: list[dict[str, float | int | str]] = []
        self._coverage_decision_trace: list[dict[str, Any]] = []
        self._coverage_active_state_exemplar_ids: list[str] = []
        self._coverage_rejected_state_exemplar_ids: set[str] = set()
        self._coverage_active_state_exemplar_distance = float("nan")
        self._coverage_active_state_exemplar_profile_token: np.ndarray | None = None
        self._debug_state = self._make_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )

    def _tick_boundary_event(self, obs: dict) -> Any | None:
        if self._prev_action is not None:
            return self.boundary_detector.update(
                env_state=obs.get("env_state", np.zeros(13, dtype=np.float32)),
                action=self._prev_action,
                qpos=obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
                reward_phase=obs.get("reward_phase"),
                task_step_successes=obs.get("task_step_successes"),
                task_metrics=obs.get("task_metrics"),
            )
        return None

    def _reset_tick_switch_reason(self) -> None:
        self._switch_reason = ""

    def _current_tick_skill_name(self) -> str:
        return str(self._skill_name)

    def _account_return_timeout_for_tick(self) -> bool:
        transition_timeout = False
        if self._skill_name == "return":
            self._return_step_count += 1
            if self.return_max_steps > 0 and self._return_step_count >= self.return_max_steps:
                transition_timeout = True
                self._transition_timeout_count += 1
        return transition_timeout

    def _dispatch_tick_action(self, obs: dict) -> np.ndarray:
        if self._skill_name == BOOTSTRAP_SKILL_NAME and self._scripted_bootstrap_enabled():
            return self._scripted_bootstrap_action(obs)
        if self._skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            return self._pre_dig_align_action(obs)
        policy = self._active_policy()
        policy_obs = self._policy_obs(obs)
        return np.asarray(policy.predict(policy_obs), dtype=np.float32).reshape(
            self.action_dim
        )

    def _record_tick_previous_action(self, action: np.ndarray) -> None:
        self._prev_action = action.copy()

    def _transition_completed_after_tick_dispatch(self) -> bool:
        return self._switch_reason.startswith(
            ("return_to_dig_", "return_to_pre_dig_align_")
        )

    def _finalize_tick_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> None:
        self._debug_state = self._make_debug_state(
            transition_timeout=transition_timeout,
            transition_completed=transition_completed,
        )

    def _decide_tick_with_legacy_fsm(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        skill_before = str(preparation.skill_name_before_decision)
        self._maybe_switch_skill(obs=obs, boundary_event=boundary_event)
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=skill_before,
            skill_after=str(self._skill_name),
            switch_reason=str(self._switch_reason),
        )

    def _tick_execution_hooks(self) -> PrimitiveTickCallbacks:
        return PrimitiveTickCallbacks(
            update_boundary_event=self._tick_boundary_event,
            reset_switch_reason=self._reset_tick_switch_reason,
            current_skill_name=self._current_tick_skill_name,
            update_dig_progress=self._update_dig_progress,
            decide_tick=self._decide_tick_with_legacy_fsm,
            account_return_timeout=self._account_return_timeout_for_tick,
            dispatch_action=self._dispatch_tick_action,
            record_previous_action=self._record_tick_previous_action,
            transition_completed_after_dispatch=(
                self._transition_completed_after_tick_dispatch
            ),
            finalize_debug_state=self._finalize_tick_debug_state,
        )

    def predict(self, obs: dict) -> np.ndarray:
        result = run_primitive_tick(hooks=self._tick_execution_hooks(), obs=obs)
        return result.action

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
            "dig_depth_profile_token_injected": bool(
                self._dig_depth_profile_token_injected
            ),
            "dig_depth_profile_token_dim": int(DIG_DEPTH_PROFILE_TOKEN_DIM),
            "dig_depth_profile_source": str(self.dig_depth_profile_source),
            "dig_depth_profile_required": bool(self.dig_depth_profile_required),
            "dig_depth_profile_token_source": str(
                self._dig_depth_profile_token_source
            ),
            "dig_depth_profile_fallback_reason": str(
                self._dig_depth_profile_fallback_reason
            ),
            "dig_failed_replan_next_skill": str(self.dig_failed_replan_next_skill),
            "return_target_token_injected": bool(self._return_target_token_injected),
            "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
            "return_target_token_source": str(self._return_target_token_source),
            "return_target_tokens": self._return_target_tokens.astype(float).tolist(),
            "return_target_fallback_reason": str(
                self._return_target_fallback_reason
            ),
            "return_relocate_token_injected": bool(
                self._return_relocate_token_injected
            ),
            "return_relocate_token_dim": int(RETURN_TARGET_TOKEN_DIM),
            "return_relocate_token_source": str(self._return_target_token_source),
            "return_relocate_tokens": (
                self._return_relocate_tokens.astype(float).tolist()
            ),
            "return_start_envelope_token_injected": bool(
                self._return_start_envelope_token_injected
            ),
            "return_start_envelope_token_dim": int(RETURN_START_ENVELOPE_TOKEN_DIM),
            "return_start_envelope_token_source": str(
                self._return_start_envelope_token_source
            ),
            "return_start_envelope_tokens": (
                self._return_start_envelope_tokens.astype(float).tolist()
            ),
            "return_to_dig_entry_error_m": float(
                self._return_to_dig_entry_error_m
            ),
            "return_to_dig_entry_close": bool(self._return_to_dig_entry_close_state),
            "return_next_dig_event_seen": bool(self._return_next_dig_event_seen),
            "return_to_dig_start_envelope_gate_enabled": bool(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            "return_to_dig_start_envelope_direct_handoff_enabled": bool(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            "return_to_dig_start_envelope_ready": bool(
                self._return_to_dig_start_envelope_ready_state
            ),
            "return_to_dig_start_envelope_plane_depth_mode": str(
                self.return_to_dig_start_envelope_plane_depth_mode
            ),
            "return_to_dig_start_envelope_local_depth_tolerance_m": float(
                self.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            "return_to_dig_start_envelope_error": float(
                self._return_to_dig_start_envelope_error
            ),
            "return_to_dig_start_envelope_checks": dict(
                self._return_to_dig_start_envelope_checks
            ),
            "pending_dig_cut_cycle_id": int(self._pending_dig_cut_cycle_id),
            "pending_dig_cut_corridor_id": int(self._pending_dig_cut_corridor_id),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_token_source": str(self._dig_cut_token_source),
            "dig_cut_tokens": self._dig_cut_tokens.astype(float).tolist(),
            "dig_depth_profile_tokens": (
                self._dig_depth_profile_tokens.astype(float).tolist()
            ),
            "token_in_prior_p10_p90": bool(self._dig_cut_token_in_prior_p10_p90),
            "dig_cut_token_in_prior_p10_p90": bool(
                self._dig_cut_token_in_prior_p10_p90
            ),
            "fallback_reason": str(self._dig_cut_fallback_reason),
            "dig_cut_fallback_reason": str(self._dig_cut_fallback_reason),
            "coverage_corridor_id": int(self._coverage_active_corridor_id),
            "coverage_selected_corridor_id": int(self._coverage_active_corridor_id),
            "coverage_last_selected_corridor_id": int(
                self._coverage_last_selected_corridor_id
            ),
            "coverage_last_selected_cell_id": int(
                self._coverage_corridor_cell_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            "coverage_last_selected_row_id": int(
                self._coverage_corridor_row_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            "coverage_entry_x_m": float(self._coverage_active_value("entry_x_m")),
            "coverage_entry_z_m": float(self._coverage_active_value("entry_z_m")),
            "coverage_exit_x_m": float(self._coverage_active_value("exit_x_m")),
            "coverage_exit_z_m": float(self._coverage_active_value("exit_z_m")),
            "coverage_entry_x_p05_m": float(
                self._coverage_active_value("entry_x_p05_m")
            ),
            "coverage_entry_x_p50_m": float(
                self._coverage_active_value("entry_x_p50_m")
            ),
            "coverage_entry_x_p95_m": float(
                self._coverage_active_value("entry_x_p95_m")
            ),
            "coverage_entry_z_p05_m": float(
                self._coverage_active_value("entry_z_p05_m")
            ),
            "coverage_entry_z_p50_m": float(
                self._coverage_active_value("entry_z_p50_m")
            ),
            "coverage_entry_z_p95_m": float(
                self._coverage_active_value("entry_z_p95_m")
            ),
            "coverage_entry_radial_p75_m": float(
                self._coverage_active_value("entry_radial_p75_m")
            ),
            "coverage_entry_radial_p95_m": float(
                self._coverage_active_value("entry_radial_p95_m")
            ),
            "coverage_exit_x_p05_m": float(
                self._coverage_active_value("exit_x_p05_m")
            ),
            "coverage_exit_x_p50_m": float(
                self._coverage_active_value("exit_x_p50_m")
            ),
            "coverage_exit_x_p95_m": float(
                self._coverage_active_value("exit_x_p95_m")
            ),
            "coverage_exit_z_p05_m": float(
                self._coverage_active_value("exit_z_p05_m")
            ),
            "coverage_exit_z_p50_m": float(
                self._coverage_active_value("exit_z_p50_m")
            ),
            "coverage_exit_z_p95_m": float(
                self._coverage_active_value("exit_z_p95_m")
            ),
            "coverage_exit_radial_p75_m": float(
                self._coverage_active_value("exit_radial_p75_m")
            ),
            "coverage_exit_radial_p95_m": float(
                self._coverage_active_value("exit_radial_p95_m")
            ),
            "coverage_cut_depth_peak_p05_m": float(
                self._coverage_active_value("cut_depth_peak_p05_m")
            ),
            "coverage_cut_depth_peak_p50_m": float(
                self._coverage_active_value("cut_depth_peak_p50_m")
            ),
            "coverage_cut_depth_peak_p95_m": float(
                self._coverage_active_value("cut_depth_peak_p95_m")
            ),
            "coverage_cell_id": int(self._coverage_active_cell_id()),
            "coverage_corridor_score": float(self._coverage_active_corridor_score()),
            "coverage_state_exemplar_enabled": bool(
                self.coverage_state_exemplars_enabled
            ),
            "coverage_state_exemplar_ids": list(
                self._coverage_active_state_exemplar_ids
            ),
            "coverage_state_exemplar_distance": float(
                self._coverage_active_state_exemplar_distance
            ),
            "coverage_depleted_count": int(self._coverage_depleted_count()),
            "coverage_pass_index": int(self._coverage_pass_index),
            "coverage_multi_pass_enabled": bool(self.coverage_multi_pass_enabled),
            "coverage_multi_pass_max_passes": int(self.coverage_multi_pass_max_passes),
            "coverage_multi_pass_min_remaining_depth_m": float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
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
            "pre_dig_align_replan_after_failed_dig": bool(
                self.pre_dig_align_replan_after_failed_dig
            ),
            "pre_dig_align_entry_intent_controlled_dims": (
                None
                if self.pre_dig_align_entry_intent_controlled_dims is None
                else [
                    int(value)
                    for value in self.pre_dig_align_entry_intent_controlled_dims.tolist()
                ]
            ),
            "pre_dig_align_surface_guard_enabled": bool(
                self.pre_dig_align_surface_guard_enabled
            ),
            "pre_dig_align_surface_depth_m": float(
                self._pre_dig_align_surface_depth_m
            ),
            "pre_dig_align_surface_guard_triggered": bool(
                self._pre_dig_align_surface_guard_triggered
            ),
            "pre_dig_align_surface_guard_count": int(
                self._pre_dig_align_surface_guard_count
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
            "pre_dig_align_entry_intent_handoff_enabled": bool(
                self.pre_dig_align_entry_intent_handoff_enabled
            ),
            "pre_dig_align_entry_intent_handoff_ready": bool(
                self._pre_dig_align_entry_intent_handoff_ready
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
            "return_next_dig_event_seen": int(self._return_next_dig_event_seen),
            "return_to_dig_start_envelope_gate_enabled": int(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            "return_to_dig_start_envelope_direct_handoff_enabled": int(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            "return_to_dig_start_envelope_ready": int(
                self._return_to_dig_start_envelope_ready_state
            ),
            "return_to_dig_start_envelope_plane_depth_mode": str(
                self.return_to_dig_start_envelope_plane_depth_mode
            ),
            "return_to_dig_start_envelope_local_depth_tolerance_m": float(
                self.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            "return_to_dig_start_envelope_error": float(
                self._return_to_dig_start_envelope_error
            ),
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
            "dig_failed_replan_next_skill": str(self.dig_failed_replan_next_skill),
            "coverage_selected_corridor_id": int(self._coverage_active_corridor_id),
            "coverage_depleted_count": int(self._coverage_depleted_count()),
            "coverage_completed_dump_count": int(self._coverage_completed_dump_count),
            "coverage_pass_index": int(self._coverage_pass_index),
            "coverage_multi_pass_enabled": int(self.coverage_multi_pass_enabled),
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
            "pre_dig_align_replan_after_failed_dig": int(
                self.pre_dig_align_replan_after_failed_dig
            ),
            "pre_dig_align_surface_guard_enabled": int(
                self.pre_dig_align_surface_guard_enabled
            ),
            "pre_dig_align_surface_guard_count": int(
                self._pre_dig_align_surface_guard_count
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
                "length,cut_depth_semantic,payload,valid"
            ),
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
            "dig_cut_prior_path": str(self.dig_cut_prior_path),
            "return_target_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
            "return_target_token_contract": (
                "next entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
                "length,cut_depth_semantic,payload,valid"
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
            "coverage_pass_index": int(self._coverage_pass_index),
            "coverage_multi_pass_enabled": bool(self.coverage_multi_pass_enabled),
            "coverage_multi_pass_max_passes": int(self.coverage_multi_pass_max_passes),
            "coverage_multi_pass_min_remaining_depth_m": float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if self.coverage_first_dig_preferred_corridor_id is None
                else self.coverage_first_dig_preferred_corridor_id
            ),
            "coverage_corridors": [
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ],
            "coverage_decision_trace": list(self._coverage_decision_trace),
            "coverage_decision_trace_count": int(len(self._coverage_decision_trace)),
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
            if self._pre_dig_align_surface_guard_triggered_for_state(obs):
                self._pre_dig_align_surface_guard_count += 1
                self._pre_dig_align_hold_count = 0
                if self._pre_dig_align_surface_guard_can_handoff(obs):
                    self._pre_dig_align_completed_count += 1
                    self._set_skill("dig", "pre_dig_align_to_dig_surface_guard")
                else:
                    self._reject_active_coverage_corridor(
                        obs,
                        reason="pre_align_surface_penetration_entry_gap",
                    )
                    self._restart_dig_with_new_cut(
                        "pre_dig_align_to_dig_surface_guard_replan"
                    )
            elif self._pre_dig_align_ready(obs):
                self._pre_dig_align_completed_count += 1
                self._set_skill("dig", "pre_dig_align_to_dig_ready")
            elif self._pre_dig_align_step_count >= self.pre_dig_align_max_steps:
                self._pre_dig_align_timeout_count += 1
                if self._pre_dig_align_timeout_can_handoff(obs):
                    reason = (
                        self._pre_dig_align_timeout_handoff_reason
                        or "pre_dig_align_to_dig_timeout_close_enough"
                    )
                    self._set_skill("dig", reason)
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
                self._restart_after_failed_dig(
                    "exit_overshoot_low_payload",
                    obs,
                )
                return
            if self._dig_bad_replan_ready(obs):
                self._dig_bad_replan_count += 1
                self._reject_active_coverage_corridor(
                    obs,
                    reason="bad_dig_low_payload",
                )
                self._restart_after_failed_dig("bad_dig_low_payload", obs)
                return
            if self._dig_complete_boundary_low_payload(obs, boundary_event):
                self._dig_bad_replan_count += 1
                self._reject_active_coverage_corridor(
                    obs,
                    reason="dig_complete_low_current_payload",
                )
                self._restart_after_failed_dig("complete_low_payload", obs)
                return
            if self._dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
                self._complete_cell_entry_dig(obs)
                self._complete_coverage_dig(obs)
                reason = self._dig_to_carry_reason or "loaded"
                self._set_skill("carry", f"dig_to_carry_{reason}")
            return

        if self._skill_name == "carry":
            if self._carry_release_safety_done(obs):
                self._complete_coverage_dump(obs, reason="carry_release_safety")
                self._set_return_or_direct_handoff(
                    obs,
                    reason="carry_to_return_release_safety",
                )
                return
            dump_committed_event = bool(
                boundary_event is not None
                and getattr(boundary_event, "dump_committed_start", False)
            )
            release_onset_event = bool(
                boundary_event is not None
                and getattr(boundary_event, "release_onset", False)
            )
            dump_complete_event = bool(
                boundary_event is not None
                and getattr(boundary_event, "dump_complete", False)
            )
            if dump_complete_event:
                self._complete_coverage_dump(obs, reason="carry_dump_complete_boundary")
                self._set_return_or_direct_handoff(
                    obs,
                    reason="carry_to_return_dump_complete_boundary",
                )
                return
            legacy_dump_start_event = bool(
                boundary_event is not None
                and getattr(boundary_event, "dump_start", False)
                and not self._semantic_boundary_profile_active()
            )
            if dump_committed_event or release_onset_event or legacy_dump_start_event:
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
                    else "release_onset_boundary"
                    if release_onset_event
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
                self._set_return_or_direct_handoff(
                    obs,
                    reason=(
                        "dump_to_return_dump_complete_boundary"
                        if reason == "dump_complete_boundary"
                        else "dump_to_return_dump_end"
                    ),
                )
                return
            if not self._semantic_boundary_profile_active() and self._dump_done(obs):
                self._dump_done_hold_count += 1
            else:
                self._dump_done_hold_count = 0
            if self._dump_done_hold_count >= self.dump_done_hold_steps:
                self._complete_coverage_dump(obs, reason="dump_mass_low")
                self._set_return_or_direct_handoff(
                    obs,
                    reason="dump_to_return_mass_low",
                )
            return

        if self._skill_name == "return":
            handoff_ready = self._return_to_dig_handoff_ready(obs)
            next_dig_event = bool(
                boundary_event is not None
                and (
                    getattr(boundary_event, "next_dig_entry_ready", False)
                    or getattr(boundary_event, "qualified_dig_start", False)
                )
            )
            if next_dig_event:
                self._return_next_dig_event_seen = True
            if (next_dig_event or self._return_next_dig_event_seen) and handoff_ready:
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
            if self._return_to_dig_direct_handoff_ready(
                obs,
                handoff_ready=handoff_ready,
            ):
                self._completed_transition_count += 1
                self._cycle_index += 1
                next_skill = (
                    PRE_DIG_ALIGN_SKILL_NAME
                    if self._should_pre_dig_align_before_dig()
                    else "dig"
                )
                self._set_skill(
                    next_skill,
                    f"return_to_{next_skill}_start_envelope_ready",
                )
                return
            if (
                not self._semantic_boundary_profile_active()
                and self._return_to_dig_shallow_guard_ready(
                    obs=obs,
                    boundary_event=boundary_event,
                )
                and handoff_ready
            ):
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

    def _set_return_or_direct_handoff(self, obs: dict, *, reason: str) -> None:
        self._set_skill("return", reason)
        self._try_return_direct_handoff_at_current_obs(obs)

    def _try_return_direct_handoff_at_current_obs(self, obs: dict) -> bool:
        if self._skill_name != "return":
            return False
        if not self.return_target_planner_enabled:
            return False
        if not self.return_to_dig_start_envelope_direct_handoff_enabled:
            return False
        self._ensure_return_target_plan_for_cycle(obs)
        handoff_ready = self._return_to_dig_handoff_ready(obs)
        if not self._return_to_dig_direct_handoff_ready(
            obs,
            handoff_ready=handoff_ready,
        ):
            return False
        self._completed_transition_count += 1
        self._cycle_index += 1
        next_skill = (
            PRE_DIG_ALIGN_SKILL_NAME
            if self._should_pre_dig_align_before_dig()
            else "dig"
        )
        self._set_skill(
            next_skill,
            f"return_to_{next_skill}_start_envelope_ready",
        )
        return True

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
            self._return_next_dig_event_seen = False
        elif skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            self._pre_dig_align_step_count = 0
            self._pre_dig_align_hold_count = 0
            self._pre_dig_align_entry_close_handoff_ready = False
            self._pre_dig_align_entry_intent_handoff_ready = False
            self._pre_dig_align_timeout_handoff_reason = ""
            self._pre_dig_align_surface_guard_triggered = False
        elif skill_name == "dig":
            self._return_next_dig_event_seen = False
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
        self._pre_dig_align_entry_intent_handoff_ready = False
        self._pre_dig_align_timeout_handoff_reason = ""
        self._pre_dig_align_surface_guard_triggered = False
        self._dig_step_count = 0
        self._dig_best_mass_kg = 0.0
        self._dig_mass_plateau_count = 0
        self._dig_to_carry_reason = ""
        self._coverage_current_payload_gain_kg = 0.0
        self._coverage_active_corridor_id = -1
        self._return_next_dig_event_seen = False
        self._invalidate_pending_dig_cut_plan()
        self._clear_dig_cut_plan()

    def _try_replan_pre_dig_align_handoff(self, obs: dict) -> bool:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return False
        self._coverage_active_corridor_id = -1
        self._invalidate_pending_dig_cut_plan()
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
        self._invalidate_pending_dig_cut_plan()
        self._clear_dig_cut_plan()

    def _stop_after_failed_dig(self, reason: str, obs: dict) -> None:
        corridor = self._coverage_active_corridor()
        payload_gain = max(
            float(self._coverage_current_payload_gain_kg),
            float(self._dig_best_mass_kg),
            self._mass_in_bucket(obs),
            0.0,
        )
        self._switch_reason = f"dig_failed_stop_{reason}"
        self._record_coverage_decision_event(
            "failed_dig_stop",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "payload_gain_kg": float(payload_gain),
                "current_bucket_mass_kg": float(self._mass_in_bucket(obs)),
                "dig_best_mass_kg": float(self._dig_best_mass_kg),
                "dig_step_count": int(self._dig_step_count),
            },
        )
        self._request_coverage_terminal_stop(
            f"dig_failed_{reason}",
            replace=True,
        )

    def _restart_after_failed_dig(self, reason: str, obs: dict) -> None:
        if (
            self._should_pre_dig_align_before_dig()
            or self._should_pre_dig_align_after_failed_dig()
        ):
            self._restart_pre_dig_align(f"dig_to_pre_dig_align_{reason}")
            return
        if self.dig_failed_replan_next_skill == "stop":
            self._stop_after_failed_dig(reason, obs)
            return
        self._restart_dig_with_new_cut(f"dig_retry_{reason}")

    def _should_pre_dig_align_before_dig(self) -> bool:
        if not self.pre_dig_align_enabled:
            return False
        if not self.pre_dig_align_first_dig_only:
            return True
        return int(getattr(self, "_cycle_index", 0)) == 0

    def _should_pre_dig_align_after_failed_dig(self) -> bool:
        return bool(
            self.pre_dig_align_enabled
            and self.pre_dig_align_replan_after_failed_dig
        )

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

    def _pre_dig_align_surface_guard_triggered_for_state(self, obs: dict) -> bool:
        self._pre_dig_align_surface_depth_m = float(
            self._bucket_depth_below_local_surface(obs)
        )
        self._pre_dig_align_surface_guard_triggered = False
        if not (
            self.pre_dig_align_enabled
            and self.pre_dig_align_surface_guard_enabled
        ):
            return False
        if (
            np.isfinite(self._pre_dig_align_surface_depth_m)
            and self._pre_dig_align_surface_depth_m
            > self.pre_dig_align_surface_guard_max_penetration_m
        ):
            self._pre_dig_align_surface_guard_triggered = True
            return True
        if (
            not np.isfinite(self._pre_dig_align_surface_depth_m)
            and self.pre_dig_align_surface_guard_use_contact_fallback
            and self._bucket_dig_area_contact_mask(obs)
        ):
            self._pre_dig_align_surface_guard_triggered = True
            return True
        return False

    def _pre_dig_align_surface_guard_can_handoff(self, obs: dict) -> bool:
        self._ensure_dig_cut_plan_for_cycle(obs)
        threshold = self.pre_dig_align_surface_guard_handoff_entry_error_m
        if threshold is None:
            threshold = self.pre_dig_align_max_entry_error_m
        if threshold is None:
            threshold = self.pre_dig_align_start_envelope_max_entry_error_m
        entry_error = self._pre_dig_align_entry_error(obs)
        self._pre_dig_align_entry_error_m = float(entry_error)
        return self._pre_dig_align_entry_close(entry_error, threshold=threshold)

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
        entry_intent_handoff_ready = (
            self._pre_dig_align_entry_intent_handoff_ready_for_state(
                qpos_close=qpos_close,
                qvel_small=qvel_small,
            )
        )
        self._pre_dig_align_entry_intent_handoff_ready = bool(
            entry_intent_handoff_ready
        )
        if entry_close_handoff_ready or entry_intent_handoff_ready or (
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

    def _pre_dig_align_entry_intent_mode_enabled(self) -> bool:
        if not self.pre_dig_align_entry_intent_handoff_enabled:
            return False
        intent_dims = self.pre_dig_align_entry_intent_controlled_dims
        if intent_dims is None:
            return False
        controlled = self.pre_dig_align_controlled_dims
        return bool(np.any(controlled & intent_dims) and np.any(controlled & ~intent_dims))

    def _pre_dig_align_entry_intent_handoff_ready_for_state(
        self,
        *,
        qpos_close: bool,
        qvel_small: bool,
    ) -> bool:
        return bool(
            self._pre_dig_align_entry_intent_mode_enabled()
            and qpos_close
            and qvel_small
        )

    def _pre_dig_align_timeout_can_handoff(self, obs: dict) -> bool:
        self._pre_dig_align_timeout_handoff_reason = ""
        threshold = self.pre_dig_align_timeout_accept_entry_error_m
        if threshold is None:
            threshold = self.pre_dig_align_max_entry_error_m
        if threshold is None:
            self._pre_dig_align_timeout_handoff_reason = (
                "pre_dig_align_to_dig_timeout_no_entry_gate"
            )
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
        if self._pre_dig_align_entry_intent_mode_enabled():
            self._pre_dig_align_entry_intent_handoff_ready = True
            self._pre_dig_align_timeout_handoff_reason = (
                "pre_dig_align_to_dig_timeout_intent_aligned"
            )
            return True
        if (
            self._pre_dig_align_entry_close(entry_error, threshold=threshold)
            or start_envelope_ready
        ):
            self._pre_dig_align_timeout_handoff_reason = (
                "pre_dig_align_to_dig_timeout_close_enough"
            )
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
        if self._pre_dig_align_surface_guard_triggered_for_state(obs):
            return np.zeros(self.action_dim, dtype=np.float32)
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
        if self.pre_dig_align_entry_intent_controlled_dims is not None:
            # Pre-align may consume the planned entry point, but not the dig-depth
            # posture implied by a full dig-start token.
            hold_dims = (
                self.pre_dig_align_controlled_dims
                & ~self.pre_dig_align_entry_intent_controlled_dims
            )
            target[hold_dims] = qpos[hold_dims]
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
            if self._semantic_dig_to_carry_liveness_ready(
                obs=obs,
                boundary_event=boundary_event,
            ):
                return True
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

    def _semantic_dig_to_carry_liveness_ready(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        mass = float(metrics.get("mass_in_bucket_kg", self._mass_in_bucket(obs)))
        dig_distance = float(
            metrics.get("min_distance_to_dig_area_m", self._min_distance_to_dig_area(obs))
        )
        distance_ready = bool(
            dig_distance >= self.dig_to_carry_min_distance_to_dig_area_m
        )
        if not distance_ready:
            return False
        if mass >= self.dig_to_carry_target_bucket_mass_kg:
            self._dig_to_carry_reason = "semantic_material_loaded"
            return True
        if (
            self.dig_to_carry_mass_plateau_enabled
            and self._dig_step_count >= self.dig_to_carry_mass_plateau_min_steps
            and mass >= self.dig_to_carry_mass_plateau_min_bucket_mass_kg
            and self._dig_mass_plateau_count
            >= self.dig_to_carry_mass_plateau_hold_steps
        ):
            self._dig_to_carry_reason = "semantic_material_plateau"
            return True
        return False

    def _dig_complete_boundary_low_payload(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        if not self._semantic_boundary_profile_active():
            return False
        if boundary_event is None or not bool(
            getattr(boundary_event, "dig_complete", False)
        ):
            return False
        min_carry_mass = max(
            float(self.dig_to_carry_min_bucket_mass_kg),
            float(self.dump_ready_min_bucket_mass_kg),
        )
        return bool(self._mass_in_bucket(obs) < min_carry_mass)

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

    def _carry_release_safety_done(self, obs: dict) -> bool:
        if not self._semantic_boundary_profile_active():
            return False
        deposit_delta = self._deposited_mass(obs) - float(
            self._coverage_cycle_start_deposit_kg
        )
        return bool(
            self._mass_in_bucket(obs) <= self.dump_done_max_bucket_mass_kg
            and deposit_delta >= self.dump_done_min_deposit_delta_kg
        )

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

    def _return_to_dig_handoff_ready(self, obs: dict) -> bool:
        entry_close = self._return_to_dig_entry_close(obs)
        envelope_ready = self._return_to_dig_start_envelope_ready(obs)
        return bool(entry_close and envelope_ready)

    def _return_to_dig_direct_handoff_ready(
        self,
        obs: dict,
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        if not self.return_to_dig_start_envelope_direct_handoff_enabled:
            return False
        if not self.return_to_dig_start_envelope_gate_enabled:
            return False
        ready = (
            self._return_to_dig_handoff_ready(obs)
            if handoff_ready is None
            else bool(handoff_ready)
        )
        if not ready:
            return False
        return bool(
            self._mass_in_bucket(obs) <= self.return_to_dig_max_bucket_mass_kg
        )

    def _return_to_dig_start_envelope_ready(self, obs: dict) -> bool:
        if not self.return_to_dig_start_envelope_gate_enabled:
            self._return_to_dig_start_envelope_ready_state = True
            self._return_to_dig_start_envelope_error = float("nan")
            self._return_to_dig_start_envelope_checks = {}
            return True

        token = np.asarray(
            self._return_start_envelope_tokens,
            dtype=np.float32,
        ).reshape(-1)
        if token.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
            self._return_to_dig_start_envelope_ready_state = True
            self._return_to_dig_start_envelope_error = float("nan")
            self._return_to_dig_start_envelope_checks = {"missing_token": True}
            return True
        if float(token[16]) <= 0.5 and float(token[17]) <= 0.5:
            self._return_to_dig_start_envelope_ready_state = True
            self._return_to_dig_start_envelope_error = float("nan")
            self._return_to_dig_start_envelope_checks = {"invalid_token": True}
            return True

        lower, upper = self._return_start_envelope_prior_bounds(
            int(self._pending_dig_cut_corridor_id)
        )
        prior_mapping, _ = self._return_start_envelope_prior_mapping(
            corridor_id=int(self._pending_dig_cut_corridor_id)
        )
        checks: dict[str, Any] = {}
        max_error = 0.0
        ready = True

        def bounds_for(
            index: int,
            tolerance: float,
            *,
            use_prior_bounds: bool = True,
        ) -> tuple[float, float]:
            if use_prior_bounds and lower is not None and upper is not None:
                low = float(lower[index]) - float(tolerance)
                high = float(upper[index]) + float(tolerance)
            else:
                low = float(token[index]) - float(tolerance)
                high = float(token[index]) + float(tolerance)
            return low, high

        def add_check(name: str, value: float, low: float, high: float) -> bool:
            nonlocal max_error, ready
            finite = bool(np.isfinite(value) and np.isfinite(low) and np.isfinite(high))
            if not finite:
                ok = False
                error = float("inf")
            else:
                error = max(float(low) - float(value), float(value) - float(high), 0.0)
                ok = bool(error <= 1.0e-6)
                max_error = max(max_error, float(error))
            ready = bool(ready and ok)
            checks[name] = {
                "value": float(value),
                "min": float(low),
                "max": float(high),
                "ok": bool(ok),
                "error": float(error),
            }
            return bool(ok)

        env_state = self._env_state(obs)
        local_depth_prior = (
            None
            if prior_mapping is None
            else prior_mapping.get("dig_start_local_depth_m")
        )
        local_depth_prior_used = False
        require_contact = bool(
            self.return_to_dig_start_envelope_require_contact
            or float(token[6]) > 0.5
        )
        if float(token[17]) > 0.5:
            if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
                spatial_tol = self.return_to_dig_start_envelope_spatial_tolerance
                low, high = bounds_for(
                    0,
                    spatial_tol,
                    use_prior_bounds=self._return_start_envelope_use_prior_spatial_bounds,
                )
                add_check(
                    "long_norm",
                    float(env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]),
                    low,
                    high,
                )
                low, high = bounds_for(
                    1,
                    spatial_tol,
                    use_prior_bounds=self._return_start_envelope_use_prior_spatial_bounds,
                )
                add_check(
                    "short_norm",
                    float(env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]),
                    low,
                    high,
                )
            else:
                ready = False
                checks["spatial_missing"] = True

            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
                local_value = float(
                    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX]
                )
                if isinstance(local_depth_prior, dict):
                    local_depth_prior_used = True
                    local_tol = (
                        self.return_to_dig_start_envelope_local_depth_tolerance_m
                    )
                    p05 = float(local_depth_prior.get("p05", token[4]))
                    p50 = float(local_depth_prior.get("p50", token[2]))
                    p95 = float(local_depth_prior.get("p95", token[5]))
                    low = p05 - local_tol
                    high = p95 + local_tol
                    add_check("local_depth_m", local_value, low, high)
                    checks["local_depth_m"].update(
                        {
                            "mode": "prior_range",
                            "target": float(p50),
                            "p05": float(p05),
                            "p50": float(p50),
                            "p95": float(p95),
                        }
                    )
                else:
                    depth_tol = self.return_to_dig_start_envelope_depth_tolerance_m
                    low = float(token[4]) - depth_tol
                    high = float(token[5]) + depth_tol
                    add_check("local_depth_m", local_value, low, high)
                    checks["local_depth_m"].update({"mode": "token_range"})
            else:
                ready = False
                checks["local_depth_missing"] = True

            plane_depth_prior = (
                None
                if prior_mapping is None
                else prior_mapping.get("dig_start_plane_depth_m")
            )
            if isinstance(plane_depth_prior, dict):
                plane_tol = self.return_to_dig_start_envelope_plane_depth_tolerance_m
                p05 = float(plane_depth_prior.get("p05", token[2]))
                p50 = float(plane_depth_prior.get("p50", token[2]))
                p95 = float(plane_depth_prior.get("p95", token[5]))
                mode = self.return_to_dig_start_envelope_plane_depth_mode
                if mode == "target_band":
                    low = p50 - plane_tol
                    high = p50 + plane_tol
                elif mode == "p50_floor":
                    plane_floor = (
                        p05 if local_depth_prior_used and require_contact else p50
                    )
                    low = plane_floor - plane_tol
                    high = p95 + plane_tol
                else:
                    low = p05 - plane_tol
                    high = p95 + plane_tol
                add_check(
                    "plane_depth_m",
                    float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]),
                    low,
                    high,
                )
                checks["plane_depth_m"].update(
                    {
                        "mode": str(mode),
                        "target": float(p50),
                        "p05": float(p05),
                        "p50": float(p50),
                        "p95": float(p95),
                        "floor_source": (
                            "p05_local_contact_prior"
                            if mode == "p50_floor"
                            and local_depth_prior_used
                            and require_contact
                            else "p50"
                            if mode == "p50_floor"
                            else "range"
                        ),
                    }
                )

            if require_contact:
                if len(env_state) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX:
                    contact = float(env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX])
                    ok = bool(contact > 0.5)
                    ready = bool(ready and ok)
                    checks["dig_contact"] = {
                        "value": contact,
                        "ok": ok,
                        "required_by_config": bool(
                            self.return_to_dig_start_envelope_require_contact
                        ),
                        "required_by_token": bool(float(token[6]) > 0.5),
                    }
                else:
                    ready = False
                    checks["dig_contact_missing"] = True

        if float(token[16]) > 0.5:
            qpos = np.asarray(
                obs.get("qpos", np.zeros(self.action_dim)),
                dtype=np.float32,
            ).reshape(-1)
            if qpos.shape[0] >= 4:
                qpos_tol = self.return_to_dig_start_envelope_qpos_tolerance
                for offset in range(4):
                    index = 7 + offset
                    if (
                        self._return_start_envelope_use_prior_qpos_bounds
                        and lower is not None
                        and upper is not None
                    ):
                        low = float(lower[index]) - qpos_tol
                        high = float(upper[index]) + qpos_tol
                    else:
                        half_width = max(float(token[11 + offset]), qpos_tol)
                        low = float(token[index]) - half_width - qpos_tol
                        high = float(token[index]) + half_width + qpos_tol
                    add_check(f"qpos_{offset}", float(qpos[offset]), low, high)
            else:
                ready = False
                checks["qpos_missing"] = True

        self._return_to_dig_start_envelope_ready_state = bool(ready)
        self._return_to_dig_start_envelope_error = float(max_error)
        self._return_to_dig_start_envelope_checks = checks
        return bool(ready)

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

    def _bucket_depth_below_local_surface(self, obs: dict) -> float:
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if "bucket_depth_below_local_surface_m" in task_metrics:
            return float(task_metrics["bucket_depth_below_local_surface_m"])
        env_state = self._env_state(obs)
        return (
            float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX])
            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX
            else float("nan")
        )

    def _bucket_dig_area_contact_mask(self, obs: dict) -> bool:
        task_metrics = dict(obs.get("task_metrics", {}) or {})
        if "bucket_dig_area_penetration_contact_mask" in task_metrics:
            return bool(float(task_metrics["bucket_dig_area_penetration_contact_mask"]) > 0.5)
        if "bucket_contact_dig_area_mask" in task_metrics:
            return bool(float(task_metrics["bucket_contact_dig_area_mask"]) > 0.5)
        env_state = self._env_state(obs)
        return bool(
            len(env_state) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX
            and float(env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX]) > 0.5
        )

    def _env_state(self, obs: dict) -> np.ndarray:
        return np.asarray(
            obs.get("env_state", np.zeros(13, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(-1)

    def _policy_obs(self, obs: dict) -> dict:
        self._cell_entry_token_injected = False
        self._dig_cut_token_injected = False
        self._dig_depth_profile_token_injected = False
        self._return_target_token_injected = False
        self._return_relocate_token_injected = False
        self._return_start_envelope_token_injected = False
        goal_tokens = self._goal_tokens()
        cell_entry_tokens = self._cell_entry_tokens_for_obs(obs)
        dig_cut_tokens = self._dig_cut_tokens_for_obs(obs)
        dig_depth_profile_tokens = self._dig_depth_profile_tokens_for_obs(obs)
        return_target_tokens = self._return_target_tokens_for_obs(obs)
        return_relocate_tokens = self._return_relocate_tokens_for_obs(obs)
        return_start_envelope_tokens = (
            self._return_start_envelope_tokens_for_obs(obs)
        )
        if (
            goal_tokens is None
            and cell_entry_tokens is None
            and dig_cut_tokens is None
            and dig_depth_profile_tokens is None
            and return_target_tokens is None
            and return_relocate_tokens is None
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
        if dig_depth_profile_tokens is not None:
            policy_obs["dig_depth_profile_tokens_v1"] = dig_depth_profile_tokens
            self._dig_depth_profile_token_injected = True
        if return_target_tokens is not None:
            policy_obs["return_target_tokens"] = return_target_tokens
            self._return_target_token_injected = True
        if return_relocate_tokens is not None:
            policy_obs["return_relocate_tokens_v1"] = return_relocate_tokens
            self._return_relocate_token_injected = True
        if return_start_envelope_tokens is not None:
            policy_obs["return_start_envelope_tokens_v1"] = return_start_envelope_tokens
            self._return_start_envelope_token_injected = True
        return policy_obs

    def _return_target_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self._return_target_tokens.copy()

    def _return_relocate_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        token = self._return_relocate_token_planner().plan(self._return_target_tokens)
        self._return_relocate_tokens = token
        return token.copy()

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
                self._build_return_start_envelope_tokens_for_obs(
                    obs,
                    raw_fields,
                    corridor_id=corridor_id,
                )
            )
            self._return_target_token_source = str(source)
            self._return_target_fallback_reason = str(fallback_reason)
            self._return_target_planned_cycle_id = int(self._cycle_index)
            self._pending_dig_cut_cycle_id = int(self._cycle_index) + 1
            self._pending_dig_cut_raw_fields = dict(raw_fields)
            self._pending_dig_cut_tokens = token.astype(np.float32)
            self._pending_dig_cut_corridor_id = int(corridor_id)
            self._pending_dig_depth_profile_tokens = (
                None
                if self._coverage_active_state_exemplar_profile_token is None
                else self._coverage_active_state_exemplar_profile_token.astype(
                    np.float32
                ).copy()
            )
            self._pending_dig_state_exemplar_ids = list(
                self._coverage_active_state_exemplar_ids
            )
            self._pending_dig_state_exemplar_distance = float(
                self._coverage_active_state_exemplar_distance
            )
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
            self._return_start_envelope_token_source = "fallback_zero"
            self._return_target_fallback_reason = str(exc)
            self._return_target_planned_cycle_id = int(self._cycle_index)
            self._invalidate_pending_dig_cut_plan()

    def _dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if not self.dig_cut_planner_enabled:
            return None
        if self._coverage_terminal_stop_requested:
            return self._dig_cut_tokens.copy() if self._skill_name == "dig" else None
        if self._skill_name != "dig":
            if (
                self._skill_name != BOOTSTRAP_SKILL_NAME
                or self.bootstrap_policy is None
            ):
                return None
        self._ensure_dig_cut_plan_for_cycle(obs)
        return self._dig_cut_tokens.copy()

    def _dig_depth_profile_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if not self.dig_cut_planner_enabled:
            return None
        if self._coverage_terminal_stop_requested:
            return (
                self._dig_depth_profile_tokens.copy()
                if self._skill_name == "dig"
                else None
            )
        if self._skill_name != "dig":
            if (
                self._skill_name != BOOTSTRAP_SKILL_NAME
                or self.bootstrap_policy is None
            ):
                return None
        self._ensure_dig_cut_plan_for_cycle(obs)
        return self._dig_depth_profile_tokens.copy()

    def _ensure_dig_cut_plan_for_cycle(self, obs: dict) -> None:
        if not self.dig_cut_planner_enabled:
            return
        if (
            self.dig_cut_hold_token_until_skill_exit
            and self._dig_cut_planned_cycle_id == int(self._cycle_index)
        ):
            return
        self._dig_cut_tokens = self._build_dig_cut_tokens_for_obs(obs)
        self._dig_depth_profile_tokens = self._build_dig_depth_profile_tokens_for_obs(
            obs
        )
        self._dig_cut_planned_cycle_id = int(self._cycle_index)

    def _build_dig_depth_profile_tokens_for_obs(self, obs: dict) -> np.ndarray:
        cell_id = self._dig_depth_profile_cell_id(obs)
        planner = self._dig_depth_profile_token_planner()
        try:
            plan = planner.plan(
                cell_id=cell_id,
                raw_fields=self._dig_depth_profile_raw_fields(obs),
                env_state=self._env_state(obs),
                state_exemplar_profile_token=(
                    self._coverage_active_state_exemplar_profile_token
                ),
            )
        except DigDepthProfileTokenPlanningError as exc:
            self._dig_depth_profile_token_source = str(exc.token_source)
            self._dig_depth_profile_fallback_reason = str(exc.fallback_reason)
            raise
        return self._apply_dig_depth_profile_token_plan(plan)

    def _apply_dig_depth_profile_token_plan(
        self,
        plan: DigDepthProfileTokenPlan,
    ) -> np.ndarray:
        self._dig_depth_profile_token_source = str(plan.source)
        self._dig_depth_profile_fallback_reason = str(plan.fallback_reason)
        return plan.token.copy()

    def _build_live_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict,
        *,
        cell_id: int,
    ) -> np.ndarray:
        raw_fields = self._dig_depth_profile_raw_fields(obs)
        return self._dig_depth_profile_token_planner().live_plan_token(
            cell_id=cell_id,
            raw_fields=raw_fields,
            env_state=self._env_state(obs),
        )

    def _dig_depth_profile_prior_token(
        self,
        cell_id: int,
    ) -> tuple[np.ndarray | None, str, str]:
        return self._dig_depth_profile_token_planner().prior_token(cell_id)

    def _dig_depth_profile_prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object] | None, str, str]:
        return self._dig_depth_profile_token_planner().prior_mapping(cell_id)

    @staticmethod
    def _dig_depth_profile_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        return DigDepthProfileTokenPlanner.token_from_prior_mapping(mapping)

    def _dig_depth_profile_raw_fields(self, obs: dict) -> dict[str, float | int]:
        if (
            self._pending_dig_cut_raw_fields is not None
            and self._pending_dig_cut_cycle_id == int(self._cycle_index)
        ):
            return dict(self._pending_dig_cut_raw_fields)
        corridor = self._coverage_active_corridor()
        if corridor is not None:
            return self._coverage_raw_fields(corridor, obs=obs)
        raw_fields = self._raw_fields_from_live_pose(obs)
        token = np.asarray(self._dig_cut_tokens, dtype=np.float32).reshape(-1)
        if token.size >= DIG_CUT_TOKEN_DIM:
            raw_fields.update(
                {
                    "operator_entry_x_m": float(token[0]) * DIG_CUT_POSITION_SCALE_M,
                    "operator_entry_z_m": float(token[1]) * DIG_CUT_POSITION_SCALE_M,
                    "operator_exit_x_m": float(token[2]) * DIG_CUT_POSITION_SCALE_M,
                    "operator_exit_z_m": float(token[3]) * DIG_CUT_POSITION_SCALE_M,
                    "operator_cut_direction_x": float(token[4]),
                    "operator_cut_direction_z": float(token[5]),
                    "operator_cut_length_m": float(token[6]) * DIG_CUT_LENGTH_SCALE_M,
                    "operator_cut_depth_peak_m": float(token[7])
                    * DIG_CUT_DEPTH_SCALE_M,
                    "operator_cut_payload_gain_kg": float(token[8])
                    * DIG_CUT_PAYLOAD_SCALE_KG,
                    "operator_cut_valid": int(float(token[9]) > 0.5),
                }
            )
        return raw_fields

    def _dig_depth_profile_cell_id(self, obs: dict) -> int:
        if (
            int(self._pending_dig_cut_corridor_id) >= 0
            and self._pending_dig_cut_cycle_id == int(self._cycle_index)
        ):
            corridor = self._coverage_corridor_by_id(int(self._pending_dig_cut_corridor_id))
            if corridor is not None:
                return int(corridor.cell_id)
        corridor = self._coverage_active_corridor()
        if corridor is not None:
            return int(corridor.cell_id)
        env_state = self._env_state(obs)
        if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
            value = float(env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX])
            if np.isfinite(value):
                return int(max(0, min(5, round(value))))
        return 0

    def _build_dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray:
        self._dig_cut_fallback_reason = ""
        planner = self._dig_cut_token_planner()
        if (
            self._pending_dig_cut_tokens is not None
            and self._pending_dig_cut_cycle_id == int(self._cycle_index)
        ):
            plan = planner.plan_pending_return_target(
                tokens=self._pending_dig_cut_tokens,
                raw_fields=self._pending_dig_cut_raw_fields,
            )
            self._coverage_active_corridor_id = int(self._pending_dig_cut_corridor_id)
            self._coverage_last_selected_corridor_id = int(
                self._pending_dig_cut_corridor_id
            )
            self._coverage_current_payload_gain_kg = 0.0
            self._coverage_cycle_start_deposit_kg = self._deposited_mass(obs)
            self._coverage_active_state_exemplar_ids = list(
                self._pending_dig_state_exemplar_ids
            )
            self._coverage_active_state_exemplar_distance = float(
                self._pending_dig_state_exemplar_distance
            )
            self._coverage_active_state_exemplar_profile_token = (
                None
                if self._pending_dig_depth_profile_tokens is None
                else self._pending_dig_depth_profile_tokens.astype(np.float32).copy()
            )
            return self._apply_dig_cut_token_plan(plan)
        if self.dig_cut_planner_mode == "conservative_pose":
            return self._apply_dig_cut_token_plan(
                planner.plan_conservative_pose(self._bucket_dig_area_pose(obs))
            )
        if self.dig_cut_planner_mode == "operator_prior":
            try:
                return self._apply_dig_cut_token_plan(
                    planner.plan_operator_prior(self._bucket_dig_area_pose(obs))
                )
            except Exception as exc:
                if self.dig_cut_planner_fallback_mode != "conservative_pose":
                    raise
                return self._apply_dig_cut_token_plan(
                    planner.plan_fallback_conservative_pose(
                        self._bucket_dig_area_pose(obs),
                        fallback_reason=str(exc),
                    )
                )
        if self.dig_cut_planner_mode == "operator_prior_coverage":
            try:
                _token, raw_fields, source, fallback_reason = (
                    self._build_operator_prior_coverage_dig_cut_tokens(obs)
                )
                return self._apply_dig_cut_token_plan(
                    planner.plan_from_raw_fields(
                        raw_fields,
                        source=source,
                        fallback_reason=fallback_reason,
                    )
                )
            except Exception as exc:
                if self.dig_cut_planner_fallback_mode != "conservative_pose":
                    raise
                return self._apply_dig_cut_token_plan(
                    planner.plan_fallback_conservative_pose(
                        self._bucket_dig_area_pose(obs),
                        fallback_reason=str(exc),
                    )
                )
        if self.dig_cut_planner_mode == "operator_prior_sweep_belief":
            try:
                _token, raw_fields, source, fallback_reason = (
                    self._build_operator_prior_coverage_dig_cut_tokens(obs)
                )
                return self._apply_dig_cut_token_plan(
                    planner.plan_from_raw_fields(
                        raw_fields,
                        source=source,
                        fallback_reason=fallback_reason,
                    )
                )
            except Exception as exc:
                if self.dig_cut_planner_fallback_mode != "conservative_pose":
                    raise
                return self._apply_dig_cut_token_plan(
                    planner.plan_fallback_conservative_pose(
                        self._bucket_dig_area_pose(obs),
                        fallback_reason=str(exc),
                    )
                )
        raise ValueError(f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}.")

    def _apply_dig_cut_token_plan(self, plan: DigCutTokenPlan) -> np.ndarray:
        self._dig_cut_token_source = str(plan.source)
        self._dig_cut_fallback_reason = str(plan.fallback_reason)
        self._dig_cut_token_in_prior_p10_p90 = bool(plan.in_prior_p10_p90)
        return plan.token.copy()

    def _build_next_dig_cut_plan_for_return(
        self,
        obs: dict,
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        planner = self._return_target_token_planner()
        if self.dig_cut_planner_mode == "conservative_pose":
            return self._unpack_return_target_token_plan(
                planner.plan_conservative_pose(self._bucket_dig_area_pose(obs))
            )
        if self.dig_cut_planner_mode == "operator_prior":
            return self._unpack_return_target_token_plan(
                planner.plan_operator_prior(self._bucket_dig_area_pose(obs))
            )
        if self.dig_cut_planner_mode in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            corridor = self._select_next_coverage_corridor(obs)
            self._coverage_active_corridor_id = int(corridor.corridor_id)
            raw_fields = self._coverage_raw_fields(
                corridor,
                obs=obs,
                update_state=True,
            )
            return self._unpack_return_target_token_plan(
                planner.plan_from_coverage_raw_fields(
                    raw_fields,
                    dig_cut_planner_mode=self.dig_cut_planner_mode,
                    corridor_id=int(corridor.corridor_id),
                )
            )
        raise ValueError(f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}.")

    @staticmethod
    def _unpack_return_target_token_plan(
        plan: ReturnTargetTokenPlan,
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        return (
            plan.token.copy(),
            dict(plan.raw_fields),
            str(plan.source),
            str(plan.fallback_reason),
            int(plan.corridor_id),
        )

    def _build_return_start_envelope_tokens_for_obs(
        self,
        obs: dict,
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        plan = self._return_start_envelope_token_planner().plan(
            raw_fields=raw_fields,
            env_state=self._env_state(obs),
            qpos=np.asarray(
                obs.get("qpos", np.zeros(self.action_dim)),
                dtype=np.float32,
            ).reshape(-1),
            qvel=np.asarray(
                obs.get("qvel", np.zeros(self.action_dim)),
                dtype=np.float32,
            ).reshape(-1),
            cell_id=self._return_start_envelope_cell_id(corridor_id),
        )
        return self._apply_return_start_envelope_token_plan(plan)

    def _apply_return_start_envelope_token_plan(
        self,
        plan: ReturnStartEnvelopeTokenPlan,
    ) -> np.ndarray:
        self._return_start_envelope_token_source = str(plan.source)
        self._return_start_envelope_use_prior_spatial_bounds = bool(
            plan.use_prior_spatial_bounds
        )
        self._return_start_envelope_use_prior_qpos_bounds = bool(
            plan.use_prior_qpos_bounds
        )
        return plan.token.copy()

    def _maybe_condition_return_start_envelope_qpos_from_relocate(
        self,
        token: np.ndarray,
        *,
        raw_fields: dict[str, float | int],
        source: str,
    ) -> np.ndarray:
        plan = self._return_start_envelope_token_planner().condition_token(
            token,
            raw_fields=raw_fields,
            source=source,
            use_prior_spatial_bounds=self._return_start_envelope_use_prior_spatial_bounds,
            use_prior_qpos_bounds=self._return_start_envelope_use_prior_qpos_bounds,
        )
        return self._apply_return_start_envelope_token_plan(plan)

    def _return_start_envelope_prior_token(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, str]:
        return self._return_start_envelope_token_planner().prior_token(
            cell_id=self._return_start_envelope_cell_id(corridor_id)
        )

    def _return_start_envelope_prior_mapping(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[dict[str, object] | None, str]:
        return self._return_start_envelope_token_planner().prior_mapping(
            cell_id=self._return_start_envelope_cell_id(corridor_id)
        )

    def _return_start_envelope_prior_bounds(
        self,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        return self._return_start_envelope_token_planner().prior_bounds(
            cell_id=self._return_start_envelope_cell_id(corridor_id)
        )

    def _return_start_envelope_cell_id(self, corridor_id: int | None) -> int | None:
        if corridor_id is None:
            return None
        try:
            corridor = self._coverage_corridor_by_id(int(corridor_id))
        except Exception:
            corridor = None
        if corridor is not None:
            return int(corridor.cell_id)
        if int(corridor_id) >= 0:
            return int(corridor_id)
        return None

    @staticmethod
    def _return_start_envelope_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        return ReturnStartEnvelopeTokenPlanner.token_from_prior_mapping(mapping)

    @staticmethod
    def _normalize_plane_depth_mode(value: object) -> str:
        mode = str(value or "range").strip().lower().replace("-", "_")
        aliases = {
            "legacy": "range",
            "p05_p95": "range",
            "median_floor": "p50_floor",
            "target_floor": "p50_floor",
            "median_band": "target_band",
        }
        mode = aliases.get(mode, mode)
        if mode not in {"range", "p50_floor", "target_band"}:
            raise ValueError(
                "return_to_dig_start_envelope_plane_depth_mode must be one of "
                "'range', 'p50_floor', or 'target_band'"
            )
        return mode

    @staticmethod
    def _normalize_failed_dig_replan_skill(value: object) -> str:
        skill = str(value or "dig").strip().lower().replace("-", "_")
        aliases = {
            "fail": "stop",
            "fail_fast": "stop",
            "terminal": "stop",
            "terminal_stop": "stop",
            "same": "dig",
            "same_dig": "dig",
            "new_dig": "dig",
        }
        skill = aliases.get(skill, skill)
        if skill not in {"dig", "stop"}:
            raise ValueError(
                "dig_failed_replan_next_skill must be 'dig' or 'stop'."
            )
        return skill

    def _raw_fields_from_live_pose(self, obs: dict) -> dict[str, float | int]:
        return self._dig_cut_token_planner().raw_fields_from_live_pose(
            self._bucket_dig_area_pose(obs)
        )

    def _build_operator_prior_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        plan = self._dig_cut_token_planner().plan_operator_prior(
            self._bucket_dig_area_pose(obs)
        )
        return (
            plan.token.copy(),
            dict(plan.raw_fields),
            str(plan.source),
            str(plan.fallback_reason),
        )

    def _build_operator_prior_coverage_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        corridor = self._select_next_coverage_corridor(obs)
        self._coverage_current_payload_gain_kg = 0.0
        self._coverage_cycle_start_deposit_kg = self._deposited_mass(obs)
        raw_fields = self._coverage_raw_fields(
            corridor,
            obs=obs,
            update_state=True,
        )
        plan = self._dig_cut_token_planner().plan_from_raw_fields(
            raw_fields,
            source="operator_prior_coverage",
        )
        return plan.token.copy(), dict(plan.raw_fields), plan.source, plan.fallback_reason

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
            entry_stats = dict(cell.get("entry_stats", {}) or {})
            exit_stats = dict(cell.get("exit_stats", {}) or {})
            depth_stats = dict(cell.get("cut_depth_peak_m_stats", {}) or {})
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
                    entry_x_p05_m=self._coverage_stat_float(
                        entry_stats, "x_m", "p05", float(entry_x)
                    ),
                    entry_x_p50_m=self._coverage_stat_float(
                        entry_stats, "x_m", "p50", float(entry_x)
                    ),
                    entry_x_p95_m=self._coverage_stat_float(
                        entry_stats, "x_m", "p95", float(entry_x)
                    ),
                    entry_z_p05_m=self._coverage_stat_float(
                        entry_stats, "z_m", "p05", float(entry_z)
                    ),
                    entry_z_p50_m=self._coverage_stat_float(
                        entry_stats, "z_m", "p50", float(entry_z)
                    ),
                    entry_z_p95_m=self._coverage_stat_float(
                        entry_stats, "z_m", "p95", float(entry_z)
                    ),
                    entry_radial_p75_m=self._coverage_stat_float(
                        entry_stats, "radial_error_m", "p75", float("nan")
                    ),
                    entry_radial_p95_m=self._coverage_stat_float(
                        entry_stats, "radial_error_m", "p95", float("nan")
                    ),
                    exit_x_p05_m=self._coverage_stat_float(
                        exit_stats, "x_m", "p05", float(exit_x)
                    ),
                    exit_x_p50_m=self._coverage_stat_float(
                        exit_stats, "x_m", "p50", float(exit_x)
                    ),
                    exit_x_p95_m=self._coverage_stat_float(
                        exit_stats, "x_m", "p95", float(exit_x)
                    ),
                    exit_z_p05_m=self._coverage_stat_float(
                        exit_stats, "z_m", "p05", float(exit_z)
                    ),
                    exit_z_p50_m=self._coverage_stat_float(
                        exit_stats, "z_m", "p50", float(exit_z)
                    ),
                    exit_z_p95_m=self._coverage_stat_float(
                        exit_stats, "z_m", "p95", float(exit_z)
                    ),
                    exit_radial_p75_m=self._coverage_stat_float(
                        exit_stats, "radial_error_m", "p75", float("nan")
                    ),
                    exit_radial_p95_m=self._coverage_stat_float(
                        exit_stats, "radial_error_m", "p95", float("nan")
                    ),
                    cut_depth_peak_p05_m=self._coverage_cell_float(
                        depth_stats,
                        "p05",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p10"),
                    ),
                    cut_depth_peak_p50_m=self._coverage_cell_float(
                        depth_stats,
                        "p50",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p50"),
                    ),
                    cut_depth_peak_p95_m=self._coverage_cell_float(
                        depth_stats,
                        "p95",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p90"),
                    ),
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

    @classmethod
    def _coverage_stat_float(
        cls,
        mapping: dict[str, object],
        section: str,
        name: str,
        default: float,
    ) -> float:
        section_mapping = mapping.get(section, {})
        if not isinstance(section_mapping, dict):
            return float(default)
        return cls._coverage_cell_float(section_mapping, name, default)

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
        if self._coverage_all_depleted():
            self._maybe_reopen_coverage_pass(obs, reason="select_all_depleted")
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
            state_exemplar_distance = self._coverage_state_exemplar_distance(
                corridor,
                obs,
            )
            score = (
                self._coverage_score(corridor, remaining_depth, obs=obs)
                + first_dig_bonus
            )
            if first_dig_gated_out or rare_first_dig_gated_out:
                score = -1.0e12 + float(score)
            corridor.score = float(score)
            corridor.last_remaining_depth_m = float(remaining_depth)
            recent_row_reference = self._coverage_recent_row_reference_corridor()
            recent_row_reference_id = (
                -1
                if recent_row_reference is None
                else int(recent_row_reference.corridor_id)
            )
            recent_row_reference_cell_id = (
                -1
                if recent_row_reference is None
                else int(self._coverage_cell_id(recent_row_reference))
            )
            recent_row_reference_row_id = (
                -1
                if recent_row_reference is None
                else int(self._coverage_corridor_row_id(recent_row_reference))
            )
            row_id = int(self._coverage_corridor_row_id(corridor))
            same_recent_row = bool(
                recent_row_reference is not None
                and int(recent_row_reference.corridor_id)
                != int(corridor.corridor_id)
                and row_id == recent_row_reference_row_id
            )
            self._coverage_candidate_scores.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(self._coverage_cell_id(corridor)),
                    "row_id": int(row_id),
                    "score": float(score),
                    "attempts": int(corridor.attempts),
                    "attempt_limit": int(self._coverage_corridor_attempt_limit(corridor)),
                    "depleted": int(corridor.depleted),
                    "source_count": int(corridor.source_count),
                    "source_fraction": float(corridor.source_fraction),
                    "cell_confidence": float(self._coverage_cell_confidence(corridor)),
                    "state_exemplar_distance": float(state_exemplar_distance),
                    "state_exemplar_id": str(
                        self._coverage_state_exemplar_id(corridor, obs)
                    ),
                    "belief_coverage": float(corridor.belief_coverage),
                    "remaining_depth_m": float(remaining_depth),
                    "first_dig_bonus": float(first_dig_bonus),
                    "recent_row_penalty": float(
                        self._coverage_recent_row_penalty(corridor)
                    ),
                    "recent_row_reference_corridor_id": int(
                        recent_row_reference_id
                    ),
                    "recent_row_reference_cell_id": int(
                        recent_row_reference_cell_id
                    ),
                    "recent_row_reference_row_id": int(
                        recent_row_reference_row_id
                    ),
                    "same_recent_row": int(same_recent_row),
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
        self._record_coverage_decision_event(
            "select_corridor",
            obs=obs,
            corridor=best,
            extra={
                "selected_score": float(best_score),
                "candidate_scores": list(self._coverage_candidate_scores),
                "first_dig_gate_available": int(first_dig_gate_available),
            },
        )
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(obs, reason="select_all_depleted"):
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
        *,
        obs: dict | None = None,
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
        state_exemplar_penalty = 0.0
        if obs is not None and self.coverage_state_exemplars_enabled:
            distance = self._coverage_state_exemplar_distance(corridor, obs)
            if np.isfinite(distance):
                state_exemplar_penalty = (
                    self.coverage_state_exemplar_score_weight * float(distance)
                )
        return (
            2.0 * remaining_ratio
            + productivity
            + self.coverage_cell_confidence_weight * cell_confidence
            + unattempted_bonus
            - repeat_penalty
            - row_penalty
            - attempt_penalty
            - state_exemplar_penalty
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
        previous = self._coverage_recent_row_reference_corridor()
        if previous is None:
            return 0.0
        if int(previous.corridor_id) == int(corridor.corridor_id):
            return 0.0
        same_row = bool(
            self._coverage_corridor_row_id(previous)
            == self._coverage_corridor_row_id(corridor)
        )
        return float(self.coverage_recent_row_selection_penalty if same_row else 0.0)

    def _coverage_recent_row_reference_corridor(
        self,
    ) -> CoverageCorridorState | None:
        previous = self._coverage_corridor_by_id(self._coverage_last_selected_corridor_id)
        if previous is not None:
            return previous
        return self._coverage_active_corridor()

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
        raw_fields = self._coverage_raw_fields(corridor, obs=obs)
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
        self,
        corridor: CoverageCorridorState,
        *,
        obs: dict | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        if obs is not None:
            state_plan = self._coverage_state_conditioned_plan(
                corridor,
                obs,
                update_state=update_state,
            )
            if state_plan is not None:
                return dict(state_plan["raw_fields"])
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
            "operator_effective_deposit_delta_kg": float(
                self._clamp_to_prior(
                    fields,
                    "effective_deposit_delta_kg",
                    float(corridor.effective_deposit_delta_kg)
                    if np.isfinite(corridor.effective_deposit_delta_kg)
                    else self._prior_percentile(
                        fields,
                        "effective_deposit_delta_kg",
                        "p50",
                    ),
                )
            ),
            "operator_cut_valid": 1,
        }

    def _load_coverage_state_exemplars(self) -> dict[int, list[dict[str, Any]]]:
        if not self.coverage_state_exemplars_enabled:
            return {}
        raw_path = str(self.coverage_state_exemplar_path).strip()
        if not raw_path:
            raise ValueError(
                "coverage.state_conditioned_exemplars.enabled=true requires a path."
            )
        path = Path(raw_path).expanduser()
        if not path.is_absolute() and not path.exists():
            prior_path = Path(self.dig_cut_prior_path).expanduser()
            if not prior_path.is_absolute():
                prior_path = Path.cwd() / prior_path
            path = prior_path.parent / path
        if not path.is_absolute():
            path = Path.cwd() / path
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_exemplars = payload.get("exemplars", [])
        if not isinstance(raw_exemplars, list):
            raise ValueError(
                f"coverage state exemplar file {path} must contain an exemplars list."
            )
        exemplars_by_cell: dict[int, list[dict[str, Any]]] = {
            cell_id: [] for cell_id in range(6)
        }
        for item in raw_exemplars:
            if not isinstance(item, dict):
                continue
            try:
                cell_id = int(item.get("cell_id", -1))
            except (TypeError, ValueError):
                continue
            if cell_id < 0 or cell_id > 5:
                continue
            raw_fields = item.get("raw_fields", {})
            if not isinstance(raw_fields, dict):
                continue
            exemplar = dict(item)
            exemplar["raw_fields"] = dict(raw_fields)
            exemplar["exemplar_id"] = str(
                exemplar.get("exemplar_id", f"cell_{cell_id}_{len(exemplars_by_cell[cell_id])}")
            )
            exemplars_by_cell[cell_id].append(exemplar)
        if not any(exemplars_by_cell.values()):
            raise ValueError(f"coverage state exemplar file {path} has no usable rows.")
        return exemplars_by_cell

    def _coverage_state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
        *,
        update_state: bool,
    ) -> dict[str, object] | None:
        if not self.coverage_state_exemplars_enabled:
            return None
        cell_id = self._coverage_cell_id(corridor)
        exemplars = list(self.coverage_state_exemplars_by_cell.get(cell_id, []))
        if not exemplars:
            return None
        removed_grid = self._coverage_removed_depth_grid(obs)
        if removed_grid is None:
            return None
        scored: list[tuple[float, dict[str, Any]]] = []
        for exemplar in exemplars:
            distance = self._coverage_state_exemplar_distance_for_grid(
                removed_grid,
                exemplar,
                cell_id=cell_id,
            )
            if np.isfinite(distance):
                scored.append((float(distance), exemplar))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0])
        if self.coverage_state_exemplar_skip_rejected:
            filtered = [
                item
                for item in scored
                if str(item[1].get("exemplar_id", ""))
                not in self._coverage_rejected_state_exemplar_ids
            ]
            if filtered:
                scored = filtered
        selected = scored[: self.coverage_state_exemplar_k]
        raw_fields = self._weighted_state_exemplar_raw_fields(selected)
        profile_token = self._weighted_state_exemplar_profile_token(selected)
        exemplar_ids = [str(exemplar.get("exemplar_id", "")) for _, exemplar in selected]
        best_distance = float(selected[0][0])
        if update_state:
            self._coverage_active_state_exemplar_ids = exemplar_ids
            self._coverage_active_state_exemplar_distance = best_distance
            self._coverage_active_state_exemplar_profile_token = (
                None
                if profile_token is None
                else profile_token.astype(np.float32).copy()
            )
            corridor.state_exemplar_id = ",".join(exemplar_ids)
            corridor.state_exemplar_distance = best_distance
        return {
            "raw_fields": raw_fields,
            "profile_token": profile_token,
            "exemplar_ids": exemplar_ids,
            "distance": best_distance,
        }

    def _coverage_state_exemplar_distance(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        state_plan = self._coverage_state_conditioned_plan(
            corridor,
            obs,
            update_state=False,
        )
        if state_plan is None:
            return float("nan")
        return float(state_plan["distance"])

    def _coverage_state_exemplar_id(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> str:
        state_plan = self._coverage_state_conditioned_plan(
            corridor,
            obs,
            update_state=False,
        )
        if state_plan is None:
            return ""
        exemplar_ids = state_plan.get("exemplar_ids", [])
        if not exemplar_ids:
            return ""
        return str(exemplar_ids[0])

    def _coverage_removed_depth_grid(self, obs: dict) -> np.ndarray | None:
        env_state = self._env_state(obs)
        start = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        end = start + 6
        if len(env_state) < end:
            return None
        grid = np.asarray(env_state[start:end], dtype=np.float32).reshape(6)
        if not np.all(np.isfinite(grid)):
            return None
        return np.maximum(grid, 0.0).astype(np.float32)

    def _coverage_state_exemplar_distance_for_grid(
        self,
        removed_grid: np.ndarray,
        exemplar: dict[str, Any],
        *,
        cell_id: int,
    ) -> float:
        exemplar_grid = np.asarray(
            exemplar.get("start_removed_depth_grid_m", []),
            dtype=np.float32,
        ).reshape(-1)
        if exemplar_grid.size < 6 or not np.all(np.isfinite(exemplar_grid[:6])):
            return float("nan")
        scale = float(self.coverage_state_exemplar_removed_depth_scale_m)
        diff = (
            np.asarray(removed_grid, dtype=np.float32).reshape(6)
            - exemplar_grid[:6].astype(np.float32)
        ) / scale
        cell_index = int(max(0, min(5, cell_id)))
        diff[cell_index] *= float(self.coverage_state_exemplar_target_cell_weight)
        return float(np.sqrt(np.mean(np.square(diff.astype(np.float32)))))

    def _state_exemplar_weights(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray:
        distances = np.asarray([distance for distance, _ in selected], dtype=np.float32)
        if distances.size == 0:
            return np.zeros(0, dtype=np.float32)
        if not np.all(np.isfinite(distances)):
            return np.full(distances.shape, 1.0 / float(distances.size), dtype=np.float32)
        shifted = distances - float(np.min(distances))
        weights = np.exp(-shifted / float(self.coverage_state_exemplar_temperature))
        weight_sum = float(np.sum(weights))
        if not np.isfinite(weight_sum) or weight_sum <= 1.0e-8:
            return np.full(distances.shape, 1.0 / float(distances.size), dtype=np.float32)
        return (weights / weight_sum).astype(np.float32)

    def _weighted_state_exemplar_raw_fields(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> dict[str, float | int]:
        weights = self._state_exemplar_weights(selected)

        def weighted(name: str, default: float = 0.0) -> float:
            values: list[float] = []
            for _, exemplar in selected:
                raw_fields = dict(exemplar.get("raw_fields", {}) or {})
                try:
                    value = float(raw_fields.get(name, default))
                except (TypeError, ValueError):
                    value = float(default)
                values.append(value if np.isfinite(value) else float(default))
            return float(np.dot(weights, np.asarray(values, dtype=np.float32)))

        entry_x = weighted("operator_entry_x_m")
        entry_y = weighted("operator_entry_y_m")
        entry_z = weighted("operator_entry_z_m")
        exit_x = weighted("operator_exit_x_m")
        exit_y = weighted("operator_exit_y_m", default=entry_y)
        exit_z = weighted("operator_exit_z_m")
        delta_x = exit_x - entry_x
        delta_y = exit_y - entry_y
        delta_z = exit_z - entry_z
        length = float(np.sqrt(delta_x * delta_x + delta_y * delta_y + delta_z * delta_z))
        if length <= 1.0e-6:
            dir_x = weighted("operator_cut_direction_x", default=-1.0)
            dir_y = weighted("operator_cut_direction_y", default=0.0)
            dir_z = weighted("operator_cut_direction_z", default=0.0)
            length = weighted("operator_cut_length_m", default=1.0)
        else:
            dir_x = delta_x / length
            dir_y = delta_y / length
            dir_z = delta_z / length
        return {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": float(entry_y),
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": float(exit_y),
            "operator_exit_z_m": float(exit_z),
            "operator_cut_direction_x": float(dir_x),
            "operator_cut_direction_y": float(dir_y),
            "operator_cut_direction_z": float(dir_z),
            "operator_cut_length_m": float(length),
            "operator_cut_depth_peak_m": weighted("operator_cut_depth_peak_m"),
            "operator_cut_payload_gain_kg": weighted("operator_cut_payload_gain_kg"),
            "operator_effective_deposit_delta_kg": weighted(
                "operator_effective_deposit_delta_kg",
                default=weighted("operator_cut_payload_gain_kg"),
            ),
            "operator_cut_valid": 1,
        }

    def _weighted_state_exemplar_profile_token(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray | None:
        weights = self._state_exemplar_weights(selected)
        tokens: list[np.ndarray] = []
        for _, exemplar in selected:
            if "dig_depth_profile_token" not in exemplar:
                return None
            token = np.asarray(
                exemplar.get("dig_depth_profile_token", []),
                dtype=np.float32,
            ).reshape(-1)
            if token.shape[0] != DIG_DEPTH_PROFILE_TOKEN_DIM:
                return None
            if not np.all(np.isfinite(token)):
                return None
            tokens.append(token)
        if not tokens:
            return None
        stacked = np.stack(tokens, axis=0)
        merged = np.sum(stacked * weights.reshape(-1, 1), axis=0)
        merged[-1] = 1.0
        return merged.astype(np.float32)

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

    def _coverage_corridor_row_id(self, corridor: CoverageCorridorState) -> int:
        return int(self._coverage_cell_id(corridor) // 2)

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
        remaining_depth_available = bool(
            self.coverage_use_env_removed_depth
            and np.isfinite(remaining_depth)
            and float(remaining_depth) >= self.coverage_min_remaining_depth_m
        )
        if (
            corridor.attempts >= self._coverage_corridor_attempt_limit(corridor)
            and not remaining_depth_available
        ):
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

        self._record_coverage_decision_event(
            "complete_dump",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "final_reason": str(corridor.last_reason),
                "payload_gain_kg": float(payload_gain),
                "effective_deposit_delta_kg": float(effective_deposit),
                "remaining_depth_m": float(remaining_depth),
                "low_productivity": int(low_productivity),
                "completed_dump_count": int(self._coverage_completed_dump_count),
            },
        )
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(obs, reason="complete_all_depleted"):
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
        self._coverage_rejected_state_exemplar_ids.update(
            exemplar_id
            for exemplar_id in self._coverage_active_state_exemplar_ids
            if exemplar_id
        )
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
        if str(reason) == "align_entry_gap_timeout":
            corridor.last_payload_gain_kg = float(payload_gain)
            corridor.last_effective_deposit_delta_kg = float(effective_deposit)
            corridor.last_remaining_depth_m = float(remaining_depth)
            corridor.last_reason = str(reason)
            self._coverage_last_payload_gain_kg = float(payload_gain)
            self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
            self._record_coverage_decision_event(
                "reject_corridor",
                obs=obs,
                corridor=corridor,
                extra={
                    "reason": str(reason),
                    "payload_gain_kg": float(payload_gain),
                    "effective_deposit_delta_kg": float(effective_deposit),
                    "remaining_depth_m": float(remaining_depth),
                    "counted_attempt": 0,
                },
            )
            return
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
        self._record_coverage_decision_event(
            "reject_corridor",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "payload_gain_kg": float(payload_gain),
                "effective_deposit_delta_kg": float(effective_deposit),
                "remaining_depth_m": float(remaining_depth),
                "counted_attempt": 1,
            },
        )
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(obs, reason="reject_all_depleted"):
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

    def _record_coverage_decision_event(
        self,
        event: str,
        *,
        obs: dict | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": str(event),
            "cycle_index": int(self._cycle_index),
            "skill_name": str(self._skill_name),
            "active_corridor_id": int(self._coverage_active_corridor_id),
            "last_selected_corridor_id": int(
                self._coverage_last_selected_corridor_id
            ),
            "last_selected_cell_id": int(
                self._coverage_corridor_cell_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            "last_selected_row_id": int(
                self._coverage_corridor_row_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            "depleted_count": int(self._coverage_depleted_count()),
            "pass_index": int(self._coverage_pass_index),
            "global_low_productivity_streak": int(
                self._coverage_global_low_productivity_streak
            ),
            "terminal_stop_requested": int(self._coverage_terminal_stop_requested),
            "terminal_stop_reason": str(self._coverage_terminal_stop_reason),
        }
        if corridor is not None:
            payload["corridor"] = self._coverage_corridor_to_debug(corridor)
        if obs is not None:
            env_state = self._env_state(obs)
            payload["bucket"] = {
                "mass_kg": float(self._mass_in_bucket(obs)),
                "deposited_mass_kg": float(self._deposited_mass(obs)),
                "dig_area_x_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
                ),
                "dig_area_y_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
                ),
                "dig_area_z_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
                ),
                "long_norm": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
                ),
                "short_norm": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
                ),
                "plane_depth_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
                ),
                "local_depth_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
                ),
            }
        payload.update(dict(extra or {}))
        self._coverage_decision_trace.append(payload)

    @staticmethod
    def _env_state_value(env_state: np.ndarray, index: int) -> float:
        if len(env_state) <= int(index):
            return float("nan")
        return float(env_state[int(index)])

    def _coverage_all_depleted(self) -> bool:
        return bool(
            self._coverage_corridors
            and all(corridor.depleted for corridor in self._coverage_corridors)
        )

    def _maybe_reopen_coverage_pass(self, obs: dict, *, reason: str) -> bool:
        if not self.coverage_multi_pass_enabled:
            return False
        if self._coverage_terminal_stop_requested:
            return False
        if not self.coverage_use_env_removed_depth:
            return False
        if not self._coverage_all_depleted():
            return False
        if (
            int(self._coverage_pass_index) + 1
            >= int(self.coverage_multi_pass_max_passes)
        ):
            return False

        threshold = float(self.coverage_multi_pass_min_remaining_depth_m)
        reopened: list[dict[str, float | int | str]] = []
        for corridor in self._coverage_corridors:
            remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
            if not (
                np.isfinite(remaining_depth)
                and float(remaining_depth) >= threshold
            ):
                corridor.last_remaining_depth_m = float(remaining_depth)
                continue
            reopened.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(self._coverage_cell_id(corridor)),
                    "previous_attempts": int(corridor.attempts),
                    "previous_low_productivity_streak": int(
                        corridor.low_productivity_streak
                    ),
                    "previous_reason": str(corridor.last_reason),
                    "remaining_depth_m": float(remaining_depth),
                }
            )
            corridor.depleted = False
            corridor.attempts = 0
            corridor.low_productivity_streak = 0
            corridor.last_remaining_depth_m = float(remaining_depth)
            corridor.last_reason = f"multi_pass_reopened:{reason}"

        if not reopened:
            return False

        self._coverage_pass_index += 1
        self._coverage_active_corridor_id = -1
        self._coverage_global_low_productivity_streak = 0
        self._coverage_rejected_state_exemplar_ids.clear()
        self._record_coverage_decision_event(
            "reopen_coverage_pass",
            obs=obs,
            extra={
                "reason": str(reason),
                "pass_index": int(self._coverage_pass_index),
                "max_passes": int(self.coverage_multi_pass_max_passes),
                "min_remaining_depth_m": float(threshold),
                "reopened_corridors": reopened,
            },
        )
        return True

    def _request_coverage_terminal_stop(
        self,
        reason: str,
        *,
        replace: bool = False,
    ) -> None:
        if self._coverage_terminal_stop_requested and not replace:
            return
        self._coverage_terminal_stop_requested = True
        self._coverage_terminal_stop_reason = str(reason)
        self._record_coverage_decision_event(
            "terminal_stop",
            corridor=self._coverage_active_corridor(),
            extra={"reason": str(reason)},
        )

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

    def _coverage_active_cell_id(self) -> int:
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return -1
        return int(self._coverage_cell_id(corridor))

    def _coverage_corridor_cell_id_by_id(self, corridor_id: int) -> int:
        corridor = self._coverage_corridor_by_id(corridor_id)
        if corridor is None:
            return -1
        return int(self._coverage_cell_id(corridor))

    def _coverage_corridor_row_id_by_id(self, corridor_id: int) -> int:
        corridor = self._coverage_corridor_by_id(corridor_id)
        if corridor is None:
            return -1
        return int(self._coverage_corridor_row_id(corridor))

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
            "entry_x_p05_m": float(corridor.entry_x_p05_m),
            "entry_x_p50_m": float(corridor.entry_x_p50_m),
            "entry_x_p95_m": float(corridor.entry_x_p95_m),
            "entry_z_p05_m": float(corridor.entry_z_p05_m),
            "entry_z_p50_m": float(corridor.entry_z_p50_m),
            "entry_z_p95_m": float(corridor.entry_z_p95_m),
            "entry_radial_p75_m": float(corridor.entry_radial_p75_m),
            "entry_radial_p95_m": float(corridor.entry_radial_p95_m),
            "exit_x_p05_m": float(corridor.exit_x_p05_m),
            "exit_x_p50_m": float(corridor.exit_x_p50_m),
            "exit_x_p95_m": float(corridor.exit_x_p95_m),
            "exit_z_p05_m": float(corridor.exit_z_p05_m),
            "exit_z_p50_m": float(corridor.exit_z_p50_m),
            "exit_z_p95_m": float(corridor.exit_z_p95_m),
            "exit_radial_p75_m": float(corridor.exit_radial_p75_m),
            "exit_radial_p95_m": float(corridor.exit_radial_p95_m),
            "cut_depth_peak_p05_m": float(corridor.cut_depth_peak_p05_m),
            "cut_depth_peak_p50_m": float(corridor.cut_depth_peak_p50_m),
            "cut_depth_peak_p95_m": float(corridor.cut_depth_peak_p95_m),
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
            "state_exemplar_id": str(corridor.state_exemplar_id),
            "state_exemplar_distance": float(corridor.state_exemplar_distance),
        }

    def _clear_dig_cut_plan(self) -> None:
        self._dig_cut_planned_cycle_id = -1
        self._dig_cut_tokens = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        self._dig_depth_profile_tokens = np.zeros(
            DIG_DEPTH_PROFILE_TOKEN_DIM,
            dtype=np.float32,
        )
        self._dig_cut_token_source = "none"
        self._dig_cut_fallback_reason = ""
        self._dig_cut_token_in_prior_p10_p90 = False
        self._coverage_active_state_exemplar_ids = []
        self._coverage_active_state_exemplar_distance = float("nan")
        self._coverage_active_state_exemplar_profile_token = None

    def _invalidate_pending_dig_cut_plan(self) -> None:
        self._pending_dig_cut_cycle_id = -1
        self._pending_dig_cut_corridor_id = -1
        self._pending_dig_cut_raw_fields = None
        self._pending_dig_cut_tokens = None
        self._pending_dig_depth_profile_tokens = None
        self._pending_dig_state_exemplar_ids = []
        self._pending_dig_state_exemplar_distance = float("nan")

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
        supported_profile_sources = {"live_plan", "prior_profile"}
        if self.dig_depth_profile_source not in supported_profile_sources:
            raise ValueError(
                "Unsupported dig_depth_profile.source "
                f"{self.dig_depth_profile_source!r}; expected one of "
                f"{sorted(supported_profile_sources)}."
            )
        if self.dig_depth_profile_source == "prior_profile":
            if not self.dig_cut_prior_path:
                raise ValueError(
                    "dig_depth_profile.source='prior_profile' requires prior_path."
                )
            if "dig_depth_profile_cells" not in self.dig_cut_prior:
                raise ValueError(
                    "dig_depth_profile.source='prior_profile' requires "
                    "dig_depth_profile_cells in the dig cut prior."
                )
            if (
                self.dig_depth_profile_required
                and self.dig_depth_profile_allow_live_fallback
            ):
                raise ValueError(
                    "dig_depth_profile.required=true must set "
                    "allow_live_fallback=false so missing prior profiles fail fast."
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
        return DigCutTokenPlanner.prior_percentile(fields, field_name, percentile)

    def _clamp_to_prior(
        self, fields: dict[str, Any], field_name: str, value: float
    ) -> float:
        return self._dig_cut_token_planner().clamp_to_prior(fields, field_name, value)

    def _raw_fields_in_prior_range(self, raw_fields: dict[str, float | int]) -> bool:
        return self._dig_cut_token_planner().raw_fields_in_prior_range(raw_fields)

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
            geometry_available=self._bucket_dig_area_cell_in_bounds_mask(obs),
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

    def _bucket_dig_area_cell_in_bounds_mask(self, obs: dict) -> bool:
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
        return self._goal_token_provider().tokens_for_cycle(self._cycle_index)

    def _goal_sector_id(self, cycle_index: int) -> int:
        return self._goal_token_provider().sector_id(cycle_index)

    def _next_goal_sector_id(self) -> int:
        return self._goal_token_provider().next_sector_id(self._cycle_index)

    def _goal_token_provider(self) -> GoalTokenProvider:
        return GoalTokenProvider(
            goal_sequence=tuple(self.goal_sequence),
            scenario_id=self.goal_scenario_id,
            depth_norm=self.goal_depth_norm,
            dump_target_norm=self.goal_dump_target_norm,
        )

    def _dig_cut_token_planner(self) -> DigCutTokenPlanner:
        return DigCutTokenPlanner(prior=dict(self.dig_cut_prior or {}))

    def _dig_depth_profile_token_planner(self) -> DigDepthProfileTokenPlanner:
        return DigDepthProfileTokenPlanner(
            prior=dict(self.dig_cut_prior or {}),
            source=str(self.dig_depth_profile_source),
            required=bool(self.dig_depth_profile_required),
            allow_live_fallback=bool(self.dig_depth_profile_allow_live_fallback),
            allow_global_fallback=bool(self.dig_depth_profile_allow_global_fallback),
        )

    def _return_target_token_planner(self) -> ReturnTargetTokenPlanner:
        return ReturnTargetTokenPlanner(
            dig_cut_planner=self._dig_cut_token_planner(),
            source_prefix=str(self.return_target_token_source_prefix),
        )

    @staticmethod
    def _return_relocate_token_planner() -> ReturnRelocateTokenPlanner:
        return ReturnRelocateTokenPlanner()

    def _return_start_envelope_token_planner(self) -> ReturnStartEnvelopeTokenPlanner:
        return ReturnStartEnvelopeTokenPlanner(
            prior=dict(self.dig_cut_prior or {}),
            use_cell_prior=bool(self.return_start_envelope_use_cell_prior),
            min_source_count=int(self.return_start_envelope_min_source_count),
            min_source_fraction=float(self.return_start_envelope_min_source_fraction),
            conditioning=ReturnStartEnvelopeConditioningConfig(
                qpos_enabled=bool(
                    self.return_start_envelope_qpos_from_relocate_enabled
                ),
                qpos_coefficients=self.return_start_envelope_qpos_from_relocate_coefficients,
                qpos_min=self.return_start_envelope_qpos_from_relocate_min,
                qpos_max=self.return_start_envelope_qpos_from_relocate_max,
                qpos_use_prior_bounds=bool(
                    self.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds
                ),
                spatial_enabled=bool(
                    self.return_start_envelope_spatial_from_relocate_enabled
                ),
                spatial_coefficients=(
                    self.return_start_envelope_spatial_from_relocate_coefficients
                ),
                spatial_min=self.return_start_envelope_spatial_from_relocate_min,
                spatial_max=self.return_start_envelope_spatial_from_relocate_max,
                spatial_use_prior_bounds=bool(
                    self.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds
                ),
            ),
        )

    @staticmethod
    def _normalize_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | None,
    ) -> tuple[int, ...]:
        return GoalTokenProvider.normalize_goal_sequence(goal_sequence)

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
        dig_failed_replan_next_skill: str = "dig",
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
        return_to_dig_start_envelope_gate_enabled: bool = False,
        return_to_dig_start_envelope_spatial_tolerance: float = 0.10,
        return_to_dig_start_envelope_depth_tolerance_m: float = 0.08,
        return_to_dig_start_envelope_local_depth_tolerance_m: float = 0.005,
        return_to_dig_start_envelope_plane_depth_tolerance_m: float = 0.05,
        return_to_dig_start_envelope_plane_depth_mode: str = "range",
        return_to_dig_start_envelope_qpos_tolerance: float = 0.04,
        return_to_dig_start_envelope_require_contact: bool = True,
        return_to_dig_start_envelope_direct_handoff_enabled: bool = False,
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
            dig_failed_replan_next_skill=dig_failed_replan_next_skill,
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
            return_to_dig_start_envelope_gate_enabled=(
                return_to_dig_start_envelope_gate_enabled
            ),
            return_to_dig_start_envelope_spatial_tolerance=(
                return_to_dig_start_envelope_spatial_tolerance
            ),
            return_to_dig_start_envelope_depth_tolerance_m=(
                return_to_dig_start_envelope_depth_tolerance_m
            ),
            return_to_dig_start_envelope_local_depth_tolerance_m=(
                return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            return_to_dig_start_envelope_plane_depth_tolerance_m=(
                return_to_dig_start_envelope_plane_depth_tolerance_m
            ),
            return_to_dig_start_envelope_plane_depth_mode=(
                return_to_dig_start_envelope_plane_depth_mode
            ),
            return_to_dig_start_envelope_qpos_tolerance=(
                return_to_dig_start_envelope_qpos_tolerance
            ),
            return_to_dig_start_envelope_require_contact=(
                return_to_dig_start_envelope_require_contact
            ),
            return_to_dig_start_envelope_direct_handoff_enabled=(
                return_to_dig_start_envelope_direct_handoff_enabled
            ),
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
            if self._return_to_dig_direct_handoff_ready(obs):
                self._completed_transition_count += 1
                self._cycle_index += 1
                self._set_skill("dig", "return_to_dig_start_envelope_ready")
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
