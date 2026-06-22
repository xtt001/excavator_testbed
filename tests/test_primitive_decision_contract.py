from __future__ import annotations

from types import MethodType
from typing import Any

from testbed.planner.primitive_decision import (
    LEGACY_FSM_DECISION_SOURCE,
    LegacyDecisionOutcomeEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    SwitchSkillEffect,
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
        RequestedPlannerEffect(effect_type="restart_after_failed_dig", reason="second"),
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


def test_switch_skill_effect_records_semantic_target_and_reason() -> None:
    effect = SwitchSkillEffect(
        target_skill_name="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
        effects=(effect,),
    )

    assert result.effects == (effect,)
    assert effect.effect_type == "switch_skill"
    assert effect.target_skill_name == "carry"
    assert effect.switch_reason == "dig_to_carry_boundary_confirmed"
    assert effect.reason == "dig_to_carry_boundary_confirmed"


def test_switch_skill_effect_rejects_empty_skill_or_reason() -> None:
    invalid_results = (
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="",
            switch_reason="dig_to_carry_boundary_confirmed",
            effects=(
                SwitchSkillEffect(
                    target_skill_name="",
                    switch_reason="dig_to_carry_boundary_confirmed",
                ),
            ),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="carry",
            switch_reason="",
            effects=(SwitchSkillEffect(target_skill_name="carry", switch_reason=""),),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
            effects=(
                RequestedPlannerEffect(
                    effect_type="switch_skill",
                    payload={
                        "target_skill_name": "carry",
                        "switch_reason": "dig_to_carry_boundary_confirmed",
                    },
                ),
            ),
            validate=False,
        ),
    )

    for result in invalid_results:
        try:
            validate_decision_effect_contract(result)
        except PrimitiveDecisionContractError:
            pass
        else:
            raise AssertionError("invalid SwitchSkill effect was accepted")


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


def test_primitive_planner_requested_effect_bridge_allows_empty_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)

    planner._apply_requested_tick_effects(())


def test_primitive_planner_requested_effect_bridge_rejects_live_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    effects = (
        RequestedPlannerEffect(
            effect_type="record_decision_trace",
            reason="future_backend_probe",
        ),
    )

    try:
        planner._apply_requested_tick_effects(effects)
    except PrimitiveDecisionContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("live requested effects were silently ignored")

    assert "real planner" in message
    assert "requested-effect application" in message
    assert "only supports SwitchSkill" in message


def test_primitive_planner_requested_effect_bridge_applies_switch_skill() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    calls: list[tuple[str, str]] = []

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        calls.append((skill_name, reason))

    planner._set_skill = MethodType(fake_set_skill, planner)

    planner._apply_requested_tick_effects(
        (
            SwitchSkillEffect(
                target_skill_name="carry",
                switch_reason="dig_to_carry_boundary_confirmed",
            ),
        )
    )

    assert calls == [("carry", "dig_to_carry_boundary_confirmed")]


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


def test_primitive_planner_bootstrap_decision_bridge_returns_requested_switch() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "bootstrap"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    calls: list[tuple[str, str]] = []

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        calls.append((skill_name, reason))

    planner._set_skill = MethodType(fake_set_skill, planner)
    planner._should_end_bootstrap = MethodType(
        lambda self, *, obs, boundary_event: True,
        planner,
    )
    planner.bootstrap_end_mode = "first_qualified_dig_start"
    planner._should_pre_dig_align_before_dig = MethodType(
        lambda self: False,
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="bootstrap",
            dig_progress_updated=False,
        ),
    )

    assert calls == []
    assert result.side_effects_applied is False
    assert result.skill_before == "bootstrap"
    assert result.skill_after == "dig"
    assert result.switch_reason == "bootstrap_to_dig"
    assert result.effects == (
        SwitchSkillEffect(
            target_skill_name="dig",
            switch_reason="bootstrap_to_dig",
        ),
    )
