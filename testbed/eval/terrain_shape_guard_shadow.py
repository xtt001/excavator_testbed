"""Shape-guard shadow-audit event contract for terrain residual diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

SCHEMA = "terrain_shape_guard_shadow_audit_v1"
SOURCE = "explicit_target_shape_guard_shadow_audit"
EVENT_NAMES = (
    "low_payload_shape_guard_stop",
    "overdig_guard_stop",
    "depth_budget_exhausted",
    "outside_protected_removed_increased",
)


def build_shape_guard_shadow_audit(
    baseline_report: Mapping[str, Any],
    *,
    max_target_overdig_depth_sum_m: Any = None,
    max_target_positive_residual_depth_sum_m: Any = None,
    max_outside_target_removed_depth_delta_m: Any = None,
    latest_payload_fraction: Any = None,
    min_payload_fraction: Any = None,
) -> dict[str, Any]:
    """Build diagnostic-only shape-guard events from an explicit target report."""

    validation_errors: list[str] = []
    parsed_max_overdig = _optional_nonnegative_float(
        max_target_overdig_depth_sum_m,
        field_name="max_target_overdig_depth_sum_m",
        validation_errors=validation_errors,
    )
    parsed_max_positive_residual = _optional_nonnegative_float(
        max_target_positive_residual_depth_sum_m,
        field_name="max_target_positive_residual_depth_sum_m",
        validation_errors=validation_errors,
    )
    parsed_max_outside_delta = _optional_nonnegative_float(
        max_outside_target_removed_depth_delta_m,
        field_name="max_outside_target_removed_depth_delta_m",
        validation_errors=validation_errors,
    )
    parsed_latest_payload_fraction = _optional_fraction_float(
        latest_payload_fraction,
        field_name="latest_payload_fraction",
        validation_errors=validation_errors,
    )
    parsed_min_payload_fraction = _optional_fraction_float(
        min_payload_fraction,
        field_name="min_payload_fraction",
        validation_errors=validation_errors,
    )

    latest_metrics = _latest_target_metrics(baseline_report)
    convergence_summary = _convergence_summary(baseline_report)
    events = [
        _payload_event(
            latest_payload_fraction=parsed_latest_payload_fraction,
            min_payload_fraction=parsed_min_payload_fraction,
        ),
        _overdig_event(
            latest_target_overdig_depth_sum_m=_mapping_float(
                latest_metrics,
                "target_overdig_depth_sum_m",
            ),
            max_target_overdig_depth_sum_m=parsed_max_overdig,
        ),
        _depth_budget_event(
            latest_target_positive_residual_depth_sum_m=_mapping_float(
                latest_metrics,
                "target_positive_residual_depth_sum_m",
            ),
            max_target_positive_residual_depth_sum_m=(
                parsed_max_positive_residual
            ),
        ),
        _outside_protected_event(
            outside_target_removed_depth_sum_delta_m=_mapping_float(
                convergence_summary,
                "outside_target_removed_depth_sum_delta_m",
            ),
            max_outside_target_removed_depth_delta_m=parsed_max_outside_delta,
        ),
    ]
    triggered_event_names = [
        str(event["event_name"])
        for event in events
        if event["status"] == "triggered"
    ]
    not_evaluated_event_names = [
        str(event["event_name"])
        for event in events
        if event["status"] == "not_evaluated"
    ]
    return {
        "status": _audit_status(events, validation_errors),
        "schema": SCHEMA,
        "source": SOURCE,
        "shadow_only": True,
        "semantics": "diagnostic_shadow_only",
        "no_production_decision": True,
        "events": events,
        "triggered_event_names": triggered_event_names,
        "not_evaluated_event_names": not_evaluated_event_names,
        "validation_errors": validation_errors,
    }


def _payload_event(
    *,
    latest_payload_fraction: tuple[float | None, str],
    min_payload_fraction: tuple[float | None, str],
) -> dict[str, Any]:
    latest_value, latest_status = latest_payload_fraction
    min_value, min_status = min_payload_fraction
    if latest_status == "invalid" or min_status == "invalid":
        return _event(
            "low_payload_shape_guard_stop",
            status="invalid_input",
            reason="invalid_explicit_payload_inputs",
            evidence={
                "latest_payload_fraction": latest_value,
                "min_payload_fraction": min_value,
            },
        )
    if latest_status == "missing" or min_status == "missing":
        return _event(
            "low_payload_shape_guard_stop",
            status="not_evaluated",
            reason="missing_explicit_payload_inputs",
            evidence={
                "latest_payload_fraction": latest_value,
                "min_payload_fraction": min_value,
            },
        )
    if latest_value is not None and min_value is not None and latest_value < min_value:
        return _event(
            "low_payload_shape_guard_stop",
            status="triggered",
            reason="latest_payload_fraction_below_explicit_min",
            evidence={
                "latest_payload_fraction": latest_value,
                "min_payload_fraction": min_value,
            },
        )
    return _event(
        "low_payload_shape_guard_stop",
        status="not_triggered",
        reason="latest_payload_fraction_at_or_above_explicit_min",
        evidence={
            "latest_payload_fraction": latest_value,
            "min_payload_fraction": min_value,
        },
    )


def _overdig_event(
    *,
    latest_target_overdig_depth_sum_m: float | None,
    max_target_overdig_depth_sum_m: tuple[float | None, str],
) -> dict[str, Any]:
    max_value, max_status = max_target_overdig_depth_sum_m
    if max_status == "invalid":
        return _event(
            "overdig_guard_stop",
            status="invalid_input",
            reason="invalid_explicit_max_target_overdig_depth_sum_m",
            evidence={
                "latest_target_overdig_depth_sum_m": (
                    latest_target_overdig_depth_sum_m
                ),
                "max_target_overdig_depth_sum_m": max_value,
            },
        )
    if max_status == "missing":
        return _event(
            "overdig_guard_stop",
            status="not_evaluated",
            reason="missing_explicit_max_target_overdig_depth_sum_m",
            evidence={
                "latest_target_overdig_depth_sum_m": (
                    latest_target_overdig_depth_sum_m
                ),
                "max_target_overdig_depth_sum_m": max_value,
            },
        )
    if latest_target_overdig_depth_sum_m is None:
        return _event(
            "overdig_guard_stop",
            status="not_evaluated",
            reason="missing_latest_target_overdig_depth_sum_m",
            evidence={
                "latest_target_overdig_depth_sum_m": None,
                "max_target_overdig_depth_sum_m": max_value,
            },
        )
    if max_value is not None and latest_target_overdig_depth_sum_m > max_value:
        return _event(
            "overdig_guard_stop",
            status="triggered",
            reason="latest_target_overdig_exceeds_explicit_max",
            evidence={
                "latest_target_overdig_depth_sum_m": (
                    latest_target_overdig_depth_sum_m
                ),
                "max_target_overdig_depth_sum_m": max_value,
            },
        )
    return _event(
        "overdig_guard_stop",
        status="not_triggered",
        reason="latest_target_overdig_within_explicit_max",
        evidence={
            "latest_target_overdig_depth_sum_m": latest_target_overdig_depth_sum_m,
            "max_target_overdig_depth_sum_m": max_value,
        },
    )


def _depth_budget_event(
    *,
    latest_target_positive_residual_depth_sum_m: float | None,
    max_target_positive_residual_depth_sum_m: tuple[float | None, str],
) -> dict[str, Any]:
    max_value, max_status = max_target_positive_residual_depth_sum_m
    if max_status == "invalid":
        return _event(
            "depth_budget_exhausted",
            status="invalid_input",
            reason="invalid_explicit_max_target_positive_residual_depth_sum_m",
            evidence={
                "latest_target_positive_residual_depth_sum_m": (
                    latest_target_positive_residual_depth_sum_m
                ),
                "max_target_positive_residual_depth_sum_m": max_value,
            },
        )
    if max_status == "missing":
        return _event(
            "depth_budget_exhausted",
            status="not_evaluated",
            reason="missing_explicit_max_target_positive_residual_depth_sum_m",
            evidence={
                "latest_target_positive_residual_depth_sum_m": (
                    latest_target_positive_residual_depth_sum_m
                ),
                "max_target_positive_residual_depth_sum_m": max_value,
            },
        )
    if latest_target_positive_residual_depth_sum_m is None:
        return _event(
            "depth_budget_exhausted",
            status="not_evaluated",
            reason="missing_latest_target_positive_residual_depth_sum_m",
            evidence={
                "latest_target_positive_residual_depth_sum_m": None,
                "max_target_positive_residual_depth_sum_m": max_value,
            },
        )
    if (
        max_value is not None
        and latest_target_positive_residual_depth_sum_m <= max_value
    ):
        return _event(
            "depth_budget_exhausted",
            status="triggered",
            reason="latest_target_positive_residual_at_or_below_explicit_max",
            evidence={
                "latest_target_positive_residual_depth_sum_m": (
                    latest_target_positive_residual_depth_sum_m
                ),
                "max_target_positive_residual_depth_sum_m": max_value,
            },
        )
    return _event(
        "depth_budget_exhausted",
        status="not_triggered",
        reason="latest_target_positive_residual_above_explicit_max",
        evidence={
            "latest_target_positive_residual_depth_sum_m": (
                latest_target_positive_residual_depth_sum_m
            ),
            "max_target_positive_residual_depth_sum_m": max_value,
        },
    )


def _outside_protected_event(
    *,
    outside_target_removed_depth_sum_delta_m: float | None,
    max_outside_target_removed_depth_delta_m: tuple[float | None, str],
) -> dict[str, Any]:
    max_value, max_status = max_outside_target_removed_depth_delta_m
    if max_status == "invalid":
        return _event(
            "outside_protected_removed_increased",
            status="invalid_input",
            reason="invalid_explicit_max_outside_target_removed_depth_delta_m",
            evidence={
                "outside_target_removed_depth_sum_delta_m": (
                    outside_target_removed_depth_sum_delta_m
                ),
                "max_outside_target_removed_depth_delta_m": max_value,
            },
        )
    if max_status == "missing":
        return _event(
            "outside_protected_removed_increased",
            status="not_evaluated",
            reason="missing_explicit_max_outside_target_removed_depth_delta_m",
            evidence={
                "outside_target_removed_depth_sum_delta_m": (
                    outside_target_removed_depth_sum_delta_m
                ),
                "max_outside_target_removed_depth_delta_m": max_value,
            },
        )
    if outside_target_removed_depth_sum_delta_m is None:
        return _event(
            "outside_protected_removed_increased",
            status="not_evaluated",
            reason="missing_outside_target_removed_depth_sum_delta_m",
            evidence={
                "outside_target_removed_depth_sum_delta_m": None,
                "max_outside_target_removed_depth_delta_m": max_value,
            },
        )
    if (
        max_value is not None
        and outside_target_removed_depth_sum_delta_m > max_value
    ):
        return _event(
            "outside_protected_removed_increased",
            status="triggered",
            reason="outside_target_removed_delta_exceeds_explicit_max",
            evidence={
                "outside_target_removed_depth_sum_delta_m": (
                    outside_target_removed_depth_sum_delta_m
                ),
                "max_outside_target_removed_depth_delta_m": max_value,
            },
        )
    return _event(
        "outside_protected_removed_increased",
        status="not_triggered",
        reason="outside_target_removed_delta_within_explicit_max",
        evidence={
            "outside_target_removed_depth_sum_delta_m": (
                outside_target_removed_depth_sum_delta_m
            ),
            "max_outside_target_removed_depth_delta_m": max_value,
        },
    )


def _event(
    event_name: str,
    *,
    status: str,
    reason: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_name": event_name,
        "status": status,
        "shadow_only": True,
        "reason": reason,
        "evidence": evidence,
    }


def _audit_status(
    events: list[dict[str, Any]],
    validation_errors: list[str],
) -> str:
    if validation_errors:
        return "invalid_input"
    if all(event["status"] == "not_evaluated" for event in events):
        return "not_evaluated"
    return "present"


def _latest_target_metrics(
    baseline_report: Mapping[str, Any],
) -> Mapping[str, Any]:
    latest_projection = baseline_report.get("latest_projection")
    if not isinstance(latest_projection, Mapping):
        return {}
    target_residual_metrics = latest_projection.get("target_residual_metrics")
    if not isinstance(target_residual_metrics, Mapping):
        return {}
    return target_residual_metrics


def _convergence_summary(
    baseline_report: Mapping[str, Any],
) -> Mapping[str, Any]:
    convergence_projection = baseline_report.get("convergence_projection")
    if not isinstance(convergence_projection, Mapping):
        return {}
    summary = convergence_projection.get("summary")
    if not isinstance(summary, Mapping):
        return {}
    return summary


def _mapping_float(mapping: Mapping[str, Any], field_name: str) -> float | None:
    return _finite_float(mapping.get(field_name))


def _optional_nonnegative_float(
    value: Any,
    *,
    field_name: str,
    validation_errors: list[str],
) -> tuple[float | None, str]:
    if value is None:
        return None, "missing"
    parsed = _finite_float(value)
    if parsed is None or parsed < 0.0:
        validation_errors.append(f"{field_name} must be finite and nonnegative")
        return None, "invalid"
    return _metric_float(parsed), "present"


def _optional_fraction_float(
    value: Any,
    *,
    field_name: str,
    validation_errors: list[str],
) -> tuple[float | None, str]:
    if value is None:
        return None, "missing"
    parsed = _finite_float(value)
    if parsed is None or parsed < 0.0 or parsed > 1.0:
        validation_errors.append(
            f"{field_name} must be finite and between 0.0 and 1.0"
        )
        return None, "invalid"
    return _metric_float(parsed), "present"


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


__all__ = ["build_shape_guard_shadow_audit"]
