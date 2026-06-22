from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testbed.planner.primitive_decision import (
    CompleteReturnTransitionEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    SwitchToNextSkillAfterReturnEffect,
    SwitchSkillEffect,
)
from testbed.planner.primitive_execution import (
    PrimitiveTickHooks,
    run_primitive_tick,
)


@dataclass
class FakeTickHooks(PrimitiveTickHooks):
    active_skill_name: str
    action: list[float] = field(default_factory=lambda: [0.1, 0.2, 0.3, 0.4])
    return_timeout: bool = False
    transition_completed: bool = False
    previous_action_present: bool = True
    requested_decision: PrimitiveDecisionResult | None = None
    events: list[str] = field(default_factory=list)
    applied_effects: list[str] = field(default_factory=list)
    applied_obs_markers: list[str] = field(default_factory=list)

    def update_boundary_event(self, obs: dict[str, Any]) -> str | None:
        self.events.append("boundary_update")
        return "boundary-event" if self.previous_action_present else None

    def reset_switch_reason(self) -> None:
        self.events.append("switch_reason_reset")

    def current_skill_name(self) -> str:
        self.events.append("current_skill_before_progress")
        return self.active_skill_name

    def update_dig_progress(self, obs: dict[str, Any]) -> None:
        self.events.append("dig_progress_update")

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: Any,
    ) -> PrimitiveDecisionResult:
        self.events.append(
            f"decide:{boundary_event}:{preparation.skill_name_before_decision}"
        )
        if self.requested_decision is not None:
            return self.requested_decision
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=preparation.skill_name_before_decision,
            skill_after=preparation.skill_name_before_decision,
            switch_reason="",
        )

    def apply_requested_effects(
        self,
        obs: dict[str, Any],
        effects: tuple[RequestedPlannerEffect, ...],
    ) -> None:
        self.events.append(f"apply_effects:{len(effects)}")
        self.applied_obs_markers.append(str(obs.get("marker", "")))
        self.applied_effects.extend(effect.effect_type for effect in effects)

    def account_return_timeout(self) -> bool:
        self.events.append("return_timeout_accounting")
        return self.return_timeout

    def dispatch_action(self, obs: dict[str, Any]) -> list[float]:
        self.events.append("dispatch_action")
        return self.action

    def record_previous_action(self, action: Any) -> None:
        self.events.append(f"prev_action_update:{action}")

    def transition_completed_after_dispatch(self) -> bool:
        self.events.append("transition_completed_check")
        return self.transition_completed

    def finalize_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> None:
        self.events.append(
            f"debug_finalize:timeout={transition_timeout}:completed={transition_completed}"
        )


def test_run_primitive_tick_orders_dig_tick_hooks_and_returns_result() -> None:
    hooks = FakeTickHooks(
        active_skill_name="dig",
        return_timeout=True,
        transition_completed=True,
    )

    result = run_primitive_tick(hooks=hooks, obs={"qpos": [1.0]})

    assert result.action == [0.1, 0.2, 0.3, 0.4]
    assert result.boundary_event == "boundary-event"
    assert result.preparation.boundary_event == "boundary-event"
    assert result.preparation.skill_name_before_decision == "dig"
    assert result.preparation.dig_progress_updated is True
    assert result.decision.status == "no_change"
    assert result.decision.skill_before == "dig"
    assert result.decision.skill_after == "dig"
    assert result.transition_timeout is True
    assert result.transition_completed is True
    assert hooks.events == [
        "boundary_update",
        "switch_reason_reset",
        "current_skill_before_progress",
        "dig_progress_update",
        "decide:boundary-event:dig",
        "return_timeout_accounting",
        "dispatch_action",
        "prev_action_update:[0.1, 0.2, 0.3, 0.4]",
        "transition_completed_check",
        "debug_finalize:timeout=True:completed=True",
    ]


def test_run_primitive_tick_skips_dig_progress_for_non_dig_skill() -> None:
    hooks = FakeTickHooks(active_skill_name="return")

    result = run_primitive_tick(hooks=hooks, obs={})

    assert result.transition_timeout is False
    assert "dig_progress_update" not in hooks.events
    assert hooks.events == [
        "boundary_update",
        "switch_reason_reset",
        "current_skill_before_progress",
        "decide:boundary-event:return",
        "return_timeout_accounting",
        "dispatch_action",
        "prev_action_update:[0.1, 0.2, 0.3, 0.4]",
        "transition_completed_check",
        "debug_finalize:timeout=False:completed=False",
    ]


def test_run_primitive_tick_applies_requested_effects_before_timeout_and_dispatch() -> None:
    requested_effects = (
        RequestedPlannerEffect(effect_type="record_decision_trace", reason="first"),
        RequestedPlannerEffect(effect_type="record_decision_note", reason="second"),
    )
    hooks = FakeTickHooks(
        active_skill_name="dig",
        requested_decision=PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
            effects=requested_effects,
        ),
    )

    result = run_primitive_tick(hooks=hooks, obs={"marker": "current_obs"})

    assert result.decision.effects == requested_effects
    assert hooks.applied_obs_markers == ["current_obs"]
    assert hooks.applied_effects == [
        "record_decision_trace",
        "record_decision_note",
    ]
    assert hooks.events == [
        "boundary_update",
        "switch_reason_reset",
        "current_skill_before_progress",
        "dig_progress_update",
        "decide:boundary-event:dig",
        "apply_effects:2",
        "return_timeout_accounting",
        "dispatch_action",
        "prev_action_update:[0.1, 0.2, 0.3, 0.4]",
        "transition_completed_check",
        "debug_finalize:timeout=False:completed=False",
    ]


def test_run_primitive_tick_applies_bootstrap_switch_before_dispatch() -> None:
    requested_effects = (
        SwitchSkillEffect(
            target_skill_name="dig",
            switch_reason="bootstrap_to_dig",
        ),
    )
    hooks = FakeTickHooks(
        active_skill_name="bootstrap",
        requested_decision=PrimitiveDecisionResult.from_requested_effects(
            decision_source="legacy_fsm_bootstrap_requested_effect",
            status="skill_switch",
            skill_before="bootstrap",
            skill_after="dig",
            switch_reason="bootstrap_to_dig",
            effects=requested_effects,
        ),
    )

    result = run_primitive_tick(hooks=hooks, obs={})

    assert result.decision.effects == requested_effects
    assert hooks.applied_effects == ["switch_skill"]
    assert hooks.events == [
        "boundary_update",
        "switch_reason_reset",
        "current_skill_before_progress",
        "decide:boundary-event:bootstrap",
        "apply_effects:1",
        "return_timeout_accounting",
        "dispatch_action",
        "prev_action_update:[0.1, 0.2, 0.3, 0.4]",
        "transition_completed_check",
        "debug_finalize:timeout=False:completed=False",
    ]


def test_run_primitive_tick_applies_return_effects_before_dispatch() -> None:
    requested_effects = (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )
    hooks = FakeTickHooks(
        active_skill_name="return",
        requested_decision=PrimitiveDecisionResult.from_requested_effects(
            decision_source="legacy_fsm_return_requested_effect",
            status="skill_switch",
            skill_before="return",
            skill_after="return",
            switch_reason="",
            effects=requested_effects,
        ),
    )

    result = run_primitive_tick(hooks=hooks, obs={})

    assert result.decision.effects == requested_effects
    assert hooks.applied_effects == [
        "mark_return_next_dig_event_seen",
        "complete_return_transition",
        "switch_to_next_skill_after_return",
    ]
    assert hooks.events == [
        "boundary_update",
        "switch_reason_reset",
        "current_skill_before_progress",
        "decide:boundary-event:return",
        "apply_effects:3",
        "return_timeout_accounting",
        "dispatch_action",
        "prev_action_update:[0.1, 0.2, 0.3, 0.4]",
        "transition_completed_check",
        "debug_finalize:timeout=False:completed=False",
    ]


def test_run_primitive_tick_does_not_apply_legacy_already_applied_effects() -> None:
    hooks = FakeTickHooks(active_skill_name="dig")

    result = run_primitive_tick(hooks=hooks, obs={})

    assert result.decision.side_effects_applied is True
    assert hooks.applied_effects == []
    assert "apply_effects:0" not in hooks.events
