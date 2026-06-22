from __future__ import annotations

from pathlib import Path

import pytest

from testbed.planner.evidence_trace import (
    BASELINE_CAPABILITY_SPECS,
    CapabilitySpec,
    EvidenceEvent,
    EvidenceTraceError,
    classify_evidence,
    events_from_rollout_row,
    read_evidence_jsonl,
    write_evidence_jsonl,
)


def test_evidence_event_round_trips_through_stable_json_schema(tmp_path: Path) -> None:
    event = EvidenceEvent(
        tick_id=7,
        capability_id="token.dig_cut",
        event_type="token",
        producer="PrimitivePlannerACTPolicy._dig_cut_tokens_for_obs",
        observed=True,
        consumed_by_decision=True,
        reported=True,
        supports=("gate.dig_to_carry",),
        payload={"source": "coverage_corridor", "valid": True},
    )

    path = tmp_path / "trace.jsonl"
    write_evidence_jsonl(path, [event])

    rows = [item.to_json() for item in read_evidence_jsonl(path)]
    assert rows == [
        {
            "schema_version": 1,
            "tick_id": 7,
            "capability_id": "token.dig_cut",
            "event_type": "token",
            "producer": "PrimitivePlannerACTPolicy._dig_cut_tokens_for_obs",
            "observed": True,
            "consumed_by_decision": True,
            "reported": True,
            "supports": ["gate.dig_to_carry"],
            "payload": {"source": "coverage_corridor", "valid": True},
        }
    ]

    with pytest.raises(EvidenceTraceError, match="capability_id"):
        EvidenceEvent.from_json({"schema_version": 1, "tick_id": 1})


def test_classifier_separates_live_support_report_owners_and_legacy_parking() -> None:
    specs = [
        CapabilitySpec(
            capability_id="gate.dig_to_carry",
            owner="PrimitivePlannerACTPolicy._maybe_switch_skill",
            category="gate",
        ),
        CapabilitySpec(
            capability_id="metric.dig_mass_progress",
            owner="PrimitivePlannerACTPolicy._update_dig_progress",
            category="metric",
        ),
        CapabilitySpec(
            capability_id="debug.rollout_summary",
            owner="PrimitivePlannerACTPolicy.rollout_summary",
            category="report",
        ),
        CapabilitySpec(
            capability_id="policy.public_adapter",
            owner="PrimitivePlannerACTPolicy",
            category="compatibility",
            owner_classification="compatibility",
        ),
        CapabilitySpec(
            capability_id="legacy.5p_removed_runtime",
            owner="removed 5P runtime planner (git history only)",
            category="compatibility",
            owner_classification="removed-runtime",
        ),
        CapabilitySpec(
            capability_id="unused.current_packet",
            owner="PrimitivePlannerACTPolicy._unused_current_packet",
            category="unknown",
        ),
        CapabilitySpec(
            capability_id="unused.protected_diagnostic",
            owner="PrimitivePlannerACTPolicy._protected_diagnostic",
            category="unknown",
            protect_when_unobserved=True,
        ),
    ]
    events = [
        EvidenceEvent(
            tick_id=11,
            capability_id="gate.dig_to_carry",
            event_type="gate",
            producer="PrimitivePlannerACTPolicy._maybe_switch_skill",
            observed=True,
            consumed_by_decision=True,
            reported=True,
            payload={"reason": "dig_to_carry_boundary_event"},
        ),
        EvidenceEvent(
            tick_id=11,
            capability_id="metric.dig_mass_progress",
            event_type="metric",
            producer="PrimitivePlannerACTPolicy._update_dig_progress",
            observed=True,
            supports=("gate.dig_to_carry",),
            payload={"best_mass_kg": 42.0},
        ),
        EvidenceEvent(
            tick_id=11,
            capability_id="debug.rollout_summary",
            event_type="report",
            producer="PrimitivePlannerACTPolicy.rollout_summary",
            observed=True,
            reported=True,
        ),
    ]

    report = classify_evidence(
        events,
        specs,
        evidence_packet_count=3,
        dead_candidate_min_packets=2,
    )
    by_id = {row.capability_id: row for row in report.rows}

    assert by_id["gate.dig_to_carry"].classification == "confirmed-live"
    assert by_id["metric.dig_mass_progress"].classification == "support-live"
    assert by_id["debug.rollout_summary"].classification == "report-only"
    assert by_id["policy.public_adapter"].classification == "compatibility"
    assert by_id["legacy.5p_removed_runtime"].classification == "removed-runtime"
    assert by_id["unused.current_packet"].classification == "dead-candidate"
    assert by_id["unused.protected_diagnostic"].classification == "not-observed"
    assert by_id["gate.dig_to_carry"].retention_decision == "retain-and-migrate"
    assert by_id["debug.rollout_summary"].retention_decision == "retain-report-boundary"
    assert by_id["unused.current_packet"].retention_decision == "retain-legacy-parking"
    assert (
        by_id["legacy.5p_removed_runtime"].retention_decision
        == "removed-runtime-cleanup"
    )
    assert by_id["unused.protected_diagnostic"].retention_decision == "hold-unobserved"


def test_rollout_rows_are_converted_into_capability_evidence() -> None:
    row = {
        "t": 42,
        "skill_name": "dig",
        "skill_switch_reason": "pre_dig_align_to_dig_ready",
        "transition_completed": False,
        "transition_timeout": False,
        "goal_tokens": [0.0, 1.0],
        "dig_cut_token_injected": True,
        "dig_cut_token_source": "coverage_corridor",
        "dig_depth_profile_token_injected": True,
        "dig_depth_profile_token_source": "state_exemplar",
        "return_target_token_injected": False,
        "return_target_token_source": "none",
        "return_start_envelope_token_injected": False,
        "return_start_envelope_token_source": "none",
        "coverage_corridor_id": 3,
        "coverage_terminal_stop_requested": False,
        "pre_dig_align_completed_count": 1,
        "pre_dig_align_entry_error_m": 0.03,
        "dig_step_count": 10,
        "dig_best_mass_kg": 51.5,
        "dig_to_carry_reason": "",
        "dump_ready_hold_count": 0,
        "dump_done_hold_count": 0,
        "return_to_dig_entry_close": True,
        "return_to_dig_entry_error_m": 0.02,
    }

    events = events_from_rollout_row(row)
    report = classify_evidence(events, BASELINE_CAPABILITY_SPECS)
    by_id = {item.capability_id: item for item in report.rows}

    assert by_id["execution.predict_tick"].classification == "confirmed-live"
    assert by_id["fsm.skill_switch"].classification == "confirmed-live"
    assert by_id["token.goal"].classification == "confirmed-live"
    assert by_id["token.dig_cut"].classification == "confirmed-live"
    assert by_id["token.dig_depth_profile"].classification == "confirmed-live"
    assert by_id["gate.pre_dig_align"].classification == "confirmed-live"
    assert by_id["metric.dig_progress"].classification == "support-live"
    assert by_id["coverage.corridor"].classification == "confirmed-live"
    assert by_id["token.return_target"].classification == "dead-candidate"
    assert by_id["token.return_target"].retention_decision == "retain-legacy-parking"


def test_mainline_absent_cell_entry_and_pre_dig_align_are_parked_outside_mainline() -> None:
    report = classify_evidence(
        [
            EvidenceEvent(
                tick_id=1,
                capability_id="execution.predict_tick",
                event_type="execution",
                producer="PrimitivePlannerACTPolicy.predict",
                consumed_by_decision=True,
                reported=True,
            )
        ],
        BASELINE_CAPABILITY_SPECS,
        evidence_packet_count=3,
        dead_candidate_min_packets=2,
    )
    by_id = {item.capability_id: item for item in report.rows}

    assert by_id["token.cell_entry"].classification == "dead-candidate"
    assert by_id["token.cell_entry"].retention_decision == "retain-legacy-parking"
    assert by_id["gate.pre_dig_align"].classification == "dead-candidate"
    assert by_id["gate.pre_dig_align"].retention_decision == "retain-legacy-parking"
