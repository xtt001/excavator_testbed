"""Execution ordering for one primitive planner tick."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from testbed.planner.primitive_decision import (
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    validate_decision_effect_contract,
)


class PrimitiveTickHooks(Protocol):
    """Narrow callbacks needed to execute one public planner tick."""

    def update_boundary_event(self, obs: dict[str, Any]) -> Any | None: ...

    def reset_switch_reason(self) -> None: ...

    def current_skill_name(self) -> str: ...

    def update_dig_progress(self, obs: dict[str, Any]) -> None: ...

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: "PrimitiveTickPreparation",
    ) -> PrimitiveDecisionResult: ...

    def apply_requested_effects(
        self,
        effects: tuple[RequestedPlannerEffect, ...],
    ) -> None: ...

    def account_return_timeout(self) -> bool: ...

    def dispatch_action(self, obs: dict[str, Any]) -> Any: ...

    def record_previous_action(self, action: Any) -> None: ...

    def transition_completed_after_dispatch(self) -> bool: ...

    def finalize_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> None: ...


@dataclass(frozen=True)
class PrimitiveTickPreparation:
    boundary_event: Any | None
    skill_name_before_decision: str
    dig_progress_updated: bool


@dataclass(frozen=True)
class PrimitiveTickResult:
    action: Any
    preparation: PrimitiveTickPreparation
    decision: PrimitiveDecisionResult
    boundary_event: Any | None
    transition_timeout: bool
    transition_completed: bool


@dataclass(frozen=True)
class PrimitiveTickCallbacks:
    update_boundary_event: Callable[[dict[str, Any]], Any | None]
    reset_switch_reason: Callable[[], None]
    current_skill_name: Callable[[], str]
    update_dig_progress: Callable[[dict[str, Any]], None]
    decide_tick: Callable[..., PrimitiveDecisionResult]
    apply_requested_effects: Callable[[tuple[RequestedPlannerEffect, ...]], None]
    account_return_timeout: Callable[[], bool]
    dispatch_action: Callable[[dict[str, Any]], Any]
    record_previous_action: Callable[[Any], None]
    transition_completed_after_dispatch: Callable[[], bool]
    finalize_debug_state: Callable[..., None]


def run_primitive_tick(
    *,
    hooks: PrimitiveTickHooks,
    obs: dict[str, Any],
    dig_skill_name: str = "dig",
) -> PrimitiveTickResult:
    """Run one planner tick while keeping behavior inside the supplied hooks."""

    boundary_event = hooks.update_boundary_event(obs)
    hooks.reset_switch_reason()
    skill_name_before_decision = hooks.current_skill_name()
    dig_progress_updated = skill_name_before_decision == dig_skill_name
    if dig_progress_updated:
        hooks.update_dig_progress(obs)
    preparation = PrimitiveTickPreparation(
        boundary_event=boundary_event,
        skill_name_before_decision=skill_name_before_decision,
        dig_progress_updated=dig_progress_updated,
    )
    decision = hooks.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=preparation,
    )
    _apply_requested_effects_if_needed(hooks=hooks, decision=decision)

    transition_timeout = hooks.account_return_timeout()
    action = hooks.dispatch_action(obs)
    hooks.record_previous_action(action)

    transition_completed = hooks.transition_completed_after_dispatch()
    hooks.finalize_debug_state(
        transition_timeout=transition_timeout,
        transition_completed=transition_completed,
    )
    return PrimitiveTickResult(
        action=action,
        preparation=preparation,
        decision=decision,
        boundary_event=boundary_event,
        transition_timeout=transition_timeout,
        transition_completed=transition_completed,
    )


def _apply_requested_effects_if_needed(
    *,
    hooks: PrimitiveTickHooks,
    decision: PrimitiveDecisionResult,
) -> None:
    validate_decision_effect_contract(decision)
    if decision.side_effects_applied:
        return
    requested_effects = tuple(
        effect
        for effect in decision.effects
        if isinstance(effect, RequestedPlannerEffect)
    )
    hooks.apply_requested_effects(requested_effects)
