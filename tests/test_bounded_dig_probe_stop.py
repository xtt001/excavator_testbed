from __future__ import annotations

from types import MethodType

import numpy as np
import pytest

from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
    SafetyActionDecision,
    SafetyInterlockConfig,
)
from testbed.planner.primitive.effects.bounded_dig_probe_stop import (
    BOUNDED_DIG_PROBE_ENVELOPE_REASON,
    BOUNDED_DIG_PROBE_STEP_LIMIT_REASON,
    BoundedDigProbeStopConfig,
    BoundedDigProbeStopContract,
    bounded_dig_probe_step_fields,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _enabled_contract() -> BoundedDigProbeStopContract:
    config = BoundedDigProbeStopConfig.from_box_emptying_mapping(
        {
            "safety_enabled": True,
            "bounded_dig_probe_stop": {"enabled": True},
        }
    )
    return BoundedDigProbeStopContract(config)


def test_bounded_dig_probe_is_diagnostic_only_and_disabled_by_default() -> None:
    config = BoundedDigProbeStopConfig.from_box_emptying_mapping({})
    contract = BoundedDigProbeStopContract(config)

    assert config.enabled is False
    assert config.diagnostic_only is True
    assert (
        contract.observe_dig_state(
            step_id=10,
            cycle_index=1,
            dig_step_count=500,
            envelope_ready=True,
        )
        is None
    )
    assert contract.terminal_stop_requested() is False
    assert contract.debug_fields()["bounded_dig_probe_stop_enabled"] is False


def test_enabled_probe_requires_the_box_safety_interlock() -> None:
    with pytest.raises(
        ValueError,
        match="requires the safety interlock",
    ):
        BoundedDigProbeStopConfig.from_box_emptying_mapping(
            {
                "safety_enabled": False,
                "bounded_dig_probe_stop": {"enabled": True},
            }
        )

    config = BoundedDigProbeStopConfig.from_box_emptying_mapping(
        {
            "safety_enabled": True,
            "bounded_dig_probe_stop": {"enabled": True},
        }
    )
    assert config.enabled is True


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"target_cycle_index": 2}, "locked to cycle_index=1"),
        ({"max_dig_steps": 501}, "locked to max_dig_steps=500"),
        ({"diagnostic_only": False}, "must remain diagnostic_only"),
    ],
)
def test_enabled_probe_cannot_be_promoted_or_unbounded(
    override: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        BoundedDigProbeStopConfig.from_box_emptying_mapping(
            {
                "safety_enabled": True,
                "bounded_dig_probe_stop": {
                    "enabled": True,
                    **override,
                },
            }
        )


def test_probe_observes_only_cycle_one_and_envelope_precedes_step_limit() -> None:
    contract = _enabled_contract()

    assert (
        contract.observe_dig_state(
            step_id=9,
            cycle_index=0,
            dig_step_count=500,
            envelope_ready=True,
        )
        is None
    )
    reason = contract.observe_dig_state(
        step_id=10,
        cycle_index=1,
        dig_step_count=500,
        envelope_ready=True,
    )

    assert reason == BOUNDED_DIG_PROBE_ENVELOPE_REASON
    assert (
        contract.observe_dig_state(
            step_id=11,
            cycle_index=1,
            dig_step_count=501,
            envelope_ready=False,
        )
        is None
    )
    fields = contract.debug_fields()
    assert fields["bounded_dig_probe_stop_trigger_kind"] == "envelope_ready"
    assert fields["bounded_dig_probe_stop_trigger_step"] == 10


def test_probe_ignores_stale_envelope_on_cycle_switch_step_zero() -> None:
    contract = _enabled_contract()

    reason = contract.observe_dig_state(
        step_id=10,
        cycle_index=1,
        dig_step_count=0,
        envelope_ready=True,
    )

    assert reason is None
    assert contract.debug_fields()["bounded_dig_probe_stop_trigger_kind"] == ""


def test_dig_step_limit_requests_one_neutral_then_terminal_after_ack() -> None:
    contract = _enabled_contract()
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    reason = contract.observe_dig_state(
        step_id=20,
        cycle_index=1,
        dig_step_count=500,
        envelope_ready=False,
    )
    assert reason == BOUNDED_DIG_PROBE_STEP_LIMIT_REASON

    interlock.request_neutral_event(
        step_id=20,
        reason=reason,
        terminal=True,
    )
    neutral = interlock.filter_action(
        {"step_id": 20, "env_state": np.zeros(107)},
        np.ones(4, dtype=np.float32),
        active_cell_id=-1,
        active_corridor_id=-1,
    )
    contract.observe_safety_decision(neutral, cycle_index=1)

    assert neutral.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert neutral.awaiting_neutral_ack is True
    assert contract.terminal_stop_requested() is False

    acknowledged = interlock.filter_action(
        {"step_id": 21, "env_state": np.zeros(107)},
        np.ones(4, dtype=np.float32),
        active_cell_id=-1,
        active_corridor_id=-1,
    )
    contract.observe_safety_decision(acknowledged, cycle_index=1)

    assert acknowledged.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
    assert contract.terminal_stop_requested() is True


@pytest.mark.parametrize(
    ("safety_reason", "trigger_kind"),
    [
        ("wall_contact_first_session", "wall"),
        ("hard_bottom_contact", "bottom"),
        ("stuck_50_steps", "stuck"),
        ("timeout", "timeout"),
    ],
)
def test_first_safety_trigger_stops_probe_only_after_neutral_ack(
    safety_reason: str,
    trigger_kind: str,
) -> None:
    contract = _enabled_contract()
    neutral = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason=safety_reason,
        awaiting_neutral_ack=True,
    )

    contract.observe_safety_decision(neutral, cycle_index=1)

    assert contract.terminal_stop_requested() is False
    assert (
        contract.debug_fields()["bounded_dig_probe_stop_trigger_kind"]
        == trigger_kind
    )

    acknowledged = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason=f"{safety_reason}_neutral_acknowledged",
        neutral_acknowledged=True,
    )
    contract.observe_safety_decision(acknowledged, cycle_index=1)

    assert contract.terminal_stop_requested() is True
    fields = contract.debug_fields()
    assert fields["bounded_dig_probe_stop_neutral_acknowledged"] is True
    assert fields["bounded_dig_probe_stop_terminal_requested"] is True


def test_first_probe_trigger_is_latched_and_reset_clears_it() -> None:
    contract = _enabled_contract()
    contract.observe_safety_decision(
        SafetyActionDecision(
            action=np.zeros(4, dtype=np.float32),
            reason="wall_contact_first_session",
            awaiting_neutral_ack=True,
        ),
        cycle_index=1,
    )

    assert (
        contract.observe_dig_state(
            step_id=30,
            cycle_index=1,
            dig_step_count=500,
            envelope_ready=True,
        )
        is None
    )
    assert contract.debug_fields()["bounded_dig_probe_stop_trigger_kind"] == "wall"

    contract.reset()

    assert contract.debug_fields()["bounded_dig_probe_stop_trigger_kind"] == ""
    assert contract.terminal_stop_requested() is False


def test_runtime_composition_gives_an_existing_safety_decision_priority() -> None:
    contract = _enabled_contract()
    requests: list[str] = []
    safety = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason="wall_contact_first_session",
        awaiting_neutral_ack=True,
    )

    result = contract.apply_after_safety_decision(
        safety,
        step_id=40,
        cycle_index=1,
        dig_step_count=500,
        envelope_ready=True,
        request_terminal_neutral=requests.append,
        refilter_after_request=lambda: pytest.fail(
            "probe bound must not replace an existing safety decision"
        ),
    )

    assert result is safety
    assert requests == []
    assert contract.debug_fields()["bounded_dig_probe_stop_trigger_kind"] == "wall"


def test_runtime_composition_refilters_to_zero_for_envelope_stop() -> None:
    contract = _enabled_contract()
    requests: list[str] = []
    neutral = SafetyActionDecision(
        action=np.zeros(4, dtype=np.float32),
        reason=BOUNDED_DIG_PROBE_ENVELOPE_REASON,
        awaiting_neutral_ack=True,
    )

    result = contract.apply_after_safety_decision(
        SafetyActionDecision(action=np.ones(4, dtype=np.float32)),
        step_id=41,
        cycle_index=1,
        dig_step_count=100,
        envelope_ready=True,
        request_terminal_neutral=requests.append,
        refilter_after_request=lambda: neutral,
    )

    assert result is neutral
    assert result.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert requests == [BOUNDED_DIG_PROBE_ENVELOPE_REASON]
    assert (
        contract.debug_fields()[
            "bounded_dig_probe_stop_awaiting_neutral_ack"
        ]
        is True
    )


def test_planner_facade_builds_enabled_probe_from_box_config() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.box_emptying_cfg = {
        "safety_enabled": True,
        "bounded_dig_probe_stop": {"enabled": True},
    }

    contract = planner._bounded_dig_probe_stop()

    assert contract.config.enabled is True
    assert (
        planner.__dict__["_bounded_dig_probe_stop_state"]
        is contract
    )


def test_planner_filter_sends_zero_as_first_action_after_envelope_trigger() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 4
    planner._skill_name = "dig"
    contract = _enabled_contract()
    planner.__dict__["_bounded_dig_probe_stop_state"] = contract
    requests: list[dict[str, object]] = []
    applied: list[SafetyActionDecision] = []

    class _CarryGate:
        def timeout_requested(self) -> bool:
            return False

        def debug_fields(self) -> dict[str, bool]:
            return {"carry_start_envelope_ready": True}

    class _FunctionalGate:
        def terminal_neutral_requested(self) -> bool:
            return False

    class _CycleState:
        cycle_index = 1
        dig_step_count = 123
        transition_timeout_count = 0

    class _Interlock:
        pending_reason = ""

        def request_neutral_event(self, **kwargs: object) -> None:
            requests.append(dict(kwargs))
            self.pending_reason = str(kwargs["reason"])

        def filter_action(
            self,
            obs: dict[str, object],
            proposed_action: np.ndarray,
            **kwargs: object,
        ) -> SafetyActionDecision:
            del obs, kwargs
            if self.pending_reason:
                return SafetyActionDecision(
                    action=np.zeros_like(proposed_action),
                    reason=self.pending_reason,
                    awaiting_neutral_ack=True,
                )
            return SafetyActionDecision(action=proposed_action.copy())

    interlock = _Interlock()
    coverage_state = type(
        "_CoverageState",
        (),
        {
            "coverage_active_corridor_id": -1,
            "execution_return_envelope_cell_id": lambda self, corridor_id: -1,
        },
    )()
    planner.__dict__["_carry_start_envelope_gate_state"] = _CarryGate()
    planner.__dict__["_functional_cycle_gate_state"] = _FunctionalGate()
    planner._box_safety_interlock = MethodType(
        lambda self: interlock,
        planner,
    )
    planner._box_emptying_runtime_monitor = MethodType(
        lambda self: None,
        planner,
    )
    planner._primitive_cycle_runtime_state = MethodType(
        lambda self: _CycleState(),
        planner,
    )
    planner._coverage_runtime_state = MethodType(
        lambda self: coverage_state,
        planner,
    )
    planner._box_safety_active_cell_id = MethodType(
        lambda self, obs, active_corridor_id: -1,
        planner,
    )
    planner._apply_box_safety_decision = MethodType(
        lambda self, decision: applied.append(decision),
        planner,
    )

    action = planner._box_safety_filter_action(
        {"step_id": 60, "env_state": np.zeros(107, dtype=np.float32)},
        np.ones(4, dtype=np.float32),
    )

    assert action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert requests == [
        {
            "step_id": 60,
            "reason": BOUNDED_DIG_PROBE_ENVELOPE_REASON,
            "terminal": True,
        }
    ]
    assert applied[-1].awaiting_neutral_ack is True


def test_planner_terminalizes_nonterminal_safety_recovery_after_probe_ack() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    contract = _enabled_contract()
    contract.observe_safety_decision(
        SafetyActionDecision(
            action=np.zeros(4, dtype=np.float32),
            reason="hard_bottom_contact",
            awaiting_neutral_ack=True,
        ),
        cycle_index=1,
        step_id=50,
    )
    planner.__dict__["_bounded_dig_probe_stop_state"] = contract
    requested: list[tuple[str, bool]] = []

    class _CycleState:
        cycle_index = 1

    class _CoverageEffects:
        def request_coverage_terminal_stop(
            self,
            reason: str,
            *,
            replace: bool,
        ) -> None:
            requested.append((reason, replace))

    planner._primitive_cycle_runtime_state = MethodType(
        lambda self: _CycleState(),
        planner,
    )
    planner._primitive_coverage_effect_runtime = MethodType(
        lambda self: _CoverageEffects(),
        planner,
    )

    planner._apply_box_safety_decision(
        SafetyActionDecision(
            action=np.zeros(4, dtype=np.float32),
            reason="hard_bottom_contact_neutral_acknowledged",
            neutral_acknowledged=True,
            replan=True,
            hard_bottom_recovery_active=True,
            event_id=9,
        )
    )

    assert requested == [
        ("bounded_dig_probe_stop:bottom", True),
    ]


def test_rollout_projection_preserves_probe_handshake_fields() -> None:
    fields = bounded_dig_probe_step_fields(
        {
            "bounded_dig_probe_stop_enabled": True,
            "bounded_dig_probe_stop_diagnostic_only": True,
            "bounded_dig_probe_stop_target_cycle_index": 1,
            "bounded_dig_probe_stop_max_dig_steps": 500,
            "bounded_dig_probe_stop_trigger_kind": "wall",
            "bounded_dig_probe_stop_trigger_reason": (
                "wall_contact_first_session"
            ),
            "bounded_dig_probe_stop_trigger_step": 70,
            "bounded_dig_probe_stop_neutral_request_emitted": False,
            "bounded_dig_probe_stop_awaiting_neutral_ack": True,
            "bounded_dig_probe_stop_neutral_acknowledged": False,
            "bounded_dig_probe_stop_terminal_requested": False,
            "bounded_dig_probe_stop_terminal_reason": "",
        }
    )

    assert fields["bounded_dig_probe_stop_trigger_kind"] == "wall"
    assert fields["bounded_dig_probe_stop_trigger_step"] == 70
    assert fields["bounded_dig_probe_stop_awaiting_neutral_ack"] is True
    assert fields["bounded_dig_probe_stop_terminal_requested"] is False
