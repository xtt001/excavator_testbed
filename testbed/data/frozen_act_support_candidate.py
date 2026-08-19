"""Read and verify immutable ACT support candidates from audit evidence.

This is intentionally a deserialization boundary, not a fitting path.  A
caller supplies the candidate id selected by a completed support-contract
audit; this module verifies the artifact and reconstructs a
``FittedSupportCandidate`` that can be passed to ``assess_support_candidate``
without reopening a training split or recalibrating any threshold.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np

from testbed.data.act_support_contract import (
    AXIS_P0005_P9995_V2,
    AXIS_P01_P99_V1,
    JOINT_REGULARIZED_MAHALANOBIS_P99_V2,
    FittedSupportCandidate,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)

SUPPORT_CONTRACT_CANDIDATES_SCHEMA = "act_support_contract_candidates_v1"
SUPPORT_CONTRACT_VERSION = "support_contract_v2"


class FrozenSupportCandidateError(ValueError):
    """Raised when a selected support candidate artifact is incomplete or unsafe."""


def load_frozen_selected_support_candidate(
    *,
    candidates_json_path: str | Path,
    primitive: Literal["dig", "return"] | str,
    candidate_id: str,
) -> FittedSupportCandidate:
    """Load one qualified, frozen candidate from ``candidates.json``.

    ``candidate_id`` must be the candidate selected by the immutable audit
    manifest.  The loader verifies that the selected record is qualified and
    that its full numeric feature order is the canonical one for ``primitive``.
    It only deserializes fitted parameters; it never accepts target rollout
    rows, training rows, or a recalibration input.
    """
    path = Path(candidates_json_path).expanduser().resolve(strict=True)
    payload = _read_json_mapping(path)
    if payload.get("schema") != SUPPORT_CONTRACT_CANDIDATES_SCHEMA:
        raise FrozenSupportCandidateError("candidates artifact schema mismatch")
    if payload.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise FrozenSupportCandidateError("candidates artifact support contract version mismatch")
    primitive_name = _normalise_primitive(primitive)
    requested_candidate_id = str(candidate_id).strip()
    if not requested_candidate_id:
        raise FrozenSupportCandidateError("candidate_id must be non-empty")
    record = _select_candidate_record(
        payload,
        primitive=primitive_name,
        candidate_id=requested_candidate_id,
    )
    if record.get("qualified") is not True:
        raise FrozenSupportCandidateError(
            f"candidate_id {requested_candidate_id!r} is not qualified in the frozen artifact"
        )
    definition = record.get("definition")
    if not isinstance(definition, Mapping):
        raise FrozenSupportCandidateError("selected candidate definition must be a mapping")
    if str(definition.get("candidate_id", "")).strip() != requested_candidate_id:
        raise FrozenSupportCandidateError(
            "selected candidate record candidate_id disagrees with its definition"
        )
    feature_order = _expected_feature_order(primitive_name)
    observed_feature_order = _feature_order_from_definition(definition)
    if observed_feature_order != feature_order:
        raise FrozenSupportCandidateError(
            "selected candidate feature order does not match the canonical primitive contract"
        )
    common = _common_definition_fields(
        definition,
        candidate_id=requested_candidate_id,
        feature_order=feature_order,
    )
    if requested_candidate_id in {AXIS_P01_P99_V1, AXIS_P0005_P9995_V2}:
        return _deserialize_axis_candidate(definition, **common)
    if requested_candidate_id == JOINT_REGULARIZED_MAHALANOBIS_P99_V2:
        return _deserialize_joint_candidate(definition, **common)
    raise FrozenSupportCandidateError(
        f"candidate_id {requested_candidate_id!r} is not registered"
    )


def _select_candidate_record(
    payload: Mapping[str, Any],
    *,
    primitive: str,
    candidate_id: str,
) -> Mapping[str, Any]:
    primitives = payload.get("primitives")
    if not isinstance(primitives, Mapping):
        raise FrozenSupportCandidateError("candidates artifact lacks primitives mapping")
    records = primitives.get(primitive)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise FrozenSupportCandidateError(
            f"candidates artifact lacks candidate records for primitive {primitive!r}"
        )
    matches = [
        record
        for record in records
        if isinstance(record, Mapping)
        and str(record.get("candidate_id", "")).strip() == candidate_id
    ]
    if len(matches) != 1:
        raise FrozenSupportCandidateError(
            f"candidates artifact must contain exactly one candidate_id {candidate_id!r} "
            f"for primitive {primitive!r}, got {len(matches)}"
        )
    return matches[0]


def _common_definition_fields(
    definition: Mapping[str, Any],
    *,
    candidate_id: str,
    feature_order: tuple[str, ...],
) -> dict[str, Any]:
    if definition.get("fit_partition") != "strict_train":
        raise FrozenSupportCandidateError("selected candidate was not fitted on strict_train")
    fit_row_count = _positive_integer(definition.get("fit_row_count"), label="fit_row_count")
    threshold = _finite_scalar(definition.get("threshold"), label="threshold")
    if threshold < 0.0:
        raise FrozenSupportCandidateError("selected candidate threshold must be non-negative")
    return {
        "candidate_id": candidate_id,
        "feature_order": feature_order,
        "fit_partition": "strict_train",
        "fit_row_count": fit_row_count,
        "threshold": threshold,
    }


def _deserialize_axis_candidate(
    definition: Mapping[str, Any],
    *,
    candidate_id: str,
    feature_order: tuple[str, ...],
    fit_partition: Literal["strict_train"],
    fit_row_count: int,
    threshold: float,
) -> FittedSupportCandidate:
    expected_quantiles = {
        AXIS_P01_P99_V1: (0.01, 0.99),
        AXIS_P0005_P9995_V2: (0.0005, 0.9995),
    }
    expected_lower_quantile, expected_upper_quantile = expected_quantiles[candidate_id]
    lower_quantile = _finite_scalar(
        definition.get("lower_quantile"), label="lower_quantile"
    )
    upper_quantile = _finite_scalar(
        definition.get("upper_quantile"), label="upper_quantile"
    )
    if not np.isclose(lower_quantile, expected_lower_quantile, rtol=0.0, atol=1.0e-15):
        raise FrozenSupportCandidateError("selected axis candidate lower_quantile mismatch")
    if not np.isclose(upper_quantile, expected_upper_quantile, rtol=0.0, atol=1.0e-15):
        raise FrozenSupportCandidateError("selected axis candidate upper_quantile mismatch")
    if definition.get("threshold_kind") != "axis_interval_excess_zero":
        raise FrozenSupportCandidateError("selected axis candidate threshold_kind mismatch")
    if threshold != 0.0:
        raise FrozenSupportCandidateError("selected axis candidate threshold must equal zero")
    _require_none_or_absent(definition, "mean")
    _require_none_or_absent(definition, "covariance")
    _require_none_or_absent(definition, "precision")
    _require_none_or_absent(definition, "regularization")
    lower = _finite_vector(
        definition.get("lower"),
        label="axis lower",
        expected_dim=len(feature_order),
    )
    upper = _finite_vector(
        definition.get("upper"),
        label="axis upper",
        expected_dim=len(feature_order),
    )
    if np.any(lower > upper):
        raise FrozenSupportCandidateError("selected axis candidate lower exceeds upper")
    return FittedSupportCandidate(
        candidate_id=candidate_id,
        feature_order=feature_order,
        fit_partition=fit_partition,
        fit_row_count=fit_row_count,
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
        lower=_freeze_array(lower),
        upper=_freeze_array(upper),
        mean=None,
        covariance=None,
        precision=None,
        regularization=None,
        threshold=threshold,
        threshold_kind="axis_interval_excess_zero",
    )


def _deserialize_joint_candidate(
    definition: Mapping[str, Any],
    *,
    candidate_id: str,
    feature_order: tuple[str, ...],
    fit_partition: Literal["strict_train"],
    fit_row_count: int,
    threshold: float,
) -> FittedSupportCandidate:
    if definition.get("threshold_kind") != "train_p99_squared_distance":
        raise FrozenSupportCandidateError("selected joint candidate threshold_kind mismatch")
    _require_none_or_absent(definition, "lower_quantile")
    _require_none_or_absent(definition, "upper_quantile")
    _require_none_or_absent(definition, "lower")
    _require_none_or_absent(definition, "upper")
    mean = _finite_vector(
        definition.get("mean"),
        label="joint mean",
        expected_dim=len(feature_order),
    )
    covariance = _finite_square_matrix(
        definition.get("covariance"),
        label="joint covariance",
        expected_dim=len(feature_order),
    )
    regularization = _finite_scalar(
        definition.get("regularization"), label="joint regularization"
    )
    if regularization <= 0.0:
        raise FrozenSupportCandidateError("selected joint regularization must be positive")
    if not np.allclose(covariance, covariance.T, rtol=1.0e-10, atol=1.0e-12):
        raise FrozenSupportCandidateError("selected joint covariance must be symmetric")
    try:
        np.linalg.cholesky(covariance)
        precision = np.linalg.inv(covariance)
    except np.linalg.LinAlgError as exc:
        raise FrozenSupportCandidateError(
            "selected joint covariance must be positive definite"
        ) from exc
    if not np.isfinite(precision).all():
        raise FrozenSupportCandidateError("selected joint precision is non-finite")
    return FittedSupportCandidate(
        candidate_id=candidate_id,
        feature_order=feature_order,
        fit_partition=fit_partition,
        fit_row_count=fit_row_count,
        lower_quantile=None,
        upper_quantile=None,
        lower=None,
        upper=None,
        mean=_freeze_array(mean),
        covariance=_freeze_array(covariance),
        precision=_freeze_array(precision),
        regularization=regularization,
        threshold=threshold,
        threshold_kind="train_p99_squared_distance",
    )


def _read_json_mapping(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FrozenSupportCandidateError("candidates artifact is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise FrozenSupportCandidateError("candidates artifact root must be a mapping")
    return payload


def _normalise_primitive(value: str) -> Literal["dig", "return"]:
    primitive = str(value).strip().lower()
    if primitive not in {"dig", "return"}:
        raise FrozenSupportCandidateError(
            f"frozen support candidates only support dig/return, got {value!r}"
        )
    return primitive  # type: ignore[return-value]


def _expected_feature_order(primitive: Literal["dig", "return"]) -> tuple[str, ...]:
    token_key, token_dim = (
        ("dig_cut_tokens", DIG_CUT_TOKEN_DIM)
        if primitive == "dig"
        else ("return_start_envelope_tokens_v1", RETURN_START_ENVELOPE_TOKEN_DIM)
    )
    return tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"{token_key}[{index}]" for index in range(token_dim)]
    )


def _feature_order_from_definition(definition: Mapping[str, Any]) -> tuple[str, ...]:
    value = definition.get("feature_order")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise FrozenSupportCandidateError("selected candidate feature order must be a sequence")
    result = tuple(str(item) for item in value)
    if not result or len(result) != len(set(result)):
        raise FrozenSupportCandidateError("selected candidate feature order is invalid")
    return result


def _positive_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise FrozenSupportCandidateError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FrozenSupportCandidateError(f"{label} must be a positive integer") from exc
    if result < 1 or str(result) != str(value).strip():
        raise FrozenSupportCandidateError(f"{label} must be a positive integer")
    return result


def _finite_scalar(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise FrozenSupportCandidateError(f"{label} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FrozenSupportCandidateError(f"{label} must be finite") from exc
    if not np.isfinite(result):
        raise FrozenSupportCandidateError(f"{label} must be finite")
    return result


def _finite_vector(value: Any, *, label: str, expected_dim: int) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise FrozenSupportCandidateError(f"{label} must be a finite vector") from exc
    if result.shape != (expected_dim,) or not np.isfinite(result).all():
        raise FrozenSupportCandidateError(
            f"{label} must be a finite vector with width {expected_dim}"
        )
    return result


def _finite_square_matrix(value: Any, *, label: str, expected_dim: int) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise FrozenSupportCandidateError(f"{label} must be a finite matrix") from exc
    if result.shape != (expected_dim, expected_dim) or not np.isfinite(result).all():
        raise FrozenSupportCandidateError(
            f"{label} must be a finite {expected_dim}x{expected_dim} matrix"
        )
    return result


def _require_none_or_absent(definition: Mapping[str, Any], key: str) -> None:
    if key in definition and definition[key] is not None:
        raise FrozenSupportCandidateError(
            f"selected candidate must not contain fitted {key!r}"
        )


def _freeze_array(value: np.ndarray) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).copy()
    result.setflags(write=False)
    return result


__all__ = [
    "FrozenSupportCandidateError",
    "SUPPORT_CONTRACT_CANDIDATES_SCHEMA",
    "SUPPORT_CONTRACT_VERSION",
    "load_frozen_selected_support_candidate",
]
