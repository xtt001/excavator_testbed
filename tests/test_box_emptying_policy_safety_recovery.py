from __future__ import annotations

from types import MethodType

import numpy as np

from testbed.planner.box_emptying.safety_interlock import SafetyActionDecision
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _planner(events: list[str]) -> PrimitivePlannerACTPolicy:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "dig"
    coverage_state = CoverageRuntimeState()

    class _TokenRuntime:
        def invalidate_return_plan(self) -> None:
            events.append("invalidate_return_plan")

        def invalidate_pending_dig_cut_plan(self) -> None:
            events.append("invalidate_pending_dig_cut_plan")

        def clear_dig_cut_plan(self) -> None:
            events.append("clear_dig_cut_plan")

    class _ObservationRuntime:
        def primitive_token_runtime(self) -> _TokenRuntime:
            return _TokenRuntime()

    class _Interlock:
        def mark_policy_restarted(self, event_id: int) -> None:
            events.append(f"mark_policy_restarted:{event_id}")

    planner._coverage_runtime_state = MethodType(
        lambda self: coverage_state,
        planner,
    )
    planner._primitive_token_observation_runtime = MethodType(
        lambda self: _ObservationRuntime(),
        planner,
    )
    planner._box_safety_interlock = MethodType(
        lambda self: _Interlock(),
        planner,
    )
    planner._restart_skill = MethodType(
        lambda self, reason: events.append(f"restart:{reason}"),
        planner,
    )
    planner._set_skill = MethodType(
        lambda self, skill, reason: events.append(
            f"switch:{skill}:{reason}"
        ),
        planner,
    )
    return planner


def test_hard_bottom_first_ack_invalidates_return_plan_then_restarts_current_act() -> None:
    events: list[str] = []
    planner = _planner(events)
    decision = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason="hard_bottom_contact_neutral_acknowledged",
        neutral_acknowledged=True,
        replan=True,
        hard_bottom_recovery_active=True,
        event_id=7,
    )

    planner._apply_box_safety_decision(decision)

    assert events == [
        "invalidate_return_plan",
        "clear_dig_cut_plan",
        "restart:hard_bottom_contact_neutral_acknowledged",
        "mark_policy_restarted:7",
    ]


def test_exhausted_cell_guard_ack_invalidates_plan_and_restarts_current_act() -> None:
    events: list[str] = []
    planner = _planner(events)
    decision = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason="depth_exhausted_cell_guard_neutral_acknowledged",
        neutral_acknowledged=True,
        replan=True,
        hard_bottom_recovery_active=True,
        depth_exhausted_guard=True,
        depth_exhausted_guard_active=True,
        event_id=8,
    )

    planner._apply_box_safety_decision(decision)

    assert events == [
        "invalidate_return_plan",
        "clear_dig_cut_plan",
        "restart:depth_exhausted_cell_guard_neutral_acknowledged",
        "mark_policy_restarted:8",
    ]


def test_clearance_ack_uses_fresh_switch_after_return_plan_invalidation() -> None:
    events: list[str] = []
    planner = _planner(events)
    decision = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason="hard_bottom_clearance_neutral_acknowledged",
        neutral_acknowledged=True,
        replan=True,
        next_skill="carry",
        event_id=7,
        hard_bottom_clearance_completed=True,
        hard_bottom_clearance_neutral_acknowledged=True,
    )

    planner._apply_box_safety_decision(decision)

    assert events == [
        "invalidate_return_plan",
        "clear_dig_cut_plan",
        "switch:carry:hard_bottom_clearance_neutral_acknowledged",
    ]


def test_clearance_ack_restarts_when_recovery_target_is_same_skill() -> None:
    events: list[str] = []
    planner = _planner(events)
    decision = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason="hard_bottom_clearance_neutral_acknowledged",
        neutral_acknowledged=True,
        replan=True,
        next_skill="dig",
        event_id=9,
    )

    planner._apply_box_safety_decision(decision)

    assert events[-1] == "restart:hard_bottom_clearance_neutral_acknowledged"


def test_transition_timeout_always_enters_safety_neutral_handshake() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 4
    planner._skill_name = "return"
    requested: list[dict[str, object]] = []

    class _Gate:
        def timeout_requested(self) -> bool:
            return False

    class _FunctionalGate:
        def terminal_neutral_requested(self) -> bool:
            return False

    class _Interlock:
        def request_neutral_event(self, **kwargs) -> None:
            requested.append(kwargs)

        def filter_action(self, obs, proposed_action, **kwargs):
            del obs, kwargs
            return SafetyActionDecision(
                action=np.zeros_like(proposed_action),
                reason="timeout",
                awaiting_neutral_ack=True,
            )

    class _Cycle:
        cycle_index = 1
        transition_timeout_count = 1

    coverage_state = CoverageRuntimeState()
    planner.__dict__["_carry_start_envelope_gate_state"] = _Gate()
    planner.__dict__["_functional_cycle_gate_state"] = _FunctionalGate()
    planner._box_safety_interlock = MethodType(
        lambda self: _Interlock(),
        planner,
    )
    planner._box_emptying_runtime_monitor = MethodType(
        lambda self: None,
        planner,
    )
    planner._primitive_cycle_runtime_state = MethodType(
        lambda self: _Cycle(),
        planner,
    )
    planner._coverage_runtime_state = MethodType(
        lambda self: coverage_state,
        planner,
    )
    planner._box_safety_active_cell_id = MethodType(
        lambda self, obs, active_corridor_id: 0,
        planner,
    )
    planner._apply_box_safety_decision = MethodType(
        lambda self, decision: None,
        planner,
    )

    action = planner._box_safety_filter_action(
        {"step_id": 50, "env_state": np.zeros(107, dtype=np.float32)},
        np.ones(4, dtype=np.float32),
    )

    assert action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert requested == [
        {
            "step_id": 50,
            "reason": "timeout",
            "terminal": True,
        }
    ]
