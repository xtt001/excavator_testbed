from __future__ import annotations

import json

from testbed.planner.primitive.decision.contracts import (
    PrimitiveDecisionResult,
    RequestedPlannerEffect,
)
from testbed.planner.primitive.report.decision_trace import (
    DecisionDiagnosticCheck,
    DecisionTraceAssembler,
    DecisionTraceMetadata,
)
from testbed.planner.primitive.report.decision_trace_export import (
    DecisionTraceExportAdapter,
    to_offline_rich_trace,
    to_online_compact_trace,
)


def _trace_record():
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow_validation",
        status="no_change",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="external_observe_only",
                reason="observe",
                payload={"safe_key": "safe_value"},
            ),
        ),
    )
    return DecisionTraceAssembler.assemble(
        result=result,
        backend_payload={
            "backend_family": "external",
            "payload_kind": "summary",
            "evidence_ids": ("frame-001",),
        },
        metadata=DecisionTraceMetadata(
            backend_name="external_shadow",
            backend_kind="external",
            tick_id="tick-001",
            episode_id="episode-001",
            sim_time_s=4.25,
            selected_operation="continue_current_skill",
            fallback_type="validator_rejected",
            reason_codes=("validator_rejected", "payload_rejected"),
            diagnostic_checks=(
                DecisionDiagnosticCheck(
                    name="proposal_effect_payload_safe",
                    status="fail",
                    reason="payload_rejected",
                    value={"payload_keys": ("safe_key",)},
                ),
            ),
            validation_status="rejected",
        ),
    )


def test_online_compact_trace_adapter_exposes_bounded_generic_fields() -> None:
    record = _trace_record()

    compact = to_online_compact_trace(record)

    assert compact == DecisionTraceExportAdapter.to_online_compact_trace(record)
    assert list(compact) == [
        "schema_version",
        "backend_name",
        "backend_kind",
        "decision_source",
        "decision_status",
        "trace_status",
        "validation_status",
        "skill_before",
        "skill_after",
        "selected_operation",
        "fallback_type",
        "reason_codes",
        "requested_effects_summary",
        "confidence",
        "score",
        "tick_id",
        "sim_time_s",
    ]
    assert compact["backend_name"] == "external_shadow"
    assert compact["backend_kind"] == "external"
    assert compact["trace_status"] == "fallback"
    assert compact["validation_status"] == "rejected"
    assert compact["selected_operation"] == "continue_current_skill"
    assert compact["fallback_type"] == "validator_rejected"
    assert compact["reason_codes"] == ["validator_rejected", "payload_rejected"]
    assert compact["requested_effects_summary"] == [
        {
            "effect_type": "external_observe_only",
            "reason": "observe",
            "already_applied": False,
        }
    ]
    assert compact["tick_id"] == "tick-001"
    assert compact["sim_time_s"] == 4.25
    assert "backend_payload" not in compact
    assert "diagnostic_checks" not in compact
    assert "switch_reason" not in compact
    json.dumps(compact, sort_keys=True)


def test_offline_rich_trace_adapter_exposes_safe_rich_record_shape() -> None:
    record = _trace_record()

    rich = to_offline_rich_trace(record)

    assert rich == DecisionTraceExportAdapter.to_offline_rich_trace(record)
    assert rich["switch_reason"] == ""
    assert rich["episode_id"] == "episode-001"
    assert rich["backend_payload"] == {
        "backend_family": "external",
        "evidence_ids": ["frame-001"],
        "payload_kind": "summary",
    }
    assert rich["diagnostic_checks"] == [
        {
            "name": "proposal_effect_payload_safe",
            "status": "fail",
            "reason": "payload_rejected",
            "value": {"payload_keys": ["safe_key"]},
        }
    ]
    assert rich["requested_effects_summary"] == [
        {
            "effect_type": "external_observe_only",
            "reason": "observe",
            "already_applied": False,
            "payload_keys": ["safe_key"],
        }
    ]
    json.dumps(rich, sort_keys=True)


def test_trace_export_adapter_tolerates_absent_trace_record() -> None:
    assert to_online_compact_trace(None) is None
    assert to_offline_rich_trace(None) is None
    assert DecisionTraceExportAdapter.to_online_compact_trace(None) is None
    assert DecisionTraceExportAdapter.to_offline_rich_trace(None) is None
