from __future__ import annotations

from dataclasses import dataclass, field
from types import MethodType
from typing import Any

import testbed.planner.primitive.execution.runtime as primitive_execution
from testbed.planner.primitive.decision.contracts import (
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
)
from testbed.planner.primitive.execution.runtime import (
    PrimitiveExecutionDriver,
    PrimitiveExecutionPorts,
    PrimitiveTickResult,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


@dataclass
class _ExecutionRecorder:
    active_skill_name: str
    action: list[float] = field(default_factory=lambda: [0.1, 0.2, 0.3, 0.4])
    return_timeout: bool = False
    transition_completed: bool = False
    requested_decision: PrimitiveDecisionResult | None = None
    events: list[str] = field(default_factory=list)
    applied_effects: list[str] = field(default_factory=list)
    applied_obs_markers: list[str] = field(default_factory=list)

    def ports(self) -> PrimitiveExecutionPorts:
        return PrimitiveExecutionPorts(
            update_boundary_event=self.update_boundary_event,
            reset_switch_reason=self.reset_switch_reason,
            current_skill_name=self.current_skill_name,
            update_dig_progress=self.update_dig_progress,
            decide_tick=self.decide_tick,
            apply_requested_effects=self.apply_requested_effects,
            account_return_timeout=self.account_return_timeout,
            dispatch_action=self.dispatch_action,
            record_previous_action=self.record_previous_action,
            transition_completed_after_dispatch=(
                self.transition_completed_after_dispatch
            ),
            finalize_debug_state=self.finalize_debug_state,
        )

    def update_boundary_event(self, obs: dict[str, Any]) -> str:
        self.events.append("boundary_update")
        return "boundary-event"

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


def test_driver_owns_full_dig_tick_ordering_and_returns_result() -> None:
    recorder = _ExecutionRecorder(
        active_skill_name="dig",
        return_timeout=True,
        transition_completed=True,
    )

    result = PrimitiveExecutionDriver.from_ports(recorder.ports()).run_tick(
        {"qpos": [1.0]}
    )

    assert result.action == [0.1, 0.2, 0.3, 0.4]
    assert result.preparation.skill_name_before_decision == "dig"
    assert result.preparation.dig_progress_updated is True
    assert result.decision.side_effects_applied is True
    assert result.transition_timeout is True
    assert result.transition_completed is True
    assert recorder.events == [
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


def test_driver_skips_dig_progress_for_non_dig_tick() -> None:
    recorder = _ExecutionRecorder(active_skill_name="return")

    result = PrimitiveExecutionDriver.from_ports(recorder.ports()).run_tick({})

    assert result.preparation.skill_name_before_decision == "return"
    assert result.preparation.dig_progress_updated is False
    assert "dig_progress_update" not in recorder.events
    assert recorder.events == [
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


def test_driver_applies_requested_effects_after_decision_before_timeout() -> None:
    effects = (
        RequestedPlannerEffect(effect_type="record_decision_trace", reason="first"),
        RequestedPlannerEffect(effect_type="record_decision_note", reason="second"),
    )
    recorder = _ExecutionRecorder(
        active_skill_name="dig",
        requested_decision=PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
            effects=effects,
        ),
    )

    result = PrimitiveExecutionDriver.from_ports(recorder.ports()).run_tick(
        {"marker": "current_obs"}
    )

    assert result.decision.effects == effects
    assert recorder.applied_obs_markers == ["current_obs"]
    assert recorder.applied_effects == [
        "record_decision_trace",
        "record_decision_note",
    ]
    assert recorder.events == [
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


def test_driver_predict_returns_action_from_run_tick() -> None:
    recorder = _ExecutionRecorder(active_skill_name="dig")

    action = PrimitiveExecutionDriver.from_ports(recorder.ports()).predict({})

    assert action == [0.1, 0.2, 0.3, 0.4]
    assert recorder.events[-1] == "debug_finalize:timeout=False:completed=False"


def test_run_primitive_tick_is_compatibility_facade_for_driver(monkeypatch: Any) -> None:
    obs = {"qpos": [1.0]}
    hooks = object()
    result = PrimitiveTickResult(
        action=[1.0],
        preparation=object(),
        decision=object(),
        boundary_event="boundary",
        transition_timeout=False,
        transition_completed=True,
    )
    events: list[str] = []

    class _FakeDriver:
        @classmethod
        def from_hooks(cls, *, hooks: Any, dig_skill_name: str) -> _FakeDriver:
            assert hooks is hooks_obj
            assert dig_skill_name == "custom_dig"
            events.append("from_hooks")
            return cls()

        def run_tick(self, got_obs: dict[str, Any]) -> PrimitiveTickResult:
            assert got_obs is obs
            events.append("run_tick")
            return result

    hooks_obj = hooks
    monkeypatch.setattr(primitive_execution, "PrimitiveExecutionDriver", _FakeDriver)

    returned = primitive_execution.run_primitive_tick(
        hooks=hooks_obj,
        obs=obs,
        dig_skill_name="custom_dig",
    )

    assert returned is result
    assert events == ["from_hooks", "run_tick"]


def test_policy_predict_delegates_to_execution_driver() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"qpos": [1.0]}
    action = [4.0, 3.0, 2.0, 1.0]
    events: list[str] = []

    class _FakeDriver:
        def predict(self, got_obs: dict[str, Any]) -> list[float]:
            assert got_obs is obs
            events.append("driver_predict")
            return action

    class _FakeExecutionRuntime:
        def execution_driver(self) -> _FakeDriver:
            return _FakeDriver()

    planner._primitive_execution_runtime = MethodType(
        lambda self: _FakeExecutionRuntime(),
        planner,
    )

    assert planner.predict(obs) is action
    assert events == ["driver_predict"]
