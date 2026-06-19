from __future__ import annotations

from types import MethodType
from typing import Any

from testbed.planner.primitive_decision import (
    LEGACY_FSM_DECISION_SOURCE,
    LegacyDecisionOutcomeEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    validate_decision_effect_contract,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_legacy_decision_result_records_observable_skill_switch_only() -> None:
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
    )

    assert result.decision_source == LEGACY_FSM_DECISION_SOURCE
    assert result.status == "skill_switch"
    assert result.skill_before == "dig"
    assert result.skill_after == "carry"
    assert result.switch_reason == "dig_to_carry_boundary_confirmed"
    assert result.side_effects_applied is True
    assert result.effects == (
        LegacyDecisionOutcomeEffect(
            effect_type="legacy_decision_outcome",
            already_applied=True,
            skill_before="dig",
            skill_after="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
        ),
    )


def test_legacy_decision_result_does_not_infer_private_effects_for_no_change() -> None:
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        skill_before="return",
        skill_after="return",
        switch_reason="",
    )

    assert result.status == "no_change"
    assert result.effects == ()
    assert result.side_effects_applied is True


def test_requested_effect_result_records_ordered_unapplied_effects() -> None:
    effects = (
        RequestedPlannerEffect(effect_type="record_decision_trace", reason="first"),
        RequestedPlannerEffect(effect_type="switch_skill", reason="second"),
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
        effects=effects,
    )

    assert result.side_effects_applied is False
    assert result.effects == effects
    assert [effect.reason for effect in result.effects] == ["first", "second"]


def test_decision_contract_rejects_callable_or_planner_method_effect_shapes() -> None:
    callable_effect = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="record_decision_trace",
                payload={"callback": lambda: None},
            ),
        ),
        validate=False,
    )
    method_effect = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="call_planner_method",
                payload={"method_name": "_set_skill"},
            ),
        ),
        validate=False,
    )

    for result in (callable_effect, method_effect):
        try:
            validate_decision_effect_contract(result)
        except PrimitiveDecisionContractError:
            pass
        else:
            raise AssertionError("invalid requested effect shape was accepted")


def test_primitive_planner_legacy_decision_bridge_calls_fsm_once() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "dig"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    calls: list[tuple[dict[str, Any], object, str]] = []

    def fake_maybe_switch_skill(
        self: PrimitivePlannerACTPolicy,
        *,
        obs: dict[str, Any],
        boundary_event: object,
    ) -> None:
        calls.append((obs, boundary_event, str(self._skill_name)))
        self._skill_name = "carry"
        self._switch_reason = "dig_to_carry_boundary_confirmed"

    planner._maybe_switch_skill = MethodType(fake_maybe_switch_skill, planner)

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert calls == [(obs, boundary_event, "dig")]
    assert result.decision_source == LEGACY_FSM_DECISION_SOURCE
    assert result.status == "skill_switch"
    assert result.skill_before == "dig"
    assert result.skill_after == "carry"
    assert result.switch_reason == "dig_to_carry_boundary_confirmed"
