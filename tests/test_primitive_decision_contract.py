from __future__ import annotations

from types import MethodType
from typing import Any

from testbed.planner.primitive_capabilities import ReturnTransitionStatus
from testbed.planner.primitive_decision import (
    LEGACY_FSM_DECISION_SOURCE,
    CompleteReturnTransitionEffect,
    LegacyDecisionOutcomeEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    SwitchToNextSkillAfterReturnEffect,
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


def test_return_cycle_effects_record_semantic_requests() -> None:
    effects = (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_return_requested_effect",
        status="skill_switch",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=effects,
    )

    assert result.effects == effects
    assert [effect.effect_type for effect in result.effects] == [
        "mark_return_next_dig_event_seen",
        "complete_return_transition",
        "switch_to_next_skill_after_return",
    ]
    assert effects[2].reason == "next_dig_entry_ready"


def test_return_cycle_effect_rejects_empty_reason_suffix() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_return_requested_effect",
        status="skill_switch",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=(SwitchToNextSkillAfterReturnEffect(reason_suffix=""),),
        validate=False,
    )

    try:
        validate_decision_effect_contract(result)
    except PrimitiveDecisionContractError:
        pass
    else:
        raise AssertionError("invalid return switch effect was accepted")


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


def test_primitive_planner_requested_effect_bridge_applies_return_cycle_in_order() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    events: list[str] = []
    state = {"cycle": 0}

    def fake_mark(self: PrimitivePlannerACTPolicy) -> None:
        events.append("mark")

    def fake_complete(self: PrimitivePlannerACTPolicy) -> None:
        state["cycle"] += 1
        events.append(f"complete:{state['cycle']}")

    def fake_next_skill(self: PrimitivePlannerACTPolicy) -> str:
        events.append(f"next_skill:{state['cycle']}")
        return "dig" if state["cycle"] > 0 else "pre_dig_align"

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        events.append(f"set:{skill_name}:{reason}")

    planner._mark_return_next_dig_event_seen = MethodType(fake_mark, planner)
    planner._complete_return_transition_for_backend = MethodType(
        fake_complete,
        planner,
    )
    planner._next_skill_after_return_transition = MethodType(fake_next_skill, planner)
    planner._set_skill = MethodType(fake_set_skill, planner)

    planner._apply_requested_tick_effects(
        (
            MarkReturnNextDigEventSeenEffect(),
            CompleteReturnTransitionEffect(),
            SwitchToNextSkillAfterReturnEffect(
                reason_suffix="next_dig_entry_ready",
            ),
        )
    )

    assert events == [
        "mark",
        "complete:1",
        "next_skill:1",
        "set:dig:return_to_dig_next_dig_entry_ready",
    ]


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


def test_primitive_planner_return_decision_bridge_returns_requested_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "return"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    calls: list[str] = []

    planner._return_transition_status_for_backend = MethodType(
        lambda self, obs, boundary_event: ReturnTransitionStatus(
            mass_in_bucket_kg=0.0,
            min_distance_to_dig_area_m=0.0,
            bucket_depth_below_dig_area_plane_m=0.0,
            semantic_boundary_profile_active=True,
            next_dig_event=True,
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            direct_handoff_ready=False,
            shallow_guard_ready=False,
            shallow_guard_allowed=False,
            completed_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_next_dig_entry_ready",
        ),
        planner,
    )
    planner._mark_return_next_dig_event_seen = MethodType(
        lambda self: calls.append("mark"),
        planner,
    )
    planner._complete_return_transition_for_backend = MethodType(
        lambda self: calls.append("complete"),
        planner,
    )
    planner._next_skill_after_return_transition = MethodType(
        lambda self: "dig",
        planner,
    )
    planner._set_skill = MethodType(
        lambda self, skill_name, reason: calls.append(f"{skill_name}:{reason}"),
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert calls == []
    assert result.side_effects_applied is False
    assert result.status == "skill_switch"
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )
