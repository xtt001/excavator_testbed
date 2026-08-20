"""Target-free held-validation selection for frozen local Dig support."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.act_support_contract import (
    FrozenObviousOodReference,
    SupportRowProvenance,
)
from testbed.data.dig_local_state_support import (
    DIG_LOCAL_STATE_CANDIDATE_SPECS,
    DIG_LOCAL_STATE_SUPPORT_SCHEMA,
    LOCAL_STATE_ACTION_COHERENCE_QUANTILE,
    LOCAL_STATE_DISTANCE_QUANTILE,
    DigLocalStateCandidateSpec,
    DigLocalStateNeighborCohort,
    DigLocalStateSupportAssessment,
    DigLocalStateSupportError,
    DigLocalStateSupportRows,
    FittedDigLocalStateSupportCandidate,
    assess_dig_local_state_support_candidate_from_cohort,
    build_dig_local_state_neighbor_cohort,
    fit_registered_dig_local_state_support_candidates,
    generate_frozen_dig_local_state_validation_ood,
    summarize_dig_local_state_support_feasibility,
)

DIG_LOCAL_STATE_SUPPORT_VALIDATION_SCHEMA = "dig_local_complete_state_validation_v1"
DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION = "support_contract_v2_dig_local_state_v1"

VALIDATION_NORMAL_COVERAGE_MIN = 0.99
FROZEN_OBVIOUS_OOD_REJECTION_MIN = 0.99


class DigLocalStateSupportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DigLocalStateCandidateValidation:
    candidate_id: str
    fixed_order: int
    validation_normal_coverage: float
    validation_distance_coverage: float
    validation_neighbor_count_coverage: float
    validation_source_diversity_coverage: float
    validation_action_coherence_coverage: float
    validation_action_axis_coherence_coverage: float
    frozen_obvious_ood_rejection: float
    validation_frozen_predicate_verified: bool
    frozen_obvious_ood_predicate_verified: bool
    validation_normal_coverage_passed: bool
    frozen_obvious_ood_rejection_passed: bool

    @property
    def qualified(self) -> bool:
        return (
            self.validation_frozen_predicate_verified
            and self.frozen_obvious_ood_predicate_verified
            and self.validation_normal_coverage
            >= VALIDATION_NORMAL_COVERAGE_MIN
            and self.frozen_obvious_ood_rejection
            >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
        )

    @property
    def qualification_status(self) -> str:
        if self.qualified:
            return "qualified"
        failures: list[str] = []
        if not self.validation_frozen_predicate_verified:
            failures.append("validation_local_predicate")
        if not self.frozen_obvious_ood_predicate_verified:
            failures.append("obvious_ood_local_predicate")
        if not self.validation_normal_coverage_passed:
            failures.append("validation_coverage")
        if not self.frozen_obvious_ood_rejection_passed:
            failures.append("obvious_ood_rejection")
        return "rejected_" + "_and_".join(failures)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "fixed_order": self.fixed_order,
            "validation_normal_coverage": self.validation_normal_coverage,
            "validation_distance_coverage": self.validation_distance_coverage,
            "validation_neighbor_count_coverage": self.validation_neighbor_count_coverage,
            "validation_source_diversity_coverage": self.validation_source_diversity_coverage,
            "validation_action_coherence_coverage": self.validation_action_coherence_coverage,
            "validation_action_axis_coherence_coverage": self.validation_action_axis_coherence_coverage,
            "frozen_obvious_ood_rejection": self.frozen_obvious_ood_rejection,
            "validation_frozen_predicate_verified": self.validation_frozen_predicate_verified,
            "frozen_obvious_ood_predicate_verified": self.frozen_obvious_ood_predicate_verified,
            "validation_normal_coverage_passed": self.validation_normal_coverage_passed,
            "frozen_obvious_ood_rejection_passed": self.frozen_obvious_ood_rejection_passed,
            "qualified": self.qualified,
            "qualification_status": self.qualification_status,
        }


def run_dig_local_state_support_validation(
    *,
    rows: DigLocalStateSupportRows,
) -> dict[str, Any]:
    """Select from strict-train candidates using held validation only."""

    _validate_rows(rows)
    try:
        candidates = fit_registered_dig_local_state_support_candidates(rows)
    except DigLocalStateSupportError as exc:
        raise DigLocalStateSupportValidationError(str(exc)) from exc
    _validate_candidate_family(candidates, rows=rows)

    try:
        obvious_ood = generate_frozen_dig_local_state_validation_ood(rows)
    except DigLocalStateSupportError as exc:
        raise DigLocalStateSupportValidationError(str(exc)) from exc
    _validate_obvious_ood(obvious_ood, rows=rows)

    validation_source_ids = _source_ids(rows.validation_provenance)
    validation_cohort = _build_cohort(
        candidates,
        rows.validation_features,
        query_source_episode_ids=validation_source_ids,
    )
    obvious_ood_cohort = _build_cohort(
        candidates,
        obvious_ood.features,
        query_source_episode_ids=_source_ids(obvious_ood.anchor_provenance),
    )
    evaluations: list[DigLocalStateCandidateValidation] = []
    candidate_records: list[dict[str, Any]] = []
    for fixed_order, spec in enumerate(DIG_LOCAL_STATE_CANDIDATE_SPECS):
        candidate = candidates[spec.candidate_id]
        validation_assessment = _assess_from_cohort(
            candidate,
            validation_cohort,
        )
        obvious_ood_assessment = _assess_from_cohort(
            candidate,
            obvious_ood_cohort,
        )
        validation_predicate_verified = _validate_assessment(
            candidate,
            validation_assessment,
            expected_row_count=rows.validation_features.shape[0],
            label="held Dig validation",
        )
        obvious_ood_predicate_verified = _validate_assessment(
            candidate,
            obvious_ood_assessment,
            expected_row_count=obvious_ood.features.shape[0],
            label="frozen Dig validation obvious-OOD",
        )

        validation_normal_coverage = validation_assessment.in_support_fraction
        obvious_ood_rejection = _rejection_fraction(obvious_ood_assessment)
        record = DigLocalStateCandidateValidation(
            candidate_id=candidate.candidate_id,
            fixed_order=fixed_order,
            validation_normal_coverage=validation_normal_coverage,
            validation_distance_coverage=_distance_coverage(
                validation_assessment,
                candidate,
            ),
            validation_neighbor_count_coverage=_neighbor_count_coverage(
                validation_assessment,
                candidate,
            ),
            validation_source_diversity_coverage=_source_diversity_coverage(
                validation_assessment,
                candidate,
            ),
            validation_action_coherence_coverage=_action_coherence_coverage(
                validation_assessment,
                candidate,
            ),
            validation_action_axis_coherence_coverage=(
                _action_axis_coherence_coverage(validation_assessment, candidate)
            ),
            frozen_obvious_ood_rejection=obvious_ood_rejection,
            validation_frozen_predicate_verified=validation_predicate_verified,
            frozen_obvious_ood_predicate_verified=obvious_ood_predicate_verified,
            validation_normal_coverage_passed=(
                validation_normal_coverage >= VALIDATION_NORMAL_COVERAGE_MIN
            ),
            frozen_obvious_ood_rejection_passed=(
                obvious_ood_rejection >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
            ),
        )
        evaluations.append(record)
        candidate_records.append(
            {
                **record.as_dict(),
                "definition": _compact_candidate_definition(candidate),
                "support_predicate": _support_predicate_description(candidate),
                "validation_assessment": _compact_assessment_summary(
                    validation_assessment,
                    candidate=candidate,
                    predicate_verified=validation_predicate_verified,
                ),
                "frozen_obvious_ood_assessment": _compact_assessment_summary(
                    obvious_ood_assessment,
                    candidate=candidate,
                    predicate_verified=obvious_ood_predicate_verified,
                ),
            }
        )

    selected = select_dig_local_state_support_candidate(evaluations)
    return {
        "schema": DIG_LOCAL_STATE_SUPPORT_VALIDATION_SCHEMA,
        "support_contract_version": DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION,
        "primitive": "dig",
        "status": "completed" if selected is not None else "support_contract_not_selected",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "runtime_support_change": False,
        "target_rollout_used_for_selection": False,
        "selection_input_scope": "strict_train_and_held_validation_only",
        "data_schema": DIG_LOCAL_STATE_SUPPORT_SCHEMA,
        "candidate_family": {
            "kind": "local_complete_state_robust_scaled_nearest_neighbour",
            "candidate_ids_in_fixed_order": [
                spec.candidate_id for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS
            ],
            "specifications": [
                {
                    "candidate_id": spec.candidate_id,
                    "k_neighbors": spec.k_neighbors,
                    "min_distinct_source_episode_ids": (
                        spec.min_distinct_source_episode_ids
                    ),
                }
                for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS
            ],
            "state_distance": "strict_train_robust_scaled_complete_18d_l2",
            "action_coherence": (
                "strict_train_robust_scaled_max_neighbour_action_distance_to_median"
            ),
            "thresholds": {
                "distance_train_calibration_quantile": LOCAL_STATE_DISTANCE_QUANTILE,
                "action_coherence_train_calibration_quantile": (
                    LOCAL_STATE_ACTION_COHERENCE_QUANTILE
                ),
            },
        },
        "selection_metrics": {
            "validation_normal_coverage_min": VALIDATION_NORMAL_COVERAGE_MIN,
            "frozen_obvious_ood_rejection_min": FROZEN_OBVIOUS_OOD_REJECTION_MIN,
            "normal_support_requires": [
                "k_neighbours_present",
                "kth_neighbour_distance_at_or_below_strict_train_threshold",
                "minimum_distinct_source_episodes",
                "neighbour_expert_action_coherence",
                "neighbour_expert_action_axis_coherence",
            ],
            "selection": (
                "qualified candidates: highest frozen_obvious_ood_rejection, "
                "then highest validation_normal_coverage, then fixed family order"
            ),
        },
        "source_separation": _source_separation(rows),
        "strict_train_feasibility": summarize_dig_local_state_support_feasibility(
            rows,
            candidates,
        ),
        "validation_neighbor_cohort": validation_cohort.as_dict(),
        "frozen_obvious_ood_neighbor_cohort": obvious_ood_cohort.as_dict(),
        "frozen_obvious_ood": obvious_ood.as_dict(),
        "candidates": candidate_records,
        "selected_candidate_id": None if selected is None else selected.candidate_id,
        "selection_status": "selected" if selected is not None else "not_selected",
    }


def select_dig_local_state_support_candidate(
    evaluations: Sequence[DigLocalStateCandidateValidation],
) -> DigLocalStateCandidateValidation | None:
    _validate_evaluations(evaluations)
    qualified = [item for item in evaluations if item.qualified]
    if not qualified:
        return None
    return min(
        qualified,
        key=lambda item: (
            -item.frozen_obvious_ood_rejection,
            -item.validation_normal_coverage,
            item.fixed_order,
        ),
    )


def _build_cohort(
    candidates: Mapping[str, FittedDigLocalStateSupportCandidate],
    features: np.ndarray,
    *,
    query_source_episode_ids: tuple[int, ...],
) -> DigLocalStateNeighborCohort:
    try:
        return build_dig_local_state_neighbor_cohort(
            candidates,
            features,
            query_source_episode_ids=query_source_episode_ids,
        )
    except DigLocalStateSupportError as exc:
        raise DigLocalStateSupportValidationError(str(exc)) from exc


def _assess_from_cohort(
    candidate: FittedDigLocalStateSupportCandidate,
    cohort: DigLocalStateNeighborCohort,
) -> DigLocalStateSupportAssessment:
    try:
        return assess_dig_local_state_support_candidate_from_cohort(candidate, cohort)
    except DigLocalStateSupportError as exc:
        raise DigLocalStateSupportValidationError(str(exc)) from exc


def _validate_rows(rows: DigLocalStateSupportRows) -> None:
    if rows.schema != DIG_LOCAL_STATE_SUPPORT_SCHEMA:
        raise DigLocalStateSupportValidationError("Dig local-state row schema mismatch")
    if rows.feature_dim != 18 or len(rows.feature_order) != 18:
        raise DigLocalStateSupportValidationError(
            "Dig local-state validation requires a complete 18D feature state"
        )
    if rows.action_dim != 4:
        raise DigLocalStateSupportValidationError(
            "Dig local-state validation requires four-dimensional expert actions"
        )
    train_sources = set(rows.train_source_episode_ids)
    validation_sources = set(rows.validation_source_episode_ids)
    if not train_sources or not validation_sources:
        raise DigLocalStateSupportValidationError(
            "Dig local-state validation requires non-empty train and validation sources"
        )
    overlap = sorted(train_sources & validation_sources)
    if overlap:
        raise DigLocalStateSupportValidationError(
            f"Dig local train/validation source episode ids overlap: {overlap}"
        )
    _validate_partition(
        features=rows.train_features,
        actions=rows.train_actions,
        provenance=rows.train_provenance,
        allowed_source_ids=train_sources,
        expected_partition="train",
        label="strict-train Dig local states",
    )
    _validate_partition(
        features=rows.validation_features,
        actions=rows.validation_actions,
        provenance=rows.validation_provenance,
        allowed_source_ids=validation_sources,
        expected_partition="validation",
        label="held Dig local states",
    )


def _validate_partition(
    *,
    features: np.ndarray,
    actions: np.ndarray,
    provenance: Sequence[SupportRowProvenance],
    allowed_source_ids: set[int],
    expected_partition: str,
    label: str,
) -> None:
    feature_matrix = np.asarray(features, dtype=np.float64)
    action_matrix = np.asarray(actions, dtype=np.float64)
    if feature_matrix.ndim != 2 or feature_matrix.shape[1] != 18:
        raise DigLocalStateSupportValidationError(f"{label} feature shape is invalid")
    if action_matrix.shape != (feature_matrix.shape[0], 4):
        raise DigLocalStateSupportValidationError(f"{label} action shape is invalid")
    if feature_matrix.shape[0] == 0 or not np.isfinite(feature_matrix).all():
        raise DigLocalStateSupportValidationError(f"{label} features are empty or non-finite")
    if not np.isfinite(action_matrix).all():
        raise DigLocalStateSupportValidationError(f"{label} actions are non-finite")
    if len(provenance) != feature_matrix.shape[0]:
        raise DigLocalStateSupportValidationError(f"{label} provenance length disagrees")
    if any(item.partition != expected_partition for item in provenance):
        raise DigLocalStateSupportValidationError(f"{label} provenance partition disagrees")
    if any(int(item.action_loss_mask) != 1 for item in provenance):
        raise DigLocalStateSupportValidationError(
            f"{label} contains a non-action-supervised row"
        )
    observed_sources = {int(item.source_episode_id) for item in provenance}
    if not observed_sources or not observed_sources <= allowed_source_ids:
        raise DigLocalStateSupportValidationError(
            f"{label} provenance sources disagree with the declared split"
        )


def _validate_candidate_family(
    candidates: Mapping[str, FittedDigLocalStateSupportCandidate],
    *,
    rows: DigLocalStateSupportRows,
) -> None:
    expected_ids = tuple(item.candidate_id for item in DIG_LOCAL_STATE_CANDIDATE_SPECS)
    if tuple(candidates) != expected_ids:
        raise DigLocalStateSupportValidationError(
            "Dig local candidate family does not match the pre-registered order"
        )
    train_sources = set(rows.train_source_episode_ids)
    validation_sources = set(rows.validation_source_episode_ids)
    reference_index_hashes: set[str] = set()
    for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS:
        candidate = candidates[spec.candidate_id]
        _validate_candidate(
            candidate,
            spec=spec,
            rows=rows,
            train_sources=train_sources,
            validation_sources=validation_sources,
        )
        reference_index_hashes.add(candidate.reference_index_sha256)
    if len(reference_index_hashes) != 1:
        raise DigLocalStateSupportValidationError(
            "local candidate family does not share one strict-train neighbour index"
        )


def _validate_candidate(
    candidate: FittedDigLocalStateSupportCandidate,
    *,
    spec: DigLocalStateCandidateSpec,
    rows: DigLocalStateSupportRows,
    train_sources: set[int],
    validation_sources: set[int],
) -> None:
    if candidate.candidate_id != spec.candidate_id:
        raise DigLocalStateSupportValidationError("local candidate id disagrees with family")
    if candidate.fit_partition != "strict_train":
        raise DigLocalStateSupportValidationError(
            "local candidate was not fitted on strict_train"
        )
    if candidate.fit_row_count != rows.train_features.shape[0]:
        raise DigLocalStateSupportValidationError(
            "local candidate fit row count disagrees with strict-train rows"
        )
    if len(candidate.reference_index_sha256) != 64:
        raise DigLocalStateSupportValidationError(
            "local candidate strict-train neighbour-index digest is invalid"
        )
    if tuple(candidate.feature_order) != tuple(rows.feature_order):
        raise DigLocalStateSupportValidationError(
            "local candidate feature order disagrees with source rows"
        )
    if candidate.k_neighbors != spec.k_neighbors or (
        candidate.min_distinct_source_episode_ids
        != spec.min_distinct_source_episode_ids
    ):
        raise DigLocalStateSupportValidationError(
            "local candidate neighbour/source requirements are not pre-registered"
        )
    if candidate.k_neighbors > rows.train_features.shape[0]:
        raise DigLocalStateSupportValidationError(
            "local candidate requires more neighbours than strict-train rows"
        )
    if tuple(candidate.calibration_source_episode_ids) != tuple(sorted(train_sources)):
        raise DigLocalStateSupportValidationError(
            "local candidate calibration sources disagree with strict-train split"
        )
    if set(candidate.calibration_source_episode_ids) & validation_sources:
        raise DigLocalStateSupportValidationError(
            "local candidate calibration includes held-validation sources"
        )
    if candidate.calibration_query_count < 1 or (
        candidate.calibration_queries_meeting_source_requirement < 1
    ):
        raise DigLocalStateSupportValidationError(
            "local candidate lacks source-diverse strict-train calibration evidence"
        )
    if candidate.calibration_queries_failing_source_requirement < 0:
        raise DigLocalStateSupportValidationError(
            "local candidate calibration source count is invalid"
        )
    if candidate.distance_threshold_quantile != LOCAL_STATE_DISTANCE_QUANTILE:
        raise DigLocalStateSupportValidationError(
            "local candidate distance quantile is not pre-registered"
        )
    if candidate.action_coherence_threshold_quantile != LOCAL_STATE_ACTION_COHERENCE_QUANTILE:
        raise DigLocalStateSupportValidationError(
            "local candidate action-coherence quantile is not pre-registered"
        )
    thresholds = np.asarray(
        [candidate.distance_threshold, candidate.action_coherence_threshold],
        dtype=np.float64,
    )
    if not np.isfinite(thresholds).all() or np.any(thresholds < 0.0):
        raise DigLocalStateSupportValidationError("local candidate thresholds are invalid")
    axis_thresholds = np.asarray(
        candidate.action_coherence_axis_thresholds,
        dtype=np.float64,
    )
    if axis_thresholds.shape != (4,) or not np.isfinite(axis_thresholds).all():
        raise DigLocalStateSupportValidationError(
            "local candidate action-axis thresholds are invalid"
        )
    if np.any(axis_thresholds < 0.0):
        raise DigLocalStateSupportValidationError(
            "local candidate action-axis thresholds are negative"
        )
    if candidate.train_features.shape != rows.train_features.shape or (
        candidate.train_actions.shape != rows.train_actions.shape
    ):
        raise DigLocalStateSupportValidationError(
            "local candidate train index shape disagrees with strict-train rows"
        )
    if tuple(candidate.train_provenance) != tuple(rows.train_provenance):
        raise DigLocalStateSupportValidationError(
            "local candidate train provenance disagrees with strict-train rows"
        )


def _validate_obvious_ood(
    reference: FrozenObviousOodReference,
    *,
    rows: DigLocalStateSupportRows,
) -> None:
    if reference.anchor_partition != "validation":
        raise DigLocalStateSupportValidationError(
            "frozen obvious-OOD must be anchored only in held validation"
        )
    if tuple(reference.feature_order) != tuple(rows.feature_order):
        raise DigLocalStateSupportValidationError(
            "frozen obvious-OOD feature order disagrees with Dig source rows"
        )
    if reference.features.shape != rows.validation_features.shape:
        raise DigLocalStateSupportValidationError(
            "frozen obvious-OOD shape disagrees with held Dig validation rows"
        )
    if tuple(reference.anchor_provenance) != tuple(rows.validation_provenance):
        raise DigLocalStateSupportValidationError(
            "frozen obvious-OOD provenance is not held Dig validation"
        )


def _validate_assessment(
    candidate: FittedDigLocalStateSupportCandidate,
    assessment: DigLocalStateSupportAssessment,
    *,
    expected_row_count: int,
    label: str,
) -> bool:
    if assessment.candidate_id != candidate.candidate_id:
        raise DigLocalStateSupportValidationError(
            f"{label} assessment candidate id disagrees with its definition"
        )
    if tuple(assessment.feature_order) != tuple(candidate.feature_order):
        raise DigLocalStateSupportValidationError(
            f"{label} assessment feature order disagrees with its definition"
        )
    if assessment.feature.shape != (expected_row_count, len(candidate.feature_order)):
        raise DigLocalStateSupportValidationError(f"{label} assessment feature shape is invalid")
    frame_supported = np.asarray(assessment.frame_in_support, dtype=bool)
    kth_distance = np.asarray(assessment.kth_neighbor_distance, dtype=np.float64)
    source_counts = np.asarray(assessment.distinct_source_episode_counts, dtype=np.int64)
    action_scores = np.asarray(assessment.action_coherence_scores, dtype=np.float64)
    action_axis_scores = np.asarray(
        assessment.action_coherence_axis_scores,
        dtype=np.float64,
    )
    for values, name in (
        (frame_supported, "support flags"),
        (kth_distance, "kth-neighbour distances"),
        (source_counts, "source counts"),
        (action_scores, "action-coherence scores"),
    ):
        if values.shape != (expected_row_count,):
            raise DigLocalStateSupportValidationError(f"{label} {name} shape is invalid")
    if not np.isfinite(kth_distance).all() or not np.isfinite(action_scores).all():
        raise DigLocalStateSupportValidationError(f"{label} support metrics are non-finite")
    if action_axis_scores.shape != (expected_row_count, 4) or not np.isfinite(
        action_axis_scores
    ).all():
        raise DigLocalStateSupportValidationError(
            f"{label} action-axis coherence scores are invalid"
        )
    if np.any(source_counts < 0):
        raise DigLocalStateSupportValidationError(f"{label} source counts are invalid")
    if assessment.required_neighbors != candidate.k_neighbors or (
        assessment.required_distinct_source_episode_ids
        != candidate.min_distinct_source_episode_ids
    ):
        raise DigLocalStateSupportValidationError(
            f"{label} frozen neighbour/source requirements disagree with candidate"
        )
    if assessment.distance_threshold != candidate.distance_threshold or (
        assessment.action_coherence_threshold != candidate.action_coherence_threshold
    ):
        raise DigLocalStateSupportValidationError(
            f"{label} frozen thresholds disagree with candidate"
        )
    if len(assessment.neighbors) != expected_row_count or (
        len(assessment.violations) != expected_row_count
    ):
        raise DigLocalStateSupportValidationError(
            f"{label} neighbour/violation rows disagree with query count"
        )

    for index, neighbors in enumerate(assessment.neighbors):
        observed_sources = {int(item.provenance.source_episode_id) for item in neighbors}
        if int(source_counts[index]) != len(observed_sources):
            raise DigLocalStateSupportValidationError(
                f"{label} source diversity count disagrees at row {index}"
            )
        if any(item.distance < 0.0 or not np.isfinite(item.distance) for item in neighbors):
            raise DigLocalStateSupportValidationError(
                f"{label} has an invalid neighbour distance at row {index}"
            )
        predicate = (
            len(neighbors) >= candidate.k_neighbors
            and int(source_counts[index])
            >= candidate.min_distinct_source_episode_ids
            and float(kth_distance[index]) <= candidate.distance_threshold
            and float(action_scores[index]) <= candidate.action_coherence_threshold
            and bool(
                np.all(
                    action_axis_scores[index]
                    <= np.asarray(
                        candidate.action_coherence_axis_thresholds,
                        dtype=np.float64,
                    )
                )
            )
        )
        if bool(frame_supported[index]) != predicate:
            raise DigLocalStateSupportValidationError(
                f"{label} local support predicate disagrees at row {index}"
            )
    return True


def _source_separation(rows: DigLocalStateSupportRows) -> dict[str, Any]:
    train_sources = sorted({int(item.source_episode_id) for item in rows.train_provenance})
    validation_sources = sorted(
        {int(item.source_episode_id) for item in rows.validation_provenance}
    )
    return {
        "fit_partition": "strict_train",
        "normal_validation_partition": "held_validation",
        "train_source_episode_ids": train_sources,
        "validation_source_episode_ids": validation_sources,
        "source_episode_id_overlap": [],
        "source_disjoint": True,
        "train_action_loss_mask": "all_rows_equal_1",
        "validation_action_loss_mask": "all_rows_equal_1",
    }


def _source_ids(provenance: Sequence[SupportRowProvenance]) -> tuple[int, ...]:
    return tuple(int(item.source_episode_id) for item in provenance)


def _rejection_fraction(assessment: DigLocalStateSupportAssessment) -> float:
    flags = np.asarray(assessment.frame_in_support, dtype=bool)
    return float(np.mean(~flags)) if flags.size else 0.0


def _distance_coverage(
    assessment: DigLocalStateSupportAssessment,
    candidate: FittedDigLocalStateSupportCandidate,
) -> float:
    return _fraction_at_or_below(
        assessment.kth_neighbor_distance,
        candidate.distance_threshold,
    )


def _neighbor_count_coverage(
    assessment: DigLocalStateSupportAssessment,
    candidate: FittedDigLocalStateSupportCandidate,
) -> float:
    counts = np.asarray([len(row) for row in assessment.neighbors], dtype=np.int64)
    return _fraction_at_or_above(counts, candidate.k_neighbors)


def _source_diversity_coverage(
    assessment: DigLocalStateSupportAssessment,
    candidate: FittedDigLocalStateSupportCandidate,
) -> float:
    return _fraction_at_or_above(
        assessment.distinct_source_episode_counts,
        candidate.min_distinct_source_episode_ids,
    )


def _action_coherence_coverage(
    assessment: DigLocalStateSupportAssessment,
    candidate: FittedDigLocalStateSupportCandidate,
) -> float:
    return _fraction_at_or_below(
        assessment.action_coherence_scores,
        candidate.action_coherence_threshold,
    )


def _action_axis_coherence_coverage(
    assessment: DigLocalStateSupportAssessment,
    candidate: FittedDigLocalStateSupportCandidate,
) -> float:
    scores = np.asarray(assessment.action_coherence_axis_scores, dtype=np.float64)
    thresholds = np.asarray(
        candidate.action_coherence_axis_thresholds,
        dtype=np.float64,
    )
    return float(np.mean(np.all(scores <= thresholds.reshape(1, -1), axis=1)))


def _fraction_at_or_below(values: np.ndarray, threshold: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.mean(array <= threshold)) if array.size else 0.0


def _fraction_at_or_above(values: np.ndarray, threshold: int) -> float:
    array = np.asarray(values, dtype=np.int64)
    return float(np.mean(array >= threshold)) if array.size else 0.0


def _support_predicate_description(
    candidate: FittedDigLocalStateSupportCandidate,
) -> dict[str, Any]:
    return {
        "all_required": True,
        "k_neighbors_present": candidate.k_neighbors,
        "minimum_distinct_source_episode_ids": (
            candidate.min_distinct_source_episode_ids
        ),
        "kth_neighbor_distance_at_or_below": candidate.distance_threshold,
        "neighbor_expert_action_coherence_at_or_below": (
            candidate.action_coherence_threshold
        ),
        "neighbor_expert_action_axis_coherence_at_or_below": [
            float(value)
            for value in np.asarray(
                candidate.action_coherence_axis_thresholds,
                dtype=np.float64,
            )
        ],
    }


def _compact_candidate_definition(
    candidate: FittedDigLocalStateSupportCandidate,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "feature_order": list(candidate.feature_order),
        "fit_partition": candidate.fit_partition,
        "fit_row_count": candidate.fit_row_count,
        "strict_train_reference_index_sha256": candidate.reference_index_sha256,
        "k_neighbors": candidate.k_neighbors,
        "min_distinct_source_episode_ids": (
            candidate.min_distinct_source_episode_ids
        ),
        "state_scale": candidate.state_scale.as_dict(),
        "action_scale": candidate.action_scale.as_dict(),
        "distance_threshold": candidate.distance_threshold,
        "distance_threshold_quantile": candidate.distance_threshold_quantile,
        "action_coherence_threshold": candidate.action_coherence_threshold,
        "action_coherence_threshold_quantile": (
            candidate.action_coherence_threshold_quantile
        ),
        "action_coherence_axis_thresholds": [
            float(value)
            for value in np.asarray(
                candidate.action_coherence_axis_thresholds,
                dtype=np.float64,
            )
        ],
        "calibration_query_count": candidate.calibration_query_count,
        "calibration_source_episode_ids": list(
            candidate.calibration_source_episode_ids
        ),
        "calibration_queries_meeting_source_requirement": (
            candidate.calibration_queries_meeting_source_requirement
        ),
        "calibration_queries_failing_source_requirement": (
            candidate.calibration_queries_failing_source_requirement
        ),
        "calibration_query_provenance_sha256": _calibration_query_digest(candidate),
    }


def _compact_assessment_summary(
    assessment: DigLocalStateSupportAssessment,
    *,
    candidate: FittedDigLocalStateSupportCandidate,
    predicate_verified: bool,
) -> dict[str, Any]:
    flags = np.asarray(assessment.frame_in_support, dtype=bool)
    return {
        "candidate_id": assessment.candidate_id,
        "query_row_count": int(flags.size),
        "in_support_row_count": int(np.count_nonzero(flags)),
        "in_support_fraction": assessment.in_support_fraction,
        "distance_coverage": _distance_coverage(assessment, candidate),
        "neighbor_count_coverage": _neighbor_count_coverage(assessment, candidate),
        "source_diversity_coverage": _source_diversity_coverage(
            assessment,
            candidate,
        ),
        "action_coherence_coverage": _action_coherence_coverage(
            assessment,
            candidate,
        ),
        "action_axis_coherence_coverage": _action_axis_coherence_coverage(
            assessment,
            candidate,
        ),
        "support_predicate_verified": predicate_verified,
        "metric_ranges": {
            "kth_neighbor_distance": _finite_range(assessment.kth_neighbor_distance),
            "distinct_source_episode_count": _integer_range(
                assessment.distinct_source_episode_counts
            ),
            "action_coherence_score": _finite_range(
                assessment.action_coherence_scores
            ),
            "action_axis_coherence_score": _axis_ranges(
                assessment.action_coherence_axis_scores
            ),
        },
        "assessment_sha256": _assessment_digest(assessment),
        "per_row_neighbors_serialized": False,
    }


def _finite_range(values: np.ndarray) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {"min": float(np.min(array)), "max": float(np.max(array))}


def _integer_range(values: np.ndarray) -> dict[str, int]:
    array = np.asarray(values, dtype=np.int64)
    return {"min": int(np.min(array)), "max": int(np.max(array))}


def _axis_ranges(values: np.ndarray) -> list[dict[str, float]]:
    array = np.asarray(values, dtype=np.float64)
    return [
        {"min": float(np.min(array[:, axis])), "max": float(np.max(array[:, axis]))}
        for axis in range(array.shape[1])
    ]


def _calibration_query_digest(
    candidate: FittedDigLocalStateSupportCandidate,
) -> str:
    digest = hashlib.sha256()
    _hash_text(digest, candidate.candidate_id)
    _hash_integer(digest, candidate.calibration_query_count)
    for query in candidate.calibration_queries:
        _hash_integer(digest, query.train_row_index)
        _hash_provenance(digest, query.provenance)
    return digest.hexdigest()


def _assessment_digest(assessment: DigLocalStateSupportAssessment) -> str:
    digest = hashlib.sha256()
    _hash_text(digest, assessment.candidate_id)
    _hash_json(digest, list(assessment.feature_order))
    _hash_array(digest, assessment.feature, dtype=np.float64)
    _hash_array(digest, assessment.frame_in_support, dtype=np.uint8)
    _hash_array(digest, assessment.kth_neighbor_distance, dtype=np.float64)
    _hash_array(digest, assessment.distinct_source_episode_counts, dtype=np.int64)
    _hash_array(digest, assessment.action_coherence_scores, dtype=np.float64)
    _hash_array(digest, assessment.action_coherence_axis_scores, dtype=np.float64)
    _hash_array(digest, assessment.action_coherence_centres, dtype=np.float64)
    _hash_integer(digest, assessment.required_neighbors)
    _hash_integer(digest, assessment.required_distinct_source_episode_ids)
    _hash_float(digest, assessment.distance_threshold)
    _hash_float(digest, assessment.action_coherence_threshold)
    for neighbors, violations in zip(
        assessment.neighbors,
        assessment.violations,
        strict=True,
    ):
        _hash_integer(digest, len(neighbors))
        for neighbor in neighbors:
            _hash_integer(digest, neighbor.train_row_index)
            _hash_float(digest, neighbor.distance)
            _hash_provenance(digest, neighbor.provenance)
            _hash_array(digest, neighbor.action, dtype=np.float64)
        _hash_integer(digest, len(violations))
        for violation in violations:
            _hash_json(digest, violation.as_dict())
    return digest.hexdigest()


def _hash_array(
    digest: Any,
    values: np.ndarray,
    *,
    dtype: np.dtype[Any] | type[np.generic],
) -> None:
    array = np.ascontiguousarray(np.asarray(values, dtype=dtype))
    _hash_text(digest, array.dtype.str)
    _hash_json(digest, list(array.shape))
    digest.update(array.tobytes(order="C"))


def _hash_provenance(digest: Any, provenance: SupportRowProvenance) -> None:
    _hash_json(digest, provenance.as_dict())


def _hash_json(digest: Any, value: Any) -> None:
    digest.update(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    )


def _hash_text(digest: Any, value: str) -> None:
    encoded = value.encode("utf-8")
    _hash_integer(digest, len(encoded))
    digest.update(encoded)


def _hash_integer(digest: Any, value: int) -> None:
    digest.update(int(value).to_bytes(8, byteorder="big", signed=True))


def _hash_float(digest: Any, value: float) -> None:
    _hash_array(digest, np.asarray([value], dtype=np.float64), dtype=np.float64)


def _validate_evaluations(
    evaluations: Sequence[DigLocalStateCandidateValidation],
) -> None:
    if len(evaluations) != len(DIG_LOCAL_STATE_CANDIDATE_SPECS):
        raise DigLocalStateSupportValidationError(
            "selection requires every pre-registered local Dig candidate"
        )
    for fixed_order, (spec, evaluation) in enumerate(
        zip(DIG_LOCAL_STATE_CANDIDATE_SPECS, evaluations, strict=True)
    ):
        if evaluation.candidate_id != spec.candidate_id or evaluation.fixed_order != fixed_order:
            raise DigLocalStateSupportValidationError(
                "local candidate evaluation order is not the pre-registered family order"
            )
        for value, label in (
            (evaluation.validation_normal_coverage, "validation normal coverage"),
            (evaluation.validation_distance_coverage, "validation distance coverage"),
            (
                evaluation.validation_neighbor_count_coverage,
                "validation neighbour-count coverage",
            ),
            (
                evaluation.validation_source_diversity_coverage,
                "validation source-diversity coverage",
            ),
            (
                evaluation.validation_action_coherence_coverage,
                "validation action-coherence coverage",
            ),
            (
                evaluation.validation_action_axis_coherence_coverage,
                "validation action-axis-coherence coverage",
            ),
            (evaluation.frozen_obvious_ood_rejection, "obvious-OOD rejection"),
        ):
            if not 0.0 <= value <= 1.0:
                raise DigLocalStateSupportValidationError(f"{label} must lie in [0, 1]")
        if evaluation.validation_normal_coverage_passed != (
            evaluation.validation_normal_coverage >= VALIDATION_NORMAL_COVERAGE_MIN
        ):
            raise DigLocalStateSupportValidationError(
                "validation coverage pass flag disagrees with its pre-registered gate"
            )
        if evaluation.frozen_obvious_ood_rejection_passed != (
            evaluation.frozen_obvious_ood_rejection
            >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
        ):
            raise DigLocalStateSupportValidationError(
                "obvious-OOD rejection pass flag disagrees with its pre-registered gate"
            )


__all__ = [
    "DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION",
    "DIG_LOCAL_STATE_SUPPORT_VALIDATION_SCHEMA",
    "FROZEN_OBVIOUS_OOD_REJECTION_MIN",
    "VALIDATION_NORMAL_COVERAGE_MIN",
    "DigLocalStateCandidateValidation",
    "DigLocalStateSupportValidationError",
    "run_dig_local_state_support_validation",
    "select_dig_local_state_support_candidate",
]
