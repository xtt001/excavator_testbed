"""V2.2 scripted planners over ACT primitives."""

from __future__ import annotations

from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
)
from testbed.planner.boundary_detector import BoundaryDetector
from testbed.planner.primitive.execution.boundary_event import (
    PrimitiveBoundaryEventRuntimePorts,
    PrimitiveBoundaryEventRuntimeService,
)
from testbed.planner.primitive.facts.capabilities import (
    BootstrapStatus,
    PrimitiveObservationFacts,
)
from testbed.planner.primitive.compatibility.cell_entry import (
    PrimitiveCellEntryCompatibilityRuntimeState,
)
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.config import PrimitiveCoverageStaticConfig
from testbed.planner.primitive.coverage.selection_runtime import (
    PrimitiveCoverageSelectionRuntime,
    PrimitiveCoverageSelectionRuntimePorts as CoverageSelectionBoundaryPorts,
)
from testbed.planner.primitive.coverage.report_runtime import (
    PrimitiveCoverageReportRuntime,
    PrimitiveCoverageReportRuntimePorts as CoverageReportBoundaryPorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.effect_runtime import (
    PrimitiveCoverageEffectRuntime,
    PrimitiveCoverageEffectRuntimePorts as CoverageEffectBoundaryPorts,
)
from testbed.planner.primitive.execution.action_dispatch import (
    PrimitiveActionDispatchPorts,
    PrimitiveActionDispatchService,
)
from testbed.planner.primitive.execution.runtime import (
    PrimitiveExecutionRuntime,
    PrimitiveExecutionRuntimePorts,
)
from testbed.planner.primitive.execution.tick_finalization import (
    PrimitiveTickFinalizationRuntime,
    PrimitiveTickFinalizationRuntimePorts,
)
from testbed.planner.primitive.decision.runtime import (
    LEGACY_FSM_DECISION_BACKEND_NAME,
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimeConfig,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive.decision.backends.legacy_fsm import (
    LegacyFSMDecisionBackendFactory,
    LegacyFSMDecisionBackendFactoryPorts,
)
from testbed.planner.primitive.execution.dig_recovery import (
    PrimitiveDigRecoveryPorts,
    PrimitiveDigRecoveryService,
)
from testbed.planner.primitive.execution.dig_progress import (
    PrimitiveDigProgressRuntimeConfig,
    PrimitiveDigProgressRuntimePorts,
    PrimitiveDigProgressRuntimeService,
)
from testbed.planner.primitive.effects.requested import (
    PrimitiveRequestedEffectRuntime,
    PrimitiveRequestedEffectRuntimePorts,
)
from testbed.planner.primitive.execution.skill_lifecycle import (
    PrimitiveSkillLifecyclePorts,
    PrimitiveSkillLifecycleService,
)
from testbed.planner.primitive.execution.reset_lifecycle import (
    PrimitiveResetLifecyclePorts,
    PrimitiveResetLifecycleService,
    PrimitiveResetLifecycleState,
)
from testbed.planner.primitive.shell.runtime_kernel import (
    PrimitivePlannerPublicRuntime,
    PrimitivePlannerPublicRuntimePorts,
)
from testbed.planner.primitive.execution.cycle_state import (
    PrimitiveCycleReportStatus,
    PrimitiveCycleRuntimeState,
)
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.execution.return_state import (
    PrimitiveReturnReportStatus,
    PrimitiveReturnRuntimeState,
)
from testbed.planner.primitive.execution.scripted_bootstrap import (
    PrimitiveScriptedBootstrapReportStatus,
    PrimitiveScriptedBootstrapRuntimeConfig,
    PrimitiveScriptedBootstrapRuntimeService,
    PrimitiveScriptedBootstrapRuntimeState,
)
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignPorts,
    PrimitivePreDigAlignRuntimeConfig,
    PrimitivePreDigAlignRuntimeService,
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.token.state import (
    PrimitiveTokenRuntimeState,
)
import testbed.planner.primitive.config.adapter as adapter_config
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
    PrimitivePlannerAdapterConfigState,
)
from testbed.planner.primitive.token.observation_runtime import (
    PrimitiveTokenObservationRuntime,
    PrimitiveTokenObservationRuntimePorts,
)
from testbed.planner.primitive.token.planning_runtime import (
    PrimitiveTokenPlanningRuntime,
    PrimitiveTokenPlanningRuntimePorts,
)
from testbed.planner.primitive.token.factory import (
    PrimitiveTokenPlannerFactory,
    PrimitiveTokenPlannerFactoryConfig,
)
from testbed.planner.primitive.facts.observation import (
    PrimitiveObservationInjectionRuntimeState,
)
from testbed.planner.primitive.report.runtime import (
    PrimitiveReportCompositionPorts,
    PrimitiveReportCompositionRuntime,
    TRANSITION_POLICY_MODE_PRIMITIVE,
    TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
)
from testbed.planner.primitive.effects.return_handoff_runtime import (
    PrimitiveReturnHandoffRuntime,
    PrimitiveReturnHandoffRuntimePorts,
)
from testbed.policies.base import Policy, register_policy
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK


PRIMITIVE_SKILL_NAMES = ("dig", "carry", "dump", "return")
PRIMITIVE_SKILL_IDS = {name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES)}
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
        if config_state.fsm_capability_provider_config is not None:
            self._fsm_capability_provider_config = (
                config_state.fsm_capability_provider_config
            )
        if config_state.return_handoff_readiness_config is not None:
            self._primitive_return_handoff_config = (
                config_state.return_handoff_readiness_config
            )

    def reset(self) -> None:
        self._primitive_runtime_kernel_runtime().reset()

    def _primitive_runtime_kernel_runtime_ports(
        self,
    ) -> PrimitivePlannerPublicRuntimePorts:
        return PrimitivePlannerPublicRuntimePorts(
            reset_lifecycle_service=self._primitive_reset_lifecycle_service,
            apply_reset_lifecycle_state=self._apply_reset_lifecycle_state,
            tick_finalization_runtime=self._primitive_tick_finalization_runtime,
            set_debug_state=lambda state: setattr(self, "_debug_state", state),
            execution_runtime=self._primitive_execution_runtime,
            report_runtime=(
                lambda: (
                    self._primitive_report_composition_runtime().report_runtime()
                )
            ),
        )

    def _primitive_runtime_kernel_runtime(self) -> PrimitivePlannerPublicRuntime:
        return PrimitivePlannerPublicRuntime.from_ports(
            self._primitive_runtime_kernel_runtime_ports()
        )

    def _primitive_reset_lifecycle_service(self) -> PrimitiveResetLifecycleService:
        return PrimitiveResetLifecycleService.from_ports(
            self._primitive_reset_lifecycle_ports()
        )

    def _primitive_reset_lifecycle_ports(self) -> PrimitiveResetLifecyclePorts:
        return PrimitiveResetLifecyclePorts(
            all_policies=lambda: self._action_dispatch_service().all_policies(),
            reset_boundary_detector=lambda: self.boundary_detector.reset(),
            bootstrap_end_mode=lambda: str(self.bootstrap_end_mode),
            bootstrap_policy_available=lambda: self.bootstrap_policy is not None,
            scripted_bootstrap_enabled=lambda: self._scripted_bootstrap_enabled(),
            should_pre_dig_align_before_dig=(
                lambda: self._primitive_pre_dig_align_runtime_service()
                .should_pre_dig_align_before_dig()
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

    def _primitive_scripted_bootstrap_runtime_state(
        self,
    ) -> PrimitiveScriptedBootstrapRuntimeState:
        state = self.__dict__.get("_scripted_bootstrap_state")
        if state is None:
            state = PrimitiveScriptedBootstrapRuntimeState.fresh()
            self.__dict__["_scripted_bootstrap_state"] = state
        return state

    def _primitive_pre_dig_align_runtime_state(
        self,
    ) -> PrimitivePreDigAlignRuntimeState:
        state = self.__dict__.get("_pre_dig_align_runtime_state")
        if state is None:
            state = PrimitivePreDigAlignRuntimeState.fresh(
                action_dim=int(getattr(self, "action_dim", 4))
            )
            self.__dict__["_pre_dig_align_runtime_state"] = state
        return state

    def _scripted_bootstrap_report_status(
        self,
    ) -> PrimitiveScriptedBootstrapReportStatus:
        return self._primitive_scripted_bootstrap_runtime_state().to_report_status()

    def _primitive_observation_injection_runtime_state(
        self,
    ) -> PrimitiveObservationInjectionRuntimeState:
        state = self.__dict__.get("_observation_injection_state")
        if state is None:
            state = PrimitiveObservationInjectionRuntimeState.fresh()
            self.__dict__["_observation_injection_state"] = state
        return state

    def _primitive_token_runtime_state(self) -> PrimitiveTokenRuntimeState:
        state = self.__dict__.get("_token_state")
        if state is None:
            state = PrimitiveTokenRuntimeState.fresh()
            self.__dict__["_token_state"] = state
        return state

    def _coverage_runtime_state(self) -> CoverageRuntimeState:
        state = self.__dict__.get("_coverage_state")
        if state is None:
            state = CoverageRuntimeState()
            self.__dict__["_coverage_state"] = state
        return state

    def _primitive_boundary_event_runtime_service(
        self,
    ) -> PrimitiveBoundaryEventRuntimeService:
        return PrimitiveBoundaryEventRuntimeService.from_ports(
            self._primitive_boundary_event_runtime_ports()
        )

    def _primitive_boundary_event_runtime_ports(
        self,
    ) -> PrimitiveBoundaryEventRuntimePorts:
        return PrimitiveBoundaryEventRuntimePorts(
            execution_state=self._primitive_execution_runtime_state(),
            boundary_detector=self.boundary_detector,
            observation_facts=lambda obs: PrimitiveObservationFacts.from_obs(
                obs,
                action_dim=int(self.action_dim),
            ),
        )

    def _primitive_tick_finalization_runtime_ports(
        self,
    ) -> PrimitiveTickFinalizationRuntimePorts:
        return PrimitiveTickFinalizationRuntimePorts(
            execution_state=self._primitive_execution_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            cycle_report_status=self._cycle_report_status,
            first_dig_policy_active=(
                lambda: self._action_dispatch_service().first_dig_policy_active()
            ),
            skill_ids=PRIMITIVE_SKILL_IDS,
            primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            transition_skill_names=("return",),
            return_skill_name="return",
            return_max_steps=int(self.return_max_steps),
            work_hybrid_mode=HYBRID_MODE_WORK,
            transition_hybrid_mode=HYBRID_MODE_TRANSITION,
        )

    def _primitive_tick_finalization_runtime(
        self,
    ) -> PrimitiveTickFinalizationRuntime:
        return PrimitiveTickFinalizationRuntime.from_ports(
            self._primitive_tick_finalization_runtime_ports()
        )

    def _action_dispatch_service(self) -> PrimitiveActionDispatchService:
        return PrimitiveActionDispatchService.from_ports(self._action_dispatch_ports())

    def _action_dispatch_ports(self) -> PrimitiveActionDispatchPorts:
        return PrimitiveActionDispatchPorts(
            execution_state=self._primitive_execution_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
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
            policy_observation=(
                lambda obs: self._primitive_token_observation_runtime().policy_obs(
                    obs
                )
            ),
            scripted_bootstrap_enabled=lambda: self._scripted_bootstrap_enabled(),
            scripted_bootstrap_action=lambda obs: self._scripted_bootstrap_action(obs),
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            dig_skill_name="dig",
            pre_dig_align_action=(
                lambda obs: self._primitive_pre_dig_align_runtime_service().action(
                    obs
                )
            ),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )

    def _decision_runtime(self) -> PrimitiveDecisionRuntime:
        legacy_factory_ports = LegacyFSMDecisionBackendFactoryPorts(
            capability_provider_config=self._fsm_capability_provider_config,
            semantic_boundary_profile_active=(
                lambda: self._semantic_boundary_profile_active()
            ),
            cycle_state=self._primitive_cycle_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            return_handoff_readiness_service=(
                self._primitive_return_handoff_runtime().readiness_service()
            ),
            current_skill_name=lambda: str(self._skill_name),
            current_switch_reason=lambda: str(self._switch_reason),
            should_end_bootstrap=self._should_end_bootstrap,
            bootstrap_end_mode=lambda: str(self.bootstrap_end_mode),
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            dig_skill_name="dig",
            carry_skill_name="carry",
            dump_skill_name="dump",
            return_skill_name="return",
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            pre_dig_align_service=(
                self._primitive_pre_dig_align_runtime_service()
            ),
        )
        return PrimitiveDecisionRuntime.from_ports(
            PrimitiveDecisionRuntimePorts(
                backend_factories={
                    LEGACY_FSM_DECISION_BACKEND_NAME: (
                        lambda: LegacyFSMDecisionBackendFactory.from_runtime_ports(
                            legacy_factory_ports
                        )
                    ),
                },
            ),
            config=self._decision_runtime_config(),
        )

    @staticmethod
    def _decision_runtime_config() -> PrimitiveDecisionRuntimeConfig:
        return PrimitiveDecisionRuntimeConfig()

    def _primitive_requested_effect_runtime_ports(
        self,
    ) -> PrimitiveRequestedEffectRuntimePorts:
        return PrimitiveRequestedEffectRuntimePorts(
            cycle_state=self._primitive_cycle_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            set_skill=lambda skill, reason: self._set_skill(skill, reason),
            return_transition_next_skill_name="dig",
            return_transition_next_skill=(
                lambda: (
                    PRE_DIG_ALIGN_SKILL_NAME
                    if self._primitive_pre_dig_align_runtime_service()
                    .should_pre_dig_align_before_dig()
                    else "dig"
                )
            ),
            coverage_effect_runtime=self._primitive_coverage_effect_runtime(),
            dig_recovery_service=self._primitive_dig_recovery(),
            return_handoff_runtime=self._primitive_return_handoff_runtime(),
            action_dim=int(self.action_dim),
        )

    def _primitive_requested_effect_runtime(self) -> PrimitiveRequestedEffectRuntime:
        return PrimitiveRequestedEffectRuntime.from_ports(
            self._primitive_requested_effect_runtime_ports()
        )

    def _primitive_execution_runtime_ports(self) -> PrimitiveExecutionRuntimePorts:
        return PrimitiveExecutionRuntimePorts(
            execution_state=self._primitive_execution_runtime_state(),
            boundary_event_runtime=self._primitive_boundary_event_runtime_service(),
            dig_progress_runtime=self._primitive_dig_progress_runtime_service(),
            decision_runtime=self._decision_runtime(),
            requested_effect_applier=self._primitive_requested_effect_runtime(),
            tick_finalization_runtime=self._primitive_tick_finalization_runtime(),
            action_dispatch_service=self._action_dispatch_service(),
        )

    def _primitive_execution_runtime(self) -> PrimitiveExecutionRuntime:
        return PrimitiveExecutionRuntime.from_ports(
            self._primitive_execution_runtime_ports()
        )

    def predict(self, obs: dict) -> np.ndarray:
        return self._primitive_runtime_kernel_runtime().predict(obs)

    def debug_state(self) -> dict[str, Any]:
        return self._primitive_runtime_kernel_runtime().debug_state()

    def _primitive_coverage_static_config(self) -> PrimitiveCoverageStaticConfig:
        return PrimitiveCoverageStaticConfig(
            dig_cut_prior=dict(self.dig_cut_prior or {}),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            dig_cut_planner_mode=str(self.dig_cut_planner_mode),
            action_dim=int(self.action_dim),
            candidate_layout=str(self.coverage_candidate_layout),
            entry_x_percentiles=tuple(self.coverage_entry_x_percentiles),
            entry_z_percentiles=tuple(self.coverage_entry_z_percentiles),
            cut_direction_percentile=str(self.coverage_cut_direction_percentile),
            cut_length_percentile=str(self.coverage_cut_length_percentile),
            cut_depth_percentile=str(self.coverage_cut_depth_percentile),
            payload_percentile=str(self.coverage_payload_percentile),
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
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            first_dig_preferred_corridor_id=(
                self.coverage_first_dig_preferred_corridor_id
            ),
            first_dig_preferred_bonus=float(self.coverage_first_dig_preferred_bonus),
            first_dig_proximity_weight=float(self.coverage_first_dig_proximity_weight),
            first_dig_max_entry_distance_m=self.coverage_first_dig_max_entry_distance_m,
            first_dig_qpos_delta_weight=float(self.coverage_first_dig_qpos_delta_weight),
            first_dig_max_qpos_delta=self.coverage_first_dig_max_qpos_delta,
            pre_dig_align_controlled_dims=self.pre_dig_align_controlled_dims,
            state_exemplars_enabled=bool(self.coverage_state_exemplars_enabled),
            state_exemplar_path=str(self.coverage_state_exemplar_path),
            state_exemplar_k=int(self.coverage_state_exemplar_k),
            state_exemplar_removed_depth_scale_m=float(
                self.coverage_state_exemplar_removed_depth_scale_m
            ),
            state_exemplar_target_cell_weight=float(
                self.coverage_state_exemplar_target_cell_weight
            ),
            state_exemplar_temperature=float(self.coverage_state_exemplar_temperature),
            state_exemplar_skip_rejected=bool(
                self.coverage_state_exemplar_skip_rejected
            ),
            state_exemplar_score_weight=float(self.coverage_state_exemplar_score_weight),
            state_exemplars_by_cell=self.coverage_state_exemplars_by_cell,
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
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
            global_low_productivity_stop=int(
                self.coverage_global_low_productivity_stop
            ),
        )

    def _primitive_coverage_report_runtime_ports(
        self,
    ) -> CoverageReportBoundaryPorts:
        return CoverageReportBoundaryPorts(
            state=self._coverage_runtime_state(),
            static_config=self._primitive_coverage_static_config(),
            cycle_index=lambda: int(self._primitive_cycle_runtime_state().cycle_index),
            skill_name=lambda: str(self._skill_name),
            observation_facts=(
                lambda obs: PrimitiveObservationFacts.from_obs(
                    obs,
                    action_dim=int(self.action_dim),
                )
            ),
            selection_service=(
                lambda: (
                    self._primitive_coverage_selection_runtime()
                    .coverage_selection_service()
                )
            ),
        )

    def _primitive_coverage_report_runtime(self) -> PrimitiveCoverageReportRuntime:
        return PrimitiveCoverageReportRuntime.from_ports(
            self._primitive_coverage_report_runtime_ports()
        )

    def _primitive_report_composition_runtime_ports(
        self,
    ) -> PrimitiveReportCompositionPorts:
        return PrimitiveReportCompositionPorts(
            debug_state=lambda: self._debug_state,
            cycle_report_status=self._cycle_report_status,
            return_report_status=self._return_report_status,
            token_state=self._primitive_token_runtime_state,
            observation_injection_state=(
                self._primitive_observation_injection_runtime_state
            ),
            coverage_state=self._coverage_runtime_state,
            coverage_report_runtime=self._primitive_coverage_report_runtime,
            coverage_selection_service=(
                lambda: (
                    self._primitive_coverage_selection_runtime()
                    .coverage_selection_service()
                )
            ),
            cell_entry_state=PrimitiveCellEntryCompatibilityRuntimeState.fresh,
            scripted_bootstrap_report_status=(
                self._scripted_bootstrap_report_status
            ),
            pre_dig_align_state=self._primitive_pre_dig_align_runtime_state,
            pre_dig_align_enabled=lambda: bool(self.pre_dig_align_enabled),
            pre_dig_align_first_dig_only=(
                lambda: bool(self.pre_dig_align_first_dig_only)
            ),
            pre_dig_align_replan_after_failed_dig=(
                lambda: bool(self.pre_dig_align_replan_after_failed_dig)
            ),
            pre_dig_align_entry_intent_controlled_dims=(
                lambda: self.pre_dig_align_entry_intent_controlled_dims
            ),
            pre_dig_align_surface_guard_enabled=(
                lambda: bool(self.pre_dig_align_surface_guard_enabled)
            ),
            pre_dig_align_active_for_next_dig=(
                lambda: self._primitive_pre_dig_align_runtime_service()
                .should_pre_dig_align_before_dig()
            ),
            pre_dig_align_first_dig_entry_close_handoff=(
                lambda: bool(self.pre_dig_align_first_dig_entry_close_handoff)
            ),
            pre_dig_align_entry_intent_handoff_enabled=(
                lambda: bool(self.pre_dig_align_entry_intent_handoff_enabled)
            ),
            pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max=(
                lambda: (
                    self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
                )
            ),
            pre_dig_align_controlled_dims=(
                lambda: self.pre_dig_align_controlled_dims
            ),
            pre_dig_align_bucket_target_qpos=(
                lambda: self.pre_dig_align_bucket_target_qpos
            ),
            action_dim=lambda: int(getattr(self, "action_dim", 4)),
            goal_sector_id=self._primitive_token_planner_factory().goal_sector_id,
            next_goal_sector_id=(
                lambda: (
                    self._primitive_token_planner_factory().next_goal_sector_id(
                        self._primitive_cycle_runtime_state().cycle_index
                    )
                )
            ),
            dig_failed_replan_next_skill=(
                lambda: str(self.dig_failed_replan_next_skill)
            ),
            dump_done_use_boundary_event=(
                lambda: bool(self.dump_done_use_boundary_event)
            ),
            skill_name=lambda: str(self._skill_name),
            return_target_planner_enabled=(
                lambda: bool(self.return_target_planner_enabled)
            ),
            return_target_token_source=(
                lambda: str(
                    self._primitive_token_runtime_state()
                    .return_target_token_source
                )
            ),
            return_to_dig_max_entry_error_m=(
                lambda: self.return_to_dig_max_entry_error_m
            ),
            dig_depth_profile_source=lambda: str(self.dig_depth_profile_source),
            dig_depth_profile_required=(
                lambda: bool(self.dig_depth_profile_required)
            ),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            dig_cut_prior_id=lambda: str(self.dig_cut_prior_id),
            dig_cut_prior_path=lambda: str(self.dig_cut_prior_path),
        )

    def _primitive_report_composition_runtime(
        self,
    ) -> PrimitiveReportCompositionRuntime:
        return PrimitiveReportCompositionRuntime.from_ports(
            self._primitive_report_composition_runtime_ports()
        )

    def rollout_summary(self) -> dict[str, float | int | str | list[str]]:
        return self._primitive_runtime_kernel_runtime().rollout_summary()

    def planner_trace(self) -> dict[str, object]:
        return self._primitive_runtime_kernel_runtime().planner_trace()

    def _primitive_return_handoff_runtime_ports(
        self,
    ) -> PrimitiveReturnHandoffRuntimePorts:
        return PrimitiveReturnHandoffRuntimePorts(
            config=self._primitive_return_handoff_config,
            action_dim=int(getattr(self, "action_dim", 0)),
            execution_state=self._primitive_execution_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
            return_state=self._primitive_return_runtime_state(),
            token_state=self._primitive_token_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            set_skill=lambda skill, reason: self._set_skill(skill, reason),
            ensure_return_target_plan_for_cycle=(
                lambda obs: (
                    self._primitive_token_observation_runtime()
                    .ensure_return_target_plan_for_cycle(obs)
                )
            ),
            return_start_envelope_prior_bounds=(
                lambda corridor_id: (
                    self._primitive_token_planning_runtime()
                    .return_start_envelope_prior_bounds(corridor_id)
                )
            ),
            return_start_envelope_prior_mapping=(
                lambda corridor_id: (
                    self._primitive_token_planning_runtime()
                    .return_start_envelope_prior_mapping(
                        corridor_id=corridor_id,
                    )[0]
                )
            ),
            should_pre_dig_align_before_dig=(
                lambda: self._primitive_pre_dig_align_runtime_service()
                .should_pre_dig_align_before_dig()
            ),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            dig_skill_name="dig",
        )

    def _primitive_return_handoff_runtime(self) -> PrimitiveReturnHandoffRuntime:
        return PrimitiveReturnHandoffRuntime.from_ports(
            self._primitive_return_handoff_runtime_ports()
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
            coverage_state=self._coverage_runtime_state(),
            reset_active_policy=(
                lambda: self._action_dispatch_service().active_policy().reset()
            ),
            clear_dig_cut_plan=(
                lambda: (
                    self._primitive_token_observation_runtime()
                    .primitive_token_runtime()
                    .clear_dig_cut_plan()
                )
            ),
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
            pre_dig_align_state=self._primitive_pre_dig_align_runtime_state(),
            reset_active_policy=(
                lambda: self._action_dispatch_service().active_policy().reset()
            ),
            invalidate_pending_dig_cut_plan=(
                lambda: (
                    self._primitive_token_observation_runtime()
                    .primitive_token_runtime()
                    .invalidate_pending_dig_cut_plan()
                )
            ),
            clear_dig_cut_plan=(
                lambda: (
                    self._primitive_token_observation_runtime()
                    .primitive_token_runtime()
                    .clear_dig_cut_plan()
                )
            ),
            build_operator_prior_coverage_dig_cut_tokens=(
                lambda obs: (
                    self._primitive_token_planning_runtime()
                    .build_operator_prior_coverage_dig_cut_tokens(obs)
                )
            ),
            raw_fields_in_prior_range=(
                lambda raw_fields: (
                    self._primitive_token_planner_factory()
                    .dig_cut_token_planner()
                    .raw_fields_in_prior_range(raw_fields)
                )
            ),
            pre_dig_align_entry_error=(
                lambda obs: self._primitive_pre_dig_align_runtime_service()
                .entry_error(obs)
            ),
            pre_dig_align_timeout_can_handoff=(
                lambda obs: self._primitive_pre_dig_align_runtime_service()
                .timeout_can_handoff(obs)
            ),
            set_skill=lambda skill_name, reason: self._set_skill(
                skill_name,
                reason,
            ),
            record_coverage_decision_event=(
                lambda event, *, obs, corridor, extra: (
                    self._primitive_coverage_report_runtime().record_decision_event(
                        event,
                        obs=obs,
                        corridor=corridor,
                        extra=extra,
                    )
                )
            ),
            request_coverage_terminal_stop=(
                lambda reason, *, replace=False: (
                    self._primitive_coverage_effect_runtime()
                    .request_coverage_terminal_stop(
                        reason,
                        replace=replace,
                    )
                )
            ),
            observation_facts=(
                lambda obs: PrimitiveObservationFacts.from_obs(
                    obs,
                    action_dim=int(self.action_dim),
                )
            ),
            should_pre_dig_align_before_dig=(
                lambda: self._primitive_pre_dig_align_runtime_service()
                .should_pre_dig_align_before_dig()
            ),
            should_pre_dig_align_after_failed_dig=(
                lambda: self._primitive_pre_dig_align_runtime_service()
                .should_pre_dig_align_after_failed_dig()
            ),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            dig_failed_replan_next_skill=(
                lambda: str(self.dig_failed_replan_next_skill)
            ),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )

    def _should_end_bootstrap(self, *, obs: dict, boundary_event: Any | None) -> bool:
        scripted_bootstrap = self._primitive_scripted_bootstrap_runtime_service()
        if scripted_bootstrap.enabled():
            return scripted_bootstrap.should_end_bootstrap(obs)
        observation = PrimitiveObservationFacts.from_obs(
            obs,
            action_dim=int(self.action_dim),
        )
        status = BootstrapStatus.from_inputs(
            observation=observation,
            boundary_event=boundary_event,
            bootstrap_policy_present=self.bootstrap_policy is not None,
            bootstrap_end_mode=str(self.bootstrap_end_mode),
            bootstrap_end_min_bucket_mass_kg=float(
                self.bootstrap_end_min_bucket_mass_kg
            ),
            bootstrap_end_min_distance_to_dig_area_m=float(
                self.bootstrap_end_min_distance_to_dig_area_m
            ),
        )
        return status.should_end

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

    def _scripted_bootstrap_action(self, obs: dict) -> np.ndarray:
        return self._primitive_scripted_bootstrap_runtime_service().action(obs)

    def _primitive_pre_dig_align_runtime_config(
        self,
    ) -> PrimitivePreDigAlignRuntimeConfig:
        return PrimitivePreDigAlignRuntimeConfig(
            action_dim=int(self.action_dim),
            enabled=bool(self.pre_dig_align_enabled),
            first_dig_only=bool(self.pre_dig_align_first_dig_only),
            replan_after_failed_dig=bool(
                self.pre_dig_align_replan_after_failed_dig
            ),
            kp=float(self.pre_dig_align_kp),
            kd=float(self.pre_dig_align_kd),
            action_clip=self.pre_dig_align_action_clip,
            action_signs=self.pre_dig_align_action_signs,
            controlled_dims=self.pre_dig_align_controlled_dims,
            entry_intent_controlled_dims=(
                self.pre_dig_align_entry_intent_controlled_dims
            ),
            bucket_target_qpos=self.pre_dig_align_bucket_target_qpos,
            qpos_tolerance=self.pre_dig_align_qpos_tolerance,
            qvel_abs_max=float(self.pre_dig_align_qvel_abs_max),
            hold_steps=int(self.pre_dig_align_hold_steps),
            max_steps=int(self.pre_dig_align_max_steps),
            max_entry_error_m=self.pre_dig_align_max_entry_error_m,
            timeout_accept_entry_error_m=(
                self.pre_dig_align_timeout_accept_entry_error_m
            ),
            timeout_replan_entry_error_m=(
                self.pre_dig_align_timeout_replan_entry_error_m
            ),
            start_envelope_enabled=bool(
                self.pre_dig_align_start_envelope_enabled
            ),
            first_dig_entry_close_handoff=bool(
                self.pre_dig_align_first_dig_entry_close_handoff
            ),
            first_dig_entry_close_handoff_qvel_abs_max=(
                self.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
            ),
            start_envelope_max_entry_error_m=float(
                self.pre_dig_align_start_envelope_max_entry_error_m
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
            qpos_min=self.pre_dig_align_qpos_min,
            qpos_max=self.pre_dig_align_qpos_max,
            qpos_from_token_coefficients=(
                self.pre_dig_align_qpos_from_token_coefficients
            ),
        )

    def _primitive_pre_dig_align_runtime_ports(
        self,
    ) -> PrimitivePreDigAlignPorts:
        return PrimitivePreDigAlignPorts(
            ensure_dig_cut_plan_for_cycle=(
                lambda obs: (
                    self._primitive_token_observation_runtime()
                    .ensure_dig_cut_plan_for_cycle(obs)
                )
            ),
            dig_cut_tokens=lambda: self._primitive_token_runtime_state().dig_cut_tokens,
            active_coverage_corridor=(
                lambda: self._coverage_runtime_state().active_corridor()
            ),
            bucket_tip_dig_area_pose=(
                lambda obs: (
                    PrimitiveObservationFacts.from_obs(
                        obs,
                        action_dim=int(self.action_dim),
                    ).bucket_tip_dig_area_pose()
                )
            ),
            bucket_dig_area_pose=(
                lambda obs: (
                    PrimitiveObservationFacts.from_obs(
                        obs,
                        action_dim=int(self.action_dim),
                    ).bucket_dig_area_pose()
                )
            ),
            bucket_depth_below_local_surface=(
                lambda obs: (
                    PrimitiveObservationFacts.from_obs(
                        obs,
                        action_dim=int(self.action_dim),
                    ).env_state_value(
                        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX
                    )
                )
            ),
            bucket_dig_area_contact_mask=(
                lambda obs: (
                    PrimitiveObservationFacts.from_obs(
                        obs,
                        action_dim=int(self.action_dim),
                    ).env_state_value(
                        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
                        default=0.0,
                    )
                    > 0.5
                )
            ),
            cycle_index=lambda: int(self._primitive_cycle_runtime_state().cycle_index),
        )

    def _primitive_pre_dig_align_runtime_service(
        self,
    ) -> PrimitivePreDigAlignRuntimeService:
        return PrimitivePreDigAlignRuntimeService.from_ports(
            config=self._primitive_pre_dig_align_runtime_config(),
            state=self._primitive_pre_dig_align_runtime_state(),
            ports=self._primitive_pre_dig_align_runtime_ports(),
        )

    def _update_dig_progress(self, obs: dict) -> None:
        self._primitive_dig_progress_runtime_service().update(obs)

    def _primitive_dig_progress_runtime_service(
        self,
    ) -> PrimitiveDigProgressRuntimeService:
        return PrimitiveDigProgressRuntimeService.from_ports(
            self._primitive_dig_progress_runtime_ports()
        )

    def _primitive_dig_progress_runtime_ports(
        self,
    ) -> PrimitiveDigProgressRuntimePorts:
        return PrimitiveDigProgressRuntimePorts(
            cycle_state=self._primitive_cycle_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            observation_facts=lambda obs: PrimitiveObservationFacts.from_obs(
                obs,
                action_dim=int(self.action_dim),
            ),
            config=PrimitiveDigProgressRuntimeConfig(
                plateau_epsilon_kg=float(self.dig_to_carry_mass_plateau_epsilon_kg)
            ),
        )

    def _semantic_boundary_profile_active(self) -> bool:
        config = getattr(self.boundary_detector, "config", None)
        profile = str(getattr(config, "boundary_profile", "legacy"))
        return profile == "v2_4_5_spatial_mass"

    def _primitive_token_observation_runtime(
        self,
    ) -> PrimitiveTokenObservationRuntime:
        return PrimitiveTokenObservationRuntime.from_ports(
            self._primitive_token_observation_runtime_ports()
        )

    def _primitive_token_observation_runtime_ports(
        self,
    ) -> PrimitiveTokenObservationRuntimePorts:
        return PrimitiveTokenObservationRuntimePorts(
            observation_injection_state=(
                self._primitive_observation_injection_runtime_state()
            ),
            token_state=self._primitive_token_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            goal_tokens=(
                lambda: (
                    self._primitive_token_planner_factory().goal_tokens_for_cycle(
                        self._primitive_cycle_runtime_state().cycle_index
                    )
                )
            ),
            current_skill_name=lambda: str(self._skill_name),
            bootstrap_policy_available=lambda: self.bootstrap_policy is not None,
            cycle_index=lambda: int(self._primitive_cycle_runtime_state().cycle_index),
            dig_cut_planner_enabled=lambda: bool(self.dig_cut_planner_enabled),
            dig_cut_hold_token_until_skill_exit=(
                lambda: bool(self.dig_cut_hold_token_until_skill_exit)
            ),
            coverage_terminal_stop_requested=(
                lambda: bool(
                    self._coverage_runtime_state().coverage_terminal_stop_requested
                )
            ),
            return_target_planner_enabled=(
                lambda: bool(self.return_target_planner_enabled)
            ),
            return_target_hold_token_until_skill_exit=(
                lambda: bool(self.return_target_hold_token_until_skill_exit)
            ),
            build_dig_cut_tokens_for_obs=(
                lambda obs: (
                    self._primitive_token_planning_runtime()
                    .build_dig_cut_tokens_for_obs(obs)
                )
            ),
            build_dig_depth_profile_tokens_for_obs=(
                lambda obs: (
                    self._primitive_token_planning_runtime()
                    .build_dig_depth_profile_tokens_for_obs(obs)
                )
            ),
            build_next_dig_cut_plan_for_return=(
                lambda obs: (
                    self._primitive_token_planning_runtime()
                    .build_next_dig_cut_plan_for_return(obs)
                )
            ),
            build_return_start_envelope_tokens_for_obs=(
                lambda obs, raw_fields, *, corridor_id: (
                    self._primitive_token_planning_runtime()
                    .build_return_start_envelope_tokens_for_obs(
                        obs,
                        raw_fields,
                        corridor_id=corridor_id,
                    )
                )
            ),
            plan_return_relocate_tokens=(
                lambda token: (
                    self._primitive_token_planner_factory()
                    .return_relocate_token_planner()
                    .plan(token)
                )
            ),
            dig_skill_name="dig",
            return_skill_name="return",
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
        )

    def _primitive_token_planning_runtime(self) -> PrimitiveTokenPlanningRuntime:
        return PrimitiveTokenPlanningRuntime.from_ports(
            self._primitive_token_planning_runtime_ports()
        )

    def _primitive_token_planning_runtime_ports(
        self,
    ) -> PrimitiveTokenPlanningRuntimePorts:
        return PrimitiveTokenPlanningRuntimePorts(
            token_state=self._primitive_token_runtime_state(),
            coverage_state=self._coverage_runtime_state(),
            dig_cut_planner_mode=lambda: str(self.dig_cut_planner_mode),
            dig_cut_planner_fallback_mode=(
                lambda: str(self.dig_cut_planner_fallback_mode)
            ),
            cycle_index=lambda: int(self._primitive_cycle_runtime_state().cycle_index),
            dig_cut_token_planner=(
                self._primitive_token_planner_factory().dig_cut_token_planner
            ),
            dig_depth_profile_token_planner=(
                self._primitive_token_planner_factory()
                .dig_depth_profile_token_planner
            ),
            return_target_token_planner=(
                self._primitive_token_planner_factory().return_target_token_planner
            ),
            return_start_envelope_token_planner=(
                self._primitive_token_planner_factory()
                .return_start_envelope_token_planner
            ),
            observation_facts=(
                lambda obs: PrimitiveObservationFacts.from_obs(
                    obs,
                    action_dim=int(self.action_dim),
                )
            ),
            select_next_coverage_corridor=(
                lambda obs: (
                    self._primitive_coverage_selection_runtime()
                    .select_next_coverage_corridor(obs)
                )
            ),
            coverage_raw_fields=(
                lambda corridor, *, obs, update_state=False: (
                    self._primitive_coverage_selection_runtime()
                    .coverage_raw_fields(
                        corridor,
                        obs=obs,
                        update_state=update_state,
                    )
                )
            ),
        )

    def _primitive_coverage_selection_runtime_ports(
        self,
    ) -> CoverageSelectionBoundaryPorts:
        return CoverageSelectionBoundaryPorts(
            state=self._coverage_runtime_state(),
            static_config=self._primitive_coverage_static_config(),
            cycle_index=lambda: int(self._primitive_cycle_runtime_state().cycle_index),
            observation_facts=(
                lambda obs: PrimitiveObservationFacts.from_obs(
                    obs,
                    action_dim=int(self.action_dim),
                )
            ),
            maybe_reopen_pass=(
                lambda obs, reason: (
                    self._primitive_coverage_effect_runtime()
                    .maybe_reopen_coverage_pass(obs, reason=reason)
                )
            ),
            request_terminal_stop=(
                lambda reason: (
                    self._primitive_coverage_effect_runtime()
                    .request_coverage_terminal_stop(reason)
                )
            ),
            record_decision_event=(
                self._primitive_coverage_report_runtime().record_decision_event
            ),
        )

    def _primitive_coverage_selection_runtime(
        self,
    ) -> PrimitiveCoverageSelectionRuntime:
        return PrimitiveCoverageSelectionRuntime.from_ports(
            self._primitive_coverage_selection_runtime_ports()
        )

    def _primitive_coverage_effect_runtime_ports(
        self,
    ) -> CoverageEffectBoundaryPorts:
        return CoverageEffectBoundaryPorts(
            state=self._coverage_runtime_state(),
            cycle_state=self._primitive_cycle_runtime_state(),
            static_config=self._primitive_coverage_static_config(),
            observation_facts=(
                lambda obs: PrimitiveObservationFacts.from_obs(
                    obs,
                    action_dim=int(self.action_dim),
                )
            ),
            remaining_depth=lambda obs, corridor: (
                self._primitive_coverage_selection_runtime()
                .coverage_remaining_depth_for_corridor(
                    obs,
                    corridor,
                )
            ),
            corridor_attempt_limit=(
                lambda corridor: (
                    self._primitive_coverage_selection_runtime()
                    .coverage_corridor_attempt_limit(corridor)
                )
            ),
            record_decision_event=(
                self._primitive_coverage_report_runtime().record_decision_event
            ),
        )

    def _primitive_coverage_effect_runtime(self) -> PrimitiveCoverageEffectRuntime:
        return PrimitiveCoverageEffectRuntime.from_ports(
            self._primitive_coverage_effect_runtime_ports()
        )

    def _primitive_token_planner_factory(self) -> PrimitiveTokenPlannerFactory:
        return PrimitiveTokenPlannerFactory(
            PrimitiveTokenPlannerFactoryConfig(
                goal_sequence=tuple(self.goal_sequence),
                goal_scenario_id=str(self.goal_scenario_id),
                goal_depth_norm=float(self.goal_depth_norm),
                goal_dump_target_norm=float(self.goal_dump_target_norm),
                dig_cut_prior=dict(self.dig_cut_prior or {}),
                dig_depth_profile_source=str(self.dig_depth_profile_source),
                dig_depth_profile_required=bool(self.dig_depth_profile_required),
                dig_depth_profile_allow_live_fallback=bool(
                    self.dig_depth_profile_allow_live_fallback
                ),
                dig_depth_profile_allow_global_fallback=bool(
                    self.dig_depth_profile_allow_global_fallback
                ),
                return_target_token_source_prefix=str(
                    self.return_target_token_source_prefix
                ),
                return_start_envelope_use_cell_prior=bool(
                    self.return_start_envelope_use_cell_prior
                ),
                return_start_envelope_min_source_count=int(
                    self.return_start_envelope_min_source_count
                ),
                return_start_envelope_min_source_fraction=float(
                    self.return_start_envelope_min_source_fraction
                ),
                return_start_envelope_qpos_from_relocate_enabled=bool(
                    self.return_start_envelope_qpos_from_relocate_enabled
                ),
                return_start_envelope_qpos_from_relocate_coefficients=(
                    self.return_start_envelope_qpos_from_relocate_coefficients
                ),
                return_start_envelope_qpos_from_relocate_min=(
                    self.return_start_envelope_qpos_from_relocate_min
                ),
                return_start_envelope_qpos_from_relocate_max=(
                    self.return_start_envelope_qpos_from_relocate_max
                ),
                return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds=bool(
                    self.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds
                ),
                return_start_envelope_spatial_from_relocate_enabled=bool(
                    self.return_start_envelope_spatial_from_relocate_enabled
                ),
                return_start_envelope_spatial_from_relocate_coefficients=(
                    self.return_start_envelope_spatial_from_relocate_coefficients
                ),
                return_start_envelope_spatial_from_relocate_min=(
                    self.return_start_envelope_spatial_from_relocate_min
                ),
                return_start_envelope_spatial_from_relocate_max=(
                    self.return_start_envelope_spatial_from_relocate_max
                ),
                return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds=bool(
                    self.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds
                ),
            )
        )
