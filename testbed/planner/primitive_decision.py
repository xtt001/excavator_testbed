"""Typed decision and effect contracts for primitive planner ticks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal


LEGACY_FSM_DECISION_SOURCE = "legacy_fsm_side_effects_applied"

PrimitiveDecisionStatus = Literal["no_change", "skill_switch"]


class PrimitiveDecisionContractError(ValueError):
    """Raised when a decision result violates the effect-boundary contract."""


@dataclass(frozen=True)
class PlannerEffect:
    """Base effect record for legacy outcomes and future requested effects."""

    effect_type: str
    already_applied: bool


@dataclass(frozen=True)
class LegacyDecisionOutcomeEffect(PlannerEffect):
    """Observable outcome emitted by the legacy FSM after it already mutated state."""

    skill_before: str
    skill_after: str
    switch_reason: str


@dataclass(frozen=True)
class RequestedPlannerEffect(PlannerEffect):
    """Ordered semantic mutation request returned by a future pure backend."""

    already_applied: bool = field(default=False, init=False)
    reason: str = ""
    payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "already_applied", False)


@dataclass(frozen=True)
class PrimitiveDecisionResult:
    """Decision result returned to the public tick template."""

    decision_source: str
    status: PrimitiveDecisionStatus
    skill_before: str
    skill_after: str
    switch_reason: str
    effects: tuple[PlannerEffect, ...]
    side_effects_applied: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", tuple(self.effects))

    @classmethod
    def from_legacy_fsm_outcome(
        cls,
        *,
        skill_before: str,
        skill_after: str,
        switch_reason: str,
    ) -> "PrimitiveDecisionResult":
        status: PrimitiveDecisionStatus = (
            "skill_switch" if skill_after != skill_before else "no_change"
        )
        effects: tuple[PlannerEffect, ...]
        if skill_after != skill_before:
            effects = (
                LegacyDecisionOutcomeEffect(
                    effect_type="legacy_decision_outcome",
                    already_applied=True,
                    skill_before=str(skill_before),
                    skill_after=str(skill_after),
                    switch_reason=str(switch_reason),
                ),
            )
        else:
            effects = ()
        return cls(
            decision_source=LEGACY_FSM_DECISION_SOURCE,
            status=status,
            skill_before=str(skill_before),
            skill_after=str(skill_after),
            switch_reason=str(switch_reason),
            effects=effects,
            side_effects_applied=True,
        )

    @classmethod
    def from_requested_effects(
        cls,
        *,
        decision_source: str,
        status: PrimitiveDecisionStatus,
        skill_before: str,
        skill_after: str,
        switch_reason: str,
        effects: tuple[RequestedPlannerEffect, ...],
        validate: bool = True,
    ) -> "PrimitiveDecisionResult":
        result = cls(
            decision_source=str(decision_source),
            status=status,
            skill_before=str(skill_before),
            skill_after=str(skill_after),
            switch_reason=str(switch_reason),
            effects=tuple(effects),
            side_effects_applied=False,
        )
        if validate:
            validate_decision_effect_contract(result)
        return result


_FORBIDDEN_EFFECT_TYPES = {
    "setplannerattr",
    "set_planner_attr",
    "callplannermethod",
    "call_planner_method",
    "set_attr",
    "call_method",
}

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


def validate_decision_effect_contract(result: PrimitiveDecisionResult) -> None:
    """Validate the transitional legacy/requested-effect split."""

    if result.side_effects_applied:
        for effect in result.effects:
            if not effect.already_applied:
                raise PrimitiveDecisionContractError(
                    "already-applied decision result cannot contain requested effects"
                )
        return

    for effect in result.effects:
        if effect.already_applied or not isinstance(effect, RequestedPlannerEffect):
            raise PrimitiveDecisionContractError(
                "requested-effect result cannot contain already-applied effects"
            )
        _validate_requested_effect_shape(effect)


def _validate_requested_effect_shape(effect: RequestedPlannerEffect) -> None:
    effect_type = str(effect.effect_type)
    normalized_type = effect_type.strip().lower()
    if normalized_type in _FORBIDDEN_EFFECT_TYPES:
        raise PrimitiveDecisionContractError(
            f"forbidden planner effect type: {effect_type}"
        )
    if "planner_attr" in normalized_type or "planner_method" in normalized_type:
        raise PrimitiveDecisionContractError(
            f"forbidden planner effect type: {effect_type}"
        )
    if callable(effect):
        raise PrimitiveDecisionContractError("effect object must not be callable")
    if effect.payload is not None:
        _validate_payload_value(effect.payload, path="payload")


def _validate_payload_value(value: object, *, path: str) -> None:
    if callable(value):
        raise PrimitiveDecisionContractError(f"callable effect payload at {path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text.strip().lower() in _FORBIDDEN_PAYLOAD_KEYS:
                raise PrimitiveDecisionContractError(
                    f"forbidden effect payload key at {path}: {key_text}"
                )
            _validate_payload_value(item, path=f"{path}.{key_text}")
        return
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            _validate_payload_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, item in enumerate(value):
            _validate_payload_value(item, path=f"{path}[{index}]")
        return
    raise PrimitiveDecisionContractError(
        f"unsupported effect payload object at {path}: {type(value).__name__}"
    )
