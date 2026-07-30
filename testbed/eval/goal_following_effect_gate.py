"""Fail-closed support and calibration gate for planned-cut effects."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MINIMUM_POSITIVE_SAMPLES = 20
MINIMUM_NEGATIVE_SAMPLES = 20
MINIMUM_RESET_GROUPS = 3
CALIBRATION_STAGE_ORDER = (
    "planned_to_executed",
    "executed_to_effect",
)
_SPLITS = frozenset(("train", "calibration", "evaluation"))


@dataclass(frozen=True)
class CalibrationInterval:
    """A calibrated residual interval for one ordered model stage."""

    lower: float
    upper: float
    coverage_level: float
    calibrated: bool


@dataclass(frozen=True)
class EffectCalibrationSample:
    """One retained controlled-execution sample, including failures."""

    sample_id: str
    capability_class: str
    reset_group_id: str
    split: str
    outcome: str
    failed: bool
    planned_cut: Mapping[str, Any]
    executed_cut: Mapping[str, Any]
    effect: Mapping[str, Any]


@dataclass(frozen=True)
class EffectCalibrationEvidence:
    """Lineage and intervals emitted by the two ordered calibration stages."""

    capability_class: str
    retained_sample_ids: tuple[str, ...]
    stage_order: tuple[str, ...]
    planned_to_executed_interval: CalibrationInterval | None
    executed_to_effect_interval: CalibrationInterval | None


@dataclass(frozen=True)
class CapabilitySupportResult:
    capability_class: str
    passed: bool
    positive_count: int
    negative_count: int
    failed_negative_count: int
    reset_group_count: int
    retained_sample_count: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EffectCalibrationGateResult:
    passed: bool
    reasons: tuple[str, ...]
    capabilities: tuple[CapabilitySupportResult, ...]


def evaluate_effect_calibration_gate(
    *,
    samples: Sequence[EffectCalibrationSample],
    evidence: Sequence[EffectCalibrationEvidence],
) -> EffectCalibrationGateResult:
    """Validate support, reset isolation, sample retention, and intervals.

    This module evaluates model evidence; it deliberately does not choose a
    fixed expert target or fit a planner-side corrective threshold.
    """

    reasons: list[str] = []
    sample_ids: set[str] = set()
    reset_split_owner: dict[str, str] = {}
    samples_by_capability: dict[str, list[EffectCalibrationSample]] = {}
    for sample in samples:
        capability = sample.capability_class.strip()
        if not capability:
            _append_once(reasons, "capability_class_missing")
            continue
        if not sample.sample_id.strip():
            _append_once(reasons, f"{capability}:sample_id_missing")
        elif sample.sample_id in sample_ids:
            _append_once(
                reasons,
                f"{capability}:duplicate_sample_id:{sample.sample_id}",
            )
        sample_ids.add(sample.sample_id)
        if sample.split not in _SPLITS:
            _append_once(reasons, f"{capability}:split_invalid")
        if sample.outcome not in {"positive", "negative"}:
            _append_once(reasons, f"{capability}:outcome_invalid")
        if type(sample.failed) is not bool:
            _append_once(reasons, f"{capability}:failed_type_invalid")
        elif sample.failed and sample.outcome != "negative":
            _append_once(
                reasons,
                f"{capability}:failed_sample_must_be_negative",
            )
        if not sample.reset_group_id.strip():
            _append_once(reasons, f"{capability}:reset_group_id_missing")
        previous_split = reset_split_owner.setdefault(
            sample.reset_group_id,
            sample.split,
        )
        if previous_split != sample.split:
            _append_once(
                reasons,
                f"reset_group_split_leakage:{sample.reset_group_id}",
            )
        for label, payload in (
            ("planned_cut", sample.planned_cut),
            ("executed_cut", sample.executed_cut),
            ("effect", sample.effect),
        ):
            if not isinstance(payload, Mapping):
                _append_once(
                    reasons,
                    f"{capability}:{label}_mapping_invalid",
                )
                continue
            forbidden = _find_forbidden_field(payload)
            if forbidden is not None:
                _append_once(
                    reasons,
                    f"{capability}:forbidden_field:{forbidden}",
                )
        samples_by_capability.setdefault(capability, []).append(sample)
    if not samples_by_capability:
        _append_once(reasons, "sample_inventory_empty")

    evidence_by_capability: dict[str, EffectCalibrationEvidence] = {}
    for item in evidence:
        if item.capability_class in evidence_by_capability:
            _append_once(
                reasons,
                f"{item.capability_class}:duplicate_calibration_evidence",
            )
        evidence_by_capability[item.capability_class] = item
    for capability in sorted(
        set(evidence_by_capability) - set(samples_by_capability)
    ):
        _append_once(reasons, f"{capability}:samples_missing")

    capability_results: list[CapabilitySupportResult] = []
    for capability in sorted(samples_by_capability):
        capability_samples = samples_by_capability[capability]
        capability_reasons: list[str] = []
        positives = sum(
            sample.outcome == "positive" for sample in capability_samples
        )
        negatives = sum(
            sample.outcome == "negative" for sample in capability_samples
        )
        failed_negatives = sum(
            sample.failed is True and sample.outcome == "negative"
            for sample in capability_samples
        )
        reset_groups = {
            sample.reset_group_id for sample in capability_samples
        }
        split_inventory = {sample.split for sample in capability_samples}
        if positives < MINIMUM_POSITIVE_SAMPLES:
            capability_reasons.append(
                f"{capability}:positive_support_below_20"
            )
        if negatives < MINIMUM_NEGATIVE_SAMPLES:
            capability_reasons.append(
                f"{capability}:negative_support_below_20"
            )
        if len(reset_groups) < MINIMUM_RESET_GROUPS:
            capability_reasons.append(
                f"{capability}:reset_group_support_below_3"
            )
        for split in sorted(_SPLITS - split_inventory):
            capability_reasons.append(
                f"{capability}:{split}_split_missing"
            )

        model_evidence = evidence_by_capability.get(capability)
        if model_evidence is None:
            capability_reasons.append(
                f"{capability}:calibration_evidence_missing"
            )
        else:
            if model_evidence.stage_order != CALIBRATION_STAGE_ORDER:
                capability_reasons.append(
                    f"{capability}:calibration_stage_order_invalid"
                )
            expected_ids = {
                sample.sample_id for sample in capability_samples
            }
            retained_ids = set(model_evidence.retained_sample_ids)
            if (
                retained_ids != expected_ids
                or len(retained_ids)
                != len(model_evidence.retained_sample_ids)
            ):
                capability_reasons.append(
                    f"{capability}:sample_retention_mismatch"
                )
            _validate_interval(
                capability_reasons,
                capability=capability,
                stage="planned_to_executed",
                interval=model_evidence.planned_to_executed_interval,
            )
            _validate_interval(
                capability_reasons,
                capability=capability,
                stage="executed_to_effect",
                interval=model_evidence.executed_to_effect_interval,
            )
        for reason in capability_reasons:
            _append_once(reasons, reason)
        capability_results.append(
            CapabilitySupportResult(
                capability_class=capability,
                passed=not capability_reasons,
                positive_count=positives,
                negative_count=negatives,
                failed_negative_count=failed_negatives,
                reset_group_count=len(reset_groups),
                retained_sample_count=(
                    0
                    if model_evidence is None
                    else len(model_evidence.retained_sample_ids)
                ),
                reasons=tuple(capability_reasons),
            )
        )
    return EffectCalibrationGateResult(
        passed=not reasons,
        reasons=tuple(reasons),
        capabilities=tuple(capability_results),
    )


def _validate_interval(
    reasons: list[str],
    *,
    capability: str,
    stage: str,
    interval: CalibrationInterval | None,
) -> None:
    if interval is None:
        reasons.append(f"{capability}:{stage}_interval_missing")
        return
    try:
        lower = float(interval.lower)
        upper = float(interval.upper)
        coverage_level = float(interval.coverage_level)
    except (TypeError, ValueError, OverflowError):
        reasons.append(f"{capability}:{stage}_interval_nonfinite")
        return
    if not all(
        math.isfinite(value)
        for value in (lower, upper, coverage_level)
    ):
        reasons.append(f"{capability}:{stage}_interval_nonfinite")
        return
    if lower > upper:
        reasons.append(f"{capability}:{stage}_interval_order_invalid")
    if not 0.0 < coverage_level <= 1.0:
        reasons.append(f"{capability}:{stage}_coverage_level_invalid")
    if type(interval.calibrated) is not bool:
        reasons.append(f"{capability}:{stage}_calibrated_type_invalid")
    elif not interval.calibrated:
        reasons.append(f"{capability}:{stage}_interval_not_calibrated")


def _find_forbidden_field(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if (
                "hindsight" in normalized
                or "temp_cell" in normalized
                or "temporary_cell" in normalized
                or normalized in {"expert_median", "fixed_expert_median"}
            ):
                return str(key)
            nested_match = _find_forbidden_field(nested)
            if nested_match is not None:
                return nested_match
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes),
    ):
        for nested in value:
            nested_match = _find_forbidden_field(nested)
            if nested_match is not None:
                return nested_match
    return None


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
