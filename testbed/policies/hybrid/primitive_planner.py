"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

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
    PlannerDecisionAudit,
    PrimitiveCycleOutcome,
    build_cell_entry_tokens,
)
from testbed.planner.primitive_backend import (
    LegacyFSMBranchPorts,
    LegacyFSMBranchSet,
    LegacyFSMCompatibilityDecisionBackend,
    LegacyFSMDecisionBackendFactory,
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
from testbed.planner.primitive_cell_entry_state import (
    PrimitiveCellEntryCompatibilityRuntimeState,
)
from testbed.planner.primitive_pre_dig_align_state import (
    PrimitivePreDigAlignCompatibilityRuntimeState,
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
    CoverageDebugReportInputs,
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
from testbed.planner.primitive_dig_recovery import (
    PrimitiveDigRecoveryPorts,
    PrimitiveDigRecoveryService,
)
from testbed.planner.primitive_effects import (
    RequestedEffectApplier,
    RequestedEffectApplierPorts,
)
from testbed.planner.primitive_skill_lifecycle import (
    PrimitiveSkillLifecyclePorts,
    PrimitiveSkillLifecycleService,
)
from testbed.planner.primitive_dig_token_planning import (
    PrimitiveDigTokenPlanningPorts,
    PrimitiveDigTokenPlanningService,
)
from testbed.planner.primitive_return_token_planning import (
    PrimitiveReturnTokenPlanningPorts,
    PrimitiveReturnTokenPlanningService,
)
from testbed.planner.primitive_reset_lifecycle import (
    PrimitiveResetLifecyclePorts,
    PrimitiveResetLifecycleService,
    PrimitiveResetLifecycleState,
)
from testbed.planner.primitive_runtime_kernel import (
    PrimitivePlannerRuntimeKernel,
    PrimitivePlannerRuntimeKernelPorts,
)
from testbed.planner.primitive_cycle_state import (
    PrimitiveCycleReportStatus,
    PrimitiveCycleRuntimeState,
)
from testbed.planner.primitive_execution_state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive_return_state import (
    PrimitiveReturnReportStatus,
    PrimitiveReturnRuntimeState,
)
from testbed.planner.primitive_scripted_bootstrap import (
    PrimitiveScriptedBootstrapReportStatus,
    PrimitiveScriptedBootstrapRuntimeConfig,
    PrimitiveScriptedBootstrapRuntimeService,
    PrimitiveScriptedBootstrapRuntimeState,
)
from testbed.planner.primitive_token_state import (
    PrimitiveTokenReportStatus,
    PrimitiveTokenRuntimeState,
)
from testbed.planner import primitive_adapter_config as adapter_config
from testbed.planner.primitive_adapter_config import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
    PrimitivePlannerAdapterConfigState,
)
from testbed.planner.primitive_token_runtime import (
    PrimitiveTokenRuntimeCoordinator,
    PrimitiveTokenRuntimePorts,
)
from testbed.planner.primitive_observation import (
    PrimitiveObservationInjectionRuntimeState,
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
        config_inputs = PrimitivePlannerAdapterConfigInputs(
            bootstrap_end_mode=bootstrap_end_mode,
            bootstrap_end_min_bucket_mass_kg=bootstrap_end_min_bucket_mass_kg,
            bootstrap_end_min_distance_to_dig_area_m=bootstrap_end_min_distance_to_dig_area_m,
            dig_to_carry_min_bucket_mass_kg=dig_to_carry_min_bucket_mass_kg,
            dig_to_carry_min_distance_to_dig_area_m=dig_to_carry_min_distance_to_dig_area_m,
            dig_to_carry_target_bucket_mass_kg=dig_to_carry_target_bucket_mass_kg,
            dig_to_carry_mass_plateau_enabled=dig_to_carry_mass_plateau_enabled,
            dig_to_carry_mass_plateau_min_bucket_mass_kg=dig_to_carry_mass_plateau_min_bucket_mass_kg,
            dig_to_carry_mass_plateau_epsilon_kg=dig_to_carry_mass_plateau_epsilon_kg,
            dig_to_carry_mass_plateau_hold_steps=dig_to_carry_mass_plateau_hold_steps,
            dig_to_carry_mass_plateau_min_steps=dig_to_carry_mass_plateau_min_steps,
            dig_bad_replan_enabled=dig_bad_replan_enabled,
            dig_bad_replan_max_steps=dig_bad_replan_max_steps,
            dig_bad_replan_min_bucket_mass_kg=dig_bad_replan_min_bucket_mass_kg,
            dig_exit_guard_enabled=dig_exit_guard_enabled,
            dig_exit_guard_min_steps=dig_exit_guard_min_steps,
            dig_exit_guard_overshoot_m=dig_exit_guard_overshoot_m,
            dig_exit_guard_min_bucket_mass_kg=dig_exit_guard_min_bucket_mass_kg,
            dig_failed_replan_next_skill=dig_failed_replan_next_skill,
            dump_ready_min_bucket_mass_kg=dump_ready_min_bucket_mass_kg,
            dump_ready_min_height_above_rim_m=dump_ready_min_height_above_rim_m,
            dump_ready_require_over_footprint=dump_ready_require_over_footprint,
            dump_ready_require_clearance=dump_ready_require_clearance,
            dump_ready_max_horizontal_distance_m=dump_ready_max_horizontal_distance_m,
            dump_ready_position_mode=dump_ready_position_mode,
            dump_ready_max_dump_area_footprint_outside_distance_m=dump_ready_max_dump_area_footprint_outside_distance_m,
            dump_ready_min_dump_area_relative_x_m=dump_ready_min_dump_area_relative_x_m,
            dump_ready_max_dump_area_relative_x_m=dump_ready_max_dump_area_relative_x_m,
            dump_ready_min_dump_area_relative_z_m=dump_ready_min_dump_area_relative_z_m,
            dump_ready_max_dump_area_relative_z_m=dump_ready_max_dump_area_relative_z_m,
            dump_ready_hold_steps=dump_ready_hold_steps,
            dump_ready_near_window_enabled=dump_ready_near_window_enabled,
            dump_ready_near_window_x_tolerance_m=dump_ready_near_window_x_tolerance_m,
            dump_ready_near_window_z_tolerance_m=dump_ready_near_window_z_tolerance_m,
            dump_ready_near_window_outside_tolerance_m=dump_ready_near_window_outside_tolerance_m,
            dump_ready_near_window_require_over_footprint=dump_ready_near_window_require_over_footprint,
            dump_done_max_bucket_mass_kg=dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=dump_done_min_deposit_delta_kg,
            dump_done_hold_steps=dump_done_hold_steps,
            dump_done_use_boundary_event=dump_done_use_boundary_event,
            return_to_dig_shallow_guard_enabled=return_to_dig_shallow_guard_enabled,
            return_to_dig_max_bucket_mass_kg=return_to_dig_max_bucket_mass_kg,
            return_to_dig_touch_tolerance_m=return_to_dig_touch_tolerance_m,
            return_to_dig_min_depth_m=return_to_dig_min_depth_m,
            return_to_dig_max_depth_m=return_to_dig_max_depth_m,
            return_to_dig_max_entry_error_m=return_to_dig_max_entry_error_m,
            return_to_dig_start_envelope_gate_enabled=return_to_dig_start_envelope_gate_enabled,
            return_to_dig_start_envelope_spatial_tolerance=return_to_dig_start_envelope_spatial_tolerance,
            return_to_dig_start_envelope_depth_tolerance_m=return_to_dig_start_envelope_depth_tolerance_m,
            return_to_dig_start_envelope_local_depth_tolerance_m=return_to_dig_start_envelope_local_depth_tolerance_m,
            return_to_dig_start_envelope_plane_depth_tolerance_m=return_to_dig_start_envelope_plane_depth_tolerance_m,
            return_to_dig_start_envelope_plane_depth_mode=return_to_dig_start_envelope_plane_depth_mode,
            return_to_dig_start_envelope_qpos_tolerance=return_to_dig_start_envelope_qpos_tolerance,
            return_to_dig_start_envelope_require_contact=return_to_dig_start_envelope_require_contact,
            return_to_dig_start_envelope_direct_handoff_enabled=return_to_dig_start_envelope_direct_handoff_enabled,
            return_max_steps=return_max_steps,
            action_dim=action_dim,
            primitive_checkpoint_paths=primitive_checkpoint_paths,
            goal_sequence=goal_sequence,
            goal_scenario_id=goal_scenario_id,
            goal_depth_norm=goal_depth_norm,
            goal_dump_target_norm=goal_dump_target_norm,
            cell_entry_enabled=cell_entry_enabled,
            cell_entry_grid=cell_entry_grid,
            cell_entry_low_productivity_payload_gain_kg=cell_entry_low_productivity_payload_gain_kg,
            dig_cut_planner=dig_cut_planner,
            return_target_planner=return_target_planner,
            scripted_bootstrap_target_qpos=scripted_bootstrap_target_qpos,
            scripted_bootstrap_kp=scripted_bootstrap_kp,
            scripted_bootstrap_kd=scripted_bootstrap_kd,
            scripted_bootstrap_action_clip=scripted_bootstrap_action_clip,
            scripted_bootstrap_action_signs=scripted_bootstrap_action_signs,
            scripted_bootstrap_qpos_tolerance=scripted_bootstrap_qpos_tolerance,
            scripted_bootstrap_qvel_abs_max=scripted_bootstrap_qvel_abs_max,
            scripted_bootstrap_hold_steps=scripted_bootstrap_hold_steps,
            scripted_bootstrap_max_steps=scripted_bootstrap_max_steps,
            pre_dig_align=pre_dig_align,
        )
        config_state = PrimitivePlannerAdapterConfigNormalizer.normalize(
            config_inputs
        )
        self._apply_adapter_config_state(config_state)
        self.reset()

    def _apply_adapter_config_state(
        self,
        config_state: PrimitivePlannerAdapterConfigState,
    ) -> None:
        for field_name, value in config_state.as_policy_field_updates().items():
            setattr(self, field_name, value)

    def reset(self) -> None:
        self._runtime_kernel().reset()

    def _runtime_kernel(self) -> PrimitivePlannerRuntimeKernel:
        return PrimitivePlannerRuntimeKernel.from_ports(self._runtime_kernel_ports())

    def _runtime_kernel_ports(self) -> PrimitivePlannerRuntimeKernelPorts:
        return PrimitivePlannerRuntimeKernelPorts(
            reset_lifecycle_service=self._primitive_reset_lifecycle_service,
            apply_reset_lifecycle_state=self._apply_reset_lifecycle_state,
            make_debug_state=self._make_debug_state,
            set_debug_state=lambda state: setattr(self, "_debug_state", state),
            execution_driver=self._execution_driver,
            debug_report_builder=self._debug_report_builder,
            debug_report_inputs=self._debug_report_inputs,
            rollout_summary_builder=self._rollout_summary_builder,
            rollout_summary_inputs=self._rollout_summary_inputs,
            planner_trace_builder=self._planner_trace_builder,
            planner_trace_inputs=self._planner_trace_inputs,
        )

    def _primitive_reset_lifecycle_service(self) -> PrimitiveResetLifecycleService:
        return PrimitiveResetLifecycleService.from_ports(
            self._primitive_reset_lifecycle_ports()
        )

    def _primitive_reset_lifecycle_ports(self) -> PrimitiveResetLifecyclePorts:
        return PrimitiveResetLifecyclePorts(
            all_policies=lambda: self._all_policies(),
            reset_boundary_detector=lambda: self.boundary_detector.reset(),
            reset_cell_entry_planner=lambda: self.cell_entry_planner.reset(),
            bootstrap_end_mode=lambda: str(self.bootstrap_end_mode),
            bootstrap_policy_available=lambda: self.bootstrap_policy is not None,
            scripted_bootstrap_enabled=lambda: self._scripted_bootstrap_enabled(),
            should_pre_dig_align_before_dig=(
                lambda: self._should_pre_dig_align_before_dig()
            ),
            action_dim=int(self.action_dim),
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            dig_skill_name="dig",
        )

    def _apply_reset_lifecycle_state(
        self,
        reset_state: PrimitiveResetLifecycleState,
    ) -> None:
        for field_name, value in reset_state.as_policy_field_updates().items():
            setattr(self, field_name, value)

    def _primitive_execution_runtime_state(self) -> PrimitiveExecutionRuntimeState:
        state = self.__dict__.get("_execution_state")
        if state is None:
            state = PrimitiveExecutionRuntimeState.fresh()
            self.__dict__["_execution_state"] = state
        return state

    @property
    def _skill_name(self) -> str:
        return str(self._primitive_execution_runtime_state().skill_name)

    @_skill_name.setter
    def _skill_name(self, value: str) -> None:
        self._primitive_execution_runtime_state().set_skill_name(value)

    @property
    def _switch_reason(self) -> str:
        return str(self._primitive_execution_runtime_state().switch_reason)

    @_switch_reason.setter
    def _switch_reason(self, value: str) -> None:
        self._primitive_execution_runtime_state().set_switch_reason(value)

    @property
    def _prev_action(self) -> np.ndarray | None:
        return self._primitive_execution_runtime_state().prev_action

    @_prev_action.setter
    def _prev_action(self, value: np.ndarray | None) -> None:
        self._primitive_execution_runtime_state().set_prev_action(value)

    @property
    def _debug_state(self) -> Any | None:
        return self._primitive_execution_runtime_state().debug_state

    @_debug_state.setter
    def _debug_state(self, value: Any) -> None:
        self._primitive_execution_runtime_state().set_debug_state(value)

    def _primitive_cycle_runtime_state(self) -> PrimitiveCycleRuntimeState:
        state = self.__dict__.get("_cycle_state")
        if state is None:
            state = PrimitiveCycleRuntimeState.fresh()
            self.__dict__["_cycle_state"] = state
        return state

    def _cycle_report_status(self) -> PrimitiveCycleReportStatus:
        return self._primitive_cycle_runtime_state().to_report_status()

    @property
    def _dump_ready_hold_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().dump_ready_hold_count)

    @_dump_ready_hold_count.setter
    def _dump_ready_hold_count(self, value: int) -> None:
        self._primitive_cycle_runtime_state().dump_ready_hold_count = int(value)

    @property
    def _dump_done_hold_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().dump_done_hold_count)

    @_dump_done_hold_count.setter
    def _dump_done_hold_count(self, value: int) -> None:
        self._primitive_cycle_runtime_state().dump_done_hold_count = int(value)

    @property
    def _dig_step_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().dig_step_count)

    @_dig_step_count.setter
    def _dig_step_count(self, value: int) -> None:
        self._primitive_cycle_runtime_state().dig_step_count = int(value)

    @property
    def _dig_best_mass_kg(self) -> float:
        return float(self._primitive_cycle_runtime_state().dig_best_mass_kg)

    @_dig_best_mass_kg.setter
    def _dig_best_mass_kg(self, value: float) -> None:
        self._primitive_cycle_runtime_state().dig_best_mass_kg = float(value)

    @property
    def _dig_mass_plateau_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().dig_mass_plateau_count)

    @_dig_mass_plateau_count.setter
    def _dig_mass_plateau_count(self, value: int) -> None:
        self._primitive_cycle_runtime_state().dig_mass_plateau_count = int(value)

    @property
    def _dig_to_carry_reason(self) -> str:
        return str(self._primitive_cycle_runtime_state().dig_to_carry_reason)

    @_dig_to_carry_reason.setter
    def _dig_to_carry_reason(self, value: str) -> None:
        self._primitive_cycle_runtime_state().dig_to_carry_reason = str(value)

    @property
    def _dig_bad_replan_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().dig_bad_replan_count)

    @_dig_bad_replan_count.setter
    def _dig_bad_replan_count(self, value: int) -> None:
        self._primitive_cycle_runtime_state().dig_bad_replan_count = int(value)

    @property
    def _dig_exit_guard_replan_count(self) -> int:
        return int(
            self._primitive_cycle_runtime_state().dig_exit_guard_replan_count
        )

    @_dig_exit_guard_replan_count.setter
    def _dig_exit_guard_replan_count(self, value: int) -> None:
        state = self._primitive_cycle_runtime_state()
        state.dig_exit_guard_replan_count = int(value)

    @property
    def _completed_transition_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().completed_transition_count)

    @_completed_transition_count.setter
    def _completed_transition_count(self, value: int) -> None:
        state = self._primitive_cycle_runtime_state()
        state.completed_transition_count = int(value)

    @property
    def _transition_timeout_count(self) -> int:
        return int(self._primitive_cycle_runtime_state().transition_timeout_count)

    @_transition_timeout_count.setter
    def _transition_timeout_count(self, value: int) -> None:
        state = self._primitive_cycle_runtime_state()
        state.transition_timeout_count = int(value)

    @property
    def _cycle_index(self) -> int:
        return int(self._primitive_cycle_runtime_state().cycle_index)

    @_cycle_index.setter
    def _cycle_index(self, value: int) -> None:
        self._primitive_cycle_runtime_state().cycle_index = int(value)

    @property
    def _dump_start_deposited_mass_kg(self) -> float:
        return float(
            self._primitive_cycle_runtime_state().dump_start_deposited_mass_kg
        )

    @_dump_start_deposited_mass_kg.setter
    def _dump_start_deposited_mass_kg(self, value: float) -> None:
        state = self._primitive_cycle_runtime_state()
        state.dump_start_deposited_mass_kg = float(value)

    def _primitive_return_runtime_state(self) -> PrimitiveReturnRuntimeState:
        state = self.__dict__.get("_return_state")
        if state is None:
            state = PrimitiveReturnRuntimeState.fresh()
            self.__dict__["_return_state"] = state
        return state

    def _return_report_status(self) -> PrimitiveReturnReportStatus:
        return self._primitive_return_runtime_state().to_report_status(
            start_envelope_gate_enabled=bool(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            start_envelope_direct_handoff_enabled=bool(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            start_envelope_plane_depth_mode=str(
                self.return_to_dig_start_envelope_plane_depth_mode
            ),
            start_envelope_local_depth_tolerance_m=float(
                self.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
        )

    @property
    def _return_step_count(self) -> int:
        return int(self._primitive_return_runtime_state().return_step_count)

    @_return_step_count.setter
    def _return_step_count(self, value: int) -> None:
        self._primitive_return_runtime_state().return_step_count = int(value)

    @property
    def _return_to_dig_entry_error_m(self) -> float:
        return float(
            self._primitive_return_runtime_state().return_to_dig_entry_error_m
        )

    @_return_to_dig_entry_error_m.setter
    def _return_to_dig_entry_error_m(self, value: float) -> None:
        self._primitive_return_runtime_state().return_to_dig_entry_error_m = float(
            value
        )

    @property
    def _return_to_dig_entry_close_state(self) -> bool:
        return bool(
            self._primitive_return_runtime_state().return_to_dig_entry_close_state
        )

    @_return_to_dig_entry_close_state.setter
    def _return_to_dig_entry_close_state(self, value: bool) -> None:
        state = self._primitive_return_runtime_state()
        state.return_to_dig_entry_close_state = bool(value)

    @property
    def _return_next_dig_event_seen(self) -> bool:
        return bool(self._primitive_return_runtime_state().return_next_dig_event_seen)

    @_return_next_dig_event_seen.setter
    def _return_next_dig_event_seen(self, value: bool) -> None:
        state = self._primitive_return_runtime_state()
        state.return_next_dig_event_seen = bool(value)

    @property
    def _return_to_dig_start_envelope_ready_state(self) -> bool:
        return bool(
            self._primitive_return_runtime_state()
            .return_to_dig_start_envelope_ready_state
        )

    @_return_to_dig_start_envelope_ready_state.setter
    def _return_to_dig_start_envelope_ready_state(self, value: bool) -> None:
        state = self._primitive_return_runtime_state()
        state.return_to_dig_start_envelope_ready_state = bool(value)

    @property
    def _return_to_dig_start_envelope_error(self) -> float:
        return float(
            self._primitive_return_runtime_state()
            .return_to_dig_start_envelope_error
        )

    @_return_to_dig_start_envelope_error.setter
    def _return_to_dig_start_envelope_error(self, value: float) -> None:
        state = self._primitive_return_runtime_state()
        state.return_to_dig_start_envelope_error = float(value)

    @property
    def _return_to_dig_start_envelope_checks(self) -> dict[str, Any]:
        return (
            self._primitive_return_runtime_state()
            .return_to_dig_start_envelope_checks
        )

    @_return_to_dig_start_envelope_checks.setter
    def _return_to_dig_start_envelope_checks(
        self,
        value: dict[str, Any],
    ) -> None:
        state = self._primitive_return_runtime_state()
        state.return_to_dig_start_envelope_checks = value

    def _primitive_scripted_bootstrap_runtime_state(
        self,
    ) -> PrimitiveScriptedBootstrapRuntimeState:
        state = self.__dict__.get("_scripted_bootstrap_state")
        if state is None:
            state = PrimitiveScriptedBootstrapRuntimeState.fresh()
            self.__dict__["_scripted_bootstrap_state"] = state
        return state

    def _scripted_bootstrap_report_status(
        self,
    ) -> PrimitiveScriptedBootstrapReportStatus:
        return self._primitive_scripted_bootstrap_runtime_state().to_report_status()

    @property
    def _scripted_bootstrap_step_count(self) -> int:
        return int(self._primitive_scripted_bootstrap_runtime_state().step_count)

    @_scripted_bootstrap_step_count.setter
    def _scripted_bootstrap_step_count(self, value: int) -> None:
        self._primitive_scripted_bootstrap_runtime_state().step_count = int(value)

    @property
    def _scripted_bootstrap_hold_count(self) -> int:
        return int(self._primitive_scripted_bootstrap_runtime_state().hold_count)

    @_scripted_bootstrap_hold_count.setter
    def _scripted_bootstrap_hold_count(self, value: int) -> None:
        self._primitive_scripted_bootstrap_runtime_state().hold_count = int(value)

    @property
    def _scripted_bootstrap_timeout_count(self) -> int:
        return int(self._primitive_scripted_bootstrap_runtime_state().timeout_count)

    @_scripted_bootstrap_timeout_count.setter
    def _scripted_bootstrap_timeout_count(self, value: int) -> None:
        self._primitive_scripted_bootstrap_runtime_state().timeout_count = int(value)

    def _primitive_pre_dig_align_compatibility_runtime_state(
        self,
    ) -> PrimitivePreDigAlignCompatibilityRuntimeState:
        state = self.__dict__.get("_pre_dig_align_state")
        if state is None:
            state = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(
                action_dim=int(getattr(self, "action_dim", 4)),
            )
            self.__dict__["_pre_dig_align_state"] = state
        return state

    @property
    def _pre_dig_align_step_count(self) -> int:
        return int(
            self._primitive_pre_dig_align_compatibility_runtime_state().step_count
        )

    @_pre_dig_align_step_count.setter
    def _pre_dig_align_step_count(self, value: int) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.step_count = int(value)

    @property
    def _pre_dig_align_hold_count(self) -> int:
        return int(
            self._primitive_pre_dig_align_compatibility_runtime_state().hold_count
        )

    @_pre_dig_align_hold_count.setter
    def _pre_dig_align_hold_count(self, value: int) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.hold_count = int(value)

    @property
    def _pre_dig_align_timeout_count(self) -> int:
        return int(
            self._primitive_pre_dig_align_compatibility_runtime_state().timeout_count
        )

    @_pre_dig_align_timeout_count.setter
    def _pre_dig_align_timeout_count(self, value: int) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.timeout_count = int(value)

    @property
    def _pre_dig_align_completed_count(self) -> int:
        return int(
            self._primitive_pre_dig_align_compatibility_runtime_state().completed_count
        )

    @_pre_dig_align_completed_count.setter
    def _pre_dig_align_completed_count(self, value: int) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.completed_count = int(value)

    @property
    def _pre_dig_align_replan_count(self) -> int:
        return int(
            self._primitive_pre_dig_align_compatibility_runtime_state().replan_count
        )

    @_pre_dig_align_replan_count.setter
    def _pre_dig_align_replan_count(self, value: int) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.replan_count = int(value)

    @property
    def _pre_dig_align_target_qpos(self) -> np.ndarray:
        return (
            self._primitive_pre_dig_align_compatibility_runtime_state().target_qpos
        )

    @_pre_dig_align_target_qpos.setter
    def _pre_dig_align_target_qpos(self, value: np.ndarray) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.target_qpos = value

    @property
    def _pre_dig_align_error(self) -> np.ndarray:
        return self._primitive_pre_dig_align_compatibility_runtime_state().error

    @_pre_dig_align_error.setter
    def _pre_dig_align_error(self, value: np.ndarray) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.error = value

    @property
    def _pre_dig_align_entry_error_m(self) -> float:
        return float(
            self._primitive_pre_dig_align_compatibility_runtime_state().entry_error_m
        )

    @_pre_dig_align_entry_error_m.setter
    def _pre_dig_align_entry_error_m(self, value: float) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.entry_error_m = float(value)

    @property
    def _pre_dig_align_start_envelope_ready(self) -> bool:
        return bool(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .start_envelope_ready
        )

    @_pre_dig_align_start_envelope_ready.setter
    def _pre_dig_align_start_envelope_ready(self, value: bool) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.start_envelope_ready = bool(value)

    @property
    def _pre_dig_align_entry_close_handoff_ready(self) -> bool:
        return bool(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .entry_close_handoff_ready
        )

    @_pre_dig_align_entry_close_handoff_ready.setter
    def _pre_dig_align_entry_close_handoff_ready(self, value: bool) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.entry_close_handoff_ready = bool(value)

    @property
    def _pre_dig_align_entry_intent_handoff_ready(self) -> bool:
        return bool(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .entry_intent_handoff_ready
        )

    @_pre_dig_align_entry_intent_handoff_ready.setter
    def _pre_dig_align_entry_intent_handoff_ready(self, value: bool) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.entry_intent_handoff_ready = bool(value)

    @property
    def _pre_dig_align_timeout_handoff_reason(self) -> str:
        return str(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .timeout_handoff_reason
        )

    @_pre_dig_align_timeout_handoff_reason.setter
    def _pre_dig_align_timeout_handoff_reason(self, value: str) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.timeout_handoff_reason = str(value)

    @property
    def _pre_dig_align_surface_depth_m(self) -> float:
        return float(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .surface_depth_m
        )

    @_pre_dig_align_surface_depth_m.setter
    def _pre_dig_align_surface_depth_m(self, value: float) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.surface_depth_m = float(value)

    @property
    def _pre_dig_align_surface_guard_triggered(self) -> bool:
        return bool(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .surface_guard_triggered
        )

    @_pre_dig_align_surface_guard_triggered.setter
    def _pre_dig_align_surface_guard_triggered(self, value: bool) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.surface_guard_triggered = bool(value)

    @property
    def _pre_dig_align_surface_guard_count(self) -> int:
        return int(
            self._primitive_pre_dig_align_compatibility_runtime_state()
            .surface_guard_count
        )

    @_pre_dig_align_surface_guard_count.setter
    def _pre_dig_align_surface_guard_count(self, value: int) -> None:
        state = self._primitive_pre_dig_align_compatibility_runtime_state()
        state.surface_guard_count = int(value)

    def _primitive_observation_injection_runtime_state(
        self,
    ) -> PrimitiveObservationInjectionRuntimeState:
        state = self.__dict__.get("_observation_injection_state")
        if state is None:
            state = PrimitiveObservationInjectionRuntimeState.fresh()
            self.__dict__["_observation_injection_state"] = state
        return state

    @property
    def _cell_entry_token_injected(self) -> bool:
        return bool(
            self._primitive_observation_injection_runtime_state()
            .cell_entry_token_injected
        )

    @_cell_entry_token_injected.setter
    def _cell_entry_token_injected(self, value: bool) -> None:
        state = self._primitive_observation_injection_runtime_state()
        state.cell_entry_token_injected = bool(value)

    @property
    def _dig_cut_token_injected(self) -> bool:
        return bool(
            self._primitive_observation_injection_runtime_state()
            .dig_cut_token_injected
        )

    @_dig_cut_token_injected.setter
    def _dig_cut_token_injected(self, value: bool) -> None:
        state = self._primitive_observation_injection_runtime_state()
        state.dig_cut_token_injected = bool(value)

    @property
    def _dig_depth_profile_token_injected(self) -> bool:
        return bool(
            self._primitive_observation_injection_runtime_state()
            .dig_depth_profile_token_injected
        )

    @_dig_depth_profile_token_injected.setter
    def _dig_depth_profile_token_injected(self, value: bool) -> None:
        state = self._primitive_observation_injection_runtime_state()
        state.dig_depth_profile_token_injected = bool(value)

    @property
    def _return_target_token_injected(self) -> bool:
        return bool(
            self._primitive_observation_injection_runtime_state()
            .return_target_token_injected
        )

    @_return_target_token_injected.setter
    def _return_target_token_injected(self, value: bool) -> None:
        state = self._primitive_observation_injection_runtime_state()
        state.return_target_token_injected = bool(value)

    @property
    def _return_relocate_token_injected(self) -> bool:
        return bool(
            self._primitive_observation_injection_runtime_state()
            .return_relocate_token_injected
        )

    @_return_relocate_token_injected.setter
    def _return_relocate_token_injected(self, value: bool) -> None:
        state = self._primitive_observation_injection_runtime_state()
        state.return_relocate_token_injected = bool(value)

    @property
    def _return_start_envelope_token_injected(self) -> bool:
        return bool(
            self._primitive_observation_injection_runtime_state()
            .return_start_envelope_token_injected
        )

    @_return_start_envelope_token_injected.setter
    def _return_start_envelope_token_injected(self, value: bool) -> None:
        state = self._primitive_observation_injection_runtime_state()
        state.return_start_envelope_token_injected = bool(value)

    def _primitive_cell_entry_compatibility_runtime_state(
        self,
    ) -> PrimitiveCellEntryCompatibilityRuntimeState:
        state = self.__dict__.get("_cell_entry_state")
        if state is None:
            state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()
            self.__dict__["_cell_entry_state"] = state
        return state

    @property
    def _cell_entry_goal(self) -> Any | None:
        return self._primitive_cell_entry_compatibility_runtime_state().goal

    @_cell_entry_goal.setter
    def _cell_entry_goal(self, value: Any | None) -> None:
        self._primitive_cell_entry_compatibility_runtime_state().goal = value

    @property
    def _cell_entry_goal_cycle_id(self) -> int:
        return int(
            self._primitive_cell_entry_compatibility_runtime_state().goal_cycle_id
        )

    @_cell_entry_goal_cycle_id.setter
    def _cell_entry_goal_cycle_id(self, value: int) -> None:
        state = self._primitive_cell_entry_compatibility_runtime_state()
        state.goal_cycle_id = int(value)

    @property
    def _cell_entry_audit(self) -> Any | None:
        return self._primitive_cell_entry_compatibility_runtime_state().audit

    @_cell_entry_audit.setter
    def _cell_entry_audit(self, value: Any | None) -> None:
        self._primitive_cell_entry_compatibility_runtime_state().audit = value

    @property
    def _cell_entry_tokens(self) -> np.ndarray:
        return self._primitive_cell_entry_compatibility_runtime_state().tokens

    @_cell_entry_tokens.setter
    def _cell_entry_tokens(self, value: np.ndarray) -> None:
        self._primitive_cell_entry_compatibility_runtime_state().tokens = value

    @property
    def _cell_entry_seen_cell_id(self) -> int:
        return int(
            self._primitive_cell_entry_compatibility_runtime_state().seen_cell_id
        )

    @_cell_entry_seen_cell_id.setter
    def _cell_entry_seen_cell_id(self, value: int) -> None:
        state = self._primitive_cell_entry_compatibility_runtime_state()
        state.seen_cell_id = int(value)

    @property
    def _cell_entry_trace(self) -> list[dict[str, Any]]:
        return self._primitive_cell_entry_compatibility_runtime_state().trace

    @_cell_entry_trace.setter
    def _cell_entry_trace(self, value: list[dict[str, Any]]) -> None:
        self._primitive_cell_entry_compatibility_runtime_state().trace = value

    def _primitive_token_runtime_state(self) -> PrimitiveTokenRuntimeState:
        state = self.__dict__.get("_token_state")
        if state is None:
            state = PrimitiveTokenRuntimeState.fresh()
            self.__dict__["_token_state"] = state
        return state

    @property
    def _dig_cut_planned_cycle_id(self) -> int:
        return int(self._primitive_token_runtime_state().dig_cut_planned_cycle_id)

    @_dig_cut_planned_cycle_id.setter
    def _dig_cut_planned_cycle_id(self, value: int) -> None:
        self._primitive_token_runtime_state().dig_cut_planned_cycle_id = int(value)

    @property
    def _dig_cut_tokens(self) -> np.ndarray:
        return self._primitive_token_runtime_state().dig_cut_tokens

    @_dig_cut_tokens.setter
    def _dig_cut_tokens(self, value: np.ndarray) -> None:
        self._primitive_token_runtime_state().dig_cut_tokens = value

    @property
    def _dig_depth_profile_tokens(self) -> np.ndarray:
        return self._primitive_token_runtime_state().dig_depth_profile_tokens

    @_dig_depth_profile_tokens.setter
    def _dig_depth_profile_tokens(self, value: np.ndarray) -> None:
        self._primitive_token_runtime_state().dig_depth_profile_tokens = value

    @property
    def _dig_cut_token_source(self) -> str:
        return str(self._primitive_token_runtime_state().dig_cut_token_source)

    @_dig_cut_token_source.setter
    def _dig_cut_token_source(self, value: str) -> None:
        self._primitive_token_runtime_state().dig_cut_token_source = str(value)

    @property
    def _dig_cut_fallback_reason(self) -> str:
        return str(self._primitive_token_runtime_state().dig_cut_fallback_reason)

    @_dig_cut_fallback_reason.setter
    def _dig_cut_fallback_reason(self, value: str) -> None:
        self._primitive_token_runtime_state().dig_cut_fallback_reason = str(value)

    @property
    def _dig_cut_token_in_prior_p10_p90(self) -> bool:
        return bool(
            self._primitive_token_runtime_state().dig_cut_token_in_prior_p10_p90
        )

    @_dig_cut_token_in_prior_p10_p90.setter
    def _dig_cut_token_in_prior_p10_p90(self, value: bool) -> None:
        self._primitive_token_runtime_state().dig_cut_token_in_prior_p10_p90 = bool(
            value
        )

    @property
    def _dig_depth_profile_token_source(self) -> str:
        return str(
            self._primitive_token_runtime_state().dig_depth_profile_token_source
        )

    @_dig_depth_profile_token_source.setter
    def _dig_depth_profile_token_source(self, value: str) -> None:
        self._primitive_token_runtime_state().dig_depth_profile_token_source = str(
            value
        )

    @property
    def _dig_depth_profile_fallback_reason(self) -> str:
        return str(
            self._primitive_token_runtime_state().dig_depth_profile_fallback_reason
        )

    @_dig_depth_profile_fallback_reason.setter
    def _dig_depth_profile_fallback_reason(self, value: str) -> None:
        self._primitive_token_runtime_state().dig_depth_profile_fallback_reason = str(
            value
        )

    @property
    def _return_target_planned_cycle_id(self) -> int:
        return int(
            self._primitive_token_runtime_state().return_target_planned_cycle_id
        )

    @_return_target_planned_cycle_id.setter
    def _return_target_planned_cycle_id(self, value: int) -> None:
        self._primitive_token_runtime_state().return_target_planned_cycle_id = int(
            value
        )

    @property
    def _return_target_tokens(self) -> np.ndarray:
        return self._primitive_token_runtime_state().return_target_tokens

    @_return_target_tokens.setter
    def _return_target_tokens(self, value: np.ndarray) -> None:
        self._primitive_token_runtime_state().return_target_tokens = value

    @property
    def _return_relocate_tokens(self) -> np.ndarray:
        return self._primitive_token_runtime_state().return_relocate_tokens

    @_return_relocate_tokens.setter
    def _return_relocate_tokens(self, value: np.ndarray) -> None:
        self._primitive_token_runtime_state().return_relocate_tokens = value

    @property
    def _return_start_envelope_tokens(self) -> np.ndarray:
        return self._primitive_token_runtime_state().return_start_envelope_tokens

    @_return_start_envelope_tokens.setter
    def _return_start_envelope_tokens(self, value: np.ndarray) -> None:
        self._primitive_token_runtime_state().return_start_envelope_tokens = value

    @property
    def _return_target_token_source(self) -> str:
        return str(self._primitive_token_runtime_state().return_target_token_source)

    @_return_target_token_source.setter
    def _return_target_token_source(self, value: str) -> None:
        self._primitive_token_runtime_state().return_target_token_source = str(value)

    @property
    def _return_target_fallback_reason(self) -> str:
        return str(self._primitive_token_runtime_state().return_target_fallback_reason)

    @_return_target_fallback_reason.setter
    def _return_target_fallback_reason(self, value: str) -> None:
        self._primitive_token_runtime_state().return_target_fallback_reason = str(
            value
        )

    @property
    def _return_start_envelope_token_source(self) -> str:
        return str(
            self._primitive_token_runtime_state().return_start_envelope_token_source
        )

    @_return_start_envelope_token_source.setter
    def _return_start_envelope_token_source(self, value: str) -> None:
        self._primitive_token_runtime_state().return_start_envelope_token_source = str(
            value
        )

    @property
    def _return_start_envelope_use_prior_spatial_bounds(self) -> bool:
        return bool(
            self._primitive_token_runtime_state()
            .return_start_envelope_use_prior_spatial_bounds
        )

    @_return_start_envelope_use_prior_spatial_bounds.setter
    def _return_start_envelope_use_prior_spatial_bounds(self, value: bool) -> None:
        state = self._primitive_token_runtime_state()
        state.return_start_envelope_use_prior_spatial_bounds = bool(value)

    @property
    def _return_start_envelope_use_prior_qpos_bounds(self) -> bool:
        return bool(
            self._primitive_token_runtime_state()
            .return_start_envelope_use_prior_qpos_bounds
        )

    @_return_start_envelope_use_prior_qpos_bounds.setter
    def _return_start_envelope_use_prior_qpos_bounds(self, value: bool) -> None:
        state = self._primitive_token_runtime_state()
        state.return_start_envelope_use_prior_qpos_bounds = bool(value)

    @property
    def _pending_dig_cut_cycle_id(self) -> int:
        return int(self._primitive_token_runtime_state().pending_dig_cut_cycle_id)

    @_pending_dig_cut_cycle_id.setter
    def _pending_dig_cut_cycle_id(self, value: int) -> None:
        self._primitive_token_runtime_state().pending_dig_cut_cycle_id = int(value)

    @property
    def _pending_dig_cut_corridor_id(self) -> int:
        return int(self._primitive_token_runtime_state().pending_dig_cut_corridor_id)

    @_pending_dig_cut_corridor_id.setter
    def _pending_dig_cut_corridor_id(self, value: int) -> None:
        self._primitive_token_runtime_state().pending_dig_cut_corridor_id = int(value)

    @property
    def _pending_dig_cut_raw_fields(self) -> dict[str, float | int] | None:
        return self._primitive_token_runtime_state().pending_dig_cut_raw_fields

    @_pending_dig_cut_raw_fields.setter
    def _pending_dig_cut_raw_fields(
        self,
        value: dict[str, float | int] | None,
    ) -> None:
        self._primitive_token_runtime_state().pending_dig_cut_raw_fields = value

    @property
    def _pending_dig_cut_tokens(self) -> np.ndarray | None:
        return self._primitive_token_runtime_state().pending_dig_cut_tokens

    @_pending_dig_cut_tokens.setter
    def _pending_dig_cut_tokens(self, value: np.ndarray | None) -> None:
        self._primitive_token_runtime_state().pending_dig_cut_tokens = value

    @property
    def _pending_dig_depth_profile_tokens(self) -> np.ndarray | None:
        return self._primitive_token_runtime_state().pending_dig_depth_profile_tokens

    @_pending_dig_depth_profile_tokens.setter
    def _pending_dig_depth_profile_tokens(self, value: np.ndarray | None) -> None:
        state = self._primitive_token_runtime_state()
        state.pending_dig_depth_profile_tokens = value

    @property
    def _pending_dig_state_exemplar_ids(self) -> list[str]:
        return self._primitive_token_runtime_state().pending_dig_state_exemplar_ids

    @_pending_dig_state_exemplar_ids.setter
    def _pending_dig_state_exemplar_ids(self, value: list[str]) -> None:
        self._primitive_token_runtime_state().pending_dig_state_exemplar_ids = list(
            value
        )

    @property
    def _pending_dig_state_exemplar_distance(self) -> float:
        return float(
            self._primitive_token_runtime_state().pending_dig_state_exemplar_distance
        )

    @_pending_dig_state_exemplar_distance.setter
    def _pending_dig_state_exemplar_distance(self, value: float) -> None:
        state = self._primitive_token_runtime_state()
        state.pending_dig_state_exemplar_distance = float(value)

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
                state = self._primitive_cycle_runtime_state()
                state.increment_transition_timeout_count()
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
            backend_factories={
                "legacy_fsm": self._legacy_fsm_backend_factory,
            },
        )

    def _legacy_fsm_backend_factory(self) -> LegacyFSMDecisionBackendFactory:
        return LegacyFSMDecisionBackendFactory.from_ports(
            self._legacy_fsm_branch_ports()
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
            cycle_state=self._primitive_cycle_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            set_skill=lambda skill, reason: self._set_skill(skill, reason),
            next_skill_after_return_transition=(
                lambda: self._next_skill_after_return_transition()
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
            deposited_mass=lambda obs: self._deposited_mass(obs),
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
        capabilities = self._primitive_decision_capabilities()
        return LegacyFSMBranchPorts(
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            dig_skill_name="dig",
            carry_skill_name="carry",
            dump_skill_name="dump",
            return_skill_name="return",
            facts_source=capabilities.facts_source(),
            compatibility_actions=capabilities.compatibility_actions(),
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
            cycle_state=self._primitive_cycle_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
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
            dump_done_hold_steps=self.dump_done_hold_steps,
            refresh_return_handoff_state=(
                lambda obs: self._return_to_dig_handoff_ready(obs)
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
        self._primitive_cycle_runtime_state().set_dump_ready_hold_count(value)

    def _set_dump_start_deposited_mass(self, value: float) -> None:
        self._primitive_cycle_runtime_state().set_dump_start_deposited_mass_kg(value)

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
        self._primitive_cycle_runtime_state().set_dump_done_hold_count(value)

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
        self._primitive_return_runtime_state().mark_next_dig_event_seen()

    def _complete_return_transition_for_backend(self) -> None:
        self._primitive_cycle_runtime_state().complete_return_transition()

    def _next_skill_after_return_transition(self) -> str:
        return (
            PRE_DIG_ALIGN_SKILL_NAME
            if self._should_pre_dig_align_before_dig()
            else "dig"
        )

    def _increment_dig_exit_guard_replan_count(self) -> None:
        self._primitive_cycle_runtime_state().increment_dig_exit_guard_replan_count()

    def _increment_dig_bad_replan_count(self) -> None:
        self._primitive_cycle_runtime_state().increment_dig_bad_replan_count()

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
        return self._runtime_kernel().predict(obs)

    def debug_state(self) -> dict[str, Any]:
        return self._runtime_kernel().debug_state()

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
        return self._primitive_token_runtime_state().to_token_status(
            cell_entry_enabled=bool(self.cell_entry_enabled),
            token_injection_state=(
                self._primitive_observation_injection_runtime_state()
                .to_token_injection_state()
            ),
            dig_depth_profile_source=str(self.dig_depth_profile_source),
            dig_depth_profile_required=bool(self.dig_depth_profile_required),
        )

    def _token_report_status(self) -> PrimitiveTokenReportStatus:
        return self._primitive_token_runtime_state().to_report_status(
            token_injection_state=(
                self._primitive_observation_injection_runtime_state()
                .to_token_injection_state()
            ),
            dig_cut_planner_mode=str(self.dig_cut_planner_mode),
            dig_cut_prior_id=str(self.dig_cut_prior_id),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
        )

    def _debug_report_return_fields(self) -> dict[str, Any]:
        return self._return_report_status().debug_fields()

    def _debug_report_pending_fields(self) -> dict[str, Any]:
        return self._token_report_status().pending_debug_fields()

    def _debug_report_dig_cut_fields(self) -> dict[str, Any]:
        return self._token_report_status().dig_cut_debug_fields()

    def _debug_report_coverage_fields(self) -> dict[str, Any]:
        active_corridor = self._coverage_active_corridor()
        return self._coverage_report_service().debug_fields(
            CoverageDebugReportInputs(
                active_corridor_id=int(self._coverage_active_corridor_id),
                last_selected_corridor_id=int(
                    self._coverage_last_selected_corridor_id
                ),
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
                active_corridor=(
                    None
                    if active_corridor is None
                    else self._coverage_corridor_to_debug(active_corridor)
                ),
                active_cell_id=int(self._coverage_active_cell_id()),
                active_score=float(self._coverage_active_corridor_score()),
                state_exemplar_enabled=bool(self.coverage_state_exemplars_enabled),
                state_exemplar_ids=list(self._coverage_active_state_exemplar_ids),
                state_exemplar_distance=float(
                    self._coverage_active_state_exemplar_distance
                ),
                depleted_count=int(self._coverage_depleted_count()),
                pass_index=int(self._coverage_pass_index),
                multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
                multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
                multi_pass_min_remaining_depth_m=float(
                    self.coverage_multi_pass_min_remaining_depth_m
                ),
                last_payload_gain_kg=float(self._coverage_last_payload_gain_kg),
                last_effective_deposit_delta_kg=float(
                    self._coverage_last_effective_deposit_delta_kg
                ),
                global_low_productivity_streak=int(
                    self._coverage_global_low_productivity_streak
                ),
                use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
                candidate_layout=str(self.coverage_candidate_layout),
                first_dig_strategy=str(self.coverage_first_dig_strategy),
                first_dig_preferred_corridor_id=(
                    self.coverage_first_dig_preferred_corridor_id
                ),
                first_dig_max_entry_distance_m=(
                    self.coverage_first_dig_max_entry_distance_m
                ),
                first_dig_qpos_delta_weight=float(
                    self.coverage_first_dig_qpos_delta_weight
                ),
                first_dig_max_qpos_delta=self.coverage_first_dig_max_qpos_delta,
                terminal_stop_requested=bool(
                    self._coverage_terminal_stop_requested
                ),
                terminal_stop_reason=str(self._coverage_terminal_stop_reason),
                corridors=[
                    self._coverage_corridor_to_debug(corridor)
                    for corridor in self._coverage_corridors
                ],
                candidate_scores=list(self._coverage_candidate_scores),
            )
        )

    def _debug_report_cell_entry_fields(self) -> dict[str, Any]:
        return self._primitive_cell_entry_compatibility_runtime_state().debug_fields()

    def _debug_report_scripted_bootstrap_fields(self) -> dict[str, Any]:
        return self._scripted_bootstrap_report_status().debug_fields()

    def _debug_report_dig_progress_fields(self) -> dict[str, Any]:
        return self._cycle_report_status().dig_progress_debug_fields()

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
        return self._runtime_kernel().rollout_summary()

    @staticmethod
    def _rollout_summary_builder() -> PrimitiveRolloutSummaryBuilder:
        return PrimitiveRolloutSummaryBuilder()

    def _rollout_summary_inputs(self) -> PrimitiveRolloutSummaryInputs:
        cycle_status = self._cycle_report_status()
        return_status = self._return_report_status()
        scripted_bootstrap_status = self._scripted_bootstrap_report_status()
        token_status = self._token_report_status()
        coverage_status = self._coverage_report_service().summary_status(
            selected_corridor_id=int(self._coverage_active_corridor_id),
            depleted_count=int(self._coverage_depleted_count()),
            completed_dump_count=int(self._coverage_completed_dump_count),
            pass_index=int(self._coverage_pass_index),
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            candidate_layout=str(self.coverage_candidate_layout),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            first_dig_max_entry_distance_m=(
                self.coverage_first_dig_max_entry_distance_m
            ),
            first_dig_qpos_delta_weight=float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            terminal_stop_requested=bool(
                self._coverage_terminal_stop_requested
            ),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )
        return PrimitiveRolloutSummaryInputs(
            transition_source=TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            transition_policy_mode=TRANSITION_POLICY_MODE_PRIMITIVE,
            transition_fallback_count=0,
            transition_fallback_reason="",
            transition_timeout_count=cycle_status.transition_timeout_count,
            completed_transition_count=cycle_status.completed_transition_count,
            dump_done_use_boundary_event=bool(self.dump_done_use_boundary_event),
            primitive_final_skill=str(self._skill_name),
            primitive_cycle_index=cycle_status.primitive_cycle_index,
            cell_entry_enabled=bool(self.cell_entry_enabled),
            cell_entry_trace_count=int(len(self._cell_entry_trace)),
            dig_cut_token_dim=int(DIG_CUT_TOKEN_DIM),
            return_target_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_target_token_source=str(self._return_target_token_source),
            return_to_dig_max_entry_error_m=self.return_to_dig_max_entry_error_m,
            return_to_dig_entry_error_m=(
                return_status.return_to_dig_entry_error_m
            ),
            return_to_dig_entry_close=return_status.return_to_dig_entry_close,
            return_next_dig_event_seen=return_status.return_next_dig_event_seen,
            return_to_dig_start_envelope_gate_enabled=(
                return_status.return_to_dig_start_envelope_gate_enabled
            ),
            return_to_dig_start_envelope_direct_handoff_enabled=(
                return_status
                .return_to_dig_start_envelope_direct_handoff_enabled
            ),
            return_to_dig_start_envelope_ready=(
                return_status.return_to_dig_start_envelope_ready
            ),
            return_to_dig_start_envelope_plane_depth_mode=(
                return_status.return_to_dig_start_envelope_plane_depth_mode
            ),
            return_to_dig_start_envelope_local_depth_tolerance_m=(
                return_status
                .return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            return_to_dig_start_envelope_error=(
                return_status.return_to_dig_start_envelope_error
            ),
            token=token_status,
            dig_failed_replan_next_skill=str(self.dig_failed_replan_next_skill),
            coverage=coverage_status,
            scripted_bootstrap_timeout_count=(
                scripted_bootstrap_status.timeout_count
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
            dig_bad_replan_count=cycle_status.dig_bad_replan_count,
            dig_exit_guard_replan_count=(
                cycle_status.dig_exit_guard_replan_count
            ),
        )

    def planner_trace(self) -> dict[str, object]:
        return self._runtime_kernel().planner_trace()

    @staticmethod
    def _planner_trace_builder() -> PrimitivePlannerTraceBuilder:
        return PrimitivePlannerTraceBuilder()

    def _planner_trace_inputs(self) -> PrimitivePlannerTraceInputs:
        coverage = self._coverage_report_service().trace_status(
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            candidate_layout=str(self.coverage_candidate_layout),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            pass_index=int(self._coverage_pass_index),
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            corridors=[
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ],
            decision_trace=self._coverage_decision_trace,
            terminal_stop_requested=bool(
                self._coverage_terminal_stop_requested
            ),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )
        return PrimitivePlannerTraceInputs(
            cell_entry_trace=self._cell_entry_trace,
            token=self._token_report_status(),
            return_target_planner_enabled=bool(self.return_target_planner_enabled),
            coverage=coverage,
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
            execution_state=self._primitive_execution_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
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
            should_pre_dig_align_before_dig=(
                lambda: self._should_pre_dig_align_before_dig()
            ),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )

    def _set_skill(self, skill_name: str, reason: str) -> None:
        self._primitive_skill_lifecycle().set_skill(skill_name, reason)

    def _primitive_skill_lifecycle(self) -> PrimitiveSkillLifecycleService:
        return PrimitiveSkillLifecycleService.from_ports(
            self._primitive_skill_lifecycle_ports()
        )

    def _primitive_skill_lifecycle_ports(self) -> PrimitiveSkillLifecyclePorts:
        return PrimitiveSkillLifecyclePorts(
            execution_state=self._primitive_execution_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            pre_dig_align_state=(
                self._primitive_pre_dig_align_compatibility_runtime_state()
            ),
            coverage_state=self._coverage_runtime_state(),
            reset_active_policy=lambda: self._active_policy().reset(),
            clear_dig_cut_plan=lambda: self._clear_dig_cut_plan(),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )

    def _primitive_dig_recovery(self) -> PrimitiveDigRecoveryService:
        return PrimitiveDigRecoveryService.from_ports(
            self._primitive_dig_recovery_ports()
        )

    def _primitive_dig_recovery_ports(self) -> PrimitiveDigRecoveryPorts:
        return PrimitiveDigRecoveryPorts(
            execution_state=self._primitive_execution_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            token_state=self._primitive_token_runtime_state(),
            pre_dig_align_state=(
                self._primitive_pre_dig_align_compatibility_runtime_state()
            ),
            reset_active_policy=lambda: self._active_policy().reset(),
            invalidate_pending_dig_cut_plan=(
                lambda: self._invalidate_pending_dig_cut_plan()
            ),
            clear_dig_cut_plan=lambda: self._clear_dig_cut_plan(),
            build_operator_prior_coverage_dig_cut_tokens=(
                lambda obs: self._build_operator_prior_coverage_dig_cut_tokens(obs)
            ),
            raw_fields_in_prior_range=(
                lambda raw_fields: self._raw_fields_in_prior_range(raw_fields)
            ),
            pre_dig_align_entry_error=(
                lambda obs: self._pre_dig_align_entry_error(obs)
            ),
            pre_dig_align_timeout_can_handoff=(
                lambda obs: self._pre_dig_align_timeout_can_handoff(obs)
            ),
            set_skill=lambda skill_name, reason: self._set_skill(
                skill_name,
                reason,
            ),
            record_coverage_decision_event=(
                lambda event, *, obs, corridor, extra: (
                    self._record_coverage_decision_event(
                        event,
                        obs=obs,
                        corridor=corridor,
                        extra=extra,
                    )
                )
            ),
            request_coverage_terminal_stop=(
                lambda reason, *, replace=False: (
                    self._request_coverage_terminal_stop(
                        reason,
                        replace=replace,
                    )
                )
            ),
            mass_in_bucket=lambda obs: self._mass_in_bucket(obs),
            should_pre_dig_align_before_dig=(
                lambda: self._should_pre_dig_align_before_dig()
            ),
            should_pre_dig_align_after_failed_dig=(
                lambda: self._should_pre_dig_align_after_failed_dig()
            ),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            dig_failed_replan_next_skill=(
                lambda: str(self.dig_failed_replan_next_skill)
            ),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )

    def _restart_pre_dig_align(self, reason: str) -> None:
        self._primitive_dig_recovery().restart_pre_dig_align(reason)

    def _try_replan_pre_dig_align_handoff(self, obs: dict) -> bool:
        return self._primitive_dig_recovery().try_replan_pre_dig_align_handoff(obs)

    def _restart_dig_with_new_cut(self, reason: str) -> None:
        self._primitive_dig_recovery().restart_dig_with_new_cut(reason)

    def _stop_after_failed_dig(self, reason: str, obs: dict) -> None:
        self._primitive_dig_recovery().stop_after_failed_dig(reason, obs)

    def _restart_after_failed_dig(self, reason: str, obs: dict) -> None:
        self._primitive_dig_recovery().restart_after_failed_dig(reason, obs)

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
        scripted_bootstrap = self._primitive_scripted_bootstrap_runtime_service()
        if scripted_bootstrap.enabled():
            return scripted_bootstrap.should_end_bootstrap(obs)
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

    def _primitive_scripted_bootstrap_runtime_config(
        self,
    ) -> PrimitiveScriptedBootstrapRuntimeConfig:
        return PrimitiveScriptedBootstrapRuntimeConfig(
            action_dim=int(self.action_dim),
            bootstrap_end_mode=str(self.bootstrap_end_mode),
            target_qpos=self.scripted_bootstrap_target_qpos,
            kp=float(self.scripted_bootstrap_kp),
            kd=float(self.scripted_bootstrap_kd),
            action_clip=self.scripted_bootstrap_action_clip,
            action_signs=self.scripted_bootstrap_action_signs,
            qpos_tolerance=float(self.scripted_bootstrap_qpos_tolerance),
            qvel_abs_max=float(self.scripted_bootstrap_qvel_abs_max),
            hold_steps=int(self.scripted_bootstrap_hold_steps),
            max_steps=int(self.scripted_bootstrap_max_steps),
        )

    def _primitive_scripted_bootstrap_runtime_service(
        self,
    ) -> PrimitiveScriptedBootstrapRuntimeService:
        return PrimitiveScriptedBootstrapRuntimeService(
            config=self._primitive_scripted_bootstrap_runtime_config(),
            state=self._primitive_scripted_bootstrap_runtime_state(),
        )

    def _scripted_bootstrap_enabled(self) -> bool:
        return self._primitive_scripted_bootstrap_runtime_service().enabled()

    def _scripted_bootstrap_target_reached(self, obs: dict) -> bool:
        return self._primitive_scripted_bootstrap_runtime_service().target_reached(
            obs
        )

    def _scripted_bootstrap_action(self, obs: dict) -> np.ndarray:
        return self._primitive_scripted_bootstrap_runtime_service().action(obs)

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
        mass = self._mass_in_bucket(obs)
        self._primitive_cycle_runtime_state().update_dig_progress(
            mass_in_bucket_kg=float(mass),
            plateau_epsilon_kg=float(self.dig_to_carry_mass_plateau_epsilon_kg),
        )
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
        if self.return_to_dig_max_entry_error_m is None:
            close = True
        elif not np.isfinite(entry_error):
            close = True
        else:
            close = bool(
                float(entry_error) <= float(self.return_to_dig_max_entry_error_m)
            )
        self._primitive_return_runtime_state().set_entry_close_result(
            error_m=float(entry_error),
            close=close,
        )
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
        self._primitive_return_runtime_state().apply_start_envelope_gate_result(
            ready=bool(result.ready),
            error=float(result.error),
            checks=dict(result.checks),
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
        self._primitive_observation_injection_runtime_state().clear()

    def _apply_policy_observation_assembly(
        self,
        result: PrimitivePolicyObservationAssemblyResult,
    ) -> None:
        self._primitive_observation_injection_runtime_state().apply_token_injection_state(
            result.token_injection_state
        )

    def _return_target_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        return self._primitive_token_runtime().return_target_tokens_for_obs(obs)

    def _return_relocate_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        return self._primitive_token_runtime().return_relocate_tokens_for_obs(obs)

    def _return_start_envelope_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        return self._primitive_token_runtime().return_start_envelope_tokens_for_obs(obs)

    def _ensure_return_target_plan_for_cycle(self, obs: dict) -> None:
        self._primitive_token_runtime().ensure_return_target_plan_for_cycle(obs)

    def _dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        return self._primitive_token_runtime().dig_cut_tokens_for_obs(obs)

    def _dig_depth_profile_tokens_for_obs(self, obs: dict) -> np.ndarray | None:
        return self._primitive_token_runtime().dig_depth_profile_tokens_for_obs(obs)

    def _ensure_dig_cut_plan_for_cycle(self, obs: dict) -> None:
        self._primitive_token_runtime().ensure_dig_cut_plan_for_cycle(obs)

    def _primitive_token_runtime(self) -> PrimitiveTokenRuntimeCoordinator:
        return PrimitiveTokenRuntimeCoordinator.from_ports(
            self._primitive_token_runtime_ports()
        )

    def _primitive_token_runtime_ports(self) -> PrimitiveTokenRuntimePorts:
        return PrimitiveTokenRuntimePorts(
            state=self._primitive_token_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            current_skill_name=lambda: str(self._skill_name),
            bootstrap_policy_available=lambda: self.bootstrap_policy is not None,
            cycle_index=lambda: int(self._cycle_index),
            dig_cut_planner_enabled=lambda: bool(self.dig_cut_planner_enabled),
            dig_cut_hold_token_until_skill_exit=(
                lambda: bool(self.dig_cut_hold_token_until_skill_exit)
            ),
            coverage_terminal_stop_requested=(
                lambda: bool(self._coverage_terminal_stop_requested)
            ),
            return_target_planner_enabled=(
                lambda: bool(self.return_target_planner_enabled)
            ),
            return_target_hold_token_until_skill_exit=(
                lambda: bool(self.return_target_hold_token_until_skill_exit)
            ),
            build_dig_cut_tokens_for_obs=(
                lambda obs: self._build_dig_cut_tokens_for_obs(obs)
            ),
            build_dig_depth_profile_tokens_for_obs=(
                lambda obs: self._build_dig_depth_profile_tokens_for_obs(obs)
            ),
            build_next_dig_cut_plan_for_return=(
                lambda obs: self._build_next_dig_cut_plan_for_return(obs)
            ),
            build_return_start_envelope_tokens_for_obs=(
                lambda obs, raw_fields, *, corridor_id: (
                    self._build_return_start_envelope_tokens_for_obs(
                        obs,
                        raw_fields,
                        corridor_id=corridor_id,
                    )
                )
            ),
            plan_return_relocate_tokens=(
                lambda token: self._return_relocate_token_planner().plan(token)
            ),
            dig_skill_name="dig",
            return_skill_name="return",
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
        )

    def _primitive_dig_token_planning_service(
        self,
    ) -> PrimitiveDigTokenPlanningService:
        return PrimitiveDigTokenPlanningService.from_ports(
            self._primitive_dig_token_planning_ports()
        )

    def _primitive_dig_token_planning_ports(
        self,
    ) -> PrimitiveDigTokenPlanningPorts:
        return PrimitiveDigTokenPlanningPorts(
            token_state=self._primitive_token_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            dig_cut_planner_fallback_mode=(
                lambda: str(self.dig_cut_planner_fallback_mode)
            ),
            cycle_index=lambda: int(self._cycle_index),
            dig_cut_token_planner=lambda: self._dig_cut_token_planner(),
            dig_depth_profile_token_planner=(
                lambda: self._dig_depth_profile_token_planner()
            ),
            bucket_dig_area_pose=lambda obs: self._bucket_dig_area_pose(obs),
            deposited_mass=lambda obs: self._deposited_mass(obs),
            env_state=lambda obs: self._env_state(obs),
            select_next_coverage_corridor=(
                lambda obs: self._select_next_coverage_corridor(obs)
            ),
            coverage_raw_fields=(
                lambda corridor, *, obs, update_state=False: self._coverage_raw_fields(
                    corridor,
                    obs=obs,
                    update_state=update_state,
                )
            ),
        )

    def _build_dig_depth_profile_tokens_for_obs(self, obs: dict) -> np.ndarray:
        return (
            self._primitive_dig_token_planning_service()
            .build_dig_depth_profile_tokens_for_obs(obs)
        )

    def _apply_dig_depth_profile_token_plan(
        self,
        plan: DigDepthProfileTokenPlan,
    ) -> np.ndarray:
        return (
            self._primitive_dig_token_planning_service()
            .apply_dig_depth_profile_token_plan(plan)
        )

    def _build_live_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict,
        *,
        cell_id: int,
    ) -> np.ndarray:
        return (
            self._primitive_dig_token_planning_service()
            .build_live_dig_depth_profile_tokens_for_obs(
                obs,
                cell_id=cell_id,
            )
        )

    def _dig_depth_profile_prior_token(
        self,
        cell_id: int,
    ) -> tuple[np.ndarray | None, str, str]:
        return (
            self._primitive_dig_token_planning_service()
            .dig_depth_profile_prior_token(cell_id)
        )

    def _dig_depth_profile_prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object] | None, str, str]:
        return (
            self._primitive_dig_token_planning_service()
            .dig_depth_profile_prior_mapping(cell_id)
        )

    @staticmethod
    def _dig_depth_profile_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        service_class = PrimitiveDigTokenPlanningService
        return service_class.dig_depth_profile_token_from_prior_mapping(mapping)

    def _dig_depth_profile_raw_fields(self, obs: dict) -> dict[str, float | int]:
        return (
            self._primitive_dig_token_planning_service()
            .dig_depth_profile_raw_fields(obs)
        )

    def _dig_depth_profile_cell_id(self, obs: dict) -> int:
        return (
            self._primitive_dig_token_planning_service()
            .dig_depth_profile_cell_id(obs)
        )

    def _build_dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray:
        return (
            self._primitive_dig_token_planning_service()
            .build_dig_cut_tokens_for_obs(obs)
        )

    def _apply_dig_cut_token_plan(self, plan: DigCutTokenPlan) -> np.ndarray:
        return (
            self._primitive_dig_token_planning_service()
            .apply_dig_cut_token_plan(plan)
        )

    def _primitive_return_token_planning_service(
        self,
    ) -> PrimitiveReturnTokenPlanningService:
        return PrimitiveReturnTokenPlanningService.from_ports(
            self._primitive_return_token_planning_ports()
        )

    def _primitive_return_token_planning_ports(
        self,
    ) -> PrimitiveReturnTokenPlanningPorts:
        return PrimitiveReturnTokenPlanningPorts(
            token_state=self._primitive_token_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            return_target_token_planner=lambda: self._return_target_token_planner(),
            return_start_envelope_token_planner=(
                lambda: self._return_start_envelope_token_planner()
            ),
            bucket_dig_area_pose=lambda obs: self._bucket_dig_area_pose(obs),
            select_next_coverage_corridor=(
                lambda obs: self._select_next_coverage_corridor(obs)
            ),
            coverage_raw_fields=(
                lambda corridor, *, obs, update_state: self._coverage_raw_fields(
                    corridor,
                    obs=obs,
                    update_state=update_state,
                )
            ),
            env_state=lambda obs: self._env_state(obs),
            qpos=(
                lambda obs: np.asarray(
                    obs.get("qpos", np.zeros(self.action_dim)),
                    dtype=np.float32,
                ).reshape(-1)
            ),
            qvel=(
                lambda obs: np.asarray(
                    obs.get("qvel", np.zeros(self.action_dim)),
                    dtype=np.float32,
                ).reshape(-1)
            ),
        )

    def _build_next_dig_cut_plan_for_return(
        self,
        obs: dict,
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        return (
            self._primitive_return_token_planning_service()
            .build_next_dig_cut_plan_for_return(obs)
        )

    @staticmethod
    def _unpack_return_target_token_plan(
        plan: ReturnTargetTokenPlan,
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        return PrimitiveReturnTokenPlanningService.unpack_return_target_token_plan(
            plan
        )

    def _build_return_start_envelope_tokens_for_obs(
        self,
        obs: dict,
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        return (
            self._primitive_return_token_planning_service()
            .build_return_start_envelope_tokens_for_obs(
                obs,
                raw_fields,
                corridor_id=corridor_id,
            )
        )

    def _apply_return_start_envelope_token_plan(
        self,
        plan: ReturnStartEnvelopeTokenPlan,
    ) -> np.ndarray:
        return (
            self._primitive_return_token_planning_service()
            .apply_return_start_envelope_token_plan(plan)
        )

    def _maybe_condition_return_start_envelope_qpos_from_relocate(
        self,
        token: np.ndarray,
        *,
        raw_fields: dict[str, float | int],
        source: str,
    ) -> np.ndarray:
        return (
            self._primitive_return_token_planning_service()
            .condition_return_start_envelope_qpos_from_relocate(
                token,
                raw_fields=raw_fields,
                source=source,
            )
        )

    def _return_start_envelope_prior_token(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, str]:
        return (
            self._primitive_return_token_planning_service()
            .return_start_envelope_prior_token(corridor_id=corridor_id)
        )

    def _return_start_envelope_prior_mapping(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[dict[str, object] | None, str]:
        return (
            self._primitive_return_token_planning_service()
            .return_start_envelope_prior_mapping(corridor_id=corridor_id)
        )

    def _return_start_envelope_prior_bounds(
        self,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        return (
            self._primitive_return_token_planning_service()
            .return_start_envelope_prior_bounds(corridor_id)
        )

    def _return_start_envelope_cell_id(self, corridor_id: int | None) -> int | None:
        return (
            self._primitive_return_token_planning_service()
            .return_start_envelope_cell_id(corridor_id)
        )

    @staticmethod
    def _return_start_envelope_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        service_class = PrimitiveReturnTokenPlanningService
        return service_class.return_start_envelope_token_from_prior_mapping(mapping)

    @staticmethod
    def _normalize_plane_depth_mode(value: object) -> str:
        return adapter_config.normalize_plane_depth_mode(value)

    @staticmethod
    def _normalize_failed_dig_replan_skill(value: object) -> str:
        return adapter_config.normalize_failed_dig_replan_skill(value)

    def _raw_fields_from_live_pose(self, obs: dict) -> dict[str, float | int]:
        return (
            self._primitive_dig_token_planning_service()
            .raw_fields_from_live_pose(obs)
        )

    def _build_operator_prior_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return (
            self._primitive_dig_token_planning_service()
            .build_operator_prior_dig_cut_tokens(obs)
        )

    def _build_operator_prior_coverage_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return (
            self._primitive_dig_token_planning_service()
            .build_operator_prior_coverage_dig_cut_tokens(obs)
        )

    def _coverage_selection_runtime_ports(self) -> CoverageSelectionRuntimePorts:
        return CoverageSelectionRuntimePorts(
            state=self._coverage_runtime_state(),
            dig_cut_prior=lambda: dict(self.dig_cut_prior or {}),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            candidate_builder=lambda: self._coverage_candidate_builder(),
            selection_service=lambda: self._coverage_selection_service(),
            selection_facts=(
                lambda obs, corridors: self._coverage_selection_facts(
                    obs,
                    corridors,
                )
            ),
            recent_row_reference=lambda: self._coverage_recent_row_reference_corridor(),
            maybe_reopen_pass=(
                lambda obs, reason: self._maybe_reopen_coverage_pass(
                    obs,
                    reason=reason,
                )
            ),
            request_terminal_stop=lambda reason: self._request_coverage_terminal_stop(
                reason
            ),
            record_decision_event=self._record_coverage_decision_event,
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
            state=self._coverage_runtime_state(),
            coverage_mode=lambda: str(self.dig_cut_planner_mode),
            coverage_update_service=lambda: self._coverage_update_service(),
            coverage_runtime_service=lambda: self._coverage_runtime_service(),
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
        self._primitive_token_runtime().clear_dig_cut_plan()

    def _invalidate_pending_dig_cut_plan(self) -> None:
        self._primitive_token_runtime().invalidate_pending_dig_cut_plan()

    def _validate_dig_cut_planner_config(self) -> None:
        adapter_config.validate_dig_cut_planner_config(
            dig_cut_planner_enabled=bool(self.dig_cut_planner_enabled),
            dig_cut_planner_mode=str(self.dig_cut_planner_mode),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            coverage_candidate_layout=str(self.coverage_candidate_layout),
            dig_depth_profile_source=str(self.dig_depth_profile_source),
            dig_depth_profile_required=bool(self.dig_depth_profile_required),
            dig_depth_profile_allow_live_fallback=bool(
                self.dig_depth_profile_allow_live_fallback
            ),
            dig_cut_prior=dict(self.dig_cut_prior or {}),
        )

    @staticmethod
    def _coverage_percentile_list(
        value: object,
        *,
        default: tuple[str, ...],
    ) -> tuple[str, ...]:
        return adapter_config.coverage_percentile_list(value, default=default)

    @staticmethod
    def _coverage_percentile_name(value: object, *, default: str) -> str:
        return adapter_config.coverage_percentile_name(value, default=default)

    def _align_vector(
        self,
        value: object,
        *,
        default: list[float] | tuple[float, ...],
    ) -> np.ndarray:
        return adapter_config.align_vector(
            value,
            default=default,
            action_dim=int(self.action_dim),
        )

    def _optional_align_vector(self, value: object) -> np.ndarray | None:
        return adapter_config.optional_align_vector(
            value,
            action_dim=int(self.action_dim),
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        return adapter_config.optional_float(value)

    @staticmethod
    def _load_dig_cut_prior(path: str) -> dict[str, Any]:
        return adapter_config.load_dig_cut_prior(path)

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
        return adapter_config.normalize_goal_sequence(goal_sequence)

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
        cycle_status = self._cycle_report_status()
        return PrimitiveTickFinalizationInputs(
            skill_name=str(self._skill_name),
            skill_ids=PRIMITIVE_SKILL_IDS,
            skill_switch_reason=str(self._switch_reason),
            primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            first_dig_policy_active=bool(self._first_dig_policy_active()),
            transition_skill_names=("return", PRE_DIG_ALIGN_SKILL_NAME),
            transition_timeout=bool(transition_timeout),
            transition_completed=bool(transition_completed),
            completed_transition_count=cycle_status.completed_transition_count,
            transition_timeout_count=cycle_status.transition_timeout_count,
            dump_ready_hold_count=cycle_status.dump_ready_hold_count,
            dump_done_hold_count=cycle_status.dump_done_hold_count,
            primitive_cycle_index=cycle_status.primitive_cycle_index,
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
