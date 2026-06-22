"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

import json
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
from testbed.planner.primitive_backend import (
    LegacyFSMBranchPorts,
    LegacyFSMBranchSet,
    LegacyFSMCompatibilityDecisionBackend,
    LegacyFSMRequestedDecisionBackend,
)
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_capability_provider import (
    PrimitiveFSMCapabilityProvider,
    PrimitiveFSMCapabilityProviderPorts,
)
from testbed.planner.primitive_coverage import (
    CoverageCandidateBuilder,
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionConfig,
    CoverageSelectionRuntimeCoordinator,
    CoverageSelectionRuntimePorts,
    CoverageSelectionService,
)
from testbed.planner.primitive_coverage_exemplars import (
    CoverageStateExemplarPlanInputs,
    CoverageStateExemplarPlanner,
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive_coverage_reports import (
    CoverageBucketSnapshot,
    CoverageReportService,
    CoverageReportState,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_coverage_updates import (
    CoverageCompletionFacts,
    CoverageEffectRuntimeCoordinator,
    CoverageEffectRuntimePorts,
    CoverageReopenFacts,
    CoverageRejectionFacts,
    CoverageRuntimeConfig,
    CoverageRuntimeService,
    CoverageTerminalFacts,
    CoverageUpdateConfig,
    CoverageUpdateService,
)
from testbed.planner.primitive_debug_report import (
    PrimitiveDebugReportBuilder,
    PrimitiveDebugReportInputs,
    PrimitiveDebugStateSnapshot,
)
from testbed.planner.primitive_action_dispatch import (
    PrimitiveActionDispatchPorts,
    PrimitiveActionDispatchService,
)
from testbed.planner.primitive_execution import (
    PrimitiveExecutionDriver,
    PrimitiveExecutionPorts,
    PrimitiveTickCallbacks,
    PrimitiveTickPreparation,
)
from testbed.planner.primitive_tick_finalization import (
    PrimitivePlannerDebugState,
    PrimitiveTickFinalizationInputs,
    PrimitiveTickFinalizationService,
)
from testbed.planner.primitive_decision import (
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
)
from testbed.planner.primitive_decision_capabilities import (
    PrimitiveDecisionCapabilities,
    PrimitiveDecisionCapabilitiesPorts,
)
from testbed.planner.primitive_decision_runtime import (
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimeConfig,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive_effects import (
    RequestedEffectApplier,
    RequestedEffectApplierPorts,
)
from testbed.planner.primitive_observation import (
    PrimitivePolicyObservationAssembler,
    PrimitivePolicyObservationAssemblerPorts,
    PrimitivePolicyObservationAssemblyResult,
)
from testbed.planner.primitive_planner_trace import (
    PrimitivePlannerTraceBuilder,
    PrimitivePlannerTraceInputs,
)
from testbed.planner.primitive_rollout_summary import (
    PrimitiveRolloutSummaryBuilder,
    PrimitiveRolloutSummaryInputs,
)
from testbed.planner.primitive_return_handoff import (
    ReturnDirectHandoffEffectPorts,
    ReturnDirectHandoffEffectService,
    ReturnStartEnvelopeGateConfig,
    ReturnStartEnvelopeGateInputs,
    ReturnStartEnvelopeGateResult,
    ReturnStartEnvelopeGateService,
)
from testbed.planner.primitive_token_status import TokenStatus
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
        self._coverage_state = CoverageRuntimeState()
        self._debug_state = self._make_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )

    def _coverage_runtime_state(self) -> CoverageRuntimeState:
        state = self.__dict__.get("_coverage_state")
        if state is None:
            state = CoverageRuntimeState()
            self.__dict__["_coverage_state"] = state
        return state

    @property
    def _coverage_corridors(self) -> list[CoverageCorridorState]:
        return self._coverage_runtime_state().coverage_corridors

    @_coverage_corridors.setter
    def _coverage_corridors(self, value: list[CoverageCorridorState]) -> None:
        self._coverage_runtime_state().coverage_corridors = value

    @property
    def _coverage_active_corridor_id(self) -> int:
        return int(self._coverage_runtime_state().coverage_active_corridor_id)

    @_coverage_active_corridor_id.setter
    def _coverage_active_corridor_id(self, value: int) -> None:
        self._coverage_runtime_state().coverage_active_corridor_id = int(value)

    @property
    def _coverage_last_selected_corridor_id(self) -> int:
        return int(self._coverage_runtime_state().coverage_last_selected_corridor_id)

    @_coverage_last_selected_corridor_id.setter
    def _coverage_last_selected_corridor_id(self, value: int) -> None:
        self._coverage_runtime_state().coverage_last_selected_corridor_id = int(value)

    @property
    def _coverage_current_payload_gain_kg(self) -> float:
        return float(self._coverage_runtime_state().coverage_current_payload_gain_kg)

    @_coverage_current_payload_gain_kg.setter
    def _coverage_current_payload_gain_kg(self, value: float) -> None:
        self._coverage_runtime_state().coverage_current_payload_gain_kg = float(value)

    @property
    def _coverage_cycle_start_deposit_kg(self) -> float:
        return float(self._coverage_runtime_state().coverage_cycle_start_deposit_kg)

    @_coverage_cycle_start_deposit_kg.setter
    def _coverage_cycle_start_deposit_kg(self, value: float) -> None:
        self._coverage_runtime_state().coverage_cycle_start_deposit_kg = float(value)

    @property
    def _coverage_last_payload_gain_kg(self) -> float:
        return float(self._coverage_runtime_state().coverage_last_payload_gain_kg)

    @_coverage_last_payload_gain_kg.setter
    def _coverage_last_payload_gain_kg(self, value: float) -> None:
        self._coverage_runtime_state().coverage_last_payload_gain_kg = float(value)

    @property
    def _coverage_last_effective_deposit_delta_kg(self) -> float:
        return float(
            self._coverage_runtime_state().coverage_last_effective_deposit_delta_kg
        )

    @_coverage_last_effective_deposit_delta_kg.setter
    def _coverage_last_effective_deposit_delta_kg(self, value: float) -> None:
        self._coverage_runtime_state().coverage_last_effective_deposit_delta_kg = (
            float(value)
        )

    @property
    def _coverage_global_low_productivity_streak(self) -> int:
        return int(
            self._coverage_runtime_state().coverage_global_low_productivity_streak
        )

    @_coverage_global_low_productivity_streak.setter
    def _coverage_global_low_productivity_streak(self, value: int) -> None:
        self._coverage_runtime_state().coverage_global_low_productivity_streak = int(
            value
        )

    @property
    def _coverage_completed_dump_count(self) -> int:
        return int(self._coverage_runtime_state().coverage_completed_dump_count)

    @_coverage_completed_dump_count.setter
    def _coverage_completed_dump_count(self, value: int) -> None:
        self._coverage_runtime_state().coverage_completed_dump_count = int(value)

    @property
    def _coverage_pass_index(self) -> int:
        return int(self._coverage_runtime_state().coverage_pass_index)

    @_coverage_pass_index.setter
    def _coverage_pass_index(self, value: int) -> None:
        self._coverage_runtime_state().coverage_pass_index = int(value)

    @property
    def _coverage_terminal_stop_requested(self) -> bool:
        return bool(self._coverage_runtime_state().coverage_terminal_stop_requested)

    @_coverage_terminal_stop_requested.setter
    def _coverage_terminal_stop_requested(self, value: bool) -> None:
        self._coverage_runtime_state().coverage_terminal_stop_requested = bool(value)

    @property
    def _coverage_terminal_stop_reason(self) -> str:
        return str(self._coverage_runtime_state().coverage_terminal_stop_reason)

    @_coverage_terminal_stop_reason.setter
    def _coverage_terminal_stop_reason(self, value: str) -> None:
        self._coverage_runtime_state().coverage_terminal_stop_reason = str(value)

    @property
    def _coverage_candidate_scores(self) -> list[dict[str, Any]]:
        return self._coverage_runtime_state().coverage_candidate_scores

    @_coverage_candidate_scores.setter
    def _coverage_candidate_scores(self, value: list[dict[str, Any]]) -> None:
        self._coverage_runtime_state().coverage_candidate_scores = value

    @property
    def _coverage_decision_trace(self) -> list[dict[str, Any]]:
        return self._coverage_runtime_state().coverage_decision_trace

    @_coverage_decision_trace.setter
    def _coverage_decision_trace(self, value: list[dict[str, Any]]) -> None:
        self._coverage_runtime_state().coverage_decision_trace = value

    @property
    def _coverage_active_state_exemplar_ids(self) -> list[str]:
        return self._coverage_runtime_state().coverage_active_state_exemplar_ids

    @_coverage_active_state_exemplar_ids.setter
    def _coverage_active_state_exemplar_ids(self, value: list[str]) -> None:
        self._coverage_runtime_state().coverage_active_state_exemplar_ids = value

    @property
    def _coverage_rejected_state_exemplar_ids(self) -> set[str]:
        return self._coverage_runtime_state().coverage_rejected_state_exemplar_ids

    @_coverage_rejected_state_exemplar_ids.setter
    def _coverage_rejected_state_exemplar_ids(self, value: set[str]) -> None:
        self._coverage_runtime_state().coverage_rejected_state_exemplar_ids = value

    @property
    def _coverage_active_state_exemplar_distance(self) -> float:
        return float(
            self._coverage_runtime_state().coverage_active_state_exemplar_distance
        )

    @_coverage_active_state_exemplar_distance.setter
    def _coverage_active_state_exemplar_distance(self, value: float) -> None:
        self._coverage_runtime_state().coverage_active_state_exemplar_distance = float(
            value
        )

    @property
    def _coverage_active_state_exemplar_profile_token(self) -> np.ndarray | None:
        return (
            self._coverage_runtime_state().coverage_active_state_exemplar_profile_token
        )

    @_coverage_active_state_exemplar_profile_token.setter
    def _coverage_active_state_exemplar_profile_token(
        self,
        value: np.ndarray | None,
    ) -> None:
        self._coverage_runtime_state().coverage_active_state_exemplar_profile_token = (
            value
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
        return self._action_dispatch_service().dispatch_action(obs)

    def _action_dispatch_service(self) -> PrimitiveActionDispatchService:
        return PrimitiveActionDispatchService.from_ports(self._action_dispatch_ports())

    def _action_dispatch_ports(self) -> PrimitiveActionDispatchPorts:
        return PrimitiveActionDispatchPorts(
            current_skill_name=lambda: str(self._skill_name),
            action_dim=int(self.action_dim),
            skill_policies={
                "dig": self.dig_policy,
                "carry": self.carry_policy,
                "dump": self.dump_policy,
                "return": self.return_policy,
            },
            base_policy_order=("dig", "carry", "dump", "return"),
            optional_policy_order=("first_dig", "bootstrap"),
            first_dig_policy=self.first_dig_policy,
            bootstrap_policy=self.bootstrap_policy,
            cycle_index=lambda: int(getattr(self, "_cycle_index", 0)),
            coverage_completed_dump_count=lambda: int(
                getattr(self, "_coverage_completed_dump_count", 0)
            ),
            policy_observation=lambda obs: self._policy_obs(obs),
            scripted_bootstrap_enabled=lambda: self._scripted_bootstrap_enabled(),
            scripted_bootstrap_action=lambda obs: self._scripted_bootstrap_action(obs),
            pre_dig_align_action=lambda obs: self._pre_dig_align_action(obs),
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            dig_skill_name="dig",
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )

    def _record_tick_previous_action(self, action: np.ndarray) -> None:
        self._prev_action = self._tick_finalization_service().copy_previous_action(
            action
        )

    def _transition_completed_after_tick_dispatch(self) -> bool:
        return self._tick_finalization_service().transition_completed_after_dispatch(
            self._switch_reason
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

    @staticmethod
    def _tick_finalization_service() -> PrimitiveTickFinalizationService:
        return PrimitiveTickFinalizationService()

    def _decide_tick_with_legacy_fsm(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self._decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )

    def _decide_tick(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self._decision_runtime().decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )

    def _decision_runtime(self) -> PrimitiveDecisionRuntime:
        return PrimitiveDecisionRuntime.from_ports(
            self._decision_runtime_ports(),
            config=self._decision_runtime_config(),
        )

    @staticmethod
    def _decision_runtime_config() -> PrimitiveDecisionRuntimeConfig:
        return PrimitiveDecisionRuntimeConfig()

    def _decision_runtime_ports(self) -> PrimitiveDecisionRuntimePorts:
        return PrimitiveDecisionRuntimePorts(
            legacy_fsm_branch_set=(
                lambda: LegacyFSMBranchSet.from_ports(self._legacy_fsm_branch_ports())
            ),
        )

    def _legacy_fsm_requested_decision_backend(
        self,
    ) -> LegacyFSMRequestedDecisionBackend:
        return self._decision_runtime().legacy_fsm_requested_decision_backend()

    def _legacy_fsm_compatibility_decision_backend(
        self,
    ) -> LegacyFSMCompatibilityDecisionBackend:
        return self._decision_runtime().legacy_fsm_compatibility_decision_backend()

    def _legacy_fsm_branch_set(self) -> LegacyFSMBranchSet:
        return self._decision_runtime().legacy_fsm_branch_set()

    def _apply_requested_tick_effects(
        self,
        obs: dict,
        effects: tuple[RequestedPlannerEffect, ...],
    ) -> None:
        if not effects:
            return
        self._requested_effect_applier().apply(obs, effects)

    def _requested_effect_applier(self) -> RequestedEffectApplier:
        return RequestedEffectApplier.from_ports(self._requested_effect_applier_ports())

    def _requested_effect_applier_ports(self) -> RequestedEffectApplierPorts:
        return RequestedEffectApplierPorts(
            set_skill=lambda skill, reason: self._set_skill(skill, reason),
            mark_return_next_dig_event_seen=(
                lambda: self._mark_return_next_dig_event_seen()
            ),
            complete_return_transition=(
                lambda: self._complete_return_transition_for_backend()
            ),
            next_skill_after_return_transition=(
                lambda: self._next_skill_after_return_transition()
            ),
            increment_dig_exit_guard_replan_count=(
                lambda: self._increment_dig_exit_guard_replan_count()
            ),
            increment_dig_bad_replan_count=(
                lambda: self._increment_dig_bad_replan_count()
            ),
            reject_active_coverage_corridor=(
                lambda obs, reason: self._reject_active_coverage_corridor(
                    obs,
                    reason=reason,
                )
            ),
            restart_after_failed_dig=(
                lambda reason, obs: self._restart_after_failed_dig(reason, obs)
            ),
            complete_cell_entry_dig=lambda obs: self._complete_cell_entry_dig(obs),
            complete_coverage_dig=lambda obs: self._complete_coverage_dig(obs),
            set_dump_ready_hold_count=(
                lambda value: self._set_dump_ready_hold_count(value)
            ),
            deposited_mass=lambda obs: self._deposited_mass(obs),
            set_dump_start_deposited_mass=(
                lambda value: self._set_dump_start_deposited_mass(value)
            ),
            set_dump_done_hold_count=lambda value: self._set_dump_done_hold_count(value),
            complete_coverage_dump=(
                lambda obs, reason: self._complete_coverage_dump(
                    obs,
                    reason=reason,
                )
            ),
            set_return_or_direct_handoff=(
                lambda obs, reason: self._set_return_or_direct_handoff(
                    obs,
                    reason=reason,
                )
            ),
        )

    def _legacy_fsm_branch_ports(self) -> LegacyFSMBranchPorts:
        return LegacyFSMBranchPorts(
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            dig_skill_name="dig",
            carry_skill_name="carry",
            dump_skill_name="dump",
            return_skill_name="return",
            capabilities=self._primitive_decision_capabilities(),
        )

    def _primitive_decision_capabilities(self) -> PrimitiveDecisionCapabilities:
        return PrimitiveDecisionCapabilities.from_ports(
            self._primitive_decision_capabilities_ports()
        )

    def _primitive_decision_capabilities_ports(
        self,
    ) -> PrimitiveDecisionCapabilitiesPorts:
        return PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: str(self._skill_name),
            current_switch_reason=lambda: str(self._switch_reason),
            should_end_bootstrap=self._should_end_bootstrap,
            bootstrap_end_mode=lambda: str(self.bootstrap_end_mode),
            should_pre_dig_align_before_dig=self._should_pre_dig_align_before_dig,
            transition_status_provider=self._primitive_fsm_capability_provider(),
            maybe_handle_residual_pre_dig_align=(
                self._maybe_handle_pre_dig_align_skill
            ),
        )

    def _primitive_fsm_capability_provider(
        self,
    ) -> PrimitiveFSMCapabilityProvider:
        return PrimitiveFSMCapabilityProvider.from_ports(
            self._primitive_fsm_capability_provider_ports()
        )

    def _primitive_fsm_capability_provider_ports(
        self,
    ) -> PrimitiveFSMCapabilityProviderPorts:
        return PrimitiveFSMCapabilityProviderPorts(
            action_dim=self.action_dim,
            semantic_boundary_profile_active=(
                lambda: self._semantic_boundary_profile_active()
            ),
            coverage_terminal_stop_requested=self._coverage_terminal_stop_requested,
            dig_step_count=self._dig_step_count,
            dig_mass_plateau_count=self._dig_mass_plateau_count,
            dig_to_carry_min_distance_to_dig_area_m=(
                self.dig_to_carry_min_distance_to_dig_area_m
            ),
            dig_to_carry_min_bucket_mass_kg=self.dig_to_carry_min_bucket_mass_kg,
            dig_to_carry_target_bucket_mass_kg=(
                self.dig_to_carry_target_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_enabled=(
                self.dig_to_carry_mass_plateau_enabled
            ),
            dig_to_carry_mass_plateau_min_bucket_mass_kg=(
                self.dig_to_carry_mass_plateau_min_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_hold_steps=(
                self.dig_to_carry_mass_plateau_hold_steps
            ),
            dig_to_carry_mass_plateau_min_steps=(
                self.dig_to_carry_mass_plateau_min_steps
            ),
            dump_ready_min_bucket_mass_kg=self.dump_ready_min_bucket_mass_kg,
            dig_bad_replan_enabled=self.dig_bad_replan_enabled,
            dig_bad_replan_max_steps=self.dig_bad_replan_max_steps,
            dig_bad_replan_min_bucket_mass_kg=self.dig_bad_replan_min_bucket_mass_kg,
            dig_exit_guard_enabled=self.dig_exit_guard_enabled,
            dig_exit_guard_min_steps=self.dig_exit_guard_min_steps,
            dig_exit_guard_min_bucket_mass_kg=self.dig_exit_guard_min_bucket_mass_kg,
            dig_exit_guard_overshoot_m=self.dig_exit_guard_overshoot_m,
            dig_exit_overshoot_m=lambda obs: self._dig_exit_overshoot_m(obs),
            set_dig_to_carry_reason=(
                lambda reason: setattr(
                    self,
                    "_dig_to_carry_reason",
                    str(reason),
                )
            ),
            coverage_cycle_start_deposit_kg=self._coverage_cycle_start_deposit_kg,
            dump_ready_hold_count=self._dump_ready_hold_count,
            dump_ready_hold_steps=self.dump_ready_hold_steps,
            dump_ready_min_height_above_rim_m=self.dump_ready_min_height_above_rim_m,
            dump_ready_require_over_footprint=self.dump_ready_require_over_footprint,
            dump_ready_require_clearance=self.dump_ready_require_clearance,
            dump_ready_max_horizontal_distance_m=(
                self.dump_ready_max_horizontal_distance_m
            ),
            dump_ready_position_mode=self.dump_ready_position_mode,
            dump_ready_max_dump_area_footprint_outside_distance_m=(
                self.dump_ready_max_dump_area_footprint_outside_distance_m
            ),
            dump_ready_min_dump_area_relative_x_m=(
                self.dump_ready_min_dump_area_relative_x_m
            ),
            dump_ready_max_dump_area_relative_x_m=(
                self.dump_ready_max_dump_area_relative_x_m
            ),
            dump_ready_min_dump_area_relative_z_m=(
                self.dump_ready_min_dump_area_relative_z_m
            ),
            dump_ready_max_dump_area_relative_z_m=(
                self.dump_ready_max_dump_area_relative_z_m
            ),
            dump_ready_near_window_enabled=self.dump_ready_near_window_enabled,
            dump_ready_near_window_x_tolerance_m=(
                self.dump_ready_near_window_x_tolerance_m
            ),
            dump_ready_near_window_z_tolerance_m=(
                self.dump_ready_near_window_z_tolerance_m
            ),
            dump_ready_near_window_outside_tolerance_m=(
                self.dump_ready_near_window_outside_tolerance_m
            ),
            dump_ready_near_window_require_over_footprint=(
                self.dump_ready_near_window_require_over_footprint
            ),
            dump_done_max_bucket_mass_kg=self.dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=self.dump_done_min_deposit_delta_kg,
            dump_done_use_boundary_event=self.dump_done_use_boundary_event,
            dump_start_deposited_mass_kg=self._dump_start_deposited_mass_kg,
            dump_done_hold_count=self._dump_done_hold_count,
            dump_done_hold_steps=self.dump_done_hold_steps,
            refresh_return_handoff_state=(
                lambda obs: self._return_to_dig_handoff_ready(obs)
            ),
            return_next_dig_event_seen=(
                lambda: bool(self._return_next_dig_event_seen)
            ),
            return_entry_close=(
                lambda: bool(self._return_to_dig_entry_close_state)
            ),
            return_start_envelope_ready=(
                lambda: bool(self._return_to_dig_start_envelope_ready_state)
            ),
            pre_dig_align_before_dig=(
                lambda: self._should_pre_dig_align_before_dig()
            ),
            return_to_dig_start_envelope_direct_handoff_enabled=(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            return_to_dig_start_envelope_gate_enabled=(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            return_to_dig_shallow_guard_enabled=(
                self.return_to_dig_shallow_guard_enabled
            ),
            return_to_dig_max_bucket_mass_kg=self.return_to_dig_max_bucket_mass_kg,
            return_to_dig_touch_tolerance_m=self.return_to_dig_touch_tolerance_m,
            return_to_dig_min_depth_m=self.return_to_dig_min_depth_m,
            return_to_dig_max_depth_m=self.return_to_dig_max_depth_m,
            return_to_dig_max_entry_error_m=self.return_to_dig_max_entry_error_m,
        )

    def _dig_transition_status_for_backend(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> DigTransitionStatus:
        return self._primitive_fsm_capability_provider().dig_transition_status(
            obs,
            boundary_event,
        )

    def _carry_transition_status_for_backend(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> CarryTransitionStatus:
        return self._primitive_fsm_capability_provider().carry_transition_status(
            obs,
            boundary_event,
        )

    def _set_dump_ready_hold_count(self, value: int) -> None:
        self._dump_ready_hold_count = int(value)

    def _set_dump_start_deposited_mass(self, value: float) -> None:
        self._dump_start_deposited_mass_kg = float(value)

    def _dump_transition_status_for_backend(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> DumpTransitionStatus:
        return self._primitive_fsm_capability_provider().dump_transition_status(
            obs,
            boundary_event,
        )

    def _set_dump_done_hold_count(self, value: int) -> None:
        self._dump_done_hold_count = int(value)

    def _return_transition_status_for_backend(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        return self._primitive_fsm_capability_provider().return_transition_status(
            obs,
            boundary_event,
        )

    def _mark_return_next_dig_event_seen(self) -> None:
        self._return_next_dig_event_seen = True

    def _complete_return_transition_for_backend(self) -> None:
        self._completed_transition_count += 1
        self._cycle_index += 1

    def _next_skill_after_return_transition(self) -> str:
        return (
            PRE_DIG_ALIGN_SKILL_NAME
            if self._should_pre_dig_align_before_dig()
            else "dig"
        )

    def _increment_dig_exit_guard_replan_count(self) -> None:
        self._dig_exit_guard_replan_count += 1

    def _increment_dig_bad_replan_count(self) -> None:
        self._dig_bad_replan_count += 1

    def _tick_execution_hooks(self) -> PrimitiveTickCallbacks:
        ports = self._execution_driver_ports()
        return PrimitiveTickCallbacks(
            update_boundary_event=ports.update_boundary_event,
            reset_switch_reason=ports.reset_switch_reason,
            current_skill_name=ports.current_skill_name,
            update_dig_progress=ports.update_dig_progress,
            decide_tick=ports.decide_tick,
            apply_requested_effects=ports.apply_requested_effects,
            account_return_timeout=ports.account_return_timeout,
            dispatch_action=ports.dispatch_action,
            record_previous_action=ports.record_previous_action,
            transition_completed_after_dispatch=(
                ports.transition_completed_after_dispatch
            ),
            finalize_debug_state=ports.finalize_debug_state,
        )

    def _execution_driver_ports(self) -> PrimitiveExecutionPorts:
        return PrimitiveExecutionPorts(
            update_boundary_event=self._tick_boundary_event,
            reset_switch_reason=self._reset_tick_switch_reason,
            current_skill_name=self._current_tick_skill_name,
            update_dig_progress=self._update_dig_progress,
            decide_tick=self._decide_tick,
            apply_requested_effects=self._apply_requested_tick_effects,
            account_return_timeout=self._account_return_timeout_for_tick,
            dispatch_action=self._dispatch_tick_action,
            record_previous_action=self._record_tick_previous_action,
            transition_completed_after_dispatch=(
                self._transition_completed_after_tick_dispatch
            ),
            finalize_debug_state=self._finalize_tick_debug_state,
        )

    def _execution_driver(self) -> PrimitiveExecutionDriver:
        return PrimitiveExecutionDriver.from_ports(self._execution_driver_ports())

    def predict(self, obs: dict) -> np.ndarray:
        return self._execution_driver().predict(obs)

    def debug_state(self) -> dict[str, Any]:
        return self._debug_report_builder().build(self._debug_report_inputs())

    @staticmethod
    def _debug_report_builder() -> PrimitiveDebugReportBuilder:
        return PrimitiveDebugReportBuilder()

    def _debug_report_inputs(self) -> PrimitiveDebugReportInputs:
        return PrimitiveDebugReportInputs(
            debug_state=self._debug_state_snapshot_for_report(),
            transition_source=TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            transition_policy_mode=TRANSITION_POLICY_MODE_PRIMITIVE,
            transition_fallback_count=0,
            transition_fallback_reason="",
            primitive_goal_curr_sector_id=int(self._goal_sector_id(self._cycle_index)),
            primitive_goal_next_sector_id=int(self._next_goal_sector_id()),
            token_status=self._token_status_for_debug_report(),
            dig_failed_replan_next_skill=str(self.dig_failed_replan_next_skill),
            return_fields=self._debug_report_return_fields(),
            pending_fields=self._debug_report_pending_fields(),
            dig_cut_fields=self._debug_report_dig_cut_fields(),
            coverage_fields=self._debug_report_coverage_fields(),
            cell_entry_fields=self._debug_report_cell_entry_fields(),
            scripted_bootstrap_fields=self._debug_report_scripted_bootstrap_fields(),
            dig_progress_fields=self._debug_report_dig_progress_fields(),
            pre_dig_align_fields=self._debug_report_pre_dig_align_fields(),
        )

    def _debug_state_snapshot_for_report(self) -> PrimitiveDebugStateSnapshot:
        state = self._debug_state
        return PrimitiveDebugStateSnapshot(
            skill_name=str(state.skill_name),
            skill_id=int(state.skill_id),
            skill_switch_reason=str(state.skill_switch_reason),
            primitive_checkpoint_path=str(state.primitive_checkpoint_path),
            hybrid_mode=str(state.hybrid_mode),
            transition_timeout=bool(state.transition_timeout),
            transition_completed=bool(state.transition_completed),
            completed_transition_count=int(state.completed_transition_count),
            transition_timeout_count=int(state.transition_timeout_count),
            dump_ready_hold_count=int(state.dump_ready_hold_count),
            dump_done_hold_count=int(state.dump_done_hold_count),
            approach_ready_hold_count=int(state.approach_ready_hold_count),
            dump_release_ready_hold_count=int(state.dump_release_ready_hold_count),
            primitive_cycle_index=int(state.primitive_cycle_index),
        )

    def _token_status_for_debug_report(self) -> TokenStatus:
        return TokenStatus.from_inputs(
            cell_entry_enabled=bool(self.cell_entry_enabled),
            cell_entry_token_injected=bool(self._cell_entry_token_injected),
            cell_entry_token_dim=int(CELL_ENTRY_TOKEN_DIM),
            dig_cut_token_injected=bool(self._dig_cut_token_injected),
            dig_cut_token_dim=int(DIG_CUT_TOKEN_DIM),
            dig_cut_token_source=str(self._dig_cut_token_source),
            dig_cut_tokens=self._dig_cut_tokens,
            dig_cut_fallback_reason=str(self._dig_cut_fallback_reason),
            dig_cut_token_in_prior_p10_p90=bool(
                self._dig_cut_token_in_prior_p10_p90
            ),
            dig_depth_profile_token_injected=bool(
                self._dig_depth_profile_token_injected
            ),
            dig_depth_profile_token_dim=int(DIG_DEPTH_PROFILE_TOKEN_DIM),
            dig_depth_profile_source=str(self.dig_depth_profile_source),
            dig_depth_profile_required=bool(self.dig_depth_profile_required),
            dig_depth_profile_token_source=str(self._dig_depth_profile_token_source),
            dig_depth_profile_tokens=self._dig_depth_profile_tokens,
            dig_depth_profile_fallback_reason=str(
                self._dig_depth_profile_fallback_reason
            ),
            return_target_token_injected=bool(self._return_target_token_injected),
            return_target_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_target_token_source=str(self._return_target_token_source),
            return_target_tokens=self._return_target_tokens,
            return_target_fallback_reason=str(self._return_target_fallback_reason),
            return_relocate_token_injected=bool(self._return_relocate_token_injected),
            return_relocate_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_relocate_token_source=str(self._return_target_token_source),
            return_relocate_tokens=self._return_relocate_tokens,
            return_start_envelope_token_injected=bool(
                self._return_start_envelope_token_injected
            ),
            return_start_envelope_token_dim=int(RETURN_START_ENVELOPE_TOKEN_DIM),
            return_start_envelope_token_source=str(
                self._return_start_envelope_token_source
            ),
            return_start_envelope_tokens=self._return_start_envelope_tokens,
        )

    def _debug_report_return_fields(self) -> dict[str, Any]:
        return {
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
        }

    def _debug_report_pending_fields(self) -> dict[str, Any]:
        return {
            "pending_dig_cut_cycle_id": int(self._pending_dig_cut_cycle_id),
            "pending_dig_cut_corridor_id": int(self._pending_dig_cut_corridor_id),
        }

    def _debug_report_dig_cut_fields(self) -> dict[str, Any]:
        return {
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
        }

    def _debug_report_coverage_fields(self) -> dict[str, Any]:
        return {
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
        }

    def _debug_report_cell_entry_fields(self) -> dict[str, Any]:
        cell_goal = self._cell_entry_goal
        cell_audit = self._cell_entry_audit
        return {
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
        }

    def _debug_report_scripted_bootstrap_fields(self) -> dict[str, Any]:
        return {
            "scripted_bootstrap_step_count": int(self._scripted_bootstrap_step_count),
            "scripted_bootstrap_hold_count": int(self._scripted_bootstrap_hold_count),
            "scripted_bootstrap_timeout_count": int(
                self._scripted_bootstrap_timeout_count
            ),
        }

    def _debug_report_dig_progress_fields(self) -> dict[str, Any]:
        return {
            "dig_step_count": int(self._dig_step_count),
            "dig_best_mass_kg": float(self._dig_best_mass_kg),
            "dig_mass_plateau_count": int(self._dig_mass_plateau_count),
            "dig_to_carry_reason": str(self._dig_to_carry_reason),
            "dig_bad_replan_count": int(self._dig_bad_replan_count),
            "dig_exit_guard_replan_count": int(self._dig_exit_guard_replan_count),
        }

    def _debug_report_pre_dig_align_fields(self) -> dict[str, Any]:
        return {
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
        return self._rollout_summary_builder().build(
            self._rollout_summary_inputs()
        )

    @staticmethod
    def _rollout_summary_builder() -> PrimitiveRolloutSummaryBuilder:
        return PrimitiveRolloutSummaryBuilder()

    def _rollout_summary_inputs(self) -> PrimitiveRolloutSummaryInputs:
        return PrimitiveRolloutSummaryInputs(
            transition_source=TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            transition_policy_mode=TRANSITION_POLICY_MODE_PRIMITIVE,
            transition_fallback_count=0,
            transition_fallback_reason="",
            transition_timeout_count=int(self._transition_timeout_count),
            completed_transition_count=int(self._completed_transition_count),
            dump_done_use_boundary_event=bool(self.dump_done_use_boundary_event),
            primitive_final_skill=str(self._skill_name),
            primitive_cycle_index=int(self._cycle_index),
            cell_entry_enabled=bool(self.cell_entry_enabled),
            cell_entry_trace_count=int(len(self._cell_entry_trace)),
            dig_cut_token_dim=int(DIG_CUT_TOKEN_DIM),
            return_target_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_target_token_source=str(self._return_target_token_source),
            return_to_dig_max_entry_error_m=self.return_to_dig_max_entry_error_m,
            return_to_dig_entry_error_m=float(self._return_to_dig_entry_error_m),
            return_to_dig_entry_close=bool(self._return_to_dig_entry_close_state),
            return_next_dig_event_seen=bool(self._return_next_dig_event_seen),
            return_to_dig_start_envelope_gate_enabled=bool(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            return_to_dig_start_envelope_direct_handoff_enabled=bool(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            return_to_dig_start_envelope_ready=bool(
                self._return_to_dig_start_envelope_ready_state
            ),
            return_to_dig_start_envelope_plane_depth_mode=str(
                self.return_to_dig_start_envelope_plane_depth_mode
            ),
            return_to_dig_start_envelope_local_depth_tolerance_m=float(
                self.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            return_to_dig_start_envelope_error=float(
                self._return_to_dig_start_envelope_error
            ),
            pending_dig_cut_cycle_id=int(self._pending_dig_cut_cycle_id),
            pending_dig_cut_corridor_id=int(self._pending_dig_cut_corridor_id),
            dig_cut_token_injected=bool(self._dig_cut_token_injected),
            dig_cut_planner_mode=str(self.dig_cut_planner_mode),
            dig_cut_prior_id=str(self.dig_cut_prior_id),
            dig_cut_token_source=str(self._dig_cut_token_source),
            dig_cut_token_in_prior_p10_p90=bool(
                self._dig_cut_token_in_prior_p10_p90
            ),
            dig_cut_fallback_reason=str(self._dig_cut_fallback_reason),
            dig_failed_replan_next_skill=str(self.dig_failed_replan_next_skill),
            coverage_selected_corridor_id=int(self._coverage_active_corridor_id),
            coverage_depleted_count=int(self._coverage_depleted_count()),
            coverage_completed_dump_count=int(self._coverage_completed_dump_count),
            coverage_pass_index=int(self._coverage_pass_index),
            coverage_multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            coverage_use_env_removed_depth=bool(
                self.coverage_use_env_removed_depth
            ),
            coverage_candidate_layout=str(self.coverage_candidate_layout),
            coverage_first_dig_strategy=str(self.coverage_first_dig_strategy),
            coverage_first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            coverage_first_dig_max_entry_distance_m=(
                self.coverage_first_dig_max_entry_distance_m
            ),
            coverage_first_dig_qpos_delta_weight=float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            coverage_terminal_stop_requested=bool(
                self._coverage_terminal_stop_requested
            ),
            coverage_terminal_stop_reason=str(self._coverage_terminal_stop_reason),
            scripted_bootstrap_timeout_count=int(
                self._scripted_bootstrap_timeout_count
            ),
            pre_dig_align_enabled=bool(self.pre_dig_align_enabled),
            pre_dig_align_first_dig_only=bool(self.pre_dig_align_first_dig_only),
            pre_dig_align_replan_after_failed_dig=bool(
                self.pre_dig_align_replan_after_failed_dig
            ),
            pre_dig_align_surface_guard_enabled=bool(
                self.pre_dig_align_surface_guard_enabled
            ),
            pre_dig_align_surface_guard_count=int(
                self._pre_dig_align_surface_guard_count
            ),
            pre_dig_align_timeout_count=int(self._pre_dig_align_timeout_count),
            pre_dig_align_completed_count=int(self._pre_dig_align_completed_count),
            pre_dig_align_replan_count=int(self._pre_dig_align_replan_count),
            dig_bad_replan_count=int(self._dig_bad_replan_count),
            dig_exit_guard_replan_count=int(self._dig_exit_guard_replan_count),
        )

    def planner_trace(self) -> dict[str, object]:
        return self._planner_trace_builder().build(self._planner_trace_inputs())

    @staticmethod
    def _planner_trace_builder() -> PrimitivePlannerTraceBuilder:
        return PrimitivePlannerTraceBuilder()

    def _planner_trace_inputs(self) -> PrimitivePlannerTraceInputs:
        return PrimitivePlannerTraceInputs(
            cell_entry_trace=self._cell_entry_trace,
            dig_cut_planner_mode=str(self.dig_cut_planner_mode),
            dig_cut_prior_id=str(self.dig_cut_prior_id),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            return_target_planner_enabled=bool(self.return_target_planner_enabled),
            coverage_use_env_removed_depth=bool(
                self.coverage_use_env_removed_depth
            ),
            coverage_candidate_layout=str(self.coverage_candidate_layout),
            coverage_first_dig_strategy=str(self.coverage_first_dig_strategy),
            coverage_pass_index=int(self._coverage_pass_index),
            coverage_multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            coverage_multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            coverage_multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
            coverage_first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            coverage_corridors=[
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ],
            coverage_decision_trace=self._coverage_decision_trace,
            coverage_terminal_stop_requested=bool(
                self._coverage_terminal_stop_requested
            ),
            coverage_terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        skill_before = str(self._skill_name)
        result = self._decision_runtime().decide_legacy_compatibility_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=skill_before,
                dig_progress_updated=skill_before == "dig",
            ),
        )
        if result is None or result.side_effects_applied:
            return
        self._apply_requested_tick_effects(obs, result.effects)

    def _maybe_handle_pre_dig_align_skill(self, obs: dict) -> bool:
        if self._skill_name != PRE_DIG_ALIGN_SKILL_NAME:
            return False
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
        return True

    def _set_return_or_direct_handoff(self, obs: dict, *, reason: str) -> None:
        self._return_direct_handoff_effect_service().apply(obs, reason=reason)

    def _try_return_direct_handoff_at_current_obs(self, obs: dict) -> bool:
        result = self._return_direct_handoff_effect_service().try_direct_handoff(obs)
        return bool(result.direct_handoff_applied)

    def _return_direct_handoff_effect_service(
        self,
    ) -> ReturnDirectHandoffEffectService:
        return ReturnDirectHandoffEffectService(
            ports=self._return_direct_handoff_effect_ports()
        )

    def _return_direct_handoff_effect_ports(
        self,
    ) -> ReturnDirectHandoffEffectPorts:
        return ReturnDirectHandoffEffectPorts(
            current_skill_name=lambda: str(self._skill_name),
            set_skill=lambda skill, reason: self._set_skill(skill, reason),
            return_target_planner_enabled=self.return_target_planner_enabled,
            return_to_dig_start_envelope_direct_handoff_enabled=(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            ensure_return_target_plan_for_cycle=(
                lambda obs: self._ensure_return_target_plan_for_cycle(obs)
            ),
            return_to_dig_handoff_ready=(
                lambda obs: self._return_to_dig_handoff_ready(obs)
            ),
            return_to_dig_direct_handoff_ready=(
                lambda obs, *, handoff_ready: self._return_to_dig_direct_handoff_ready(
                    obs,
                    handoff_ready=handoff_ready,
                )
            ),
            complete_return_transition=(
                lambda: self._complete_return_transition_for_backend()
            ),
            next_skill_after_return_transition=(
                lambda: self._next_skill_after_return_transition()
            ),
        )

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
        result = self._return_start_envelope_gate_service().evaluate(
            self._return_start_envelope_gate_inputs(obs)
        )
        self._apply_return_start_envelope_gate_result(result)
        return bool(result.ready)

    def _return_start_envelope_gate_service(self) -> ReturnStartEnvelopeGateService:
        return ReturnStartEnvelopeGateService(
            config=self._return_start_envelope_gate_config()
        )

    def _return_start_envelope_gate_config(self) -> ReturnStartEnvelopeGateConfig:
        return ReturnStartEnvelopeGateConfig(
            enabled=self.return_to_dig_start_envelope_gate_enabled,
            action_dim=self.action_dim,
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

    def _return_start_envelope_gate_inputs(
        self,
        obs: dict,
    ) -> ReturnStartEnvelopeGateInputs:
        corridor_id = int(self._pending_dig_cut_corridor_id)
        return ReturnStartEnvelopeGateInputs(
            token=self._return_start_envelope_tokens,
            env_state=self._env_state(obs),
            qpos=np.asarray(
                obs.get("qpos", np.zeros(self.action_dim)),
                dtype=np.float32,
            ).reshape(-1),
            prior_bounds=lambda: self._return_start_envelope_prior_bounds(corridor_id),
            prior_mapping=(
                lambda: self._return_start_envelope_prior_mapping(
                    corridor_id=corridor_id,
                )[0]
            ),
            use_prior_spatial_bounds=self._return_start_envelope_use_prior_spatial_bounds,
            use_prior_qpos_bounds=self._return_start_envelope_use_prior_qpos_bounds,
        )

    def _apply_return_start_envelope_gate_result(
        self,
        result: ReturnStartEnvelopeGateResult,
    ) -> None:
        self._return_to_dig_start_envelope_ready_state = bool(result.ready)
        self._return_to_dig_start_envelope_error = float(result.error)
        self._return_to_dig_start_envelope_checks = dict(result.checks)

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
        self._clear_policy_observation_injected_flags()
        result = self._policy_observation_assembler().assemble(obs)
        self._apply_policy_observation_assembly(result)
        return result.policy_obs

    def _policy_observation_assembler(self) -> PrimitivePolicyObservationAssembler:
        return PrimitivePolicyObservationAssembler.from_ports(
            self._policy_observation_assembler_ports()
        )

    def _policy_observation_assembler_ports(
        self,
    ) -> PrimitivePolicyObservationAssemblerPorts:
        return PrimitivePolicyObservationAssemblerPorts(
            goal_tokens=lambda: self._goal_tokens(),
            cell_entry_tokens=lambda obs: self._cell_entry_tokens_for_obs(obs),
            dig_cut_tokens=lambda obs: self._dig_cut_tokens_for_obs(obs),
            dig_depth_profile_tokens=(
                lambda obs: self._dig_depth_profile_tokens_for_obs(obs)
            ),
            return_target_tokens=lambda obs: self._return_target_tokens_for_obs(obs),
            return_relocate_tokens=(
                lambda obs: self._return_relocate_tokens_for_obs(obs)
            ),
            return_start_envelope_tokens=(
                lambda obs: self._return_start_envelope_tokens_for_obs(obs)
            ),
        )

    def _clear_policy_observation_injected_flags(self) -> None:
        self._cell_entry_token_injected = False
        self._dig_cut_token_injected = False
        self._dig_depth_profile_token_injected = False
        self._return_target_token_injected = False
        self._return_relocate_token_injected = False
        self._return_start_envelope_token_injected = False

    def _apply_policy_observation_assembly(
        self,
        result: PrimitivePolicyObservationAssemblyResult,
    ) -> None:
        state = result.token_injection_state
        self._cell_entry_token_injected = bool(state.cell_entry_token_injected)
        self._dig_cut_token_injected = bool(state.dig_cut_token_injected)
        self._dig_depth_profile_token_injected = bool(
            state.dig_depth_profile_token_injected
        )
        self._return_target_token_injected = bool(state.return_target_token_injected)
        self._return_relocate_token_injected = bool(
            state.return_relocate_token_injected
        )
        self._return_start_envelope_token_injected = bool(
            state.return_start_envelope_token_injected
        )

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

    def _coverage_selection_runtime_ports(self) -> CoverageSelectionRuntimePorts:
        return CoverageSelectionRuntimePorts(
            dig_cut_prior=lambda: dict(self.dig_cut_prior or {}),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            coverage_corridors=lambda: self._coverage_corridors,
            set_coverage_corridors=self._set_coverage_corridors,
            candidate_builder=lambda: self._coverage_candidate_builder(),
            selection_service=lambda: self._coverage_selection_service(),
            selection_facts=(
                lambda obs, corridors: self._coverage_selection_facts(
                    obs,
                    corridors,
                )
            ),
            recent_row_reference=lambda: self._coverage_recent_row_reference_corridor(),
            all_depleted=lambda: self._coverage_all_depleted(),
            maybe_reopen_pass=(
                lambda obs, reason: self._maybe_reopen_coverage_pass(
                    obs,
                    reason=reason,
                )
            ),
            request_terminal_stop=lambda reason: self._request_coverage_terminal_stop(
                reason
            ),
            set_candidate_scores=self._set_coverage_candidate_scores,
            record_decision_event=self._record_coverage_decision_event,
            set_active_corridor_id=self._set_coverage_active_corridor_id,
            set_last_selected_corridor_id=self._set_coverage_last_selected_corridor_id,
        )

    def _coverage_selection_runtime_coordinator(
        self,
    ) -> CoverageSelectionRuntimeCoordinator:
        return CoverageSelectionRuntimeCoordinator.from_ports(
            self._coverage_selection_runtime_ports()
        )

    def _set_coverage_corridors(
        self,
        corridors: list[CoverageCorridorState],
    ) -> None:
        self._coverage_runtime_state().set_coverage_corridors(corridors)

    def _set_coverage_candidate_scores(
        self,
        candidate_scores: list[dict[str, Any]],
    ) -> None:
        self._coverage_runtime_state().set_candidate_scores(candidate_scores)

    def _set_coverage_last_selected_corridor_id(self, value: int) -> None:
        self._coverage_runtime_state().set_last_selected_corridor_id(value)

    def _select_next_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        return self._coverage_selection_runtime_coordinator().select_next_corridor(
            obs
        )

    def _ensure_coverage_corridors(self) -> None:
        self._coverage_selection_runtime_coordinator().ensure_corridors()

    def _build_cell_weighted_coverage_corridors(
        self,
        fields: dict[str, object],
    ) -> list[CoverageCorridorState]:
        prior = dict(self.dig_cut_prior or {})
        prior["fields"] = dict(fields)
        return self._coverage_candidate_builder(
            candidate_layout="cell_weighted_3x2"
        ).build(prior)

    @staticmethod
    def _coverage_cell_float(
        mapping: dict[str, object],
        name: str,
        default: float,
    ) -> float:
        return CoverageCandidateBuilder._cell_float(mapping, name, default)

    @classmethod
    def _coverage_stat_float(
        cls,
        mapping: dict[str, object],
        section: str,
        name: str,
        default: float,
    ) -> float:
        return CoverageCandidateBuilder._stat_float(mapping, section, name, default)

    def _coverage_exit_from_entry(self, entry_x: float, entry_z: float) -> tuple[float, float]:
        return self._coverage_candidate_builder()._exit_from_entry(
            dict(self.dig_cut_prior.get("fields", {})),
            entry_x,
            entry_z,
        )

    def _coverage_selection_config(self) -> CoverageSelectionConfig:
        return CoverageSelectionConfig(
            candidate_layout=str(self.coverage_candidate_layout),
            prior_fields=dict(self.dig_cut_prior.get("fields", {})),
            cut_depth_percentile=str(self.coverage_cut_depth_percentile),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            max_attempts_per_corridor=int(self.coverage_max_attempts_per_corridor),
            recent_selection_penalty=float(self.coverage_recent_selection_penalty),
            unattempted_bonus=float(self.coverage_unattempted_bonus),
            attempt_penalty=float(self.coverage_attempt_penalty),
            cell_confidence_weight=float(self.coverage_cell_confidence_weight),
            rare_cell_source_fraction_threshold=float(
                self.coverage_rare_cell_source_fraction_threshold
            ),
            rare_cell_max_attempts=int(self.coverage_rare_cell_max_attempts),
            recent_row_selection_penalty=float(
                self.coverage_recent_row_selection_penalty
            ),
            last_selected_corridor_id=int(self._coverage_last_selected_corridor_id),
            cycle_index=int(self._cycle_index),
            completed_dump_count=int(self._coverage_completed_dump_count),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            first_dig_preferred_bonus=float(
                self.coverage_first_dig_preferred_bonus
            ),
            first_dig_proximity_weight=float(
                self.coverage_first_dig_proximity_weight
            ),
            first_dig_max_entry_distance_m=(
                None
                if self.coverage_first_dig_max_entry_distance_m is None
                else float(self.coverage_first_dig_max_entry_distance_m)
            ),
            first_dig_qpos_delta_weight=float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            first_dig_max_qpos_delta=(
                None
                if self.coverage_first_dig_max_qpos_delta is None
                else self.coverage_first_dig_max_qpos_delta.astype(np.float32).copy()
            ),
            pre_dig_align_controlled_dims=self.pre_dig_align_controlled_dims.astype(
                bool
            ).copy(),
            state_exemplars_enabled=bool(self.coverage_state_exemplars_enabled),
            state_exemplar_score_weight=float(
                self.coverage_state_exemplar_score_weight
            ),
        )

    def _coverage_selection_service(self) -> CoverageSelectionService:
        return CoverageSelectionService(self._coverage_selection_config())

    def _coverage_selection_facts(
        self,
        obs: dict,
        corridors: list[CoverageCorridorState] | None = None,
    ) -> dict[int, CoverageCandidateSelectionFacts]:
        facts: dict[int, CoverageCandidateSelectionFacts] = {}
        for corridor in list(self._coverage_corridors if corridors is None else corridors):
            facts[int(corridor.corridor_id)] = CoverageCandidateSelectionFacts(
                remaining_depth_m=float(
                    self._coverage_remaining_depth_for_corridor(obs, corridor)
                ),
                first_dig_entry_distance_m=float(
                    self._coverage_entry_distance_m(corridor, obs)
                ),
                first_dig_qpos_delta=self._coverage_first_dig_qpos_delta(
                    corridor,
                    obs,
                ),
                state_exemplar_distance=float(
                    self._coverage_state_exemplar_distance(corridor, obs)
                ),
                state_exemplar_id=str(self._coverage_state_exemplar_id(corridor, obs)),
            )
        return facts

    def _select_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        return self._coverage_selection_runtime_coordinator().select_corridor(obs)

    def _coverage_first_dig_active(self) -> bool:
        return self._coverage_selection_service().first_dig_active()

    def _coverage_first_dig_gate_available(self, obs: dict) -> bool:
        return self._coverage_selection_service().first_dig_gate_available(
            self._coverage_corridors,
            facts_by_corridor_id=self._coverage_selection_facts(obs),
        )

    def _coverage_first_dig_entry_reachable(self, distance: float) -> bool:
        return self._coverage_selection_service().first_dig_entry_reachable(distance)

    def _coverage_score(
        self,
        corridor: CoverageCorridorState,
        remaining_depth_m: float,
        *,
        obs: dict | None = None,
    ) -> float:
        return self._coverage_selection_service().score(
            corridor,
            remaining_depth_m,
            state_exemplar_distance=(
                float("nan")
                if obs is None
                else self._coverage_state_exemplar_distance(corridor, obs)
            ),
            recent_row_reference=self._coverage_recent_row_reference_corridor(),
        )

    def _coverage_cell_confidence(self, corridor: CoverageCorridorState) -> float:
        return self._coverage_selection_service().cell_confidence(corridor)

    def _coverage_corridor_is_rare(self, corridor: CoverageCorridorState) -> bool:
        return self._coverage_selection_service().corridor_is_rare(corridor)

    def _coverage_corridor_attempt_limit(self, corridor: CoverageCorridorState) -> int:
        return self._coverage_selection_service().corridor_attempt_limit(corridor)

    def _coverage_rare_first_dig_gated_out(
        self,
        corridor: CoverageCorridorState,
    ) -> bool:
        return self._coverage_selection_service().rare_first_dig_gated_out(
            corridor,
            self._coverage_corridors,
        )

    def _coverage_recent_row_penalty(self, corridor: CoverageCorridorState) -> float:
        return self._coverage_selection_service().recent_row_penalty(
            corridor,
            recent_row_reference=self._coverage_recent_row_reference_corridor(),
        )

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
        return self._coverage_selection_service().first_dig_bonus(
            corridor,
            CoverageCandidateSelectionFacts(
                remaining_depth_m=float("nan"),
                first_dig_entry_distance_m=float(
                    self._coverage_entry_distance_m(corridor, obs)
                ),
                first_dig_qpos_delta=self._coverage_first_dig_qpos_delta(
                    corridor,
                    obs,
                ),
            ),
        )

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
        return self._coverage_selection_service().first_dig_qpos_reachable(delta)

    def _coverage_first_dig_qpos_delta_penalty(self, delta: np.ndarray) -> float:
        return self._coverage_selection_service().first_dig_qpos_delta_penalty(delta)

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

    def _coverage_state_exemplar_planner_config(
        self,
    ) -> CoverageStateExemplarPlannerConfig:
        return CoverageStateExemplarPlannerConfig(
            enabled=bool(self.coverage_state_exemplars_enabled),
            path=str(self.coverage_state_exemplar_path),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            k=int(self.coverage_state_exemplar_k),
            removed_depth_scale_m=float(
                self.coverage_state_exemplar_removed_depth_scale_m
            ),
            target_cell_weight=float(self.coverage_state_exemplar_target_cell_weight),
            temperature=float(self.coverage_state_exemplar_temperature),
            skip_rejected=bool(self.coverage_state_exemplar_skip_rejected),
        )

    def _coverage_state_exemplar_planner(self) -> CoverageStateExemplarPlanner:
        return CoverageStateExemplarPlanner(
            self._coverage_state_exemplar_planner_config()
        )

    def _load_coverage_state_exemplars(self) -> dict[int, list[dict[str, Any]]]:
        return self._coverage_state_exemplar_planner().load_exemplars()

    def _coverage_state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
        *,
        update_state: bool,
    ) -> dict[str, object] | None:
        result = self._coverage_state_exemplar_planner().plan(
            CoverageStateExemplarPlanInputs(
                corridor=corridor,
                env_state=self._env_state(obs),
                exemplars_by_cell=self.coverage_state_exemplars_by_cell,
                rejected_exemplar_ids=self._coverage_rejected_state_exemplar_ids,
            )
        )
        if result is None:
            return None
        if update_state:
            self._coverage_runtime_state().set_active_state_exemplar(
                exemplar_ids=list(result.exemplar_ids),
                distance=float(result.distance),
                profile_token=(
                    None
                    if result.profile_token is None
                    else result.profile_token.astype(np.float32).copy()
                ),
            )
            corridor.state_exemplar_id = ",".join(result.exemplar_ids)
            corridor.state_exemplar_distance = float(result.distance)
        return {
            "raw_fields": dict(result.raw_fields),
            "profile_token": result.profile_token,
            "exemplar_ids": list(result.exemplar_ids),
            "distance": float(result.distance),
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
        return self._coverage_state_exemplar_planner().removed_depth_grid(
            self._env_state(obs)
        )

    def _coverage_state_exemplar_distance_for_grid(
        self,
        removed_grid: np.ndarray,
        exemplar: dict[str, Any],
        *,
        cell_id: int,
    ) -> float:
        return self._coverage_state_exemplar_planner().distance_for_grid(
            removed_grid,
            exemplar,
            cell_id=cell_id,
        )

    def _state_exemplar_weights(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray:
        return self._coverage_state_exemplar_planner().weights(selected)

    def _weighted_state_exemplar_raw_fields(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> dict[str, float | int]:
        return self._coverage_state_exemplar_planner().weighted_raw_fields(selected)

    def _weighted_state_exemplar_profile_token(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray | None:
        return self._coverage_state_exemplar_planner().weighted_profile_token(
            selected
        )

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
        return CoverageSelectionService.cell_id(corridor)

    def _coverage_corridor_row_id(self, corridor: CoverageCorridorState) -> int:
        return CoverageSelectionService.corridor_row_id(corridor)

    @staticmethod
    def _coverage_cell_id_from_percentile_indices(
        *,
        x_index: int,
        x_count: int,
        z_index: int,
        z_count: int,
    ) -> int:
        return CoverageCandidateBuilder.cell_id_from_percentile_indices(
            x_index=x_index,
            x_count=x_count,
            z_index=z_index,
            z_count=z_count,
        )

    def _coverage_update_config(self) -> CoverageUpdateConfig:
        return CoverageUpdateConfig(
            prior_fields=dict(self.dig_cut_prior.get("fields", {})),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            low_productivity_payload_kg=float(
                self.coverage_low_productivity_payload_kg
            ),
            low_productivity_deposit_kg=float(
                self.coverage_low_productivity_deposit_kg
            ),
            deplete_after_low_streak=int(self.coverage_deplete_after_low_streak),
            min_remaining_depth_m=float(self.coverage_min_remaining_depth_m),
            belief_depleted_score=float(self.coverage_belief_depleted_score),
            belief_gain_scale=float(self.coverage_belief_gain_scale),
        )

    def _coverage_update_service(self) -> CoverageUpdateService:
        return CoverageUpdateService(self._coverage_update_config())

    def _coverage_runtime_config(self) -> CoverageRuntimeConfig:
        return CoverageRuntimeConfig(
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
        )

    def _coverage_runtime_service(self) -> CoverageRuntimeService:
        return CoverageRuntimeService(self._coverage_runtime_config())

    def _coverage_effect_runtime_ports(self) -> CoverageEffectRuntimePorts:
        return CoverageEffectRuntimePorts(
            coverage_mode=lambda: str(self.dig_cut_planner_mode),
            coverage_update_service=lambda: self._coverage_update_service(),
            coverage_runtime_service=lambda: self._coverage_runtime_service(),
            coverage_corridors=lambda: self._coverage_corridors,
            active_corridor=lambda: self._coverage_active_corridor(),
            current_payload_gain_kg=lambda: float(
                self._coverage_current_payload_gain_kg
            ),
            set_current_payload_gain_kg=self._set_coverage_current_payload_gain_kg,
            mass_in_bucket=lambda obs: self._mass_in_bucket(obs),
            completion_facts=(
                lambda obs, corridor, reason: self._coverage_completion_facts(
                    obs,
                    corridor,
                    reason=reason,
                )
            ),
            rejection_facts=(
                lambda obs, corridor, reason: self._coverage_rejection_facts(
                    obs,
                    corridor,
                    reason=reason,
                )
            ),
            reopen_facts=(
                lambda obs, corridors, reason: self._coverage_reopen_facts(
                    obs,
                    corridors,
                    reason=reason,
                )
            ),
            terminal_facts=(
                lambda reason, replace: self._coverage_terminal_facts(
                    reason,
                    replace=replace,
                )
            ),
            set_last_payload_gain_kg=self._set_coverage_last_payload_gain_kg,
            set_last_effective_deposit_delta_kg=(
                self._set_coverage_last_effective_deposit_delta_kg
            ),
            set_completed_dump_count=self._set_coverage_completed_dump_count,
            set_global_low_productivity_streak=(
                self._set_coverage_global_low_productivity_streak
            ),
            update_rejected_state_exemplar_ids=(
                self._update_coverage_rejected_state_exemplar_ids
            ),
            set_coverage_pass_index=self._set_coverage_pass_index,
            set_active_corridor_id=self._set_coverage_active_corridor_id,
            clear_rejected_state_exemplar_ids=(
                self._clear_coverage_rejected_state_exemplar_ids
            ),
            set_terminal_stop_requested=self._set_coverage_terminal_stop_requested,
            set_terminal_stop_reason=self._set_coverage_terminal_stop_reason,
            record_decision_event=self._record_coverage_decision_event,
            coverage_global_low_productivity_stop=lambda: int(
                self.coverage_global_low_productivity_stop
            ),
            coverage_low_productivity_payload_kg=lambda: float(
                self.coverage_low_productivity_payload_kg
            ),
            coverage_low_productivity_deposit_kg=lambda: float(
                self.coverage_low_productivity_deposit_kg
            ),
        )

    def _coverage_effect_runtime_coordinator(
        self,
    ) -> CoverageEffectRuntimeCoordinator:
        return CoverageEffectRuntimeCoordinator.from_ports(
            self._coverage_effect_runtime_ports()
        )

    def _set_coverage_current_payload_gain_kg(self, value: float) -> None:
        self._coverage_runtime_state().set_current_payload_gain_kg(value)

    def _set_coverage_last_payload_gain_kg(self, value: float) -> None:
        self._coverage_runtime_state().set_last_payload_gain_kg(value)

    def _set_coverage_last_effective_deposit_delta_kg(self, value: float) -> None:
        self._coverage_runtime_state().set_last_effective_deposit_delta_kg(value)

    def _set_coverage_completed_dump_count(self, value: int) -> None:
        self._coverage_runtime_state().set_completed_dump_count(value)

    def _set_coverage_global_low_productivity_streak(self, value: int) -> None:
        self._coverage_runtime_state().set_global_low_productivity_streak(value)

    def _update_coverage_rejected_state_exemplar_ids(
        self,
        exemplar_ids: tuple[str, ...],
    ) -> None:
        self._coverage_runtime_state().update_rejected_state_exemplar_ids(exemplar_ids)

    def _set_coverage_pass_index(self, value: int) -> None:
        self._coverage_runtime_state().set_coverage_pass_index(value)

    def _set_coverage_active_corridor_id(self, value: int) -> None:
        self._coverage_runtime_state().set_active_corridor_id(value)

    def _clear_coverage_rejected_state_exemplar_ids(self) -> None:
        self._coverage_runtime_state().clear_rejected_state_exemplar_ids()

    def _set_coverage_terminal_stop_requested(self, value: bool) -> None:
        self._coverage_runtime_state().set_terminal_stop_requested(value)

    def _set_coverage_terminal_stop_reason(self, value: str) -> None:
        self._coverage_runtime_state().set_terminal_stop_reason(value)

    def _coverage_reopen_facts(
        self,
        obs: dict,
        corridors: list[CoverageCorridorState] | None = None,
        *,
        reason: str,
    ) -> CoverageReopenFacts:
        target_corridors = list(
            self._coverage_corridors if corridors is None else corridors
        )
        return CoverageReopenFacts(
            reason=str(reason),
            pass_index=int(self._coverage_pass_index),
            terminal_stop_requested=bool(self._coverage_terminal_stop_requested),
            remaining_depth_by_corridor_id={
                int(corridor.corridor_id): float(
                    self._coverage_remaining_depth_for_corridor(obs, corridor)
                )
                for corridor in target_corridors
            },
        )

    def _coverage_terminal_facts(
        self,
        reason: str,
        *,
        replace: bool,
    ) -> CoverageTerminalFacts:
        return CoverageTerminalFacts(
            reason=str(reason),
            replace=bool(replace),
            terminal_stop_requested=bool(self._coverage_terminal_stop_requested),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )

    def _coverage_completion_facts(
        self,
        obs: dict,
        corridor: CoverageCorridorState,
        *,
        reason: str,
    ) -> CoverageCompletionFacts:
        return CoverageCompletionFacts(
            payload_gain_kg=max(float(self._coverage_current_payload_gain_kg), 0.0),
            effective_deposit_delta_kg=max(
                0.0,
                self._deposited_mass(obs)
                - float(self._coverage_cycle_start_deposit_kg),
            ),
            remaining_depth_m=float(
                self._coverage_remaining_depth_for_corridor(obs, corridor)
            ),
            reason=str(reason),
            attempt_limit=int(self._coverage_corridor_attempt_limit(corridor)),
            completed_dump_count=int(self._coverage_completed_dump_count),
            global_low_productivity_streak=int(
                self._coverage_global_low_productivity_streak
            ),
        )

    def _coverage_rejection_facts(
        self,
        obs: dict,
        corridor: CoverageCorridorState,
        *,
        reason: str,
    ) -> CoverageRejectionFacts:
        return CoverageRejectionFacts(
            payload_gain_kg=max(
                float(self._coverage_current_payload_gain_kg),
                float(self._dig_best_mass_kg),
                self._mass_in_bucket(obs),
                0.0,
            ),
            effective_deposit_delta_kg=max(
                0.0,
                self._deposited_mass(obs)
                - float(self._coverage_cycle_start_deposit_kg),
            ),
            remaining_depth_m=float(
                self._coverage_remaining_depth_for_corridor(obs, corridor)
            ),
            reason=str(reason),
            attempt_limit=int(self._coverage_corridor_attempt_limit(corridor)),
            global_low_productivity_streak=int(
                self._coverage_global_low_productivity_streak
            ),
            active_state_exemplar_ids=tuple(
                str(exemplar_id)
                for exemplar_id in self._coverage_active_state_exemplar_ids
            ),
        )

    def _complete_coverage_dig(self, obs: dict) -> None:
        self._coverage_effect_runtime_coordinator().complete_dig(obs)

    def _complete_coverage_dump(self, obs: dict, *, reason: str) -> None:
        self._coverage_effect_runtime_coordinator().complete_dump(obs, reason=reason)

    def _reject_active_coverage_corridor(self, obs: dict, *, reason: str) -> None:
        self._coverage_effect_runtime_coordinator().reject_active_corridor(
            obs,
            reason=reason,
        )

    def _update_corridor_belief(
        self,
        corridor: CoverageCorridorState,
        *,
        payload_gain_kg: float,
        effective_deposit_delta_kg: float,
    ) -> None:
        self._coverage_update_service().update_belief(
            corridor,
            payload_gain_kg=payload_gain_kg,
            effective_deposit_delta_kg=effective_deposit_delta_kg,
        )

    @staticmethod
    def _coverage_report_service() -> CoverageReportService:
        return CoverageReportService()

    def _coverage_report_state(self) -> CoverageReportState:
        return CoverageReportState(
            cycle_index=int(self._cycle_index),
            skill_name=str(self._skill_name),
            active_corridor_id=int(self._coverage_active_corridor_id),
            last_selected_corridor_id=int(self._coverage_last_selected_corridor_id),
            last_selected_cell_id=int(
                self._coverage_corridor_cell_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            last_selected_row_id=int(
                self._coverage_corridor_row_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            depleted_count=int(self._coverage_depleted_count()),
            pass_index=int(self._coverage_pass_index),
            global_low_productivity_streak=int(
                self._coverage_global_low_productivity_streak
            ),
            terminal_stop_requested=bool(self._coverage_terminal_stop_requested),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )

    def _coverage_bucket_snapshot(self, obs: dict) -> CoverageBucketSnapshot:
        env_state = self._env_state(obs)
        return CoverageBucketSnapshot(
            mass_kg=float(self._mass_in_bucket(obs)),
            deposited_mass_kg=float(self._deposited_mass(obs)),
            dig_area_x_m=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
            ),
            dig_area_y_m=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
            ),
            dig_area_z_m=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
            ),
            long_norm=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
            ),
            short_norm=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
            ),
            plane_depth_m=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
            ),
            local_depth_m=self._env_state_value(
                env_state,
                ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
            ),
        )

    def _record_coverage_decision_event(
        self,
        event: str,
        *,
        obs: dict | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._coverage_decision_trace.append(
            self._coverage_report_service().decision_event(
                str(event),
                state=self._coverage_report_state(),
                corridor=(
                    None
                    if corridor is None
                    else self._coverage_corridor_to_debug(corridor)
                ),
                bucket=None if obs is None else self._coverage_bucket_snapshot(obs),
                extra=dict(extra or {}),
            )
        )

    @staticmethod
    def _env_state_value(env_state: np.ndarray, index: int) -> float:
        if len(env_state) <= int(index):
            return float("nan")
        return float(env_state[int(index)])

    def _coverage_all_depleted(self) -> bool:
        return self._coverage_runtime_state().all_depleted()

    def _maybe_reopen_coverage_pass(self, obs: dict, *, reason: str) -> bool:
        return self._coverage_effect_runtime_coordinator().maybe_reopen_pass(
            obs,
            reason=reason,
        )

    def _request_coverage_terminal_stop(
        self,
        reason: str,
        *,
        replace: bool = False,
    ) -> None:
        self._coverage_effect_runtime_coordinator().request_terminal_stop(
            reason,
            replace=replace,
        )

    def _coverage_active_corridor(self) -> CoverageCorridorState | None:
        return self._coverage_runtime_state().active_corridor()

    def _coverage_corridor_by_id(
        self,
        corridor_id: int,
    ) -> CoverageCorridorState | None:
        return self._coverage_runtime_state().corridor_by_id(corridor_id)

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
        return self._coverage_runtime_state().depleted_count()

    def _coverage_corridor_to_debug(
        self,
        corridor: CoverageCorridorState,
    ) -> dict[str, float | int | str]:
        return self._coverage_report_service().corridor_to_debug(
            corridor,
            attempt_limit=self._coverage_corridor_attempt_limit(corridor),
            cell_confidence=self._coverage_cell_confidence(corridor),
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
        self._coverage_runtime_state().clear_active_state_exemplar()

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

    def _coverage_candidate_builder(
        self,
        *,
        candidate_layout: str | None = None,
    ) -> CoverageCandidateBuilder:
        return CoverageCandidateBuilder(
            candidate_layout=str(candidate_layout or self.coverage_candidate_layout),
            entry_x_percentiles=tuple(self.coverage_entry_x_percentiles),
            entry_z_percentiles=tuple(self.coverage_entry_z_percentiles),
            cut_direction_percentile=str(self.coverage_cut_direction_percentile),
            cut_length_percentile=str(self.coverage_cut_length_percentile),
            cut_depth_percentile=str(self.coverage_cut_depth_percentile),
            payload_percentile=str(self.coverage_payload_percentile),
        )

    @staticmethod
    def _normalize_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | None,
    ) -> tuple[int, ...]:
        return GoalTokenProvider.normalize_goal_sequence(goal_sequence)

    def _active_policy(self) -> Policy:
        return self._action_dispatch_service().active_policy()

    def _all_policies(self) -> list[Policy]:
        return self._action_dispatch_service().all_policies()

    def _first_dig_policy_active(self) -> bool:
        return self._action_dispatch_service().first_dig_policy_active()

    def _make_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitivePlannerDebugState:
        return self._tick_finalization_service().make_debug_state(
            self._tick_finalization_inputs(
                transition_timeout=transition_timeout,
                transition_completed=transition_completed,
            )
        )

    def _tick_finalization_inputs(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitiveTickFinalizationInputs:
        return PrimitiveTickFinalizationInputs(
            skill_name=str(self._skill_name),
            skill_ids=PRIMITIVE_SKILL_IDS,
            skill_switch_reason=str(self._switch_reason),
            primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            first_dig_policy_active=bool(self._first_dig_policy_active()),
            transition_skill_names=("return", PRE_DIG_ALIGN_SKILL_NAME),
            transition_timeout=bool(transition_timeout),
            transition_completed=bool(transition_completed),
            completed_transition_count=int(self._completed_transition_count),
            transition_timeout_count=int(self._transition_timeout_count),
            dump_ready_hold_count=int(self._dump_ready_hold_count),
            dump_done_hold_count=int(self._dump_done_hold_count),
            primitive_cycle_index=int(self._cycle_index),
            work_hybrid_mode=HYBRID_MODE_WORK,
            transition_hybrid_mode=HYBRID_MODE_TRANSITION,
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

    def _action_dispatch_ports(self) -> PrimitiveActionDispatchPorts:
        return PrimitiveActionDispatchPorts(
            current_skill_name=lambda: str(self._skill_name),
            action_dim=int(self.action_dim),
            skill_policies={
                "dig": self.dig_policy,
                "carry": self.carry_policy,
                "approach_dump": self.approach_dump_policy,
                "dump_release": self.dump_release_policy,
                "return": self.return_policy,
            },
            base_policy_order=(
                "dig",
                "carry",
                "approach_dump",
                "dump_release",
                "return",
            ),
            optional_policy_order=("bootstrap", "first_dig"),
            first_dig_policy=self.first_dig_policy,
            bootstrap_policy=self.bootstrap_policy,
            cycle_index=lambda: int(getattr(self, "_cycle_index", 0)),
            coverage_completed_dump_count=lambda: int(
                getattr(self, "_coverage_completed_dump_count", 0)
            ),
            policy_observation=lambda obs: self._policy_obs(obs),
            scripted_bootstrap_enabled=lambda: self._scripted_bootstrap_enabled(),
            scripted_bootstrap_action=lambda obs: self._scripted_bootstrap_action(obs),
            pre_dig_align_action=lambda obs: self._pre_dig_align_action(obs),
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            dig_skill_name="dig",
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
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

    def _tick_finalization_inputs(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitiveTickFinalizationInputs:
        return PrimitiveTickFinalizationInputs(
            skill_name=str(self._skill_name),
            skill_ids=PRIMITIVE_SKILL_IDS_5P,
            skill_switch_reason=str(self._switch_reason),
            primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            first_dig_policy_active=bool(self._first_dig_policy_active()),
            transition_skill_names=("return",),
            transition_timeout=bool(transition_timeout),
            transition_completed=bool(transition_completed),
            completed_transition_count=int(self._completed_transition_count),
            transition_timeout_count=int(self._transition_timeout_count),
            dump_ready_hold_count=int(self._dump_release_ready_hold_count),
            dump_done_hold_count=int(self._dump_done_hold_count),
            primitive_cycle_index=int(self._cycle_index),
            work_hybrid_mode=HYBRID_MODE_WORK,
            transition_hybrid_mode=HYBRID_MODE_TRANSITION,
            approach_ready_hold_count=int(self._approach_ready_hold_count),
            dump_release_ready_hold_count=int(self._dump_release_ready_hold_count),
        )
