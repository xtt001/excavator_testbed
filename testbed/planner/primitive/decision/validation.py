"""Strict validation for primitive decision backend proposals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from testbed.planner.primitive.decision.contracts import (
    CompleteCoverageDigEffect,
    CompleteCoverageDumpEffect,
    CompleteReturnTransitionEffect,
    IncrementDigBadReplanCountEffect,
    IncrementDigExitGuardReplanCountEffect,
    LegacyDecisionOutcomeEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    RejectActiveCoverageCorridorEffect,
    ReplanOrRestartPreDigAlignEffect,
    RequestedPlannerEffect,
    RestartAfterFailedDigEffect,
    RestartDigWithNewCutEffect,
    SetDumpDoneHoldCountEffect,
    SetDumpReadyHoldCountEffect,
    SetDumpStartDepositedMassFromObservationEffect,
    SetReturnOrDirectHandoffEffect,
    SwitchSkillEffect,
    SwitchToNextSkillAfterReturnEffect,
    validate_decision_effect_contract,
)


DecisionProposalValidationStatus = Literal["accepted", "rejected"]
DecisionProposalValidationCheckStatus = Literal["pass", "fail", "skipped", "unknown"]

_SUPPORTED_REQUESTED_EFFECT_CLASSES = (
    SwitchSkillEffect,
    MarkReturnNextDigEventSeenEffect,
    CompleteReturnTransitionEffect,
    SwitchToNextSkillAfterReturnEffect,
    IncrementDigExitGuardReplanCountEffect,
    IncrementDigBadReplanCountEffect,
    RejectActiveCoverageCorridorEffect,
    RestartAfterFailedDigEffect,
    RestartDigWithNewCutEffect,
    ReplanOrRestartPreDigAlignEffect,
    CompleteCoverageDigEffect,
    SetDumpReadyHoldCountEffect,
    SetDumpStartDepositedMassFromObservationEffect,
    SetDumpDoneHoldCountEffect,
    CompleteCoverageDumpEffect,
    SetReturnOrDirectHandoffEffect,
)

_LEGACY_BACKEND_NAMES = {"legacy_fsm"}
VALIDATOR_REJECTED_SHADOW_FALLBACK_DECISION_SOURCE = (
    "validator_rejected_shadow_fallback"
)
VALIDATOR_REJECTED_REASON_CODE = "validator_rejected"
_FORBIDDEN_PAYLOAD_KEYS = {
    "self",
    "planner",
    "callback",
    "callable",
    "method",
    "method_name",
    "attribute",
    "attribute_name",
    "attr",
}


@dataclass(frozen=True)
class DecisionProposalValidationCheck:
    """One backend-neutral proposal validation check."""

    name: str
    status: DecisionProposalValidationCheckStatus
    reason: str = ""
    value: object | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": str(self.name),
            "status": str(self.status),
            "reason": str(self.reason),
            "value": self.value,
        }


@dataclass(frozen=True)
class DecisionProposalValidationResult:
    """Strict-mode validation summary for one decision proposal."""

    accepted: bool
    status: DecisionProposalValidationStatus
    checks: tuple[DecisionProposalValidationCheck, ...]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionProposalShadowFallbackOutcome:
    """Eval/shadow proposal outcome after optional validator fallback."""

    result: PrimitiveDecisionResult
    validation: DecisionProposalValidationResult
    fallback_applied: bool


class DecisionProposalValidator:
    """Validate proposed primitive decisions before effect application."""

    @staticmethod
    def validate(
        *,
        result: PrimitiveDecisionResult,
        backend_name: str,
        backend_kind: str,
        expected_skill_before: str | None = None,
        backend_payload: Mapping[str, object] | None = None,
    ) -> DecisionProposalValidationResult:
        del backend_payload
        backend_name_text = str(backend_name).strip()
        backend_kind_text = str(backend_kind).strip()

        _validate_result_contract(
            result=result,
            backend_name=backend_name_text,
            backend_kind=backend_kind_text,
        )
        _validate_effect_payloads_safe(result.effects)
        validate_decision_effect_contract(result)
        _validate_supported_effect_classes(result.effects)
        _validate_context_consistency(
            result=result,
            expected_skill_before=expected_skill_before,
        )

        return DecisionProposalValidationResult(
            accepted=True,
            status="accepted",
            reasons=(),
            checks=(
                DecisionProposalValidationCheck(
                    name="proposal_result_contract_valid",
                    status="pass",
                    value={
                        "decision_source": str(result.decision_source),
                        "decision_status": str(result.status),
                        "side_effects_applied": bool(result.side_effects_applied),
                    },
                ),
                DecisionProposalValidationCheck(
                    name="proposal_effect_types_supported",
                    status="pass",
                    value={
                        "effect_types": [
                            str(effect.effect_type) for effect in result.effects
                        ],
                    },
                ),
                DecisionProposalValidationCheck(
                    name="proposal_effect_payload_safe",
                    status="pass",
                    value={"effect_count": len(result.effects)},
                ),
                DecisionProposalValidationCheck(
                    name="proposal_context_consistent",
                    status="pass",
                    value={
                        "expected_skill_before": expected_skill_before,
                        "skill_before": str(result.skill_before),
                    },
                ),
            ),
        )

    @staticmethod
    def validate_with_shadow_fallback(
        *,
        result: PrimitiveDecisionResult,
        backend_name: str,
        backend_kind: str,
        expected_skill_before: str | None = None,
        backend_payload: Mapping[str, object] | None = None,
    ) -> DecisionProposalShadowFallbackOutcome:
        backend_name_text = str(backend_name).strip()
        backend_kind_text = str(backend_kind).strip()
        try:
            validation = DecisionProposalValidator.validate(
                result=result,
                backend_name=backend_name_text,
                backend_kind=backend_kind_text,
                expected_skill_before=expected_skill_before,
                backend_payload=backend_payload,
            )
        except PrimitiveDecisionContractError as exc:
            rejection_reason = str(exc)
            fallback_skill = _shadow_fallback_skill(
                result=result,
                expected_skill_before=expected_skill_before,
            )
            return DecisionProposalShadowFallbackOutcome(
                result=PrimitiveDecisionResult.from_requested_effects(
                    decision_source=(
                        VALIDATOR_REJECTED_SHADOW_FALLBACK_DECISION_SOURCE
                    ),
                    status="no_change",
                    skill_before=fallback_skill,
                    skill_after=fallback_skill,
                    switch_reason="",
                    effects=(),
                ),
                validation=DecisionProposalValidationResult(
                    accepted=False,
                    status="rejected",
                    reasons=(VALIDATOR_REJECTED_REASON_CODE, rejection_reason),
                    checks=(
                        DecisionProposalValidationCheck(
                            name="proposal_shadow_fallback_applied",
                            status="fail",
                            reason=rejection_reason,
                            value={
                                "backend_kind": backend_kind_text,
                                "backend_name": backend_name_text,
                                "fallback_skill": fallback_skill,
                                "rejected_decision_source": str(
                                    result.decision_source
                                ),
                            },
                        ),
                    ),
                ),
                fallback_applied=True,
            )

        return DecisionProposalShadowFallbackOutcome(
            result=result,
            validation=validation,
            fallback_applied=False,
        )


def _validate_result_contract(
    *,
    result: PrimitiveDecisionResult,
    backend_name: str,
    backend_kind: str,
) -> None:
    if not str(result.decision_source).strip():
        raise PrimitiveDecisionContractError("proposal requires decision_source")
    status = str(result.status)
    if status not in {"no_change", "skill_switch"}:
        raise PrimitiveDecisionContractError(
            f"unsupported proposal decision status: {status!r}"
        )
    if not str(result.skill_before).strip():
        raise PrimitiveDecisionContractError("proposal requires skill_before")
    if status == "no_change":
        if str(result.skill_before) != str(result.skill_after):
            raise PrimitiveDecisionContractError(
                "no-change proposal must preserve skill_before and skill_after"
            )
        if str(result.switch_reason).strip():
            raise PrimitiveDecisionContractError(
                "no-change proposal must not carry switch_reason"
            )
    if status == "skill_switch":
        if not str(result.skill_after).strip():
            raise PrimitiveDecisionContractError(
                "skill-switch proposal requires skill_after"
            )
        if not str(result.switch_reason).strip():
            raise PrimitiveDecisionContractError(
                "skill-switch proposal requires switch_reason"
            )
    if result.side_effects_applied and not _is_legacy_backend(
        backend_name=backend_name,
        backend_kind=backend_kind,
    ):
        raise PrimitiveDecisionContractError(
            "already-applied proposal is only valid for legacy_fsm backend"
        )
    if result.side_effects_applied:
        for effect in result.effects:
            if not isinstance(effect, LegacyDecisionOutcomeEffect):
                raise PrimitiveDecisionContractError(
                    "legacy already-applied proposal requires legacy outcome effects"
                )


def _validate_supported_effect_classes(
    effects: tuple[object, ...],
) -> None:
    for effect in effects:
        if isinstance(effect, LegacyDecisionOutcomeEffect):
            continue
        if not isinstance(effect, _SUPPORTED_REQUESTED_EFFECT_CLASSES):
            effect_name = str(getattr(effect, "effect_type", type(effect).__name__))
            raise PrimitiveDecisionContractError(
                f"unsupported requested effect class for strict validation: "
                f"{effect_name}"
            )


def _validate_context_consistency(
    *,
    result: PrimitiveDecisionResult,
    expected_skill_before: str | None,
) -> None:
    if expected_skill_before is None:
        return
    expected = str(expected_skill_before)
    actual = str(result.skill_before)
    if expected != actual:
        raise PrimitiveDecisionContractError(
            "proposal skill_before mismatch: "
            f"expected {expected!r}, received {actual!r}"
        )


def _validate_effect_payloads_safe(
    effects: tuple[object, ...],
) -> None:
    for effect_index, effect in enumerate(effects):
        if isinstance(effect, RequestedPlannerEffect):
            payload = effect.payload
            if payload is not None:
                _validate_payload_safe(payload, path=f"effects[{effect_index}].payload")


def _validate_payload_safe(value: object, *, path: str) -> None:
    if callable(value):
        raise PrimitiveDecisionContractError(f"callable effect payload at {path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            _validate_payload_safe(item, path=f"{path}.{key_text}")
            if key_text.strip().lower() in _FORBIDDEN_PAYLOAD_KEYS:
                raise PrimitiveDecisionContractError(
                    f"forbidden effect payload key at {path}: {key_text}"
                )
        return
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            _validate_payload_safe(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _validate_payload_safe(item, path=f"{path}[{index}]")
        return
    raise PrimitiveDecisionContractError(
        f"unsupported effect payload object at {path}: {type(value).__name__}"
    )


def _is_legacy_backend(*, backend_name: str, backend_kind: str) -> bool:
    return (
        str(backend_name).strip().lower() in _LEGACY_BACKEND_NAMES
        or str(backend_kind).strip().lower() in _LEGACY_BACKEND_NAMES
    )


def _shadow_fallback_skill(
    *,
    result: PrimitiveDecisionResult,
    expected_skill_before: str | None,
) -> str:
    if expected_skill_before is not None:
        expected = str(expected_skill_before).strip()
        if expected:
            return expected
    skill_before = str(result.skill_before).strip()
    if skill_before:
        return skill_before
    return "unknown"


__all__ = [
    "DecisionProposalShadowFallbackOutcome",
    "DecisionProposalValidationCheck",
    "DecisionProposalValidationCheckStatus",
    "DecisionProposalValidationResult",
    "DecisionProposalValidationStatus",
    "DecisionProposalValidator",
    "VALIDATOR_REJECTED_REASON_CODE",
    "VALIDATOR_REJECTED_SHADOW_FALLBACK_DECISION_SOURCE",
]
