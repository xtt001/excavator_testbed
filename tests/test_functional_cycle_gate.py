from __future__ import annotations

import numpy as np

from testbed.planner.box_emptying.safety_interlock import SafetyActionDecision
from testbed.planner.primitive.effects.functional_cycle_gate import (
    FunctionalCycleGate,
    FunctionalCycleGateConfig,
)
from testbed.planner.primitive.facts.capabilities import ReturnTransitionStatus


def _status(
    *,
    handoff_ready: bool = True,
    payload_kg: float = 0.0,
    completed: bool = True,
) -> ReturnTransitionStatus:
    return ReturnTransitionStatus(
        mass_in_bucket_kg=payload_kg,
        min_distance_to_dig_area_m=0.0,
        bucket_depth_below_dig_area_plane_m=0.05,
        semantic_boundary_profile_active=True,
        next_dig_event=True,
        next_or_seen_dig_event=True,
        entry_close=handoff_ready,
        start_envelope_ready=handoff_ready,
        handoff_ready=handoff_ready,
        direct_handoff_ready=False,
        shallow_guard_ready=False,
        shallow_guard_allowed=False,
        completed_transition=completed,
        next_skill="dig" if completed else "",
        switch_reason="return_to_dig_next_dig_entry_ready" if completed else "",
    )


def test_only_final_tenth_return_safe_envelope_requests_terminal_neutral() -> None:
    gate = FunctionalCycleGate(
        FunctionalCycleGateConfig(
            enabled=True,
            target_cycles=10,
            max_bucket_mass_kg=15.0,
        )
    )

    earlier = gate.apply(_status(), cycle_index=8)
    not_ready = gate.apply(_status(handoff_ready=False), cycle_index=9)
    payload_high = gate.apply(
        _status(payload_kg=15.1),
        cycle_index=9,
    )
    final = gate.apply(_status(payload_kg=15.0), cycle_index=9)

    assert earlier.completed_transition is True
    assert not_ready.completed_transition is False
    assert payload_high.completed_transition is False
    assert final.completed_transition is False
    assert final.next_skill == ""
    assert final.switch_reason == ""
    assert gate.terminal_neutral_requested() is True
    assert gate.debug_fields()["functional_terminal_return_ready"] is True


def test_terminal_neutral_handshake_is_projected_to_rollout_fields() -> None:
    gate = FunctionalCycleGate(
        FunctionalCycleGateConfig(enabled=True, target_cycles=10)
    )
    gate.apply(_status(), cycle_index=9)

    gate.observe_safety_decision(
        SafetyActionDecision(
            action=np.zeros(4, dtype=np.float32),
            reason="functional_10cycle_terminal_return_ready",
            awaiting_neutral_ack=True,
        )
    )
    awaiting = gate.debug_fields()
    assert awaiting["functional_terminal_return_ready"] is True
    assert awaiting["functional_terminal_awaiting_neutral_ack"] is True
    assert awaiting["functional_terminal_neutral_acknowledged"] is False

    gate.observe_safety_decision(
        SafetyActionDecision(
            action=np.zeros(4, dtype=np.float32),
            reason="functional_10cycle_terminal_return_ready",
            terminal=True,
            neutral_acknowledged=True,
        )
    )
    acknowledged = gate.debug_fields()
    assert acknowledged["functional_terminal_awaiting_neutral_ack"] is False
    assert acknowledged["functional_terminal_neutral_acknowledged"] is True


def test_reset_clears_terminal_request_and_history() -> None:
    gate = FunctionalCycleGate(
        FunctionalCycleGateConfig(enabled=True, target_cycles=10)
    )
    gate.apply(_status(), cycle_index=9)

    gate.reset()

    assert gate.terminal_neutral_requested() is False
    assert gate.debug_fields()["functional_terminal_return_ready"] is False


def test_disabled_gate_preserves_formal_freeze_return_semantics() -> None:
    gate = FunctionalCycleGate(FunctionalCycleGateConfig(enabled=False))
    status = _status()

    assert gate.apply(status, cycle_index=9) is status
    assert gate.terminal_neutral_requested() is False
