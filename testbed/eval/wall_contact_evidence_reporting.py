"""Aggregate readable, diagnostic-only wall-contact evidence summaries."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

DIAGNOSTIC_NEAR_WALL_THRESHOLD_M = 0.24
CONTACT_CATEGORIES = (
    "near_wall",
    "bucket_touch",
    "bucket_scrape_like",
    "forbidden_component",
    "high_force_collision",
)
_STATUS_VALUES = ("blocked", "invalid", "passed")
_PEAK_METRICS = (
    "peak_normal_force_n",
    "peak_tangential_force_n",
    "peak_total_force_n",
)
_RMS_METRICS = (
    "rms_normal_force_n",
    "rms_tangential_force_n",
    "rms_total_force_n",
)
_SUM_METRICS = (
    "normal_impulse_n_s",
    "session_count",
    "contact_duration_s",
    "callback_count",
    "contact_point_count",
)
_MAX_METRICS = (
    "maximum_session_duration_s",
    "maximum_tangential_displacement_m",
)


def summarize_geometry_paths(
    paths: Sequence[Mapping[str, Any]],
    *,
    diagnostic_near_wall_threshold_m: float = (
        DIAGNOSTIC_NEAR_WALL_THRESHOLD_M
    ),
) -> dict[str, Any]:
    """Group the complete geometry inventory without defining production policy."""

    groups: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    split_counts: Counter[str] = Counter()
    source_counts: Counter[tuple[str, int]] = Counter()
    classifications: Counter[str] = Counter()
    for path in paths:
        split = str(path.get("split", ""))
        source_id = int(path.get("source_episode_id", -1))
        path_id = str(path.get("path_id", ""))
        split_counts[split] += 1
        source_counts[(split, source_id)] += 1
        pairs = path.get("component_wall_pairs", ())
        if not isinstance(pairs, list):
            continue
        for pair in pairs:
            if not isinstance(pair, Mapping):
                continue
            component = str(pair.get("component", ""))
            wall = str(pair.get("wall_name", ""))
            clearance = float(pair.get("minimum_clearance_m", math.inf))
            contact_intervals = _intervals(
                pair.get("contact_or_overlap_intervals")
            )
            overlap_intervals = _intervals(pair.get("overlap_intervals"))
            classification = _geometry_classification(
                clearance=clearance,
                contact_intervals=contact_intervals,
                overlap_intervals=overlap_intervals,
                near_wall_threshold_m=diagnostic_near_wall_threshold_m,
            )
            classifications[classification] += 1
            key = (split, source_id, component, wall)
            aggregate = groups.setdefault(
                key,
                {
                    "split": split,
                    "source_episode_id": source_id,
                    "component": component,
                    "wall_name": wall,
                    "path_ids": [],
                    "path_count": 0,
                    "minimum_clearance_m": math.inf,
                    "classification_counts": Counter(),
                    "contact_or_overlap_intervals": [],
                    "overlap_intervals": [],
                    "bucket_local_contact_region_samples": [],
                },
            )
            aggregate["path_ids"].append(path_id)
            aggregate["path_count"] += 1
            aggregate["minimum_clearance_m"] = min(
                float(aggregate["minimum_clearance_m"]),
                clearance,
            )
            aggregate["classification_counts"][classification] += 1
            if contact_intervals:
                aggregate["contact_or_overlap_intervals"].append(
                    {"path_id": path_id, "intervals": contact_intervals}
                )
            if overlap_intervals:
                aggregate["overlap_intervals"].append(
                    {"path_id": path_id, "intervals": overlap_intervals}
                )
            samples = pair.get("bucket_local_contact_region_samples", ())
            if isinstance(samples, list):
                aggregate["bucket_local_contact_region_samples"].extend(
                    deepcopy(samples)
                )
    rows = []
    for key in sorted(groups):
        row = groups[key]
        row["path_ids"] = sorted(set(row["path_ids"]))
        row["classification_counts"] = _classification_counts(
            row["classification_counts"]
        )
        rows.append(row)
    return {
        "schema": "wall_contact_geometry_summary_v1",
        "diagnostic_near_wall_threshold_m": float(
            diagnostic_near_wall_threshold_m
        ),
        "threshold_role": "diagnostic_only_not_production_contract",
        "production_clearance_or_contact_budget_inferred": False,
        "path_count": len(paths),
        "split_path_counts": dict(sorted(split_counts.items())),
        "source_path_counts": [
            {
                "split": split,
                "source_episode_id": source_id,
                "path_count": count,
            }
            for (split, source_id), count in sorted(source_counts.items())
        ],
        "classification_counts": _classification_counts(classifications),
        "component_wall_statistics": rows,
    }


def summarize_expert_replay_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize train inference and holdout diagnostics with a hard split."""

    train = [record for record in records if record.get("split") == "train"]
    holdout = [
        record for record in records if record.get("split") == "validation"
    ]
    return {
        "schema": "wall_contact_expert_replay_summary_v1",
        "category_vocabulary": list(CONTACT_CATEGORIES),
        "train": _summarize_replay_split(
            train,
            split="train",
            selection_eligible=True,
        ),
        "holdout": _summarize_replay_split(
            holdout,
            split="validation",
            selection_eligible=False,
        ),
    }


def summarize_paired_ab_attempts(
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one compact A/B row per seed while retaining fairness details."""

    rows: list[dict[str, Any]] = []
    by_seed: dict[int, dict[str, Mapping[str, Any]]] = {}
    for attempt in attempts:
        seed = int(attempt.get("seed", -1))
        condition = str(attempt.get("condition", ""))
        by_seed.setdefault(seed, {})[condition] = attempt
    b_outcomes: Counter[str] = Counter()
    valid_count = 0
    for seed in sorted(by_seed):
        conditions = by_seed[seed]
        a = conditions.get("A", {})
        b = conditions.get("B", {})
        pair_valid = bool(a.get("pair_valid")) and bool(b.get("pair_valid"))
        valid_count += int(pair_valid)
        for field in (
            "entered_carry",
            "dump_completed",
            "contact_ended_before_carry",
            "hard_violation",
            "contact_driven_hard_failure",
        ):
            b_outcomes[field] += int(bool(b.get(field, False)))
        rows.append(
            {
                "seed": seed,
                "pair_id": str(
                    a.get("pair_id", b.get("pair_id", f"seed_{seed}"))
                ),
                "pair_valid": pair_valid,
                "reset_fairness": deepcopy(
                    a.get("reset_fairness", b.get("reset_fairness", {}))
                ),
                "A": _attempt_outcome(a),
                "B": _attempt_outcome(b),
            }
        )
    outcome_order = (
        "contact_driven_hard_failure",
        "contact_ended_before_carry",
        "dump_completed",
        "entered_carry",
        "hard_violation",
    )
    return {
        "schema": "wall_contact_paired_ab_summary_v1",
        "pair_count": len(rows),
        "valid_pair_count": valid_count,
        "invalid_pair_count": len(rows) - valid_count,
        "b_outcome_counts": {
            field: b_outcomes[field] for field in outcome_order
        },
        "pairs": rows,
    }


def build_causal_report_sections(
    *,
    geometry_collection: Mapping[str, Any],
    expert_replay_collection: Mapping[str, Any],
    paired_ab_collection: Mapping[str, Any],
    classification: str,
    blockers: Sequence[str],
) -> dict[str, Any]:
    """Embed evidence summaries, rationale, and the mandatory pause gates."""

    geometry = geometry_collection.get("summary")
    if not isinstance(geometry, Mapping):
        geometry = summarize_geometry_paths(
            _mapping_sequence(geometry_collection.get("paths"))
        )
    replay = expert_replay_collection.get("summary")
    if not isinstance(replay, Mapping):
        training = _mapping(
            expert_replay_collection.get("training_inference")
        )
        holdout = _mapping(expert_replay_collection.get("holdout_evidence"))
        replay = summarize_expert_replay_records(
            [
                *_mapping_sequence(training.get("summaries")),
                *_mapping_sequence(holdout.get("summaries")),
            ]
        )
    paired = paired_ab_collection.get("summary")
    if not isinstance(paired, Mapping):
        paired = summarize_paired_ab_attempts(
            _mapping_sequence(paired_ab_collection.get("attempts"))
        )
    rationale = classification_rationale(
        classification=classification,
        paired_ab_summary=paired,
        expert_lineage_complete=bool(
            paired_ab_collection.get("expert_lineage_complete", False)
        ),
        expert_same_region_sub_100kn=bool(
            paired_ab_collection.get(
                "expert_same_region_sub_100kn",
                False,
            )
        ),
        blockers=blockers,
    )
    return {
        "geometry_summary": geometry,
        "expert_replay_summary": replay,
        "paired_ab_summary": paired,
        "classification_rationale": rationale,
        "pause": {
            "required": True,
            "reason": "await_human_contact_budget_freeze",
            "required_human_decisions": [
                "bucket_contact_region",
                "force_budget",
                "duration_budget",
                "impulse_budget",
            ],
            "production_budget_inferred": False,
        },
        "future_gates": {
            "continuous_contact_contract_change_allowed": False,
            "qpos_predictor_implementation_allowed": False,
            "e0_g1_w1_offline_allowed": False,
            "bounded_live_allowed": False,
            "e0_g1_w1_live_allowed": False,
            "functional_1x10_allowed": False,
            "production_promotion_allowed": False,
        },
    }


def classification_rationale(
    *,
    classification: str,
    paired_ab_summary: Mapping[str, Any],
    expert_lineage_complete: bool,
    expert_same_region_sub_100kn: bool,
    blockers: Sequence[str],
) -> dict[str, Any]:
    """Explain the frozen causal rule using only validated aggregate counts."""

    outcomes = _mapping(paired_ab_summary.get("b_outcome_counts"))
    pair_count = int(paired_ab_summary.get("pair_count", 0))
    valid_pairs = int(paired_ab_summary.get("valid_pair_count", 0))
    observed = {
        "pair_count": pair_count,
        "valid_pair_count": valid_pairs,
        "b_entered_carry_count": int(outcomes.get("entered_carry", 0)),
        "b_dump_completed_count": int(outcomes.get("dump_completed", 0)),
        "b_contact_ended_before_carry_count": int(
            outcomes.get("contact_ended_before_carry", 0)
        ),
        "b_hard_violation_count": int(outcomes.get("hard_violation", 0)),
        "b_contact_driven_hard_failure_count": int(
            outcomes.get("contact_driven_hard_failure", 0)
        ),
        "expert_lineage_complete": bool(expert_lineage_complete),
        "expert_same_region_sub_100kn": bool(
            expert_same_region_sub_100kn
        ),
    }
    evidence_complete = not blockers and pair_count == 3 and valid_pairs == 3
    rules = {
        "safety_too_strict": (
            evidence_complete
            and observed["b_entered_carry_count"] == 3
            and observed["b_dump_completed_count"] == 3
            and observed["b_contact_ended_before_carry_count"] == 3
            and observed["b_hard_violation_count"] == 0
        ),
        "act_or_goal_geometry": (
            evidence_complete
            and observed["b_dump_completed_count"] == 0
            and observed["b_contact_driven_hard_failure_count"] >= 2
        ),
        "low_margin_dataset_style": (
            evidence_complete
            and observed["b_dump_completed_count"] in {1, 2}
            and expert_lineage_complete
            and expert_same_region_sub_100kn
        ),
    }
    rule_text = {
        "safety_too_strict": (
            "3/3 valid B attempts entered carry and completed dump after "
            "contact ended, with no hard-stop violation."
        ),
        "act_or_goal_geometry": (
            "0/3 valid B attempts completed dump and at least 2/3 ended in "
            "a contact-driven hard failure."
        ),
        "low_margin_dataset_style": (
            "Only 1-2/3 valid B attempts completed dump and valid train "
            "evidence matched the same sub-100kN bucket region."
        ),
        "inconclusive": (
            "No positive causal rule was fully satisfied, or required "
            "evidence/fairness was incomplete."
        ),
    }
    return {
        "classification": classification,
        "rule": rule_text.get(classification, rule_text["inconclusive"]),
        "rule_satisfied": bool(rules.get(classification, False)),
        "observed": observed,
        "evidence_blockers": list(blockers),
        "production_budget_inference_allowed": False,
    }


def render_causal_report_markdown(report: Mapping[str, Any]) -> str:
    """Render the JSON report's decision-critical facts for human review."""

    rationale = _mapping(report.get("classification_rationale"))
    observed = _mapping(rationale.get("observed"))
    future = _mapping(report.get("future_gates"))
    return "\n".join(
        (
            "# Strict-18 Wall Contact Semantics Diagnostic",
            "",
            f"- Status: `{report.get('status', 'blocked')}`",
            "- Evidence kind: diagnostic Unity geometry/replay and paired live A/B",
            f"- Causal classification: `{report.get('causal_classification', 'inconclusive')}`",
            f"- Rationale: {rationale.get('rule', '')}",
            "- B outcomes: "
            f"{observed.get('b_dump_completed_count', 0)}/3 dump, "
            f"{observed.get('b_entered_carry_count', 0)}/3 carry, "
            f"{observed.get('b_contact_ended_before_carry_count', 0)}/3 "
            "contact-ended-before-carry.",
            "- Holdout evidence selects regions/budgets: `false`",
            "- production budget inferred: `false`",
            "- Production promotion: `false`",
            "- Training HDF5 writes: none",
            "- qpos predictor gate: "
            f"`{str(bool(future.get('qpos_predictor_implementation_allowed'))).lower()}`",
            "- E0/G1/W1 offline gate: "
            f"`{str(bool(future.get('e0_g1_w1_offline_allowed'))).lower()}`",
            "- Bounded live gate: "
            f"`{str(bool(future.get('bounded_live_allowed'))).lower()}`",
            "- Functional 1x10 gate: "
            f"`{str(bool(future.get('functional_1x10_allowed'))).lower()}`",
            "- Next gate: human review must freeze the bucket contact region "
            "and force/duration/impulse budget.",
            "",
        )
    )


def _summarize_replay_split(
    records: Sequence[Mapping[str, Any]],
    *,
    split: str,
    selection_eligible: bool,
) -> dict[str, Any]:
    source_statuses: Counter[str] = Counter()
    window_statuses: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    diagnostic_pairs: list[Mapping[str, Any]] = []
    inference_pairs: list[Mapping[str, Any]] = []
    valid_for_inference = 0
    window_count = 0
    for source in records:
        source_statuses[str(source.get("status", ""))] += 1
        windows = source.get("windows", ())
        if not isinstance(windows, list):
            continue
        for window in windows:
            if not isinstance(window, Mapping):
                continue
            window_count += 1
            status = str(window.get("status", ""))
            window_statuses[status] += 1
            diagnostic = _mapping(
                window.get("all_diagnostic_contact_summary")
            )
            diagnostic_pairs.extend(
                _mapping_sequence(
                    diagnostic.get("component_wall_summaries")
                )
            )
            raw_categories = diagnostic.get("categories", ())
            if isinstance(raw_categories, list):
                for category in CONTACT_CATEGORIES:
                    categories[category] += int(category in raw_categories)
            eligible = bool(window.get("valid_for_inference", False))
            valid_for_inference += int(eligible)
            if split == "train" and eligible:
                production = _mapping(
                    window.get("production_inference_contact_summary")
                )
                inference_pairs.extend(
                    _mapping_sequence(
                        production.get("component_wall_summaries")
                    )
                )
    result = {
        "split": split,
        "source_count": len(records),
        "source_status_counts": _status_counts(source_statuses),
        "window_count": window_count,
        "window_status_counts": _status_counts(window_statuses),
        "valid_for_inference_window_count": valid_for_inference,
        "diagnostic_window_category_counts": {
            category: categories[category]
            for category in CONTACT_CATEGORIES
        },
        "diagnostic_component_wall_statistics": (
            _aggregate_component_wall(diagnostic_pairs)
        ),
        "diagnostic_statistics_basis": (
            "all_authorized_validated_window_summaries"
        ),
        "selection_eligible": selection_eligible,
        "used_for_region_or_budget_selection": False,
    }
    if split == "train":
        result["inference_component_wall_statistics"] = (
            _aggregate_component_wall(inference_pairs)
        )
        result["inference_statistics_basis"] = (
            "fairness_valid_train_windows_only"
        )
    else:
        result["inference_component_wall_statistics"] = []
        result["inference_statistics_basis"] = (
            "holdout_forbidden_from_region_or_budget_selection"
        )
    return result


def _aggregate_component_wall(
    pairs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for pair in pairs:
        key = (str(pair.get("component", "")), str(pair.get("wall_name", "")))
        groups.setdefault(key, []).append(pair)
    result = []
    for key in sorted(groups):
        items = groups[key]
        row: dict[str, Any] = {
            "component": key[0],
            "wall_name": key[1],
        }
        for metric in _PEAK_METRICS:
            row[metric] = max(_number(item.get(metric)) for item in items)
        for metric in _RMS_METRICS:
            row[metric] = _rms(
                [_number(item.get(metric)) for item in items]
            )
        for metric in _SUM_METRICS:
            values = [_number(item.get(metric)) for item in items]
            row[metric] = (
                int(sum(values))
                if metric
                in {"session_count", "callback_count", "contact_point_count"}
                else sum(values)
            )
        for metric in _MAX_METRICS:
            row[metric] = max(_number(item.get(metric)) for item in items)
        row["bucket_local_contact_region_samples"] = [
            deepcopy(sample)
            for item in items
            for sample in (
                item.get("bucket_local_contact_region_samples", ())
                if isinstance(
                    item.get("bucket_local_contact_region_samples", ()),
                    list,
                )
                else ()
            )
        ]
        result.append(row)
    return result


def _attempt_outcome(attempt: Mapping[str, Any]) -> dict[str, Any]:
    reasons = attempt.get("hard_stop_violations", ())
    return {
        "entered_carry": bool(attempt.get("entered_carry", False)),
        "dump_completed": bool(attempt.get("dump_completed", False)),
        "contact_ended_before_carry": bool(
            attempt.get("contact_ended_before_carry", False)
        ),
        "hard_violation": bool(attempt.get("hard_violation", False)),
        "hard_reason": list(reasons) if isinstance(reasons, list) else [],
        "contact_driven_hard_failure": bool(
            attempt.get("contact_driven_hard_failure", False)
        ),
        "terminal_reason": str(attempt.get("terminal_reason", "")),
    }


def _geometry_classification(
    *,
    clearance: float,
    contact_intervals: Sequence[Sequence[int]],
    overlap_intervals: Sequence[Sequence[int]],
    near_wall_threshold_m: float,
) -> str:
    if contact_intervals or overlap_intervals or clearance <= 0.0:
        return "contact_or_overlap"
    if clearance <= near_wall_threshold_m:
        return "near_wall"
    return "clear"


def _classification_counts(values: Mapping[str, int]) -> dict[str, int]:
    return {
        name: int(values.get(name, 0))
        for name in ("clear", "contact_or_overlap", "near_wall")
    }


def _status_counts(values: Mapping[str, int]) -> dict[str, int]:
    return {name: int(values.get(name, 0)) for name in _STATUS_VALUES}


def _intervals(value: Any) -> list[list[int]]:
    if not isinstance(value, list):
        return []
    return [
        [int(interval[0]), int(interval[1])]
        for interval in value
        if isinstance(interval, list) and len(interval) == 2
    ]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _number(value: Any) -> float:
    result = float(value or 0.0)
    return result if math.isfinite(result) else 0.0


def _rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


__all__ = [
    "CONTACT_CATEGORIES",
    "DIAGNOSTIC_NEAR_WALL_THRESHOLD_M",
    "build_causal_report_sections",
    "classification_rationale",
    "render_causal_report_markdown",
    "summarize_expert_replay_records",
    "summarize_geometry_paths",
    "summarize_paired_ab_attempts",
]
