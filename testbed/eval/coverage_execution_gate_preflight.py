"""Full-gate offline preflight for calibrated exact-tuple coverage planning.

This module replays the production candidate selector on one frozen cycle-zero
state, three frozen post-return selection states, and one hard-bottom replan
state.  It is deliberately offline-only: a failed case blocks bounded live and
never relaxes a planner or safety threshold.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.eval.coverage_replan_replay import (
    _production_static_config,
    _read_hdf5_observation,
    _read_jsonl_step,
    _run_production_selection,
    _source_record,
)

COVERAGE_EXECUTION_PRODUCTION_PREFLIGHT_SCHEMA = (
    "coverage_execution_production_preflight_v2"
)
OUTPUT_FILENAME = (
    f"{COVERAGE_EXECUTION_PRODUCTION_PREFLIGHT_SCHEMA}.json"
)
REQUIRED_PRODUCTION_CASE_IDS = (
    "cycle0_reset_state",
    "post_return_reset_0",
    "post_return_reset_1",
    "post_return_reset_2",
    "hard_bottom_replan_step_2987",
)
_EXPECTED_ALIGNMENT_SCHEMA = "tuple_start_alignment_diagnosis_v1"
_EXPECTED_EXECUTION_LIBRARY_SIZE = 374


def build_coverage_execution_gate_preflight(
    *,
    resolved_config_path: str | Path,
    functional_results_dir: str | Path,
    bounded_results_dir: str | Path,
    tuple_start_alignment_artifact_path: str | Path,
    output_dir: str | Path,
    initial_dig_step_id: int = 137,
    pre_contact_step_id: int = 2935,
    replan_step_id: int = 2987,
    depth_exhausted_physical_cell_id: int = 5,
) -> dict[str, Any]:
    """Replay all required frozen states through the production selector."""

    config_path = _require_file(resolved_config_path)
    functional_dir = _require_dir(functional_results_dir)
    bounded_dir = _require_dir(bounded_results_dir)
    alignment_path = _require_file(
        tuple_start_alignment_artifact_path
    )
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite preflight directory: {destination}"
        )

    resolved = _yaml_mapping(config_path)
    static_config = _production_static_config(resolved)
    contract = _validated_preflight_contract(
        resolved=resolved,
        static_config=static_config,
    )
    alignment = _json_mapping(alignment_path)

    functional_hdf5 = _require_file(
        functional_dir / "hdf5_rollouts" / "episode_0.hdf5"
    )
    functional_jsonl = _require_file(
        functional_dir / "rollouts" / "rollout_000.jsonl"
    )
    bounded_sources = _validated_bounded_alignment_sources(
        alignment=alignment,
        bounded_results_dir=bounded_dir,
    )

    cases: list[dict[str, Any]] = []
    cases.append(
        _run_case(
            case_id="cycle0_reset_state",
            selection_phase="cycle0",
            state_contract="fresh_cycle0_synthetic_empty_coverage_state",
            observation_step_id=int(initial_dig_step_id),
            observation_source=_source_record(functional_hdf5),
            planner_state_source={
                "kind": "contract_reconstruction",
                "completed_dump_count": 0,
                "attempts_by_outcome_cell": [0] * 6,
                "depleted_by_outcome_cell": [0] * 6,
            },
            static_config=static_config,
            planner_state=_initial_planner_state(),
            observation=_read_hdf5_observation(
                functional_hdf5,
                int(initial_dig_step_id),
            ),
            depth_exhausted_physical_cell_id=None,
        )
    )
    for rollout_id, source in enumerate(bounded_sources):
        return_start_step = int(source["return_start_step_id"])
        cases.append(
            _run_case(
                case_id=f"post_return_reset_{rollout_id}",
                selection_phase="post_return_planned_handoff",
                state_contract=(
                    "recorded_return_start_observation_with_cycle1_"
                    "coverage_state_reconstruction"
                ),
                observation_step_id=return_start_step,
                observation_source=dict(source["hdf5_source"]),
                planner_state_source={
                    "kind": "contract_reconstruction",
                    "completed_dump_count": 1,
                    "attempts_by_outcome_cell": [0, 0, 0, 1, 0, 0],
                    "depleted_by_outcome_cell": [0] * 6,
                    "return_start_jsonl": dict(source["jsonl_source"]),
                    "alignment_artifact": str(alignment_path),
                },
                static_config=static_config,
                planner_state=_post_return_planner_state(),
                observation=_read_hdf5_observation(
                    Path(str(source["hdf5_source"]["path"])),
                    return_start_step,
                ),
                depth_exhausted_physical_cell_id=None,
            )
        )
    cases.append(
        _run_case(
            case_id="hard_bottom_replan_step_2987",
            selection_phase="post_return_after_hard_bottom_neutral_ack",
            state_contract="recorded_step_2935_state_plus_actual_cell5_exhausted",
            observation_step_id=int(replan_step_id),
            observation_source=_source_record(functional_hdf5),
            planner_state_source={
                "kind": "recorded_jsonl_step",
                "jsonl": _source_record(functional_jsonl),
                "step_id": int(pre_contact_step_id),
                "depth_exhausted_physical_cell_id": int(
                    depth_exhausted_physical_cell_id
                ),
            },
            static_config=static_config,
            planner_state=_read_jsonl_step(
                functional_jsonl,
                int(pre_contact_step_id),
            ),
            observation=_read_hdf5_observation(
                functional_hdf5,
                int(replan_step_id),
            ),
            depth_exhausted_physical_cell_id=int(
                depth_exhausted_physical_cell_id
            ),
        )
    )

    hard_clearance_m = float(
        static_config.execution_library.worktool_sweep_3d.hard_clearance_m
    )
    gate_decision = build_gate_decision(
        cases,
        configured_hard_clearance_m=hard_clearance_m,
    )
    artifact = {
        "schema": COVERAGE_EXECUTION_PRODUCTION_PREFLIGHT_SCHEMA,
        "status": (
            "passed"
            if bool(gate_decision["bounded_live_allowed"])
            else "failed"
        ),
        "evidence_kind": "offline_production_service_replay",
        "teacher_forced_recorded_observation": True,
        "closed_loop_claim": False,
        "source_lock": {
            "resolved_config": _source_record(config_path),
            "implementation": _implementation_source_lock(),
            "functional_rollout_hdf5": _source_record(functional_hdf5),
            "functional_rollout_jsonl": _source_record(functional_jsonl),
            "tuple_start_alignment_artifact": _source_record(alignment_path),
            "bounded_rollouts": [
                {
                    "rollout_id": int(index),
                    "hdf5": dict(source["hdf5_source"]),
                    "jsonl": dict(source["jsonl_source"]),
                }
                for index, source in enumerate(bounded_sources)
            ],
        },
        "contract": contract,
        "required_case_ids": list(REQUIRED_PRODUCTION_CASE_IDS),
        "cases": cases,
        "gate_decision": gate_decision,
        "execution_guard": {
            "bounded_live_started": False,
            "diagnostic_1x3_started": False,
            "functional_1x10_started": False,
            "thresholds_relaxed": False,
            "fallback_used": False,
            "next_action": (
                "bounded_transfer_3reset"
                if bool(gate_decision["bounded_live_allowed"])
                else "stop_before_live_and_diagnose_empty_full_gate_intersection"
            ),
        },
    }
    write_preflight_artifact(
        artifact=artifact,
        output_dir=destination,
    )
    return artifact


def build_gate_decision(
    cases: Sequence[Mapping[str, Any]],
    *,
    configured_hard_clearance_m: float,
) -> dict[str, Any]:
    """Apply the all-required-states gate using the configured 3D threshold."""

    threshold = float(configured_hard_clearance_m)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("configured hard clearance must be finite and non-negative")
    by_id = {
        str(case.get("case_id", "")): case
        for case in cases
    }
    if len(by_id) != len(cases):
        raise ValueError("preflight case IDs must be non-empty and unique")
    missing = [
        case_id
        for case_id in REQUIRED_PRODUCTION_CASE_IDS
        if case_id not in by_id
    ]
    extra = sorted(set(by_id).difference(REQUIRED_PRODUCTION_CASE_IDS))
    if missing or extra:
        raise ValueError(
            f"preflight case set mismatch:missing={missing}:extra={extra}"
        )

    failed: list[str] = []
    legal_counts: dict[str, int] = {}
    for case_id in REQUIRED_PRODUCTION_CASE_IDS:
        case = by_id[case_id]
        selection = dict(case.get("selection", {}) or {})
        selected = dict(
            selection.get("selected_candidate", {}) or {}
        )
        clearance = _finite_or_none(
            selected.get(
                "worktool_sweep_3d_effective_clearance_m"
            )
        )
        legal = bool(
            selection.get("status") == "selected"
            and clearance is not None
            and clearance + 1.0e-12 >= threshold
        )
        legal_counts[case_id] = int(legal)
        if not legal:
            failed.append(case_id)
    passed = not failed
    return {
        "configured_hard_clearance_m": threshold,
        "threshold_source": (
            "resolved_config.policy.dig_cut_planner.coverage."
            "actual_tuple_execution_library.worktool_sweep_3d."
            "hard_clearance_m"
        ),
        "required_case_count": len(REQUIRED_PRODUCTION_CASE_IDS),
        "passed_case_count": len(REQUIRED_PRODUCTION_CASE_IDS) - len(failed),
        "failed_case_ids": failed,
        "full_gate_legal_candidate_count_by_case": legal_counts,
        "total_selected_legal_candidates_across_cases": sum(
            legal_counts.values()
        ),
        "all_required_states_have_legal_candidate": passed,
        "bounded_live_allowed": passed,
        "blocker": (
            ""
            if passed
            else "production_full_gate_has_no_legal_candidate"
        ),
    }


def summarize_candidate_trace(
    candidate_trace: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize a full per-tuple trace without discarding the raw evidence."""

    trace = [dict(item) for item in candidate_trace]
    reason_counts = Counter(
        str(item.get("rejection_reason", ""))
        for item in trace
        if str(item.get("rejection_reason", ""))
    )
    gate_counts = Counter(
        _gate_for_rejection(str(item.get("rejection_reason", "")))
        for item in trace
        if str(item.get("rejection_reason", ""))
    )
    status_counts = Counter(str(item.get("status", "")) for item in trace)
    evaluated = [
        (
            float(item["worktool_sweep_3d_effective_clearance_m"]),
            str(item.get("exemplar_id", "")),
        )
        for item in trace
        if _finite_or_none(
            item.get("worktool_sweep_3d_effective_clearance_m")
        )
        is not None
    ]
    best = max(evaluated, default=None)
    return {
        "candidate_count": len(trace),
        "status_count": dict(sorted(status_counts.items())),
        "rejection_count_by_reason": dict(sorted(reason_counts.items())),
        "rejection_count_by_gate": dict(sorted(gate_counts.items())),
        "selected_legal_candidate_count": int(
            status_counts.get("selected", 0)
        ),
        "wall_safety_2d_eligible_count": sum(
            int(bool(item.get("wall_safety_eligible", 0)))
            for item in trace
        ),
        "tuple_start_reachability_eligible_count": sum(
            int(bool(item.get("tuple_start_reachability_eligible", 0)))
            for item in trace
        ),
        "worktool_sweep_3d_evaluated_count": len(evaluated),
        "worktool_sweep_3d_eligible_count": sum(
            int(bool(item.get("worktool_sweep_3d_eligible", 0)))
            for item in trace
        ),
        "maximum_worktool_sweep_3d_effective_clearance_m": (
            None if best is None else float(best[0])
        ),
        "maximum_worktool_sweep_3d_effective_clearance_exemplar_id": (
            "" if best is None else str(best[1])
        ),
    }


def write_preflight_artifact(
    *,
    artifact: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    """Write one preflight artifact under a new directory."""

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite preflight directory: {destination}"
        )
    destination.mkdir(parents=True, exist_ok=False)
    output_path = destination / OUTPUT_FILENAME
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(
            dict(artifact),
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    return output_path


def _run_case(
    *,
    case_id: str,
    selection_phase: str,
    state_contract: str,
    observation_step_id: int,
    observation_source: Mapping[str, Any],
    planner_state_source: Mapping[str, Any],
    static_config: Any,
    planner_state: dict[str, Any],
    observation: dict[str, Any],
    depth_exhausted_physical_cell_id: int | None,
) -> dict[str, Any]:
    selection = _run_production_selection(
        static_config=static_config,
        pre_contact_row=planner_state,
        observation=observation,
        depth_exhausted_physical_cell_id=(
            depth_exhausted_physical_cell_id
        ),
    )
    full_trace = list(selection.get("full_candidate_scores", ()) or ())
    if len(full_trace) != _EXPECTED_EXECUTION_LIBRARY_SIZE:
        raise ValueError(
            f"{case_id} production trace must contain "
            f"{_EXPECTED_EXECUTION_LIBRARY_SIZE} tuples; "
            f"found {len(full_trace)}"
        )
    return {
        "case_id": str(case_id),
        "selection_phase": str(selection_phase),
        "state_contract": str(state_contract),
        "observation_step_id": int(observation_step_id),
        "observation_source": dict(observation_source),
        "planner_state_source": dict(planner_state_source),
        "depth_exhausted_physical_cell_id": (
            None
            if depth_exhausted_physical_cell_id is None
            else int(depth_exhausted_physical_cell_id)
        ),
        "selection": selection,
        "candidate_summary": summarize_candidate_trace(full_trace),
        "full_candidate_trace": full_trace,
    }


def _validated_preflight_contract(
    *,
    resolved: Mapping[str, Any],
    static_config: Any,
) -> dict[str, Any]:
    execution = static_config.execution_library
    if (
        not execution.enabled
        or not execution.start_reachability.enabled
        or not execution.worktool_sweep_3d.enabled
    ):
        raise ValueError(
            "production preflight requires exact tuple, start reachability, "
            "and 3D worktool sweep"
        )
    wall = static_config.wall_safety
    if not wall.enabled:
        raise ValueError("production preflight requires 2D wall safety")
    metadata = dict(
        dict(resolved.get("eval", {}) or {}).get(
            "record_hdf5_metadata",
            {},
        )
        or {}
    )
    return {
        "candidate_library_size": _EXPECTED_EXECUTION_LIBRARY_SIZE,
        "selection_order": [
            "outcome_and_blocked_corridor",
            "wall_safety_2d",
            "tuple_start_reachability",
            "planned_handoff_worktool_sweep_3d",
            "exhausted_physical_cells",
            "hard_bottom_budget",
            "removed_depth_support",
            "exact_k1_and_a0_cross_cell_score",
        ],
        "worktool_sweep_3d": execution.worktool_sweep_3d.as_dict(),
        "wall_safety_2d": wall.as_dict(),
        "start_reachability": execution.start_reachability.as_dict(),
        "execution_library": {
            "path": str(execution.path),
            "artifact_sha256": str(execution.artifact_sha256),
            "mode": str(execution.mode),
        },
        "tracking_calibration": {
            "profile": str(
                metadata.get(
                    "worktool_tracking_calibration_profile",
                    "",
                )
            ),
            "schema": str(
                metadata.get(
                    "worktool_tracking_calibration_schema",
                    "",
                )
            ),
            "sha256": str(
                metadata.get(
                    "worktool_tracking_calibration_sha256",
                    "",
                )
            ),
        },
        "a0_temporal_window": int(
            dict(
                dict(resolved.get("policy", {}) or {}).get(
                    "act_params",
                    {},
                )
                or {}
            ).get("temporal_agg_window", -1)
        ),
        "thresholds_relaxed": False,
    }


def _validated_bounded_alignment_sources(
    *,
    alignment: Mapping[str, Any],
    bounded_results_dir: Path,
) -> list[dict[str, Any]]:
    if alignment.get("schema") != _EXPECTED_ALIGNMENT_SCHEMA:
        raise ValueError("tuple-start alignment schema mismatch")
    raw_rollouts = alignment.get("rollouts")
    if not isinstance(raw_rollouts, list) or len(raw_rollouts) != 3:
        raise ValueError("tuple-start alignment must contain three rollouts")
    sources: list[dict[str, Any]] = []
    for rollout_id, raw in enumerate(raw_rollouts):
        if not isinstance(raw, dict) or int(raw.get("rollout_id", -1)) != rollout_id:
            raise ValueError("tuple-start alignment rollout order mismatch")
        contract = dict(raw.get("alignment_contract", {}) or {})
        if not bool(contract.get("hdf5_rows_are_post_action", False)):
            raise ValueError("tuple-start alignment row convention mismatch")
        hdf5_path = _require_file(
            bounded_results_dir
            / "hdf5_rollouts"
            / f"episode_{rollout_id}.hdf5"
        )
        jsonl_path = _require_file(
            bounded_results_dir
            / "rollouts"
            / f"rollout_{rollout_id:03d}.jsonl"
        )
        expected_lock = dict(raw.get("source_lock", {}) or {})
        hdf5_source = _source_record(hdf5_path)
        jsonl_source = _source_record(jsonl_path)
        _require_same_source_record(
            actual=hdf5_source,
            expected=dict(expected_lock.get("hdf5", {}) or {}),
            label=f"rollout_{rollout_id}_hdf5",
        )
        _require_same_source_record(
            actual=jsonl_source,
            expected=dict(expected_lock.get("jsonl", {}) or {}),
            label=f"rollout_{rollout_id}_jsonl",
        )
        sources.append(
            {
                "return_start_step_id": int(
                    contract["return_start_pre_action_observation_step"]
                ),
                "hdf5_source": hdf5_source,
                "jsonl_source": jsonl_source,
            }
        )
    return sources


def _initial_planner_state() -> dict[str, Any]:
    return {
        "primitive_cycle_index": 0,
        "coverage_completed_dump_count": 0,
        "coverage_corridor_id": -1,
        "coverage_candidate_scores": [
            _outcome_state_row(cell_id, attempts=0)
            for cell_id in range(6)
        ],
    }


def _post_return_planner_state() -> dict[str, Any]:
    return {
        "primitive_cycle_index": 1,
        "coverage_completed_dump_count": 1,
        "coverage_corridor_id": 3,
        "coverage_candidate_scores": [
            _outcome_state_row(
                cell_id,
                attempts=int(cell_id == 3),
            )
            for cell_id in range(6)
        ],
    }


def _outcome_state_row(
    cell_id: int,
    *,
    attempts: int,
) -> dict[str, Any]:
    return {
        "corridor_id": int(cell_id),
        "attempts": int(attempts),
        "depleted": 0,
        "belief_coverage": 0.0,
        "low_productivity_streak": 0,
        "remaining_depth_m": 0.08,
        "rejection_reason": "",
    }


def _gate_for_rejection(reason: str) -> str:
    if reason in {"outcome_depleted", "outcome_attempt_limit"}:
        return "outcome_state"
    if reason == "corridor_blocked":
        return "blocked_corridor"
    if reason.startswith("wall_"):
        return "wall_safety_2d"
    if reason.startswith("tuple_start_"):
        return "tuple_start_reachability"
    if reason.startswith("worktool_3d_"):
        return "worktool_sweep_3d"
    if "depth_exhausted" in reason:
        return "exhausted_physical_cell"
    if reason.startswith("hard_bottom_"):
        return "hard_bottom_budget"
    if reason.startswith("removed_depth_"):
        return "removed_depth_support"
    if reason in {
        "prototype_score_adjustment_rejected",
        "not_nearest_removed_depth_in_outcome_cell",
        "not_selected_equal_distance_a0_tie_break",
    }:
        return "exact_k1_or_score"
    return "other"


def _finite_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _require_same_source_record(
    *,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    label: str,
) -> None:
    for key in ("path", "size_bytes", "sha256"):
        if actual.get(key) != expected.get(key):
            raise ValueError(f"{label} source lock drift at {key}")


def _implementation_source_lock() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    relative_paths = (
        "testbed/eval/coverage_execution_gate_preflight.py",
        "testbed/eval/coverage_replan_replay.py",
        "testbed/planner/primitive/coverage/execution_candidates.py",
        "testbed/planner/primitive/coverage/execution_runtime.py",
        "testbed/planner/primitive/coverage/start_reachability.py",
        "testbed/planner/primitive/coverage/wall_safety.py",
        "testbed/planner/primitive/coverage/worktool_sweep.py",
    )
    return {
        relative_path: _source_record(
            _require_file(repo_root / relative_path)
        )
        for relative_path in relative_paths
    }


def _yaml_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def _json_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be a mapping: {path}")
    return value


def _require_file(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _require_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(resolved)
    return resolved


__all__ = [
    "COVERAGE_EXECUTION_PRODUCTION_PREFLIGHT_SCHEMA",
    "OUTPUT_FILENAME",
    "REQUIRED_PRODUCTION_CASE_IDS",
    "build_coverage_execution_gate_preflight",
    "build_gate_decision",
    "summarize_candidate_trace",
    "write_preflight_artifact",
]
