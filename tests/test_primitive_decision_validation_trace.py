from __future__ import annotations

import json

from testbed.planner.primitive.decision.contracts import (
    CompleteCoverageDigEffect,
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
    SwitchSkillEffect,
)
from testbed.planner.primitive.decision.validation import DecisionProposalValidator
from testbed.planner.primitive.report.decision_trace import (
    DecisionTraceAssembler,
    DecisionTraceMetadata,
)
from testbed.planner.primitive.report.decision_validation_trace import (
    project_shadow_fallback_outcome_to_trace,
    project_validation_result_to_trace,
)


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


def test_accepted_validation_projects_to_compact_and_rich_trace_fields() -> None:
    result = _legacy_requested_switch()
    validation = DecisionProposalValidator.validate(
        result=result,
        backend_name="legacy_fsm",
        backend_kind="legacy_fsm",
        expected_skill_before="dig",
    )

    projection = project_validation_result_to_trace(validation)
    record = DecisionTraceAssembler.assemble(
        result=result,
        backend_payload=projection.with_backend_payload(
            {"backend_family": "legacy_fsm"}
        ),
        metadata=DecisionTraceMetadata(
            backend_name="legacy_fsm",
            backend_kind="legacy_fsm",
            selected_operation="switch_skill",
            validation_status=projection.validation_status,
            reason_codes=projection.reason_codes,
            diagnostic_checks=projection.diagnostic_checks,
        ),
    )

    compact = record.to_compact_dict()
    assert compact["validation_status"] == "accepted"
    assert compact["selected_operation"] == "switch_skill"
    assert compact["fallback_type"] == "none"
    assert "backend_payload" not in compact

    rich = record.to_rich_dict()
    assert rich["backend_payload"]["backend_family"] == "legacy_fsm"
    assert rich["backend_payload"]["validation"] == {
        "accepted": True,
        "status": "accepted",
        "fallback_applied": False,
        "reasons": [],
        "checks": [
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
        ],
    }
    assert [check["name"] for check in rich["diagnostic_checks"]] == [
        "proposal_result_contract_valid",
        "proposal_effect_types_supported",
        "proposal_effect_payload_safe",
        "proposal_context_consistent",
    ]
    json.dumps(compact, sort_keys=True)
    json.dumps(rich, sort_keys=True)


def test_shadow_fallback_projection_marks_validator_rejection_without_raw_payload() -> None:
    side_effects: list[str] = []

    def mutation_callback() -> None:
        side_effects.append("called")

    rejected_result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_custom_effect",
                reason="custom",
                payload={"callback": mutation_callback, "object": object()},
            ),
        ),
        validate=False,
    )
    outcome = DecisionProposalValidator.validate_with_shadow_fallback(
        result=rejected_result,
        backend_name="external_shadow",
        backend_kind="external",
        expected_skill_before="dig",
    )

    projection = project_shadow_fallback_outcome_to_trace(outcome)
    record = DecisionTraceAssembler.assemble(
        result=outcome.result,
        backend_payload=projection.with_backend_payload(
            {"backend_family": "external", "payload_kind": "proposal_summary"}
        ),
        metadata=DecisionTraceMetadata(
            backend_name="external_shadow",
            backend_kind="external",
            selected_operation=projection.selected_operation,
            fallback_type=projection.fallback_type,
            validation_status=projection.validation_status,
            reason_codes=projection.reason_codes,
            diagnostic_checks=projection.diagnostic_checks,
        ),
    )

    assert side_effects == []
    compact = record.to_compact_dict()
    assert compact["trace_status"] == "fallback"
    assert compact["validation_status"] == "rejected"
    assert compact["selected_operation"] == "validator_rejected_fallback"
    assert compact["fallback_type"] == "validator_rejected"
    assert compact["reason_codes"] == [
        "validator_rejected",
        "callable effect payload at effects[0].payload.callback",
    ]
    assert "backend_payload" not in compact

    rich = record.to_rich_dict()
    validation_payload = rich["backend_payload"]["validation"]
    assert validation_payload["accepted"] is False
    assert validation_payload["status"] == "rejected"
    assert validation_payload["fallback_applied"] is True
    assert validation_payload["checks"] == [
        {
            "name": "proposal_shadow_fallback_applied",
            "status": "fail",
            "reason": "callable effect payload at effects[0].payload.callback",
            "value": {
                "backend_kind": "external",
                "backend_name": "external_shadow",
                "fallback_skill": "dig",
                "rejected_decision_source": "external_shadow",
            },
        }
    ]
    serialized_rich = json.dumps(rich, sort_keys=True)
    assert "called" not in serialized_rich
    assert "object object at" not in serialized_rich


def test_compact_validation_status_defaults_to_skipped_without_projection() -> None:
    record = DecisionTraceAssembler.assemble(
        result=PrimitiveDecisionResult.from_requested_effects(
            decision_source="behavior_tree_continue_current_skill",
            status="no_change",
            skill_before="return",
            skill_after="return",
            switch_reason="",
            effects=(),
        ),
        backend_payload=None,
        metadata=DecisionTraceMetadata(
            backend_name="behavior_tree_shadow",
            backend_kind="behavior_tree",
        ),
    )

    assert record.validation_status == "skipped"
    assert record.to_compact_dict()["validation_status"] == "skipped"
    assert record.to_rich_dict()["validation_status"] == "skipped"
