"""Frozen, source-safe joint-support candidates for Dig validation.

This module deliberately has a smaller responsibility than the historical
``support_contract_v1``/``v2`` implementation.  It owns one *pre-registered*
family of regularised Mahalanobis rules for Dig and the validation-only
negative control used to compare them.  It accepts only the strict
source-aware train/held-validation population; it has no parameter for a
recorded rollout, Stage-A result, planner state, or runtime gate.

That boundary matters here: candidate thresholds are a function of strict
train rows only, while held validation is used only to accept or reject a
frozen candidate.  A later replay may consume a selected candidate, but must
not be able to tune this family from its own outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.act_support_contract import (
    StrictSourceAwareSupportRows,
    SupportRowProvenance,
    load_strict_source_aware_support_rows,
)

DIG_JOINT_SUPPORT_VALIDATION_SCHEMA = "dig_joint_support_validation_v1"
"""Schema for the independent Dig joint-support validation input/output."""

DIG_JOINT_MAHALANOBIS_QUANTILES = (0.99, 0.995, 0.999, 0.9995, 0.9999)
"""Fixed train-score quantiles; callers cannot add outcome-tuned candidates."""

DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS = (
    "dig_joint_regularized_mahalanobis_p99_v1",
    "dig_joint_regularized_mahalanobis_p995_v1",
    "dig_joint_regularized_mahalanobis_p999_v1",
    "dig_joint_regularized_mahalanobis_p9995_v1",
    "dig_joint_regularized_mahalanobis_p9999_v1",
)

DIG_JOINT_MAHALANOBIS_RIDGE_TRACE_FRACTION = 1.0e-6
DIG_JOINT_MAHALANOBIS_RIDGE_FLOOR = 1.0e-12
DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD = "linear"
DIG_VALIDATION_OBVIOUS_OOD_MULTIPLIER = 32.0
DIG_VALIDATION_OBVIOUS_OOD_SCHEMA = "dig_validation_obvious_ood_v1"
DIG_VALIDATION_V1_EDGE_SCHEMA = "dig_validation_v1_edge_cohort_v1"


class DigJointSupportValidationError(ValueError):
    """Raised when the independent Dig validation boundary is violated."""


@dataclass(frozen=True)
class DigJointMahalanobisCandidate:
    """One fixed-threshold joint rule fitted from strict-train Dig rows only."""

    candidate_id: str
    train_score_quantile: float
    feature_order: tuple[str, ...]
    fit_partition: str
    fit_row_count: int
    mean: np.ndarray
    covariance: np.ndarray
    precision: np.ndarray
    regularization: float
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "train_score_quantile": self.train_score_quantile,
            "feature_order": list(self.feature_order),
            "fit_partition": self.fit_partition,
            "fit_row_count": self.fit_row_count,
            "mean": _json_ready(self.mean),
            "covariance": _json_ready(self.covariance),
            "regularization": self.regularization,
            "threshold": self.threshold,
            "quantile_method": DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
            "threshold_kind": "strict_train_quantile_squared_regularized_mahalanobis",
        }


@dataclass(frozen=True)
class DigJointSupportAssessment:
    """Support decision for a matrix under a frozen joint candidate."""

    candidate_id: str
    feature_order: tuple[str, ...]
    frame_in_support: np.ndarray
    scores: np.ndarray
    threshold: float

    @property
    def in_support_fraction(self) -> float:
        return (
            float(np.mean(self.frame_in_support))
            if self.frame_in_support.size
            else 0.0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "feature_order": list(self.feature_order),
            "frame_in_support": [bool(value) for value in self.frame_in_support],
            "scores": _json_ready(self.scores),
            "threshold": self.threshold,
            "score_kind": "squared_regularized_mahalanobis_distance",
            "in_support_fraction": self.in_support_fraction,
        }


@dataclass(frozen=True)
class FrozenDigValidationObviousOod:
    """Validation-only, deterministic numerical negative-control population."""

    schema: str
    feature_order: tuple[str, ...]
    anchor_partition: str
    multiplier: float
    anchor_features: np.ndarray
    features: np.ndarray
    perturbation: np.ndarray
    anchor_provenance: tuple[SupportRowProvenance, ...]

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "anchor_partition": self.anchor_partition,
            "multiplier": self.multiplier,
            "row_count": int(self.features.shape[0]),
            "anchor_provenance_sha256": _provenance_digest(self.anchor_provenance),
            "anchor_source_episode_ids": sorted(
                {int(item.source_episode_id) for item in self.anchor_provenance}
            ),
        }


@dataclass(frozen=True)
class DigValidationV1EdgeCohort:
    """Normal held-validation Dig rows rejected by historical axis v1.

    This cohort proves that a proposed joint rule can accept normal states near
    the historical p01--p99 boundary.  Its membership is frozen by strict-train
    v1 bounds and held-validation rows, never by a recorded target outcome.
    """

    schema: str
    feature_order: tuple[str, ...]
    anchor_partition: str
    v1_fit_partition: str
    lower: np.ndarray
    upper: np.ndarray
    validation_indices: np.ndarray
    features: np.ndarray
    provenance: tuple[SupportRowProvenance, ...]

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "anchor_partition": self.anchor_partition,
            "v1_fit_partition": self.v1_fit_partition,
            "row_count": int(self.features.shape[0]),
            "validation_indices": [int(value) for value in self.validation_indices],
            "provenance_sha256": _provenance_digest(self.provenance),
            "source_episode_ids": sorted(
                {int(item.source_episode_id) for item in self.provenance}
            ),
            "membership": (
                "held_validation_rows_rejected_by_strict_train_axis_p01_p99_v1"
            ),
            "v1_axis_bounds": {
                "fit_partition": self.v1_fit_partition,
                "lower_quantile": 0.01,
                "upper_quantile": 0.99,
                "quantile_method": DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
                "lower": _json_ready(self.lower),
                "upper": _json_ready(self.upper),
            },
        }


def load_dig_joint_support_validation_rows(
    *,
    training_config_path: str | Path,
) -> StrictSourceAwareSupportRows:
    """Load only strict-train and held-validation Dig rows from one config.

    The underlying loader validates the source-aware split and only exposes
    action-supervised rows.  This wrapper pins the primitive to Dig and checks
    the source-disjoint boundary again before exposing the population to the
    joint family fitter.
    """

    rows = load_strict_source_aware_support_rows(
        training_config_path=training_config_path,
        skill_name="dig",
    )
    validate_dig_joint_support_validation_rows(rows)
    return rows


def validate_dig_joint_support_validation_rows(
    rows: StrictSourceAwareSupportRows,
) -> None:
    """Reject any population that is not strict Dig train/held-validation data."""

    if rows.skill_name != "dig":
        raise DigJointSupportValidationError(
            f"Dig joint validation requires dig rows, got {rows.skill_name!r}"
        )
    if rows.model_token_key != "dig_cut_tokens":
        raise DigJointSupportValidationError(
            "Dig joint validation requires model token key 'dig_cut_tokens'"
        )
    _validate_feature_matrix(
        rows.train_features,
        expected_width=len(rows.feature_order),
        label="strict-train Dig features",
    )
    _validate_feature_matrix(
        rows.validation_features,
        expected_width=len(rows.feature_order),
        label="held Dig validation features",
    )
    if len(rows.train_provenance) != rows.train_features.shape[0]:
        raise DigJointSupportValidationError(
            "strict-train Dig provenance length does not match feature rows"
        )
    if len(rows.validation_provenance) != rows.validation_features.shape[0]:
        raise DigJointSupportValidationError(
            "held Dig validation provenance length does not match feature rows"
        )
    train_sources = {int(value) for value in rows.train_source_episode_ids}
    validation_sources = {int(value) for value in rows.validation_source_episode_ids}
    if not train_sources or not validation_sources:
        raise DigJointSupportValidationError(
            "Dig joint validation requires non-empty train and validation source sets"
        )
    overlap = sorted(train_sources & validation_sources)
    if overlap:
        raise DigJointSupportValidationError(
            f"Dig train and validation source episode ids overlap: {overlap}"
        )
    _validate_provenance_partition(
        rows.train_provenance,
        expected_partition="train",
        allowed_sources=train_sources,
        label="strict-train Dig",
    )
    _validate_provenance_partition(
        rows.validation_provenance,
        expected_partition="validation",
        allowed_sources=validation_sources,
        label="held Dig validation",
    )


def fit_dig_joint_mahalanobis_family(
    rows: StrictSourceAwareSupportRows,
) -> dict[str, DigJointMahalanobisCandidate]:
    """Fit the fixed Dig joint threshold family using strict-train rows only.

    Mean, covariance, ridge and every threshold are determined before held
    validation is inspected.  All family members share the same regularised
    covariance; their only difference is the pre-registered strict-train
    score quantile.
    """

    validate_dig_joint_support_validation_rows(rows)
    train = np.asarray(rows.train_features, dtype=np.float64)
    mean, covariance, precision, ridge, scores = _fit_joint_geometry(train)
    candidates: dict[str, DigJointMahalanobisCandidate] = {}
    for candidate_id, quantile in zip(
        DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS,
        DIG_JOINT_MAHALANOBIS_QUANTILES,
        strict=True,
    ):
        candidates[candidate_id] = DigJointMahalanobisCandidate(
            candidate_id=candidate_id,
            train_score_quantile=quantile,
            feature_order=tuple(rows.feature_order),
            fit_partition="strict_train",
            fit_row_count=int(train.shape[0]),
            mean=_freeze_array(mean),
            covariance=_freeze_array(covariance),
            precision=_freeze_array(precision),
            regularization=ridge,
            threshold=float(
                np.quantile(
                    scores,
                    quantile,
                    method=DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
                )
            ),
        )
    return candidates


def assess_dig_joint_mahalanobis_candidate(
    candidate: DigJointMahalanobisCandidate,
    features: np.ndarray | Sequence[Sequence[float]],
) -> DigJointSupportAssessment:
    """Apply a frozen Dig candidate without refitting or changing its threshold."""

    expected_width = len(candidate.feature_order)
    matrix = _coerce_feature_matrix(features, expected_width=expected_width)
    mean = _coerce_vector(candidate.mean, expected_width=expected_width, label="mean")
    precision = _coerce_square_matrix(
        candidate.precision,
        expected_width=expected_width,
        label="precision",
    )
    scores = _squared_mahalanobis(matrix - mean.reshape(1, -1), precision)
    return DigJointSupportAssessment(
        candidate_id=candidate.candidate_id,
        feature_order=tuple(candidate.feature_order),
        frame_in_support=_freeze_bool_array(scores <= candidate.threshold),
        scores=_freeze_array(scores),
        threshold=float(candidate.threshold),
    )


def build_frozen_dig_validation_obvious_ood(
    rows: StrictSourceAwareSupportRows,
) -> FrozenDigValidationObviousOod:
    """Build a deterministic obvious-OOD control using held validation only.

    The perturbation may use validation anchors and spans because it is a
    frozen *negative-control source*, never a candidate fit input.  It cannot
    see recorded Stage-A observations or their classifications.
    """

    validate_dig_joint_support_validation_rows(rows)
    anchor = np.asarray(rows.validation_features, dtype=np.float64)
    span = np.max(anchor, axis=0) - np.min(anchor, axis=0)
    scale = np.maximum(
        np.maximum(np.abs(anchor), span.reshape(1, -1)),
        1.0,
    )
    row_indices = np.arange(anchor.shape[0], dtype=np.int64).reshape(-1, 1)
    feature_indices = np.arange(anchor.shape[1], dtype=np.int64).reshape(1, -1)
    signs = np.where((row_indices + feature_indices) % 2 == 0, 1.0, -1.0)
    perturbation = DIG_VALIDATION_OBVIOUS_OOD_MULTIPLIER * signs * scale
    features = anchor + perturbation
    if not np.isfinite(features).all():
        raise DigJointSupportValidationError(
            "frozen Dig validation obvious-OOD construction produced non-finite values"
        )
    return FrozenDigValidationObviousOod(
        schema=DIG_VALIDATION_OBVIOUS_OOD_SCHEMA,
        feature_order=tuple(rows.feature_order),
        anchor_partition="validation",
        multiplier=DIG_VALIDATION_OBVIOUS_OOD_MULTIPLIER,
        anchor_features=_freeze_array(anchor),
        features=_freeze_array(features),
        perturbation=_freeze_array(perturbation),
        anchor_provenance=tuple(rows.validation_provenance),
    )


def build_dig_validation_v1_edge_cohort(
    rows: StrictSourceAwareSupportRows,
) -> DigValidationV1EdgeCohort:
    """Freeze the normal held-validation rows rejected by historical v1.

    The p01/p99 bounds are fit from strict-train Dig rows.  The cohort then
    selects only held-validation rows outside at least one of those bounds.
    An empty cohort is returned explicitly; the evaluator treats it as a
    fail-closed non-qualification rather than silently dropping this evidence.
    """

    validate_dig_joint_support_validation_rows(rows)
    train = np.asarray(rows.train_features, dtype=np.float64)
    validation = np.asarray(rows.validation_features, dtype=np.float64)
    lower = np.quantile(
        train,
        0.01,
        axis=0,
        method=DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
    )
    upper = np.quantile(
        train,
        0.99,
        axis=0,
        method=DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
    )
    outside = np.logical_or(validation < lower.reshape(1, -1), validation > upper.reshape(1, -1))
    indices = np.flatnonzero(np.any(outside, axis=1)).astype(np.int64, copy=False)
    return DigValidationV1EdgeCohort(
        schema=DIG_VALIDATION_V1_EDGE_SCHEMA,
        feature_order=tuple(rows.feature_order),
        anchor_partition="validation",
        v1_fit_partition="strict_train",
        lower=_freeze_array(lower),
        upper=_freeze_array(upper),
        validation_indices=_freeze_int_array(indices),
        features=_freeze_array(validation[indices]),
        provenance=tuple(rows.validation_provenance[int(index)] for index in indices),
    )


def dig_joint_support_source_provenance(
    rows: StrictSourceAwareSupportRows,
) -> dict[str, Any]:
    """Return compact, traceable proof that train and validation are separate."""

    validate_dig_joint_support_validation_rows(rows)
    train_sources = sorted({int(value) for value in rows.train_source_episode_ids})
    validation_sources = sorted(
        {int(value) for value in rows.validation_source_episode_ids}
    )
    return {
        "schema": DIG_JOINT_SUPPORT_VALIDATION_SCHEMA,
        "selection_input_scope": "strict_train_and_held_validation_only",
        "target_rollout_used_for_selection": False,
        "skill_name": "dig",
        "model_token_key": rows.model_token_key,
        "feature_order": list(rows.feature_order),
        "train": _partition_provenance(
            rows.train_provenance,
            source_episode_ids=train_sources,
        ),
        "validation": _partition_provenance(
            rows.validation_provenance,
            source_episode_ids=validation_sources,
        ),
        "source_episode_id_overlap": [],
        "source_disjoint": True,
    }


def _fit_joint_geometry(
    train: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, np.ndarray]:
    sample_count, feature_dim = train.shape
    if sample_count == 0 or feature_dim == 0:
        raise DigJointSupportValidationError("strict-train Dig matrix must be non-empty")
    mean = np.mean(train, axis=0)
    centered = train - mean.reshape(1, -1)
    covariance = (centered.T @ centered) / float(max(sample_count - 1, 1))
    trace_scale = float(np.trace(covariance) / feature_dim)
    if not np.isfinite(trace_scale) or trace_scale < 0.0:
        raise DigJointSupportValidationError("strict-train Dig covariance trace is invalid")
    ridge = max(
        DIG_JOINT_MAHALANOBIS_RIDGE_TRACE_FRACTION * trace_scale,
        DIG_JOINT_MAHALANOBIS_RIDGE_FLOOR,
    )
    regularized_covariance = covariance + ridge * np.eye(feature_dim)
    try:
        precision = np.linalg.inv(regularized_covariance)
    except np.linalg.LinAlgError as exc:
        raise DigJointSupportValidationError(
            "strict-train Dig regularized covariance is not invertible"
        ) from exc
    if not np.isfinite(precision).all():
        raise DigJointSupportValidationError("strict-train Dig precision is non-finite")
    scores = _squared_mahalanobis(centered, precision)
    return mean, regularized_covariance, precision, ridge, scores


def _validate_feature_matrix(
    value: np.ndarray,
    *,
    expected_width: int,
    label: str,
) -> None:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != expected_width:
        raise DigJointSupportValidationError(
            f"{label} must be non-empty with width {expected_width}, got {matrix.shape}"
        )
    if not np.isfinite(matrix).all():
        raise DigJointSupportValidationError(f"{label} contains non-finite values")


def _validate_provenance_partition(
    provenance: Sequence[SupportRowProvenance],
    *,
    expected_partition: str,
    allowed_sources: set[int],
    label: str,
) -> None:
    observed_sources = {int(item.source_episode_id) for item in provenance}
    if not observed_sources or not observed_sources <= allowed_sources:
        raise DigJointSupportValidationError(
            f"{label} provenance sources disagree with the declared split"
        )
    for item in provenance:
        if item.partition != expected_partition:
            raise DigJointSupportValidationError(
                f"{label} provenance contains partition {item.partition!r}"
            )
        if int(item.action_loss_mask) != 1:
            raise DigJointSupportValidationError(
                f"{label} provenance includes a non-action-supervised row"
            )


def _partition_provenance(
    provenance: Sequence[SupportRowProvenance],
    *,
    source_episode_ids: list[int],
) -> dict[str, Any]:
    return {
        "source_episode_ids": source_episode_ids,
        "observed_source_episode_ids": sorted(
            {int(item.source_episode_id) for item in provenance}
        ),
        "primitive_episode_ids": sorted(
            {int(item.primitive_episode_id) for item in provenance}
        ),
        "row_count": len(provenance),
        "provenance_sha256": _provenance_digest(provenance),
    }


def _provenance_digest(provenance: Sequence[SupportRowProvenance]) -> str:
    canonical = [item.as_dict() for item in provenance]
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _coerce_feature_matrix(
    features: np.ndarray | Sequence[Sequence[float]],
    *,
    expected_width: int,
) -> np.ndarray:
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != expected_width:
        raise DigJointSupportValidationError(
            f"assessment features must be non-empty with width {expected_width}, got {matrix.shape}"
        )
    if not np.isfinite(matrix).all():
        raise DigJointSupportValidationError("assessment features contain non-finite values")
    return matrix


def _coerce_vector(value: np.ndarray, *, expected_width: int, label: str) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64).reshape(-1)
    if vector.shape != (expected_width,) or not np.isfinite(vector).all():
        raise DigJointSupportValidationError(
            f"candidate {label} must be finite with width {expected_width}"
        )
    return vector


def _coerce_square_matrix(
    value: np.ndarray,
    *,
    expected_width: int,
    label: str,
) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (expected_width, expected_width) or not np.isfinite(matrix).all():
        raise DigJointSupportValidationError(
            f"candidate {label} must be a finite {expected_width}x{expected_width} matrix"
        )
    return matrix


def _squared_mahalanobis(centered: np.ndarray, precision: np.ndarray) -> np.ndarray:
    scores = np.einsum("ni,ij,nj->n", centered, precision, centered, optimize=True)
    # A valid positive-definite covariance can yield tiny negative round-off.
    return np.maximum(scores, 0.0)


def _freeze_array(value: np.ndarray) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).copy()
    result.setflags(write=False)
    return result


def _freeze_bool_array(value: np.ndarray) -> np.ndarray:
    result = np.asarray(value, dtype=bool).copy()
    result.setflags(write=False)
    return result


def _freeze_int_array(value: np.ndarray) -> np.ndarray:
    result = np.asarray(value, dtype=np.int64).copy()
    result.setflags(write=False)
    return result


def _json_ready(value: np.ndarray) -> list[Any]:
    return np.asarray(value, dtype=np.float64).tolist()


__all__ = [
    "DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS",
    "DIG_JOINT_MAHALANOBIS_QUANTILES",
    "DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD",
    "DIG_JOINT_MAHALANOBIS_RIDGE_FLOOR",
    "DIG_JOINT_MAHALANOBIS_RIDGE_TRACE_FRACTION",
    "DIG_JOINT_SUPPORT_VALIDATION_SCHEMA",
    "DIG_VALIDATION_OBVIOUS_OOD_MULTIPLIER",
    "DigJointMahalanobisCandidate",
    "DigJointSupportAssessment",
    "DigJointSupportValidationError",
    "DigValidationV1EdgeCohort",
    "FrozenDigValidationObviousOod",
    "assess_dig_joint_mahalanobis_candidate",
    "build_dig_validation_v1_edge_cohort",
    "build_frozen_dig_validation_obvious_ood",
    "dig_joint_support_source_provenance",
    "fit_dig_joint_mahalanobis_family",
    "load_dig_joint_support_validation_rows",
    "validate_dig_joint_support_validation_rows",
]
