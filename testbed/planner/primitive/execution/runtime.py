"""Execution ordering for one primitive planner tick."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from testbed.planner.primitive.decision.contracts import (
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    validate_decision_effect_contract,
)
from testbed.planner.primitive.execution.tick_finalization import (
    PrimitiveTickFinalizationService,
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
        preparation: PrimitiveTickPreparation,
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


class PrimitiveExecutionStateOwner(Protocol):
    """Execution state owner surface required by execution composition."""

    skill_name: str
    switch_reason: str

    def set_switch_reason(self, reason: str) -> None: ...

    def set_prev_action(self, action: Any) -> None: ...


class PrimitiveBoundaryEventRuntime(Protocol):
    """Boundary-event runtime contract used during tick preparation."""

    def update(self, obs: dict[str, Any]) -> Any | None: ...


class PrimitiveDigProgressRuntime(Protocol):
    """Dig-progress runtime contract used by dig ticks."""

    def update(self, obs: dict[str, Any]) -> None: ...


class PrimitiveDecisionRuntimeLike(Protocol):
    """Decision runtime contract used by the execution runtime."""

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult: ...


class PrimitiveRequestedEffectApplier(Protocol):
    """Requested-effect applier contract used after a decision."""

    def apply(
        self,
        obs: dict[str, Any],
        effects: tuple[RequestedPlannerEffect, ...],
    ) -> None: ...


class PrimitiveTickFinalizationRuntimeLike(Protocol):
    """Tick-finalization runtime contract used after effect application."""

    def account_return_timeout(self) -> bool: ...

    def finalize_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> None: ...


class PrimitiveActionDispatchRuntime(Protocol):
    """Action-dispatch service contract used by execution composition."""

    def dispatch_action(self, obs: dict[str, Any]) -> Any: ...

    def pre_policy_override(self, obs: dict[str, Any]) -> Any | None: ...


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
    pre_decision_action: Callable[[dict[str, Any]], Any | None] | None = None


@dataclass(frozen=True)
class PrimitiveTickCallbacks(PrimitiveExecutionPorts):
    """Compatibility callable bundle for older tick-template callers."""


@dataclass(frozen=True)
class PrimitiveExecutionRuntimePorts:
    """Focused services and owners needed to compose tick execution."""

    execution_state: PrimitiveExecutionStateOwner
    boundary_event_runtime: PrimitiveBoundaryEventRuntime
    dig_progress_runtime: PrimitiveDigProgressRuntime
    decision_runtime: PrimitiveDecisionRuntimeLike
    requested_effect_applier: PrimitiveRequestedEffectApplier
    tick_finalization_runtime: PrimitiveTickFinalizationRuntimeLike
    action_dispatch_service: PrimitiveActionDispatchRuntime
    tick_finalization_service: PrimitiveTickFinalizationService = field(
        default_factory=PrimitiveTickFinalizationService
    )
    dig_skill_name: str = "dig"


@dataclass(frozen=True)
class PrimitiveExecutionRuntime:
    """Compose the primitive execution driver from focused runtimes/services."""

    ports: PrimitiveExecutionRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveExecutionRuntimePorts,
    ) -> PrimitiveExecutionRuntime:
        return cls(ports=ports)

    def execution_driver(self) -> PrimitiveExecutionDriver:
        return PrimitiveExecutionDriver.from_ports(
            self.execution_ports(),
            dig_skill_name=self.ports.dig_skill_name,
        )

    def execution_ports(self) -> PrimitiveExecutionPorts:
        ports = self.ports
        return PrimitiveExecutionPorts(
            update_boundary_event=ports.boundary_event_runtime.update,
            reset_switch_reason=lambda: ports.execution_state.set_switch_reason(""),
            current_skill_name=lambda: str(ports.execution_state.skill_name),
            update_dig_progress=ports.dig_progress_runtime.update,
            decide_tick=self.decide_tick,
            apply_requested_effects=self.apply_requested_effects,
            account_return_timeout=ports.tick_finalization_runtime.account_return_timeout,
            dispatch_action=ports.action_dispatch_service.dispatch_action,
            record_previous_action=self.record_previous_action,
            transition_completed_after_dispatch=(
                self.transition_completed_after_dispatch
            ),
            finalize_debug_state=ports.tick_finalization_runtime.finalize_debug_state,
            pre_decision_action=getattr(
                ports.action_dispatch_service,
                "pre_policy_override",
                None,
            ),
        )

    def predict(self, obs: dict[str, Any]) -> Any:
        return self.execution_driver().predict(obs)

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.ports.decision_runtime.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )

    def apply_requested_effects(
        self,
        obs: dict[str, Any],
        effects: tuple[RequestedPlannerEffect, ...],
    ) -> None:
        self.ports.requested_effect_applier.apply(obs, effects)

    def record_previous_action(self, action: Any) -> None:
        copied_action = self.ports.tick_finalization_service.copy_previous_action(
            action
        )
        self.ports.execution_state.set_prev_action(copied_action)

    def transition_completed_after_dispatch(self) -> bool:
        return self.ports.tick_finalization_service.transition_completed_after_dispatch(
            str(self.ports.execution_state.switch_reason)
        )


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
    ) -> PrimitiveExecutionDriver:
        return cls(ports=ports, dig_skill_name=dig_skill_name)

    @classmethod
    def from_hooks(
        cls,
        *,
        hooks: PrimitiveTickHooks,
        dig_skill_name: str = "dig",
    ) -> PrimitiveExecutionDriver:
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
        if ports.pre_decision_action is not None:
            override = ports.pre_decision_action(obs)
            if override is not None:
                return self._finalize_pre_decision_override(
                    override,
                    boundary_event=boundary_event,
                )
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

    def _finalize_pre_decision_override(
        self,
        override: Any,
        *,
        boundary_event: Any | None,
    ) -> PrimitiveTickResult:
        ports = self.ports
        skill_name = ports.current_skill_name()
        action = override
        ports.record_previous_action(action)
        ports.finalize_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )
        preparation = PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision=skill_name,
            dig_progress_updated=False,
        )
        decision = PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=skill_name,
            skill_after=skill_name,
            switch_reason="",
            decision_source="pre_decision_safety_interlock",
        )
        return PrimitiveTickResult(
            action=action,
            preparation=preparation,
            decision=decision,
            boundary_event=boundary_event,
            transition_timeout=False,
            transition_completed=False,
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
