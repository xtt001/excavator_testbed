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
        obs: dict[str, Any],
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
class PrimitiveExecutionPorts:
    """Typed shell ports used by the primitive execution driver."""

    update_boundary_event: Callable[[dict[str, Any]], Any | None]
    reset_switch_reason: Callable[[], None]
    current_skill_name: Callable[[], str]
    update_dig_progress: Callable[[dict[str, Any]], None]
    decide_tick: Callable[..., PrimitiveDecisionResult]
    apply_requested_effects: Callable[
        [dict[str, Any], tuple[RequestedPlannerEffect, ...]],
        None,
    ]
    account_return_timeout: Callable[[], bool]
    dispatch_action: Callable[[dict[str, Any]], Any]
    record_previous_action: Callable[[Any], None]
    transition_completed_after_dispatch: Callable[[], bool]
    finalize_debug_state: Callable[..., None]


@dataclass(frozen=True)
class PrimitiveTickCallbacks(PrimitiveExecutionPorts):
    """Compatibility callable bundle for older tick-template callers."""


@dataclass(frozen=True)
class PrimitiveExecutionDriver:
    """Own the public primitive tick execution ordering."""

    ports: PrimitiveExecutionPorts
    dig_skill_name: str = "dig"

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveExecutionPorts,
        *,
        dig_skill_name: str = "dig",
    ) -> "PrimitiveExecutionDriver":
        return cls(ports=ports, dig_skill_name=dig_skill_name)

    @classmethod
    def from_hooks(
        cls,
        *,
        hooks: PrimitiveTickHooks,
        dig_skill_name: str = "dig",
    ) -> "PrimitiveExecutionDriver":
        return cls.from_ports(
            PrimitiveExecutionPorts(
                update_boundary_event=hooks.update_boundary_event,
                reset_switch_reason=hooks.reset_switch_reason,
                current_skill_name=hooks.current_skill_name,
                update_dig_progress=hooks.update_dig_progress,
                decide_tick=hooks.decide_tick,
                apply_requested_effects=hooks.apply_requested_effects,
                account_return_timeout=hooks.account_return_timeout,
                dispatch_action=hooks.dispatch_action,
                record_previous_action=hooks.record_previous_action,
                transition_completed_after_dispatch=(
                    hooks.transition_completed_after_dispatch
                ),
                finalize_debug_state=hooks.finalize_debug_state,
            ),
            dig_skill_name=dig_skill_name,
        )

    def predict(self, obs: dict[str, Any]) -> Any:
        return self.run_tick(obs).action

    def run_tick(self, obs: dict[str, Any]) -> PrimitiveTickResult:
        ports = self.ports
        boundary_event = ports.update_boundary_event(obs)
        ports.reset_switch_reason()
        skill_name_before_decision = ports.current_skill_name()
        dig_progress_updated = skill_name_before_decision == self.dig_skill_name
        if dig_progress_updated:
            ports.update_dig_progress(obs)
        preparation = PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision=skill_name_before_decision,
            dig_progress_updated=dig_progress_updated,
        )
        decision = ports.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )
        self._apply_requested_effects_if_needed(obs=obs, decision=decision)

        transition_timeout = ports.account_return_timeout()
        action = ports.dispatch_action(obs)
        ports.record_previous_action(action)

        transition_completed = ports.transition_completed_after_dispatch()
        ports.finalize_debug_state(
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
        self,
        *,
        obs: dict[str, Any],
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
        self.ports.apply_requested_effects(obs, requested_effects)


def run_primitive_tick(
    *,
    hooks: PrimitiveTickHooks,
    obs: dict[str, Any],
    dig_skill_name: str = "dig",
) -> PrimitiveTickResult:
    """Compatibility facade for the primitive execution driver."""

    return PrimitiveExecutionDriver.from_hooks(
        hooks=hooks,
        dig_skill_name=dig_skill_name,
    ).run_tick(obs)


def _apply_requested_effects_if_needed(
    *,
    hooks: PrimitiveTickHooks,
    obs: dict[str, Any],
    decision: PrimitiveDecisionResult,
) -> None:
    """Compatibility helper retained for older direct tests/imports."""

    validate_decision_effect_contract(decision)
    if decision.side_effects_applied:
        return
    requested_effects = tuple(
        effect
        for effect in decision.effects
        if isinstance(effect, RequestedPlannerEffect)
    )
    hooks.apply_requested_effects(obs, requested_effects)
