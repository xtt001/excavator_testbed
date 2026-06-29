"""Report-side projection of proposal validation into decision traces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from testbed.planner.primitive.decision.validation import (
    DecisionProposalShadowFallbackOutcome,
    DecisionProposalValidationResult,
)
from testbed.planner.primitive.report.decision_trace import (
    DecisionDiagnosticCheck,
    DecisionValidationStatus,
)


@dataclass(frozen=True)
class DecisionValidationTraceProjection:
    """Trace-ready projection of one proposal validation outcome."""

    validation_status: DecisionValidationStatus
    selected_operation: str | None
    fallback_type: str
    reason_codes: tuple[str, ...]
    diagnostic_checks: tuple[DecisionDiagnosticCheck, ...]
    validation_payload: Mapping[str, object]

    def with_backend_payload(
        self,
        backend_payload: Mapping[str, object] | None,
    ) -> dict[str, object]:
        payload = dict(backend_payload or {})
        payload["validation"] = dict(self.validation_payload)
        return payload


def project_validation_result_to_trace(
    validation: DecisionProposalValidationResult,
    *,
    fallback_applied: bool = False,
) -> DecisionValidationTraceProjection:
    """Project a validator result into generic trace metadata and payload."""

    validation_status: DecisionValidationStatus = (
        "accepted" if validation.accepted else "rejected"
    )
    diagnostic_checks = _diagnostic_checks_from_validation(validation)
    reason_codes = tuple(str(reason) for reason in validation.reasons)
    selected_operation = (
        "validator_rejected_fallback"
        if validation_status == "rejected" and fallback_applied
        else None
    )
    fallback_type = (
        "validator_rejected"
        if validation_status == "rejected" and fallback_applied
        else "none"
    )
    return DecisionValidationTraceProjection(
        validation_status=validation_status,
        selected_operation=selected_operation,
        fallback_type=fallback_type,
        reason_codes=reason_codes,
        diagnostic_checks=diagnostic_checks,
        validation_payload={
            "accepted": bool(validation.accepted),
            "status": str(validation.status),
            "fallback_applied": bool(fallback_applied),
            "reasons": list(reason_codes),
            "checks": [check.to_dict() for check in diagnostic_checks],
        },
    )


def project_shadow_fallback_outcome_to_trace(
    outcome: DecisionProposalShadowFallbackOutcome,
) -> DecisionValidationTraceProjection:
    """Project a shadow/eval validator outcome into trace-ready fields."""

    return project_validation_result_to_trace(
        outcome.validation,
        fallback_applied=bool(outcome.fallback_applied),
    )


def _diagnostic_checks_from_validation(
    validation: DecisionProposalValidationResult,
) -> tuple[DecisionDiagnosticCheck, ...]:
    return tuple(
        DecisionDiagnosticCheck(
            name=check.name,
            status=check.status,
            reason=check.reason,
            value=check.value,
        )
        for check in validation.checks
    )


__all__ = [
    "DecisionValidationTraceProjection",
    "project_shadow_fallback_outcome_to_trace",
    "project_validation_result_to_trace",
]
