"""Report input assembly runtime for the primitive planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.primitive.compatibility.cell_entry import (
    PrimitiveCellEntryCompatibilityRuntimeState,
    PrimitiveCellEntryReportConfig,
    PrimitiveCellEntryReportStatus,
)
from testbed.planner.primitive.compatibility.pre_dig_align import (
    PrimitivePreDigAlignReportConfig,
    PrimitivePreDigAlignReportStatus,
    pre_dig_align_report_status_from_state,
)
from testbed.planner.primitive.coverage.reports import (
    CoverageReportConfig,
    CoverageReportService,
)
from testbed.planner.primitive.coverage.selection import CoverageSelectionService
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleReportStatus
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.execution.return_state import PrimitiveReturnReportStatus
from testbed.planner.primitive.execution.scripted_bootstrap import (
    PrimitiveScriptedBootstrapReportStatus,
)
from testbed.planner.primitive.execution.tick_finalization import (
    PrimitivePlannerDebugState,
)
from testbed.planner.primitive.facts.observation import (
    PrimitiveObservationInjectionRuntimeState,
)
from testbed.planner.primitive.report.debug_report import (
    PrimitiveDebugReportInputs,
    PrimitiveDebugStateSnapshot,
)
from testbed.planner.primitive.report.planner_trace import PrimitivePlannerTraceInputs
from testbed.planner.primitive.report.rollout_summary import (
    PrimitiveRolloutSummaryInputs,
)
from testbed.planner.primitive.token.state import (
    PrimitiveTokenReportStatus,
    PrimitiveTokenRuntimeState,
)
from testbed.planner.primitive.token.status import TokenStatus

TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY = "v2_2_primitive_return_policy"
TRANSITION_POLICY_MODE_PRIMITIVE = "primitive_return_policy"


@dataclass(frozen=True)
class PrimitiveReportRuntimePorts:
    """Typed dependencies for public report input assembly."""

    debug_state: Callable[[], PrimitivePlannerDebugState]
    cycle_report_status: Callable[[], PrimitiveCycleReportStatus]
    return_report_status: Callable[[], PrimitiveReturnReportStatus]
    token_status_for_debug_report: Callable[[], TokenStatus]
    token_report_status: Callable[[], PrimitiveTokenReportStatus]
    coverage_state: Callable[[], CoverageRuntimeState]
    coverage_report_config: Callable[[], CoverageReportConfig]
    coverage_selection_service: Callable[[], CoverageSelectionService]
    coverage_report_service: Callable[[], CoverageReportService]
    cell_entry_report_status: Callable[[], PrimitiveCellEntryReportStatus]
    scripted_bootstrap_report_status: Callable[
        [], PrimitiveScriptedBootstrapReportStatus
    ]
    pre_dig_align_report_status: Callable[[], PrimitivePreDigAlignReportStatus]
    goal_sector_id: Callable[[int], int]
    next_goal_sector_id: Callable[[], int]
    dig_failed_replan_next_skill: Callable[[], str]
    dump_done_use_boundary_event: Callable[[], bool]
    skill_name: Callable[[], str]
    return_target_planner_enabled: Callable[[], bool]
    return_target_token_source: Callable[[], str]
    return_to_dig_max_entry_error_m: Callable[[], float | None]


@dataclass(frozen=True)
class PrimitiveReportRuntime:
    """Own public report input assembly for debug, summary, and trace reports."""

    ports: PrimitiveReportRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveReportRuntimePorts,
    ) -> PrimitiveReportRuntime:
        return cls(ports=ports)

    def debug_report_inputs(self) -> PrimitiveDebugReportInputs:
        cycle_status = self.ports.cycle_report_status()
        return PrimitiveDebugReportInputs(
            debug_state=self.debug_state_snapshot_for_report(),
            transition_source=TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            transition_policy_mode=TRANSITION_POLICY_MODE_PRIMITIVE,
            transition_fallback_count=0,
            transition_fallback_reason="",
            primitive_goal_curr_sector_id=int(
                self.ports.goal_sector_id(cycle_status.primitive_cycle_index)
            ),
            primitive_goal_next_sector_id=int(self.ports.next_goal_sector_id()),
            token_status=self.ports.token_status_for_debug_report(),
            dig_failed_replan_next_skill=str(
                self.ports.dig_failed_replan_next_skill()
            ),
            return_fields=self.debug_report_return_fields(),
            pending_fields=self.debug_report_pending_fields(),
            dig_cut_fields=self.debug_report_dig_cut_fields(),
            coverage_fields=self.debug_report_coverage_fields(),
            cell_entry_fields=self.debug_report_cell_entry_fields(),
            scripted_bootstrap_fields=(
                self.debug_report_scripted_bootstrap_fields()
            ),
            dig_progress_fields=self.debug_report_dig_progress_fields(),
            pre_dig_align_fields=self.debug_report_pre_dig_align_fields(),
        )

    def debug_state_snapshot_for_report(self) -> PrimitiveDebugStateSnapshot:
        state = self.ports.debug_state()
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
            dump_release_ready_hold_count=int(
                state.dump_release_ready_hold_count
            ),
            primitive_cycle_index=int(state.primitive_cycle_index),
        )

    def debug_report_return_fields(self) -> dict[str, Any]:
        return self.ports.return_report_status().debug_fields()

    def debug_report_pending_fields(self) -> dict[str, Any]:
        return self.ports.token_report_status().pending_debug_fields()

    def debug_report_dig_cut_fields(self) -> dict[str, Any]:
        return self.ports.token_report_status().dig_cut_debug_fields()

    def debug_report_coverage_fields(self) -> dict[str, Any]:
        return self.ports.coverage_report_service().debug_fields_from_state(
            self.ports.coverage_state(),
            config=self.ports.coverage_report_config(),
            selection_service=self.ports.coverage_selection_service(),
        )

    def debug_report_cell_entry_fields(self) -> dict[str, Any]:
        return self.ports.cell_entry_report_status().debug_fields()

    def debug_report_scripted_bootstrap_fields(self) -> dict[str, Any]:
        return self.ports.scripted_bootstrap_report_status().debug_fields()

    def debug_report_dig_progress_fields(self) -> dict[str, Any]:
        return self.ports.cycle_report_status().dig_progress_debug_fields()

    def debug_report_pre_dig_align_fields(self) -> dict[str, Any]:
        return self.ports.pre_dig_align_report_status().debug_fields()

    def rollout_summary_inputs(self) -> PrimitiveRolloutSummaryInputs:
        cycle_status = self.ports.cycle_report_status()
        return_status = self.ports.return_report_status()
        scripted_bootstrap_status = self.ports.scripted_bootstrap_report_status()
        token_status = self.ports.token_report_status()
        coverage_status = (
            self.ports.coverage_report_service().summary_status_from_state(
                self.ports.coverage_state(),
                config=self.ports.coverage_report_config(),
            )
        )
        return PrimitiveRolloutSummaryInputs(
            transition_source=TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
            transition_policy_mode=TRANSITION_POLICY_MODE_PRIMITIVE,
            transition_fallback_count=0,
            transition_fallback_reason="",
            transition_timeout_count=cycle_status.transition_timeout_count,
            completed_transition_count=cycle_status.completed_transition_count,
            dump_done_use_boundary_event=bool(
                self.ports.dump_done_use_boundary_event()
            ),
            primitive_final_skill=str(self.ports.skill_name()),
            primitive_cycle_index=cycle_status.primitive_cycle_index,
            cell_entry=self.ports.cell_entry_report_status(),
            dig_cut_token_dim=int(DIG_CUT_TOKEN_DIM),
            return_target_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_target_token_source=str(
                self.ports.return_target_token_source()
            ),
            return_to_dig_max_entry_error_m=(
                self.ports.return_to_dig_max_entry_error_m()
            ),
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
            dig_failed_replan_next_skill=str(
                self.ports.dig_failed_replan_next_skill()
            ),
            coverage=coverage_status,
            scripted_bootstrap_timeout_count=(
                scripted_bootstrap_status.timeout_count
            ),
            pre_dig_align=self.ports.pre_dig_align_report_status(),
            dig_bad_replan_count=cycle_status.dig_bad_replan_count,
            dig_exit_guard_replan_count=(
                cycle_status.dig_exit_guard_replan_count
            ),
        )

    def planner_trace_inputs(self) -> PrimitivePlannerTraceInputs:
        coverage = self.ports.coverage_report_service().trace_status_from_state(
            self.ports.coverage_state(),
            config=self.ports.coverage_report_config(),
            selection_service=self.ports.coverage_selection_service(),
        )
        return PrimitivePlannerTraceInputs(
            cell_entry=self.ports.cell_entry_report_status(),
            token=self.ports.token_report_status(),
            return_target_planner_enabled=bool(
                self.ports.return_target_planner_enabled()
            ),
            coverage=coverage,
        )


@dataclass(frozen=True)
class PrimitiveReportCompositionPorts:
    """Typed owners and config providers for public report runtime composition."""

    debug_state: Callable[[], PrimitivePlannerDebugState]
    cycle_report_status: Callable[[], PrimitiveCycleReportStatus]
    return_report_status: Callable[[], PrimitiveReturnReportStatus]
    token_state: Callable[[], PrimitiveTokenRuntimeState]
    observation_injection_state: Callable[
        [], PrimitiveObservationInjectionRuntimeState
    ]
    coverage_state: Callable[[], CoverageRuntimeState]
    coverage_report_runtime: Callable[[], Any]
    coverage_selection_service: Callable[[], CoverageSelectionService]
    cell_entry_state: Callable[[], PrimitiveCellEntryCompatibilityRuntimeState]
    scripted_bootstrap_report_status: Callable[
        [], PrimitiveScriptedBootstrapReportStatus
    ]
    pre_dig_align_state: Callable[[], PrimitivePreDigAlignRuntimeState]
    pre_dig_align_enabled: Callable[[], bool]
    pre_dig_align_first_dig_only: Callable[[], bool]
    pre_dig_align_replan_after_failed_dig: Callable[[], bool]
    pre_dig_align_entry_intent_controlled_dims: Callable[[], Any]
    pre_dig_align_surface_guard_enabled: Callable[[], bool]
    pre_dig_align_active_for_next_dig: Callable[[], bool]
    pre_dig_align_first_dig_entry_close_handoff: Callable[[], bool]
    pre_dig_align_entry_intent_handoff_enabled: Callable[[], bool]
    pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max: Callable[
        [], float | None
    ]
    pre_dig_align_controlled_dims: Callable[[], Any]
    pre_dig_align_bucket_target_qpos: Callable[[], float | None]
    action_dim: Callable[[], int]
    goal_sector_id: Callable[[int], int]
    next_goal_sector_id: Callable[[], int]
    dig_failed_replan_next_skill: Callable[[], str]
    dump_done_use_boundary_event: Callable[[], bool]
    skill_name: Callable[[], str]
    return_target_planner_enabled: Callable[[], bool]
    return_target_token_source: Callable[[], str]
    return_to_dig_max_entry_error_m: Callable[[], float | None]
    dig_depth_profile_source: Callable[[], str]
    dig_depth_profile_required: Callable[[], bool]
    dig_cut_planner_mode: Callable[[], str]
    dig_cut_prior_id: Callable[[], str]
    dig_cut_prior_path: Callable[[], str]


@dataclass(frozen=True)
class PrimitiveReportCompositionRuntime:
    """Own report/status projection and report runtime port composition."""

    ports: PrimitiveReportCompositionPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveReportCompositionPorts,
    ) -> PrimitiveReportCompositionRuntime:
        return cls(ports=ports)

    def token_status_for_debug_report(self) -> TokenStatus:
        return self.ports.token_state().to_token_status(
            cell_entry_enabled=False,
            token_injection_state=(
                self.ports.observation_injection_state().to_token_injection_state()
            ),
            dig_depth_profile_source=str(self.ports.dig_depth_profile_source()),
            dig_depth_profile_required=bool(self.ports.dig_depth_profile_required()),
        )

    def token_report_status(self) -> PrimitiveTokenReportStatus:
        return self.ports.token_state().to_report_status(
            token_injection_state=(
                self.ports.observation_injection_state().to_token_injection_state()
            ),
            dig_cut_planner_mode=str(self.ports.dig_cut_planner_mode()),
            dig_cut_prior_id=str(self.ports.dig_cut_prior_id()),
            dig_cut_prior_path=str(self.ports.dig_cut_prior_path()),
        )

    @staticmethod
    def cell_entry_report_config() -> PrimitiveCellEntryReportConfig:
        return PrimitiveCellEntryReportConfig(enabled=False)

    def cell_entry_report_status(self) -> PrimitiveCellEntryReportStatus:
        return self.ports.cell_entry_state().to_report_status(
            self.cell_entry_report_config()
        )

    def pre_dig_align_report_config(self) -> PrimitivePreDigAlignReportConfig:
        return PrimitivePreDigAlignReportConfig(
            enabled=bool(self.ports.pre_dig_align_enabled()),
            first_dig_only=bool(self.ports.pre_dig_align_first_dig_only()),
            replan_after_failed_dig=bool(
                self.ports.pre_dig_align_replan_after_failed_dig()
            ),
            entry_intent_controlled_dims=(
                self.ports.pre_dig_align_entry_intent_controlled_dims()
            ),
            surface_guard_enabled=bool(
                self.ports.pre_dig_align_surface_guard_enabled()
            ),
            active_for_next_dig=bool(
                self.ports.pre_dig_align_active_for_next_dig()
            ),
            first_dig_entry_close_handoff=bool(
                self.ports.pre_dig_align_first_dig_entry_close_handoff()
            ),
            entry_intent_handoff_enabled=bool(
                self.ports.pre_dig_align_entry_intent_handoff_enabled()
            ),
            first_dig_entry_close_handoff_qvel_abs_max=(
                self.ports
                .pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max()
            ),
            controlled_dims=self.ports.pre_dig_align_controlled_dims(),
            bucket_target_qpos=self.ports.pre_dig_align_bucket_target_qpos(),
        )

    def pre_dig_align_report_status(self) -> PrimitivePreDigAlignReportStatus:
        return pre_dig_align_report_status_from_state(
            self.ports.pre_dig_align_state(),
            self.pre_dig_align_report_config(),
        )

    def report_runtime_ports(self) -> PrimitiveReportRuntimePorts:
        coverage_runtime = self.ports.coverage_report_runtime
        return PrimitiveReportRuntimePorts(
            debug_state=self.ports.debug_state,
            cycle_report_status=self.ports.cycle_report_status,
            return_report_status=self.ports.return_report_status,
            token_status_for_debug_report=self.token_status_for_debug_report,
            token_report_status=self.token_report_status,
            coverage_state=self.ports.coverage_state,
            coverage_report_config=lambda: coverage_runtime().report_config(),
            coverage_selection_service=self.ports.coverage_selection_service,
            coverage_report_service=lambda: coverage_runtime().report_service(),
            cell_entry_report_status=self.cell_entry_report_status,
            scripted_bootstrap_report_status=(
                self.ports.scripted_bootstrap_report_status
            ),
            pre_dig_align_report_status=self.pre_dig_align_report_status,
            goal_sector_id=self.ports.goal_sector_id,
            next_goal_sector_id=self.ports.next_goal_sector_id,
            dig_failed_replan_next_skill=self.ports.dig_failed_replan_next_skill,
            dump_done_use_boundary_event=self.ports.dump_done_use_boundary_event,
            skill_name=self.ports.skill_name,
            return_target_planner_enabled=self.ports.return_target_planner_enabled,
            return_target_token_source=self.ports.return_target_token_source,
            return_to_dig_max_entry_error_m=(
                self.ports.return_to_dig_max_entry_error_m
            ),
        )

    def report_runtime(self) -> PrimitiveReportRuntime:
        return PrimitiveReportRuntime.from_ports(self.report_runtime_ports())


__all__ = [
    "PrimitiveReportCompositionPorts",
    "PrimitiveReportCompositionRuntime",
    "PrimitiveReportRuntime",
    "PrimitiveReportRuntimePorts",
    "TRANSITION_POLICY_MODE_PRIMITIVE",
    "TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY",
]
