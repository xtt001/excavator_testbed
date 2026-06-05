"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.contracts.primitive_profile import (
    CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
)
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
    derive_return_relocate_token,
)
from testbed.data.operator_first_v2_2 import (
    _build_dig_cut_token,
    build_live_dig_cut_tokens_from_pose,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
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
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX as ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX as ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX as ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
)
from testbed.data.schema import (
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX as ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.data.schema import (
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX as ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)
from testbed.data.v2_1 import build_goal_tokens
from testbed.planner.bootstrap import BootstrapConfig, BootstrapFacts, BootstrapService
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
from testbed.planner.dig_coverage import (
    CoverageCorridorState,
    DigCoverageMixin,
)
from testbed.planner.dig_depth_profile import (
    DigDepthProfileBuildRequest,
    DigDepthProfileConfig,
    DigDepthProfileInputFacts,
    DigDepthProfileMissingPriorError,
    DigDepthProfileService,
)
from testbed.planner.dig_lifecycle import (
    DigLifecycleConfig,
    DigLifecycleFacts,
    DigLifecycleGateService,
    FailedDigRecoveryFacts,
)
from testbed.planner.dig_start_alignment import (
    DigStartAlignmentConfig,
    DigStartAlignmentFacts,
    DigStartAlignmentService,
    PreDigAlignOutcome,
    pd_servo_action,
)
from testbed.planner.dump_lifecycle import (
    DumpLifecycleConfig,
    DumpLifecycleFacts,
    DumpLifecycleGateService,
)
from testbed.planner.policy_observation import (
    PolicyObservationAssembler,
    PolicyObservationTokens,
)
from testbed.planner.primitive_debug import (
    TRANSITION_POLICY_MODE_PRIMITIVE as TRANSITION_POLICY_MODE_PRIMITIVE,
)
from testbed.planner.primitive_debug import (
    TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY as TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
)
from testbed.planner.primitive_debug import (
    build_primitive_debug_state,
    build_primitive_planner_trace,
    build_primitive_rollout_summary,
)
from testbed.planner.primitive_decisions import primitive_boundary_facts_from_event
from testbed.planner.return_handoff import (
    ReturnToDigHandoffConfig,
    ReturnToDigHandoffContext,
    ReturnToDigHandoffDecision,
    ReturnToDigHandoffGateService,
)
from testbed.planner.return_start_envelope import (
    ReturnStartEnvelopeBuildRequest,
    ReturnStartEnvelopeConfig,
    build_return_start_envelope_for_plan,
    condition_return_start_envelope_from_relocate,
    return_start_envelope_token_from_prior_mapping,
)
from testbed.planner.return_start_envelope import (
    return_start_envelope_prior_bounds as resolve_return_start_envelope_prior_bounds,
)
from testbed.planner.return_start_envelope import (
    return_start_envelope_prior_mapping as resolve_return_start_envelope_prior_mapping,
)
from testbed.planner.return_start_envelope import (
    return_start_envelope_prior_token as resolve_return_start_envelope_prior_token,
)
from testbed.planner.return_target_plan import (
    ReturnTargetExemplarSnapshot,
    ReturnTargetPlanBuild,
    ReturnTargetPlanService,
    ReturnTargetPlanState,
)
from testbed.planner.snapshots import PlannerSnapshot, build_planner_snapshot
from testbed.policies.base import Policy, register_policy
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK

PRIMITIVE_SKILL_NAMES = ("dig", "carry", "dump", "return")
PRIMITIVE_SKILL_IDS = {name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES)}
PRIMITIVE_SKILL_NAMES_5P = ("dig", "carry", "approach_dump", "dump_release", "return")
PRIMITIVE_SKILL_IDS_5P = {
    name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES_5P)
}
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


@register_policy("primitive_planner_act")
class PrimitivePlannerACTPolicy(DigCoverageMixin, Policy):
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
        self.return_handoff_gate = ReturnToDigHandoffGateService()
        self.bootstrap_service = BootstrapService()
        self.dig_lifecycle_gate = DigLifecycleGateService()
        self.dig_start_alignment_service = DigStartAlignmentService()
        self.dump_lifecycle_gate = DumpLifecycleGateService()
        self.policy_observation_assembler = PolicyObservationAssembler()
        self.dig_depth_profile_service = DigDepthProfileService()
        self.return_target_plan_service = ReturnTargetPlanService()
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
        self.coverage_service = self._create_coverage_service()
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
        self._reset_coverage_service()
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
        return build_primitive_debug_state(self)

    def rollout_summary(self) -> dict[str, float | int | str | list[str]]:
        return build_primitive_rollout_summary(self)

    def planner_trace(self) -> dict[str, object]:
        return build_primitive_planner_trace(self)

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
            outcome = self._pre_dig_align_outcome(obs)
            if outcome.action == "surface_guard_handoff":
                self._pre_dig_align_surface_guard_count += 1
                self._pre_dig_align_hold_count = 0
                self._pre_dig_align_completed_count += 1
                self._set_skill("dig", outcome.switch_reason)
            elif outcome.action == "surface_guard_replan":
                self._pre_dig_align_surface_guard_count += 1
                self._pre_dig_align_hold_count = 0
                self._reject_active_coverage_corridor(
                    obs,
                    reason=outcome.reject_reason,
                )
                self._restart_dig_with_new_cut(outcome.switch_reason)
            elif outcome.action == "ready":
                self._pre_dig_align_completed_count += 1
                self._set_skill("dig", outcome.switch_reason)
            elif outcome.action == "timeout_handoff":
                self._pre_dig_align_timeout_count += 1
                self._set_skill("dig", outcome.switch_reason)
            elif outcome.action == "timeout_replan":
                self._pre_dig_align_timeout_count += 1
                self._reject_active_coverage_corridor(
                    obs,
                    reason=outcome.reject_reason,
                )
                if not self._try_replan_pre_dig_align_handoff(obs):
                    self._restart_pre_dig_align(outcome.switch_reason)
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

    def _stop_after_failed_dig(
        self,
        reason: str,
        obs: dict,
        *,
        switch_reason: str | None = None,
        terminal_reason: str | None = None,
    ) -> None:
        corridor = self._coverage_active_corridor()
        payload_gain = max(
            float(self._coverage_current_payload_gain_kg),
            float(self._dig_best_mass_kg),
            self._mass_in_bucket(obs),
            0.0,
        )
        self._switch_reason = str(switch_reason or f"dig_failed_stop_{reason}")
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
            str(terminal_reason or f"dig_failed_{reason}"),
            replace=True,
        )

    def _restart_after_failed_dig(self, reason: str, obs: dict) -> None:
        decision = self.dig_lifecycle_gate.failed_dig_recovery(
            reason=reason,
            facts=FailedDigRecoveryFacts(
                cycle_index=int(getattr(self, "_cycle_index", 0))
            ),
            config=self._dig_lifecycle_config(),
        )
        if decision.next_skill == PRE_DIG_ALIGN_SKILL_NAME:
            self._restart_pre_dig_align(decision.switch_reason)
            return
        if decision.next_skill == "stop":
            self._stop_after_failed_dig(
                reason,
                obs,
                switch_reason=decision.switch_reason,
                terminal_reason=decision.terminal_reason,
            )
            return
        self._restart_dig_with_new_cut(decision.switch_reason)

    def _should_pre_dig_align_before_dig(self) -> bool:
        return self.dig_lifecycle_gate.pre_dig_align_before_dig(
            FailedDigRecoveryFacts(cycle_index=int(getattr(self, "_cycle_index", 0))),
            self._dig_lifecycle_config(),
        )

    def _should_pre_dig_align_after_failed_dig(self) -> bool:
        return self.dig_lifecycle_gate.pre_dig_align_after_failed_dig(
            self._dig_lifecycle_config()
        )

    def _should_end_bootstrap(self, *, obs: dict, boundary_event: Any | None) -> bool:
        decision = self.bootstrap_service.should_end(
            self._bootstrap_facts(obs=obs, boundary_event=boundary_event),
            self._bootstrap_config(),
        )
        self._scripted_bootstrap_hold_count = int(decision.hold_count)
        if decision.timeout_increment:
            self._scripted_bootstrap_timeout_count += 1
        return bool(decision.should_end)

    def _bootstrap_config(self) -> BootstrapConfig:
        return BootstrapConfig(
            action_dim=int(self.action_dim),
            end_mode=str(self.bootstrap_end_mode),
            end_min_bucket_mass_kg=float(self.bootstrap_end_min_bucket_mass_kg),
            end_min_distance_to_dig_area_m=float(
                self.bootstrap_end_min_distance_to_dig_area_m
            ),
            scripted_target_qpos=self.scripted_bootstrap_target_qpos,
            scripted_kp=float(self.scripted_bootstrap_kp),
            scripted_kd=float(self.scripted_bootstrap_kd),
            scripted_action_clip=self.scripted_bootstrap_action_clip,
            scripted_action_signs=self.scripted_bootstrap_action_signs,
            scripted_qpos_tolerance=float(self.scripted_bootstrap_qpos_tolerance),
            scripted_qvel_abs_max=float(self.scripted_bootstrap_qvel_abs_max),
            scripted_hold_steps=int(self.scripted_bootstrap_hold_steps),
            scripted_max_steps=int(self.scripted_bootstrap_max_steps),
        )

    def _bootstrap_facts(
        self,
        *,
        obs: dict,
        boundary_event: Any | None = None,
    ) -> BootstrapFacts:
        return BootstrapFacts(
            qpos=np.asarray(
                obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
                dtype=np.float32,
            ).reshape(self.action_dim),
            qvel=np.asarray(
                obs.get("qvel", np.zeros(self.action_dim, dtype=np.float32)),
                dtype=np.float32,
            ).reshape(self.action_dim),
            mass_in_bucket_kg=self._mass_in_bucket(obs),
            min_distance_to_dig_area_m=self._min_distance_to_dig_area(obs),
            qualified_dig_start=bool(
                boundary_event is not None
                and getattr(boundary_event, "qualified_dig_start", False)
            ),
            step_count=int(self._scripted_bootstrap_step_count),
            hold_count=int(self._scripted_bootstrap_hold_count),
            bootstrap_policy_present=self.bootstrap_policy is not None,
        )

    def _scripted_bootstrap_enabled(self) -> bool:
        return self.bootstrap_service.scripted_enabled(self._bootstrap_config())

    def _scripted_bootstrap_target_reached(self, obs: dict) -> bool:
        decision = self.bootstrap_service.scripted_target_reached(
            self._bootstrap_facts(obs=obs),
            self._bootstrap_config(),
        )
        self._scripted_bootstrap_hold_count = int(decision.hold_count)
        return bool(decision.ready)

    def _scripted_bootstrap_action(self, obs: dict) -> np.ndarray:
        if self.scripted_bootstrap_target_qpos is None:
            raise RuntimeError("scripted bootstrap is active without target qpos.")
        self._scripted_bootstrap_step_count += 1
        return self.bootstrap_service.scripted_action(
            self._bootstrap_facts(obs=obs),
            self._bootstrap_config(),
        )

    def _pre_dig_align_surface_guard_triggered_for_state(self, obs: dict) -> bool:
        decision = self.dig_start_alignment_service.surface_guard_triggered(
            self._dig_start_alignment_facts(obs),
            self._dig_start_alignment_config(),
        )
        self._pre_dig_align_surface_depth_m = float(decision.surface_depth_m)
        self._pre_dig_align_surface_guard_triggered = bool(decision.triggered)
        return bool(decision.triggered)

    def _pre_dig_align_surface_guard_can_handoff(self, obs: dict) -> bool:
        self._ensure_dig_cut_plan_for_cycle(obs)
        entry_error = self._pre_dig_align_entry_error(obs)
        self._pre_dig_align_entry_error_m = float(entry_error)
        return self.dig_start_alignment_service.surface_guard_can_handoff(
            self._dig_start_alignment_facts(obs, entry_error=entry_error),
            self._dig_start_alignment_config(),
        )

    def _pre_dig_align_outcome(self, obs: dict) -> PreDigAlignOutcome:
        surface_guard_triggered = self._pre_dig_align_surface_guard_triggered_for_state(
            obs
        )
        if surface_guard_triggered:
            return self.dig_start_alignment_service.classify_outcome(
                surface_guard_triggered=True,
                surface_guard_can_handoff=self._pre_dig_align_surface_guard_can_handoff(
                    obs
                ),
            )
        if self._pre_dig_align_ready(obs):
            return self.dig_start_alignment_service.classify_outcome(
                surface_guard_triggered=False,
                ready=True,
            )
        timed_out = bool(self._pre_dig_align_step_count >= self.pre_dig_align_max_steps)
        if timed_out:
            return self.dig_start_alignment_service.classify_outcome(
                surface_guard_triggered=False,
                timed_out=True,
                timeout_can_handoff=self._pre_dig_align_timeout_can_handoff(obs),
                timeout_reason=self._pre_dig_align_timeout_handoff_reason,
            )
        return self.dig_start_alignment_service.classify_outcome(
            surface_guard_triggered=False,
        )

    def _dig_start_alignment_config(self) -> DigStartAlignmentConfig:
        return DigStartAlignmentConfig(
            action_dim=int(self.action_dim),
            qpos_min=self.pre_dig_align_qpos_min,
            qpos_max=self.pre_dig_align_qpos_max,
            qpos_from_token_coefficients=self.pre_dig_align_qpos_from_token_coefficients,
            controlled_dims=self.pre_dig_align_controlled_dims,
            entry_intent_controlled_dims=(
                None
                if self.pre_dig_align_entry_intent_controlled_dims is None
                else self.pre_dig_align_entry_intent_controlled_dims
            ),
            bucket_target_qpos=self.pre_dig_align_bucket_target_qpos,
            kp=float(self.pre_dig_align_kp),
            kd=float(self.pre_dig_align_kd),
            action_clip=self.pre_dig_align_action_clip,
            action_signs=self.pre_dig_align_action_signs,
            enabled=bool(self.pre_dig_align_enabled),
            qpos_tolerance=self.pre_dig_align_qpos_tolerance,
            qvel_abs_max=float(self.pre_dig_align_qvel_abs_max),
            hold_steps=int(self.pre_dig_align_hold_steps),
            max_entry_error_m=self.pre_dig_align_max_entry_error_m,
            timeout_accept_entry_error_m=(
                self.pre_dig_align_timeout_accept_entry_error_m
            ),
            start_envelope_enabled=bool(self.pre_dig_align_start_envelope_enabled),
            start_envelope_max_entry_error_m=float(
                self.pre_dig_align_start_envelope_max_entry_error_m
            ),
            first_dig_entry_close_handoff=bool(
                self.pre_dig_align_first_dig_entry_close_handoff
            ),
            first_dig_entry_close_handoff_qvel_abs_max=(
                self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
            ),
            entry_intent_handoff_enabled=bool(
                self.pre_dig_align_entry_intent_handoff_enabled
            ),
            surface_guard_enabled=bool(self.pre_dig_align_surface_guard_enabled),
            surface_guard_max_penetration_m=float(
                self.pre_dig_align_surface_guard_max_penetration_m
            ),
            surface_guard_handoff_entry_error_m=(
                self.pre_dig_align_surface_guard_handoff_entry_error_m
            ),
            surface_guard_use_contact_fallback=bool(
                self.pre_dig_align_surface_guard_use_contact_fallback
            ),
            start_qpos_min=self.pre_dig_align_start_qpos_min,
            start_qpos_max=self.pre_dig_align_start_qpos_max,
            start_pose_min=self.pre_dig_align_start_pose_min,
            start_pose_max=self.pre_dig_align_start_pose_max,
        )

    def _dig_start_alignment_facts(
        self,
        obs: dict,
        *,
        target_qpos: np.ndarray | None = None,
        entry_error: float | None = None,
        qpos: np.ndarray | None = None,
        qvel: np.ndarray | None = None,
    ) -> DigStartAlignmentFacts:
        qpos_arr = (
            np.asarray(qpos, dtype=np.float32).reshape(self.action_dim)
            if qpos is not None
            else np.asarray(
                obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
                dtype=np.float32,
            ).reshape(self.action_dim)
        )
        qvel_arr = (
            np.asarray(qvel, dtype=np.float32).reshape(self.action_dim)
            if qvel is not None
            else np.asarray(
                obs.get("qvel", np.zeros(self.action_dim, dtype=np.float32)),
                dtype=np.float32,
            ).reshape(self.action_dim)
        )
        target = (
            None
            if target_qpos is None
            else np.asarray(target_qpos, dtype=np.float32).reshape(self.action_dim)
        )
        return DigStartAlignmentFacts(
            qpos=qpos_arr,
            qvel=qvel_arr,
            target_qpos=target,
            entry_error_m=(
                self._pre_dig_align_entry_error(obs)
                if entry_error is None
                else float(entry_error)
            ),
            bucket_pose=self._bucket_dig_area_pose(obs),
            surface_depth_m=self._bucket_depth_below_local_surface(obs),
            contact_mask=self._bucket_dig_area_contact_mask(obs),
            cycle_index=int(getattr(self, "_cycle_index", 0)),
            hold_count=int(self._pre_dig_align_hold_count),
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
        entry_error = self._pre_dig_align_entry_error(obs)
        self._pre_dig_align_entry_error_m = float(entry_error)
        decision = self.dig_start_alignment_service.ready(
            self._dig_start_alignment_facts(
                obs,
                target_qpos=target_qpos,
                entry_error=entry_error,
                qpos=qpos,
                qvel=qvel,
            ),
            self._dig_start_alignment_config(),
        )
        self._pre_dig_align_error = decision.error.astype(np.float32)
        self._pre_dig_align_start_envelope_ready = bool(
            decision.start_envelope_ready
        )
        self._pre_dig_align_entry_close_handoff_ready = bool(
            decision.entry_close_handoff_ready
        )
        self._pre_dig_align_entry_intent_handoff_ready = bool(
            decision.entry_intent_handoff_ready
        )
        self._pre_dig_align_hold_count = int(decision.hold_count)
        return bool(decision.ready)

    def _pre_dig_align_entry_close(
        self,
        entry_error: float,
        *,
        threshold: float | None,
    ) -> bool:
        return self.dig_start_alignment_service.entry_close(
            entry_error,
            threshold=threshold,
        )

    def _pre_dig_align_entry_close_handoff_ready_for_state(
        self,
        *,
        entry_error: float,
        qvel: np.ndarray,
        start_envelope_ready: bool,
    ) -> bool:
        facts = DigStartAlignmentFacts(
            qpos=np.zeros(self.action_dim, dtype=np.float32),
            qvel=qvel,
            entry_error_m=float(entry_error),
            cycle_index=int(getattr(self, "_cycle_index", 0)),
        )
        return self.dig_start_alignment_service.entry_close_handoff_ready(
            facts=facts,
            config=self._dig_start_alignment_config(),
            start_envelope_ready=start_envelope_ready,
        )

    def _pre_dig_align_entry_intent_mode_enabled(self) -> bool:
        return self.dig_start_alignment_service.entry_intent_mode_enabled(
            self._dig_start_alignment_config()
        )

    def _pre_dig_align_entry_intent_handoff_ready_for_state(
        self,
        *,
        qpos_close: bool,
        qvel_small: bool,
    ) -> bool:
        return self.dig_start_alignment_service.entry_intent_handoff_ready(
            qpos_close=qpos_close,
            qvel_small=qvel_small,
            config=self._dig_start_alignment_config(),
        )

    def _pre_dig_align_timeout_can_handoff(self, obs: dict) -> bool:
        self._pre_dig_align_timeout_handoff_reason = ""
        config = self._dig_start_alignment_config()
        threshold = config.timeout_accept_entry_error_m
        if threshold is None:
            threshold = config.max_entry_error_m
        if threshold is None:
            decision = self.dig_start_alignment_service.timeout_can_handoff(
                DigStartAlignmentFacts(
                    qpos=np.zeros(self.action_dim, dtype=np.float32),
                    qvel=np.zeros(self.action_dim, dtype=np.float32),
                    entry_error_m=self._pre_dig_align_entry_error_m,
                ),
                config,
            )
            self._pre_dig_align_timeout_handoff_reason = str(decision.reason)
            return bool(decision.ready)
        entry_error = self._pre_dig_align_entry_error(obs)
        self._pre_dig_align_entry_error_m = float(entry_error)
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        decision = self.dig_start_alignment_service.timeout_can_handoff(
            self._dig_start_alignment_facts(
                obs,
                entry_error=entry_error,
                qpos=qpos,
            ),
            config,
        )
        self._pre_dig_align_start_envelope_ready = bool(
            decision.start_envelope_ready
        )
        if decision.entry_intent_handoff_ready:
            self._pre_dig_align_entry_intent_handoff_ready = True
        self._pre_dig_align_timeout_handoff_reason = str(decision.reason)
        return bool(decision.ready)

    def _pre_dig_align_start_envelope_ready_for_state(
        self,
        *,
        obs: dict,
        qpos: np.ndarray,
        entry_error: float,
    ) -> bool:
        return self.dig_start_alignment_service.start_envelope_ready(
            self._dig_start_alignment_facts(
                obs,
                qpos=qpos,
                entry_error=entry_error,
            ),
            self._dig_start_alignment_config(),
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
        action = self.dig_start_alignment_service.action_for_target(
            qpos=qpos,
            qvel=qvel,
            target_qpos=target_qpos,
            config=self._dig_start_alignment_config(),
        )
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
        qpos = np.asarray(
            obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)
        target = self.dig_start_alignment_service.target_from_token(
            token=token,
            qpos=qpos,
            config=self._dig_start_alignment_config(),
        )
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

    def _dig_lifecycle_config(self) -> DigLifecycleConfig:
        return DigLifecycleConfig(
            dig_to_carry_min_bucket_mass_kg=float(
                self.dig_to_carry_min_bucket_mass_kg
            ),
            dig_to_carry_min_distance_to_dig_area_m=float(
                self.dig_to_carry_min_distance_to_dig_area_m
            ),
            dig_to_carry_target_bucket_mass_kg=float(
                self.dig_to_carry_target_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_enabled=bool(
                self.dig_to_carry_mass_plateau_enabled
            ),
            dig_to_carry_mass_plateau_min_bucket_mass_kg=float(
                self.dig_to_carry_mass_plateau_min_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_epsilon_kg=float(
                self.dig_to_carry_mass_plateau_epsilon_kg
            ),
            dig_to_carry_mass_plateau_hold_steps=int(
                self.dig_to_carry_mass_plateau_hold_steps
            ),
            dig_to_carry_mass_plateau_min_steps=int(
                self.dig_to_carry_mass_plateau_min_steps
            ),
            dig_bad_replan_enabled=bool(self.dig_bad_replan_enabled),
            dig_bad_replan_max_steps=int(self.dig_bad_replan_max_steps),
            dig_bad_replan_min_bucket_mass_kg=float(
                self.dig_bad_replan_min_bucket_mass_kg
            ),
            dig_exit_guard_enabled=bool(self.dig_exit_guard_enabled),
            dig_exit_guard_min_steps=int(self.dig_exit_guard_min_steps),
            dig_exit_guard_overshoot_m=float(self.dig_exit_guard_overshoot_m),
            dig_exit_guard_min_bucket_mass_kg=float(
                self.dig_exit_guard_min_bucket_mass_kg
            ),
            dump_ready_min_bucket_mass_kg=float(self.dump_ready_min_bucket_mass_kg),
            dig_failed_replan_next_skill=str(self.dig_failed_replan_next_skill),
            pre_dig_align_enabled=bool(self.pre_dig_align_enabled),
            pre_dig_align_first_dig_only=bool(self.pre_dig_align_first_dig_only),
            pre_dig_align_replan_after_failed_dig=bool(
                self.pre_dig_align_replan_after_failed_dig
            ),
        )

    def _dig_lifecycle_facts(
        self,
        obs: dict,
        boundary_event: Any | None = None,
    ) -> DigLifecycleFacts:
        mass = self._mass_in_bucket(obs)
        dig_distance = self._min_distance_to_dig_area(obs)
        metrics = dict(getattr(boundary_event, "metrics", {}) or {})
        carry_mass = float(metrics.get("mass_in_bucket_kg", mass))
        carry_distance = float(
            metrics.get("min_distance_to_dig_area_m", dig_distance)
        )
        corridor = self._coverage_active_corridor()
        entry_xz: tuple[float, float] | None = None
        exit_xz: tuple[float, float] | None = None
        if corridor is not None:
            entry_xz = (float(corridor.entry_x_m), float(corridor.entry_z_m))
            exit_xz = (float(corridor.exit_x_m), float(corridor.exit_z_m))
        tip_pose = self._bucket_tip_dig_area_pose(obs)
        tip_xz = (
            None
            if tip_pose is None
            else (float(tip_pose[0]), float(tip_pose[2]))
        )
        return DigLifecycleFacts(
            mass_in_bucket_kg=mass,
            min_distance_to_dig_area_m=dig_distance,
            carry_mass_in_bucket_kg=carry_mass,
            carry_min_distance_to_dig_area_m=carry_distance,
            semantic_boundary_profile_active=self._semantic_boundary_profile_active(),
            boundary_dig_complete=bool(
                boundary_event is not None
                and getattr(boundary_event, "dig_complete", False)
            ),
            coverage_terminal_stop_requested=bool(
                self._coverage_terminal_stop_requested
            ),
            dig_step_count=int(self._dig_step_count),
            dig_best_mass_kg=float(self._dig_best_mass_kg),
            dig_mass_plateau_count=int(self._dig_mass_plateau_count),
            coverage_current_payload_gain_kg=float(
                self._coverage_current_payload_gain_kg
            ),
            active_corridor_entry_xz=entry_xz,
            active_corridor_exit_xz=exit_xz,
            bucket_tip_xz=tip_xz,
        )

    def _update_dig_progress(self, obs: dict) -> None:
        progress = self.dig_lifecycle_gate.update_progress(
            self._dig_lifecycle_facts(obs),
            self._dig_lifecycle_config(),
        )
        self._dig_step_count = int(progress.step_count)
        self._dig_best_mass_kg = float(progress.best_mass_kg)
        self._dig_mass_plateau_count = int(progress.mass_plateau_count)
        self._coverage_current_payload_gain_kg = float(
            progress.coverage_payload_gain_kg
        )

    def _dig_bad_replan_ready(self, obs: dict) -> bool:
        return self.dig_lifecycle_gate.bad_replan_ready(
            self._dig_lifecycle_facts(obs),
            self._dig_lifecycle_config(),
        )

    def _dig_exit_guard_ready(self, obs: dict) -> bool:
        return self.dig_lifecycle_gate.exit_guard_ready(
            self._dig_lifecycle_facts(obs),
            self._dig_lifecycle_config(),
        )

    def _dig_exit_overshoot_m(self, obs: dict) -> float:
        return self.dig_lifecycle_gate.exit_overshoot_m(
            self._dig_lifecycle_facts(obs),
        )

    def _dig_to_carry_ready(self, *, obs: dict, boundary_event: Any | None) -> bool:
        decision = self.dig_lifecycle_gate.dig_to_carry_ready(
            self._dig_lifecycle_facts(obs, boundary_event),
            self._dig_lifecycle_config(),
        )
        self._dig_to_carry_reason = str(decision.reason)
        return bool(decision.ready)

    def _semantic_dig_to_carry_liveness_ready(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        decision = self.dig_lifecycle_gate.semantic_liveness_ready(
            self._dig_lifecycle_facts(obs, boundary_event),
            self._dig_lifecycle_config(),
        )
        self._dig_to_carry_reason = str(decision.reason)
        return bool(decision.ready)

    def _dig_complete_boundary_low_payload(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        return self.dig_lifecycle_gate.complete_boundary_low_payload(
            self._dig_lifecycle_facts(obs, boundary_event),
            self._dig_lifecycle_config(),
        )

    def _semantic_boundary_profile_active(self) -> bool:
        config = getattr(self.boundary_detector, "config", None)
        profile = str(getattr(config, "boundary_profile", "legacy"))
        return profile == CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS

    def _dump_lifecycle_config(self) -> DumpLifecycleConfig:
        return DumpLifecycleConfig(
            dump_ready_min_bucket_mass_kg=float(self.dump_ready_min_bucket_mass_kg),
            dump_ready_min_height_above_rim_m=float(
                self.dump_ready_min_height_above_rim_m
            ),
            dump_ready_require_over_footprint=bool(
                self.dump_ready_require_over_footprint
            ),
            dump_ready_require_clearance=bool(self.dump_ready_require_clearance),
            dump_ready_max_horizontal_distance_m=(
                None
                if self.dump_ready_max_horizontal_distance_m is None
                else float(self.dump_ready_max_horizontal_distance_m)
            ),
            dump_ready_position_mode=str(self.dump_ready_position_mode),
            dump_ready_max_dump_area_footprint_outside_distance_m=(
                None
                if self.dump_ready_max_dump_area_footprint_outside_distance_m is None
                else float(self.dump_ready_max_dump_area_footprint_outside_distance_m)
            ),
            dump_ready_min_dump_area_relative_x_m=(
                None
                if self.dump_ready_min_dump_area_relative_x_m is None
                else float(self.dump_ready_min_dump_area_relative_x_m)
            ),
            dump_ready_max_dump_area_relative_x_m=(
                None
                if self.dump_ready_max_dump_area_relative_x_m is None
                else float(self.dump_ready_max_dump_area_relative_x_m)
            ),
            dump_ready_min_dump_area_relative_z_m=(
                None
                if self.dump_ready_min_dump_area_relative_z_m is None
                else float(self.dump_ready_min_dump_area_relative_z_m)
            ),
            dump_ready_max_dump_area_relative_z_m=(
                None
                if self.dump_ready_max_dump_area_relative_z_m is None
                else float(self.dump_ready_max_dump_area_relative_z_m)
            ),
            dump_ready_near_window_enabled=bool(self.dump_ready_near_window_enabled),
            dump_ready_near_window_x_tolerance_m=float(
                self.dump_ready_near_window_x_tolerance_m
            ),
            dump_ready_near_window_z_tolerance_m=float(
                self.dump_ready_near_window_z_tolerance_m
            ),
            dump_ready_near_window_outside_tolerance_m=float(
                self.dump_ready_near_window_outside_tolerance_m
            ),
            dump_ready_near_window_require_over_footprint=bool(
                self.dump_ready_near_window_require_over_footprint
            ),
            dump_done_max_bucket_mass_kg=float(self.dump_done_max_bucket_mass_kg),
            dump_done_min_deposit_delta_kg=float(self.dump_done_min_deposit_delta_kg),
            approach_ready_min_bucket_mass_kg=float(
                getattr(self, "approach_ready_min_bucket_mass_kg", 0.0)
            ),
            approach_ready_max_horizontal_distance_m=(
                None
                if getattr(self, "approach_ready_max_horizontal_distance_m", None)
                is None
                else float(self.approach_ready_max_horizontal_distance_m)
            ),
            approach_ready_min_height_above_rim_m=float(
                getattr(self, "approach_ready_min_height_above_rim_m", 0.0)
            ),
            approach_ready_require_clearance=bool(
                getattr(self, "approach_ready_require_clearance", True)
            ),
        )

    def _dump_lifecycle_facts(self, obs: dict) -> DumpLifecycleFacts:
        return DumpLifecycleFacts(
            mass_in_bucket_kg=self._mass_in_bucket(obs),
            deposited_mass_kg=self._deposited_mass(obs),
            target_geometry=self._target_geometry(obs),
            semantic_boundary_profile_active=self._semantic_boundary_profile_active(),
            coverage_cycle_start_deposit_kg=float(
                self._coverage_cycle_start_deposit_kg
            ),
        )

    def _dump_ready(self, obs: dict) -> bool:
        return self.dump_lifecycle_gate.dump_ready(
            self._dump_lifecycle_facts(obs),
            self._dump_lifecycle_config(),
        )

    def _dump_area_relative_dump_position_ok(self, geometry: dict[str, float]) -> bool:
        return self.dump_lifecycle_gate.dump_area_relative_dump_position_ok(
            geometry,
            self._dump_lifecycle_config(),
        )

    def _dump_area_relative_near_window_ok(
        self,
        *,
        geometry: dict[str, float],
        over_footprint: bool,
    ) -> bool:
        return self.dump_lifecycle_gate.dump_area_relative_near_window_ok(
            geometry=geometry,
            over_footprint=over_footprint,
            config=self._dump_lifecycle_config(),
        )

    @staticmethod
    def _optional_range_ok(
        *,
        geometry: dict[str, float],
        name: str,
        min_value: float | None,
        max_value: float | None,
    ) -> bool:
        return DumpLifecycleGateService.optional_range_ok(
            geometry=geometry,
            name=name,
            min_value=min_value,
            max_value=max_value,
        )

    @staticmethod
    def _optional_range_near_ok(
        *,
        geometry: dict[str, float],
        name: str,
        min_value: float | None,
        max_value: float | None,
        tolerance: float,
    ) -> bool:
        return DumpLifecycleGateService.optional_range_near_ok(
            geometry=geometry,
            name=name,
            min_value=min_value,
            max_value=max_value,
            tolerance=tolerance,
        )

    def _dump_ready_position_ok(
        self,
        *,
        over_footprint: bool,
        dump_area_relative_ok: bool,
        horizontal_ok: bool,
    ) -> bool:
        return self.dump_lifecycle_gate.dump_ready_position_ok(
            over_footprint=over_footprint,
            dump_area_relative_ok=dump_area_relative_ok,
            horizontal_ok=horizontal_ok,
            config=self._dump_lifecycle_config(),
        )

    def _dump_done(self, obs: dict) -> bool:
        return self.dump_lifecycle_gate.dump_done(
            self._dump_lifecycle_facts(obs),
            self._dump_lifecycle_config(),
            dump_start_deposited_mass_kg=self._dump_start_deposited_mass_kg,
        )

    def _carry_release_safety_done(self, obs: dict) -> bool:
        return self.dump_lifecycle_gate.carry_release_safety_done(
            self._dump_lifecycle_facts(obs),
            self._dump_lifecycle_config(),
        )

    def _make_snapshot(
        self,
        obs: dict,
        boundary_event: Any | None = None,
    ) -> PlannerSnapshot:
        return build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=self._prev_action,
            boundary_event=boundary_event,
            action_dim=self.action_dim,
        )

    def _return_to_dig_handoff_config(self) -> ReturnToDigHandoffConfig:
        return ReturnToDigHandoffConfig(
            shallow_guard_enabled=self.return_to_dig_shallow_guard_enabled,
            max_bucket_mass_kg=self.return_to_dig_max_bucket_mass_kg,
            touch_tolerance_m=self.return_to_dig_touch_tolerance_m,
            min_depth_m=self.return_to_dig_min_depth_m,
            max_depth_m=self.return_to_dig_max_depth_m,
            max_entry_error_m=self.return_to_dig_max_entry_error_m,
            start_envelope_gate_enabled=(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            direct_handoff_enabled=(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
        )

    def _return_to_dig_handoff_context(
        self,
        obs: dict,
        *,
        ensure_return_target: bool = True,
    ) -> ReturnToDigHandoffContext:
        if (
            ensure_return_target
            and self._skill_name == "return"
            and self.return_target_planner_enabled
        ):
            self._ensure_return_target_plan_for_cycle(obs)

        config = self._current_return_start_envelope_config()
        token = np.asarray(
            self._return_start_envelope_tokens,
            dtype=np.float32,
        ).reshape(-1)
        lower = None
        upper = None
        prior_mapping = None
        if config.gate_enabled and token.shape[0] == RETURN_START_ENVELOPE_TOKEN_DIM:
            token_has_bounds = not (
                float(token[RETURN_ENVELOPE_QPOS_VALID_IDX]) <= 0.5
                and float(token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX]) <= 0.5
            )
            if token_has_bounds:
                lower, upper = self._return_start_envelope_prior_bounds(
                    int(self._pending_dig_cut_corridor_id)
                )
                prior_mapping, _ = self._return_start_envelope_prior_mapping(
                    corridor_id=int(self._pending_dig_cut_corridor_id)
                )
        return ReturnToDigHandoffContext(
            entry_target=self._return_to_dig_entry_target(),
            envelope_token=token,
            envelope_config=config,
            prior_lower=lower,
            prior_upper=upper,
            prior_mapping=prior_mapping,
            use_prior_spatial_bounds=(
                self._return_start_envelope_use_prior_spatial_bounds
            ),
            use_prior_qpos_bounds=self._return_start_envelope_use_prior_qpos_bounds,
        )

    def _evaluate_return_to_dig_handoff(
        self,
        obs: dict,
        *,
        boundary_event: Any | None = None,
        handoff_ready_override: bool | None = None,
        ensure_return_target: bool = True,
    ) -> ReturnToDigHandoffDecision:
        snapshot = self._make_snapshot(obs, boundary_event=boundary_event)
        detector_config = getattr(self.boundary_detector, "config", None)
        boundary_facts = primitive_boundary_facts_from_event(
            boundary_event,
            profile_name=getattr(detector_config, "boundary_profile", ""),
        )
        context = self._return_to_dig_handoff_context(
            obs,
            ensure_return_target=ensure_return_target,
        )
        decision = self.return_handoff_gate.evaluate(
            snapshot,
            boundary_facts,
            context,
            config=self._return_to_dig_handoff_config(),
            handoff_ready_override=handoff_ready_override,
        )
        self._return_to_dig_entry_error_m = float(decision.entry_error_m)
        self._return_to_dig_entry_close_state = bool(decision.entry_close)
        self._return_to_dig_start_envelope_ready_state = bool(
            decision.envelope_state.ready
        )
        self._return_to_dig_start_envelope_error = float(decision.envelope_state.error)
        self._return_to_dig_start_envelope_checks = dict(
            decision.envelope_state.checks
        )
        return decision

    def _return_to_dig_shallow_guard_ready(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        return bool(
            self._evaluate_return_to_dig_handoff(
                obs,
                boundary_event=boundary_event,
            ).shallow_guard_ready
        )

    def _return_to_dig_entry_close(self, obs: dict) -> bool:
        return bool(self._evaluate_return_to_dig_handoff(obs).entry_close)

    def _return_to_dig_handoff_ready(self, obs: dict) -> bool:
        return bool(self._evaluate_return_to_dig_handoff(obs).handoff_ready)

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
        if handoff_ready is not None and not bool(handoff_ready):
            return False
        return bool(
            self._evaluate_return_to_dig_handoff(
                obs,
                handoff_ready_override=handoff_ready,
            ).direct_handoff_ready
        )

    def _return_to_dig_start_envelope_ready(self, obs: dict) -> bool:
        return bool(
            self._evaluate_return_to_dig_handoff(
                obs,
                ensure_return_target=False,
            ).envelope_state.ready
        )

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
        assembly = self.policy_observation_assembler.assemble(
            obs,
            PolicyObservationTokens(
                goal_tokens=self._goal_tokens(),
                cell_entry_tokens=self._cell_entry_tokens_for_obs(obs),
                dig_cut_tokens=self._dig_cut_tokens_for_obs(obs),
                dig_depth_profile_tokens=self._dig_depth_profile_tokens_for_obs(obs),
                return_target_tokens=self._return_target_tokens_for_obs(obs),
                return_relocate_tokens=self._return_relocate_tokens_for_obs(obs),
                return_start_envelope_tokens=(
                    self._return_start_envelope_tokens_for_obs(obs)
                ),
            ),
        )
        self._cell_entry_token_injected = assembly.cell_entry_token_injected
        self._dig_cut_token_injected = assembly.dig_cut_token_injected
        self._dig_depth_profile_token_injected = (
            assembly.dig_depth_profile_token_injected
        )
        self._return_target_token_injected = assembly.return_target_token_injected
        self._return_relocate_token_injected = assembly.return_relocate_token_injected
        self._return_start_envelope_token_injected = (
            assembly.return_start_envelope_token_injected
        )
        return assembly.obs

    def _return_target_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self._return_target_tokens.copy()

    def _return_relocate_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        token = derive_return_relocate_token(self._return_target_tokens)
        self._return_relocate_tokens = token
        return token

    def _return_start_envelope_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        if self._skill_name != "return" or not self.return_target_planner_enabled:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self._return_start_envelope_tokens.copy()

    def _ensure_return_target_plan_for_cycle(self, obs: dict) -> None:
        if not self.return_target_planner_enabled:
            return
        if self.return_target_plan_service.should_hold_plan(
            hold_until_skill_exit=self.return_target_hold_token_until_skill_exit,
            planned_cycle_id=self._return_target_planned_cycle_id,
            cycle_index=self._cycle_index,
        ):
            return
        try:
            token, raw_fields, source, fallback_reason, corridor_id = (
                self._build_next_dig_cut_plan_for_return(obs)
            )
            envelope_tokens = self._build_return_start_envelope_tokens_for_obs(
                obs,
                raw_fields,
                corridor_id=corridor_id,
            )
            state = self.return_target_plan_service.success_state(
                cycle_index=self._cycle_index,
                plan=ReturnTargetPlanBuild(
                    token=token,
                    raw_fields=raw_fields,
                    return_start_envelope_tokens=envelope_tokens,
                    source=source,
                    fallback_reason=fallback_reason,
                    corridor_id=corridor_id,
                ),
                exemplar=ReturnTargetExemplarSnapshot(
                    depth_profile_token=(
                        self._coverage_active_state_exemplar_profile_token
                    ),
                    state_exemplar_ids=self._coverage_active_state_exemplar_ids,
                    state_exemplar_distance=(
                        self._coverage_active_state_exemplar_distance
                    ),
                ),
            )
        except Exception as exc:
            state = self.return_target_plan_service.failure_state(
                cycle_index=self._cycle_index,
                reason=exc,
            )
        self._apply_return_target_plan_state(state)

    def _apply_return_target_plan_state(self, state: ReturnTargetPlanState) -> None:
        self._return_target_tokens = np.asarray(
            state.return_target_tokens,
            dtype=np.float32,
        )
        self._return_start_envelope_tokens = np.asarray(
            state.return_start_envelope_tokens,
            dtype=np.float32,
        )
        self._return_target_token_source = str(state.return_target_token_source)
        if state.return_start_envelope_token_source is not None:
            self._return_start_envelope_token_source = str(
                state.return_start_envelope_token_source
            )
        self._return_target_fallback_reason = str(state.return_target_fallback_reason)
        self._return_target_planned_cycle_id = int(
            state.return_target_planned_cycle_id
        )
        self._pending_dig_cut_cycle_id = int(state.pending_dig_cut_cycle_id)
        self._pending_dig_cut_raw_fields = (
            None
            if state.pending_dig_cut_raw_fields is None
            else dict(state.pending_dig_cut_raw_fields)
        )
        self._pending_dig_cut_tokens = (
            None
            if state.pending_dig_cut_tokens is None
            else np.asarray(state.pending_dig_cut_tokens, dtype=np.float32).copy()
        )
        self._pending_dig_cut_corridor_id = int(state.pending_dig_cut_corridor_id)
        self._pending_dig_depth_profile_tokens = (
            None
            if state.pending_dig_depth_profile_tokens is None
            else np.asarray(
                state.pending_dig_depth_profile_tokens,
                dtype=np.float32,
            ).copy()
        )
        self._pending_dig_state_exemplar_ids = list(
            state.pending_dig_state_exemplar_ids
        )
        self._pending_dig_state_exemplar_distance = float(
            state.pending_dig_state_exemplar_distance
        )

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
        try:
            state = self.dig_depth_profile_service.build_token(
                DigDepthProfileBuildRequest(
                    cell_id=cell_id,
                    raw_fields=self._dig_depth_profile_raw_fields(obs),
                    env_state=self._env_state(obs),
                    config=self._current_dig_depth_profile_config(),
                    dig_cut_prior=self.dig_cut_prior,
                    state_exemplar_profile_token=(
                        self._coverage_active_state_exemplar_profile_token
                    ),
                )
            )
        except DigDepthProfileMissingPriorError as exc:
            self._dig_depth_profile_token_source = "missing_required_prior"
            self._dig_depth_profile_fallback_reason = str(exc.reason)
            raise
        self._dig_depth_profile_token_source = str(state.source)
        self._dig_depth_profile_fallback_reason = str(state.fallback_reason)
        return np.asarray(state.token, dtype=np.float32)

    def _build_live_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict,
        *,
        cell_id: int,
    ) -> np.ndarray:
        return self.dig_depth_profile_service.build_live_token(
            DigDepthProfileBuildRequest(
                cell_id=cell_id,
                raw_fields=self._dig_depth_profile_raw_fields(obs),
                env_state=self._env_state(obs),
                config=self._current_dig_depth_profile_config(),
            ),
        )

    def _dig_depth_profile_prior_token(
        self,
        cell_id: int,
    ) -> tuple[np.ndarray | None, str, str]:
        return self.dig_depth_profile_service.prior_token(
            self.dig_cut_prior,
            cell_id=cell_id,
            allow_global_fallback=self.dig_depth_profile_allow_global_fallback,
        )

    def _dig_depth_profile_prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object] | None, str, str]:
        return self.dig_depth_profile_service.prior_mapping(
            self.dig_cut_prior,
            cell_id=cell_id,
            allow_global_fallback=self.dig_depth_profile_allow_global_fallback,
        )

    @staticmethod
    def _dig_depth_profile_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        return DigDepthProfileService.token_from_prior_mapping(mapping)

    def _current_dig_depth_profile_config(self) -> DigDepthProfileConfig:
        return DigDepthProfileConfig(
            source=self.dig_depth_profile_source,
            required=self.dig_depth_profile_required,
            allow_live_fallback=self.dig_depth_profile_allow_live_fallback,
            allow_global_fallback=self.dig_depth_profile_allow_global_fallback,
        )

    def _dig_depth_profile_raw_fields(self, obs: dict) -> dict[str, float | int]:
        pending_raw_fields = None
        if (
            self._pending_dig_cut_raw_fields is not None
            and self._pending_dig_cut_cycle_id == int(self._cycle_index)
        ):
            pending_raw_fields = self._pending_dig_cut_raw_fields
        active_raw_fields = None
        live_raw_fields = None
        if pending_raw_fields is None:
            corridor = self._coverage_active_corridor()
            if corridor is not None:
                active_raw_fields = self._coverage_raw_fields(corridor, obs=obs)
            else:
                live_raw_fields = self._raw_fields_from_live_pose(obs)
        return self.dig_depth_profile_service.resolve_raw_fields(
            DigDepthProfileInputFacts(
                cycle_index=int(self._cycle_index),
                pending_cycle_id=int(self._pending_dig_cut_cycle_id),
                pending_raw_fields=pending_raw_fields,
                active_corridor_raw_fields=active_raw_fields,
                live_raw_fields=live_raw_fields,
                current_dig_cut_tokens=self._dig_cut_tokens,
            )
        )

    def _dig_depth_profile_cell_id(self, obs: dict) -> int:
        pending_corridor_cell_id = None
        if (
            int(self._pending_dig_cut_corridor_id) >= 0
            and self._pending_dig_cut_cycle_id == int(self._cycle_index)
        ):
            corridor = self._coverage_corridor_by_id(int(self._pending_dig_cut_corridor_id))
            if corridor is not None:
                pending_corridor_cell_id = int(corridor.cell_id)
        active_corridor_cell_id = None
        if pending_corridor_cell_id is None:
            corridor = self._coverage_active_corridor()
            if corridor is not None:
                active_corridor_cell_id = int(corridor.cell_id)
        env_state = None
        if pending_corridor_cell_id is None and active_corridor_cell_id is None:
            env_state = self._env_state(obs)
        return self.dig_depth_profile_service.resolve_cell_id(
            DigDepthProfileInputFacts(
                cycle_index=int(self._cycle_index),
                pending_cycle_id=int(self._pending_dig_cut_cycle_id),
                pending_corridor_id=int(self._pending_dig_cut_corridor_id),
                pending_corridor_cell_id=pending_corridor_cell_id,
                active_corridor_cell_id=active_corridor_cell_id,
                env_state=env_state,
            )
        )

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
            raw_fields = self._coverage_raw_fields(
                corridor,
                obs=obs,
                update_state=True,
            )
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
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        state = build_return_start_envelope_for_plan(
            ReturnStartEnvelopeBuildRequest(
                env_state=self._env_state(obs),
                qpos=obs.get("qpos", np.zeros(self.action_dim)),
                qvel=obs.get("qvel", np.zeros(self.action_dim)),
                raw_fields=raw_fields,
                action_dim=self.action_dim,
                dig_cut_prior=self.dig_cut_prior,
                config=self._current_return_start_envelope_config(),
                cell_id=self._return_start_envelope_cell_id(corridor_id),
            )
        )
        self._return_start_envelope_token_source = str(state.source)
        self._return_start_envelope_use_prior_spatial_bounds = bool(
            state.use_prior_spatial_bounds
        )
        self._return_start_envelope_use_prior_qpos_bounds = bool(
            state.use_prior_qpos_bounds
        )
        if state.token is None:
            raise RuntimeError("return start-envelope builder returned no token.")
        return np.asarray(state.token, dtype=np.float32)

    def _maybe_condition_return_start_envelope_qpos_from_relocate(
        self,
        token: np.ndarray,
        *,
        raw_fields: dict[str, float | int],
        source: str,
    ) -> np.ndarray:
        state = condition_return_start_envelope_from_relocate(
            token,
            raw_fields=raw_fields,
            config=self._current_return_start_envelope_config(),
            source=source,
            use_prior_spatial_bounds=(
                self._return_start_envelope_use_prior_spatial_bounds
            ),
            use_prior_qpos_bounds=self._return_start_envelope_use_prior_qpos_bounds,
        )
        self._return_start_envelope_token_source = str(state.source)
        self._return_start_envelope_use_prior_spatial_bounds = bool(
            state.use_prior_spatial_bounds
        )
        self._return_start_envelope_use_prior_qpos_bounds = bool(
            state.use_prior_qpos_bounds
        )
        return np.asarray(state.token, dtype=np.float32)

    def _return_start_envelope_prior_token(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, str]:
        cell_id = self._return_start_envelope_cell_id(corridor_id)
        mapping, source = self._return_start_envelope_prior_mapping(
            corridor_id=corridor_id
        )
        return resolve_return_start_envelope_prior_token(
            mapping,
            source=source,
            cell_id=cell_id,
        )

    def _return_start_envelope_prior_mapping(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[dict[str, object] | None, str]:
        cell_id = self._return_start_envelope_cell_id(corridor_id)
        return resolve_return_start_envelope_prior_mapping(
            self.dig_cut_prior,
            config=self._current_return_start_envelope_config(),
            cell_id=cell_id,
        )

    def _return_start_envelope_prior_bounds(
        self,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        mapping, _ = self._return_start_envelope_prior_mapping(
            corridor_id=corridor_id
        )
        return resolve_return_start_envelope_prior_bounds(mapping)

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
        return return_start_envelope_token_from_prior_mapping(mapping)

    def _current_return_start_envelope_config(self) -> ReturnStartEnvelopeConfig:
        return ReturnStartEnvelopeConfig(
            use_cell_prior=self.return_start_envelope_use_cell_prior,
            min_source_count=self.return_start_envelope_min_source_count,
            min_source_fraction=self.return_start_envelope_min_source_fraction,
            qpos_from_relocate_enabled=(
                self.return_start_envelope_qpos_from_relocate_enabled
            ),
            qpos_from_relocate_coefficients=(
                self.return_start_envelope_qpos_from_relocate_coefficients
            ),
            qpos_from_relocate_min=self.return_start_envelope_qpos_from_relocate_min,
            qpos_from_relocate_max=self.return_start_envelope_qpos_from_relocate_max,
            qpos_from_relocate_use_prior_qpos_bounds=(
                self.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds
            ),
            spatial_from_relocate_enabled=(
                self.return_start_envelope_spatial_from_relocate_enabled
            ),
            spatial_from_relocate_coefficients=(
                self.return_start_envelope_spatial_from_relocate_coefficients
            ),
            spatial_from_relocate_min=(
                self.return_start_envelope_spatial_from_relocate_min
            ),
            spatial_from_relocate_max=(
                self.return_start_envelope_spatial_from_relocate_max
            ),
            spatial_from_relocate_use_prior_spatial_bounds=(
                self.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds
            ),
            gate_enabled=self.return_to_dig_start_envelope_gate_enabled,
            spatial_tolerance=self.return_to_dig_start_envelope_spatial_tolerance,
            depth_tolerance_m=self.return_to_dig_start_envelope_depth_tolerance_m,
            local_depth_tolerance_m=(
                self.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            plane_depth_tolerance_m=(
                self.return_to_dig_start_envelope_plane_depth_tolerance_m
            ),
            plane_depth_mode=self.return_to_dig_start_envelope_plane_depth_mode,
            qpos_tolerance=self.return_to_dig_start_envelope_qpos_tolerance,
            require_contact=self.return_to_dig_start_envelope_require_contact,
        )

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
                "operator_effective_deposit_delta_kg": 0.0,
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
            "operator_effective_deposit_delta_kg": 55.0,
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
            "operator_effective_deposit_delta_kg": float(
                self._prior_percentile(fields, "effective_deposit_delta_kg", "p50")
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
        raw_fields = self._coverage_raw_fields(
            corridor,
            obs=obs,
            update_state=True,
        )
        return (
            _build_dig_cut_token(raw_fields),
            raw_fields,
            "operator_prior_coverage",
            "",
        )


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
        return DigCoverageMixin._coverage_percentile_list(value, default=default)

    @staticmethod
    def _coverage_percentile_name(value: object, *, default: str) -> str:
        return DigCoverageMixin._coverage_percentile_name(value, default=default)

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
        return DigCoverageMixin._prior_percentile(fields, field_name, percentile)

    def _clamp_to_prior(
        self, fields: dict[str, Any], field_name: str, value: float
    ) -> float:
        return self._coverage_service()._clamp_to_prior(fields, field_name, value)

    def _raw_fields_in_prior_range(self, raw_fields: dict[str, float | int]) -> bool:
        return self._coverage_service().raw_fields_in_prior_range(raw_fields)

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
    return pd_servo_action(
        qpos=qpos,
        qvel=qvel,
        target_qpos=target_qpos,
        kp=kp,
        kd=kd,
        action_clip=action_clip,
        action_signs=action_signs,
    )


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
        return self.dump_lifecycle_gate.approach_ready(
            self._dump_lifecycle_facts(obs),
            self._dump_lifecycle_config(),
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
