"""Fail-closed offline audit for the Strict-18 numeric support contract.

This module deliberately owns only *evaluation* semantics.  The data layer
loads source-safe strict-train/validation rows and fits the registered support
candidates.  The thin runner/CLI supplies recorded Stage-A segments.  Keeping
those concerns separate ensures that target-rollout observations cannot
silently influence a support threshold.

The audit has two independent evidence streams:

* strict-train fit plus held-out validation select one registered rule per
  primitive; and
* the already-recorded Stage-A segments are diagnosed against that frozen
  selection and the historical p01--p99 v1 baseline.

It is diagnostic-only teacher-forced evidence.  It does not change a runtime
gate, planner target, Unity execution, or real-machine behaviour.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.act_support_contract_artifacts import (
    render_support_contract_report,
    write_json_exclusive,
    write_return_support_plots,
    write_text_exclusive,
)
from testbed.eval.act_support_contract_target_trace import build_recorded_target_trace

SUPPORT_CONTRACT_AUDIT_MANIFEST_SCHEMA = "act_support_contract_audit_manifest_v1"
SUPPORT_CONTRACT_AUDIT_CANDIDATES_SCHEMA = "act_support_contract_candidates_v1"
SUPPORT_CONTRACT_AUDIT_VALIDATION_SCHEMA = "act_support_contract_validation_v1"
SUPPORT_CONTRACT_AUDIT_TARGET_SCHEMA = "act_support_contract_target_diagnosis_v1"
SUPPORT_CONTRACT_VERSION = "support_contract_v2"
EVIDENCE_KIND = "teacher_forced_recorded_observation"

VALIDATION_NORMAL_COVERAGE_MIN = 0.99
SYNTHETIC_OBVIOUS_OOD_REJECTION_MIN = 0.99

# This is a pre-registered order, not an outcome-dependent preference.  It is
# used only after the two validation acceptance metrics tie exactly.
CANDIDATE_PRIORITY = (
    "axis_p01_p99_v1",
    "joint_regularized_mahalanobis_p99_v2",
    "axis_p0005_p9995_v2",
)

CandidateFitter = Callable[[Any], Mapping[str, Any]]
CandidateAssessor = Callable[[Any, Any], Any]
ObviousOodBuilder = Callable[[Any], Any]


class SupportContractAuditError(ValueError):
    """Raised when immutable support-audit inputs violate the contract."""


def run_support_contract_audit(
    *,
    source_lineage: Mapping[str, Any],
    feature_partitions: Mapping[str, Any],
    target_segments: Mapping[str, Sequence[Any]],
    output_root: str | Path,
    candidate_fitter: CandidateFitter | None = None,
    candidate_assessor: CandidateAssessor | None = None,
    obvious_ood_builder: ObviousOodBuilder | None = None,
) -> dict[str, Any]:
    """Select ``support_contract_v2`` and diagnose recorded Stage-A segments.

    ``feature_partitions`` is keyed by ``dig`` and ``return``.  Each value is a
    source-aware data-layer object containing train and validation feature
    matrices plus feature order/provenance.  Candidate fit, validation scoring,
    and frozen obvious-OOD construction happen before this function examines
    ``target_segments``.  The optional callables make every heavy data operation
    mock-injectable for focused tests.

    ``target_segments`` accepts the recorded segment dataclass used by Stage A
    or mapping-shaped equivalents.  A segment may expose a preassembled
    ``feature_matrix``/``support_features`` or frames with ``qpos``, ``qvel``,
    and ``token`` fields.  It is evaluated only after selection is frozen.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"support-contract output already exists: {destination}")
    lineage = _normalise_lineage(source_lineage)
    partitions = _normalise_primitive_mapping(
        feature_partitions,
        label="feature_partitions",
    )
    fitter, assessor, ood_builder = _resolve_dependencies(
        candidate_fitter=candidate_fitter,
        candidate_assessor=candidate_assessor,
        obvious_ood_builder=obvious_ood_builder,
    )

    # The selection phase intentionally has no access to target_segments.
    primitive_selection: dict[str, dict[str, Any]] = {}
    for primitive in ("dig", "return"):
        primitive_selection[primitive] = _evaluate_primitive_candidates(
            primitive=primitive,
            rows=partitions[primitive],
            candidate_fitter=fitter,
            candidate_assessor=assessor,
            obvious_ood_builder=ood_builder,
        )

    selected_by_primitive = {
        primitive: payload["selected_candidate_id"]
        for primitive, payload in primitive_selection.items()
    }
    all_selected = all(value is not None for value in selected_by_primitive.values())

    # Only after validation-based selection is complete may target evidence be
    # opened and classified.  This ordering is part of the anti-tuning contract.
    segments_by_primitive = _normalise_primitive_mapping(
        target_segments,
        label="target_segments",
    )
    target_payload, return_plot_specs = _diagnose_target_segments(
        selections=primitive_selection,
        target_segments=segments_by_primitive,
        candidate_assessor=assessor,
    )
    status = "completed" if all_selected else "support_contract_not_selected"
    target_payload["status"] = status

    candidates_payload = {
        "schema": SUPPORT_CONTRACT_AUDIT_CANDIDATES_SCHEMA,
        "support_contract_version": SUPPORT_CONTRACT_VERSION,
        "selection_order": list(CANDIDATE_PRIORITY),
        "selection_metrics": {
            "validation_normal_coverage_min": VALIDATION_NORMAL_COVERAGE_MIN,
            "synthetic_obvious_ood_rejection_min": SYNTHETIC_OBVIOUS_OOD_REJECTION_MIN,
            "selection": (
                "qualified candidates: highest synthetic_obvious_ood_rejection, "
                "then highest validation_normal_coverage, then fixed priority"
            ),
        },
        "primitives": {
            primitive: payload["candidate_records"]
            for primitive, payload in primitive_selection.items()
        },
    }
    validation_payload = {
        "schema": SUPPORT_CONTRACT_AUDIT_VALIDATION_SCHEMA,
        "support_contract_version": SUPPORT_CONTRACT_VERSION,
        "target_rollout_used_for_selection": False,
        "primitives": {
            primitive: {
                "feature_order": payload["feature_order"],
                "train_sample_count": payload["train_sample_count"],
                "validation_sample_count": payload["validation_sample_count"],
                "synthetic_obvious_ood_sample_count": payload[
                    "synthetic_obvious_ood_sample_count"
                ],
                "selected_candidate_id": payload["selected_candidate_id"],
                "selection_status": payload["selection_status"],
                "candidate_validation": [
                    _candidate_validation_view(record)
                    for record in payload["candidate_records"]
                ],
                "validation_provenance": payload["validation_provenance"],
                "synthetic_obvious_ood_provenance": payload[
                    "synthetic_obvious_ood_provenance"
                ],
            }
            for primitive, payload in primitive_selection.items()
        },
    }

    # Build all JSON payloads before creating the root.  Once the exclusive
    # directory exists it is evidence and is never replaced or cleaned up.
    destination.mkdir(parents=True, exist_ok=False)
    plot_records = write_return_support_plots(destination, return_plot_specs)
    target_payload["plots"] = plot_records
    manifest = {
        "schema": SUPPORT_CONTRACT_AUDIT_MANIFEST_SCHEMA,
        "status": status,
        "support_contract_version": SUPPORT_CONTRACT_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "source_lineage": lineage,
        "target_rollout_used_for_selection": False,
        "selected_candidate_by_primitive": selected_by_primitive,
        "selection_status_by_primitive": {
            primitive: payload["selection_status"]
            for primitive, payload in primitive_selection.items()
        },
        "artifact_files": {
            "candidates": "candidates.json",
            "validation": "validation.json",
            "target_diagnosis": "target_diagnosis.json",
            "report": "report.md",
            "return_distribution_plots": plot_records,
        },
    }
    report = render_support_contract_report(
        status=status,
        selections=primitive_selection,
        target_diagnosis=target_payload,
        plot_records=plot_records,
    )
    write_json_exclusive(destination / "manifest.json", manifest)
    write_json_exclusive(destination / "candidates.json", candidates_payload)
    write_json_exclusive(destination / "validation.json", validation_payload)
    write_json_exclusive(destination / "target_diagnosis.json", target_payload)
    write_text_exclusive(destination / "report.md", report)
    return {
        "status": status,
        "output_root": str(destination),
        "manifest": manifest,
        "selected_candidate_by_primitive": selected_by_primitive,
    }


def _evaluate_primitive_candidates(
    *,
    primitive: str,
    rows: Any,
    candidate_fitter: CandidateFitter,
    candidate_assessor: CandidateAssessor,
    obvious_ood_builder: ObviousOodBuilder,
) -> dict[str, Any]:
    feature_order = _feature_order(rows)
    train_features = _feature_matrix_from_object(
        rows,
        names=("train_features",),
        label=f"{primitive} strict-train features",
        expected_width=len(feature_order),
    )
    validation_features = _feature_matrix_from_object(
        rows,
        names=("validation_features",),
        label=f"{primitive} validation features",
        expected_width=len(feature_order),
    )
    candidates = candidate_fitter(rows)
    if not isinstance(candidates, Mapping):
        raise SupportContractAuditError(
            f"{primitive} candidate fitter must return a mapping"
        )
    missing = [candidate_id for candidate_id in CANDIDATE_PRIORITY if candidate_id not in candidates]
    extra = sorted(set(candidates) - set(CANDIDATE_PRIORITY))
    if missing or extra:
        raise SupportContractAuditError(
            f"{primitive} registered candidate ids mismatch; missing={missing}, extra={extra}"
        )
    obvious_ood = obvious_ood_builder(rows)
    ood_features = _feature_matrix_from_object(
        obvious_ood,
        names=("features", "feature_matrix", "synthetic_features"),
        label=f"{primitive} frozen obvious OOD features",
        expected_width=len(feature_order),
    )

    candidate_records: list[dict[str, Any]] = []
    candidate_objects: dict[str, Any] = {}
    for priority, candidate_id in enumerate(CANDIDATE_PRIORITY):
        candidate = candidates[candidate_id]
        observed_id = _candidate_id(candidate)
        if observed_id != candidate_id:
            raise SupportContractAuditError(
                f"{primitive} candidate key {candidate_id!r} disagrees with candidate id "
                f"{observed_id!r}"
            )
        validation_assessment = candidate_assessor(candidate, validation_features)
        ood_assessment = candidate_assessor(candidate, ood_features)
        validation_in_support = _assessment_mask(
            validation_assessment,
            expected_length=len(validation_features),
            label=f"{primitive} {candidate_id} validation assessment",
        )
        ood_in_support = _assessment_mask(
            ood_assessment,
            expected_length=len(ood_features),
            label=f"{primitive} {candidate_id} OOD assessment",
        )
        normal_coverage = float(np.mean(validation_in_support))
        ood_rejection = float(np.mean(~ood_in_support))
        coverage_ok = normal_coverage >= VALIDATION_NORMAL_COVERAGE_MIN
        rejection_ok = ood_rejection >= SYNTHETIC_OBVIOUS_OOD_REJECTION_MIN
        candidate_records.append(
            {
                "candidate_id": candidate_id,
                "priority": priority,
                "definition": _candidate_definition(candidate),
                "validation_normal_coverage": normal_coverage,
                "synthetic_obvious_ood_rejection": ood_rejection,
                "validation_normal_coverage_passed": coverage_ok,
                "synthetic_obvious_ood_rejection_passed": rejection_ok,
                "qualified": bool(coverage_ok and rejection_ok),
                "qualification_status": _qualification_status(
                    coverage_ok=coverage_ok,
                    rejection_ok=rejection_ok,
                ),
                "validation_assessment": _assessment_summary(validation_assessment),
                "synthetic_obvious_ood_assessment": _assessment_summary(ood_assessment),
            }
        )
        candidate_objects[candidate_id] = candidate
    selected = _select_candidate(candidate_records)
    selected_id = None if selected is None else str(selected["candidate_id"])
    return {
        "primitive": primitive,
        "feature_order": list(feature_order),
        "train_sample_count": int(train_features.shape[0]),
        "validation_sample_count": int(validation_features.shape[0]),
        "synthetic_obvious_ood_sample_count": int(ood_features.shape[0]),
        "validation_provenance": _provenance(rows, "validation"),
        "synthetic_obvious_ood_provenance": _provenance(obvious_ood, "synthetic_obvious_ood"),
        "candidate_records": candidate_records,
        "candidate_objects": candidate_objects,
        "selected_candidate_id": selected_id,
        "selection_status": (
            "selected" if selected_id is not None else "no_qualified_candidate"
        ),
    }


def _diagnose_target_segments(
    *,
    selections: Mapping[str, Mapping[str, Any]],
    target_segments: Mapping[str, Sequence[Any]],
    candidate_assessor: CandidateAssessor,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primitives: dict[str, dict[str, Any]] = {}
    return_plot_specs: list[dict[str, Any]] = []
    for primitive in ("dig", "return"):
        selection = selections[primitive]
        feature_order = tuple(str(value) for value in selection["feature_order"])
        v1_candidate = selection["candidate_objects"]["axis_p01_p99_v1"]
        lower, upper = _axis_bounds(v1_candidate, expected_width=len(feature_order))
        selected_id = selection["selected_candidate_id"]
        selected_candidate = (
            None
            if selected_id is None
            else selection["candidate_objects"][str(selected_id)]
        )
        records: list[dict[str, Any]] = []
        for segment in target_segments[primitive]:
            feature = _target_feature_matrix(
                segment,
                feature_order=feature_order,
                primitive=primitive,
            )
            v1_assessment = candidate_assessor(v1_candidate, feature)
            v1_mask = _assessment_mask(
                v1_assessment,
                expected_length=len(feature),
                label=f"{primitive} target v1 assessment",
            )
            expected_v1_mask = np.logical_and(feature >= lower, feature <= upper).all(axis=1)
            if not np.array_equal(v1_mask, expected_v1_mask):
                raise SupportContractAuditError(
                    f"{primitive} v1 assessment disagrees with its axis bounds"
                )
            if selected_candidate is None:
                selected_mask = None
                selected_assessment = None
            else:
                selected_assessment = candidate_assessor(selected_candidate, feature)
                selected_mask = _assessment_mask(
                    selected_assessment,
                    expected_length=len(feature),
                    label=f"{primitive} target selected assessment",
                )
            attribution = _cause_attribution(
                feature=feature,
                feature_order=feature_order,
                lower=lower,
                upper=upper,
            )
            record = {
                "segment": _segment_record(segment, primitive=primitive),
                "frame_count": int(feature.shape[0]),
                "v1_axis_p01_p99": {
                    "in_support_fraction": float(np.mean(v1_mask)),
                    "out_of_support_frame_count": int(np.count_nonzero(~v1_mask)),
                    "assessment": _assessment_summary(v1_assessment),
                },
                "selected_support_contract": _selected_target_view(
                    selected_id=selected_id,
                    selected_mask=selected_mask,
                    selected_assessment=selected_assessment,
                ),
                "cause_attribution": attribution,
                "interpretation": _target_interpretation(
                    v1_mask=v1_mask,
                    selected_id=selected_id,
                    selected_mask=selected_mask,
                ),
                "feature_distribution": _feature_distribution(
                    feature=feature,
                    feature_order=feature_order,
                    lower=lower,
                    upper=upper,
                ),
                "recorded_target_trace": build_recorded_target_trace(
                    segment=segment,
                    feature=feature,
                    feature_order=feature_order,
                ),
            }
            records.append(record)
            if primitive == "return":
                return_plot_specs.append(
                    {
                        "segment_id": record["segment"]["segment_id"],
                        "feature": feature,
                        "feature_order": feature_order,
                        "lower": lower,
                        "upper": upper,
                        "v1_in_support_fraction": record["v1_axis_p01_p99"][
                            "in_support_fraction"
                        ],
                        "selected_candidate_id": selected_id,
                        "selected_status": record["selected_support_contract"]["status"],
                    }
                )
        primitives[primitive] = {
            "segment_count": len(records),
            "segments": records,
            "aggregate": _target_aggregate(records),
        }
    return (
        {
            "schema": SUPPORT_CONTRACT_AUDIT_TARGET_SCHEMA,
            "support_contract_version": SUPPORT_CONTRACT_VERSION,
            "evidence_kind": EVIDENCE_KIND,
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
            "target_rollout_used_for_selection": False,
            "cause_attribution_limit": (
                "numeric-distribution attribution identifies the feature group "
                "that violates v1 bounds; it does not by itself establish a "
                "time-alignment or field-semantic root cause"
            ),
            "primitives": primitives,
        },
        return_plot_specs,
    )


def _select_candidate(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    qualified = [record for record in records if bool(record["qualified"])]
    if not qualified:
        return None
    return min(
        qualified,
        key=lambda record: (
            -float(record["synthetic_obvious_ood_rejection"]),
            -float(record["validation_normal_coverage"]),
            int(record["priority"]),
        ),
    )


def _qualification_status(*, coverage_ok: bool, rejection_ok: bool) -> str:
    if coverage_ok and rejection_ok:
        return "qualified"
    if not coverage_ok and not rejection_ok:
        return "rejected_validation_coverage_and_obvious_ood_rejection"
    if not coverage_ok:
        return "rejected_validation_coverage"
    return "rejected_obvious_ood_rejection"


def _candidate_validation_view(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in (
            "candidate_id",
            "priority",
            "validation_normal_coverage",
            "synthetic_obvious_ood_rejection",
            "validation_normal_coverage_passed",
            "synthetic_obvious_ood_rejection_passed",
            "qualified",
            "qualification_status",
        )
    }


def _selected_target_view(
    *,
    selected_id: str | None,
    selected_mask: np.ndarray | None,
    selected_assessment: Any | None,
) -> dict[str, Any]:
    if selected_id is None or selected_mask is None:
        return {
            "status": "not_evaluated_no_qualified_candidate",
            "candidate_id": None,
        }
    passed = bool(np.all(selected_mask))
    return {
        "status": "supported" if passed else "out_of_support",
        "candidate_id": selected_id,
        "in_support_fraction": float(np.mean(selected_mask)),
        "out_of_support_frame_count": int(np.count_nonzero(~selected_mask)),
        "assessment": _assessment_summary(selected_assessment),
    }


def _target_interpretation(
    *,
    v1_mask: np.ndarray,
    selected_id: str | None,
    selected_mask: np.ndarray | None,
) -> str:
    if bool(np.all(v1_mask)):
        return "v1_supported"
    if selected_id is None or selected_mask is None:
        return "no_validation_qualified_support_contract"
    if bool(np.all(selected_mask)):
        if selected_id == "axis_p01_p99_v1":
            return "v1_out_of_support_under_selected_v1"
        return "v1_axis_tail_accepted_by_validation_selected_contract"
    return "out_of_support_under_validation_selected_contract"


def _cause_attribution(
    *,
    feature: np.ndarray,
    feature_order: Sequence[str],
    lower: np.ndarray,
    upper: np.ndarray,
) -> dict[str, Any]:
    outside = np.logical_or(feature < lower, feature > upper)
    groups: dict[str, dict[str, Any]] = {}
    for group in ("qpos", "qvel", "token"):
        indices = [
            index
            for index, name in enumerate(feature_order)
            if _feature_group(name) == group
        ]
        if not indices:
            raise SupportContractAuditError(
                f"v1 feature order has no {group} fields"
            )
        group_outside = outside[:, indices]
        names = [feature_order[index] for index in indices]
        feature_counts = {
            name: int(np.count_nonzero(group_outside[:, offset]))
            for offset, name in enumerate(names)
            if int(np.count_nonzero(group_outside[:, offset])) > 0
        }
        groups[group] = {
            "out_of_support_frame_count": int(np.count_nonzero(group_outside.any(axis=1))),
            "out_of_support_feature_value_count": int(np.count_nonzero(group_outside)),
            "violating_feature_counts": feature_counts,
        }
    active = [
        name
        for name, payload in groups.items()
        if int(payload["out_of_support_frame_count"]) > 0
    ]
    if not active:
        dominant = "none"
    elif len(active) == 1:
        dominant = active[0]
    else:
        dominant = "mixed"
    return {
        "basis": "axis_p01_p99_v1_feature_bounds",
        "dominant_group": dominant,
        "groups": groups,
    }


def _feature_distribution(
    *,
    feature: np.ndarray,
    feature_order: Sequence[str],
    lower: np.ndarray,
    upper: np.ndarray,
) -> list[dict[str, Any]]:
    outside = np.logical_or(feature < lower, feature > upper)
    records: list[dict[str, Any]] = []
    for index, name in enumerate(feature_order):
        values = feature[:, index]
        records.append(
            {
                "field": name,
                "group": _feature_group(name),
                "recorded_min": float(np.min(values)),
                "recorded_max": float(np.max(values)),
                "strict_train_p01": float(lower[index]),
                "strict_train_p99": float(upper[index]),
                "out_of_support_frame_count": int(np.count_nonzero(outside[:, index])),
            }
        )
    return records


def _target_aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected_statuses = [
        str(record["selected_support_contract"]["status"])
        for record in records
    ]
    v1_oos = sum(
        int(record["v1_axis_p01_p99"]["out_of_support_frame_count"]) > 0
        for record in records
    )
    dominant_groups: dict[str, int] = {}
    for record in records:
        group = str(record["cause_attribution"]["dominant_group"])
        dominant_groups[group] = dominant_groups.get(group, 0) + 1
    return {
        "v1_out_of_support_segment_count": v1_oos,
        "selected_supported_segment_count": selected_statuses.count("supported"),
        "selected_out_of_support_segment_count": selected_statuses.count("out_of_support"),
        "not_evaluated_segment_count": selected_statuses.count(
            "not_evaluated_no_qualified_candidate"
        ),
        "dominant_cause_group_counts": dict(sorted(dominant_groups.items())),
    }


def _resolve_dependencies(
    *,
    candidate_fitter: CandidateFitter | None,
    candidate_assessor: CandidateAssessor | None,
    obvious_ood_builder: ObviousOodBuilder | None,
) -> tuple[CandidateFitter, CandidateAssessor, ObviousOodBuilder]:
    if (
        candidate_fitter is not None
        and candidate_assessor is not None
        and obvious_ood_builder is not None
    ):
        return candidate_fitter, candidate_assessor, obvious_ood_builder
    try:
        from testbed.data.act_support_contract import (
            assess_support_candidate,
            fit_registered_support_candidates,
            generate_frozen_obvious_ood,
        )
    except ImportError as exc:  # pragma: no cover - protects partial deployments.
        raise SupportContractAuditError(
            "support-contract data APIs are unavailable; inject dependencies or update data layer"
        ) from exc
    return (
        candidate_fitter or fit_registered_support_candidates,
        candidate_assessor or assess_support_candidate,
        obvious_ood_builder or generate_frozen_obvious_ood,
    )


def _normalise_lineage(source_lineage: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source_lineage, Mapping) or not source_lineage:
        raise SupportContractAuditError("source_lineage must be a non-empty mapping")
    if any(value is None for value in source_lineage.values()):
        raise SupportContractAuditError("source_lineage contains an unresolved value")
    return _json_ready(dict(source_lineage))


def _normalise_primitive_mapping(
    value: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SupportContractAuditError(f"{label} must be a mapping")
    expected = {"dig", "return"}
    observed = {str(key) for key in value}
    if observed != expected:
        raise SupportContractAuditError(
            f"{label} must contain exactly dig and return, got {sorted(observed)!r}"
        )
    result = {primitive: value[primitive] for primitive in expected}
    for primitive, item in result.items():
        if item is None:
            raise SupportContractAuditError(f"{label}[{primitive}] is missing")
    return result


def _feature_order(rows: Any) -> tuple[str, ...]:
    raw = _field(rows, "feature_order", None)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise SupportContractAuditError("support rows feature_order must be a sequence")
    values = tuple(str(value) for value in raw)
    if not values or len(values) != len(set(values)):
        raise SupportContractAuditError("support rows feature_order must be non-empty and unique")
    return values


def _feature_matrix_from_object(
    value: Any,
    *,
    names: Sequence[str],
    label: str,
    expected_width: int,
) -> np.ndarray:
    raw = None
    for name in names:
        raw = _field(value, name, None)
        if raw is not None:
            break
    if raw is None:
        raise SupportContractAuditError(f"{label} is missing one of {tuple(names)!r}")
    matrix = _finite_matrix(raw, label=label)
    if matrix.shape[1] != expected_width:
        raise SupportContractAuditError(
            f"{label} width {matrix.shape[1]} does not match feature order {expected_width}"
        )
    return matrix


def _candidate_id(candidate: Any) -> str:
    for name in ("candidate_id", "rule_id", "id"):
        value = _field(candidate, name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise SupportContractAuditError("fitted support candidate lacks candidate_id")


def _candidate_definition(candidate: Any) -> dict[str, Any]:
    as_dict = _field(candidate, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        if not isinstance(value, Mapping):
            raise SupportContractAuditError("candidate as_dict() must return a mapping")
        return _json_ready(dict(value))
    fields = {}
    for name in (
        "candidate_id",
        "feature_order",
        "lower",
        "upper",
        "mean",
        "covariance",
        "ridge",
        "threshold",
        "threshold_rule",
    ):
        value = _field(candidate, name, None)
        if value is not None:
            fields[name] = value
    return _json_ready(fields)


def _axis_bounds(candidate: Any, *, expected_width: int) -> tuple[np.ndarray, np.ndarray]:
    lower = _first_present_field(candidate, ("lower", "p01", "lower_bound"))
    upper = _first_present_field(candidate, ("upper", "p99", "upper_bound"))
    if lower is None or upper is None:
        definition = _candidate_definition(candidate)
        lower = lower if lower is not None else _first_present_field(
            definition,
            ("lower", "p01", "lower_bound"),
        )
        upper = upper if upper is not None else _first_present_field(
            definition,
            ("upper", "p99", "upper_bound"),
        )
    lower_array = _finite_vector(lower, label="v1 lower bound")
    upper_array = _finite_vector(upper, label="v1 upper bound")
    if lower_array.shape != (expected_width,) or upper_array.shape != (expected_width,):
        raise SupportContractAuditError("v1 axis bound width does not match feature order")
    if np.any(lower_array > upper_array):
        raise SupportContractAuditError("v1 axis bounds are inverted")
    return lower_array, upper_array


def _assessment_mask(assessment: Any, *, expected_length: int, label: str) -> np.ndarray:
    raw = _first_present_field(assessment, ("frame_in_support", "in_support"))
    if raw is None:
        raise SupportContractAuditError(f"{label} lacks frame_in_support")
    mask = np.asarray(raw)
    if mask.ndim != 1 or mask.shape[0] != expected_length:
        raise SupportContractAuditError(
            f"{label} has support mask shape {mask.shape}, expected ({expected_length},)"
        )
    if mask.dtype.kind not in "buif":
        raise SupportContractAuditError(f"{label} support mask has non-numeric dtype")
    if not np.isfinite(mask.astype(np.float64)).all():
        raise SupportContractAuditError(f"{label} support mask contains non-finite values")
    return mask.astype(bool, copy=False)


def _assessment_summary(assessment: Any) -> dict[str, Any]:
    as_dict = _field(assessment, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        if not isinstance(value, Mapping):
            raise SupportContractAuditError("assessment as_dict() must return a mapping")
        return _json_ready(dict(value))
    fields: dict[str, Any] = {}
    for name in ("threshold", "scores", "violations", "frame_in_support", "rule_id"):
        value = _field(assessment, name, None)
        if value is not None:
            fields[name] = value
    return _json_ready(fields)


def _provenance(value: Any, label: str) -> dict[str, Any]:
    names = {
        "validation": ("validation_provenance", "provenance"),
        "synthetic_obvious_ood": ("anchor_provenance", "provenance"),
    }.get(label, (f"{label}_provenance", "provenance"))
    for name in names:
        raw = _field(value, name, None)
        if raw is None:
            continue
        if isinstance(raw, Mapping):
            return _json_ready(dict(raw))
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            records: list[Any] = []
            for item in raw:
                as_dict = _field(item, "as_dict", None)
                if callable(as_dict):
                    item = as_dict()
                records.append(item)
            return {"rows": _json_ready(records)}
        as_dict = _field(raw, "as_dict", None)
        if callable(as_dict):
            mapped = as_dict()
            if isinstance(mapped, Mapping):
                return _json_ready(dict(mapped))
    return {"status": "not_provided_by_data_layer"}


def _target_feature_matrix(
    segment: Any,
    *,
    feature_order: Sequence[str],
    primitive: str,
) -> np.ndarray:
    expected_width = len(feature_order)
    for name in ("support_features", "feature_matrix", "features"):
        raw = _field(segment, name, None)
        if raw is None:
            continue
        matrix = _finite_matrix(raw, label=f"{primitive} segment {name}")
        if matrix.shape[1] != expected_width:
            raise SupportContractAuditError(
                f"{primitive} segment {name} width does not match support feature order"
            )
        return matrix
    frames = _field(segment, "frames", None)
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)) or not frames:
        raise SupportContractAuditError(
            f"{primitive} target segment needs a feature matrix or non-empty frames"
        )
    rows: list[np.ndarray] = []
    for index, frame in enumerate(frames):
        direct = _first_present_field(frame, ("support_feature", "feature", "features"))
        if direct is not None:
            vector = _finite_vector(direct, label=f"{primitive} frame {index} feature")
        else:
            qpos = _finite_vector(_field(frame, "qpos", None), label=f"{primitive} frame {index} qpos")
            qvel = _finite_vector(_field(frame, "qvel", None), label=f"{primitive} frame {index} qvel")
            token = _finite_vector(_field(frame, "token", None), label=f"{primitive} frame {index} token")
            if qpos.shape != (4,) or qvel.shape != (4,):
                raise SupportContractAuditError(
                    f"{primitive} frame {index} qpos/qvel must each have width four"
                )
            vector = np.concatenate((qpos, qvel, token))
        if vector.shape != (expected_width,):
            raise SupportContractAuditError(
                f"{primitive} frame {index} feature width {vector.size} does not match {expected_width}"
            )
        rows.append(vector)
    return np.stack(rows, axis=0).astype(np.float64, copy=False)


def _segment_record(segment: Any, *, primitive: str) -> dict[str, Any]:
    segment_id = _field(segment, "segment_id", None)
    if segment_id is None or not str(segment_id).strip():
        start = _field(segment, "start_action_step_id", "unknown")
        end = _field(segment, "end_action_step_id", "unknown")
        segment_id = f"{primitive}:{start}-{end}"
    record: dict[str, Any] = {"segment_id": str(segment_id), "primitive": primitive}
    for name in (
        "start_action_step_id",
        "end_action_step_id",
        "token_sha256",
        "token_source",
        "model_token_key",
        "primitive_cycle_indices",
    ):
        value = _field(segment, name, None)
        if value is not None:
            record[name] = value
    return _json_ready(record)


def _feature_group(name: str) -> str:
    if name.startswith("qpos["):
        return "qpos"
    if name.startswith("qvel["):
        return "qvel"
    return "token"


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _first_present_field(value: Any, names: Sequence[str]) -> Any:
    for name in names:
        item = _field(value, name, None)
        if item is not None:
            return item
    return None


def _finite_matrix(value: Any, *, label: str) -> np.ndarray:
    if value is None:
        raise SupportContractAuditError(f"{label} is missing")
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise SupportContractAuditError(f"{label} must be a non-empty rank-2 matrix")
    if not np.isfinite(matrix).all():
        raise SupportContractAuditError(f"{label} contains non-finite values")
    return matrix


def _finite_vector(value: Any, *, label: str) -> np.ndarray:
    if value is None:
        raise SupportContractAuditError(f"{label} is missing")
    vector = np.asarray(value, dtype=np.float64).reshape(-1)
    if vector.size == 0 or not np.isfinite(vector).all():
        raise SupportContractAuditError(f"{label} must be a non-empty finite vector")
    return vector


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise SupportContractAuditError("artifact JSON cannot contain non-finite floats")
    return value


__all__ = [
    "CANDIDATE_PRIORITY",
    "EVIDENCE_KIND",
    "SUPPORT_CONTRACT_AUDIT_CANDIDATES_SCHEMA",
    "SUPPORT_CONTRACT_AUDIT_MANIFEST_SCHEMA",
    "SUPPORT_CONTRACT_AUDIT_TARGET_SCHEMA",
    "SUPPORT_CONTRACT_AUDIT_VALIDATION_SCHEMA",
    "SUPPORT_CONTRACT_VERSION",
    "SupportContractAuditError",
    "SYNTHETIC_OBVIOUS_OOD_REJECTION_MIN",
    "VALIDATION_NORMAL_COVERAGE_MIN",
    "run_support_contract_audit",
]
