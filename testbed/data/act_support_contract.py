"""Source-safe numeric support contracts for frozen ACT diagnostics.

This module owns the numeric support population used by Strict-18 diagnostics.
It deliberately separates three roles:

* strict-train rows fit a support candidate;
* source-disjoint validation rows measure normal-state acceptance; and
* a deterministic, validation-derived perturbation set checks that a candidate
  still rejects states made obviously unfamiliar.

Target rollout rows are never accepted by a fitting API.  In particular, a
candidate's bounds, covariance, ridge, and threshold are functions of strict
training rows only.  This makes the candidate comparison reproducible without
tuning a rule to the rollout that later consumes it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np
import yaml

from testbed.data.action_loss_mask import read_action_loss_mask
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.data.schema import DS_STEP_ID

AXIS_P01_P99_V1 = "axis_p01_p99_v1"
"""Historical support_contract_v1: strict-train per-axis p01/p99."""

AXIS_P0005_P9995_V2 = "axis_p0005_p9995_v2"
"""Pre-registered v2 candidate: strict-train per-axis p0.05/p99.95."""

JOINT_REGULARIZED_MAHALANOBIS_P99_V2 = "joint_regularized_mahalanobis_p99_v2"
"""Pre-registered v2 candidate: strict-train full-covariance distance p99."""

SUPPORT_CANDIDATE_IDS = (
    AXIS_P01_P99_V1,
    AXIS_P0005_P9995_V2,
    JOINT_REGULARIZED_MAHALANOBIS_P99_V2,
)

FROZEN_OBVIOUS_OOD_SCHEMA = "frozen_obvious_ood_from_validation_v1"
FROZEN_OBVIOUS_OOD_MULTIPLIER = 32.0
_MAHALANOBIS_RIDGE_TRACE_FRACTION = 1.0e-6
_MAHALANOBIS_RIDGE_FLOOR = 1.0e-12


@dataclass(frozen=True)
class SupportRowProvenance:
    """Traceable origin for one action-supervised numeric feature row."""

    partition: Literal["train", "validation"]
    primitive_episode_id: int
    source_episode_id: int
    step_index: int
    step_id: int
    action_loss_mask: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "partition": self.partition,
            "primitive_episode_id": self.primitive_episode_id,
            "source_episode_id": self.source_episode_id,
            "step_index": self.step_index,
            "step_id": self.step_id,
            "action_loss_mask": self.action_loss_mask,
        }


@dataclass(frozen=True)
class StrictSourceAwareSupportRows:
    """Complete strict-train/validation numeric population for one primitive.

    Each matrix uses ``feature_order = qpos + qvel + full condition token``.
    The corresponding provenance tuple has exactly the same row order.  Arrays
    are read-only so callers cannot accidentally modify the evidence population
    after loading it.
    """

    schema: str
    skill_name: Literal["dig", "return"]
    model_token_key: str
    feature_order: tuple[str, ...]
    train_features: np.ndarray
    validation_features: np.ndarray
    train_provenance: tuple[SupportRowProvenance, ...]
    validation_provenance: tuple[SupportRowProvenance, ...]
    training_config_path: str
    primitive_dataset_dir: str
    split_path: str
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    total_step_count: int
    kept_step_count: int
    masked_step_count: int

    @property
    def feature_dim(self) -> int:
        return len(self.feature_order)

    @property
    def all_provenance(self) -> tuple[SupportRowProvenance, ...]:
        return self.train_provenance + self.validation_provenance

    def as_dict(self) -> dict[str, Any]:
        """Return compact lineage metadata without embedding all numeric rows."""
        return {
            "schema": self.schema,
            "skill_name": self.skill_name,
            "model_token_key": self.model_token_key,
            "feature_order": list(self.feature_order),
            "training_config_path": self.training_config_path,
            "primitive_dataset_dir": self.primitive_dataset_dir,
            "split_path": self.split_path,
            "train_source_episode_ids": list(self.train_source_episode_ids),
            "validation_source_episode_ids": list(self.validation_source_episode_ids),
            "train_row_count": int(self.train_features.shape[0]),
            "validation_row_count": int(self.validation_features.shape[0]),
            "total_step_count": self.total_step_count,
            "kept_step_count": self.kept_step_count,
            "masked_step_count": self.masked_step_count,
        }


@dataclass(frozen=True)
class SupportCandidateViolation:
    """One support rejection, preserving axis attribution when available."""

    kind: str
    feature_index: int | None
    field: str | None
    value: float | None
    lower: float | None
    upper: float | None
    score: float | None
    threshold: float | None

    def as_dict(self) -> dict[str, float | int | str | None]:
        return {
            "kind": self.kind,
            "feature_index": self.feature_index,
            "field": self.field,
            "value": self.value,
            "lower": self.lower,
            "upper": self.upper,
            "score": self.score,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class FittedSupportCandidate:
    """One immutable candidate fitted only from strict source-safe train rows."""

    candidate_id: str
    feature_order: tuple[str, ...]
    fit_partition: Literal["strict_train"]
    fit_row_count: int
    lower_quantile: float | None
    upper_quantile: float | None
    lower: np.ndarray | None
    upper: np.ndarray | None
    mean: np.ndarray | None
    covariance: np.ndarray | None
    precision: np.ndarray | None
    regularization: float | None
    threshold: float
    threshold_kind: str

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-ready candidate parameters and its fit boundary."""
        result: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "feature_order": list(self.feature_order),
            "fit_partition": self.fit_partition,
            "fit_row_count": self.fit_row_count,
            "lower_quantile": self.lower_quantile,
            "upper_quantile": self.upper_quantile,
            "regularization": self.regularization,
            "threshold": self.threshold,
            "threshold_kind": self.threshold_kind,
        }
        if self.lower is not None:
            result["lower"] = _float_list(self.lower)
        if self.upper is not None:
            result["upper"] = _float_list(self.upper)
        if self.mean is not None:
            result["mean"] = _float_list(self.mean)
        if self.covariance is not None:
            result["covariance"] = np.asarray(self.covariance, dtype=float).tolist()
        return result


@dataclass(frozen=True)
class SupportCandidateAssessment:
    """Assessment of one feature matrix using one fitted support candidate."""

    candidate_id: str
    feature_order: tuple[str, ...]
    feature: np.ndarray
    frame_in_support: np.ndarray
    scores: np.ndarray
    threshold: float
    score_kind: str
    violations: tuple[tuple[SupportCandidateViolation, ...], ...]

    @property
    def in_support_fraction(self) -> float:
        if not self.frame_in_support.size:
            return 0.0
        return float(np.mean(self.frame_in_support))

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "feature_order": list(self.feature_order),
            "frame_in_support": [bool(value) for value in self.frame_in_support],
            "scores": _float_list(self.scores),
            "threshold": self.threshold,
            "score_kind": self.score_kind,
            "in_support_fraction": self.in_support_fraction,
            "violations": [
                [item.as_dict() for item in row] for row in self.violations
            ],
        }


@dataclass(frozen=True)
class FrozenObviousOodReference:
    """Deterministic validation-only negative control for candidate evaluation.

    For every validation row, each feature gets an alternating-sign perturbation
    of ``32 * max(abs(anchor), validation_feature_span, 1.0)``.  The scale and
    anchors are computed only from the validation partition.  This creates an
    intentionally obvious numerical outlier without looking at target rollout
    data or modifying a candidate's fitted parameters.
    """

    schema: str
    feature_order: tuple[str, ...]
    anchor_partition: Literal["validation"]
    multiplier: float
    anchor_features: np.ndarray
    features: np.ndarray
    perturbation: np.ndarray
    anchor_provenance: tuple[SupportRowProvenance, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "feature_order": list(self.feature_order),
            "anchor_partition": self.anchor_partition,
            "multiplier": self.multiplier,
            "row_count": int(self.features.shape[0]),
            "anchor_provenance": [item.as_dict() for item in self.anchor_provenance],
        }


@dataclass(frozen=True)
class _ConditionSpec:
    skill_name: Literal["dig", "return"]
    model_token_key: str
    dataset_path: str
    token_dim: int


_CONDITION_SPECS: dict[str, _ConditionSpec] = {
    "dig": _ConditionSpec(
        skill_name="dig",
        model_token_key="dig_cut_tokens",
        dataset_path="v2/step/dig_cut_tokens",
        token_dim=DIG_CUT_TOKEN_DIM,
    ),
    "return": _ConditionSpec(
        skill_name="return",
        model_token_key="return_start_envelope_tokens_v1",
        dataset_path="v2/step/return_start_envelope_tokens_v1",
        token_dim=RETURN_START_ENVELOPE_TOKEN_DIM,
    ),
}


@dataclass(frozen=True)
class _SourceAwareSplit:
    train_ids: tuple[int, ...]
    validation_ids: tuple[int, ...]
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    source_by_primitive_episode_id: dict[int, int]


def load_strict_source_aware_support_rows(
    *,
    training_config_path: str | Path,
    skill_name: str | None = None,
) -> StrictSourceAwareSupportRows:
    """Load strict source-disjoint qpos/qvel/full-token rows from a train config.

    The config identifies the primitive dataset and exact source-aware split.
    Only ``action_loss_mask == 1`` rows are exposed, for both train and
    validation partitions.  This function is read-only and does not accept a
    rollout path, preventing target evidence from entering candidate fitting.
    """
    config_path = Path(training_config_path).expanduser().resolve(strict=True)
    config = _read_mapping_yaml(config_path, label="training config")
    spec = _resolve_condition_spec(config, requested_skill_name=skill_name)
    task = _required_mapping(config, "task", label="training config")
    train = _required_mapping(config, "train", label="training config")
    dataset_dir = _required_path(task, "dataset_dir", label="training task")
    split_path = _required_path(train, "split_path", label="training settings")
    dataset_dir = dataset_dir.resolve(strict=True)
    split_path = split_path.resolve(strict=True)
    split = _read_source_aware_split(split_path, dataset_dir=dataset_dir)

    train_features: list[np.ndarray] = []
    validation_features: list[np.ndarray] = []
    train_provenance: list[SupportRowProvenance] = []
    validation_provenance: list[SupportRowProvenance] = []
    total_step_count = 0
    masked_step_count = 0
    for partition, primitive_ids in (
        ("train", split.train_ids),
        ("validation", split.validation_ids),
    ):
        for primitive_episode_id in primitive_ids:
            path = dataset_dir / f"episode_{primitive_episode_id}.hdf5"
            if not path.is_file():
                raise FileNotFoundError(path)
            with h5py.File(path, "r") as handle:
                source_episode_id = _source_episode_id(handle)
                expected_source_episode_id = split.source_by_primitive_episode_id[
                    primitive_episode_id
                ]
                _validate_partition_source(
                    partition=partition,
                    primitive_episode_id=primitive_episode_id,
                    source_episode_id=source_episode_id,
                    expected_source_episode_id=expected_source_episode_id,
                    split=split,
                )
                feature, step_ids, mask = _read_episode_support_inputs(
                    handle,
                    spec=spec,
                    path=path,
                )
            total_step_count += int(feature.shape[0])
            keep = mask == 1
            masked_step_count += int(np.count_nonzero(~keep))
            if not np.any(keep):
                continue
            partition_features = feature[keep]
            partition_provenance = [
                SupportRowProvenance(
                    partition=partition,
                    primitive_episode_id=primitive_episode_id,
                    source_episode_id=source_episode_id,
                    step_index=int(step_index),
                    step_id=int(step_ids[step_index]),
                    action_loss_mask=int(mask[step_index]),
                )
                for step_index in np.flatnonzero(keep)
            ]
            if partition == "train":
                train_features.append(partition_features)
                train_provenance.extend(partition_provenance)
            else:
                validation_features.append(partition_features)
                validation_provenance.extend(partition_provenance)
    if not train_features:
        raise ValueError("strict train support population has no action_loss_mask=1 rows")
    if not validation_features:
        raise ValueError("validation support population has no action_loss_mask=1 rows")

    train_matrix = _freeze_array(np.concatenate(train_features, axis=0))
    validation_matrix = _freeze_array(np.concatenate(validation_features, axis=0))
    if len(train_provenance) != train_matrix.shape[0]:
        raise AssertionError("strict-train provenance length does not match feature rows")
    if len(validation_provenance) != validation_matrix.shape[0]:
        raise AssertionError("validation provenance length does not match feature rows")
    return StrictSourceAwareSupportRows(
        schema="strict_source_aware_act_support_rows_v1",
        skill_name=spec.skill_name,
        model_token_key=spec.model_token_key,
        feature_order=_feature_order(spec),
        train_features=train_matrix,
        validation_features=validation_matrix,
        train_provenance=tuple(train_provenance),
        validation_provenance=tuple(validation_provenance),
        training_config_path=str(config_path),
        primitive_dataset_dir=str(dataset_dir),
        split_path=str(split_path),
        train_source_episode_ids=split.train_source_episode_ids,
        validation_source_episode_ids=split.validation_source_episode_ids,
        total_step_count=total_step_count,
        kept_step_count=int(train_matrix.shape[0] + validation_matrix.shape[0]),
        masked_step_count=masked_step_count,
    )


def fit_registered_support_candidates(
    rows: StrictSourceAwareSupportRows,
) -> dict[str, FittedSupportCandidate]:
    """Fit the pre-registered candidates using strict-train rows only.

    Validation rows are intentionally not an input to any fit calculation.  A
    caller may later assess validation and target matrices, but must never use
    those assessments to modify these returned parameters.
    """
    _validate_rows(rows)
    train = np.asarray(rows.train_features, dtype=np.float64)
    return {
        AXIS_P01_P99_V1: _fit_axis_candidate(
            candidate_id=AXIS_P01_P99_V1,
            feature_order=rows.feature_order,
            train_features=train,
            lower_quantile=0.01,
            upper_quantile=0.99,
        ),
        AXIS_P0005_P9995_V2: _fit_axis_candidate(
            candidate_id=AXIS_P0005_P9995_V2,
            feature_order=rows.feature_order,
            train_features=train,
            lower_quantile=0.0005,
            upper_quantile=0.9995,
        ),
        JOINT_REGULARIZED_MAHALANOBIS_P99_V2: _fit_regularized_mahalanobis_candidate(
            feature_order=rows.feature_order,
            train_features=train,
        ),
    }


def assess_support_candidate(
    candidate: FittedSupportCandidate,
    features: np.ndarray | Sequence[Sequence[float]],
) -> SupportCandidateAssessment:
    """Assess a numeric matrix without fitting or recalibrating a candidate."""
    feature = _coerce_feature_matrix(features, expected_dim=len(candidate.feature_order))
    if candidate.candidate_id in {AXIS_P01_P99_V1, AXIS_P0005_P9995_V2}:
        return _assess_axis_candidate(candidate, feature)
    if candidate.candidate_id == JOINT_REGULARIZED_MAHALANOBIS_P99_V2:
        return _assess_regularized_mahalanobis_candidate(candidate, feature)
    raise ValueError(f"unknown support candidate {candidate.candidate_id!r}")


def generate_frozen_obvious_ood(
    rows: StrictSourceAwareSupportRows,
) -> FrozenObviousOodReference:
    """Generate a deterministic validation-only obvious-OOD negative control.

    It uses no target rollout rows and no strict-train statistics: the anchor,
    span, sign pattern, and perturbation all come from ``validation_features``.
    Candidate fits remain independent strict-train operations.
    """
    _validate_rows(rows)
    anchor = np.asarray(rows.validation_features, dtype=np.float64)
    span = np.max(anchor, axis=0) - np.min(anchor, axis=0)
    scale = np.maximum(np.maximum(np.abs(anchor), span.reshape(1, -1)), 1.0)
    row_indices = np.arange(anchor.shape[0], dtype=np.int64).reshape(-1, 1)
    feature_indices = np.arange(anchor.shape[1], dtype=np.int64).reshape(1, -1)
    signs = np.where((row_indices + feature_indices) % 2 == 0, 1.0, -1.0)
    perturbation = FROZEN_OBVIOUS_OOD_MULTIPLIER * signs * scale
    feature = anchor + perturbation
    if not np.isfinite(feature).all():
        raise ValueError("frozen obvious-OOD construction produced non-finite values")
    return FrozenObviousOodReference(
        schema=FROZEN_OBVIOUS_OOD_SCHEMA,
        feature_order=rows.feature_order,
        anchor_partition="validation",
        multiplier=FROZEN_OBVIOUS_OOD_MULTIPLIER,
        anchor_features=_freeze_array(anchor),
        features=_freeze_array(feature),
        perturbation=_freeze_array(perturbation),
        anchor_provenance=rows.validation_provenance,
    )


def _fit_axis_candidate(
    *,
    candidate_id: str,
    feature_order: tuple[str, ...],
    train_features: np.ndarray,
    lower_quantile: float,
    upper_quantile: float,
) -> FittedSupportCandidate:
    lower = np.quantile(train_features, lower_quantile, axis=0)
    upper = np.quantile(train_features, upper_quantile, axis=0)
    return FittedSupportCandidate(
        candidate_id=candidate_id,
        feature_order=feature_order,
        fit_partition="strict_train",
        fit_row_count=int(train_features.shape[0]),
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
        lower=_freeze_array(lower),
        upper=_freeze_array(upper),
        mean=None,
        covariance=None,
        precision=None,
        regularization=None,
        threshold=0.0,
        threshold_kind="axis_interval_excess_zero",
    )


def _fit_regularized_mahalanobis_candidate(
    *,
    feature_order: tuple[str, ...],
    train_features: np.ndarray,
) -> FittedSupportCandidate:
    mean = np.mean(train_features, axis=0)
    centered = train_features - mean
    sample_count, feature_dim = centered.shape
    denominator = max(sample_count - 1, 1)
    covariance = (centered.T @ centered) / float(denominator)
    trace_scale = float(np.trace(covariance) / feature_dim)
    if not np.isfinite(trace_scale) or trace_scale < 0.0:
        raise ValueError("strict-train covariance trace is invalid")
    regularization = max(
        _MAHALANOBIS_RIDGE_TRACE_FRACTION * trace_scale,
        _MAHALANOBIS_RIDGE_FLOOR,
    )
    regularized_covariance = covariance + regularization * np.eye(feature_dim)
    precision = np.linalg.inv(regularized_covariance)
    train_scores = _squared_mahalanobis(centered, precision)
    threshold = float(np.quantile(train_scores, 0.99))
    return FittedSupportCandidate(
        candidate_id=JOINT_REGULARIZED_MAHALANOBIS_P99_V2,
        feature_order=feature_order,
        fit_partition="strict_train",
        fit_row_count=sample_count,
        lower_quantile=None,
        upper_quantile=None,
        lower=None,
        upper=None,
        mean=_freeze_array(mean),
        covariance=_freeze_array(regularized_covariance),
        precision=_freeze_array(precision),
        regularization=regularization,
        threshold=threshold,
        threshold_kind="train_p99_squared_distance",
    )


def _assess_axis_candidate(
    candidate: FittedSupportCandidate,
    feature: np.ndarray,
) -> SupportCandidateAssessment:
    lower = _required_candidate_vector(candidate.lower, label="axis lower")
    upper = _required_candidate_vector(candidate.upper, label="axis upper")
    if lower.shape != feature.shape[1:] or upper.shape != feature.shape[1:]:
        raise ValueError("axis candidate dimensions do not match assessment feature matrix")
    below = feature < lower.reshape(1, -1)
    above = feature > upper.reshape(1, -1)
    frame_in_support = ~(below | above).any(axis=1)
    excess = np.maximum(
        np.maximum(lower.reshape(1, -1) - feature, feature - upper.reshape(1, -1)),
        0.0,
    )
    scores = np.max(excess, axis=1)
    violations: list[tuple[SupportCandidateViolation, ...]] = []
    for row_index in range(feature.shape[0]):
        row: list[SupportCandidateViolation] = []
        for feature_index in np.flatnonzero(below[row_index] | above[row_index]):
            row.append(
                SupportCandidateViolation(
                    kind="below_axis_lower" if below[row_index, feature_index] else "above_axis_upper",
                    feature_index=int(feature_index),
                    field=candidate.feature_order[int(feature_index)],
                    value=float(feature[row_index, feature_index]),
                    lower=float(lower[feature_index]),
                    upper=float(upper[feature_index]),
                    score=float(scores[row_index]),
                    threshold=0.0,
                )
            )
        violations.append(tuple(row))
    return SupportCandidateAssessment(
        candidate_id=candidate.candidate_id,
        feature_order=candidate.feature_order,
        feature=_freeze_array(feature),
        frame_in_support=_freeze_array(frame_in_support.astype(bool)),
        scores=_freeze_array(scores),
        threshold=candidate.threshold,
        score_kind="maximum_axis_interval_excess",
        violations=tuple(violations),
    )


def _assess_regularized_mahalanobis_candidate(
    candidate: FittedSupportCandidate,
    feature: np.ndarray,
) -> SupportCandidateAssessment:
    mean = _required_candidate_vector(candidate.mean, label="Mahalanobis mean")
    precision = _required_candidate_matrix(candidate.precision, label="Mahalanobis precision")
    if mean.shape != feature.shape[1:] or precision.shape != (feature.shape[1], feature.shape[1]):
        raise ValueError("Mahalanobis candidate dimensions do not match assessment feature matrix")
    scores = _squared_mahalanobis(feature - mean.reshape(1, -1), precision)
    frame_in_support = scores <= candidate.threshold
    violations = tuple(
        ()
        if supported
        else (
            SupportCandidateViolation(
                kind="joint_squared_distance_above_threshold",
                feature_index=None,
                field=None,
                value=None,
                lower=None,
                upper=None,
                score=float(score),
                threshold=candidate.threshold,
            ),
        )
        for supported, score in zip(frame_in_support, scores, strict=True)
    )
    return SupportCandidateAssessment(
        candidate_id=candidate.candidate_id,
        feature_order=candidate.feature_order,
        feature=_freeze_array(feature),
        frame_in_support=_freeze_array(frame_in_support.astype(bool)),
        scores=_freeze_array(scores),
        threshold=candidate.threshold,
        score_kind="squared_regularized_mahalanobis_distance",
        violations=violations,
    )


def _read_mapping_yaml(path: Path, *, label: str) -> Mapping[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must contain a mapping")
    return payload


def _resolve_condition_spec(
    config: Mapping[str, Any],
    *,
    requested_skill_name: str | None,
) -> _ConditionSpec:
    policy = _required_mapping(config, "policy", label="training config")
    raw_keys = policy.get("low_dim_keys")
    if not isinstance(raw_keys, Sequence) or isinstance(raw_keys, (str, bytes)):
        raise ValueError("training policy low_dim_keys must be a sequence")
    keys = tuple(str(value) for value in raw_keys)
    matching_specs = [
        spec
        for spec in _CONDITION_SPECS.values()
        if spec.model_token_key in keys
    ]
    if len(matching_specs) != 1:
        raise ValueError(
            "training policy must contain exactly one conditioned Dig or Return token key"
        )
    spec = matching_specs[0]
    if requested_skill_name is not None:
        requested = str(requested_skill_name).strip().lower()
        if requested != spec.skill_name:
            raise ValueError(
                f"training config token key is for {spec.skill_name!r}, not {requested!r}"
            )
    expected_keys = ("qpos", "qvel", spec.model_token_key)
    if keys != expected_keys:
        raise ValueError(
            "support contract requires ordered low_dim_keys "
            f"{expected_keys!r}, got {keys!r}"
        )
    return spec


def _required_mapping(
    value: Mapping[str, Any],
    key: str,
    *,
    label: str,
) -> Mapping[str, Any]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{label} lacks mapping {key!r}")
    return result


def _required_path(value: Mapping[str, Any], key: str, *, label: str) -> Path:
    raw = str(value.get(key, "")).strip()
    if not raw:
        raise ValueError(f"{label} lacks {key!r}")
    return Path(raw).expanduser()


def _read_source_aware_split(split_path: Path, *, dataset_dir: Path) -> _SourceAwareSplit:
    payload = _read_mapping_yaml(split_path, label="source-aware split")
    if str(payload.get("split_policy", "")) != "source_identity_exact_allowlist_v1":
        raise ValueError("source-aware split policy mismatch")
    recorded_dataset_dir = _required_path(payload, "dataset_dir", label="source-aware split")
    if recorded_dataset_dir.resolve(strict=True) != dataset_dir:
        raise ValueError("source-aware split dataset_dir does not match training config")
    train_ids = _integer_tuple(payload.get("train_ids"), label="train_ids")
    validation_ids = _integer_tuple(payload.get("val_ids"), label="val_ids")
    if not train_ids or not validation_ids:
        raise ValueError("source-aware split must include non-empty train_ids and val_ids")
    if set(train_ids) & set(validation_ids):
        raise ValueError("source-aware split train and validation ids overlap")
    train_sources = _integer_tuple(
        payload.get("train_source_episode_ids"),
        label="train_source_episode_ids",
    )
    validation_sources = _integer_tuple(
        payload.get("val_source_episode_ids"),
        label="val_source_episode_ids",
    )
    if not train_sources or not validation_sources:
        raise ValueError("source-aware split must include train and validation sources")
    if set(train_sources) & set(validation_sources):
        raise ValueError("source-aware split train and validation sources overlap")
    allowed_sources = _integer_tuple(
        payload.get("allowed_source_episode_ids"),
        label="allowed_source_episode_ids",
    )
    if set(allowed_sources) != set(train_sources) | set(validation_sources):
        raise ValueError("source-aware split allowlist does not match train/validation sources")
    raw_source_mapping = payload.get("source_episode_id_by_primitive_episode_id")
    if not isinstance(raw_source_mapping, Mapping):
        raise ValueError("source-aware split source mapping is missing")
    source_mapping = {
        _integer(key, label="source map primitive id"): _source_id(
            value,
            label="source map episode id",
        )
        for key, value in raw_source_mapping.items()
    }
    required_ids = set(train_ids) | set(validation_ids)
    if not required_ids <= set(source_mapping):
        raise ValueError("source-aware split is missing primitive source mappings")
    for primitive_episode_id in train_ids:
        if source_mapping[primitive_episode_id] not in train_sources:
            raise ValueError("source-aware split train primitive maps outside train sources")
    for primitive_episode_id in validation_ids:
        if source_mapping[primitive_episode_id] not in validation_sources:
            raise ValueError("source-aware split validation primitive maps outside validation sources")
    return _SourceAwareSplit(
        train_ids=train_ids,
        validation_ids=validation_ids,
        train_source_episode_ids=train_sources,
        validation_source_episode_ids=validation_sources,
        source_by_primitive_episode_id=source_mapping,
    )


def _validate_partition_source(
    *,
    partition: str,
    primitive_episode_id: int,
    source_episode_id: int,
    expected_source_episode_id: int,
    split: _SourceAwareSplit,
) -> None:
    if partition == "train":
        if source_episode_id in split.validation_source_episode_ids:
            raise ValueError(
                f"train primitive {primitive_episode_id} contains validation source "
                f"episode {source_episode_id}"
            )
        if source_episode_id not in split.train_source_episode_ids:
            raise ValueError(
                f"train primitive {primitive_episode_id} source episode "
                f"{source_episode_id} is not in the train allowlist"
            )
    elif partition == "validation":
        if source_episode_id not in split.validation_source_episode_ids:
            raise ValueError(
                f"validation primitive {primitive_episode_id} source episode "
                f"{source_episode_id} is not in the validation allowlist"
            )
    else:
        raise AssertionError(f"unknown source partition {partition!r}")
    if source_episode_id != expected_source_episode_id:
        raise ValueError(
            f"primitive {primitive_episode_id} source metadata does not match split mapping"
        )


def _read_episode_support_inputs(
    handle: h5py.File,
    *,
    spec: _ConditionSpec,
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    required_paths = (
        "observations/qpos",
        "observations/qvel",
        spec.dataset_path,
        "action",
        DS_STEP_ID,
    )
    missing = [item for item in required_paths if item not in handle]
    if missing:
        raise KeyError(f"{path} is missing required support fields {missing!r}")
    qpos = np.asarray(handle["observations/qpos"][:], dtype=np.float64)
    qvel = np.asarray(handle["observations/qvel"][:], dtype=np.float64)
    token = np.asarray(handle[spec.dataset_path][:], dtype=np.float64)
    action = np.asarray(handle["action"][:], dtype=np.float64)
    step_ids = np.asarray(handle[DS_STEP_ID][:], dtype=np.int64).reshape(-1)
    count = int(qpos.shape[0])
    if qpos.shape != (count, 4) or qvel.shape != (count, 4):
        raise ValueError(f"{path} qpos/qvel must each have shape (T, 4)")
    if token.shape != (count, spec.token_dim):
        raise ValueError(f"{path} token must have shape (T, {spec.token_dim})")
    if action.shape != (count, 4) or step_ids.shape != (count,):
        raise ValueError(f"{path} action or step_id shape does not match qpos")
    if count < 1 or np.any(np.diff(step_ids) <= 0):
        raise ValueError(f"{path} must contain strictly increasing step_ids")
    mask = read_action_loss_mask(handle, expected_length=count, required=True)
    assert mask is not None
    feature = np.concatenate((qpos, qvel, token), axis=1)
    if not np.isfinite(feature).all() or not np.isfinite(action).all():
        raise ValueError(f"{path} contains non-finite action-supervised ACT inputs")
    return feature, step_ids, mask


def _source_episode_id(handle: h5py.File) -> int:
    if "metadata" not in handle:
        raise ValueError("primitive episode is missing metadata/source_episode_id")
    value = handle["metadata"].attrs.get("source_episode_id")
    if value is None:
        raise ValueError("primitive episode is missing metadata/source_episode_id")
    return _source_id(value, label="metadata/source_episode_id")


def _feature_order(spec: _ConditionSpec) -> tuple[str, ...]:
    return tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"{spec.model_token_key}[{index}]" for index in range(spec.token_dim)]
    )


def _validate_rows(rows: StrictSourceAwareSupportRows) -> None:
    if rows.skill_name not in _CONDITION_SPECS:
        raise ValueError(f"unsupported support skill {rows.skill_name!r}")
    spec = _CONDITION_SPECS[rows.skill_name]
    if rows.model_token_key != spec.model_token_key:
        raise ValueError("support rows model token key does not match skill")
    if rows.feature_order != _feature_order(spec):
        raise ValueError("support rows feature order does not match skill")
    for name, matrix, provenance in (
        ("train", rows.train_features, rows.train_provenance),
        ("validation", rows.validation_features, rows.validation_provenance),
    ):
        array = _coerce_feature_matrix(matrix, expected_dim=len(rows.feature_order))
        if array.shape[0] != len(provenance):
            raise ValueError(f"{name} support provenance does not match feature rows")
        if not all(item.partition == name for item in provenance):
            raise ValueError(f"{name} support provenance contains another partition")
    if set(rows.train_source_episode_ids) & set(rows.validation_source_episode_ids):
        raise ValueError("support rows train and validation source ids overlap")
    if any(
        item.source_episode_id not in rows.train_source_episode_ids
        for item in rows.train_provenance
    ):
        raise ValueError("train support provenance contains a non-train source")
    if any(
        item.source_episode_id not in rows.validation_source_episode_ids
        for item in rows.validation_provenance
    ):
        raise ValueError("validation support provenance contains a non-validation source")


def _coerce_feature_matrix(
    value: np.ndarray | Sequence[Sequence[float]],
    *,
    expected_dim: int,
) -> np.ndarray:
    feature = np.asarray(value, dtype=np.float64)
    if feature.ndim == 1:
        feature = feature.reshape(1, -1)
    if feature.ndim != 2 or feature.shape[1] != expected_dim:
        raise ValueError(
            f"support feature matrix must have shape (T, {expected_dim}), got {feature.shape}"
        )
    if feature.shape[0] < 1 or not np.isfinite(feature).all():
        raise ValueError("support feature matrix must be non-empty and finite")
    return feature


def _required_candidate_vector(value: np.ndarray | None, *, label: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"candidate is missing {label}")
    result = np.asarray(value, dtype=np.float64).reshape(-1)
    if not np.isfinite(result).all():
        raise ValueError(f"candidate {label} is non-finite")
    return result


def _required_candidate_matrix(value: np.ndarray | None, *, label: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"candidate is missing {label}")
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 2 or result.shape[0] != result.shape[1] or not np.isfinite(result).all():
        raise ValueError(f"candidate {label} is invalid")
    return result


def _squared_mahalanobis(centered: np.ndarray, precision: np.ndarray) -> np.ndarray:
    score = np.einsum("ni,ij,nj->n", centered, precision, centered, optimize=True)
    # Tiny negative values can occur from floating point roundoff with an SPD
    # precision matrix; they do not represent a negative squared distance.
    return np.maximum(score, 0.0)


def _freeze_array(value: np.ndarray) -> np.ndarray:
    result = np.asarray(value).copy()
    result.setflags(write=False)
    return result


def _float_list(value: np.ndarray) -> list[float]:
    return [float(item) for item in np.asarray(value, dtype=float).reshape(-1)]


def _integer_tuple(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    result = tuple(_integer(item, label=label) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if str(result) != str(value).strip() and not isinstance(value, (int, np.integer)):
        raise ValueError(f"{label} must be an integer")
    return result


def _source_id(value: Any, *, label: str) -> int:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    text = str(value).strip()
    if text.startswith("episode_"):
        text = text.removeprefix("episode_")
    return _integer(text, label=label)


__all__ = [
    "AXIS_P0005_P9995_V2",
    "AXIS_P01_P99_V1",
    "FROZEN_OBVIOUS_OOD_MULTIPLIER",
    "FROZEN_OBVIOUS_OOD_SCHEMA",
    "FrozenObviousOodReference",
    "FittedSupportCandidate",
    "JOINT_REGULARIZED_MAHALANOBIS_P99_V2",
    "SUPPORT_CANDIDATE_IDS",
    "StrictSourceAwareSupportRows",
    "SupportCandidateAssessment",
    "SupportCandidateViolation",
    "SupportRowProvenance",
    "assess_support_candidate",
    "fit_registered_support_candidates",
    "generate_frozen_obvious_ood",
    "load_strict_source_aware_support_rows",
]
