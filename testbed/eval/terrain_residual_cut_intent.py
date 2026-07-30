"""Eval-only heuristic cut-intent evidence for terrain residual planning."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "terrain_residual_heuristic_cut_intent_v1"
SOURCE = "explicit_heuristic_residual_cut_intent"
DEFAULT_PROFILE = "phase6e_heuristic_residual_cut_intent"
SELECTION_POLICY = "score_ranking_first"
HEURISTIC_BRANCH_NAME = "heuristic_residual_pipeline"
TARGET_REQUIRED_FIELDS = (
    "grid_shape",
    "row_start",
    "row_end",
    "col_start",
    "col_end",
    "target_depth_m",
    "official_semantics",
)
BRANCH_PLAN_ERROR = (
    "branch_run_plan must be present with heuristic branch readiness and "
    "cut-intent boundary evidence"
)
SCORING_ERROR = (
    "candidate_scoring must be present with a diagnostic offline ranking first entry"
)
GENERATION_ERROR = (
    "candidate_generation must include the ranked candidate with required candidate fields"
)
EVIDENCE_ERROR = (
    "candidate_evidence must include the ranked candidate evidence record"
)
EFFECT_SUMMARY_ERROR = (
    "candidate_effect_summary must include the ranked candidate summary record"
)
TARGET_SPEC_ERROR = (
    "target_spec must include grid_shape, row/col bounds, target_depth_m, and "
    "official_semantics"
)


def build_heuristic_residual_cut_intent(
    *,
    branch_run_plan: Mapping[str, Any],
    candidate_generation: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    candidate_scoring: Mapping[str, Any],
    candidate_effect_summary: Mapping[str, Any],
    target_spec: Mapping[str, Any],
    selection_policy: Any,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build one eval-only B-branch cut intent from explicit heuristic evidence."""

    b_branch_status, branch_errors = _b_branch_status(branch_run_plan)
    if branch_errors:
        return _cut_intent_result(
            status="invalid_branch_run_plan",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=branch_errors,
        )

    if selection_policy != SELECTION_POLICY:
        return _cut_intent_result(
            status="invalid_selection_policy",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=[
                "selection_policy must be explicit score_ranking_first",
            ],
        )

    ranking_entry, score_record, scoring_errors = _selected_score_evidence(
        candidate_scoring
    )
    if scoring_errors:
        return _cut_intent_result(
            status="invalid_candidate_scoring",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=scoring_errors,
        )

    candidate_id = ranking_entry["candidate_id"]
    candidate, generation_errors = _candidate_for_id(
        candidate_generation,
        candidate_id,
    )
    if generation_errors:
        return _cut_intent_result(
            status="invalid_candidate_generation",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=generation_errors,
        )

    evidence_record, evidence_errors = _evidence_for_id(
        candidate_evidence,
        candidate_id,
    )
    if evidence_errors:
        return _cut_intent_result(
            status="invalid_candidate_evidence",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=evidence_errors,
        )

    effect_summary, effect_errors = _effect_summary_for_id(
        candidate_effect_summary,
        candidate_id,
    )
    if effect_errors:
        return _cut_intent_result(
            status="invalid_candidate_effect_summary",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=effect_errors,
        )

    target_provenance, target_errors = _target_spec_provenance(target_spec)
    if target_errors:
        return _cut_intent_result(
            status="invalid_target_spec",
            profile=profile,
            selection_policy=selection_policy,
            b_branch_status=b_branch_status,
            cut_intent={},
            validation_errors=target_errors,
        )

    cut_intent = _cut_intent_record(
        candidate=candidate,
        evidence_record=evidence_record,
        ranking_entry=ranking_entry,
        score_record=score_record,
        effect_summary=effect_summary,
        target_provenance=target_provenance,
        selection_policy=selection_policy,
    )
    return _cut_intent_result(
        status="present",
        profile=profile,
        selection_policy=selection_policy,
        b_branch_status=b_branch_status,
        cut_intent=cut_intent,
        validation_errors=[],
    )


def _b_branch_status(
    branch_run_plan: Mapping[str, Any],
) -> tuple[dict[str, str], list[str]]:
    default = {
        "status": "invalid",
        "input_readiness_status": "missing",
        "runtime_integration_status": "missing",
        "cut_intent_boundary_status": "missing",
    }
    if not isinstance(branch_run_plan, Mapping):
        return default, [BRANCH_PLAN_ERROR]
    if (
        branch_run_plan.get("status") != "present"
        or branch_run_plan.get("offline_only") is not True
    ):
        return default, [BRANCH_PLAN_ERROR]
    branch_run_plans = branch_run_plan.get("branch_run_plans")
    if not isinstance(branch_run_plans, Mapping):
        return default, [BRANCH_PLAN_ERROR]
    heuristic = branch_run_plans.get(HEURISTIC_BRANCH_NAME)
    if not isinstance(heuristic, Mapping):
        return default, [BRANCH_PLAN_ERROR]
    b_status = {
        "status": str(heuristic.get("status", "missing")),
        "input_readiness_status": str(
            heuristic.get("input_readiness_status", "missing")
        ),
        "runtime_integration_status": str(
            heuristic.get("runtime_integration_status", "missing")
        ),
        "cut_intent_boundary_status": str(
            heuristic.get("cut_intent_boundary_status", "missing")
        ),
    }
    if b_status != {
        "status": "present",
        "input_readiness_status": "present",
        "runtime_integration_status": "not_integrated",
        "cut_intent_boundary_status": "present",
    }:
        return b_status, [BRANCH_PLAN_ERROR]

    boundary = branch_run_plan.get("executable_cut_intent_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("status") != "present":
        return b_status, [BRANCH_PLAN_ERROR]
    return b_status, []


def _selected_score_evidence(
    candidate_scoring: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if (
        not isinstance(candidate_scoring, Mapping)
        or candidate_scoring.get("status") != "present"
        or candidate_scoring.get("offline_only") is not True
    ):
        return {}, {}, [SCORING_ERROR]
    ranking = candidate_scoring.get("ranking")
    if (
        not isinstance(ranking, Mapping)
        or ranking.get("semantics") != "diagnostic_offline_ranking_only"
        or ranking.get("no_production_action") is not True
    ):
        return {}, {}, [SCORING_ERROR]
    ranked_candidates = ranking.get("ranked_candidates")
    if (
        isinstance(ranked_candidates, (str, bytes))
        or not isinstance(ranked_candidates, Sequence)
        or not ranked_candidates
        or not isinstance(ranked_candidates[0], Mapping)
    ):
        return {}, {}, [SCORING_ERROR]

    selected = {
        "rank": _parse_positive_integer(ranked_candidates[0].get("rank")),
        "candidate_id": str(ranked_candidates[0].get("candidate_id", "")),
        "total_score": _parse_finite_float(ranked_candidates[0].get("total_score")),
        "input_index": _parse_nonnegative_integer(
            ranked_candidates[0].get("input_index")
        ),
    }
    if (
        selected["rank"] is None
        or selected["rank"] != 1
        or not selected["candidate_id"]
        or selected["total_score"] is None
        or selected["input_index"] is None
    ):
        return {}, {}, [SCORING_ERROR]

    score_record = _record_for_id(
        candidate_scoring.get("score_records"),
        selected["candidate_id"],
    )
    if not score_record:
        return {}, {}, [SCORING_ERROR]
    if score_record.get("offline_only") is not True:
        return {}, {}, [SCORING_ERROR]
    return selected, score_record, []


def _candidate_for_id(
    candidate_generation: Mapping[str, Any],
    candidate_id: str,
) -> tuple[dict[str, Any], list[str]]:
    if (
        not isinstance(candidate_generation, Mapping)
        or candidate_generation.get("status") != "present"
        or candidate_generation.get("offline_only") is not True
    ):
        return {}, [GENERATION_ERROR]
    candidate = _record_for_id(candidate_generation.get("candidates"), candidate_id)
    if not candidate:
        return {}, [GENERATION_ERROR]

    parsed = {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "anchor_cell_index": _parse_nonnegative_integer(
            candidate.get("anchor_cell_index")
        ),
        "anchor_row": _parse_nonnegative_integer(candidate.get("anchor_row")),
        "anchor_col": _parse_nonnegative_integer(candidate.get("anchor_col")),
        "direction": str(candidate.get("direction", "")),
        "candidate_depth_m": _parse_nonnegative_float(
            candidate.get("candidate_depth_m")
        ),
        "offline_only": candidate.get("offline_only") is True,
    }
    if (
        parsed["candidate_id"] != candidate_id
        or parsed["anchor_cell_index"] is None
        or parsed["anchor_row"] is None
        or parsed["anchor_col"] is None
        or not parsed["direction"]
        or parsed["candidate_depth_m"] is None
        or parsed["offline_only"] is not True
    ):
        return {}, [GENERATION_ERROR]
    return parsed, []


def _evidence_for_id(
    candidate_evidence: Mapping[str, Any],
    candidate_id: str,
) -> tuple[dict[str, Any], list[str]]:
    if (
        not isinstance(candidate_evidence, Mapping)
        or candidate_evidence.get("status") != "present"
        or candidate_evidence.get("offline_only") is not True
    ):
        return {}, [EVIDENCE_ERROR]
    evidence = _record_for_id(candidate_evidence.get("evidence_records"), candidate_id)
    if not evidence or evidence.get("offline_only") is not True:
        return {}, [EVIDENCE_ERROR]
    return dict(evidence), []


def _effect_summary_for_id(
    candidate_effect_summary: Mapping[str, Any],
    candidate_id: str,
) -> tuple[dict[str, Any], list[str]]:
    if (
        not isinstance(candidate_effect_summary, Mapping)
        or candidate_effect_summary.get("status") != "present"
        or candidate_effect_summary.get("offline_only") is not True
    ):
        return {}, [EFFECT_SUMMARY_ERROR]
    summary = _record_for_id(
        candidate_effect_summary.get("summary_records"),
        candidate_id,
    )
    if not summary or summary.get("offline_only") is not True:
        return {}, [EFFECT_SUMMARY_ERROR]

    required_numbers = (
        "expected_removed_volume_m3",
        "target_removed_volume_m3",
        "outside_target_removed_volume_m3",
        "overdig_volume_delta_m3",
        "payload_proxy_fraction",
    )
    for field in required_numbers:
        if _parse_nonnegative_float(summary.get(field)) is None:
            return {}, [EFFECT_SUMMARY_ERROR]
    footprint_cell_count = _parse_nonnegative_integer(
        summary.get("footprint_cell_count")
    )
    if footprint_cell_count is None or not isinstance(
        summary.get("footprint_clipped_by_grid_boundary"),
        bool,
    ):
        return {}, [EFFECT_SUMMARY_ERROR]
    return dict(summary), []


def _target_spec_provenance(
    target_spec: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(target_spec, Mapping) or not all(
        field in target_spec for field in TARGET_REQUIRED_FIELDS
    ):
        return {}, [TARGET_SPEC_ERROR]
    depth = _parse_finite_float(target_spec.get("target_depth_m"))
    grid_shape = target_spec.get("grid_shape")
    if (
        depth is None
        or isinstance(grid_shape, (str, bytes))
        or not isinstance(grid_shape, Sequence)
        or len(grid_shape) != 2
    ):
        return {}, [TARGET_SPEC_ERROR]
    return {
        "source": "explicit_input_target_spec",
        "target_id": str(target_spec.get("target_id", "")),
        "grid_shape": list(grid_shape),
        "row_start": target_spec["row_start"],
        "row_end": target_spec["row_end"],
        "col_start": target_spec["col_start"],
        "col_end": target_spec["col_end"],
        "target_depth_m": depth,
        "official_semantics": str(target_spec["official_semantics"]),
    }, []


def _cut_intent_record(
    *,
    candidate: Mapping[str, Any],
    evidence_record: Mapping[str, Any],
    ranking_entry: Mapping[str, Any],
    score_record: Mapping[str, Any],
    effect_summary: Mapping[str, Any],
    target_provenance: Mapping[str, Any],
    selection_policy: str,
) -> dict[str, Any]:
    return {
        "cut_intent_candidate_id": candidate["candidate_id"],
        "candidate_id": candidate["candidate_id"],
        "offline_only": True,
        "anchor_cell_index": candidate["anchor_cell_index"],
        "anchor_row": candidate["anchor_row"],
        "anchor_col": candidate["anchor_col"],
        "direction": candidate["direction"],
        "candidate_depth_m": candidate["candidate_depth_m"],
        "score_rank_provenance": {
            "source": "explicit_candidate_heuristic_score_evidence",
            "selection_policy": selection_policy,
            "rank": ranking_entry["rank"],
            "total_score": ranking_entry["total_score"],
            "input_index": ranking_entry["input_index"],
            "score_record_status": (
                "present" if score_record.get("candidate_id") == candidate["candidate_id"] else "missing"
            ),
        },
        "effect_evidence_provenance": {
            "source": "explicit_candidate_effect_summary",
            "effect_status": str(effect_summary.get("effect_status")),
            "expected_removed_volume_m3": effect_summary[
                "expected_removed_volume_m3"
            ],
            "target_removed_volume_m3": effect_summary[
                "target_removed_volume_m3"
            ],
            "outside_target_removed_volume_m3": effect_summary[
                "outside_target_removed_volume_m3"
            ],
            "overdig_volume_delta_m3": effect_summary["overdig_volume_delta_m3"],
            "payload_proxy_fraction": effect_summary["payload_proxy_fraction"],
            "footprint_cell_count": effect_summary["footprint_cell_count"],
            "footprint_clipped_by_grid_boundary": effect_summary[
                "footprint_clipped_by_grid_boundary"
            ],
        },
        "target_spec_provenance": dict(target_provenance),
        "safety_stop_condition_provenance_status": (
            _safety_stop_condition_provenance_status(evidence_record)
        ),
        "runner_input_status": "ready_for_eval_harness",
        "production_runtime_action": False,
    }


def _safety_stop_condition_provenance_status(
    evidence_record: Mapping[str, Any],
) -> str:
    if evidence_record.get("depth_budget_status") and evidence_record.get(
        "return_alignment_cost_proxy"
    ):
        return "from_branch_run_plan_contract"
    return "incomplete"


def _cut_intent_result(
    *,
    status: str,
    profile: str,
    selection_policy: Any,
    b_branch_status: Mapping[str, Any],
    cut_intent: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "selection_policy": str(selection_policy),
        "b_branch_status": dict(b_branch_status),
        "cut_intent": dict(cut_intent),
        "validation_errors": validation_errors,
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(),
    }


def _record_for_id(records: Any, candidate_id: str) -> dict[str, Any]:
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        return {}
    for record in records:
        if isinstance(record, Mapping) and str(record.get("candidate_id", "")) == candidate_id:
            return dict(record)
    return {}


def _parse_positive_integer(value: Any) -> int | None:
    parsed = _parse_nonnegative_integer(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _parse_nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return None


def _parse_nonnegative_float(value: Any) -> float | None:
    parsed = _parse_finite_float(value)
    if parsed is None or parsed < 0.0:
        return None
    return parsed


def _parse_finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "run_artifact_status": "not_created",
        "branch_output_file_status": "not_created",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "command_space_control_status": "not_emitted",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses() -> dict[str, str]:
    return {
        "branch_run_plan_source": "explicit_input",
        "candidate_generation_source": "explicit_input",
        "candidate_evidence_source": "explicit_input",
        "candidate_scoring_source": "explicit_input",
        "candidate_effect_summary_source": "explicit_input",
        "target_spec_source": "explicit_input",
        "artifact_write_status": "not_written",
        "runner_execution_status": "not_run",
    }
