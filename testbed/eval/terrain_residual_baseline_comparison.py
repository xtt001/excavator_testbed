"""Offline baseline-comparison evidence for terrain residual planning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA = "terrain_residual_planner_baseline_comparison_v1"
SOURCE = "explicit_offline_residual_planner_baseline_comparison"
DEFAULT_PROFILE = "heuristic_only_offline_baseline_comparison"
BRANCH_ORDER = [
    "current_planner_baseline",
    "heuristic_residual_pipeline",
    "calibrated_residual_pipeline",
]


def build_residual_planner_baseline_comparison(
    *,
    current_planner_evidence: Mapping[str, Any],
    target_residual_report: Mapping[str, Any],
    candidate_generation: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    candidate_scoring: Mapping[str, Any],
    candidate_effect_summary: Mapping[str, Any],
    calibrated_branch_evidence: Mapping[str, Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build an offline-only comparison of current, heuristic, and calibrated branches."""

    branches = {
        "current_planner_baseline": _current_branch(
            current_planner_evidence,
            target_residual_report,
        ),
        "heuristic_residual_pipeline": _heuristic_branch(
            candidate_generation,
            candidate_evidence,
            candidate_scoring,
            candidate_effect_summary,
        ),
        "calibrated_residual_pipeline": _calibrated_branch(
            calibrated_branch_evidence,
        ),
    }

    status, validation_errors = _comparison_status(branches)
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "branch_order": list(BRANCH_ORDER),
        "branches": branches,
        "comparison_limits": _comparison_limits(),
        "validation_errors": validation_errors,
    }


def _current_branch(
    current_planner_evidence: Mapping[str, Any],
    target_residual_report: Mapping[str, Any],
) -> dict[str, Any]:
    if not _has_present_status(current_planner_evidence):
        return {
            "branch_name": "current_planner_baseline",
            "status": "invalid",
            "reason": "current_planner_evidence status must be present",
        }
    if not _has_present_status(target_residual_report):
        return {
            "branch_name": "current_planner_baseline",
            "status": "invalid",
            "reason": "target_residual_report status must be present",
        }

    summary = _target_report_summary(target_residual_report)
    return {
        "branch_name": "current_planner_baseline",
        "status": "present",
        "source_status": str(current_planner_evidence.get("status")),
        "rollout_evidence": {
            "planned_cycle_count": current_planner_evidence.get(
                "planned_cycle_count"
            ),
            "actual_cycle_count": current_planner_evidence.get("actual_cycle_count"),
            "payload_summary": current_planner_evidence.get("payload_summary"),
        },
        "target_residual_evidence": {
            "report_status": str(target_residual_report.get("status")),
            "latest_snapshot_row_index": summary.get("latest_snapshot_row_index"),
            "latest_target_positive_residual_depth_sum_m": summary.get(
                "latest_target_positive_residual_depth_sum_m"
            ),
            "latest_target_overdig_depth_sum_m": summary.get(
                "latest_target_overdig_depth_sum_m"
            ),
            "latest_outside_target_removed_depth_sum_m": summary.get(
                "latest_outside_target_removed_depth_sum_m"
            ),
            "convergence_summary_status": summary.get("convergence_summary_status"),
            "convergence_point_count": summary.get("convergence_point_count"),
            "convergence_diagnostic_trend": summary.get(
                "convergence_diagnostic_trend"
            ),
        },
        "target_success_claim": "not_claimed",
    }


def _heuristic_branch(
    candidate_generation: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    candidate_scoring: Mapping[str, Any],
    candidate_effect_summary: Mapping[str, Any],
) -> dict[str, Any]:
    status_error = _first_heuristic_status_error(
        candidate_generation=candidate_generation,
        candidate_evidence=candidate_evidence,
        candidate_scoring=candidate_scoring,
        candidate_effect_summary=candidate_effect_summary,
    )
    if status_error is not None:
        return {
            "branch_name": "heuristic_residual_pipeline",
            "status": "invalid",
            "reason": status_error,
        }

    coverage = _mapping_value(candidate_generation.get("positive_residual_coverage"))
    ranking = _mapping_value(candidate_scoring.get("ranking"))
    score_summary = _mapping_value(candidate_scoring.get("score_summary"))
    aggregate_summary = _mapping_value(
        candidate_effect_summary.get("aggregate_summary")
    )
    return {
        "branch_name": "heuristic_residual_pipeline",
        "status": "present",
        "candidate_count": candidate_generation.get("candidate_count"),
        "positive_residual_cell_count": candidate_generation.get(
            "positive_residual_cell_count"
        ),
        "candidate_coverage_status": coverage.get("status"),
        "constraint_summary": candidate_evidence.get("constraint_summary"),
        "score_summary": {
            "best_candidate_id": score_summary.get("best_candidate_id"),
            "best_score": score_summary.get("best_score"),
            "worst_candidate_id": score_summary.get("worst_candidate_id"),
            "worst_score": score_summary.get("worst_score"),
        },
        "diagnostic_ranking": {
            "ranked_candidate_ids": ranking.get("ranked_candidate_ids"),
            "best_candidate_id": score_summary.get("best_candidate_id"),
        },
        "effect_summary": {
            "effect_record_count": candidate_effect_summary.get(
                "effect_record_count"
            ),
            "payload_proxy_fraction_max": aggregate_summary.get(
                "payload_proxy_fraction_max"
            ),
            "expected_removed_volume_total_m3": aggregate_summary.get(
                "expected_removed_volume_total_m3"
            ),
            "target_removed_volume_total_m3": aggregate_summary.get(
                "target_removed_volume_total_m3"
            ),
            "outside_target_removed_volume_total_m3": aggregate_summary.get(
                "outside_target_removed_volume_total_m3"
            ),
            "overdig_volume_delta_total_m3": aggregate_summary.get(
                "overdig_volume_delta_total_m3"
            ),
            "max_payload_proxy_candidate_id": aggregate_summary.get(
                "max_payload_proxy_candidate_id"
            ),
            "max_outside_target_volume_candidate_id": aggregate_summary.get(
                "max_outside_target_volume_candidate_id"
            ),
            "max_overdig_volume_candidate_id": aggregate_summary.get(
                "max_overdig_volume_candidate_id"
            ),
        },
        "closed_loop_proof_status": "not_run",
    }


def _calibrated_branch(
    calibrated_branch_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(calibrated_branch_evidence, Mapping):
        return {
            "branch_name": "calibrated_residual_pipeline",
            "status": "invalid",
            "reason": "calibrated branch evidence must be a mapping",
        }
    if "usable_record_count" not in calibrated_branch_evidence:
        return {
            "branch_name": "calibrated_residual_pipeline",
            "status": "invalid",
            "reason": "calibrated branch evidence must include usable gold sample count",
        }

    usable_gold_sample_count = calibrated_branch_evidence.get("usable_record_count")
    usable_extracted_record_count = calibrated_branch_evidence.get(
        "usable_extracted_record_count",
        0,
    )
    schema_gap_summary = _mapping_value(
        calibrated_branch_evidence.get("schema_gap_summary")
    )
    if usable_gold_sample_count == 0 and usable_extracted_record_count == 0:
        status = "not_evaluated"
        reason = "blocked_by_missing_gold_samples"
    else:
        status = "not_evaluated"
        reason = "calibrated_branch_not_fit_in_this_offline_comparison"

    return {
        "branch_name": "calibrated_residual_pipeline",
        "status": status,
        "reason": reason,
        "usable_gold_sample_count": usable_gold_sample_count,
        "usable_extracted_record_count": usable_extracted_record_count,
        "schema_gap_implication": schema_gap_summary.get("usable_record_implication"),
    }


def _comparison_status(
    branches: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    current_branch = branches["current_planner_baseline"]
    if current_branch["status"] != "present":
        return "invalid_current_planner_evidence", [current_branch["reason"]]

    heuristic_branch = branches["heuristic_residual_pipeline"]
    if heuristic_branch["status"] != "present":
        return "invalid_heuristic_evidence", [heuristic_branch["reason"]]

    calibrated_branch = branches["calibrated_residual_pipeline"]
    if calibrated_branch["status"] == "invalid":
        return "invalid_calibrated_evidence", [calibrated_branch["reason"]]

    return "present", []


def _first_heuristic_status_error(
    *,
    candidate_generation: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    candidate_scoring: Mapping[str, Any],
    candidate_effect_summary: Mapping[str, Any],
) -> str | None:
    for label, evidence in (
        ("candidate_generation", candidate_generation),
        ("candidate_evidence", candidate_evidence),
        ("candidate_scoring", candidate_scoring),
        ("candidate_effect_summary", candidate_effect_summary),
    ):
        if not _has_present_status(evidence):
            return f"{label} status must be present"
    return None


def _has_present_status(evidence: Any) -> bool:
    return isinstance(evidence, Mapping) and evidence.get("status") == "present"


def _mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _target_report_summary(target_residual_report: Mapping[str, Any]) -> Mapping[str, Any]:
    diagnostic_summary = target_residual_report.get("diagnostic_summary")
    if isinstance(diagnostic_summary, Mapping):
        return diagnostic_summary
    return _mapping_value(target_residual_report.get("summary"))


def _comparison_limits() -> dict[str, str]:
    return {
        "closed_loop_resimulation_status": "not_run",
        "counterfactual_cycle_count_status": "not_available",
        "cycle_time_status": "not_available",
        "production_integration_status": "not_integrated",
        "official_success_semantics_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


__all__ = ["build_residual_planner_baseline_comparison"]
