"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from testbed.contracts.primitive_profile import (
    CYCLE_BOUNDARY_PROFILE_LEGACY,
    is_v2_4_5_cycle_boundary_profile,
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
from testbed.planner import primitive_config as primitive_config_helpers
from testbed.planner.bootstrap import (
    BOOTSTRAP_CONFIG_KEYS,
    BOOTSTRAP_RUNTIME_CONFIG_FIELDS,
    BOOTSTRAP_RUNTIME_STATUS_FIELDS,
    BootstrapConfig,
    BootstrapEndDecision,
    BootstrapFacts,
    BootstrapPlannerConfig,
    BootstrapRuntimeStatusSnapshot,
    BootstrapRuntimeStatusState,
    BootstrapService,
    BootstrapTargetDecision,
    BootstrapTransitionDecision,
    build_bootstrap_config_from_mapping,
    build_bootstrap_planner_config_from_mapping,
    build_bootstrap_runtime_status_state_from_mapping,
)
from testbed.planner.boundary_detector import BoundaryDetector
from testbed.planner.cell_entry import (
    CELL_ENTRY_CONFIG_KEYS,
    CELL_ENTRY_RUNTIME_STATE_FIELDS,
    CELL_ENTRY_TOKEN_DIM,
    CellEntryDebugSnapshot,
    CellEntryPlanner,
    CellEntryPlannerConfig,
    CellEntryRuntimeCompletionResult,
    CellEntryRuntimeConfig,
    CellEntryRuntimeFacts,
    CellEntryRuntimeService,
    CellEntryRuntimeState,
    CellEntryRuntimeTokenResult,
    PlannerDecisionAuditor,
    build_cell_entry_planner_config_from_mapping,
    build_cell_entry_runtime_state_from_mapping,
)
from testbed.planner.dig_coverage import DigCoverageMixin
from testbed.planner.dig_cut_plan import (
    DIG_CUT_PLAN_DISPATCH_FACT_FIELDS,
    DIG_CUT_RUNTIME_STATUS_CONFIG_FIELDS,
    DIG_CUT_RUNTIME_STATUS_STATE_FIELDS,
    DigCutPlanClearState,
    DigCutPlanCycleApplyState,
    DigCutPlanDispatchFacts,
    DigCutPlanService,
    DigCutPlanState,
    DigCutPlanTokenResult,
    DigCutRuntimeState,
    DigCutRuntimeStatusSnapshot,
    OperatorPriorDigCutPlanRequest,
    build_conservative_pose_dig_cut_plan,
    build_dig_cut_plan_dispatch_facts_from_mapping,
    build_operator_prior_dig_cut_plan,
    build_raw_fields_dig_cut_plan,
)
from testbed.planner.dig_cut_plan import (
    raw_fields_from_live_pose as dig_cut_raw_fields_from_live_pose,
)
from testbed.planner.dig_depth_profile import (
    DIG_DEPTH_PROFILE_CONFIG_FIELDS,
    DIG_DEPTH_PROFILE_RUNTIME_STATUS_STATE_FIELDS,
    DigDepthProfileBuildRequest,
    DigDepthProfileConfig,
    DigDepthProfileInputFacts,
    DigDepthProfileInputSourceCallbacks,
    DigDepthProfileMissingPriorError,
    DigDepthProfileRuntimeState,
    DigDepthProfileRuntimeStatusSnapshot,
    DigDepthProfileService,
    DigDepthProfileState,
    DigDepthProfileTokenResult,
    build_dig_depth_profile_config_from_mapping,
)
from testbed.planner.dig_lifecycle import (
    DIG_LIFECYCLE_CONFIG_KEYS,
    DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS,
    DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS,
    DIG_LIFECYCLE_RUNTIME_STATUS_FIELDS,
    DigLifecycleConfig,
    DigLifecycleEntryRuntimeState,
    DigLifecycleFacts,
    DigLifecycleGateService,
    DigLifecyclePlannerConfig,
    DigLifecycleRuntimeStatusSnapshot,
    DigLifecycleRuntimeStatusState,
    DigProgressState,
    DigTransitionRuntimeProjection,
    FailedDigRecoveryDecision,
    FailedDigRecoveryFacts,
    FailedDigStopState,
    build_dig_lifecycle_config_from_mapping,
    build_dig_lifecycle_entry_runtime_facts_from_mapping,
    build_dig_lifecycle_runtime_config_from_mapping,
    build_dig_lifecycle_runtime_status_state_from_mapping,
    build_failed_dig_stop_facts_from_runtime,
)
from testbed.planner.dig_start_alignment import (
    DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS,
    DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS,
    DigStartAlignmentDebugSnapshot,
    DigStartAlignmentRuntimeState,
    DigStartAlignmentService,
    debug_state_from_mapping,
    runtime_state_from_mapping,
)
from testbed.planner.dig_start_alignment_action import (
    AlignmentActionDecision,
    pd_servo_action,
)
from testbed.planner.dig_start_alignment_context import (
    DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS,
    DigStartAlignmentConfig,
    DigStartAlignmentFacts,
    build_dig_start_alignment_runtime_config_from_mapping,
)
from testbed.planner.dig_start_alignment_outcome import (
    PreDigAlignOutcome,
)
from testbed.planner.dig_start_alignment_readiness import (
    AlignmentReadyDecision,
    SurfaceGuardDecision,
    TimeoutHandoffDecision,
)
from testbed.planner.dig_start_alignment_runtime import (
    PreDigAlignOutcomeRuntimeProjection,
)
from testbed.planner.dump_lifecycle import (
    DUMP_LIFECYCLE_CONFIG_KEYS,
    DUMP_LIFECYCLE_RUNTIME_CONFIG_KEYS,
    DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS,
    CarryTransitionRuntimeState,
    DumpLifecycleConfig,
    DumpLifecycleFacts,
    DumpLifecycleGateService,
    DumpLifecyclePlannerConfig,
    DumpLifecycleRuntimeState,
    DumpLifecycleRuntimeStatusSnapshot,
    DumpLifecycleRuntimeStatusState,
    DumpTransitionRuntimeState,
    build_carry_transition_runtime_request,
    build_dump_lifecycle_config_from_mapping,
    build_dump_lifecycle_runtime_config_from_mapping,
    build_dump_lifecycle_runtime_status_state_from_mapping,
    build_dump_transition_runtime_request,
)
from testbed.planner.goal_sequence import (
    GOAL_SEQUENCE_CONFIG_KEYS,
    GoalSequenceConfig,
    GoalSequenceFacts,
    GoalSequencePlannerConfig,
    GoalSequenceService,
    build_goal_sequence_planner_config_from_mapping,
)
from testbed.planner.policy_observation import (
    DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS,
    POLICY_OBSERVATION_REQUEST_FACT_FIELDS,
    DigConditioningObservationTokenGateDecision,
    PolicyObservationAssembler,
    PolicyObservationAssembly,
    PolicyObservationRequestConfig,
    PolicyObservationTokenRequest,
    PolicyObservationTokens,
)
from testbed.planner.primitive_debug import (
    TRANSITION_POLICY_MODE_PRIMITIVE as TRANSITION_POLICY_MODE_PRIMITIVE,
)
from testbed.planner.primitive_debug import (
    TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY as TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
)
from testbed.planner.primitive_debug import (
    PrimitiveDebugStateFacts,
    PrimitiveDebugStateSnapshotConfig,
    PrimitiveDebugStateSnapshotFacts,
    PrimitivePlannerDebugState,
    PrimitivePlannerTraceFacts,
    PrimitiveRolloutSummaryFacts,
    build_primitive_debug_state_from_facts,
    build_primitive_debug_state_snapshot_from_runtime,
    build_primitive_planner_trace_from_facts,
    build_primitive_rollout_summary_from_facts,
)
from testbed.planner.primitive_debug_facts import (
    PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS,
    PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS,
    PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS,
    build_primitive_debug_state_facts_from_mapping,
    build_primitive_planner_trace_facts_from_mapping,
    build_primitive_rollout_summary_facts_from_mapping,
)
from testbed.planner.primitive_decisions import primitive_boundary_facts_from_event
from testbed.planner.return_handoff import (
    RETURN_TO_DIG_CONFIG_KEYS,
    RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS,
    RETURN_TO_DIG_HANDOFF_STATUS_FIELDS,
    ReturnNextDigEntryTargetResolver,
    ReturnToDigEntryErrorFacts,
    ReturnToDigHandoffConfig,
    ReturnToDigHandoffContext,
    ReturnToDigHandoffDecision,
    ReturnToDigHandoffGateService,
    ReturnToDigHandoffStatusSnapshot,
    ReturnToDigHandoffStatusState,
    ReturnToDigPlannerConfig,
    build_return_next_dig_entry_target_facts_from_runtime,
    build_return_to_dig_config_from_mapping,
    build_return_to_dig_handoff_config_from_mapping,
    build_return_to_dig_handoff_context_from_runtime,
    build_return_to_dig_handoff_status_state_from_mapping,
)
from testbed.planner.return_start_envelope import (
    RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS,
    ReturnStartEnvelopeBuildRequest,
    ReturnStartEnvelopeConfig,
    ReturnStartEnvelopeState,
    build_return_start_envelope_config_from_mapping,
    build_return_start_envelope_for_plan,
    build_return_start_envelope_request_from_observation_view,
    condition_return_start_envelope_from_relocate,
    require_return_start_envelope_token_result,
    resolve_return_start_envelope_cell_id,
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
    PENDING_RETURN_TARGET_ACTIVATION_FACT_FIELDS,
    RETURN_TARGET_CONDITIONING_STATUS_FIELDS,
    PendingDigCutPlanState,
    PendingReturnTargetActivation,
    PendingReturnTargetActivationFacts,
    ReturnRelocateObservationTokenResult,
    ReturnTargetConditioningRuntimeState,
    ReturnTargetConditioningStatusSnapshot,
    ReturnTargetDigCutBuildCallbacks,
    ReturnTargetDigCutBuildResult,
    ReturnTargetPlanBuildFacts,
    ReturnTargetPlanService,
    ReturnTargetPlanState,
    build_pending_return_target_activation_facts_from_mapping,
)
from testbed.planner.return_to_dig_transition import (
    ReturnDirectHandoffRuntimeProjection,
    ReturnToDigTransitionCompletion,
    ReturnToDigTransitionRuntimeProjection,
    ReturnToDigTransitionService,
)
from testbed.planner.snapshots import (
    BoundaryDetectorUpdateFacts,
    PlannerSnapshot,
    boundary_detector_update_facts_from_obs,
    bucket_depth_below_dig_area_plane_from_obs,
    bucket_depth_below_local_surface_from_obs,
    bucket_dig_area_cell_in_bounds_mask_from_obs,
    bucket_dig_area_contact_mask_from_obs,
    bucket_dig_area_pose_from_obs,
    bucket_tip_dig_area_pose_from_obs,
    build_planner_snapshot,
    deposited_mass_from_obs,
    dig_cell_id_from_obs,
    env_state_from_obs,
    mass_in_bucket_from_obs,
    min_distance_to_dig_area_from_obs,
    target_geometry_from_obs,
)
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
        self.return_entry_target_resolver = ReturnNextDigEntryTargetResolver()
        self.return_handoff_gate = ReturnToDigHandoffGateService()
        self.return_transition_service = ReturnToDigTransitionService()
        self.bootstrap_service = BootstrapService()
        self.dig_lifecycle_gate = DigLifecycleGateService()
        self.dig_start_alignment_service = DigStartAlignmentService()
        self.dump_lifecycle_gate = DumpLifecycleGateService()
        self.goal_sequence_service = GoalSequenceService()
        self.policy_observation_assembler = PolicyObservationAssembler()
        self.dig_cut_plan_service = DigCutPlanService()
        self.dig_depth_profile_service = DigDepthProfileService()
        self.return_target_plan_service = ReturnTargetPlanService()
        init_values = locals()
        dig_lifecycle_values = {
            key: init_values[key]
            for key in DIG_LIFECYCLE_CONFIG_KEYS
        }
        self._apply_dig_lifecycle_config(
            build_dig_lifecycle_config_from_mapping(dig_lifecycle_values)
        )
        dump_lifecycle_values = {
            key: init_values[key]
            for key in DUMP_LIFECYCLE_CONFIG_KEYS
        }
        self._apply_dump_lifecycle_config(
            build_dump_lifecycle_config_from_mapping(dump_lifecycle_values)
        )
        init_values = locals()
        return_to_dig_values = {
            key: init_values[key]
            for key in RETURN_TO_DIG_CONFIG_KEYS
        }
        self._apply_return_to_dig_config(
            build_return_to_dig_config_from_mapping(return_to_dig_values)
        )
        self.action_dim = int(action_dim)
        self.primitive_checkpoint_paths = {
            str(name): str(path)
            for name, path in dict(primitive_checkpoint_paths or {}).items()
        }
        bootstrap_values = {
            key: init_values[key]
            for key in BOOTSTRAP_CONFIG_KEYS
        }
        self._apply_bootstrap_config(
            build_bootstrap_planner_config_from_mapping(
                bootstrap_values,
                action_dim=self.action_dim,
            )
        )
        goal_sequence_values = {
            key: init_values[key]
            for key in GOAL_SEQUENCE_CONFIG_KEYS
        }
        self._apply_goal_sequence_config(
            build_goal_sequence_planner_config_from_mapping(goal_sequence_values)
        )
        cell_entry_values = {
            key: init_values[key]
            for key in CELL_ENTRY_CONFIG_KEYS
        }
        self._apply_cell_entry_config(
            build_cell_entry_planner_config_from_mapping(cell_entry_values)
        )
        self.cell_entry_planner = CellEntryPlanner(grid=self.cell_entry_grid)
        self.cell_entry_auditor = PlannerDecisionAuditor(
            grid=self.cell_entry_grid,
            low_productivity_payload_gain_kg=(
                self.cell_entry_low_productivity_payload_gain_kg
            ),
        )
        self.cell_entry_runtime_service = CellEntryRuntimeService()
        self._apply_conditioning_config(
            primitive_config_helpers.build_conditioning_config(
                dig_cut_planner=dig_cut_planner,
                return_target_planner=return_target_planner,
                action_dim=self.action_dim,
                coverage_percentile_list_fn=self._coverage_percentile_list,
                coverage_percentile_name_fn=self._coverage_percentile_name,
            )
        )
        self.coverage_state_exemplars_by_cell = (
            self._load_coverage_state_exemplars()
        )
        self._apply_pre_dig_align_config(
            primitive_config_helpers.build_pre_dig_alignment_config(
                pre_dig_align=pre_dig_align,
                action_dim=self.action_dim,
            )
        )
        self.coverage_service = self._create_coverage_service()
        self._validate_dig_cut_planner_config()
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
        self._reset_dump_lifecycle_runtime()
        self._return_step_count = 0
        self._reset_bootstrap_runtime()
        self._reset_pre_dig_align_runtime()
        self._reset_dig_lifecycle_runtime()
        self._completed_transition_count = 0
        self._transition_timeout_count = 0
        self._cycle_index = 0
        self._reset_cell_entry_runtime()
        self._reset_dig_cut_runtime()
        self._reset_dig_depth_profile_runtime()
        self._reset_return_target_conditioning_runtime()
        self._reset_return_to_dig_handoff_runtime()
        self._debug_state = self._make_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )

    def predict(self, obs: dict) -> np.ndarray:
        boundary_event = None
        if self._prev_action is not None:
            detector_facts = self._boundary_detector_update_facts(obs)
            boundary_event = self.boundary_detector.update(
                env_state=detector_facts.env_state,
                action=detector_facts.action,
                qpos=detector_facts.qpos,
                reward_phase=detector_facts.reward_phase,
                task_step_successes=detector_facts.task_step_successes,
                task_metrics=detector_facts.task_metrics,
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
        return build_primitive_debug_state_from_facts(self._debug_state_facts())

    def rollout_summary(self) -> dict[str, float | int | str | list[str]]:
        return build_primitive_rollout_summary_from_facts(
            self._rollout_summary_facts()
        )

    def planner_trace(self) -> dict[str, object]:
        return build_primitive_planner_trace_from_facts(self._planner_trace_facts())

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self._should_end_bootstrap(obs=obs, boundary_event=boundary_event):
                transition_request = self.bootstrap_service.end_transition_request(
                    pre_dig_align_before_dig=(
                        self._should_pre_dig_align_before_dig()
                    ),
                    pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
                )
                transition = self.bootstrap_service.end_transition(
                    transition_request.facts,
                    self._bootstrap_config(),
                    transition_request.transition_config,
                )
                self._apply_bootstrap_transition_decision(transition)
            return

        if self._skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            outcome = self._pre_dig_align_outcome(obs)
            if self._apply_pre_dig_align_outcome(outcome, obs):
                return
            return

        if self._skill_name == "dig":
            exit_guard_ready = self._dig_exit_guard_ready(obs)
            request = self.dig_lifecycle_gate.dig_transition_runtime_request(
                exit_guard_ready=exit_guard_ready,
            )
            bad_replan_ready = False
            complete_boundary_low_payload = False
            dig_to_carry_ready = False
            dig_to_carry_reason = ""
            if request.should_check_bad_replan:
                bad_replan_ready = self._dig_bad_replan_ready(obs)
            if request.should_check_complete_boundary_low_payload(bad_replan_ready):
                complete_boundary_low_payload = (
                    self._dig_complete_boundary_low_payload(obs, boundary_event)
                )
            if request.should_check_dig_to_carry(
                bad_replan_ready=bad_replan_ready,
                complete_boundary_low_payload=complete_boundary_low_payload,
            ):
                dig_to_carry_ready = self._dig_to_carry_ready(
                    obs=obs,
                    boundary_event=boundary_event,
                )
                if dig_to_carry_ready:
                    dig_to_carry_reason = str(self._dig_to_carry_reason)
            outcome = self.dig_lifecycle_gate.dig_transition_runtime(
                request.facts_with_gate_results(
                    bad_replan_ready=bad_replan_ready,
                    dig_to_carry_reason=dig_to_carry_reason,
                    complete_boundary_low_payload=complete_boundary_low_payload,
                    dig_to_carry_ready=dig_to_carry_ready,
                )
            )
            projection = self.dig_lifecycle_gate.dig_transition_runtime_projection(
                outcome
            )
            if self._apply_dig_transition_runtime_projection(projection, obs):
                return
            return

        if self._skill_name == "carry":
            release_safety_done = self._carry_release_safety_done(obs)
            request = build_carry_transition_runtime_request(
                release_safety_done=release_safety_done,
                boundary_event=boundary_event,
                semantic_boundary_profile_active=(
                    self._semantic_boundary_profile_active()
                ),
                current_dump_ready_hold_count=self._dump_ready_hold_count,
            )
            dump_ready = False
            if request.should_check_dump_ready and self._dump_ready(obs):
                dump_ready = True
            runtime = self.dump_lifecycle_gate.carry_transition_runtime(
                request.facts_with_dump_ready(dump_ready),
                dump_ready_hold_steps=self.dump_ready_hold_steps,
            )
            if self._apply_carry_transition_runtime(runtime, obs):
                return
            return

        if self._skill_name == "dump":
            request = build_dump_transition_runtime_request(
                dump_done_use_boundary_event=self.dump_done_use_boundary_event,
                boundary_event=boundary_event,
                semantic_boundary_profile_active=(
                    self._semantic_boundary_profile_active()
                ),
                current_dump_done_hold_count=self._dump_done_hold_count,
            )
            dump_done = False
            if request.should_check_dump_done and self._dump_done(obs):
                dump_done = True
            runtime = self.dump_lifecycle_gate.dump_transition_runtime(
                request.facts_with_dump_done(dump_done),
                dump_done_hold_steps=self.dump_done_hold_steps,
            )
            if self._apply_dump_transition_runtime(runtime, obs):
                return
            return

        if self._skill_name == "return":
            handoff_ready = self._return_to_dig_handoff_ready(obs)
            request = self.return_transition_service.transition_request(
                handoff_ready=handoff_ready,
                boundary_event=boundary_event,
                previous_next_dig_event_seen=self._return_next_dig_event_seen,
                semantic_boundary_profile_active=(
                    self._semantic_boundary_profile_active()
                ),
            )
            direct_handoff_ready = False
            shallow_guard_ready = False
            if request.should_check_direct_handoff:
                direct_handoff_ready = self._return_to_dig_direct_handoff_ready(
                    obs,
                    handoff_ready=handoff_ready,
                )
            if request.should_check_shallow_guard(direct_handoff_ready):
                shallow_guard_ready = self._return_to_dig_shallow_guard_ready(
                    obs=obs,
                    boundary_event=boundary_event,
                )
            outcome = self.return_transition_service.classify(
                request.facts_with_gate_results(
                    direct_handoff_ready=direct_handoff_ready,
                    shallow_guard_ready=shallow_guard_ready,
                ),
                request.config,
            )
            projection = self.return_transition_service.transition_runtime_projection(
                outcome
            )
            if not self._apply_return_to_dig_transition_runtime_projection(
                projection
            ):
                return
            completion_request = self.return_transition_service.completion_request(
                pre_dig_align_before_dig=self._should_pre_dig_align_before_dig(),
                pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            )
            completion = self.return_transition_service.transition_completion(
                outcome,
                completion_request.facts,
                completion_request.config,
            )
            self._apply_return_to_dig_transition_completion(completion)
            return

    def _set_return_or_direct_handoff(self, obs: dict, *, reason: str) -> None:
        self._set_skill("return", reason)
        self._try_return_direct_handoff_at_current_obs(obs)

    def _try_return_direct_handoff_at_current_obs(self, obs: dict) -> bool:
        request = self.return_transition_service.direct_handoff_attempt_request(
            active_skill_name=self._skill_name,
            return_target_planner_enabled=self.return_target_planner_enabled,
            direct_handoff_enabled=(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
        )
        if not request.should_prepare_return_target:
            return False
        self._ensure_return_target_plan_for_cycle(obs)
        handoff_ready = self._return_to_dig_handoff_ready(obs)
        direct_handoff_ready = self._return_to_dig_direct_handoff_ready(
            obs,
            handoff_ready=handoff_ready,
        )
        attempt = self.return_transition_service.direct_handoff_attempt(
            request.facts_with_gate_results(
                handoff_ready=handoff_ready,
                direct_handoff_ready=direct_handoff_ready,
            ),
            request.config,
        )
        if attempt.action != "direct_handoff":
            return False
        projection = self.return_transition_service.direct_handoff_runtime_projection(
            attempt
        )
        if not self._apply_return_to_dig_transition_runtime_projection(projection):
            return False
        completion_request = self.return_transition_service.completion_request(
            pre_dig_align_before_dig=self._should_pre_dig_align_before_dig(),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )
        completion = self.return_transition_service.direct_handoff_completion(
            attempt,
            completion_request.facts,
            completion_request.config,
        )
        return self._apply_return_to_dig_transition_completion(completion)

    def _apply_bootstrap_transition_decision(
        self,
        decision: BootstrapTransitionDecision,
    ) -> None:
        self._set_skill(decision.next_skill, decision.switch_reason)

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
            self._apply_pre_dig_align_enter_runtime_state()
        elif skill_name == "dig":
            self._return_next_dig_event_seen = False
            self._dump_ready_hold_count = 0
            self._dump_done_hold_count = 0
            self._reset_dig_entry_runtime()
        if skill_name not in {"dig", PRE_DIG_ALIGN_SKILL_NAME}:
            self._clear_dig_cut_plan()

    def _restart_pre_dig_align(self, reason: str) -> None:
        self._skill_name = PRE_DIG_ALIGN_SKILL_NAME
        self._switch_reason = str(reason)
        self._apply_pre_dig_align_restart_runtime_state()
        self._reset_dig_entry_runtime()
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
        entry_error = self._pre_dig_align_entry_error(obs)
        self._apply_pre_dig_align_entry_error_runtime_state(
            entry_error_m=entry_error
        )
        if not self._pre_dig_align_timeout_can_handoff(obs):
            return False
        self._apply_pre_dig_align_replan_handoff_runtime_state()
        self._set_skill("dig", "pre_dig_align_replan_to_dig_entry_close")
        return True

    def _restart_dig_with_new_cut(self, reason: str) -> None:
        self._skill_name = "dig"
        self._switch_reason = str(reason)
        self._active_policy().reset()
        self._reset_dig_entry_runtime()
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
        stop_state = self.dig_lifecycle_gate.failed_dig_stop_state(
            build_failed_dig_stop_facts_from_runtime(
                reason=reason,
                coverage_current_payload_gain_kg=(
                    self._coverage_current_payload_gain_kg
                ),
                dig_best_mass_kg=self._dig_best_mass_kg,
                current_bucket_mass_kg=self._mass_in_bucket(obs),
                dig_step_count=self._dig_step_count,
                switch_reason=switch_reason,
                terminal_reason=terminal_reason,
            )
        )
        self._apply_failed_dig_stop_state(stop_state, obs=obs, corridor=corridor)

    def _apply_failed_dig_stop_state(
        self,
        state: FailedDigStopState,
        *,
        obs: dict,
        corridor: Any | None,
    ) -> None:
        self._switch_reason = str(state.switch_reason)
        self._record_coverage_decision_event(
            state.coverage_event,
            obs=obs,
            corridor=corridor,
            extra=state.coverage_event_extra,
        )
        self._request_coverage_terminal_stop(
            state.terminal_reason,
            replace=bool(state.terminal_stop_replace),
        )

    def _restart_after_failed_dig(self, reason: str, obs: dict) -> None:
        decision = self.dig_lifecycle_gate.failed_dig_recovery(
            reason=reason,
            facts=FailedDigRecoveryFacts(
                cycle_index=int(getattr(self, "_cycle_index", 0))
            ),
            config=self._dig_lifecycle_config(),
        )
        self._apply_failed_dig_recovery_decision(
            decision,
            reason=reason,
            obs=obs,
        )

    def _apply_failed_dig_recovery_decision(
        self,
        decision: FailedDigRecoveryDecision,
        *,
        reason: str,
        obs: dict,
    ) -> None:
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
        return self._apply_bootstrap_end_decision(decision)

    def _apply_bootstrap_end_decision(
        self,
        decision: BootstrapEndDecision,
    ) -> bool:
        self._scripted_bootstrap_hold_count = int(decision.hold_count)
        if decision.timeout_increment:
            self._scripted_bootstrap_timeout_count += 1
        return bool(decision.should_end)

    def _apply_bootstrap_target_decision(
        self,
        decision: BootstrapTargetDecision,
    ) -> bool:
        self._scripted_bootstrap_hold_count = int(decision.hold_count)
        return bool(decision.ready)

    def _bootstrap_config(self) -> BootstrapConfig:
        return build_bootstrap_config_from_mapping(
            {
                config_key: getattr(self, attr_name)
                for config_key, attr_name in BOOTSTRAP_RUNTIME_CONFIG_FIELDS
            },
            action_dim=int(self.action_dim),
        )

    def _bootstrap_facts(
        self,
        *,
        obs: dict,
        boundary_event: Any | None = None,
    ) -> BootstrapFacts:
        snapshot = self._make_snapshot(obs, boundary_event=boundary_event)
        return self.bootstrap_service.facts_from_observation_view(
            view=snapshot.view,
            boundary_event=boundary_event,
            step_count=self._scripted_bootstrap_step_count,
            hold_count=self._scripted_bootstrap_hold_count,
            bootstrap_policy_present=self.bootstrap_policy is not None,
        )

    def _bootstrap_runtime_status_snapshot(self) -> BootstrapRuntimeStatusSnapshot:
        return self.bootstrap_service.runtime_status_snapshot(
            build_bootstrap_runtime_status_state_from_mapping(
                {
                    field_name: getattr(self, attr_name)
                    for field_name, attr_name in BOOTSTRAP_RUNTIME_STATUS_FIELDS
                }
            )
        )

    def _reset_bootstrap_runtime(self) -> None:
        state = self.bootstrap_service.initial_runtime_state()
        self._apply_bootstrap_runtime_state(state)

    def _apply_bootstrap_runtime_state(
        self,
        state: BootstrapRuntimeStatusState,
    ) -> None:
        self._scripted_bootstrap_step_count = int(state.step_count)
        self._scripted_bootstrap_hold_count = int(state.hold_count)
        self._scripted_bootstrap_timeout_count = int(state.timeout_count)

    def _reset_dump_lifecycle_runtime(self) -> None:
        state = self.dump_lifecycle_gate.initial_runtime_state()
        self._apply_dump_lifecycle_runtime_state(state)

    def _dump_lifecycle_runtime_status_snapshot(
        self,
    ) -> DumpLifecycleRuntimeStatusSnapshot:
        return self.dump_lifecycle_gate.runtime_status_snapshot(
            build_dump_lifecycle_runtime_status_state_from_mapping(
                {
                    field_name: getattr(self, attr_name)
                    for (
                        field_name,
                        attr_name,
                    ) in DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS
                }
            )
        )

    def _apply_dump_lifecycle_runtime_state(
        self,
        state: DumpLifecycleRuntimeState,
    ) -> None:
        self._dump_ready_hold_count = int(state.ready_hold_count)
        self._dump_done_hold_count = int(state.done_hold_count)
        self._dump_start_deposited_mass_kg = float(state.start_deposited_mass_kg)

    def _apply_carry_transition_runtime(
        self,
        runtime: CarryTransitionRuntimeState,
        obs: dict,
    ) -> bool:
        self._dump_ready_hold_count = int(runtime.dump_ready_hold_count)
        outcome = runtime.outcome
        if outcome.action == "return":
            self._complete_coverage_dump(obs, reason=outcome.coverage_reason)
            self._set_return_or_direct_handoff(obs, reason=outcome.switch_reason)
            return True
        if outcome.action == "dump":
            self._dump_start_deposited_mass_kg = self._deposited_mass(obs)
            self._set_skill("dump", outcome.switch_reason)
            return True
        return False

    def _apply_dump_transition_runtime(
        self,
        runtime: DumpTransitionRuntimeState,
        obs: dict,
    ) -> bool:
        self._dump_done_hold_count = int(runtime.dump_done_hold_count)
        outcome = runtime.outcome
        if outcome.action == "return":
            self._complete_coverage_dump(obs, reason=outcome.coverage_reason)
            self._set_return_or_direct_handoff(
                obs,
                reason=outcome.switch_reason,
            )
            return True
        return False

    def _apply_pre_dig_align_outcome_runtime_projection(
        self,
        projection: PreDigAlignOutcomeRuntimeProjection,
        obs: dict,
    ) -> bool:
        if projection.transition_action != "none":
            self._apply_pre_dig_align_runtime_state(projection.runtime_state)
        if projection.should_handoff_to_dig:
            self._set_skill("dig", projection.switch_reason)
            return True
        if projection.should_restart_dig_with_new_cut:
            self._reject_active_coverage_corridor(
                obs,
                reason=projection.reject_reason,
            )
            self._restart_dig_with_new_cut(projection.switch_reason)
            return True
        if projection.should_try_replan_handoff:
            self._reject_active_coverage_corridor(
                obs,
                reason=projection.reject_reason,
            )
            if not self._try_replan_pre_dig_align_handoff(obs):
                self._restart_pre_dig_align(projection.switch_reason)
            return True
        return False

    def _apply_pre_dig_align_outcome(
        self,
        outcome: PreDigAlignOutcome,
        obs: dict,
    ) -> bool:
        projection = (
            self.dig_start_alignment_service.outcome_runtime_projection_from_state(
                outcome=outcome,
                state=self._pre_dig_align_runtime_state(),
            )
        )
        return self._apply_pre_dig_align_outcome_runtime_projection(projection, obs)

    def _scripted_bootstrap_enabled(self) -> bool:
        return self.bootstrap_service.scripted_enabled(self._bootstrap_config())

    def _scripted_bootstrap_target_reached(self, obs: dict) -> bool:
        decision = self.bootstrap_service.scripted_target_reached(
            self._bootstrap_facts(obs=obs),
            self._bootstrap_config(),
        )
        return self._apply_bootstrap_target_decision(decision)

    def _scripted_bootstrap_action(self, obs: dict) -> np.ndarray:
        if self.scripted_bootstrap_target_qpos is None:
            raise RuntimeError("scripted bootstrap is active without target qpos.")
        self._scripted_bootstrap_step_count += 1
        return self.bootstrap_service.scripted_action(
            self._bootstrap_facts(obs=obs),
            self._bootstrap_config(),
        )

    def _pre_dig_align_surface_guard_triggered_for_state(self, obs: dict) -> bool:
        snapshot = build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        entry_error = self._pre_dig_align_entry_error(obs)
        decision = (
            self.dig_start_alignment_service.surface_guard_triggered_from_observation_view(
                view=snapshot.view,
                config=self._dig_start_alignment_config(),
                entry_error_m=entry_error,
                cycle_index=getattr(self, "_cycle_index", 0),
                hold_count=self._pre_dig_align_hold_count,
            )
        )
        return self._apply_pre_dig_align_surface_guard_decision(decision)

    def _pre_dig_align_surface_guard_can_handoff(self, obs: dict) -> bool:
        self._ensure_dig_cut_plan_for_cycle(obs)
        entry_error = self._pre_dig_align_entry_error(obs)
        self._apply_pre_dig_align_entry_error_runtime_state(
            entry_error_m=entry_error
        )
        snapshot = build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        return (
            self.dig_start_alignment_service.surface_guard_can_handoff_from_observation_view(
                view=snapshot.view,
                entry_error_m=entry_error,
                config=self._dig_start_alignment_config(),
                cycle_index=getattr(self, "_cycle_index", 0),
                hold_count=self._pre_dig_align_hold_count,
            )
        )

    def _pre_dig_align_outcome(self, obs: dict) -> PreDigAlignOutcome:
        surface_guard_triggered = self._pre_dig_align_surface_guard_triggered_for_state(
            obs
        )
        request = self.dig_start_alignment_service.outcome_request(
            surface_guard_triggered=surface_guard_triggered,
            step_count=int(self._pre_dig_align_step_count),
            max_steps=int(self.pre_dig_align_max_steps),
        )
        surface_guard_can_handoff = False
        ready = False
        timeout_can_handoff = False
        timeout_reason = ""
        if request.should_check_surface_guard_handoff:
            surface_guard_can_handoff = (
                self._pre_dig_align_surface_guard_can_handoff(obs)
            )
        elif request.should_check_ready:
            ready = self._pre_dig_align_ready(obs)
        if request.should_check_timeout(ready=ready):
            timeout_can_handoff = self._pre_dig_align_timeout_can_handoff(obs)
            timeout_reason = self._pre_dig_align_timeout_handoff_reason
        return request.outcome_with_gate_results(
            surface_guard_can_handoff=surface_guard_can_handoff,
            ready=ready,
            timeout_can_handoff=timeout_can_handoff,
            timeout_reason=timeout_reason,
        )

    def _dig_start_alignment_config(self) -> DigStartAlignmentConfig:
        return build_dig_start_alignment_runtime_config_from_mapping(
            {
                config_key: getattr(self, attr_name)
                for config_key, attr_name in (
                    DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS
                )
            }
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
        snapshot_obs = obs
        if qpos is not None or qvel is not None:
            snapshot_obs = dict(obs)
            if qpos is not None:
                snapshot_obs["qpos"] = qpos
            if qvel is not None:
                snapshot_obs["qvel"] = qvel
        snapshot = build_planner_snapshot(
            snapshot_obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        return self.dig_start_alignment_service.facts_from_observation_view(
            view=snapshot.view,
            target_qpos=target_qpos,
            entry_error_m=(
                self._pre_dig_align_entry_error(obs)
                if entry_error is None
                else entry_error
            ),
            qpos=qpos,
            qvel=qvel,
            cycle_index=getattr(self, "_cycle_index", 0),
            hold_count=self._pre_dig_align_hold_count,
        )

    def _reset_pre_dig_align_runtime(self) -> None:
        self._apply_pre_dig_align_initial_runtime_state()

    def _pre_dig_align_runtime_state(self) -> DigStartAlignmentRuntimeState:
        return runtime_state_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for field_name, attr_name in DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS
            }
        )

    def _apply_pre_dig_align_runtime_state(
        self,
        state: DigStartAlignmentRuntimeState,
    ) -> None:
        self._pre_dig_align_step_count = int(state.step_count)
        self._pre_dig_align_hold_count = int(state.hold_count)
        self._pre_dig_align_timeout_count = int(state.timeout_count)
        self._pre_dig_align_completed_count = int(state.completed_count)
        self._pre_dig_align_replan_count = int(state.replan_count)
        self._pre_dig_align_target_qpos = (
            np.asarray(state.target_qpos, dtype=np.float32)
            .reshape(self.action_dim)
            .copy()
        )
        self._pre_dig_align_error = (
            np.asarray(state.error, dtype=np.float32).reshape(self.action_dim).copy()
        )
        self._pre_dig_align_entry_error_m = float(state.entry_error_m)
        self._pre_dig_align_start_envelope_ready = bool(state.start_envelope_ready)
        self._pre_dig_align_entry_close_handoff_ready = bool(
            state.entry_close_handoff_ready
        )
        self._pre_dig_align_entry_intent_handoff_ready = bool(
            state.entry_intent_handoff_ready
        )
        self._pre_dig_align_timeout_handoff_reason = str(
            state.timeout_handoff_reason
        )
        self._pre_dig_align_surface_depth_m = float(state.surface_depth_m)
        self._pre_dig_align_surface_guard_triggered = bool(
            state.surface_guard_triggered
        )
        self._pre_dig_align_surface_guard_count = int(state.surface_guard_count)

    def _apply_pre_dig_align_initial_runtime_state(self) -> None:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.initial_runtime_state(
                self._dig_start_alignment_config()
            )
        )

    def _apply_pre_dig_align_enter_runtime_state(self) -> None:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.enter_runtime_state(
                self._pre_dig_align_runtime_state(),
                self._dig_start_alignment_config(),
            )
        )

    def _apply_pre_dig_align_restart_runtime_state(self) -> None:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.restart_runtime_state(
                self._pre_dig_align_runtime_state(),
                self._dig_start_alignment_config(),
            )
        )

    def _apply_pre_dig_align_replan_handoff_runtime_state(self) -> None:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.replan_handoff_runtime_state(
                self._pre_dig_align_runtime_state(),
                self._dig_start_alignment_config(),
            )
        )

    def _apply_pre_dig_align_surface_guard_decision(
        self,
        decision: SurfaceGuardDecision,
    ) -> bool:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.surface_guard_runtime_state(
                self._pre_dig_align_runtime_state(),
                decision,
            )
        )
        return bool(decision.triggered)

    def _apply_pre_dig_align_entry_error_runtime_state(
        self,
        *,
        entry_error_m: float,
    ) -> None:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.entry_error_runtime_state(
                self._pre_dig_align_runtime_state(),
                entry_error_m=entry_error_m,
            )
        )

    def _apply_pre_dig_align_ready_decision(
        self,
        decision: AlignmentReadyDecision,
        *,
        entry_error_m: float,
    ) -> bool:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.ready_runtime_state(
                self._pre_dig_align_runtime_state(),
                decision,
                entry_error_m=entry_error_m,
            )
        )
        return bool(decision.ready)

    def _apply_pre_dig_align_timeout_handoff_decision(
        self,
        decision: TimeoutHandoffDecision,
        *,
        sampled_entry_error_m: float | None = None,
    ) -> bool:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.timeout_handoff_runtime_state(
                self._pre_dig_align_runtime_state(),
                decision,
                sampled_entry_error_m=sampled_entry_error_m,
            )
        )
        return bool(decision.ready)

    def _apply_pre_dig_align_action_decision(
        self,
        decision: AlignmentActionDecision,
    ) -> np.ndarray:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.action_runtime_state(
                self._pre_dig_align_runtime_state(),
                decision,
            )
        )
        return decision.action

    def _apply_pre_dig_align_target_runtime_state(
        self,
        *,
        target_qpos: object,
    ) -> None:
        self._apply_pre_dig_align_runtime_state(
            self.dig_start_alignment_service.target_runtime_state(
                self._pre_dig_align_runtime_state(),
                target_qpos=target_qpos,
                config=self._dig_start_alignment_config(),
            )
        )

    def _pre_dig_align_debug_snapshot(self) -> DigStartAlignmentDebugSnapshot:
        return self.dig_start_alignment_service.debug_snapshot(
            config=self._dig_start_alignment_config(),
            state=debug_state_from_mapping(
                {
                    field_name: getattr(self, attr_name)
                    for field_name, attr_name in DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS
                }
            ),
        )

    def _pre_dig_align_ready(self, obs: dict) -> bool:
        if not self.pre_dig_align_enabled:
            return True
        target_qpos = self._pre_dig_align_target(obs)
        entry_error = self._pre_dig_align_entry_error(obs)
        snapshot = build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        decision = self.dig_start_alignment_service.ready_from_observation_view(
            view=snapshot.view,
            target_qpos=target_qpos,
            entry_error_m=entry_error,
            config=self._dig_start_alignment_config(),
            cycle_index=getattr(self, "_cycle_index", 0),
            hold_count=self._pre_dig_align_hold_count,
        )
        return self._apply_pre_dig_align_ready_decision(
            decision,
            entry_error_m=entry_error,
        )

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
        return (
            self.dig_start_alignment_service.entry_close_handoff_ready_from_runtime_values(
                action_dim=int(self.action_dim),
                qvel=qvel,
                entry_error_m=entry_error,
                cycle_index=getattr(self, "_cycle_index", 0),
                config=self._dig_start_alignment_config(),
                start_envelope_ready=start_envelope_ready,
            )
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
        request = self.dig_start_alignment_service.timeout_handoff_request(
            current_entry_error_m=float(self._pre_dig_align_entry_error_m),
            config=config,
        )
        view = None
        if request.should_sample_entry_error:
            entry_error = self._pre_dig_align_entry_error(obs)
            snapshot = build_planner_snapshot(
                obs,
                active_skill=self._skill_name,
                cycle_index=int(self._cycle_index),
                prev_action=None,
                boundary_event=None,
                action_dim=self.action_dim,
            )
            view = snapshot.view
        else:
            entry_error = None
        decision = self.dig_start_alignment_service.timeout_handoff_decision(
            request=request,
            config=config,
            action_dim=int(self.action_dim),
            view=view,
            sampled_entry_error_m=entry_error,
        )
        return self._apply_pre_dig_align_timeout_handoff_decision(
            decision,
            sampled_entry_error_m=entry_error,
        )

    def _pre_dig_align_start_envelope_ready_for_state(
        self,
        *,
        obs: dict,
        qpos: np.ndarray,
        entry_error: float,
    ) -> bool:
        snapshot_obs = dict(obs)
        snapshot_obs["qpos"] = qpos
        snapshot_obs["qvel"] = np.zeros(self.action_dim, dtype=np.float32)
        snapshot = build_planner_snapshot(
            snapshot_obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        return self.dig_start_alignment_service.start_envelope_ready_from_observation_view(
            view=snapshot.view,
            qpos=qpos,
            entry_error_m=entry_error,
            config=self._dig_start_alignment_config(),
        )

    def _pre_dig_align_action(self, obs: dict) -> np.ndarray:
        if not self.pre_dig_align_enabled:
            raise RuntimeError("pre-dig align action requested while disabled.")
        self._pre_dig_align_step_count += 1
        if self._pre_dig_align_surface_guard_triggered_for_state(obs):
            return np.zeros(self.action_dim, dtype=np.float32)
        target_qpos = self._pre_dig_align_target(obs)
        entry_error = self._pre_dig_align_entry_error(obs)
        snapshot = build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        decision = (
            self.dig_start_alignment_service.action_decision_from_observation_view(
                view=snapshot.view,
                target_qpos=target_qpos,
                entry_error_m=entry_error,
                config=self._dig_start_alignment_config(),
                cycle_index=getattr(self, "_cycle_index", 0),
                hold_count=self._pre_dig_align_hold_count,
            )
        )
        return self._apply_pre_dig_align_action_decision(decision)

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
        snapshot = build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        target = (
            self.dig_start_alignment_service.target_from_token_from_observation_view(
                view=snapshot.view,
                token=token,
                entry_error_m=float("nan"),
                config=self._dig_start_alignment_config(),
                cycle_index=getattr(self, "_cycle_index", 0),
                hold_count=self._pre_dig_align_hold_count,
            )
        )
        if update_state:
            self._apply_pre_dig_align_target_runtime_state(target_qpos=target)
        return target.copy()

    def _pre_dig_align_entry_error(self, obs: dict) -> float:
        corridor = self._coverage_active_corridor()
        active_entry_xz = (
            None
            if corridor is None
            else (float(corridor.entry_x_m), float(corridor.entry_z_m))
        )
        snapshot = build_planner_snapshot(
            obs,
            active_skill=self._skill_name,
            cycle_index=int(self._cycle_index),
            prev_action=None,
            boundary_event=None,
            action_dim=self.action_dim,
        )
        return self.dig_start_alignment_service.entry_error_from_observation_view(
            view=snapshot.view,
            active_corridor_entry_xz=active_entry_xz,
        )

    def _dig_lifecycle_config(self) -> DigLifecycleConfig:
        return build_dig_lifecycle_runtime_config_from_mapping(
            {
                key: getattr(self, key)
                for key in DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS
            }
        )

    def _dig_lifecycle_runtime_status_snapshot(
        self,
    ) -> DigLifecycleRuntimeStatusSnapshot:
        return self.dig_lifecycle_gate.runtime_status_snapshot(
            config=self._dig_lifecycle_config(),
            state=build_dig_lifecycle_runtime_status_state_from_mapping(
                {
                    field_name: getattr(self, attr_name)
                    for field_name, attr_name in DIG_LIFECYCLE_RUNTIME_STATUS_FIELDS
                }
            ),
        )

    def _dig_lifecycle_facts(
        self,
        obs: dict,
        boundary_event: Any | None = None,
    ) -> DigLifecycleFacts:
        snapshot = self._make_snapshot(obs, boundary_event=boundary_event)
        return self.dig_lifecycle_gate.facts_from_observation_view(
            view=snapshot.view,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=(
                self._semantic_boundary_profile_active()
            ),
            coverage_terminal_stop_requested=(
                self._coverage_terminal_stop_requested
            ),
            dig_step_count=int(self._dig_step_count),
            dig_best_mass_kg=float(self._dig_best_mass_kg),
            dig_mass_plateau_count=int(self._dig_mass_plateau_count),
            coverage_current_payload_gain_kg=float(
                self._coverage_current_payload_gain_kg
            ),
            active_corridor=self._coverage_active_corridor(),
        )

    def _update_dig_progress(self, obs: dict) -> None:
        progress = self.dig_lifecycle_gate.update_progress(
            self._dig_lifecycle_facts(obs),
            self._dig_lifecycle_config(),
        )
        self._apply_dig_progress_state(progress)

    def _apply_dig_progress_state(
        self,
        progress: DigProgressState,
    ) -> None:
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
        return is_v2_4_5_cycle_boundary_profile(
            getattr(config, "boundary_profile", CYCLE_BOUNDARY_PROFILE_LEGACY)
        )

    def _dump_lifecycle_config(self) -> DumpLifecycleConfig:
        return build_dump_lifecycle_runtime_config_from_mapping(
            {
                key: getattr(self, key)
                for key in DUMP_LIFECYCLE_RUNTIME_CONFIG_KEYS
                if hasattr(self, key)
            }
        )

    def _dump_lifecycle_facts(self, obs: dict) -> DumpLifecycleFacts:
        snapshot = self._make_snapshot(obs)
        return self.dump_lifecycle_gate.facts_from_observation_view(
            view=snapshot.view,
            semantic_boundary_profile_active=(
                self._semantic_boundary_profile_active()
            ),
            coverage_cycle_start_deposit_kg=(
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
        return build_return_to_dig_handoff_config_from_mapping(
            {
                config_key: getattr(self, attr_name)
                for config_key, attr_name in RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS
            }
        )

    def _return_to_dig_handoff_status_snapshot(
        self,
    ) -> ReturnToDigHandoffStatusSnapshot:
        return self.return_handoff_gate.status_snapshot(
            handoff_config=self._return_to_dig_handoff_config(),
            envelope_config=self._current_return_start_envelope_config(),
            state=build_return_to_dig_handoff_status_state_from_mapping(
                {
                    field_name: getattr(self, attr_name)
                    for field_name, attr_name in RETURN_TO_DIG_HANDOFF_STATUS_FIELDS
                }
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

        return build_return_to_dig_handoff_context_from_runtime(
            entry_target=self._return_to_dig_entry_target(),
            envelope_token=self._return_start_envelope_tokens,
            envelope_config=self._current_return_start_envelope_config(),
            dig_cut_prior=self.dig_cut_prior,
            pending_corridor_id=int(self._pending_dig_cut_corridor_id),
            corridor_cell_id_resolver=self._return_start_envelope_cell_id,
            use_prior_spatial_bounds=(
                self._return_start_envelope_use_prior_spatial_bounds
            ),
            use_prior_qpos_bounds=self._return_start_envelope_use_prior_qpos_bounds,
        )

    def _return_start_envelope_corridor_cell_id(
        self,
        corridor_id: int,
    ) -> int | None:
        try:
            corridor = self._coverage_corridor_by_id(int(corridor_id))
        except Exception:
            return None
        if corridor is None:
            return None
        return int(corridor.cell_id)

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
        state = self.return_handoff_gate.runtime_state_from_decision(
            decision,
            next_dig_event_seen=self._return_next_dig_event_seen,
        )
        self._apply_return_to_dig_handoff_runtime_state(state)
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
        return self.return_handoff_gate.entry_error(
            ReturnToDigEntryErrorFacts(
                entry_target=self._return_to_dig_entry_target(),
                bucket_dig_area_pose=self._bucket_dig_area_pose(obs),
            )
        )

    def _return_to_dig_entry_target(self) -> tuple[float, float] | None:
        resolution = self.return_entry_target_resolver.resolve(
            build_return_next_dig_entry_target_facts_from_runtime(
                cycle_index=self._cycle_index,
                pending_dig_cut_cycle_id=self._pending_dig_cut_cycle_id,
                pending_dig_cut_raw_fields=self._pending_dig_cut_raw_fields,
                active_corridor=self._coverage_active_corridor(),
            )
        )
        return resolution.entry_target

    def _target_geometry(self, obs: dict) -> dict[str, float]:
        return target_geometry_from_obs(obs)

    def _mass_in_bucket(self, obs: dict) -> float:
        return mass_in_bucket_from_obs(obs)

    def _deposited_mass(self, obs: dict) -> float:
        return deposited_mass_from_obs(obs)

    def _min_distance_to_dig_area(self, obs: dict) -> float:
        return min_distance_to_dig_area_from_obs(obs)

    def _bucket_depth_below_dig_area_plane(self, obs: dict) -> float:
        return bucket_depth_below_dig_area_plane_from_obs(obs)

    def _bucket_depth_below_local_surface(self, obs: dict) -> float:
        return bucket_depth_below_local_surface_from_obs(obs)

    def _bucket_dig_area_contact_mask(self, obs: dict) -> bool:
        return bucket_dig_area_contact_mask_from_obs(obs)

    def _env_state(self, obs: dict) -> np.ndarray:
        return env_state_from_obs(obs)

    def _boundary_detector_update_facts(
        self,
        obs: dict,
    ) -> BoundaryDetectorUpdateFacts:
        return boundary_detector_update_facts_from_obs(
            obs,
            action=self._prev_action,
            action_dim=self.action_dim,
        )

    def _policy_obs(self, obs: dict) -> dict:
        token_request = self._policy_observation_token_request()
        assembly = self.policy_observation_assembler.assemble(
            obs,
            PolicyObservationTokens(
                goal_tokens=(
                    self._goal_tokens() if token_request.goal_tokens else None
                ),
                cell_entry_tokens=(
                    self._cell_entry_tokens_for_obs(obs, token_request)
                    if token_request.cell_entry_tokens
                    else None
                ),
                dig_cut_tokens=(
                    self._dig_cut_tokens_for_obs(obs, token_request)
                    if token_request.dig_cut_tokens
                    else None
                ),
                dig_depth_profile_tokens=(
                    self._dig_depth_profile_tokens_for_obs(obs, token_request)
                    if token_request.dig_depth_profile_tokens
                    else None
                ),
                return_target_tokens=(
                    self._return_target_tokens_for_obs(obs, token_request)
                    if token_request.return_target_tokens
                    else None
                ),
                return_relocate_tokens=(
                    self._return_relocate_tokens_for_obs(obs, token_request)
                    if token_request.return_relocate_tokens
                    else None
                ),
                return_start_envelope_tokens=(
                    self._return_start_envelope_tokens_for_obs(obs, token_request)
                    if token_request.return_start_envelope_tokens
                    else None
                ),
            ),
        )
        return self._apply_policy_observation_assembly(assembly)

    def _apply_policy_observation_assembly(
        self,
        assembly: PolicyObservationAssembly,
    ) -> dict:
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

    def _reset_cell_entry_runtime(self) -> None:
        self.cell_entry_planner.reset()
        state = self.cell_entry_runtime_service.initial_runtime_state()
        self._apply_cell_entry_runtime_state(state)

    def _apply_cell_entry_runtime_state(
        self,
        state: CellEntryRuntimeState,
    ) -> None:
        self._cell_entry_goal = state.goal
        self._cell_entry_goal_cycle_id = int(state.goal_cycle_id)
        self._cell_entry_audit = state.audit
        tokens = (
            np.zeros(CELL_ENTRY_TOKEN_DIM, dtype=np.float32)
            if state.tokens is None
            else np.asarray(state.tokens, dtype=np.float32)
        )
        self._cell_entry_tokens = tokens.copy()
        self._cell_entry_token_injected = bool(state.token_injected)
        self._cell_entry_seen_cell_id = int(state.seen_cell_id)
        self._cell_entry_trace = [dict(event) for event in state.trace_events]

    def _reset_dig_lifecycle_runtime(self) -> None:
        state = self.dig_lifecycle_gate.initial_runtime_state()
        self._apply_dig_lifecycle_runtime_state(state)

    def _reset_dig_entry_runtime(self) -> None:
        state = self.dig_lifecycle_gate.entry_runtime_state(
            build_dig_lifecycle_entry_runtime_facts_from_mapping(
                {
                    field_name: getattr(self, attr_name)
                    for field_name, attr_name in (
                        DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS
                    )
                }
            )
        )
        self._apply_dig_lifecycle_entry_runtime_state(state)

    def _apply_dig_lifecycle_entry_runtime_state(
        self,
        state: DigLifecycleEntryRuntimeState,
    ) -> None:
        self._dig_step_count = int(state.step_count)
        self._dig_best_mass_kg = float(state.best_mass_kg)
        self._dig_mass_plateau_count = int(state.mass_plateau_count)
        self._dig_to_carry_reason = str(state.dig_to_carry_reason)
        self._coverage_current_payload_gain_kg = float(
            state.coverage_payload_gain_kg
        )
        self._dig_bad_replan_count = int(state.bad_replan_count)
        self._dig_exit_guard_replan_count = int(state.exit_guard_replan_count)

    def _apply_dig_transition_runtime_projection(
        self,
        projection: DigTransitionRuntimeProjection,
        obs: dict,
    ) -> bool:
        outcome = projection.outcome
        self._dig_exit_guard_replan_count += int(
            projection.exit_guard_replan_count_increment
        )
        self._dig_bad_replan_count += int(
            projection.bad_replan_count_increment
        )
        if projection.should_restart_after_failed_dig:
            self._reject_active_coverage_corridor(
                obs,
                reason=outcome.coverage_reject_reason,
            )
            self._restart_after_failed_dig(
                outcome.failed_dig_reason,
                obs,
            )
            return True
        if projection.should_handoff_to_carry:
            self._complete_cell_entry_dig(obs)
            self._complete_coverage_dig(obs)
            self._set_skill("carry", outcome.switch_reason)
            return True
        return False

    def _apply_dig_lifecycle_runtime_state(
        self,
        state: DigLifecycleRuntimeStatusState,
    ) -> None:
        self._dig_step_count = int(state.step_count)
        self._dig_best_mass_kg = float(state.best_mass_kg)
        self._dig_mass_plateau_count = int(state.mass_plateau_count)
        self._dig_to_carry_reason = str(state.dig_to_carry_reason)
        self._dig_bad_replan_count = int(state.bad_replan_count)
        self._dig_exit_guard_replan_count = int(state.exit_guard_replan_count)

    def _reset_dig_cut_runtime(self) -> None:
        state = self.dig_cut_plan_service.initial_runtime_state()
        self._apply_dig_cut_runtime_state(state)

    def _apply_dig_cut_runtime_state(
        self,
        state: DigCutRuntimeState,
    ) -> None:
        self._dig_cut_tokens = np.asarray(
            state.tokens,
            dtype=np.float32,
        ).copy()
        self._dig_cut_token_injected = bool(state.token_injected)
        self._dig_cut_planned_cycle_id = int(state.planned_cycle_id)
        self._dig_cut_token_source = str(state.token_source)
        self._dig_cut_fallback_reason = str(state.fallback_reason)
        self._dig_cut_token_in_prior_p10_p90 = bool(state.token_in_prior_p10_p90)

    def _reset_dig_depth_profile_runtime(self) -> None:
        state = self.dig_depth_profile_service.initial_runtime_state()
        self._apply_dig_depth_profile_runtime_state(state)

    def _apply_dig_depth_profile_runtime_state(
        self,
        state: DigDepthProfileRuntimeState,
    ) -> None:
        self._dig_depth_profile_tokens = np.asarray(
            state.tokens,
            dtype=np.float32,
        ).copy()
        self._dig_depth_profile_token_injected = bool(state.token_injected)
        self._dig_depth_profile_token_source = str(state.token_source)
        self._dig_depth_profile_fallback_reason = str(state.fallback_reason)

    def _reset_return_target_conditioning_runtime(self) -> None:
        state = self.return_target_plan_service.initial_conditioning_state()
        self._apply_return_target_conditioning_runtime_state(state)

    def _apply_return_target_conditioning_runtime_state(
        self,
        state: ReturnTargetConditioningRuntimeState,
    ) -> None:
        self._return_target_tokens = np.asarray(
            state.target_tokens,
            dtype=np.float32,
        ).copy()
        self._return_target_token_injected = bool(state.target_token_injected)
        self._return_target_token_source = str(state.target_token_source)
        self._return_target_fallback_reason = str(state.target_fallback_reason)
        self._return_relocate_tokens = np.asarray(
            state.relocate_tokens,
            dtype=np.float32,
        ).copy()
        self._return_relocate_token_injected = bool(state.relocate_token_injected)
        self._return_start_envelope_tokens = np.asarray(
            state.start_envelope_tokens,
            dtype=np.float32,
        ).copy()
        self._return_start_envelope_token_injected = bool(
            state.start_envelope_token_injected
        )
        self._return_start_envelope_token_source = str(
            state.start_envelope_token_source
        )
        self._return_start_envelope_use_prior_spatial_bounds = bool(
            state.start_envelope_use_prior_spatial_bounds
        )
        self._return_start_envelope_use_prior_qpos_bounds = bool(
            state.start_envelope_use_prior_qpos_bounds
        )
        self._return_target_planned_cycle_id = int(state.planned_cycle_id)
        self._apply_pending_dig_cut_plan_state(
            self.return_target_plan_service.pending_plan_state_from_conditioning_state(
                state
            )
        )

    def _reset_return_to_dig_handoff_runtime(self) -> None:
        state = self.return_handoff_gate.initial_runtime_state()
        self._apply_return_to_dig_handoff_runtime_state(state)

    def _apply_return_to_dig_handoff_runtime_state(
        self,
        state: ReturnToDigHandoffStatusState,
    ) -> None:
        self._return_to_dig_entry_error_m = float(state.entry_error_m)
        self._return_to_dig_entry_close_state = bool(state.entry_close)
        self._return_next_dig_event_seen = bool(state.next_dig_event_seen)
        self._return_to_dig_start_envelope_ready_state = bool(
            state.start_envelope_ready
        )
        self._return_to_dig_start_envelope_error = float(state.start_envelope_error)
        self._return_to_dig_start_envelope_checks = deepcopy(
            state.start_envelope_checks
        )

    def _apply_return_to_dig_transition_runtime_projection(
        self,
        projection: (
            ReturnToDigTransitionRuntimeProjection
            | ReturnDirectHandoffRuntimeProjection
        ),
    ) -> bool:
        if isinstance(projection, ReturnToDigTransitionRuntimeProjection):
            self._return_next_dig_event_seen = bool(projection.next_dig_event_seen)
        if not projection.should_transition:
            return False
        self._completed_transition_count += int(
            projection.completed_transition_increment
        )
        self._cycle_index += int(projection.cycle_index_increment)
        return True

    def _apply_return_to_dig_transition_completion(
        self,
        completion: ReturnToDigTransitionCompletion,
    ) -> bool:
        if not completion.should_transition:
            return False
        self._set_skill(completion.next_skill, completion.switch_reason)
        return True

    def _policy_observation_token_request(self) -> PolicyObservationTokenRequest:
        return self.policy_observation_assembler.token_request_from_mapping(
            {
                config_key: getattr(self, attr_name)
                for config_key, attr_name in POLICY_OBSERVATION_REQUEST_FACT_FIELDS
            },
            PolicyObservationRequestConfig(
                dig_skill_name="dig",
                return_skill_name="return",
                bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            ),
        )

    def _return_target_tokens_for_obs(
        self,
        obs: dict,
        token_request: PolicyObservationTokenRequest | None = None,
    ) -> np.ndarray | None:
        token_request = token_request or self._policy_observation_token_request()
        if not token_request.return_target_tokens:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self.return_target_plan_service.return_target_token_result(
            self._return_target_tokens
        ).tokens

    def _return_relocate_tokens_for_obs(
        self,
        obs: dict,
        token_request: PolicyObservationTokenRequest | None = None,
    ) -> np.ndarray | None:
        token_request = token_request or self._policy_observation_token_request()
        if not token_request.return_relocate_tokens:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self._apply_return_relocate_token_result(
            self.return_target_plan_service.return_relocate_token_result(
                self._return_target_tokens
            )
        )

    def _apply_return_relocate_token_result(
        self,
        result: ReturnRelocateObservationTokenResult,
    ) -> np.ndarray:
        self._return_relocate_tokens = result.tokens
        return result.tokens

    def _return_start_envelope_tokens_for_obs(
        self,
        obs: dict,
        token_request: PolicyObservationTokenRequest | None = None,
    ) -> np.ndarray | None:
        token_request = token_request or self._policy_observation_token_request()
        if not token_request.return_start_envelope_tokens:
            return None
        self._ensure_return_target_plan_for_cycle(obs)
        return self.return_target_plan_service.return_start_envelope_token_result(
            self._return_start_envelope_tokens
        ).tokens

    def _ensure_return_target_plan_for_cycle(self, obs: dict) -> None:
        request = self.return_target_plan_service.plan_request_from_runtime(
            enabled=self.return_target_planner_enabled,
            hold_until_skill_exit=self.return_target_hold_token_until_skill_exit,
            planned_cycle_id=self._return_target_planned_cycle_id,
            cycle_index=self._cycle_index,
            depth_profile_token=(self._coverage_active_state_exemplar_profile_token),
            state_exemplar_ids=self._coverage_active_state_exemplar_ids,
            state_exemplar_distance=(self._coverage_active_state_exemplar_distance),
        )
        if not request.should_build:
            return

        def build_facts() -> ReturnTargetPlanBuildFacts:
            token, raw_fields, source, fallback_reason, corridor_id = (
                self._build_next_dig_cut_plan_for_return(obs)
            )
            envelope_tokens = self._build_return_start_envelope_tokens_for_obs(
                obs,
                raw_fields,
                corridor_id=corridor_id,
            )
            return self.return_target_plan_service.plan_build_facts_from_parts(
                token=token,
                raw_fields=raw_fields,
                return_start_envelope_tokens=envelope_tokens,
                source=source,
                fallback_reason=fallback_reason,
                corridor_id=corridor_id,
            )

        state = self.return_target_plan_service.state_from_build_facts_callback(
            request=request,
            build_facts=build_facts,
        )
        self._apply_return_target_plan_state(state)

    def _apply_return_target_plan_state(self, state: ReturnTargetPlanState) -> None:
        update = self.return_target_plan_service.runtime_update_from_plan_state(state)
        self._return_target_tokens = update.return_target_tokens
        self._return_start_envelope_tokens = update.return_start_envelope_tokens
        self._return_target_token_source = update.return_target_token_source
        if update.return_start_envelope_token_source is not None:
            self._return_start_envelope_token_source = (
                update.return_start_envelope_token_source
            )
        self._return_target_fallback_reason = update.return_target_fallback_reason
        self._return_target_planned_cycle_id = update.return_target_planned_cycle_id
        self._apply_pending_dig_cut_plan_state(update.pending_plan)

    def _return_target_conditioning_status_snapshot(
        self,
    ) -> ReturnTargetConditioningStatusSnapshot:
        return self.return_target_plan_service.conditioning_status_snapshot_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for field_name, attr_name in RETURN_TARGET_CONDITIONING_STATUS_FIELDS
            }
        )

    def _dig_cut_tokens_for_obs(
        self,
        obs: dict,
        token_request: PolicyObservationTokenRequest | None = None,
    ) -> np.ndarray | None:
        token_request = token_request or self._policy_observation_token_request()
        decision = self._dig_conditioning_token_gate(
            token_requested=bool(token_request.dig_cut_tokens)
        )
        if not decision.return_token:
            return None
        if decision.should_build_plan:
            self._ensure_dig_cut_plan_for_cycle(obs)
        return self.dig_cut_plan_service.observation_token_result(
            self._dig_cut_tokens
        ).token

    def _dig_depth_profile_tokens_for_obs(
        self,
        obs: dict,
        token_request: PolicyObservationTokenRequest | None = None,
    ) -> np.ndarray | None:
        token_request = token_request or self._policy_observation_token_request()
        decision = self._dig_conditioning_token_gate(
            token_requested=bool(token_request.dig_depth_profile_tokens)
        )
        if not decision.return_token:
            return None
        if decision.should_build_plan:
            self._ensure_dig_cut_plan_for_cycle(obs)
        return self.dig_depth_profile_service.observation_token_result(
            self._dig_depth_profile_tokens
        ).token

    def _dig_conditioning_token_gate(
        self,
        *,
        token_requested: bool,
    ) -> DigConditioningObservationTokenGateDecision:
        return self.policy_observation_assembler.dig_conditioning_token_gate_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for (
                    field_name,
                    attr_name,
                ) in DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS
            },
            token_requested=bool(token_requested),
            config=PolicyObservationRequestConfig(dig_skill_name="dig"),
        )

    def _ensure_dig_cut_plan_for_cycle(self, obs: dict) -> None:
        decision = self.dig_cut_plan_service.cycle_decision_from_runtime(
            enabled=self.dig_cut_planner_enabled,
            hold_until_skill_exit=self.dig_cut_hold_token_until_skill_exit,
            planned_cycle_id=self._dig_cut_planned_cycle_id,
            cycle_index=self._cycle_index,
        )
        if not decision.should_build:
            return
        dig_cut_tokens = self._build_dig_cut_tokens_for_obs(obs)
        self._dig_cut_tokens = dig_cut_tokens
        cycle_state = self.dig_cut_plan_service.cycle_apply_state(
            dig_cut_tokens=dig_cut_tokens,
            dig_depth_profile_tokens=self._build_dig_depth_profile_tokens_for_obs(
                obs
            ),
            cycle_index=int(self._cycle_index),
        )
        self._apply_dig_cut_plan_cycle_state(cycle_state)

    def _apply_dig_cut_plan_cycle_state(
        self,
        state: DigCutPlanCycleApplyState,
    ) -> None:
        self._dig_cut_tokens = state.dig_cut_tokens
        self._dig_depth_profile_tokens = state.dig_depth_profile_tokens
        self._dig_cut_planned_cycle_id = int(state.planned_cycle_id)

    def _build_dig_depth_profile_tokens_for_obs(self, obs: dict) -> np.ndarray:
        try:
            state = self.dig_depth_profile_service.build_token_from_input_facts(
                self._dig_depth_profile_input_facts(obs, include_env_state=True),
                config=self._current_dig_depth_profile_config(),
                dig_cut_prior=self.dig_cut_prior,
                state_exemplar_profile_token=(
                    self._coverage_active_state_exemplar_profile_token
                ),
            )
        except DigDepthProfileMissingPriorError as exc:
            self._dig_depth_profile_token_source = "missing_required_prior"
            self._dig_depth_profile_fallback_reason = str(exc.reason)
            raise
        return self._apply_dig_depth_profile_token_result(state)

    def _apply_dig_depth_profile_token_result(
        self,
        state: DigDepthProfileState,
    ) -> np.ndarray:
        result: DigDepthProfileTokenResult = (
            self.dig_depth_profile_service.token_result(state)
        )
        self._dig_depth_profile_token_source = str(result.source)
        self._dig_depth_profile_fallback_reason = str(result.fallback_reason)
        return result.token

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
        return build_dig_depth_profile_config_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for field_name, attr_name in DIG_DEPTH_PROFILE_CONFIG_FIELDS
            }
        )

    def _dig_depth_profile_runtime_status_snapshot(
        self,
    ) -> DigDepthProfileRuntimeStatusSnapshot:
        return self.dig_depth_profile_service.runtime_status_snapshot_from_mappings(
            config_values={
                field_name: getattr(self, attr_name)
                for field_name, attr_name in DIG_DEPTH_PROFILE_CONFIG_FIELDS
            },
            state_values={
                field_name: getattr(self, attr_name)
                for (
                    field_name,
                    attr_name,
                ) in DIG_DEPTH_PROFILE_RUNTIME_STATUS_STATE_FIELDS
            },
        )

    def _dig_depth_profile_input_facts(
        self,
        obs: dict,
        *,
        include_env_state: bool = False,
    ) -> DigDepthProfileInputFacts:
        def pending_corridor_cell_id(pending_corridor_id: int) -> int | None:
            corridor = self._coverage_corridor_by_id(pending_corridor_id)
            if corridor is not None:
                return int(corridor.cell_id)
            return None

        return self.dig_depth_profile_service.input_facts_from_source_callbacks(
            cycle_index=int(self._cycle_index),
            pending_cycle_id=int(self._pending_dig_cut_cycle_id),
            pending_corridor_id=int(self._pending_dig_cut_corridor_id),
            pending_raw_fields=self._pending_dig_cut_raw_fields,
            current_dig_cut_tokens=self._dig_cut_tokens,
            include_env_state=bool(include_env_state),
            callbacks=DigDepthProfileInputSourceCallbacks(
                pending_corridor_cell_id=pending_corridor_cell_id,
                active_corridor=self._coverage_active_corridor,
                active_corridor_raw_fields=lambda corridor: self._coverage_raw_fields(
                    corridor,
                    obs=obs,
                ),
                active_corridor_cell_id=lambda corridor: int(corridor.cell_id),
                live_raw_fields=lambda: self._raw_fields_from_live_pose(obs),
                env_state=lambda: self._env_state(obs),
            ),
        )

    def _dig_depth_profile_raw_fields(self, obs: dict) -> dict[str, float | int]:
        return self.dig_depth_profile_service.resolve_raw_fields(
            self._dig_depth_profile_input_facts(obs)
        )

    def _dig_depth_profile_cell_id(self, obs: dict) -> int:
        return self.dig_depth_profile_service.resolve_cell_id(
            self._dig_depth_profile_input_facts(obs)
        )

    def _build_dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray:
        self._dig_cut_fallback_reason = ""
        decision = self.dig_cut_plan_service.dispatch_decision(
            self._dig_cut_plan_dispatch_facts()
        )
        if decision.action == "pending_return_target":
            activation = self.return_target_plan_service.pending_activation(
                self._pending_return_target_activation_facts(obs)
            )
            return self._apply_pending_return_target_activation(activation)
        if decision.builder_kind == "conservative_pose":
            plan = build_conservative_pose_dig_cut_plan(
                self._bucket_dig_area_pose(obs)
            )
            state = self.dig_cut_plan_service.state_from_success_plan(
                plan,
                raw_fields_in_prior_range=False,
            )
            return self._apply_dig_cut_plan_state(state)
        if decision.builder_kind == "operator_prior":
            state = self._dig_cut_plan_state_from_builder(
                obs,
                self._build_operator_prior_dig_cut_tokens,
            )
            return self._apply_dig_cut_plan_state(state)
        if decision.builder_kind == "operator_prior_coverage":
            state = self._dig_cut_plan_state_from_builder(
                obs,
                self._build_operator_prior_coverage_dig_cut_tokens,
            )
            return self._apply_dig_cut_plan_state(state)
        raise ValueError(
            f"Unsupported dig_cut_planner mode {self.dig_cut_planner_mode!r}."
        )

    def _pending_return_target_activation_facts(
        self,
        obs: dict,
    ) -> PendingReturnTargetActivationFacts:
        raw_fields_in_prior_range = (
            False
            if self._pending_dig_cut_raw_fields is None
            else self._raw_fields_in_prior_range(self._pending_dig_cut_raw_fields)
        )
        return build_pending_return_target_activation_facts_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for (
                    field_name,
                    attr_name,
                ) in PENDING_RETURN_TARGET_ACTIVATION_FACT_FIELDS
            },
            raw_fields_in_prior_range=raw_fields_in_prior_range,
            cycle_start_deposit_kg=self._deposited_mass(obs),
        )

    def _apply_pending_return_target_activation(
        self,
        activation: PendingReturnTargetActivation,
    ) -> np.ndarray:
        self._dig_cut_token_source = activation.dig_cut_token_source
        self._dig_cut_fallback_reason = activation.dig_cut_fallback_reason
        self._dig_cut_token_in_prior_p10_p90 = (
            activation.dig_cut_token_in_prior_p10_p90
        )
        self._coverage_active_corridor_id = activation.coverage_active_corridor_id
        self._coverage_last_selected_corridor_id = (
            activation.coverage_last_selected_corridor_id
        )
        self._coverage_current_payload_gain_kg = (
            activation.coverage_current_payload_gain_kg
        )
        self._coverage_cycle_start_deposit_kg = (
            activation.coverage_cycle_start_deposit_kg
        )
        self._coverage_active_state_exemplar_ids = list(
            activation.active_state_exemplar_ids
        )
        self._coverage_active_state_exemplar_distance = float(
            activation.active_state_exemplar_distance
        )
        self._coverage_active_state_exemplar_profile_token = (
            None
            if activation.active_state_exemplar_profile_token is None
            else activation.active_state_exemplar_profile_token.copy()
        )
        return np.asarray(activation.dig_cut_tokens, dtype=np.float32).copy()

    def _dig_cut_plan_state_from_builder(
        self,
        obs: dict,
        builder: Any,
    ) -> DigCutPlanState:
        return self.dig_cut_plan_service.state_from_builder_attempt(
            build_plan=lambda: builder(obs),
            raw_fields_in_prior_range=self._raw_fields_in_prior_range,
            fallback_mode=str(self.dig_cut_planner_fallback_mode),
            fallback_plan=lambda exc: build_conservative_pose_dig_cut_plan(
                self._bucket_dig_area_pose(obs),
                source="fallback_conservative_pose",
                fallback_reason=str(exc),
            ),
        )

    def _apply_dig_cut_plan_state(self, state: DigCutPlanState) -> np.ndarray:
        result: DigCutPlanTokenResult = self.dig_cut_plan_service.token_result(state)
        self._dig_cut_token_source = str(result.source)
        self._dig_cut_fallback_reason = str(result.fallback_reason)
        self._dig_cut_token_in_prior_p10_p90 = bool(result.token_in_prior_p10_p90)
        return result.token

    def _build_next_dig_cut_plan_for_return(
        self,
        obs: dict,
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        decision = self.dig_cut_plan_service.dispatch_decision(
            self._dig_cut_plan_dispatch_facts(pending_tokens_present=False)
        )
        context = self.return_target_plan_service.dig_cut_build_context(
            source_prefix=self.return_target_token_source_prefix,
            builder_kind=decision.builder_kind,
            planner_mode=self.dig_cut_planner_mode,
        )

        def conservative_pose_plan() -> Any:
            return build_conservative_pose_dig_cut_plan(
                self._bucket_dig_area_pose(obs)
            )

        def operator_prior_parts() -> tuple[
            np.ndarray,
            dict[str, float | int],
            str,
            str,
        ]:
            return self._build_operator_prior_dig_cut_tokens(obs)

        def coverage_plan() -> tuple[Any, int]:
            corridor = self._select_next_coverage_corridor(obs)
            self._coverage_active_corridor_id = int(corridor.corridor_id)
            raw_fields = self._coverage_raw_fields(
                corridor,
                obs=obs,
                update_state=True,
            )
            plan = build_raw_fields_dig_cut_plan(
                raw_fields,
                source=context.planner_mode,
            )
            return plan, int(corridor.corridor_id)

        result: ReturnTargetDigCutBuildResult = (
            self.return_target_plan_service.dig_cut_build_result_from_callbacks(
                context,
                ReturnTargetDigCutBuildCallbacks(
                    conservative_pose_plan=conservative_pose_plan,
                    operator_prior_parts=operator_prior_parts,
                    coverage_plan=coverage_plan,
                ),
            )
        )
        return result.legacy_tuple()

    def _dig_cut_plan_dispatch_facts(
        self,
        *,
        pending_tokens_present: object | None = None,
    ) -> DigCutPlanDispatchFacts:
        return build_dig_cut_plan_dispatch_facts_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for (
                    field_name,
                    attr_name,
                ) in DIG_CUT_PLAN_DISPATCH_FACT_FIELDS
            },
            pending_tokens_present=pending_tokens_present,
        )

    def _build_return_start_envelope_tokens_for_obs(
        self,
        obs: dict,
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        state = build_return_start_envelope_for_plan(
            self._return_start_envelope_build_request(
                obs,
                raw_fields,
                corridor_id=corridor_id,
            )
        )
        return self._apply_return_start_envelope_token_result(state)

    def _return_start_envelope_build_request(
        self,
        obs: dict,
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> ReturnStartEnvelopeBuildRequest:
        return build_return_start_envelope_request_from_observation_view(
            self._make_snapshot(obs).view,
            raw_fields=raw_fields,
            dig_cut_prior=self.dig_cut_prior,
            config=self._current_return_start_envelope_config(),
            cell_id=self._return_start_envelope_cell_id(corridor_id),
        )

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
        return self._apply_return_start_envelope_token_result(state)

    def _apply_return_start_envelope_token_result(
        self,
        state: ReturnStartEnvelopeState,
    ) -> np.ndarray:
        result = require_return_start_envelope_token_result(state)
        self._return_start_envelope_token_source = result.source
        self._return_start_envelope_use_prior_spatial_bounds = (
            result.use_prior_spatial_bounds
        )
        self._return_start_envelope_use_prior_qpos_bounds = (
            result.use_prior_qpos_bounds
        )
        return result.token

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
        corridor_cell_id = None
        try:
            corridor = self._coverage_corridor_by_id(int(corridor_id))
        except Exception:
            corridor = None
        if corridor is not None:
            corridor_cell_id = int(corridor.cell_id)
        return resolve_return_start_envelope_cell_id(
            corridor_id=corridor_id,
            corridor_cell_id=corridor_cell_id,
        )

    @staticmethod
    def _return_start_envelope_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        return return_start_envelope_token_from_prior_mapping(mapping)

    def _current_return_start_envelope_config(self) -> ReturnStartEnvelopeConfig:
        return build_return_start_envelope_config_from_mapping(
            {
                config_key: getattr(self, attr_name)
                for config_key, attr_name in (
                    RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS
                )
            }
        )

    @staticmethod
    def _normalize_plane_depth_mode(value: object) -> str:
        return primitive_config_helpers.normalize_plane_depth_mode(value)

    @staticmethod
    def _normalize_failed_dig_replan_skill(value: object) -> str:
        return primitive_config_helpers.normalize_failed_dig_replan_skill(value)

    def _raw_fields_from_live_pose(self, obs: dict) -> dict[str, float | int]:
        return dig_cut_raw_fields_from_live_pose(self._bucket_dig_area_pose(obs))

    def _build_operator_prior_dig_cut_tokens(
        self, obs: dict
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        plan = build_operator_prior_dig_cut_plan(
            OperatorPriorDigCutPlanRequest(
                dig_cut_prior=dict(self.dig_cut_prior),
                bucket_dig_area_pose=self._bucket_dig_area_pose(obs),
            )
        )
        return (
            np.asarray(plan.token, dtype=np.float32),
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
        plan = build_raw_fields_dig_cut_plan(
            raw_fields,
            source="operator_prior_coverage",
        )
        return (
            plan.token,
            plan.raw_fields,
            plan.source,
            plan.fallback_reason,
        )

    def _dig_cut_runtime_status_snapshot(self) -> DigCutRuntimeStatusSnapshot:
        return self.dig_cut_plan_service.runtime_status_snapshot_from_mappings(
            config_values={
                field_name: getattr(self, attr_name)
                for field_name, attr_name in DIG_CUT_RUNTIME_STATUS_CONFIG_FIELDS
            },
            state_values={
                field_name: getattr(self, attr_name)
                for field_name, attr_name in DIG_CUT_RUNTIME_STATUS_STATE_FIELDS
            },
        )

    def _clear_dig_cut_plan(self) -> None:
        self._apply_dig_cut_plan_clear_state(
            self.dig_cut_plan_service.cleared_plan_state()
        )
        self._clear_coverage_active_state_exemplar()

    def _apply_dig_cut_plan_clear_state(
        self,
        state: DigCutPlanClearState,
    ) -> None:
        self._dig_cut_planned_cycle_id = int(state.planned_cycle_id)
        self._dig_cut_tokens = np.asarray(
            state.dig_cut_tokens,
            dtype=np.float32,
        ).copy()
        self._dig_depth_profile_tokens = np.asarray(
            state.dig_depth_profile_tokens,
            dtype=np.float32,
        ).copy()
        self._dig_cut_token_source = str(state.token_source)
        self._dig_cut_fallback_reason = str(state.fallback_reason)
        self._dig_cut_token_in_prior_p10_p90 = bool(state.token_in_prior_p10_p90)

    def _invalidate_pending_dig_cut_plan(self) -> None:
        self._apply_pending_dig_cut_plan_state(
            self.return_target_plan_service.invalidated_pending_dig_cut_plan()
        )

    def _apply_pending_dig_cut_plan_state(
        self,
        state: PendingDigCutPlanState,
    ) -> None:
        self._pending_dig_cut_cycle_id = int(state.cycle_id)
        self._pending_dig_cut_corridor_id = int(state.corridor_id)
        self._pending_dig_cut_raw_fields = (
            None if state.raw_fields is None else dict(state.raw_fields)
        )
        self._pending_dig_cut_tokens = (
            None
            if state.tokens is None
            else np.asarray(state.tokens, dtype=np.float32).copy()
        )
        self._pending_dig_depth_profile_tokens = (
            None
            if state.depth_profile_tokens is None
            else np.asarray(state.depth_profile_tokens, dtype=np.float32).copy()
        )
        self._pending_dig_state_exemplar_ids = list(state.state_exemplar_ids)
        self._pending_dig_state_exemplar_distance = float(
            state.state_exemplar_distance
        )

    def _apply_conditioning_config(
        self,
        config: primitive_config_helpers.PrimitiveConditioningConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_dig_lifecycle_config(
        self,
        config: DigLifecyclePlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_dump_lifecycle_config(
        self,
        config: DumpLifecyclePlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_return_to_dig_config(
        self,
        config: ReturnToDigPlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_bootstrap_config(
        self,
        config: BootstrapPlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_goal_sequence_config(
        self,
        config: GoalSequencePlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_cell_entry_config(
        self,
        config: CellEntryPlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _apply_pre_dig_align_config(
        self,
        config: primitive_config_helpers.PreDigAlignmentPlannerConfig,
    ) -> None:
        primitive_config_helpers.apply_planner_config_items(self, config)

    def _validate_dig_cut_planner_config(self) -> None:
        primitive_config_helpers.validate_dig_cut_planner_config(
            dig_cut_planner_enabled=self.dig_cut_planner_enabled,
            dig_cut_planner_mode=self.dig_cut_planner_mode,
            dig_cut_prior_path=self.dig_cut_prior_path,
            coverage_candidate_layout=self.coverage_candidate_layout,
            dig_depth_profile_source=self.dig_depth_profile_source,
            dig_cut_prior=self.dig_cut_prior,
            dig_depth_profile_required=self.dig_depth_profile_required,
            dig_depth_profile_allow_live_fallback=(
                self.dig_depth_profile_allow_live_fallback
            ),
        )

    def _align_vector(
        self,
        value: object,
        *,
        default: list[float] | tuple[float, ...],
    ) -> np.ndarray:
        return primitive_config_helpers.align_vector(
            value,
            default=default,
            action_dim=self.action_dim,
        )

    def _optional_align_vector(self, value: object) -> np.ndarray | None:
        return primitive_config_helpers.optional_align_vector(
            value,
            action_dim=self.action_dim,
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        return primitive_config_helpers.optional_float(value)

    @staticmethod
    def _load_dig_cut_prior(path: str) -> dict[str, Any]:
        return primitive_config_helpers.load_dig_cut_prior(path)

    def _cell_entry_tokens_for_obs(
        self,
        obs: dict,
        token_request: PolicyObservationTokenRequest | None = None,
    ) -> np.ndarray | None:
        token_request = token_request or self._policy_observation_token_request()
        if not token_request.cell_entry_tokens:
            return None
        result = self.cell_entry_runtime_service.tokens_for_obs(
            planner=self.cell_entry_planner,
            auditor=self.cell_entry_auditor,
            facts=self._cell_entry_runtime_facts(obs),
            config=CellEntryRuntimeConfig(enabled=self.cell_entry_enabled),
            state=self._cell_entry_runtime_state(),
        )
        return self._apply_cell_entry_runtime_token_result(result)

    def _apply_cell_entry_runtime_token_result(
        self,
        result: CellEntryRuntimeTokenResult,
    ) -> np.ndarray | None:
        if result.tokens is None:
            return None
        self._cell_entry_goal = result.state.goal
        self._cell_entry_goal_cycle_id = int(result.state.goal_cycle_id)
        self._cell_entry_audit = result.state.audit
        self._cell_entry_seen_cell_id = int(result.state.seen_cell_id)
        self._cell_entry_tokens = np.asarray(result.tokens, dtype=np.float32).copy()
        return self._cell_entry_tokens.copy()

    def _complete_cell_entry_dig(self, obs: dict) -> None:
        if not self.cell_entry_enabled or self._cell_entry_goal is None:
            return
        result = self.cell_entry_runtime_service.complete_dig(
            planner=self.cell_entry_planner,
            facts=self._cell_entry_runtime_facts(obs),
            config=CellEntryRuntimeConfig(enabled=self.cell_entry_enabled),
            state=self._cell_entry_runtime_state(),
        )
        self._apply_cell_entry_runtime_completion_result(result)

    def _apply_cell_entry_runtime_completion_result(
        self,
        result: CellEntryRuntimeCompletionResult,
    ) -> None:
        if result.trace_event is not None:
            self._cell_entry_trace.append(result.trace_event)

    def _cell_entry_debug_snapshot(self) -> CellEntryDebugSnapshot:
        return self.cell_entry_runtime_service.debug_snapshot(
            state=self._cell_entry_runtime_state()
        )

    def _cell_entry_runtime_facts(self, obs: dict) -> CellEntryRuntimeFacts:
        snapshot = self._make_snapshot(obs)
        return self.cell_entry_runtime_service.facts_from_observation_view(
            view=snapshot.view,
            cycle_index=self._cycle_index,
            active_skill=self._skill_name,
        )

    def _cell_entry_runtime_state(self) -> CellEntryRuntimeState:
        return build_cell_entry_runtime_state_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for field_name, attr_name in CELL_ENTRY_RUNTIME_STATE_FIELDS
            }
        )

    def _bucket_dig_area_cell_in_bounds_mask(self, obs: dict) -> bool:
        return bucket_dig_area_cell_in_bounds_mask_from_obs(obs)

    def _dig_cell_id(self, obs: dict) -> int:
        return dig_cell_id_from_obs(obs)

    def _bucket_dig_area_pose(self, obs: dict) -> tuple[float, float, float] | None:
        return bucket_dig_area_pose_from_obs(obs)

    def _bucket_tip_dig_area_pose(self, obs: dict) -> tuple[float, float, float] | None:
        return bucket_tip_dig_area_pose_from_obs(obs)

    def _goal_tokens(self) -> np.ndarray | None:
        return self.goal_sequence_service.tokens_for_cycle(
            sequence=self.goal_sequence,
            facts=GoalSequenceFacts(cycle_index=int(self._cycle_index)),
            config=GoalSequenceConfig(
                scenario_id=self.goal_scenario_id,
                depth_norm=self.goal_depth_norm,
                dump_target_norm=self.goal_dump_target_norm,
            ),
        ).tokens

    def _goal_sector_id(self, cycle_index: int) -> int:
        return self.goal_sequence_service.sector_id_for_cycle(
            sequence=self.goal_sequence,
            cycle_index=int(cycle_index),
        )

    def _next_goal_sector_id(self) -> int:
        return self.goal_sequence_service.next_sector_id(
            sequence=self.goal_sequence,
            cycle_index=int(self._cycle_index),
        )

    @staticmethod
    def _normalize_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | None,
    ) -> tuple[int, ...]:
        return primitive_config_helpers.normalize_goal_sequence(goal_sequence)

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
        dump_status = self._dump_lifecycle_runtime_status_snapshot()
        return build_primitive_debug_state_snapshot_from_runtime(
            config=PrimitiveDebugStateSnapshotConfig(
                skill_ids=PRIMITIVE_SKILL_IDS,
                transition_skill_names=("return", PRE_DIG_ALIGN_SKILL_NAME),
                transition_hybrid_mode=HYBRID_MODE_TRANSITION,
                work_hybrid_mode=HYBRID_MODE_WORK,
                primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            ),
            facts=PrimitiveDebugStateSnapshotFacts(
                skill_name=str(self._skill_name),
                skill_switch_reason=str(self._switch_reason),
                first_dig_policy_active=self._first_dig_policy_active(),
                transition_timeout=bool(transition_timeout),
                transition_completed=bool(transition_completed),
                completed_transition_count=int(self._completed_transition_count),
                transition_timeout_count=int(self._transition_timeout_count),
                dump_ready_hold_count=int(dump_status.ready_hold_count),
                dump_done_hold_count=int(dump_status.done_hold_count),
                primitive_cycle_index=int(self._cycle_index),
            ),
        )

    def _debug_state_facts(self) -> PrimitiveDebugStateFacts:
        return build_primitive_debug_state_facts_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for field_name, attr_name in PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS
            },
            primitive_goal_curr_sector_id=self._goal_sector_id(self._cycle_index),
            primitive_goal_next_sector_id=self._next_goal_sector_id(),
            pre_dig_align_active_for_next_dig=(
                self._should_pre_dig_align_before_dig()
            ),
            coverage_debug=self._coverage_debug_snapshot(),
            return_handoff_status=self._return_to_dig_handoff_status_snapshot(),
            dig_cut_status=self._dig_cut_runtime_status_snapshot(),
            dig_depth_profile_status=(
                self._dig_depth_profile_runtime_status_snapshot()
            ),
            return_target_status=self._return_target_conditioning_status_snapshot(),
            dig_lifecycle_status=self._dig_lifecycle_runtime_status_snapshot(),
            bootstrap_status=self._bootstrap_runtime_status_snapshot(),
            cell_entry_debug=self._cell_entry_debug_snapshot(),
            pre_dig_align_debug=self._pre_dig_align_debug_snapshot(),
        )

    def _planner_trace_facts(self) -> PrimitivePlannerTraceFacts:
        return build_primitive_planner_trace_facts_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for (
                    field_name,
                    attr_name,
                ) in PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS
            },
            coverage_trace=self._coverage_trace_snapshot(),
        )

    def _rollout_summary_facts(self) -> PrimitiveRolloutSummaryFacts:
        return build_primitive_rollout_summary_facts_from_mapping(
            {
                field_name: getattr(self, attr_name)
                for (
                    field_name,
                    attr_name,
                ) in PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS
            },
            coverage_summary=self._coverage_rollout_summary_snapshot(),
            return_handoff_status=self._return_to_dig_handoff_status_snapshot(),
            dig_cut_status=self._dig_cut_runtime_status_snapshot(),
            return_target_status=self._return_target_conditioning_status_snapshot(),
            dig_lifecycle_status=self._dig_lifecycle_runtime_status_snapshot(),
            bootstrap_status=self._bootstrap_runtime_status_snapshot(),
            pre_dig_align_debug=self._pre_dig_align_debug_snapshot(),
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

    def _dump_lifecycle_runtime_status_snapshot(
        self,
    ) -> DumpLifecycleRuntimeStatusSnapshot:
        return self.dump_lifecycle_gate.runtime_status_snapshot(
            DumpLifecycleRuntimeStatusState(
                ready_hold_count=int(self._dump_release_ready_hold_count),
                done_hold_count=int(self._dump_done_hold_count),
            )
        )

    def _make_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitivePlannerDebugState:
        dump_status = self._dump_lifecycle_runtime_status_snapshot()
        return build_primitive_debug_state_snapshot_from_runtime(
            config=PrimitiveDebugStateSnapshotConfig(
                skill_ids=PRIMITIVE_SKILL_IDS_5P,
                transition_skill_names=("return",),
                transition_hybrid_mode=HYBRID_MODE_TRANSITION,
                work_hybrid_mode=HYBRID_MODE_WORK,
                primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            ),
            facts=PrimitiveDebugStateSnapshotFacts(
                skill_name=str(self._skill_name),
                skill_switch_reason=str(self._switch_reason),
                first_dig_policy_active=self._first_dig_policy_active(),
                transition_timeout=bool(transition_timeout),
                transition_completed=bool(transition_completed),
                completed_transition_count=int(self._completed_transition_count),
                transition_timeout_count=int(self._transition_timeout_count),
                dump_ready_hold_count=int(dump_status.ready_hold_count),
                dump_done_hold_count=int(dump_status.done_hold_count),
                primitive_cycle_index=int(self._cycle_index),
                approach_ready_hold_count=int(self._approach_ready_hold_count),
                dump_release_ready_hold_count=int(dump_status.ready_hold_count),
            ),
        )
