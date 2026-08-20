"""Compare a read-only Dig target segment with frozen support populations.

Population loading is intentionally owned by
``dig_support_outlier_population``. This module has no source-HDF5 fitting
path: it only measures a target matrix against already frozen references.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.dig_support_outlier_population import (
    DIG_FEATURE_ORDER,
    DIG_QVEL1_FEATURE_INDEX,
    DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA,
    DigSupportOutlierDistributionError,
    DigSupportOutlierDistributionReferences,
    Qvel1Population,
    Qvel1RowProvenance,
    load_dig_support_outlier_distribution_references,
    validate_dig_support_outlier_distribution_references,
)

_QVEL1_FIELD = "qvel[1]"


@dataclass(frozen=True)
class DigSupportOutlierSegmentAnalysis:
    """Read-only result for one target feature matrix."""

    references: DigSupportOutlierDistributionReferences
    target_features: np.ndarray
    frames: tuple[Mapping[str, Any], ...]
    target_qvel1_interval: tuple[float, float]
    held_validation_distribution: Mapping[str, Any]
    qvel1_same_numeric_range_populations: Mapping[str, Mapping[str, Any]]
    qvel1_v1_outside_numeric_range_populations: Mapping[str, Mapping[str, Any]]
    segment_qvel1_excursion_measurement: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        support = self.references.v1_support
        return {
            "schema": DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA,
            "evidence_scope": "read_only_target_comparison_against_preloaded_references",
            "target_rollout_used_for_fit_or_selection": False,
            "candidate_selection_performed": False,
            "runtime_support_change": False,
            "reference_lineage": {
                "training_config_path": self.references.training_config_path,
                "split_path": self.references.split_path,
                "dig_dataset_dir": self.references.dig_dataset_dir,
                "excluded_dig_primitive_missing_episode_ids": list(
                    self.references.excluded_dig_primitive_missing_episode_ids
                ),
            },
            "v1_support": {
                "candidate_id": "axis_p01_p99_v1",
                "fit_partition": "strict_train",
                "feature_order": list(support.feature_order),
                "p01": _float_list(support.p01),
                "p99": _float_list(support.p99),
                "strict_train_row_count": support.kept_step_count,
                "action_loss_mask_scope": "action_loss_mask_equals_1_only",
            },
            "target_feature_matrix": {
                "shape": [int(value) for value in self.target_features.shape],
                "read_only": not bool(self.target_features.flags.writeable),
                "qvel1_field": _QVEL1_FIELD,
                "qvel1_interval": {
                    "lower": self.target_qvel1_interval[0],
                    "upper": self.target_qvel1_interval[1],
                },
            },
            "frames": [dict(frame) for frame in self.frames],
            "held_validation_distribution": dict(self.held_validation_distribution),
            "qvel1_same_numeric_range_populations": {
                name: dict(summary)
                for name, summary in self.qvel1_same_numeric_range_populations.items()
            },
            "qvel1_v1_outside_numeric_range_populations": {
                name: dict(summary)
                for name, summary in self.qvel1_v1_outside_numeric_range_populations.items()
            },
            "segment_qvel1_excursion_measurement": dict(
                self.segment_qvel1_excursion_measurement
            ),
            "decision_boundary": "no_threshold_or_runtime_decision_is_made_here",
        }


def analyze_dig_support_outlier_segment(
    *,
    references: DigSupportOutlierDistributionReferences,
    target_features: np.ndarray,
) -> DigSupportOutlierSegmentAnalysis:
    """Measure a frozen target without fitting, selecting, or widening support."""

    _validate_references(references)
    target = _readonly_matrix(target_features, width=len(DIG_FEATURE_ORDER))
    support = references.v1_support
    train = np.asarray(references.strict_rows.train_features, dtype=np.float64)
    lower = np.asarray(support.p01, dtype=np.float64)
    upper = np.asarray(support.p99, dtype=np.float64)
    scale = np.where(np.abs(upper - lower) > 0.0, np.abs(upper - lower), 1.0)
    frames = tuple(
        _frame_evidence(
            index=index,
            feature=feature,
            train=train,
            lower=lower,
            upper=upper,
            scale=scale,
            feature_order=support.feature_order,
            train_provenance=references.strict_rows.train_provenance,
        )
        for index, feature in enumerate(target)
    )
    qvel1 = target[:, DIG_QVEL1_FEATURE_INDEX]
    interval = (float(np.min(qvel1)), float(np.max(qvel1)))
    qvel1_outside = np.logical_or(
        qvel1 < lower[DIG_QVEL1_FEATURE_INDEX],
        qvel1 > upper[DIG_QVEL1_FEATURE_INDEX],
    )
    outside_values = qvel1[qvel1_outside]
    return DigSupportOutlierSegmentAnalysis(
        references=references,
        target_features=target,
        frames=frames,
        target_qvel1_interval=interval,
        held_validation_distribution=_held_validation_summary(
            references=references,
            interval=interval,
        ),
        qvel1_same_numeric_range_populations=_population_summaries(
            references=references,
            interval=interval,
        ),
        qvel1_v1_outside_numeric_range_populations=(
            _population_summaries(
                references=references,
                interval=(float(np.min(outside_values)), float(np.max(outside_values))),
            )
            if outside_values.size
            else {}
        ),
        segment_qvel1_excursion_measurement=_excursion_measurement(
            qvel1=qvel1,
            lower=float(lower[DIG_QVEL1_FEATURE_INDEX]),
            upper=float(upper[DIG_QVEL1_FEATURE_INDEX]),
        ),
    )


def _frame_evidence(
    *,
    index: int,
    feature: np.ndarray,
    train: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    scale: np.ndarray,
    feature_order: Sequence[str],
    train_provenance: Sequence[Any],
) -> dict[str, Any]:
    deltas = (train - feature.reshape(1, -1)) / scale.reshape(1, -1)
    squared = np.sum(deltas * deltas, axis=1)
    nearest_index = int(np.argmin(squared))
    nearest = train[nearest_index]
    outside = np.logical_or(feature < lower, feature > upper)
    value = float(feature[DIG_QVEL1_FEATURE_INDEX])
    qvel_status = (
        "below_p01"
        if value < lower[DIG_QVEL1_FEATURE_INDEX]
        else "above_p99"
        if value > upper[DIG_QVEL1_FEATURE_INDEX]
        else "in_p01_p99"
    )
    return {
        "frame_index": index,
        "qpos": _float_list(feature[:4]),
        "qvel": _float_list(feature[4:8]),
        "token": _float_list(feature[8:]),
        "frame_v1_in_support": not bool(np.any(outside)),
        "v1_outside_fields": [
            field for field, rejected in zip(feature_order, outside, strict=True) if rejected
        ],
        "qvel1_v1_status": qvel_status,
        "nearest_strict_train": {
            "train_row_index": nearest_index,
            "provenance": train_provenance[nearest_index].as_dict(),
            "feature": _float_list(nearest),
            "qvel1_abs_delta": float(abs(nearest[DIG_QVEL1_FEATURE_INDEX] - value)),
            "qvel1_only_nearest_abs_delta": float(
                np.min(abs(train[:, DIG_QVEL1_FEATURE_INDEX] - value))
            ),
            "full_feature_v1_span_normalised_l2": float(np.sqrt(squared[nearest_index])),
            "full_feature_raw_l2": float(np.linalg.norm(nearest - feature)),
            "metric": "v1_axis_span_normalised_l2_fixed_diagnostic_only",
        },
    }


def _population_summaries(
    *,
    references: DigSupportOutlierDistributionReferences,
    interval: tuple[float, float],
) -> dict[str, Mapping[str, Any]]:
    populations = (
        references.strict_train_qvel1,
        references.held_validation_qvel1,
        references.strict_train_masked_qvel1,
        references.excluded_dig_primitive_qvel1,
        *references.other_primitive_qvel1,
    )
    return {
        population.name: population.range_summary(lower=interval[0], upper=interval[1])
        for population in populations
    }


def _held_validation_summary(
    *,
    references: DigSupportOutlierDistributionReferences,
    interval: tuple[float, float],
) -> dict[str, Any]:
    values = np.asarray(references.held_validation_qvel1.values, dtype=np.float64)
    features = np.asarray(references.strict_rows.validation_features, dtype=np.float64)
    lower = np.asarray(references.v1_support.p01, dtype=np.float64)
    upper = np.asarray(references.v1_support.p99, dtype=np.float64)
    in_support = np.logical_and(features >= lower, features <= upper).all(axis=1)
    summary = references.held_validation_qvel1.range_summary(
        lower=interval[0], upper=interval[1]
    )
    summary.update(
        {
            "partition": "held_validation",
            "read_only_presentation": True,
            "used_for_fit_or_selection": False,
            "v1_full_feature_in_support_row_count": int(np.count_nonzero(in_support)),
            "v1_full_feature_in_support_fraction": float(np.mean(in_support)),
            "qvel1_p01": float(np.quantile(values, 0.01)),
            "qvel1_p50": float(np.quantile(values, 0.50)),
            "qvel1_p99": float(np.quantile(values, 0.99)),
        }
    )
    return summary


def _excursion_measurement(
    *,
    qvel1: np.ndarray,
    lower: float,
    upper: float,
) -> dict[str, Any]:
    outside = np.logical_or(qvel1 < lower, qvel1 > upper)
    runs = _runs(outside)
    indices = np.flatnonzero(outside)
    if not runs:
        topology = "no_v1_qvel1_excursion"
    elif len(runs) == 1 and runs[0][2] == 1:
        topology = "one_single_frame_run"
    elif len(runs) == 1:
        topology = "one_contiguous_multi_frame_run"
    else:
        topology = "multiple_separated_runs"
    deltas = np.abs(np.diff(qvel1))
    return {
        "qvel1_field": _QVEL1_FIELD,
        "v1_lower": lower,
        "v1_upper": upper,
        "qvel1_v1_outside_frame_indices": [int(value) for value in indices],
        "qvel1_v1_outside_frame_count": int(indices.size),
        "qvel1_v1_outside_fraction": float(indices.size / qvel1.size),
        "qvel1_v1_runs": [
            {"start_frame_index": start, "end_frame_index": end, "length": length}
            for start, end, length in runs
        ],
        "qvel1_v1_longest_contiguous_run": max(
            (length for _, _, length in runs), default=0
        ),
        "v1_excursion_topology": topology,
        "target_qvel1_min": float(np.min(qvel1)),
        "target_qvel1_max": float(np.max(qvel1)),
        "target_qvel1_max_abs_adjacent_delta": (
            0.0 if not deltas.size else float(np.max(deltas))
        ),
        "target_qvel1_median_abs_adjacent_delta": (
            0.0 if not deltas.size else float(np.median(deltas))
        ),
        "interpretation_boundary": (
            "Descriptive frozen-v1 count/run measurement; not a new anomaly threshold."
        ),
    }


def _runs(mask: np.ndarray) -> tuple[tuple[int, int, int], ...]:
    result: list[tuple[int, int, int]] = []
    start: int | None = None
    for index, active in enumerate(mask.tolist()):
        if active and start is None:
            start = index
        elif not active and start is not None:
            result.append((start, index - 1, index - start))
            start = None
    if start is not None:
        result.append((start, int(mask.size) - 1, int(mask.size) - start))
    return tuple(result)


def _validate_references(references: DigSupportOutlierDistributionReferences) -> None:
    if references.schema != DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA:
        raise DigSupportOutlierDistributionError("Dig OOS reference schema mismatch")
    validate_dig_support_outlier_distribution_references(
        strict_rows=references.strict_rows,
        v1_support=references.v1_support,
    )


def _readonly_matrix(target_features: np.ndarray, *, width: int) -> np.ndarray:
    if not isinstance(target_features, np.ndarray) or target_features.flags.writeable:
        raise DigSupportOutlierDistributionError(
            "target feature matrix must be a read-only numpy array"
        )
    matrix = np.asarray(target_features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] != width:
        raise DigSupportOutlierDistributionError(
            f"target feature matrix must have shape (T, {width})"
        )
    if not np.isfinite(matrix).all():
        raise DigSupportOutlierDistributionError("target feature matrix is non-finite")
    result = matrix.copy()
    result.setflags(write=False)
    return result


def _float_list(values: np.ndarray | Sequence[float]) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


__all__ = [
    "DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA",
    "DigSupportOutlierDistributionError",
    "DigSupportOutlierDistributionReferences",
    "DigSupportOutlierSegmentAnalysis",
    "Qvel1Population",
    "Qvel1RowProvenance",
    "analyze_dig_support_outlier_segment",
    "load_dig_support_outlier_distribution_references",
]
