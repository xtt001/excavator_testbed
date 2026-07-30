from __future__ import annotations

import pytest

from testbed.planner.primitive.decision.contracts import (
    LEGACY_FSM_DECISION_SOURCE,
    CompleteCoverageDigEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    SwitchSkillEffect,
)
from testbed.planner.primitive.decision.validation import DecisionProposalValidator


def _legacy_requested_switch() -> PrimitiveDecisionResult:
    return PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_dig_requested_effect",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(
            CompleteCoverageDigEffect(),
            SwitchSkillEffect(
                target_skill_name="carry",
                switch_reason="dig_to_carry_loaded",
            ),
        ),
    )


def _bt_continue_fallback() -> PrimitiveDecisionResult:
    return PrimitiveDecisionResult.from_requested_effects(
        decision_source="behavior_tree_continue_current_skill",
        status="no_change",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=(),
    )


def test_valid_legacy_fsm_requested_effect_result_is_accepted() -> None:
    validation = DecisionProposalValidator.validate(
        result=_legacy_requested_switch(),
        backend_name="legacy_fsm",
        backend_kind="legacy_fsm",
        expected_skill_before="dig",
    )

    assert validation.accepted is True
    assert validation.status == "accepted"
    assert validation.reasons == ()
    assert [check.to_dict() for check in validation.checks] == [
        {
            "name": "proposal_result_contract_valid",
            "status": "pass",
            "reason": "",
            "value": {
                "decision_source": "legacy_fsm_dig_requested_effect",
                "decision_status": "skill_switch",
                "side_effects_applied": False,
            },
        },
        {
            "name": "proposal_effect_types_supported",
            "status": "pass",
            "reason": "",
            "value": {"effect_types": ["complete_coverage_dig", "switch_skill"]},
        },
        {
            "name": "proposal_effect_payload_safe",
            "status": "pass",
            "reason": "",
            "value": {"effect_count": 2},
        },
        {
            "name": "proposal_context_consistent",
            "status": "pass",
            "reason": "",
            "value": {"expected_skill_before": "dig", "skill_before": "dig"},
        },
    ]


def test_valid_legacy_compatibility_outcome_is_accepted_for_legacy_backend() -> None:
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        skill_before="carry",
        skill_after="dump",
        switch_reason="carry_to_dump_target_ready",
        decision_source=LEGACY_FSM_DECISION_SOURCE,
    )

    validation = DecisionProposalValidator.validate(
        result=result,
        backend_name="legacy_fsm",
        backend_kind="legacy_fsm",
    )

    assert validation.accepted is True
    assert validation.status == "accepted"
    assert validation.reasons == ()


def test_valid_behavior_tree_no_change_fallback_is_accepted() -> None:
    validation = DecisionProposalValidator.validate(
        result=_bt_continue_fallback(),
        backend_name="behavior_tree_shadow",
        backend_kind="behavior_tree",
        expected_skill_before="return",
    )

    assert validation.accepted is True
    assert validation.status == "accepted"
    assert validation.reasons == ()


def test_unsupported_requested_effect_class_is_rejected() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
            ),
        ),
    )

    with pytest.raises(
        PrimitiveDecisionContractError,
        match="unsupported requested effect class",
    ):
        DecisionProposalValidator.validate(
            result=result,
            backend_name="external_shadow",
            backend_kind="external",
        )


def test_callable_or_object_payload_is_rejected() -> None:
    unsafe_callable_called = False

    def unsafe_callable() -> None:
        nonlocal unsafe_callable_called
        unsafe_callable_called = True

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
                payload={"callback": unsafe_callable, "object": object()},
            ),
        ),
        validate=False,
    )

    with pytest.raises(PrimitiveDecisionContractError, match="callable effect payload"):
        DecisionProposalValidator.validate(
            result=result,
            backend_name="external_shadow",
            backend_kind="external",
        )
    assert unsafe_callable_called is False


def test_expected_skill_mismatch_is_rejected() -> None:
    with pytest.raises(
        PrimitiveDecisionContractError,
        match="proposal skill_before mismatch",
    ):
        DecisionProposalValidator.validate(
            result=_legacy_requested_switch(),
            backend_name="legacy_fsm",
            backend_kind="legacy_fsm",
            expected_skill_before="carry",
        )


def test_no_change_result_with_different_before_after_skill_is_rejected() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="no_change",
        skill_before="dig",
        skill_after="carry",
        switch_reason="",
        effects=(),
        validate=False,
    )

    with pytest.raises(
        PrimitiveDecisionContractError,
        match="no-change proposal must preserve skill",
    ):
        DecisionProposalValidator.validate(
            result=result,
            backend_name="external_shadow",
            backend_kind="external",
        )


def test_strict_mode_raises_and_never_applies_effects() -> None:
    side_effects: list[str] = []

    def mutation_callback() -> None:
        side_effects.append("called")

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
                payload={"callback": mutation_callback},
            ),
        ),
        validate=False,
    )

    with pytest.raises(PrimitiveDecisionContractError):
        DecisionProposalValidator.validate(
            result=result,
            backend_name="external_shadow",
            backend_kind="external",
        )
    assert side_effects == []


def test_shadow_fallback_accepts_valid_proposal_without_replacement() -> None:
    result = _legacy_requested_switch()

    outcome = DecisionProposalValidator.validate_with_shadow_fallback(
        result=result,
        backend_name="legacy_fsm",
        backend_kind="legacy_fsm",
        expected_skill_before="dig",
    )

    assert outcome.result is result
    assert outcome.fallback_applied is False
    assert outcome.validation.accepted is True
    assert outcome.validation.status == "accepted"


def test_shadow_fallback_converts_unsupported_effect_to_no_change_result() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
            ),
        ),
    )

    outcome = DecisionProposalValidator.validate_with_shadow_fallback(
        result=result,
        backend_name="external_shadow",
        backend_kind="external",
        expected_skill_before="dig",
    )

    assert outcome.fallback_applied is True
    assert outcome.result.decision_source == "validator_rejected_shadow_fallback"
    assert outcome.result.status == "no_change"
    assert outcome.result.skill_before == "dig"
    assert outcome.result.skill_after == "dig"
    assert outcome.result.switch_reason == ""
    assert outcome.result.effects == ()
    assert outcome.validation.accepted is False
    assert outcome.validation.status == "rejected"
    assert outcome.validation.reasons[0] == "validator_rejected"
    assert [check.to_dict() for check in outcome.validation.checks] == [
        {
            "name": "proposal_shadow_fallback_applied",
            "status": "fail",
            "reason": (
                "unsupported requested effect class for strict validation: "
                "external_custom_effect"
            ),
            "value": {
                "backend_kind": "external",
                "backend_name": "external_shadow",
                "fallback_skill": "dig",
                "rejected_decision_source": "external_shadow",
            },
        }
    ]


def test_shadow_fallback_does_not_call_rejected_payloads() -> None:
    side_effects: list[str] = []

    def mutation_callback() -> None:
        side_effects.append("called")

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
                payload={"callback": mutation_callback},
            ),
        ),
        validate=False,
    )

    outcome = DecisionProposalValidator.validate_with_shadow_fallback(
        result=result,
        backend_name="external_shadow",
        backend_kind="external",
        expected_skill_before="dig",
    )

    assert side_effects == []
    assert outcome.fallback_applied is True
    assert outcome.result.effects == ()
    assert outcome.validation.accepted is False
    assert outcome.validation.reasons == (
        "validator_rejected",
        "callable effect payload at effects[0].payload.callback",
    )


def test_shadow_fallback_keeps_strict_validate_raising() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
            ),
        ),
    )

    with pytest.raises(
        PrimitiveDecisionContractError,
        match="unsupported requested effect class",
    ):
        DecisionProposalValidator.validate(
            result=result,
            backend_name="external_shadow",
            backend_kind="external",
        )


def test_shadow_fallback_uses_expected_skill_for_context_mismatch() -> None:
    outcome = DecisionProposalValidator.validate_with_shadow_fallback(
        result=_legacy_requested_switch(),
        backend_name="legacy_fsm",
        backend_kind="legacy_fsm",
        expected_skill_before="carry",
    )

    assert outcome.fallback_applied is True
    assert outcome.result.status == "no_change"
    assert outcome.result.skill_before == "carry"
    assert outcome.result.skill_after == "carry"
    assert outcome.result.effects == ()
    assert outcome.validation.reasons == (
        "validator_rejected",
        "proposal skill_before mismatch: expected 'carry', received 'dig'",
    )
