"""Train-only, source-diverse local complete-state support candidates for Dig.

This data-layer module never reads a target rollout or changes runtime support.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np
import yaml

from testbed.data.act_support_contract import (
    FrozenObviousOodReference,
    StrictSourceAwareSupportRows,
    SupportRowProvenance,
    generate_frozen_obvious_ood,
    load_strict_source_aware_support_rows,
)
from testbed.data.action_loss_mask import ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS
from testbed.data.local_state_neighbor_queries import (
    LOCAL_STATE_QUERY_BLOCK_SIZE,
    LOCAL_STATE_QUERY_ENGINE,
    LOCAL_STATE_REFERENCE_BLOCK_SIZE,
    LocalStateNeighborQuery,
    RobustTrainScale,
    linear_quantile,
    local_action_coherence,
    normalise_by_train_scale,
    query_neighbors_excluding_query_source,
    robust_train_scale,
    source_stratified_indices,
)
from testbed.data.schema import DS_STEP_ID

DIG_LOCAL_STATE_SUPPORT_SCHEMA = "dig_local_complete_state_support_v1"

LOCAL_STATE_DISTANCE_QUANTILE = 0.99
LOCAL_STATE_ACTION_COHERENCE_QUANTILE = 0.99
LOCAL_STATE_MAX_CALIBRATION_ROWS_PER_SOURCE = 128


@dataclass(frozen=True)
class DigLocalStateCandidateSpec:
    candidate_id: str
    k_neighbors: int
    min_distinct_source_episode_ids: int


DIG_LOCAL_STATE_CANDIDATE_SPECS = (
    DigLocalStateCandidateSpec("dig_local_complete_state_k8_sources2_v1", 8, 2),
    DigLocalStateCandidateSpec("dig_local_complete_state_k16_sources2_v1", 16, 2),
    DigLocalStateCandidateSpec("dig_local_complete_state_k32_sources3_v1", 32, 3),
)


class DigLocalStateSupportError(ValueError):
    pass


@dataclass(frozen=True)
class DigLocalStateSupportRows:
    schema: str
    feature_order: tuple[str, ...]
    train_features: np.ndarray
    validation_features: np.ndarray
    train_actions: np.ndarray
    validation_actions: np.ndarray
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
    action_loss_mask_scope: str
    _numeric_rows: StrictSourceAwareSupportRows

    @property
    def feature_dim(self) -> int:
        return len(self.feature_order)

    @property
    def action_dim(self) -> int:
        return int(self.train_actions.shape[1])

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "skill_name": "dig",
            "feature_order": list(self.feature_order),
            "feature_dim": self.feature_dim,
            "action_dim": self.action_dim,
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
            "action_loss_mask_scope": self.action_loss_mask_scope,
            "action_rows": "strict_train_and_validation_action_loss_mask_equals_1_only",
        }


@dataclass(frozen=True)
class LocalStateNeighbor:
    train_row_index: int
    distance: float
    provenance: SupportRowProvenance
    action: np.ndarray

    def as_dict(self) -> dict[str, Any]:
        return {
            "train_row_index": self.train_row_index,
            "distance": self.distance,
            "provenance": self.provenance.as_dict(),
            "action": _float_list(self.action),
        }


@dataclass(frozen=True)
class LocalStateCalibrationQuery:
    train_row_index: int
    provenance: SupportRowProvenance

    def as_dict(self) -> dict[str, Any]:
        return {
            "train_row_index": self.train_row_index,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class FittedDigLocalStateSupportCandidate:
    candidate_id: str
    feature_order: tuple[str, ...]
    fit_partition: Literal["strict_train"]
    fit_row_count: int
    k_neighbors: int
    min_distinct_source_episode_ids: int
    state_scale: RobustTrainScale
    action_scale: RobustTrainScale
    distance_threshold: float
    action_coherence_threshold: float
    action_coherence_axis_thresholds: np.ndarray
    distance_threshold_quantile: float
    action_coherence_threshold_quantile: float
    calibration_query_count: int
    calibration_source_episode_ids: tuple[int, ...]
    reference_index_sha256: str
    calibration_queries: tuple[LocalStateCalibrationQuery, ...]
    calibration_queries_meeting_source_requirement: int
    calibration_queries_failing_source_requirement: int
    train_features: np.ndarray
    train_actions: np.ndarray
    train_provenance: tuple[SupportRowProvenance, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "feature_order": list(self.feature_order),
            "fit_partition": self.fit_partition,
            "fit_row_count": self.fit_row_count,
            "k_neighbors": self.k_neighbors,
            "min_distinct_source_episode_ids": self.min_distinct_source_episode_ids,
            "state_scale": self.state_scale.as_dict(),
            "action_scale": self.action_scale.as_dict(),
            "distance_threshold": self.distance_threshold,
            "distance_threshold_kind": "strict_train_source_excluded_calibration_p99_kth_neighbor_distance",
            "distance_threshold_quantile": self.distance_threshold_quantile,
            "action_coherence_threshold": self.action_coherence_threshold,
            "action_coherence_threshold_kind": "strict_train_source_excluded_calibration_p99_max_normalized_action_distance_to_componentwise_median",
            "action_coherence_threshold_quantile": self.action_coherence_threshold_quantile,
            "action_coherence_axis_thresholds": _float_list(self.action_coherence_axis_thresholds),
            "action_coherence_axis_threshold_kind": "strict_train_source_excluded_calibration_p99_max_absolute_normalized_action_axis_distance_to_componentwise_median",
            "calibration_query_count": self.calibration_query_count,
            "calibration_source_episode_ids": list(self.calibration_source_episode_ids),
            "strict_train_reference_index_sha256": self.reference_index_sha256,
            "calibration_query_selection": {
                "kind": "deterministic_source_stratified_source_excluded",
                "row_selection": "per-source evenly-spaced row positions including first and last",
                "max_rows_per_source": LOCAL_STATE_MAX_CALIBRATION_ROWS_PER_SOURCE,
                "reference_population": "all strict-train rows outside the query source episode",
                "query_engine": LOCAL_STATE_QUERY_ENGINE,
                "query_block_size": LOCAL_STATE_QUERY_BLOCK_SIZE,
                "reference_block_size": LOCAL_STATE_REFERENCE_BLOCK_SIZE,
            },
            "calibration_queries_meeting_source_requirement": self.calibration_queries_meeting_source_requirement,
            "calibration_queries_failing_source_requirement": self.calibration_queries_failing_source_requirement,
            "calibration_queries": [item.as_dict() for item in self.calibration_queries],
        }


@dataclass(frozen=True)
class DigLocalStateNeighborCohort:
    """One frozen max-k query reusable by all candidates with one train index."""

    candidate_ids: tuple[str, ...]
    feature_order: tuple[str, ...]
    reference_index_sha256: str
    feature: np.ndarray
    query_source_episode_ids: np.ndarray
    max_k_neighbors: int
    neighbor_query: LocalStateNeighborQuery

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_ids": list(self.candidate_ids),
            "feature_order": list(self.feature_order),
            "reference_index_sha256": self.reference_index_sha256,
            "query_row_count": int(self.feature.shape[0]),
            "max_k_neighbors": self.max_k_neighbors,
            "query_engine": LOCAL_STATE_QUERY_ENGINE,
        }


@dataclass(frozen=True)
class LocalStateSupportViolation:
    kind: str
    value: float | int | None
    threshold: float | int | None

    def as_dict(self) -> dict[str, float | int | str | None]:
        return {"kind": self.kind, "value": self.value, "threshold": self.threshold}


@dataclass(frozen=True)
class DigLocalStateSupportAssessment:
    candidate_id: str
    feature_order: tuple[str, ...]
    feature: np.ndarray
    frame_in_support: np.ndarray
    kth_neighbor_distance: np.ndarray
    distinct_source_episode_counts: np.ndarray
    action_coherence_scores: np.ndarray
    action_coherence_axis_scores: np.ndarray
    action_coherence_centres: np.ndarray
    required_neighbors: int
    required_distinct_source_episode_ids: int
    distance_threshold: float
    action_coherence_threshold: float
    neighbors: tuple[tuple[LocalStateNeighbor, ...], ...]
    violations: tuple[tuple[LocalStateSupportViolation, ...], ...]

    @property
    def in_support_fraction(self) -> float:
        if not self.frame_in_support.size:
            return 0.0
        return float(np.mean(self.frame_in_support))

    def as_dict(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for index, row_neighbors in enumerate(self.neighbors):
            rows.append(
                {
                    "frame_index": index,
                    "in_support": bool(self.frame_in_support[index]),
                    "kth_neighbor_distance": float(self.kth_neighbor_distance[index]),
                    "distinct_source_episode_count": int(self.distinct_source_episode_counts[index]),
                    "action_coherence_score": float(self.action_coherence_scores[index]),
                    "action_coherence_axis_scores": _float_list(self.action_coherence_axis_scores[index]),
                    "action_coherence_centre": _float_list(self.action_coherence_centres[index]),
                    "neighbors": [item.as_dict() for item in row_neighbors],
                    "violations": [item.as_dict() for item in self.violations[index]],
                }
            )
        return {
            "candidate_id": self.candidate_id,
            "feature_order": list(self.feature_order),
            "required_neighbors": self.required_neighbors,
            "required_distinct_source_episode_ids": self.required_distinct_source_episode_ids,
            "distance_threshold": self.distance_threshold,
            "action_coherence_threshold": self.action_coherence_threshold,
            "frame_in_support": [bool(value) for value in self.frame_in_support],
            "kth_neighbor_distance": _float_list(self.kth_neighbor_distance),
            "distinct_source_episode_counts": [int(value) for value in self.distinct_source_episode_counts],
            "action_coherence_scores": _float_list(self.action_coherence_scores),
            "action_coherence_axis_scores": np.asarray(self.action_coherence_axis_scores, dtype=float).tolist(),
            "action_coherence_centres": np.asarray(self.action_coherence_centres, dtype=float).tolist(),
            "in_support_fraction": self.in_support_fraction,
            "query_engine": LOCAL_STATE_QUERY_ENGINE,
            "rows": rows,
        }


def load_strict_dig_local_state_support_rows(*, training_config_path: str | Path) -> DigLocalStateSupportRows:
    """Load strict Dig 18D state/action/provenance; no rollout is accepted."""

    numeric_rows = load_strict_source_aware_support_rows(
        training_config_path=training_config_path,
        skill_name="dig",
    )
    _validate_dig_numeric_rows(numeric_rows)
    config_path = Path(numeric_rows.training_config_path).resolve(strict=True)
    action_loss_mask_scope = _read_action_loss_mask_scope(config_path)
    if action_loss_mask_scope != ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS:
        raise DigLocalStateSupportError(
            "Dig local-state support requires train.action_loss_mask_scope="
            "'loss_sampling_stats'"
        )
    dataset_dir = Path(numeric_rows.primitive_dataset_dir).resolve(strict=True)
    train_actions = _read_actions_for_provenance(
        dataset_dir=dataset_dir,
        provenance=numeric_rows.train_provenance,
    )
    validation_actions = _read_actions_for_provenance(
        dataset_dir=dataset_dir,
        provenance=numeric_rows.validation_provenance,
    )
    return DigLocalStateSupportRows(
        schema=DIG_LOCAL_STATE_SUPPORT_SCHEMA,
        feature_order=numeric_rows.feature_order,
        train_features=_freeze_array(numeric_rows.train_features),
        validation_features=_freeze_array(numeric_rows.validation_features),
        train_actions=train_actions,
        validation_actions=validation_actions,
        train_provenance=numeric_rows.train_provenance,
        validation_provenance=numeric_rows.validation_provenance,
        training_config_path=str(config_path),
        primitive_dataset_dir=str(dataset_dir),
        split_path=numeric_rows.split_path,
        train_source_episode_ids=numeric_rows.train_source_episode_ids,
        validation_source_episode_ids=numeric_rows.validation_source_episode_ids,
        total_step_count=numeric_rows.total_step_count,
        kept_step_count=numeric_rows.kept_step_count,
        masked_step_count=numeric_rows.masked_step_count,
        action_loss_mask_scope=action_loss_mask_scope,
        _numeric_rows=numeric_rows,
    )


def fit_registered_dig_local_state_support_candidates(rows: DigLocalStateSupportRows) -> dict[str, FittedDigLocalStateSupportCandidate]:
    """Fit train-only p99 criteria from bounded source-excluded exact k-NN."""

    _validate_rows(rows)
    state_scale = robust_train_scale(rows.train_features)
    action_scale = robust_train_scale(rows.train_actions)
    source_ids = _source_ids(rows.train_provenance)
    reference_index_sha256 = _reference_index_sha256(rows)
    train_features = normalise_by_train_scale(rows.train_features, state_scale)
    calibration_indices = source_stratified_indices(
        source_ids,
        max_rows_per_source=LOCAL_STATE_MAX_CALIBRATION_ROWS_PER_SOURCE,
    )
    if not calibration_indices.size:
        raise DigLocalStateSupportError("strict Dig train has no calibration rows")
    max_k = max(spec.k_neighbors for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS)
    calibration_neighbors = query_neighbors_excluding_query_source(
        reference_features=train_features,
        query_features=train_features[calibration_indices],
        query_source_episode_ids=source_ids[calibration_indices],
        reference_source_episode_ids=source_ids,
        k_neighbors=max_k,
    )
    if np.any(calibration_neighbors.indices < 0):
        raise DigLocalStateSupportError(
            "strict Dig train lacks enough other-source rows for the pre-registered "
            f"maximum k={max_k} calibration query"
        )
    return {
        spec.candidate_id: _fit_candidate(
            spec=spec,
            rows=rows,
            state_scale=state_scale,
            action_scale=action_scale,
            reference_index_sha256=reference_index_sha256,
            calibration_indices=calibration_indices,
            calibration_neighbors=calibration_neighbors,
        )
        for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS
    }


def assess_dig_local_state_support_candidate(
    candidate: FittedDigLocalStateSupportCandidate,
    features: np.ndarray | Sequence[Sequence[float]],
    *,
    query_source_episode_ids: Sequence[int | None] | None = None,
) -> DigLocalStateSupportAssessment:
    """Assess one candidate; use a cohort API when assessing a family."""

    cohort = build_dig_local_state_neighbor_cohort(
        (candidate,),
        features,
        query_source_episode_ids=query_source_episode_ids,
    )
    return assess_dig_local_state_support_candidate_from_cohort(candidate, cohort)


def build_dig_local_state_neighbor_cohort(
    candidates: Mapping[str, FittedDigLocalStateSupportCandidate]
    | Sequence[FittedDigLocalStateSupportCandidate],
    features: np.ndarray | Sequence[Sequence[float]],
    *,
    query_source_episode_ids: Sequence[int | None] | None = None,
) -> DigLocalStateNeighborCohort:
    """Build one exact max-k query for compatible frozen candidates."""

    selected = tuple(candidates.values()) if isinstance(candidates, Mapping) else tuple(candidates)
    if not selected:
        raise DigLocalStateSupportError("local support cohort needs at least one candidate")
    for candidate in selected:
        _validate_candidate(candidate)
    reference = selected[0]
    if len({item.candidate_id for item in selected}) != len(selected):
        raise DigLocalStateSupportError("local support cohort candidate ids are duplicated")
    if any(not _shares_neighbor_index(reference, item) for item in selected[1:]):
        raise DigLocalStateSupportError("local support cohort candidates do not share one train index")
    feature = _coerce_feature_matrix(features, expected_dim=len(reference.feature_order))
    source_ids = _normalise_optional_source_ids(
        query_source_episode_ids,
        expected_count=feature.shape[0],
    )
    max_k = max(item.k_neighbors for item in selected)
    query = query_neighbors_excluding_query_source(
        reference_features=normalise_by_train_scale(reference.train_features, reference.state_scale),
        query_features=normalise_by_train_scale(feature, reference.state_scale),
        query_source_episode_ids=source_ids,
        reference_source_episode_ids=_source_ids(reference.train_provenance),
        k_neighbors=max_k,
    )
    return DigLocalStateNeighborCohort(
        candidate_ids=tuple(item.candidate_id for item in selected),
        feature_order=reference.feature_order,
        reference_index_sha256=reference.reference_index_sha256,
        feature=_freeze_array(feature),
        query_source_episode_ids=_freeze_array(source_ids),
        max_k_neighbors=max_k,
        neighbor_query=query,
    )


def assess_dig_local_state_support_candidate_from_cohort(
    candidate: FittedDigLocalStateSupportCandidate,
    cohort: DigLocalStateNeighborCohort,
) -> DigLocalStateSupportAssessment:
    """Evaluate one candidate from a compatible precomputed max-k query."""

    _validate_candidate(candidate)
    _validate_cohort(candidate, cohort)
    feature = cohort.feature
    query = cohort.neighbor_query
    rows: list[tuple[LocalStateNeighbor, ...]] = []
    violations: list[tuple[LocalStateSupportViolation, ...]] = []
    supported: list[bool] = []
    source_counts: list[int] = []
    action_scores: list[float] = []
    action_axis_scores: list[np.ndarray] = []
    action_centres: list[np.ndarray] = []
    kth_distances: list[float] = []
    for query_index, all_neighbor_indices in enumerate(query.indices):
        neighbor_indices = all_neighbor_indices[: candidate.k_neighbors]
        valid = neighbor_indices[neighbor_indices >= 0]
        distance_values = query.distances[query_index, : valid.size]
        row_neighbors = tuple(
            LocalStateNeighbor(
                train_row_index=int(index),
                distance=float(distance),
                provenance=candidate.train_provenance[int(index)],
                action=_freeze_array(candidate.train_actions[int(index)]),
            )
            for index, distance in zip(valid, distance_values, strict=True)
        )
        rows.append(row_neighbors)
        row_violations: list[LocalStateSupportViolation] = []
        if valid.size < candidate.k_neighbors:
            row_violations.append(
                LocalStateSupportViolation(
                    kind="insufficient_neighbors",
                    value=int(valid.size),
                    threshold=candidate.k_neighbors,
                )
            )
        distinct_sources = len(
            {candidate.train_provenance[int(index)].source_episode_id for index in valid}
        )
        source_counts.append(distinct_sources)
        if distinct_sources < candidate.min_distinct_source_episode_ids:
            row_violations.append(
                LocalStateSupportViolation(
                    kind="insufficient_distinct_source_episodes",
                    value=distinct_sources,
                    threshold=candidate.min_distinct_source_episode_ids,
                )
            )
        kth_distance = float(distance_values[-1]) if valid.size else float("inf")
        kth_distances.append(kth_distance)
        if kth_distance > candidate.distance_threshold:
            row_violations.append(
                LocalStateSupportViolation(
                    kind="kth_neighbor_distance_above_threshold",
                    value=kth_distance,
                    threshold=candidate.distance_threshold,
                )
            )
        coherence = local_action_coherence(
            candidate.train_actions[valid],
            candidate.action_scale,
        )
        action_scores.append(coherence.total_score)
        action_axis_scores.append(coherence.axis_scores)
        action_centres.append(coherence.centre)
        if coherence.total_score > candidate.action_coherence_threshold:
            row_violations.append(
                LocalStateSupportViolation(
                    kind="neighbor_actions_incoherent",
                    value=coherence.total_score,
                    threshold=candidate.action_coherence_threshold,
                )
            )
        for axis, (score, threshold) in enumerate(
            zip(
                coherence.axis_scores,
                candidate.action_coherence_axis_thresholds,
                strict=True,
            )
        ):
            if score > threshold:
                row_violations.append(
                    LocalStateSupportViolation(
                        kind=f"neighbor_action_axis_{axis}_incoherent",
                        value=float(score),
                        threshold=float(threshold),
                    )
                )
        violations.append(tuple(row_violations))
        supported.append(not row_violations)
    return DigLocalStateSupportAssessment(
        candidate_id=candidate.candidate_id,
        feature_order=candidate.feature_order,
        feature=_freeze_array(feature),
        frame_in_support=_freeze_array(np.asarray(supported, dtype=bool)),
        kth_neighbor_distance=_freeze_array(np.asarray(kth_distances, dtype=np.float64)),
        distinct_source_episode_counts=_freeze_array(
            np.asarray(source_counts, dtype=np.int64)
        ),
        action_coherence_scores=_freeze_array(np.asarray(action_scores, dtype=np.float64)),
        action_coherence_axis_scores=_freeze_array(
            np.stack(action_axis_scores, axis=0)
        ),
        action_coherence_centres=_freeze_array(np.stack(action_centres, axis=0)),
        required_neighbors=candidate.k_neighbors,
        required_distinct_source_episode_ids=candidate.min_distinct_source_episode_ids,
        distance_threshold=candidate.distance_threshold,
        action_coherence_threshold=candidate.action_coherence_threshold,
        neighbors=tuple(rows),
        violations=tuple(violations),
    )


def generate_frozen_dig_local_state_validation_ood(
    rows: DigLocalStateSupportRows,
) -> FrozenObviousOodReference:
    """Return the existing validation-derived numerical negative control."""

    _validate_rows(rows)
    return generate_frozen_obvious_ood(rows._numeric_rows)


def summarize_dig_local_state_support_feasibility(
    rows: DigLocalStateSupportRows,
    candidates: Mapping[str, FittedDigLocalStateSupportCandidate],
) -> dict[str, Any]:

    _validate_rows(rows)
    expected_ids = tuple(spec.candidate_id for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS)
    if tuple(candidates) != expected_ids:
        raise DigLocalStateSupportError("local Dig candidate family/order mismatch")
    source_counts = _source_row_counts(rows.train_provenance)
    return {
        "schema": DIG_LOCAL_STATE_SUPPORT_SCHEMA,
        "target_rollout_used_for_fit_or_summary": False,
        "fit_partition": "strict_train",
        "validation_partition": "held_out_source_disjoint",
        "train_row_count": int(rows.train_features.shape[0]),
        "validation_row_count": int(rows.validation_features.shape[0]),
        "train_source_row_counts": {str(key): value for key, value in source_counts.items()},
        "candidate_feasibility": {
            candidate_id: {
                "k_neighbors": candidate.k_neighbors,
                "min_distinct_source_episode_ids": (
                    candidate.min_distinct_source_episode_ids
                ),
                "calibration_query_count": candidate.calibration_query_count,
                "calibration_queries_meeting_source_requirement": (
                    candidate.calibration_queries_meeting_source_requirement
                ),
                "calibration_queries_failing_source_requirement": (
                    candidate.calibration_queries_failing_source_requirement
                ),
            }
            for candidate_id, candidate in candidates.items()
        },
        "query_engine": LOCAL_STATE_QUERY_ENGINE,
        "distance_definition": "robust_train_normalised_l2",
        "action_coherence_definition": (
            "maximum robust-normalised action distance to componentwise neighbour median"
        ),
    }


def _fit_candidate(
    *,
    spec: DigLocalStateCandidateSpec,
    rows: DigLocalStateSupportRows,
    state_scale: RobustTrainScale,
    action_scale: RobustTrainScale,
    reference_index_sha256: str,
    calibration_indices: np.ndarray,
    calibration_neighbors: LocalStateNeighborQuery,
) -> FittedDigLocalStateSupportCandidate:
    neighbor_indices = calibration_neighbors.indices[:, : spec.k_neighbors]
    neighbor_distances = calibration_neighbors.distances[:, : spec.k_neighbors]
    source_counts = np.asarray(
        [
            len(
                {
                    rows.train_provenance[int(index)].source_episode_id
                    for index in row
                    if index >= 0
                }
            )
            for row in neighbor_indices
        ],
        dtype=np.int64,
    )
    eligible = source_counts >= spec.min_distinct_source_episode_ids
    if not np.any(eligible):
        raise DigLocalStateSupportError(
            f"{spec.candidate_id} has no source-diverse strict-train calibration queries"
        )
    kth_distance = neighbor_distances[:, -1]
    coherence = tuple(
        local_action_coherence(rows.train_actions[row], action_scale) for row in neighbor_indices
    )
    coherence_total = np.asarray([item.total_score for item in coherence], dtype=np.float64)
    coherence_axis = np.stack([item.axis_scores for item in coherence], axis=0)
    if not np.isfinite(kth_distance[eligible]).all() or not np.isfinite(
        coherence_total[eligible]
    ).all():
        raise DigLocalStateSupportError("local-state calibration statistics are non-finite")
    return FittedDigLocalStateSupportCandidate(
        candidate_id=spec.candidate_id,
        feature_order=rows.feature_order,
        fit_partition="strict_train",
        fit_row_count=int(rows.train_features.shape[0]),
        k_neighbors=spec.k_neighbors,
        min_distinct_source_episode_ids=spec.min_distinct_source_episode_ids,
        state_scale=state_scale,
        action_scale=action_scale,
        distance_threshold=float(
            linear_quantile(kth_distance[eligible], LOCAL_STATE_DISTANCE_QUANTILE)
        ),
        action_coherence_threshold=float(
            linear_quantile(
                coherence_total[eligible], LOCAL_STATE_ACTION_COHERENCE_QUANTILE
            )
        ),
        action_coherence_axis_thresholds=_freeze_array(
            linear_quantile(
                coherence_axis[eligible],
                LOCAL_STATE_ACTION_COHERENCE_QUANTILE,
                axis=0,
            )
        ),
        distance_threshold_quantile=LOCAL_STATE_DISTANCE_QUANTILE,
        action_coherence_threshold_quantile=LOCAL_STATE_ACTION_COHERENCE_QUANTILE,
        calibration_query_count=int(calibration_neighbors.indices.shape[0]),
        calibration_source_episode_ids=tuple(sorted({item.source_episode_id for item in rows.train_provenance})),
        reference_index_sha256=reference_index_sha256,
        calibration_queries=tuple(
            LocalStateCalibrationQuery(
                train_row_index=int(index),
                provenance=rows.train_provenance[int(index)],
            )
            for index in calibration_indices
        ),
        calibration_queries_meeting_source_requirement=int(np.count_nonzero(eligible)),
        calibration_queries_failing_source_requirement=int(np.count_nonzero(~eligible)),
        train_features=_freeze_array(rows.train_features),
        train_actions=_freeze_array(rows.train_actions),
        train_provenance=rows.train_provenance,
    )


def _read_actions_for_provenance(
    *,
    dataset_dir: Path,
    provenance: Sequence[SupportRowProvenance],
) -> np.ndarray:
    cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    actions: list[np.ndarray] = []
    for item in provenance:
        cached = cache.get(item.primitive_episode_id)
        if cached is None:
            path = dataset_dir / f"episode_{item.primitive_episode_id}.hdf5"
            with h5py.File(path, "r") as handle:
                if "action" not in handle or DS_STEP_ID not in handle:
                    raise DigLocalStateSupportError(
                        f"{path} is missing action or {DS_STEP_ID}"
                    )
                episode_actions = np.asarray(handle["action"][:], dtype=np.float64)
                step_ids = np.asarray(handle[DS_STEP_ID][:], dtype=np.int64).reshape(-1)
            if episode_actions.ndim != 2 or episode_actions.shape[1] != 4:
                raise DigLocalStateSupportError(f"{path} action must have shape (T, 4)")
            if step_ids.shape != (episode_actions.shape[0],):
                raise DigLocalStateSupportError(f"{path} action and step_id lengths disagree")
            if not np.isfinite(episode_actions).all():
                raise DigLocalStateSupportError(f"{path} action contains non-finite values")
            cached = (episode_actions, step_ids)
            cache[item.primitive_episode_id] = cached
        episode_actions, step_ids = cached
        if not 0 <= item.step_index < episode_actions.shape[0]:
            raise DigLocalStateSupportError("support provenance step index is outside action")
        if int(step_ids[item.step_index]) != item.step_id:
            raise DigLocalStateSupportError("support provenance step id no longer matches action")
        actions.append(episode_actions[item.step_index])
    if not actions:
        raise DigLocalStateSupportError("strict Dig partition has no action-supervised actions")
    return _freeze_array(np.stack(actions, axis=0))


def _read_action_loss_mask_scope(config_path: Path) -> str:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise DigLocalStateSupportError("Dig training config must be a mapping")
    train = payload.get("train")
    if not isinstance(train, Mapping):
        raise DigLocalStateSupportError("Dig training config lacks train mapping")
    return str(train.get("action_loss_mask_scope", "")).strip()


def _validate_dig_numeric_rows(rows: StrictSourceAwareSupportRows) -> None:
    if rows.skill_name != "dig" or rows.model_token_key != "dig_cut_tokens":
        raise DigLocalStateSupportError("local support only accepts a Dig training config")
    if len(rows.feature_order) != 18:
        raise DigLocalStateSupportError("Dig local support requires complete 18D input")
    expected = tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"dig_cut_tokens[{index}]" for index in range(10)]
    )
    if rows.feature_order != expected:
        raise DigLocalStateSupportError("Dig local support feature order mismatch")


def _validate_rows(rows: DigLocalStateSupportRows) -> None:
    if rows.schema != DIG_LOCAL_STATE_SUPPORT_SCHEMA:
        raise DigLocalStateSupportError("Dig local-state support schema mismatch")
    if rows.action_loss_mask_scope != ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS:
        raise DigLocalStateSupportError("Dig local-state support mask scope mismatch")
    _validate_dig_numeric_rows(rows._numeric_rows)
    for label, feature, action, provenance, sources in (
        ("train", rows.train_features, rows.train_actions, rows.train_provenance, rows.train_source_episode_ids),
        ("validation", rows.validation_features, rows.validation_actions, rows.validation_provenance, rows.validation_source_episode_ids),
    ):
        matrix = _coerce_feature_matrix(feature, expected_dim=18)
        actions = _coerce_feature_matrix(action, expected_dim=4)
        if matrix.shape[0] != actions.shape[0] or matrix.shape[0] != len(provenance):
            raise DigLocalStateSupportError(f"{label} local-state arrays/provenance disagree")
        if any(item.partition != label for item in provenance):
            raise DigLocalStateSupportError(f"{label} provenance partition mismatch")
        if any(item.action_loss_mask != 1 for item in provenance):
            raise DigLocalStateSupportError(f"{label} contains an action_loss_mask=0 row")
        if any(item.source_episode_id not in sources for item in provenance):
            raise DigLocalStateSupportError(f"{label} source provenance lies outside split")
    if set(rows.train_source_episode_ids) & set(rows.validation_source_episode_ids):
        raise DigLocalStateSupportError("Dig local train/validation sources overlap")


def _validate_candidate(candidate: FittedDigLocalStateSupportCandidate) -> None:
    if candidate.fit_partition != "strict_train":
        raise DigLocalStateSupportError("local candidate was not fitted on strict_train")
    if candidate.candidate_id not in {
        item.candidate_id for item in DIG_LOCAL_STATE_CANDIDATE_SPECS
    }:
        raise DigLocalStateSupportError("unknown local Dig candidate")
    if candidate.k_neighbors < 1 or candidate.min_distinct_source_episode_ids < 1:
        raise DigLocalStateSupportError("local candidate neighbour/source requirements are invalid")
    if candidate.train_features.shape[0] != len(candidate.train_provenance):
        raise DigLocalStateSupportError("local candidate train provenance mismatch")
    if candidate.train_actions.shape != (candidate.train_features.shape[0], 4):
        raise DigLocalStateSupportError("local candidate train action shape mismatch")
    if candidate.train_features.shape[1] != len(candidate.feature_order):
        raise DigLocalStateSupportError("local candidate feature order mismatch")
    if not np.isfinite(candidate.distance_threshold) or candidate.distance_threshold < 0.0:
        raise DigLocalStateSupportError("local candidate distance threshold is invalid")
    if not np.isfinite(candidate.action_coherence_threshold) or candidate.action_coherence_threshold < 0.0:
        raise DigLocalStateSupportError("local candidate action threshold is invalid")
    axis_thresholds = np.asarray(candidate.action_coherence_axis_thresholds, dtype=float)
    if axis_thresholds.shape != (4,) or not np.isfinite(axis_thresholds).all() or np.any(axis_thresholds < 0.0):
        raise DigLocalStateSupportError("local candidate action-axis thresholds are invalid")


def _shares_neighbor_index(
    first: FittedDigLocalStateSupportCandidate,
    second: FittedDigLocalStateSupportCandidate,
) -> bool:
    return (
        first.feature_order == second.feature_order
        and first.fit_row_count == second.fit_row_count
        and first.reference_index_sha256 == second.reference_index_sha256
        and np.array_equal(first.state_scale.centre, second.state_scale.centre)
        and np.array_equal(first.state_scale.scale, second.state_scale.scale)
    )


def _validate_cohort(
    candidate: FittedDigLocalStateSupportCandidate,
    cohort: DigLocalStateNeighborCohort,
) -> None:
    if candidate.candidate_id not in cohort.candidate_ids:
        raise DigLocalStateSupportError("local support candidate is absent from cohort")
    if candidate.feature_order != cohort.feature_order:
        raise DigLocalStateSupportError("local support cohort feature order mismatch")
    if candidate.reference_index_sha256 != cohort.reference_index_sha256:
        raise DigLocalStateSupportError("local support cohort train index mismatch")
    if cohort.max_k_neighbors < candidate.k_neighbors:
        raise DigLocalStateSupportError("local support cohort lacks candidate k neighbours")
    if cohort.feature.shape[0] != cohort.query_source_episode_ids.shape[0]:
        raise DigLocalStateSupportError("local support cohort query source length mismatch")
    if cohort.neighbor_query.indices.shape != (
        cohort.feature.shape[0],
        cohort.max_k_neighbors,
    ) or cohort.neighbor_query.distances.shape != cohort.neighbor_query.indices.shape:
        raise DigLocalStateSupportError("local support cohort neighbor query shape mismatch")


def _coerce_feature_matrix(
    values: np.ndarray | Sequence[Sequence[float]],
    *,
    expected_dim: int | None,
) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2 or (expected_dim is not None and matrix.shape[1] != expected_dim):
        expected = "a two-dimensional finite matrix" if expected_dim is None else f"(T, {expected_dim})"
        raise DigLocalStateSupportError(
            f"local-state matrix must have shape {expected}, got {matrix.shape}"
        )
    if matrix.shape[0] < 1 or not np.isfinite(matrix).all():
        raise DigLocalStateSupportError("local-state matrix must be non-empty and finite")
    return matrix


def _normalise_optional_source_ids(
    values: Sequence[int | None] | None,
    *,
    expected_count: int,
) -> np.ndarray:
    if values is None:
        return np.full(expected_count, -1, dtype=np.int64)
    if len(values) != expected_count:
        raise DigLocalStateSupportError("query source episode ids do not match query row count")
    result = np.empty(expected_count, dtype=np.int64)
    for index, value in enumerate(values):
        if value is None:
            result[index] = -1
        elif isinstance(value, (int, np.integer)) and int(value) >= 0:
            result[index] = int(value)
        else:
            raise DigLocalStateSupportError("query source episode id must be non-negative integer or None")
    return result


def _source_ids(provenance: Sequence[SupportRowProvenance]) -> np.ndarray:
    return np.asarray([item.source_episode_id for item in provenance], dtype=np.int64)


def _source_row_counts(provenance: Sequence[SupportRowProvenance]) -> dict[int, int]:
    values, counts = np.unique(_source_ids(provenance), return_counts=True)
    return {int(value): int(count) for value, count in zip(values, counts, strict=True)}


def _reference_index_sha256(rows: DigLocalStateSupportRows) -> str:
    digest = hashlib.sha256()
    digest.update("\x1f".join(rows.feature_order).encode("utf-8"))
    for matrix in (rows.train_features, rows.train_actions):
        values = np.ascontiguousarray(np.asarray(matrix, dtype=np.float64))
        digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
        digest.update(values.tobytes())
    for item in rows.train_provenance:
        digest.update(
            f"{item.primitive_episode_id}:{item.source_episode_id}:{item.step_index}:{item.step_id}:{item.action_loss_mask};".encode(
                "ascii"
            )
        )
    return digest.hexdigest()


def _freeze_array(values: np.ndarray | Sequence[float] | Sequence[Sequence[float]]) -> np.ndarray:
    result = np.asarray(values).copy()
    result.setflags(write=False)
    return result


def _float_list(values: np.ndarray | Sequence[float]) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]
