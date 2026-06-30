"""Offline rollout-review evidence gate for primitive planner eval outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rollout_review_v1"
MAX_REVIEW_CYCLES = 30


def build_rollout_review(results_dir: str | Path) -> dict[str, Any]:
    """Build a diagnostic rollout-review report from an eval results directory."""

    source_results_dir = Path(results_dir)
    manifest_path = source_results_dir / "rollout_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    manifest_rollouts = list(manifest.get("rollouts", []) or [])
    if not manifest_rollouts:
        manifest_rollouts = _discover_rollout_summaries(source_results_dir)

    rollout_reviews: list[dict[str, Any]] = []
    evidence_gaps: list[str] = []
    root_cause_hints: list[str] = []

    for index, manifest_rollout in enumerate(manifest_rollouts):
        rollout_id = int(manifest_rollout.get("rollout_id", index))
        summary, summary_path = _load_rollout_summary(
            source_results_dir=source_results_dir,
            rollout_id=rollout_id,
            manifest_rollout=manifest_rollout,
        )
        trace, trace_path = _load_planner_trace(
            source_results_dir=source_results_dir,
            rollout_id=rollout_id,
            summary=summary,
        )
        review = _review_single_rollout(
            rollout_id=rollout_id,
            summary=summary,
            summary_path=summary_path,
            planner_trace=trace,
            planner_trace_path=trace_path,
        )
        rollout_reviews.append(review)
        evidence_gaps.extend(review["evidence_gaps"])
        root_cause_hints.extend(review["root_cause_hints"])

    overall_status = _overall_status(rollout_reviews)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_results_dir": str(source_results_dir),
        "overall_status": overall_status,
        "evidence_gaps": _unique_strings(evidence_gaps),
        "rollout_reviews": rollout_reviews,
        "root_cause_hints": _unique_strings(root_cause_hints),
        "llm_candidate_ranking_ready": bool(
            overall_status == "llm_candidate_ranking_candidate"
        ),
    }


def write_rollout_review(
    results_dir: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Write rollout review JSON and return the output path."""

    review = build_rollout_review(results_dir)
    output_path = Path(output) if output is not None else Path(results_dir) / "rollout_review.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_jsonable(review), indent=2, sort_keys=True) + "\n")
    return output_path


def _review_single_rollout(
    *,
    rollout_id: int,
    summary: dict[str, Any],
    summary_path: Path,
    planner_trace: dict[str, Any],
    planner_trace_path: Path,
) -> dict[str, Any]:
    evidence_gaps: list[str] = []
    root_cause_hints: list[str] = []
    if not summary:
        evidence_gaps.append(f"rollout_{rollout_id}:summary_missing")

    quality = _quality_review(summary)
    if bool(summary.get("success", False)) and quality["flags"]:
        root_cause_hints.append("success_does_not_prove_quality")
    if quality["flags"]:
        root_cause_hints.append("inspect_policy_handoff_or_live_scaling")

    handoff = _handoff_review(summary)
    if handoff["status"] == "missing":
        evidence_gaps.append(f"rollout_{rollout_id}:return_to_dig_handoff_fields_missing")

    coverage = _coverage_review(summary, planner_trace)
    if coverage["status"] == "missing":
        evidence_gaps.append(f"rollout_{rollout_id}:coverage_decision_trace_missing")
    if coverage["candidate_ranking_issue"]:
        root_cause_hints.append("coverage_candidate_ranking_review")

    status = _rollout_status(
        evidence_gaps=evidence_gaps,
        quality_flags=quality["flags"],
        coverage_candidate_ranking_issue=bool(coverage["candidate_ranking_issue"]),
    )
    return {
        "rollout_id": int(rollout_id),
        "status": status,
        "success": bool(summary.get("success", False)),
        "target_cycle_gate_success": bool(
            summary.get("target_cycle_gate_success", False)
        ),
        "rollout_stop_reason": str(summary.get("rollout_stop_reason", "")),
        "summary_path": str(summary_path),
        "planner_trace_path": str(planner_trace_path),
        "quality": quality,
        "handoff": handoff,
        "coverage": coverage,
        "planned_actual_cycles": _planned_actual_cycles(summary),
        "evidence_gaps": evidence_gaps,
        "root_cause_hints": _unique_strings(root_cause_hints),
    }


def _quality_review(summary: dict[str, Any]) -> dict[str, Any]:
    flags: list[str] = []
    for key in (
        "quality_issue_count",
        "low_cycle_deposited_fraction_count",
        "high_cycle_post_dump_drop_count",
        "shallow_peak_bucket_depth_count",
        "dig_area_escape_cycle_count",
    ):
        if _float_value(summary.get(key), default=0.0) > 0.0:
            flags.append(key)
    return {
        "status": "issue" if flags else "clean",
        "flags": flags,
        "quality_issue_count": int(_float_value(summary.get("quality_issue_count"), 0.0)),
        "low_cycle_deposited_fraction_count": int(
            _float_value(summary.get("low_cycle_deposited_fraction_count"), 0.0)
        ),
        "cycle_deposited_fraction_min": _optional_float(
            summary.get("cycle_deposited_fraction_min")
        ),
        "dig_depth_abs_error_max_m": _optional_float(
            summary.get("dig_depth_abs_error_max_m")
        ),
    }


def _handoff_review(summary: dict[str, Any]) -> dict[str, Any]:
    required = (
        "return_to_dig_entry_close",
        "return_to_dig_entry_error_m",
        "return_to_dig_max_entry_error_m",
    )
    if any(key not in summary for key in required):
        return {
            "status": "missing",
            "return_to_dig_entry_close": None,
            "return_to_dig_entry_error_m": None,
            "return_to_dig_max_entry_error_m": None,
        }
    entry_error = _optional_float(summary.get("return_to_dig_entry_error_m"))
    max_error = _optional_float(summary.get("return_to_dig_max_entry_error_m"))
    entry_close = bool(int(_float_value(summary.get("return_to_dig_entry_close"), 0.0)))
    status = "ready" if entry_close else "not_ready"
    if entry_error is not None and max_error is not None and entry_error > max_error:
        status = "not_ready"
    return {
        "status": status,
        "return_to_dig_entry_close": entry_close,
        "return_to_dig_entry_error_m": entry_error,
        "return_to_dig_max_entry_error_m": max_error,
    }


def _coverage_review(
    summary: dict[str, Any],
    planner_trace: dict[str, Any],
) -> dict[str, Any]:
    decision_trace = list(planner_trace.get("coverage_decision_trace", []) or [])
    events = [str(item.get("event", "")) for item in decision_trace if isinstance(item, dict)]
    terminal_stop_reason = str(
        planner_trace.get(
            "coverage_terminal_stop_reason",
            summary.get("coverage_terminal_stop_reason", ""),
        )
    )
    depleted_count = int(_float_value(summary.get("coverage_depleted_count"), 0.0))
    candidate_issue = bool(
        decision_trace
        and (
            depleted_count > 0
            or "reject_corridor" in events
            or "terminal_stop" in events
            or bool(terminal_stop_reason)
        )
    )
    return {
        "status": "present" if decision_trace else "missing",
        "decision_trace_count": int(len(decision_trace)),
        "events": events,
        "terminal_stop_requested": bool(
            planner_trace.get(
                "coverage_terminal_stop_requested",
                summary.get("coverage_terminal_stop_requested", False),
            )
        ),
        "terminal_stop_reason": terminal_stop_reason,
        "depleted_count": depleted_count,
        "candidate_ranking_issue": candidate_issue,
    }


def _planned_actual_cycles(summary: dict[str, Any]) -> list[dict[str, Any]]:
    cycles: list[dict[str, Any]] = []
    for cycle_index in range(1, MAX_REVIEW_CYCLES + 1):
        prefix = f"cycle{cycle_index}"
        keys = {
            "entry_planned_x_m": f"{prefix}_entry_planned_x_m",
            "entry_actual_x_m": f"{prefix}_entry_actual_x_m",
            "exit_planned_x_m": f"{prefix}_exit_planned_x_m",
            "exit_actual_x_m": f"{prefix}_exit_actual_x_m",
            "depth_target_m": f"{prefix}_depth_target_m",
            "depth_peak_m": f"{prefix}_depth_peak_m",
            "deposited_fraction": f"{prefix}_deposited_fraction",
        }
        if not any(key in summary for key in keys.values()):
            continue
        cycles.append(
            {
                "cycle_index": cycle_index,
                **{
                    name: _optional_float(summary.get(source_key))
                    for name, source_key in keys.items()
                    if source_key in summary
                },
            }
        )
    return cycles


def _rollout_status(
    *,
    evidence_gaps: list[str],
    quality_flags: list[str],
    coverage_candidate_ranking_issue: bool,
) -> str:
    if any(gap.endswith("summary_missing") for gap in evidence_gaps):
        return "insufficient_evidence"
    if any("return_to_dig_handoff_fields_missing" in gap for gap in evidence_gaps):
        return "insufficient_evidence"
    if coverage_candidate_ranking_issue and not quality_flags:
        return "llm_candidate_ranking_candidate"
    if quality_flags:
        return "needs_root_cause_audit"
    return "reviewed"


def _overall_status(rollout_reviews: list[dict[str, Any]]) -> str:
    statuses = {str(review["status"]) for review in rollout_reviews}
    if "insufficient_evidence" in statuses:
        return "insufficient_evidence"
    if "needs_root_cause_audit" in statuses:
        return "needs_root_cause_audit"
    if "llm_candidate_ranking_candidate" in statuses:
        return "llm_candidate_ranking_candidate"
    return "reviewed"


def _load_rollout_summary(
    *,
    source_results_dir: Path,
    rollout_id: int,
    manifest_rollout: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    path_value = manifest_rollout.get("summary_path")
    summary_path = (
        _resolve_path(path_value, source_results_dir)
        if path_value
        else source_results_dir / "rollouts" / f"rollout_{rollout_id:03d}_summary.json"
    )
    if summary_path.exists():
        return _read_json(summary_path), summary_path
    return dict(manifest_rollout), summary_path


def _load_planner_trace(
    *,
    source_results_dir: Path,
    rollout_id: int,
    summary: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    path_value = summary.get("planner_trace_path")
    trace_path = (
        _resolve_path(path_value, source_results_dir)
        if path_value
        else source_results_dir / "rollouts" / f"rollout_{rollout_id:03d}_planner_trace.json"
    )
    if trace_path.exists():
        return _read_json(trace_path), trace_path
    return {}, trace_path


def _discover_rollout_summaries(source_results_dir: Path) -> list[dict[str, Any]]:
    rollouts_dir = source_results_dir / "rollouts"
    discovered: list[dict[str, Any]] = []
    for index, summary_path in enumerate(sorted(rollouts_dir.glob("rollout_*_summary.json"))):
        discovered.append({"rollout_id": index, "summary_path": str(summary_path)})
    return discovered


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _resolve_path(value: object, base_dir: Path) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    base_relative_path = base_dir / path
    if base_relative_path.exists():
        return base_relative_path
    if path.exists():
        return path
    return base_relative_path


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _float_value(value: object, default: float = 0.0) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "SCHEMA_VERSION",
    "build_rollout_review",
    "write_rollout_review",
]
