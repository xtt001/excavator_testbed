"""Cell-entry online runtime service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from testbed.planner.snapshots import (
    bucket_dig_area_cell_in_bounds_mask_from_obs,
    bucket_dig_area_pose_from_obs,
    dig_cell_id_from_obs,
    mass_in_bucket_from_obs,
)

if TYPE_CHECKING:
    from testbed.planner.cell_entry import (
        CellEntryGoal,
        CellEntryPlanner,
        PlannerDecisionAudit,
        PlannerDecisionAuditor,
        PrimitiveCycleOutcome,
    )
    from testbed.planner.snapshots import PlannerObservationView


@dataclass(frozen=True)
class CellEntryRuntimeConfig:
    enabled: bool


@dataclass(frozen=True)
class CellEntryRuntimeFacts:
    cycle_index: int
    active_skill: str
    cell_id: int
    bucket_pose: tuple[float, float, float] | None
    geometry_available: bool
    bucket_mass_kg: float


CELL_ENTRY_RUNTIME_FACT_FIELDS: tuple[str, ...] = (
    "cycle_index",
    "active_skill",
    "cell_id",
    "bucket_pose",
    "geometry_available",
    "bucket_mass_kg",
)


def build_cell_entry_runtime_facts_from_mapping(
    values: Mapping[str, Any],
) -> CellEntryRuntimeFacts:
    return CellEntryRuntimeFacts(
        cycle_index=int(values["cycle_index"]),
        active_skill=str(values["active_skill"]),
        cell_id=int(values["cell_id"]),
        bucket_pose=values["bucket_pose"],
        geometry_available=bool(values["geometry_available"]),
        bucket_mass_kg=float(values["bucket_mass_kg"]),
    )


def build_cell_entry_runtime_facts_from_observation_view(
    *,
    view: PlannerObservationView,
    cycle_index: int,
    active_skill: str,
) -> CellEntryRuntimeFacts:
    return build_cell_entry_runtime_facts_from_mapping(
        {
            "cycle_index": cycle_index,
            "active_skill": active_skill,
            "cell_id": dig_cell_id_from_obs(view.obs),
            "bucket_pose": bucket_dig_area_pose_from_obs(view.obs),
            "geometry_available": (
                bucket_dig_area_cell_in_bounds_mask_from_obs(view.obs)
            ),
            "bucket_mass_kg": mass_in_bucket_from_obs(view.obs),
        }
    )


@dataclass(frozen=True)
class CellEntryRuntimeState:
    goal: CellEntryGoal | None = None
    goal_cycle_id: int = -1
    audit: PlannerDecisionAudit | None = None
    tokens: np.ndarray | None = None
    token_injected: bool = False
    seen_cell_id: int = -1
    trace_events: tuple[dict[str, int | float | str], ...] = ()


CELL_ENTRY_RUNTIME_STATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("goal", "_cell_entry_goal"),
    ("goal_cycle_id", "_cell_entry_goal_cycle_id"),
    ("audit", "_cell_entry_audit"),
    ("tokens", "_cell_entry_tokens"),
    ("seen_cell_id", "_cell_entry_seen_cell_id"),
)


def build_cell_entry_runtime_state_from_mapping(
    values: Mapping[str, Any],
) -> CellEntryRuntimeState:
    return CellEntryRuntimeState(
        goal=values["goal"],
        goal_cycle_id=int(values["goal_cycle_id"]),
        audit=values["audit"],
        tokens=values["tokens"],
        seen_cell_id=int(values["seen_cell_id"]),
    )


@dataclass(frozen=True)
class CellEntryDebugSnapshot:
    selected_cell_id: int
    selected_long_index: int
    selected_short_index: int
    planned_entry_x_m: float
    planned_entry_y_m: float
    planned_entry_z_m: float
    planner_ok: bool
    audit_reason_code: int
    audit_reason: str
    audit_risk_flags: int
    inside_entry_envelope: bool
    distance_to_entry_envelope_m: float
    seen_cell_id: int


@dataclass(frozen=True)
class CellEntryRuntimeTokenResult:
    tokens: np.ndarray | None
    state: CellEntryRuntimeState


@dataclass(frozen=True)
class CellEntryRuntimeCompletionResult:
    trace_event: dict[str, int | float | str] | None
    outcome: PrimitiveCycleOutcome | None
    state: CellEntryRuntimeState


class CellEntryRuntimeService:
    """Online cell-entry token, audit, and completion-trace assembly."""

    @staticmethod
    def facts_from_observation_view(
        *,
        view: PlannerObservationView,
        cycle_index: int,
        active_skill: str,
    ) -> CellEntryRuntimeFacts:
        return build_cell_entry_runtime_facts_from_observation_view(
            view=view,
            cycle_index=cycle_index,
            active_skill=active_skill,
        )

    @staticmethod
    def initial_runtime_state() -> CellEntryRuntimeState:
        from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM

        return CellEntryRuntimeState(
            goal=None,
            goal_cycle_id=-1,
            audit=None,
            tokens=np.zeros(CELL_ENTRY_TOKEN_DIM, dtype=np.float32),
            token_injected=False,
            seen_cell_id=-1,
            trace_events=(),
        )

    @staticmethod
    def debug_snapshot(*, state: CellEntryRuntimeState) -> CellEntryDebugSnapshot:
        goal = state.goal
        audit = state.audit
        return CellEntryDebugSnapshot(
            selected_cell_id=int(-1 if goal is None else goal.selected_cell_id),
            selected_long_index=int(-1 if goal is None else goal.selected_long_index),
            selected_short_index=int(
                -1 if goal is None else goal.selected_short_index
            ),
            planned_entry_x_m=float(
                float("nan") if goal is None else goal.planned_entry_x_m
            ),
            planned_entry_y_m=float(
                float("nan") if goal is None else goal.planned_entry_y_m
            ),
            planned_entry_z_m=float(
                float("nan") if goal is None else goal.planned_entry_z_m
            ),
            planner_ok=bool(False if audit is None else audit.planner_ok),
            audit_reason_code=int(-1 if audit is None else audit.reason_code),
            audit_reason=str("" if audit is None else audit.reason),
            audit_risk_flags=int(0 if audit is None else audit.risk_flags),
            inside_entry_envelope=bool(
                False if audit is None else audit.inside_entry_envelope
            ),
            distance_to_entry_envelope_m=float(
                float("nan") if audit is None else audit.distance_to_entry_envelope_m
            ),
            seen_cell_id=int(state.seen_cell_id),
        )

    @staticmethod
    def tokens_for_obs(
        *,
        planner: CellEntryPlanner,
        auditor: PlannerDecisionAuditor,
        facts: CellEntryRuntimeFacts,
        config: CellEntryRuntimeConfig,
        state: CellEntryRuntimeState,
    ) -> CellEntryRuntimeTokenResult:
        from testbed.planner.cell_entry import build_cell_entry_tokens

        if not config.enabled or facts.active_skill != "dig":
            return CellEntryRuntimeTokenResult(tokens=None, state=state)

        goal = state.goal
        goal_cycle_id = int(state.goal_cycle_id)
        seen_cell_id = int(state.seen_cell_id)
        if goal is None or goal_cycle_id != int(facts.cycle_index):
            goal = planner.plan(cycle_id=int(facts.cycle_index))
            goal_cycle_id = int(facts.cycle_index)
            seen_cell_id = -1

        cell_id = int(facts.cell_id)
        if cell_id >= 0 and seen_cell_id < 0:
            seen_cell_id = int(cell_id)
        outcome = _runtime_outcome(
            facts=facts,
            cell_id=cell_id,
            payload_gain_kg=float(auditor.low_productivity_payload_gain_kg),
        )
        audit = auditor.audit(
            goal=goal,
            outcome=outcome,
            current_bucket_pose=facts.bucket_pose,
            geometry_available=bool(facts.geometry_available),
        )
        tokens = build_cell_entry_tokens(
            grid=auditor.grid,
            goal=goal,
            audit=audit,
        )
        runtime_state = CellEntryRuntimeState(
            goal=goal,
            goal_cycle_id=goal_cycle_id,
            audit=audit,
            tokens=tokens.copy(),
            seen_cell_id=seen_cell_id,
        )
        return CellEntryRuntimeTokenResult(
            tokens=tokens.copy(),
            state=runtime_state,
        )

    @staticmethod
    def complete_dig(
        *,
        planner: CellEntryPlanner,
        facts: CellEntryRuntimeFacts,
        config: CellEntryRuntimeConfig,
        state: CellEntryRuntimeState,
    ) -> CellEntryRuntimeCompletionResult:
        goal = state.goal
        if not config.enabled or goal is None:
            return CellEntryRuntimeCompletionResult(
                trace_event=None,
                outcome=None,
                state=state,
            )

        cell_id = int(facts.cell_id)
        if cell_id < 0:
            cell_id = int(state.seen_cell_id)
        outcome = _runtime_outcome(
            facts=facts,
            cell_id=cell_id,
            payload_gain_kg=float(facts.bucket_mass_kg),
        )
        planner.update(outcome)
        trace_event = {
            "cycle_id": int(facts.cycle_index),
            "selected_cell_id": int(goal.selected_cell_id),
            "actual_cell_id": int(cell_id),
            "payload_gain_kg": float(outcome.payload_gain_kg),
            "audit_reason_code": int(
                -1 if state.audit is None else state.audit.reason_code
            ),
            "audit_reason": str("" if state.audit is None else state.audit.reason),
        }
        return CellEntryRuntimeCompletionResult(
            trace_event=trace_event,
            outcome=outcome,
            state=state,
        )


def _runtime_outcome(
    *,
    facts: CellEntryRuntimeFacts,
    cell_id: int,
    payload_gain_kg: float,
) -> PrimitiveCycleOutcome:
    from testbed.planner.cell_entry import PrimitiveCycleOutcome

    return PrimitiveCycleOutcome(
        cycle_id=int(facts.cycle_index),
        actual_start_step=-1,
        actual_bite_step=-1,
        actual_removal_step=-1,
        actual_start_cell_id=int(cell_id),
        actual_bite_cell_id=int(cell_id),
        actual_removal_cell_id=int(cell_id),
        payload_gain_kg=float(payload_gain_kg),
        deposit_delta_kg=0.0,
        collision_count_delta=0,
        return_miss=False,
    )
