"""Independent held-validation audit for the pre-registered Dig joint family.

Unlike the earlier support-contract audit, this evaluator intentionally does
not accept a recorded rollout or Stage-A artifact.  Its complete input is the
strict source-aware Dig train/held-validation population.  Therefore the
selection below cannot adjust a threshold after observing a target replay.

The result is diagnostic evidence only.  It selects no runtime gate and does
not alter an existing support contract by itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.act_support_contract import StrictSourceAwareSupportRows
from testbed.data.dig_joint_support_validation import (
    DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS,
    DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
    DIG_JOINT_MAHALANOBIS_QUANTILES,
    DIG_JOINT_MAHALANOBIS_RIDGE_FLOOR,
    DIG_JOINT_MAHALANOBIS_RIDGE_TRACE_FRACTION,
    DIG_JOINT_SUPPORT_VALIDATION_SCHEMA,
    DigJointMahalanobisCandidate,
    DigJointSupportValidationError,
    DigValidationV1EdgeCohort,
    FrozenDigValidationObviousOod,
    assess_dig_joint_mahalanobis_candidate,
    build_dig_validation_v1_edge_cohort,
    build_frozen_dig_validation_obvious_ood,
    dig_joint_support_source_provenance,
    fit_dig_joint_mahalanobis_family,
    validate_dig_joint_support_validation_rows,
)

DIG_JOINT_SUPPORT_VALIDATION_AUDIT_SCHEMA = "dig_joint_support_validation_audit_v1"
DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION = "support_contract_v2_dig_joint_v1"
VALIDATION_NORMAL_COVERAGE_MIN = 0.99
FROZEN_OBVIOUS_OOD_REJECTION_MIN = 0.99
VALIDATION_V1_EDGE_COVERAGE_MIN = 0.99


class DigJointSupportValidationAuditError(ValueError):
    """Raised when a Dig joint validation audit cannot remain source-safe."""


@dataclass(frozen=True)
class DigJointCandidateValidation:
    """Validation metrics for one fixed, strict-train-fitted candidate."""

    candidate_id: str
    fixed_order: int
    train_score_quantile: float
    validation_normal_coverage: float
    validation_v1_edge_coverage: float | None
    validation_v1_edge_nonempty: bool
    frozen_obvious_ood_rejection: float
    validation_normal_coverage_passed: bool
    validation_v1_edge_coverage_passed: bool
    frozen_obvious_ood_rejection_passed: bool

    @property
    def qualified(self) -> bool:
        return (
            self.validation_normal_coverage >= VALIDATION_NORMAL_COVERAGE_MIN
            and self.validation_v1_edge_nonempty
            and self.validation_v1_edge_coverage is not None
            and self.validation_v1_edge_coverage >= VALIDATION_V1_EDGE_COVERAGE_MIN
            and self.frozen_obvious_ood_rejection >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
        )

    @property
    def qualification_status(self) -> str:
        if self.qualified:
            return "qualified"
        failures: list[str] = []
        if not self.validation_normal_coverage_passed:
            failures.append("validation_coverage")
        if not self.validation_v1_edge_coverage_passed:
            failures.append("validation_v1_edge_coverage")
        if not self.frozen_obvious_ood_rejection_passed:
            failures.append("obvious_ood_rejection")
        if len(failures) > 1:
            return "rejected_" + "_and_".join(failures)
        if not self.validation_normal_coverage_passed:
            return "rejected_validation_coverage"
        if not self.validation_v1_edge_coverage_passed:
            return "rejected_validation_v1_edge_coverage"
        return "rejected_obvious_ood_rejection"

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "fixed_order": self.fixed_order,
            "train_score_quantile": self.train_score_quantile,
            "validation_normal_coverage": self.validation_normal_coverage,
            "validation_v1_edge_coverage": self.validation_v1_edge_coverage,
            "validation_v1_edge_nonempty": self.validation_v1_edge_nonempty,
            "frozen_obvious_ood_rejection": self.frozen_obvious_ood_rejection,
            "validation_normal_coverage_passed": self.validation_normal_coverage_passed,
            "validation_v1_edge_coverage_passed": self.validation_v1_edge_coverage_passed,
            "frozen_obvious_ood_rejection_passed": self.frozen_obvious_ood_rejection_passed,
            "qualified": self.qualified,
            "qualification_status": self.qualification_status,
        }


def run_dig_joint_support_validation_audit(
    *,
    rows: StrictSourceAwareSupportRows,
) -> dict[str, Any]:
    """Evaluate and select the frozen Dig joint family using validation only.

    There is deliberately no ``target_segments``, rollout path, Stage-A result
    or threshold argument.  The candidate family and ridge policy are fixed in
    the data module.  Held validation measures only acceptance/rejection of
    the already fitted candidates.
    """

    try:
        validate_dig_joint_support_validation_rows(rows)
    except DigJointSupportValidationError as exc:
        raise DigJointSupportValidationAuditError(str(exc)) from exc

    candidates = fit_dig_joint_mahalanobis_family(rows)
    _validate_candidate_family(candidates, rows=rows)
    validation_v1_edge = build_dig_validation_v1_edge_cohort(rows)
    _validate_validation_v1_edge(validation_v1_edge, rows=rows)
    obvious_ood = build_frozen_dig_validation_obvious_ood(rows)
    _validate_obvious_ood(obvious_ood, rows=rows)

    evaluations: list[DigJointCandidateValidation] = []
    candidate_records: list[dict[str, Any]] = []
    validation = np.asarray(rows.validation_features, dtype=np.float64)
    for fixed_order, candidate_id in enumerate(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS):
        candidate = candidates[candidate_id]
        validation_assessment = assess_dig_joint_mahalanobis_candidate(
            candidate,
            validation,
        )
        ood_assessment = assess_dig_joint_mahalanobis_candidate(
            candidate,
            obvious_ood.features,
        )
        edge_assessment = (
            assess_dig_joint_mahalanobis_candidate(
                candidate,
                validation_v1_edge.features,
            )
            if validation_v1_edge.features.shape[0] > 0
            else None
        )
        edge_coverage = (
            None if edge_assessment is None else edge_assessment.in_support_fraction
        )
        ood_rejection = float(np.mean(~ood_assessment.frame_in_support))
        record = DigJointCandidateValidation(
            candidate_id=candidate_id,
            fixed_order=fixed_order,
            train_score_quantile=candidate.train_score_quantile,
            validation_normal_coverage=validation_assessment.in_support_fraction,
            validation_v1_edge_coverage=edge_coverage,
            validation_v1_edge_nonempty=edge_assessment is not None,
            frozen_obvious_ood_rejection=ood_rejection,
            validation_normal_coverage_passed=(
                validation_assessment.in_support_fraction >= VALIDATION_NORMAL_COVERAGE_MIN
            ),
            validation_v1_edge_coverage_passed=(
                edge_coverage is not None
                and edge_coverage >= VALIDATION_V1_EDGE_COVERAGE_MIN
            ),
            frozen_obvious_ood_rejection_passed=(
                ood_rejection >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
            ),
        )
        evaluations.append(record)
        candidate_records.append(
            {
                **record.as_dict(),
                "definition": candidate.as_dict(),
                "validation_assessment": validation_assessment.as_dict(),
                "validation_v1_edge_assessment": (
                    None if edge_assessment is None else edge_assessment.as_dict()
                ),
                "frozen_obvious_ood_assessment": ood_assessment.as_dict(),
            }
        )

    selected = select_dig_joint_support_candidate(evaluations)
    selected_candidate_id = None if selected is None else selected.candidate_id
    return {
        "schema": DIG_JOINT_SUPPORT_VALIDATION_AUDIT_SCHEMA,
        "support_contract_version": DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION,
        "primitive": "dig",
        "status": "completed" if selected is not None else "support_contract_not_selected",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "runtime_support_change": False,
        "target_rollout_used_for_selection": False,
        "selection_input_scope": "strict_train_and_held_validation_only",
        "data_schema": DIG_JOINT_SUPPORT_VALIDATION_SCHEMA,
        "candidate_family": {
            "kind": "regularized_joint_mahalanobis",
            "train_score_quantiles": list(DIG_JOINT_MAHALANOBIS_QUANTILES),
            "train_score_quantile_method": DIG_JOINT_MAHALANOBIS_QUANTILE_METHOD,
            "candidate_ids_in_fixed_order": list(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS),
            "ridge_policy": {
                "trace_fraction": DIG_JOINT_MAHALANOBIS_RIDGE_TRACE_FRACTION,
                "floor": DIG_JOINT_MAHALANOBIS_RIDGE_FLOOR,
                "formula": "max(trace(train_covariance) / feature_dim * trace_fraction, floor)",
            },
        },
        "selection_metrics": {
            "validation_normal_coverage_min": VALIDATION_NORMAL_COVERAGE_MIN,
            "validation_v1_edge_coverage_min": VALIDATION_V1_EDGE_COVERAGE_MIN,
            "validation_v1_edge_nonempty_required": True,
            "frozen_obvious_ood_rejection_min": FROZEN_OBVIOUS_OOD_REJECTION_MIN,
            "selection": (
                "qualified candidates: highest frozen_obvious_ood_rejection, "
                "then highest validation_normal_coverage, then fixed family order"
            ),
        },
        "source_separation": dig_joint_support_source_provenance(rows),
        "validation_v1_edge_cohort": validation_v1_edge.provenance_dict(),
        "frozen_obvious_ood": obvious_ood.provenance_dict(),
        "candidates": candidate_records,
        "selected_candidate_id": selected_candidate_id,
        "selection_status": "selected" if selected is not None else "not_selected",
    }


def select_dig_joint_support_candidate(
    evaluations: Sequence[DigJointCandidateValidation],
) -> DigJointCandidateValidation | None:
    """Select only fully qualified candidates using the pre-registered order.

    The first two ordering keys reward stronger rejection of frozen obvious
    OOD, then broader normal held-validation coverage.  The final key is the
    immutable family order, never a result-dependent preference.
    """

    _validate_evaluations(evaluations)
    qualified = [evaluation for evaluation in evaluations if evaluation.qualified]
    if not qualified:
        return None
    return min(
        qualified,
        key=lambda evaluation: (
            -evaluation.frozen_obvious_ood_rejection,
            -evaluation.validation_normal_coverage,
            evaluation.fixed_order,
        ),
    )


def _validate_candidate_family(
    candidates: Mapping[str, DigJointMahalanobisCandidate],
    *,
    rows: StrictSourceAwareSupportRows,
) -> None:
    observed = tuple(candidates)
    if observed != DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS:
        raise DigJointSupportValidationAuditError(
            "Dig joint candidate family does not match the pre-registered order"
        )
    expected_feature_order = tuple(rows.feature_order)
    expected_count = int(rows.train_features.shape[0])
    for candidate_id, quantile in zip(
        DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS,
        DIG_JOINT_MAHALANOBIS_QUANTILES,
        strict=True,
    ):
        candidate = candidates[candidate_id]
        if candidate.candidate_id != candidate_id:
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate id disagrees with its family key"
            )
        if candidate.train_score_quantile != quantile:
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate train quantile is not pre-registered"
            )
        if candidate.fit_partition != "strict_train":
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate was not fitted on strict_train"
            )
        if candidate.fit_row_count != expected_count:
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate fit row count disagrees with strict_train"
            )
        if tuple(candidate.feature_order) != expected_feature_order:
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate feature order disagrees with the source rows"
            )
        if candidate.regularization <= 0.0 or not np.isfinite(candidate.regularization):
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate regularization must be finite and positive"
            )
        if candidate.threshold < 0.0 or not np.isfinite(candidate.threshold):
            raise DigJointSupportValidationAuditError(
                "Dig joint candidate threshold must be finite and non-negative"
            )


def _validate_obvious_ood(
    reference: FrozenDigValidationObviousOod,
    *,
    rows: StrictSourceAwareSupportRows,
) -> None:
    if reference.anchor_partition != "validation":
        raise DigJointSupportValidationAuditError(
            "frozen obvious-OOD must be anchored only in held validation"
        )
    if tuple(reference.feature_order) != tuple(rows.feature_order):
        raise DigJointSupportValidationAuditError(
            "frozen obvious-OOD feature order disagrees with Dig source rows"
        )
    if reference.features.shape != rows.validation_features.shape:
        raise DigJointSupportValidationAuditError(
            "frozen obvious-OOD shape disagrees with held Dig validation rows"
        )
    if tuple(reference.anchor_provenance) != tuple(rows.validation_provenance):
        raise DigJointSupportValidationAuditError(
            "frozen obvious-OOD provenance is not the held Dig validation partition"
        )


def _validate_validation_v1_edge(
    cohort: DigValidationV1EdgeCohort,
    *,
    rows: StrictSourceAwareSupportRows,
) -> None:
    if cohort.anchor_partition != "validation" or cohort.v1_fit_partition != "strict_train":
        raise DigJointSupportValidationAuditError(
            "Dig v1 edge cohort must use strict-train v1 and held validation only"
        )
    if tuple(cohort.feature_order) != tuple(rows.feature_order):
        raise DigJointSupportValidationAuditError(
            "Dig v1 edge cohort feature order disagrees with source rows"
        )
    if cohort.features.ndim != 2 or cohort.features.shape[1] != len(rows.feature_order):
        raise DigJointSupportValidationAuditError(
            "Dig v1 edge cohort feature dimensions are invalid"
        )
    if cohort.validation_indices.shape != (cohort.features.shape[0],):
        raise DigJointSupportValidationAuditError(
            "Dig v1 edge cohort indices do not match its feature rows"
        )
    if len(cohort.provenance) != cohort.features.shape[0]:
        raise DigJointSupportValidationAuditError(
            "Dig v1 edge cohort provenance does not match its feature rows"
        )
    if any(item.partition != "validation" for item in cohort.provenance):
        raise DigJointSupportValidationAuditError(
            "Dig v1 edge cohort includes a non-validation source row"
        )


def _validate_evaluations(
    evaluations: Sequence[DigJointCandidateValidation],
) -> None:
    if len(evaluations) != len(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS):
        raise DigJointSupportValidationAuditError(
            "selection requires every pre-registered Dig joint candidate"
        )
    for fixed_order, (expected_id, evaluation) in enumerate(
        zip(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS, evaluations, strict=True)
    ):
        if evaluation.candidate_id != expected_id or evaluation.fixed_order != fixed_order:
            raise DigJointSupportValidationAuditError(
                "candidate evaluation order is not the pre-registered family order"
            )
        if not (0.0 <= evaluation.validation_normal_coverage <= 1.0):
            raise DigJointSupportValidationAuditError(
                "validation normal coverage must lie in [0, 1]"
            )
        if evaluation.validation_v1_edge_coverage is not None and not (
            0.0 <= evaluation.validation_v1_edge_coverage <= 1.0
        ):
            raise DigJointSupportValidationAuditError(
                "validation v1-edge coverage must lie in [0, 1]"
            )
        if (
            evaluation.validation_v1_edge_nonempty
            != (evaluation.validation_v1_edge_coverage is not None)
        ):
            raise DigJointSupportValidationAuditError(
                "validation v1-edge cohort presence disagrees with its coverage"
            )
        if evaluation.validation_normal_coverage_passed != (
            evaluation.validation_normal_coverage >= VALIDATION_NORMAL_COVERAGE_MIN
        ):
            raise DigJointSupportValidationAuditError(
                "validation normal coverage pass flag disagrees with its threshold"
            )
        if evaluation.validation_v1_edge_coverage_passed != (
            evaluation.validation_v1_edge_coverage is not None
            and evaluation.validation_v1_edge_coverage
            >= VALIDATION_V1_EDGE_COVERAGE_MIN
        ):
            raise DigJointSupportValidationAuditError(
                "validation v1-edge pass flag disagrees with its threshold"
            )
        if not (0.0 <= evaluation.frozen_obvious_ood_rejection <= 1.0):
            raise DigJointSupportValidationAuditError(
                "frozen obvious-OOD rejection must lie in [0, 1]"
            )
        if evaluation.frozen_obvious_ood_rejection_passed != (
            evaluation.frozen_obvious_ood_rejection
            >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
        ):
            raise DigJointSupportValidationAuditError(
                "obvious-OOD rejection pass flag disagrees with its threshold"
            )


__all__ = [
    "DIG_JOINT_SUPPORT_VALIDATION_AUDIT_SCHEMA",
    "DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION",
    "FROZEN_OBVIOUS_OOD_REJECTION_MIN",
    "VALIDATION_NORMAL_COVERAGE_MIN",
    "VALIDATION_V1_EDGE_COVERAGE_MIN",
    "DigJointCandidateValidation",
    "DigJointSupportValidationAuditError",
    "run_dig_joint_support_validation_audit",
    "select_dig_joint_support_candidate",
]
