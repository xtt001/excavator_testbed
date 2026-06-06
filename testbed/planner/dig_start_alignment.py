"""Dig-start alignment target and action helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from testbed.planner import dig_start_alignment_runtime
from testbed.planner.dig_start_alignment_action import (
    AlignmentActionDecision as AlignmentActionDecision,
)
from testbed.planner.dig_start_alignment_action import (
    DigStartAlignmentActionService,
)
from testbed.planner.dig_start_alignment_action import (
    pd_servo_action as pd_servo_action,
)
from testbed.planner.dig_start_alignment_context import (
    DIG_START_ALIGNMENT_FACT_FIELDS as DIG_START_ALIGNMENT_FACT_FIELDS,
)
from testbed.planner.dig_start_alignment_context import (
    DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS as DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS,
)
from testbed.planner.dig_start_alignment_context import (
    DigStartAlignmentConfig as DigStartAlignmentConfig,
)
from testbed.planner.dig_start_alignment_context import (
    DigStartAlignmentEntryErrorFacts as DigStartAlignmentEntryErrorFacts,
)
from testbed.planner.dig_start_alignment_context import (
    DigStartAlignmentFacts as DigStartAlignmentFacts,
)
from testbed.planner.dig_start_alignment_context import (
    build_dig_start_alignment_entry_error_facts_from_observation_view as build_dig_start_alignment_entry_error_facts_from_observation_view,
)
from testbed.planner.dig_start_alignment_context import (
    build_dig_start_alignment_facts as build_dig_start_alignment_facts,
)
from testbed.planner.dig_start_alignment_context import (
    build_dig_start_alignment_facts_from_mapping as build_dig_start_alignment_facts_from_mapping,
)
from testbed.planner.dig_start_alignment_context import (
    build_dig_start_alignment_facts_from_observation_view as build_dig_start_alignment_facts_from_observation_view,
)
from testbed.planner.dig_start_alignment_context import (
    build_dig_start_alignment_runtime_config as build_dig_start_alignment_runtime_config,
)
from testbed.planner.dig_start_alignment_context import (
    build_dig_start_alignment_runtime_config_from_mapping as build_dig_start_alignment_runtime_config_from_mapping,
)
from testbed.planner.dig_start_alignment_context import (
    dig_start_alignment_entry_error as dig_start_alignment_entry_error,
)
from testbed.planner.dig_start_alignment_outcome import (
    DigStartAlignmentOutcomeService,
)
from testbed.planner.dig_start_alignment_outcome import (
    PreDigAlignOutcome as PreDigAlignOutcome,
)
from testbed.planner.dig_start_alignment_outcome import (
    PreDigAlignOutcomeRequest as PreDigAlignOutcomeRequest,
)
from testbed.planner.dig_start_alignment_outcome import (
    PreDigAlignOutcomeRuntimeFacts as PreDigAlignOutcomeRuntimeFacts,
)
from testbed.planner.dig_start_alignment_readiness import (
    AlignmentReadyDecision as AlignmentReadyDecision,
)
from testbed.planner.dig_start_alignment_readiness import (
    DigStartAlignmentReadinessService,
)
from testbed.planner.dig_start_alignment_readiness import (
    PreDigAlignTimeoutHandoffRequest as PreDigAlignTimeoutHandoffRequest,
)
from testbed.planner.dig_start_alignment_readiness import (
    SurfaceGuardDecision as SurfaceGuardDecision,
)
from testbed.planner.dig_start_alignment_readiness import (
    TimeoutHandoffDecision as TimeoutHandoffDecision,
)
from testbed.planner.dig_start_alignment_runtime import (
    DigStartAlignmentDebugSnapshot as DigStartAlignmentDebugSnapshot,
)
from testbed.planner.dig_start_alignment_runtime import (
    DigStartAlignmentDebugState as DigStartAlignmentDebugState,
)
from testbed.planner.dig_start_alignment_runtime import (
    DigStartAlignmentRuntimeService,
)
from testbed.planner.dig_start_alignment_runtime import (
    DigStartAlignmentRuntimeState as DigStartAlignmentRuntimeState,
)

DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS = (
    dig_start_alignment_runtime.DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS
)
DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS = (
    dig_start_alignment_runtime.DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS
)
debug_state_from_mapping = dig_start_alignment_runtime.debug_state_from_mapping
runtime_state_from_mapping = dig_start_alignment_runtime.runtime_state_from_mapping

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView


class DigStartAlignmentService(
    DigStartAlignmentActionService,
    DigStartAlignmentReadinessService,
    DigStartAlignmentOutcomeService,
    DigStartAlignmentRuntimeService,
):
    """Computes pre-dig alignment targets and actions without scheduler state."""

    @staticmethod
    def entry_error(facts: DigStartAlignmentEntryErrorFacts) -> float:
        return dig_start_alignment_entry_error(facts)

    @staticmethod
    def entry_error_from_observation_view(
        *,
        view: PlannerObservationView,
        active_corridor_entry_xz: tuple[float, float] | None,
    ) -> float:
        return dig_start_alignment_entry_error(
            build_dig_start_alignment_entry_error_facts_from_observation_view(
                view=view,
                active_corridor_entry_xz=active_corridor_entry_xz,
            )
        )

    @staticmethod
    def facts_from_observation_view(
        *,
        view: PlannerObservationView,
        target_qpos: object | None = None,
        entry_error_m: float = float("nan"),
        qpos: object | None = None,
        qvel: object | None = None,
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> DigStartAlignmentFacts:
        return build_dig_start_alignment_facts_from_observation_view(
            view=view,
            target_qpos=target_qpos,
            entry_error_m=entry_error_m,
            qpos=qpos,
            qvel=qvel,
            cycle_index=cycle_index,
            hold_count=hold_count,
        )
