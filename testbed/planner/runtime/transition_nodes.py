"""Backend-neutral transition node result builders."""

from __future__ import annotations

from testbed.planner.runtime.contracts import (
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)
from testbed.planner.runtime.effects import (
    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
)
from testbed.planner.runtime.ports import (
    PlannerDigTransitionPorts,
    PlannerDumpLifecyclePorts,
    PlannerReturnTransitionPorts,
)


def build_dig_transition_result(
    context: PlannerTickContext,
    *,
    active_skill: str,
    node_root: str,
    ports: PlannerDigTransitionPorts,
) -> PlannerTickResult:
    """Build a dig transition tick result without applying side effects."""

    obs = dict(context.obs)
    exit_guard_ready = ports.exit_guard_ready(obs)
    request = ports.lifecycle_gate.dig_transition_runtime_request(
        exit_guard_ready=exit_guard_ready,
    )
    bad_replan_ready = False
    complete_boundary_low_payload = False
    dig_to_carry_ready = False
    dig_to_carry_reason = ""
    if request.should_check_bad_replan:
        bad_replan_ready = ports.bad_replan_ready(obs)
    if request.should_check_complete_boundary_low_payload(bad_replan_ready):
        complete_boundary_low_payload = ports.complete_boundary_low_payload(
            obs,
            context.boundary_event,
        )
    if request.should_check_dig_to_carry(
        bad_replan_ready=bad_replan_ready,
        complete_boundary_low_payload=complete_boundary_low_payload,
    ):
        dig_to_carry_decision = ports.dig_to_carry_decision(
            obs=obs,
            boundary_event=context.boundary_event,
        )
        dig_to_carry_ready = bool(dig_to_carry_decision.ready)
        if dig_to_carry_ready:
            dig_to_carry_reason = str(dig_to_carry_decision.reason)
    outcome = ports.lifecycle_gate.dig_transition_runtime(
        request.facts_with_gate_results(
            bad_replan_ready=bad_replan_ready,
            dig_to_carry_reason=dig_to_carry_reason,
            complete_boundary_low_payload=complete_boundary_low_payload,
            dig_to_carry_ready=dig_to_carry_ready,
        )
    )
    projection = ports.lifecycle_gate.dig_transition_runtime_projection(outcome)
    return PlannerTickResult(
        node_path=(node_root, "transition", active_skill),
        status="running",
        reason=str(getattr(outcome, "switch_reason", "")),
        effects=(
            PlannerRuntimeEffect(
                APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
                {"projection": projection, "obs": obs},
            ),
        ),
        diagnostics={
            "active_skill": active_skill,
            "action": str(getattr(outcome, "action", "")),
            "switch_reason": str(getattr(outcome, "switch_reason", "")),
        },
    )


def build_return_transition_result(
    context: PlannerTickContext,
    *,
    active_skill: str,
    node_root: str,
    ports: PlannerReturnTransitionPorts,
) -> PlannerTickResult:
    """Build a return transition tick result without applying side effects."""

    obs = dict(context.obs)
    runtime = ports.return_transition_runtime(
        obs=obs,
        boundary_event=context.boundary_event,
        previous_next_dig_event_seen=(
            context.blackboard.return_next_dig_event_seen
        ),
    )
    outcome = runtime.outcome
    projection = runtime.projection
    return PlannerTickResult(
        node_path=(node_root, "transition", active_skill),
        status="running",
        reason=str(getattr(outcome, "reason_suffix", "")),
        effects=(
            PlannerRuntimeEffect(
                APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
                {"outcome": outcome, "projection": projection},
            ),
        ),
        diagnostics={
            "active_skill": active_skill,
            "action": str(getattr(outcome, "action", "")),
            "reason_suffix": str(getattr(outcome, "reason_suffix", "")),
            "next_dig_event_seen": bool(
                getattr(outcome, "next_dig_event_seen", False)
            ),
        },
    )


def build_carry_transition_result(
    context: PlannerTickContext,
    *,
    active_skill: str,
    node_root: str,
    ports: PlannerDumpLifecyclePorts,
) -> PlannerTickResult:
    """Build a carry transition tick result without applying side effects."""

    obs = dict(context.obs)
    runtime = ports.carry_transition_runtime(
        obs=obs,
        boundary_event=context.boundary_event,
        current_dump_ready_hold_count=context.blackboard.dump_ready_hold_count,
    )
    outcome = runtime.outcome
    return PlannerTickResult(
        node_path=(node_root, "transition", active_skill),
        status="running",
        reason=str(getattr(outcome, "switch_reason", "")),
        effects=(
            PlannerRuntimeEffect(
                APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
                {"runtime": runtime, "obs": obs},
            ),
        ),
        diagnostics={
            "active_skill": active_skill,
            "action": str(getattr(outcome, "action", "")),
            "switch_reason": str(getattr(outcome, "switch_reason", "")),
        },
    )


def build_dump_transition_result(
    context: PlannerTickContext,
    *,
    active_skill: str,
    node_root: str,
    ports: PlannerDumpLifecyclePorts,
) -> PlannerTickResult:
    """Build a dump transition tick result without applying side effects."""

    obs = dict(context.obs)
    runtime = ports.dump_transition_runtime(
        obs=obs,
        boundary_event=context.boundary_event,
        current_dump_done_hold_count=context.blackboard.dump_done_hold_count,
    )
    outcome = runtime.outcome
    return PlannerTickResult(
        node_path=(node_root, "transition", active_skill),
        status="running",
        reason=str(getattr(outcome, "switch_reason", "")),
        effects=(
            PlannerRuntimeEffect(
                APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
                {"runtime": runtime, "obs": obs},
            ),
        ),
        diagnostics={
            "active_skill": active_skill,
            "action": str(getattr(outcome, "action", "")),
            "switch_reason": str(getattr(outcome, "switch_reason", "")),
        },
    )


__all__ = [
    "build_carry_transition_result",
    "build_dig_transition_result",
    "build_dump_transition_result",
    "build_return_transition_result",
]
