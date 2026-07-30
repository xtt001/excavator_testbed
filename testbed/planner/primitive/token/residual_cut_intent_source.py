"""Explicit residual cut-intent runtime source provider."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.token.dig_planning import (
    DigCutPlanTuple,
    ResidualCutIntentPlanProvider,
)

RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA = (
    "residual_cut_intent_runtime_source_v1"
)
RESIDUAL_CUT_INTENT_RUNTIME_SOURCE = (
    "explicit_residual_cut_intent_runtime_source"
)


class ResidualCutIntentPlanSourceError(ValueError):
    """Raised when an explicit residual cut-intent source is missing or invalid."""

    def __init__(
        self,
        message: str,
        *,
        status: str,
        validation_errors: Sequence[str],
    ) -> None:
        self.status = str(status)
        self.validation_errors = list(validation_errors)
        details = "; ".join(self.validation_errors)
        suffix = f": {details}" if details else ""
        super().__init__(f"{message}{suffix}")


@dataclass(frozen=True)
class ExplicitResidualCutIntentPlanSource:
    """Cycle-indexed residual cut-intent runtime plans loaded from one file."""

    path: str
    plans_by_cycle: Mapping[int, DigCutPlanTuple]

    def plan_for_cycle(self, cycle_index: int) -> DigCutPlanTuple:
        try:
            token, raw_fields, source, fallback_reason = self.plans_by_cycle[
                cycle_index
            ]
        except KeyError as exc:
            raise ResidualCutIntentPlanSourceError(
                f"residual_cut_intent source missing plan for cycle_index {cycle_index}",
                status="missing_cycle_plan",
                validation_errors=[
                    f"missing plan for cycle_index {cycle_index}",
                ],
            ) from exc
        return (
            token.copy(),
            dict(raw_fields),
            str(source),
            str(fallback_reason),
        )


def build_residual_cut_intent_plan_provider_from_source_path(
    source_path: Any,
    *,
    cycle_index: Callable[[], int],
) -> ResidualCutIntentPlanProvider | None:
    """Build a runtime provider from an explicit source path, or None if absent."""

    normalized_path = _optional_source_path(source_path)
    if normalized_path is None:
        return None
    source = load_explicit_residual_cut_intent_plan_source(normalized_path)

    def provider(_obs: dict[str, Any]) -> DigCutPlanTuple:
        return source.plan_for_cycle(_current_cycle_index(cycle_index))

    return provider


def load_explicit_residual_cut_intent_plan_source(
    source_path: Any,
) -> ExplicitResidualCutIntentPlanSource:
    """Load and validate a durable residual cut-intent runtime source JSON."""

    normalized_path = _required_source_path(source_path)
    payload = _read_json_mapping(normalized_path)
    validation_errors: list[str] = []

    if payload.get("schema") != RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA:
        validation_errors.append(
            "schema must be residual_cut_intent_runtime_source_v1"
        )
    if payload.get("source") != RESIDUAL_CUT_INTENT_RUNTIME_SOURCE:
        validation_errors.append(
            "source must be explicit_residual_cut_intent_runtime_source"
        )
    if payload.get("status") != "present":
        validation_errors.append("source status must be present")

    raw_plans = payload.get("plans")
    plans_by_cycle: dict[int, DigCutPlanTuple] = {}
    if not _is_sequence(raw_plans):
        validation_errors.append("plans must be a non-empty sequence")
    elif len(raw_plans) == 0:
        validation_errors.append("plans must be a non-empty sequence")
    else:
        for index, raw_plan in enumerate(raw_plans):
            plan, plan_errors = _parse_plan_record(raw_plan, index=index)
            validation_errors.extend(plan_errors)
            if plan is None:
                continue
            cycle, plan_tuple = plan
            if cycle in plans_by_cycle:
                validation_errors.append(
                    f"plans[{index}] cycle_index {cycle} is duplicated"
                )
                continue
            plans_by_cycle[cycle] = plan_tuple

    if validation_errors:
        raise ResidualCutIntentPlanSourceError(
            "invalid residual_cut_intent source",
            status="invalid_source",
            validation_errors=validation_errors,
        )

    return ExplicitResidualCutIntentPlanSource(
        path=normalized_path,
        plans_by_cycle=plans_by_cycle,
    )


def _parse_plan_record(
    raw_plan: Any,
    *,
    index: int,
) -> tuple[tuple[int, DigCutPlanTuple] | None, list[str]]:
    prefix = f"plans[{index}]"
    if not isinstance(raw_plan, Mapping):
        return None, [f"{prefix} must be a mapping"]

    cycle_index = _parse_nonnegative_integer(raw_plan.get("cycle_index"))
    errors: list[str] = []
    if cycle_index is None:
        errors.append(f"{prefix} cycle_index must be a non-negative integer")

    plan_payload = raw_plan.get(
        "plan",
        raw_plan.get("adapter_output", raw_plan.get("dig_cut_plan", raw_plan)),
    )
    if not isinstance(plan_payload, Mapping):
        errors.append(f"{prefix} plan must be a mapping")
        return None, errors
    if plan_payload.get("status") != "present":
        errors.append(f"{prefix} plan status must be present")

    token, token_errors = _parse_token(plan_payload.get("dig_cut_tokens"), prefix=prefix)
    raw_fields, raw_field_errors = _parse_raw_fields(
        plan_payload.get("raw_fields"),
        prefix=prefix,
    )
    errors.extend(token_errors)
    errors.extend(raw_field_errors)

    source_value = plan_payload.get("source", raw_plan.get("source", ""))
    source = str(source_value) if source_value is not None else ""
    if not source:
        errors.append(f"{prefix} source must be non-empty")

    fallback_value = raw_plan.get(
        "fallback_reason",
        plan_payload.get("fallback_reason", ""),
    )
    fallback_reason = str(fallback_value) if fallback_value is not None else ""

    if errors or cycle_index is None or token is None or raw_fields is None:
        return None, errors
    return (cycle_index, (token, raw_fields, source, fallback_reason)), []


def _parse_token(value: Any, *, prefix: str) -> tuple[np.ndarray | None, list[str]]:
    if not _is_sequence(value):
        return None, [f"{prefix} dig_cut_tokens must be a sequence"]
    if len(value) != DIG_CUT_TOKEN_DIM:
        return None, [
            f"{prefix} dig_cut_tokens length must be {DIG_CUT_TOKEN_DIM}"
        ]
    parsed: list[float] = []
    for item in value:
        number = _parse_finite_float(item)
        if number is None:
            return None, [f"{prefix} dig_cut_tokens must be finite numbers"]
        parsed.append(number)
    return np.asarray(parsed, dtype=np.float32), []


def _parse_raw_fields(
    value: Any,
    *,
    prefix: str,
) -> tuple[dict[str, float | int] | None, list[str]]:
    if not isinstance(value, Mapping):
        return None, [f"{prefix} raw_fields must be a mapping"]
    parsed: dict[str, float | int] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            return None, [f"{prefix} raw_fields keys must be strings"]
        number = _parse_finite_float(raw_value)
        if number is None:
            return None, [f"{prefix} raw_fields values must be finite numbers"]
        parsed[key] = number
    if not parsed:
        return None, [f"{prefix} raw_fields must be non-empty"]
    return parsed, []


def _optional_source_path(source_path: Any) -> str | None:
    if source_path is None:
        return None
    if not isinstance(source_path, (str, Path)):
        raise ResidualCutIntentPlanSourceError(
            "invalid residual_cut_intent source path",
            status="invalid_source_path",
            validation_errors=[
                "residual_cut_intent source path must be a path string",
            ],
        )
    normalized = str(source_path).strip()
    return normalized or None


def _required_source_path(source_path: Any) -> str:
    normalized = _optional_source_path(source_path)
    if normalized is None:
        raise ResidualCutIntentPlanSourceError(
            "missing residual_cut_intent source path",
            status="missing_source_path",
            validation_errors=[
                "residual_cut_intent source path must be non-empty",
            ],
        )
    return normalized


def _read_json_mapping(source_path: str) -> Mapping[str, Any]:
    path = Path(source_path)
    if not path.exists():
        raise ResidualCutIntentPlanSourceError(
            "residual_cut_intent source path does not exist",
            status="missing_source_path",
            validation_errors=[f"source path does not exist: {source_path}"],
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResidualCutIntentPlanSourceError(
            "invalid residual_cut_intent source JSON",
            status="invalid_json",
            validation_errors=[f"source JSON decode failed: {exc.msg}"],
        ) from exc
    if not isinstance(payload, Mapping):
        raise ResidualCutIntentPlanSourceError(
            "invalid residual_cut_intent source",
            status="invalid_source",
            validation_errors=["source JSON must be an object"],
        )
    return payload


def _current_cycle_index(cycle_index: Callable[[], int]) -> int:
    try:
        parsed = _parse_nonnegative_integer(cycle_index())
    except Exception as exc:
        raise ResidualCutIntentPlanSourceError(
            "invalid residual_cut_intent source cycle_index",
            status="invalid_cycle_index",
            validation_errors=["cycle_index provider failed"],
        ) from exc
    if parsed is None:
        raise ResidualCutIntentPlanSourceError(
            "invalid residual_cut_intent source cycle_index",
            status="invalid_cycle_index",
            validation_errors=["cycle_index must be a non-negative integer"],
        )
    return parsed


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _parse_finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _parse_nonnegative_integer(value: Any) -> int | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0:
        return None
    integer = int(parsed)
    if not math.isclose(parsed, float(integer), abs_tol=1.0e-9):
        return None
    return integer


__all__ = [
    "RESIDUAL_CUT_INTENT_RUNTIME_SOURCE",
    "RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA",
    "ExplicitResidualCutIntentPlanSource",
    "ResidualCutIntentPlanSourceError",
    "build_residual_cut_intent_plan_provider_from_source_path",
    "load_explicit_residual_cut_intent_plan_source",
]
