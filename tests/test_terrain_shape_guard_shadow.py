from __future__ import annotations

from testbed.eval.terrain_shape_guard_shadow import build_shape_guard_shadow_audit


def _baseline_report(
    *,
    latest_target_overdig_depth_sum_m: float | None = 0.0,
    latest_target_positive_residual_depth_sum_m: float | None = 0.374,
    outside_target_removed_depth_sum_delta_m: float | None = 0.429,
) -> dict[str, object]:
    return {
        "status": "present",
        "latest_projection": {
            "status": "present",
            "target_residual_metrics": {
                "target_overdig_depth_sum_m": (
                    latest_target_overdig_depth_sum_m
                ),
                "target_positive_residual_depth_sum_m": (
                    latest_target_positive_residual_depth_sum_m
                ),
            },
        },
        "convergence_projection": {
            "status": "present",
            "summary": {
                "outside_target_removed_depth_sum_delta_m": (
                    outside_target_removed_depth_sum_delta_m
                ),
            },
        },
    }


def _events_by_name(audit: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(event["event_name"]): event
        for event in audit["events"]  # type: ignore[index]
    }


def test_shape_guard_shadow_audit_uses_explicit_thresholds_only() -> None:
    audit = build_shape_guard_shadow_audit(
        _baseline_report(),
        max_target_overdig_depth_sum_m=0.0,
        max_target_positive_residual_depth_sum_m=0.4,
        max_outside_target_removed_depth_delta_m=0.0,
    )

    assert audit["status"] == "present"
    assert audit["schema"] == "terrain_shape_guard_shadow_audit_v1"
    assert audit["source"] == "explicit_target_shape_guard_shadow_audit"
    assert audit["shadow_only"] is True
    assert audit["no_production_decision"] is True
    assert audit["triggered_event_names"] == [
        "depth_budget_exhausted",
        "outside_protected_removed_increased",
    ]
    assert audit["not_evaluated_event_names"] == [
        "low_payload_shape_guard_stop",
    ]
    assert audit["validation_errors"] == []

    events = _events_by_name(audit)
    assert events["overdig_guard_stop"] == {
        "event_name": "overdig_guard_stop",
        "status": "not_triggered",
        "shadow_only": True,
        "reason": "latest_target_overdig_within_explicit_max",
        "evidence": {
            "latest_target_overdig_depth_sum_m": 0.0,
            "max_target_overdig_depth_sum_m": 0.0,
        },
    }
    assert events["depth_budget_exhausted"] == {
        "event_name": "depth_budget_exhausted",
        "status": "triggered",
        "shadow_only": True,
        "reason": "latest_target_positive_residual_at_or_below_explicit_max",
        "evidence": {
            "latest_target_positive_residual_depth_sum_m": 0.374,
            "max_target_positive_residual_depth_sum_m": 0.4,
        },
    }
    assert events["outside_protected_removed_increased"] == {
        "event_name": "outside_protected_removed_increased",
        "status": "triggered",
        "shadow_only": True,
        "reason": "outside_target_removed_delta_exceeds_explicit_max",
        "evidence": {
            "outside_target_removed_depth_sum_delta_m": 0.429,
            "max_outside_target_removed_depth_delta_m": 0.0,
        },
    }
    assert events["low_payload_shape_guard_stop"] == {
        "event_name": "low_payload_shape_guard_stop",
        "status": "not_evaluated",
        "shadow_only": True,
        "reason": "missing_explicit_payload_inputs",
        "evidence": {
            "latest_payload_fraction": None,
            "min_payload_fraction": None,
        },
    }


def test_shape_guard_shadow_audit_does_not_infer_missing_report_fields() -> None:
    audit = build_shape_guard_shadow_audit(
        {
            "status": "partial",
            "latest_projection": {"status": "missing_snapshot"},
            "convergence_projection": {"status": "missing_curve"},
        },
        max_target_overdig_depth_sum_m=0.0,
        max_target_positive_residual_depth_sum_m=0.4,
        max_outside_target_removed_depth_delta_m=0.0,
        latest_payload_fraction=0.8,
        min_payload_fraction=0.5,
    )

    assert audit["status"] == "present"
    assert audit["triggered_event_names"] == []
    assert audit["not_evaluated_event_names"] == [
        "overdig_guard_stop",
        "depth_budget_exhausted",
        "outside_protected_removed_increased",
    ]

    events = _events_by_name(audit)
    assert events["overdig_guard_stop"]["status"] == "not_evaluated"
    assert events["overdig_guard_stop"]["reason"] == (
        "missing_latest_target_overdig_depth_sum_m"
    )
    assert events["depth_budget_exhausted"]["status"] == "not_evaluated"
    assert events["depth_budget_exhausted"]["reason"] == (
        "missing_latest_target_positive_residual_depth_sum_m"
    )
    assert events["outside_protected_removed_increased"]["status"] == (
        "not_evaluated"
    )
    assert events["outside_protected_removed_increased"]["reason"] == (
        "missing_outside_target_removed_depth_sum_delta_m"
    )
    assert events["low_payload_shape_guard_stop"] == {
        "event_name": "low_payload_shape_guard_stop",
        "status": "not_triggered",
        "shadow_only": True,
        "reason": "latest_payload_fraction_at_or_above_explicit_min",
        "evidence": {
            "latest_payload_fraction": 0.8,
            "min_payload_fraction": 0.5,
        },
    }


def test_shape_guard_shadow_audit_validates_explicit_numeric_inputs() -> None:
    audit = build_shape_guard_shadow_audit(
        _baseline_report(),
        max_target_overdig_depth_sum_m=-0.1,
        max_target_positive_residual_depth_sum_m="not-a-number",
        max_outside_target_removed_depth_delta_m=0.0,
        latest_payload_fraction=1.2,
        min_payload_fraction=0.5,
    )

    assert audit["status"] == "invalid_input"
    assert audit["triggered_event_names"] == [
        "outside_protected_removed_increased",
    ]
    assert audit["validation_errors"] == [
        "max_target_overdig_depth_sum_m must be finite and nonnegative",
        "max_target_positive_residual_depth_sum_m must be finite and nonnegative",
        "latest_payload_fraction must be finite and between 0.0 and 1.0",
    ]

    events = _events_by_name(audit)
    assert events["overdig_guard_stop"]["status"] == "invalid_input"
    assert events["overdig_guard_stop"]["reason"] == (
        "invalid_explicit_max_target_overdig_depth_sum_m"
    )
    assert events["depth_budget_exhausted"]["status"] == "invalid_input"
    assert events["depth_budget_exhausted"]["reason"] == (
        "invalid_explicit_max_target_positive_residual_depth_sum_m"
    )
    assert events["low_payload_shape_guard_stop"]["status"] == "invalid_input"
    assert events["low_payload_shape_guard_stop"]["reason"] == (
        "invalid_explicit_payload_inputs"
    )


def test_shape_guard_shadow_audit_reports_all_missing_thresholds_as_not_evaluated() -> None:
    audit = build_shape_guard_shadow_audit(_baseline_report())

    assert audit["status"] == "not_evaluated"
    assert audit["triggered_event_names"] == []
    assert audit["not_evaluated_event_names"] == [
        "low_payload_shape_guard_stop",
        "overdig_guard_stop",
        "depth_budget_exhausted",
        "outside_protected_removed_increased",
    ]
    assert {event["status"] for event in audit["events"]} == {"not_evaluated"}
