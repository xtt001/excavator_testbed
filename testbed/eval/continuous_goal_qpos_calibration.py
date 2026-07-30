"""Source-grouped normalization, OOD, and conformal qpos calibration."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.continuous_goal_qpos_paths import (
    PATH_PROGRESS_POINT_COUNT,
    QPOS_DIM,
)

CONFORMAL_HELDOUT_SOURCE_IDS = (33, 34)
CONFORMAL_HELDOUT_SOURCE_COUNTS = ((33, 29), (34, 30))
CONFORMAL_HELDOUT_SAMPLE_COUNT = 59
CONFORMAL_COVERAGE_LEVEL = 0.95
SOURCE_GROUPED_FOLD_COUNT = 5
OOD_THRESHOLD_RULE = "leave_one_source_out_p99"
OOD_MAX_STANDARDIZED_DISTANCE = 100.0


class CalibrationContractError(ValueError):
    """Raised for split leakage or incomplete predictor calibration."""


@dataclass(frozen=True)
class SourceGroupedFold:
    """One source-disjoint member fold."""

    fold_index: int
    train_source_ids: tuple[int, ...]
    validation_source_ids: tuple[int, ...]


@dataclass(frozen=True)
class FeatureNormalization:
    """Immutable feature statistics fitted on training sources only."""

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    lineage_sha256: str

    @classmethod
    def fit(
        cls,
        features: Any,
        *,
        feature_names: Sequence[str],
    ) -> FeatureNormalization:
        matrix = _feature_matrix(features)
        names = tuple(str(name) for name in feature_names)
        if len(names) != matrix.shape[1] or len(set(names)) != len(names):
            raise CalibrationContractError(
                "feature_names must uniquely cover every feature column"
            )
        mean = np.mean(matrix, axis=0, dtype=np.float64)
        scale = np.std(matrix, axis=0, dtype=np.float64)
        scale = np.where(scale > 1.0e-12, scale, 1.0)
        lineage = _normalization_sha256(names, mean, scale)
        mean.setflags(write=False)
        scale.setflags(write=False)
        return cls(
            feature_names=names,
            mean=mean,
            scale=scale,
            lineage_sha256=lineage,
        )

    def transform(self, features: Any) -> np.ndarray:
        array = np.asarray(features, dtype=np.float64)
        if array.shape[-1:] != (len(self.feature_names),):
            raise CalibrationContractError("normalization feature dimension mismatch")
        if not np.all(np.isfinite(array)):
            raise CalibrationContractError("normalization inputs must be finite")
        return (array - self.mean) / self.scale

    def computed_lineage_sha256(self) -> str:
        return _normalization_sha256(
            self.feature_names,
            self.mean,
            self.scale,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "lineage_sha256": self.lineage_sha256,
        }


@dataclass(frozen=True)
class LosoOODCalibration:
    """LOSO p99 support threshold over standardized source centroids."""

    source_ids: tuple[int, ...]
    source_centroids: np.ndarray
    loso_distance_samples: np.ndarray
    training_sample_count: int
    threshold: float
    threshold_rule: str
    lineage_sha256: str

    def score(
        self,
        feature: Any,
        *,
        normalization: FeatureNormalization,
    ) -> float:
        vector = np.asarray(feature, dtype=np.float64).reshape(-1)
        if vector.shape != (len(normalization.feature_names),):
            raise CalibrationContractError("OOD feature dimension mismatch")
        standardized = normalization.transform(vector)
        distances = np.linalg.norm(
            self.source_centroids - standardized[None, :],
            axis=1,
        ) / math.sqrt(float(vector.size))
        return float(np.min(distances))

    def computed_lineage_sha256(self) -> str:
        return _ood_sha256(
            source_ids=self.source_ids,
            source_centroids=self.source_centroids,
            loso_distance_samples=self.loso_distance_samples,
            training_sample_count=self.training_sample_count,
            threshold=self.threshold,
            threshold_rule=self.threshold_rule,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_ids": list(self.source_ids),
            "source_centroids": self.source_centroids.tolist(),
            "loso_distance_samples": self.loso_distance_samples.tolist(),
            "training_sample_count": self.training_sample_count,
            "threshold": self.threshold,
            "threshold_rule": self.threshold_rule,
            "lineage_sha256": self.lineage_sha256,
        }


@dataclass(frozen=True)
class ConformalQposCalibration:
    """Per-progress, per-joint 95% absolute-error bounds."""

    absolute_error_bound: np.ndarray
    coverage_level: float
    source_ids: tuple[int, ...]
    source_sample_counts: tuple[tuple[int, int], ...]
    calibration_sample_count: int
    lineage_sha256: str

    def computed_lineage_sha256(self) -> str:
        return _conformal_sha256(
            absolute_error_bound=self.absolute_error_bound,
            coverage_level=self.coverage_level,
            source_ids=self.source_ids,
            source_sample_counts=self.source_sample_counts,
            calibration_sample_count=self.calibration_sample_count,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "absolute_error_bound": self.absolute_error_bound.tolist(),
            "coverage_level": self.coverage_level,
            "source_ids": list(self.source_ids),
            "source_sample_counts": [
                [source_id, count] for source_id, count in self.source_sample_counts
            ],
            "calibration_sample_count": self.calibration_sample_count,
            "lineage_sha256": self.lineage_sha256,
        }


def build_source_grouped_folds(
    source_ids: Sequence[int],
    *,
    fold_count: int = SOURCE_GROUPED_FOLD_COUNT,
    conformal_source_ids: Sequence[int] = CONFORMAL_HELDOUT_SOURCE_IDS,
) -> tuple[SourceGroupedFold, ...]:
    """Assign whole training sources to one of five validation folds."""

    if (
        isinstance(fold_count, bool)
        or not isinstance(fold_count, int)
        or fold_count != SOURCE_GROUPED_FOLD_COUNT
    ):
        raise CalibrationContractError(
            "continuous qpos predictor v1 is fixed to five source folds"
        )
    parsed = tuple(_source_id(value) for value in source_ids)
    heldout = tuple(sorted({_source_id(value) for value in conformal_source_ids}))
    if heldout != CONFORMAL_HELDOUT_SOURCE_IDS:
        raise CalibrationContractError(
            "conformal calibration sources are fixed to 33 and 34"
        )
    observed = set(parsed)
    if not set(heldout).issubset(observed):
        raise CalibrationContractError(
            "source inventory must include conformal sources 33 and 34"
        )
    training_sources = tuple(sorted(observed - set(heldout)))
    if len(training_sources) < SOURCE_GROUPED_FOLD_COUNT:
        raise CalibrationContractError(
            "source-grouped predictor training requires at least five "
            "non-conformal sources"
        )
    fold_sources = tuple(
        tuple(
            source
            for index, source in enumerate(training_sources)
            if index % SOURCE_GROUPED_FOLD_COUNT == fold_index
        )
        for fold_index in range(SOURCE_GROUPED_FOLD_COUNT)
    )
    folds: list[SourceGroupedFold] = []
    for fold_index, validation_sources in enumerate(fold_sources):
        train_sources = tuple(
            source for source in training_sources if source not in validation_sources
        )
        if not validation_sources or not train_sources:
            raise CalibrationContractError(
                "every source-grouped fold must have train and validation sources"
            )
        folds.append(
            SourceGroupedFold(
                fold_index=fold_index,
                train_source_ids=train_sources,
                validation_source_ids=validation_sources,
            )
        )
    return tuple(folds)


def fit_loso_ood_calibration(
    *,
    features: Any,
    source_ids: Sequence[int],
    normalization: FeatureNormalization,
) -> LosoOODCalibration:
    """Fit the p99 leave-one-source-out standardized feature distance."""

    matrix = _feature_matrix(features)
    sources = np.asarray([_source_id(value) for value in source_ids], dtype=np.int64)
    if sources.shape != (matrix.shape[0],):
        raise CalibrationContractError("OOD source_ids must align with feature rows")
    if any(source in CONFORMAL_HELDOUT_SOURCE_IDS for source in sources):
        raise CalibrationContractError(
            "OOD fitting must not include held-out sources 33 or 34"
        )
    unique_sources = tuple(int(value) for value in np.unique(sources))
    if len(unique_sources) < 2:
        raise CalibrationContractError(
            "LOSO OOD calibration requires at least two training sources"
        )
    standardized = normalization.transform(matrix)
    centroids = np.vstack(
        [np.mean(standardized[sources == source], axis=0) for source in unique_sources]
    )
    loso_distances: list[float] = []
    dimension_scale = math.sqrt(float(matrix.shape[1]))
    for row, source in zip(standardized, sources, strict=True):
        other = centroids[np.asarray(unique_sources, dtype=np.int64) != source]
        loso_distances.append(
            float(np.min(np.linalg.norm(other - row[None, :], axis=1)))
            / dimension_scale
        )
    distance_samples = np.asarray(loso_distances, dtype=np.float64)
    threshold = float(
        np.quantile(
            distance_samples,
            0.99,
            method="higher",
        )
    )
    if not math.isfinite(threshold) or threshold < 0.0:
        raise CalibrationContractError("LOSO OOD threshold is invalid")
    rule = OOD_THRESHOLD_RULE
    lineage = _ood_sha256(
        source_ids=unique_sources,
        source_centroids=centroids,
        loso_distance_samples=distance_samples,
        training_sample_count=matrix.shape[0],
        threshold=threshold,
        threshold_rule=rule,
    )
    centroids.setflags(write=False)
    distance_samples.setflags(write=False)
    return LosoOODCalibration(
        source_ids=unique_sources,
        source_centroids=centroids,
        loso_distance_samples=distance_samples,
        training_sample_count=matrix.shape[0],
        threshold=threshold,
        threshold_rule=rule,
        lineage_sha256=lineage,
    )


def fit_conformal_qpos_calibration(
    *,
    absolute_residuals: Any,
    source_ids: Sequence[int],
    coverage_level: float = CONFORMAL_COVERAGE_LEVEL,
) -> ConformalQposCalibration:
    """Fit a finite-sample 95% absolute-residual conformal bound."""

    residuals = np.asarray(absolute_residuals, dtype=np.float64)
    expected_suffix = (PATH_PROGRESS_POINT_COUNT, QPOS_DIM)
    if (
        residuals.ndim != 3
        or residuals.shape[1:] != expected_suffix
        or residuals.shape[0] == 0
        or not np.all(np.isfinite(residuals))
        or np.any(residuals < 0.0)
    ):
        raise CalibrationContractError(
            "conformal residuals must have finite non-negative shape (N, 64, 4)"
        )
    sources = tuple(_source_id(value) for value in source_ids)
    if len(sources) != residuals.shape[0]:
        raise CalibrationContractError(
            "conformal source_ids must align with residual rows"
        )
    unique_sources = tuple(sorted(set(sources)))
    source_counts = tuple(
        (source_id, sources.count(source_id)) for source_id in unique_sources
    )
    if (
        unique_sources != CONFORMAL_HELDOUT_SOURCE_IDS
        or source_counts != CONFORMAL_HELDOUT_SOURCE_COUNTS
        or residuals.shape[0] != CONFORMAL_HELDOUT_SAMPLE_COUNT
    ):
        raise CalibrationContractError(
            "conformal calibration requires exactly 59 held-out samples: "
            "source 33 count 29 and source 34 count 30"
        )
    if (
        isinstance(coverage_level, bool)
        or not isinstance(coverage_level, (int, float))
        or float(coverage_level) != CONFORMAL_COVERAGE_LEVEL
    ):
        raise CalibrationContractError(
            "continuous qpos conformal coverage is fixed to 0.95"
        )
    sample_count = residuals.shape[0]
    rank = min(
        sample_count,
        int(math.ceil((sample_count + 1) * CONFORMAL_COVERAGE_LEVEL)),
    )
    bounds = np.sort(residuals, axis=0)[rank - 1]
    lineage = _conformal_sha256(
        absolute_error_bound=bounds,
        coverage_level=CONFORMAL_COVERAGE_LEVEL,
        source_ids=unique_sources,
        source_sample_counts=source_counts,
        calibration_sample_count=sample_count,
    )
    bounds.setflags(write=False)
    return ConformalQposCalibration(
        absolute_error_bound=bounds,
        coverage_level=CONFORMAL_COVERAGE_LEVEL,
        source_ids=unique_sources,
        source_sample_counts=source_counts,
        calibration_sample_count=sample_count,
        lineage_sha256=lineage,
    )


def combined_calibration_sha256(
    *,
    ood: LosoOODCalibration,
    conformal: ConformalQposCalibration,
) -> str:
    """Lock both support and uncertainty calibration into one lineage."""

    return _canonical_sha256(
        {
            "ood_lineage_sha256": ood.lineage_sha256,
            "conformal_lineage_sha256": conformal.lineage_sha256,
        }
    )


def predictor_normalization_lineage_sha256(
    *,
    ood_normalization: FeatureNormalization,
    members: Sequence[Any],
) -> str:
    """Bind the OOD transform and every member inference transform."""

    return _canonical_sha256(
        {
            "ood_normalization_sha256": (ood_normalization.lineage_sha256),
            "member_normalization_sha256": [
                {
                    "seed": _strict_nonnegative_int(
                        member.seed,
                        label="member.seed",
                    ),
                    "sha256": member.normalization.lineage_sha256,
                }
                for member in members
            ],
        }
    )


def validate_qpos_predictor_semantics(
    *,
    members: Sequence[Any],
    folds: Sequence[SourceGroupedFold],
    feature_names: Sequence[str],
    ood_normalization: FeatureNormalization,
    ood: LosoOODCalibration,
    conformal: ConformalQposCalibration | None,
) -> None:
    """Validate fixed split, calibration, and preprocessing semantics."""

    names = tuple(str(value) for value in feature_names)
    if not names or len(names) != len(set(names)):
        raise CalibrationContractError("predictor feature schema is invalid")
    _validate_normalization(ood_normalization, feature_names=names)
    if conformal is None:
        raise CalibrationContractError("predictor conformal calibration missing")
    if (
        isinstance(conformal.coverage_level, bool)
        or conformal.coverage_level != CONFORMAL_COVERAGE_LEVEL
        or conformal.source_ids != CONFORMAL_HELDOUT_SOURCE_IDS
        or conformal.source_sample_counts != CONFORMAL_HELDOUT_SOURCE_COUNTS
        or _strict_positive_int(
            conformal.calibration_sample_count,
            label="conformal calibration sample count",
        )
        != CONFORMAL_HELDOUT_SAMPLE_COUNT
        or conformal.absolute_error_bound.shape != (PATH_PROGRESS_POINT_COUNT, QPOS_DIM)
        or not np.all(np.isfinite(conformal.absolute_error_bound))
        or np.any(conformal.absolute_error_bound < 0.0)
        or conformal.computed_lineage_sha256() != conformal.lineage_sha256
    ):
        raise CalibrationContractError(
            "predictor conformal semantics require 95 percent coverage "
            "and source counts 33=29, 34=30"
        )

    source_ids = tuple(_source_id(value) for value in ood.source_ids)
    distances = np.asarray(ood.loso_distance_samples, dtype=np.float64)
    training_count = _strict_positive_int(
        ood.training_sample_count,
        label="OOD training sample count",
    )
    expected_threshold = (
        float(np.quantile(distances, 0.99, method="higher"))
        if distances.shape == (training_count,)
        and np.all(np.isfinite(distances))
        and np.all(distances >= 0.0)
        else math.nan
    )
    if (
        source_ids != tuple(sorted(set(source_ids)))
        or len(source_ids) < 2
        or set(source_ids) & set(CONFORMAL_HELDOUT_SOURCE_IDS)
        or ood.threshold_rule != OOD_THRESHOLD_RULE
        or ood.source_centroids.shape != (len(source_ids), len(names))
        or not np.all(np.isfinite(ood.source_centroids))
        or not math.isfinite(float(ood.threshold))
        or isinstance(ood.threshold, bool)
        or float(ood.threshold) < 0.0
        or float(ood.threshold) > OOD_MAX_STANDARDIZED_DISTANCE
        or float(ood.threshold) != expected_threshold
        or ood.computed_lineage_sha256() != ood.lineage_sha256
    ):
        raise CalibrationContractError(
            "predictor OOD semantics require finite training-source LOSO p99"
        )

    member_rows = tuple(members)
    fold_rows = tuple(folds)
    if len(member_rows) != 5 or len(fold_rows) != 5:
        raise CalibrationContractError(
            "predictor fold/member inventory must contain five entries"
        )
    training_sources = set(source_ids)
    validation_counts = {source: 0 for source in source_ids}
    for expected_index, (member, fold) in enumerate(
        zip(member_rows, fold_rows, strict=True)
    ):
        fold_index = _strict_nonnegative_int(
            fold.fold_index,
            label="fold index",
        )
        member_seed = _strict_nonnegative_int(
            member.seed,
            label="member seed",
        )
        train = tuple(_source_id(value) for value in fold.train_source_ids)
        validation = tuple(_source_id(value) for value in fold.validation_source_ids)
        if (
            fold_index != expected_index
            or member_seed != expected_index
            or train != tuple(sorted(set(train)))
            or validation != tuple(sorted(set(validation)))
            or not train
            or not validation
            or set(train) & set(validation)
            or set(train) | set(validation) != training_sources
            or tuple(member.train_source_ids) != train
            or tuple(member.validation_source_ids) != validation
        ):
            raise CalibrationContractError(
                "predictor fold/member source ownership is invalid"
            )
        _validate_normalization(member.normalization, feature_names=names)
        for source in validation:
            validation_counts[source] += 1
    if set(validation_counts.values()) != {1}:
        raise CalibrationContractError(
            "each training source must own exactly one validation fold"
        )


def _validate_normalization(
    value: FeatureNormalization,
    *,
    feature_names: tuple[str, ...],
) -> None:
    if (
        not isinstance(value, FeatureNormalization)
        or value.feature_names != feature_names
        or value.mean.shape != (len(feature_names),)
        or value.scale.shape != (len(feature_names),)
        or not np.all(np.isfinite(value.mean))
        or not np.all(np.isfinite(value.scale))
        or np.any(value.scale <= 0.0)
        or value.computed_lineage_sha256() != value.lineage_sha256
    ):
        raise CalibrationContractError("predictor normalization semantics are invalid")


def _feature_matrix(value: Any) -> np.ndarray:
    try:
        matrix = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise CalibrationContractError(
            "features must be a finite two-dimensional matrix"
        ) from exc
    if (
        matrix.ndim != 2
        or matrix.shape[0] == 0
        or matrix.shape[1] == 0
        or not np.all(np.isfinite(matrix))
    ):
        raise CalibrationContractError(
            "features must be a finite two-dimensional matrix"
        )
    return matrix


def _source_id(value: Any) -> int:
    return _strict_nonnegative_int(value, label="source id")


def _strict_nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise CalibrationContractError(f"{label} must be a non-negative integer")
    parsed = int(value)
    if parsed < 0:
        raise CalibrationContractError(f"{label} must be a non-negative integer")
    return parsed


def _strict_positive_int(value: Any, *, label: str) -> int:
    parsed = _strict_nonnegative_int(value, label=label)
    if parsed <= 0:
        raise CalibrationContractError(f"{label} must be a positive integer")
    return parsed


def _normalization_sha256(
    feature_names: Sequence[str],
    mean: Any,
    scale: Any,
) -> str:
    return _canonical_sha256(
        {
            "feature_names": list(feature_names),
            "mean": np.asarray(mean, dtype=np.float64).tolist(),
            "scale": np.asarray(scale, dtype=np.float64).tolist(),
        }
    )


def _ood_sha256(
    *,
    source_ids: Sequence[int],
    source_centroids: Any,
    loso_distance_samples: Any,
    training_sample_count: int,
    threshold: float,
    threshold_rule: str,
) -> str:
    return _canonical_sha256(
        {
            "source_ids": list(source_ids),
            "source_centroids": np.asarray(
                source_centroids,
                dtype=np.float64,
            ).tolist(),
            "loso_distance_samples": np.asarray(
                loso_distance_samples,
                dtype=np.float64,
            ).tolist(),
            "training_sample_count": _strict_positive_int(
                training_sample_count,
                label="training_sample_count",
            ),
            "threshold": float(threshold),
            "threshold_rule": str(threshold_rule),
        }
    )


def _conformal_sha256(
    *,
    absolute_error_bound: Any,
    coverage_level: float,
    source_ids: Sequence[int],
    source_sample_counts: Sequence[Sequence[int]],
    calibration_sample_count: int,
) -> str:
    return _canonical_sha256(
        {
            "absolute_error_bound": np.asarray(
                absolute_error_bound,
                dtype=np.float64,
            ).tolist(),
            "coverage_level": float(coverage_level),
            "source_ids": list(source_ids),
            "source_sample_counts": [
                [
                    _source_id(item[0]),
                    _strict_positive_int(
                        item[1],
                        label="source_sample_count",
                    ),
                ]
                for item in source_sample_counts
            ],
            "calibration_sample_count": _strict_positive_int(
                calibration_sample_count,
                label="calibration_sample_count",
            ),
        }
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CONFORMAL_COVERAGE_LEVEL",
    "CONFORMAL_HELDOUT_SAMPLE_COUNT",
    "CONFORMAL_HELDOUT_SOURCE_COUNTS",
    "CONFORMAL_HELDOUT_SOURCE_IDS",
    "OOD_MAX_STANDARDIZED_DISTANCE",
    "OOD_THRESHOLD_RULE",
    "SOURCE_GROUPED_FOLD_COUNT",
    "CalibrationContractError",
    "ConformalQposCalibration",
    "FeatureNormalization",
    "LosoOODCalibration",
    "SourceGroupedFold",
    "build_source_grouped_folds",
    "combined_calibration_sha256",
    "fit_conformal_qpos_calibration",
    "fit_loso_ood_calibration",
    "predictor_normalization_lineage_sha256",
    "validate_qpos_predictor_semantics",
]
