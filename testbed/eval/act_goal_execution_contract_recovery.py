"""Offline audit of the planner-to-ACT dig goal execution contract.

It combines frozen cycle-six geometry, M0/E1/W1 teacher-forced policy evidence,
and the strict-train execution library.  It never alters runtime behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ACT_GOAL_EXECUTION_CONTRACT_RECOVERY_SCHEMA = "act_goal_execution_contract_recovery_v1"
MANIFEST_FILENAME = "manifest.json"
EVIDENCE_SCOPE = "offline_frozen_and_teacher_forced"
_DIAGNOSIS_SCHEMA = "act_hard_bottom_cycle6_diagnosis_v1"
_GOAL_COMPARISON_SCHEMA = "hard_bottom_goal_comparison_v1"
_POLICY_REPLAY_SCHEMA = "hard_bottom_goal_policy_replay_v1"
_STRICT_LIBRARY_SCHEMA = "strict_train_coverage_execution_library_v1_1"
_SOURCE_MANIFEST_SCHEMA = "frozen_failure_artifact_sha256_manifest_v1"
_EXPECTED_SAMPLE_COUNT = 374
_TARGET_ORDER = ("M0", "E1", "W1")
_PRIMARY = "planner_act_execution_contract_primary"
_FINDINGS = (
    "synthetic_goal_tuple_joint_ood",
    "dig_goal_supervision_horizon_mismatch",
    "effect_outcome_cell_not_safety_geometry",
)
_FLOAT_TOLERANCE = 1.0e-6

_EXPECTED_REPLAN_STEP_ID = 2987
_EXPECTED_REPLAN: dict[str, Any] = {
    "corridor_id": 1_000_168,
    "source_exemplar_id": "episode_168",
    "source_primitive_episode_id": 168,
    "source_episode_id": 24,
    "effect_outcome_cell_id": 1,
    "return_envelope_cell_id": 0,
    "live_swept_physical_cell_ids": [1, 3],
    "wall_minimum_clearance_m": 0.3736593339760881,
    "planned_hard_bottom_clearance_before_tail_m": 0.06416751444339752,
    "execution_tail_plane_depth_reserve_m": 0.0034275054931640625,
    "planned_hard_bottom_budget_after_tail_m": 0.06074000895023346,
}


def evaluate_coverage_execution_query(
    artifact: Mapping[str, Any],
    *,
    effect_outcome_cell_id: int,
    start_removed_depth_grid_m: Sequence[float],
    raw_fields: Mapping[str, Any],
) -> dict[str, Any]:
    """Delegate to the strict execution library without duplicating semantics."""

    from testbed.data.coverage_execution_library import (
        evaluate_coverage_execution_query as evaluate,
    )

    return evaluate(
        artifact,
        effect_outcome_cell_id=effect_outcome_cell_id,
        start_removed_depth_grid_m=start_removed_depth_grid_m,
        raw_fields=raw_fields,
    )


def build_act_goal_execution_contract_recovery(
    *,
    cycle6_diagnosis_path: str | Path,
    goal_comparison_path: str | Path,
    policy_replay_path: str | Path,
    strict_execution_library_path: str | Path,
    output_dir: str | Path,
    production_replan_pre_path: str | Path | None = None,
    production_replan_post_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build one no-overwrite root-cause and recovery-gate artifact."""

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"output directory already exists: {destination}")
    if (production_replan_pre_path is None) != (
        production_replan_post_path is None
    ):
        raise ValueError("production replan pre and post paths must be provided together")

    paths = {
        "cycle6_diagnosis": _require_file(cycle6_diagnosis_path),
        "goal_comparison": _require_file(goal_comparison_path),
        "policy_replay": _require_file(policy_replay_path),
        "strict_execution_library": _require_file(
            strict_execution_library_path
        ),
    }
    diagnosis = _read_json(paths["cycle6_diagnosis"])
    comparison = _read_json(paths["goal_comparison"])
    replay = _read_json(paths["policy_replay"])
    library = _read_json(paths["strict_execution_library"])
    _require_schema(diagnosis, _DIAGNOSIS_SCHEMA, label="cycle6 diagnosis")
    _require_schema(comparison, _GOAL_COMPARISON_SCHEMA, label="goal comparison")
    _require_schema(replay, _POLICY_REPLAY_SCHEMA, label="policy replay")
    _require_schema(
        library,
        _STRICT_LIBRARY_SCHEMA,
        label="strict execution library",
    )
    source_manifest_path = _validate_cycle6_source_manifest(
        diagnosis=diagnosis,
        diagnosis_path=paths["cycle6_diagnosis"],
    )
    _validate_policy_replay_source(
        policy_replay=replay,
        goal_comparison_path=paths["goal_comparison"],
    )
    _validate_evidence_contracts(
        diagnosis=diagnosis,
        comparison=comparison,
        replay=replay,
        library=library,
    )

    plan = _mapping(diagnosis.get("plan"), "diagnosis.plan")
    logical_cell_id = _integer(
        plan.get("logical_cell_id"),
        "diagnosis.plan.logical_cell_id",
    )
    comparison_window = _mapping(
        comparison.get("recorded_observation_window"),
        "comparison.recorded_observation_window",
    )
    start_removed_depth = _finite_vector(
        comparison_window.get("start_removed_depth_grid_m"),
        6,
        label="start_removed_depth_grid_m",
    )
    targets = _mapping(comparison.get("targets"), "comparison.targets")
    m0 = _mapping(targets.get("M0"), "comparison.targets.M0")
    m0_raw_fields = _mapping(m0.get("raw_fields"), "M0.raw_fields")
    query = evaluate_coverage_execution_query(
        library,
        effect_outcome_cell_id=logical_cell_id,
        start_removed_depth_grid_m=start_removed_depth,
        raw_fields=m0_raw_fields,
    )
    tuple_evidence = _tuple_consistency_evidence(query=query)

    trajectory = _validated_trajectory(diagnosis)
    crossing, contact = _target_crossing(
        diagnosis=diagnosis,
        trajectory=trajectory,
    )
    replay_targets = _mapping(replay.get("targets"), "policy_replay.targets")
    replay_m0 = _mapping(replay_targets.get("M0"), "policy_replay.targets.M0")
    replay_records = _record_sequence(
        replay_m0.get("records"),
        label="policy_replay.targets.M0.records",
    )
    target_crossing = _target_crossing_evidence(
        diagnosis=diagnosis,
        crossing=crossing,
        contact=contact,
        replay_records=replay_records,
    )
    tail = _crossing_to_contact_tail(
        diagnosis=diagnosis,
        trajectory=trajectory,
        crossing=crossing,
        contact=contact,
        replay_records=replay_records,
    )
    supervision_tail = _strict_supervision_tail(library)
    _validate_fixed_findings(
        diagnosis=diagnosis,
        tuple_evidence=tuple_evidence,
        target_crossing=target_crossing,
        tail=tail,
        supervision_tail=supervision_tail,
    )

    source_lock = {
        label: _source_record(path)
        for label, path in (
            ("cycle6_diagnosis", paths["cycle6_diagnosis"]),
            ("cycle6_source_manifest", source_manifest_path),
            ("goal_comparison", paths["goal_comparison"]),
            ("policy_replay", paths["policy_replay"]),
            ("strict_execution_library", paths["strict_execution_library"]),
        )
    }
    production_replan_gate: dict[str, Any]
    if production_replan_pre_path is None:
        production_replan_gate = {
            "status": "gate_pending",
            "reason": "production_replan_pre_post_not_supplied",
            "required_step_id": _EXPECTED_REPLAN_STEP_ID,
        }
        status = "gate_pending"
    else:
        pre_path = _require_file(production_replan_pre_path)
        post_path = _require_file(production_replan_post_path)
        source_lock["production_replan_pre"] = _source_record(pre_path)
        source_lock["production_replan_post"] = _source_record(post_path)
        production_replan_gate = _production_replan_gate(
            pre=_read_json(pre_path),
            post=_read_json(post_path),
        )
        status = (
            "completed"
            if production_replan_gate["all_checks_passed"]
            else "gate_failed"
        )

    artifact: dict[str, Any] = {
        "schema": ACT_GOAL_EXECUTION_CONTRACT_RECOVERY_SCHEMA,
        "status": status,
        "evidence_scope": EVIDENCE_SCOPE,
        "offline_only": True,
        "closed_loop_claim": False,
        "promotion_eligible": False,
        "classification": {
            "primary": _PRIMARY,
            "findings": list(_FINDINGS),
        },
        "m0_tuple_consistency": tuple_evidence,
        "target_crossing": target_crossing,
        "crossing_to_contact_tail": tail,
        "strict_train_supervision_tail": supervision_tail,
        "planned_depth_guard_shadow": {
            "mode": "shadow_only",
            "would_trigger": True,
            "trigger_observation_step_id": target_crossing[
                "observation_step_id"
            ],
            "trigger_local_penetration_m": target_crossing[
                "actual_local_penetration_m"
            ],
            "planned_depth_m": target_crossing["planned_depth_m"],
            "steps_before_contact": target_crossing[
                "contact_step_delta"
            ],
            "runtime_enforced": False,
            "planner_or_policy_semantics_changed": False,
            "closed_loop_success_claim": False,
        },
        "production_replan_gate": production_replan_gate,
        "gate": {
            "formal_a0_1x10_allowed": False,
            "reason": "planner_act_execution_contract_root_cause_unfixed",
            "next_action": "single_factor_planner_act_execution_contract_fix",
            "effect_model_allowed": False,
            "retraining_allowed": False,
        },
        "source_lock": source_lock,
    }
    destination.mkdir(parents=True, exist_ok=False)
    output_path = destination / MANIFEST_FILENAME
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return artifact


def _tuple_consistency_evidence(*, query: Mapping[str, Any]) -> dict[str, Any]:
    residual = _finite_float(
        query.get("tuple_consistency_residual_m"),
        "coverage query tuple_consistency_residual_m",
    )
    p99 = _finite_float(
        query.get("tuple_consistency_residual_p99_m"),
        "coverage query tuple_consistency_residual_p99_m",
    )
    state_distance = _finite_float(
        query.get("removed_depth_distance"),
        "coverage query removed_depth_distance",
    )
    state_p99 = _finite_float(
        query.get("removed_depth_distance_p99"),
        "coverage query removed_depth_distance_p99",
    )
    nearest = str(query.get("nearest_exemplar_id", "")).strip()
    if not nearest:
        raise ValueError("coverage query nearest_exemplar_id is missing")
    raw_residuals = _mapping(
        query.get("raw_field_residuals_from_nearest_exemplar"),
        "coverage query raw_field_residuals_from_nearest_exemplar",
    )
    return {
        "metric": "cut_tuple_consistency_residual_m",
        "effect_outcome_cell_id": _integer(
            query.get("effect_outcome_cell_id"),
            "coverage query effect_outcome_cell_id",
        ),
        "nearest_exemplar_id": nearest,
        "residual": residual,
        "strict_train_p99": p99,
        "strict_train_outcome_cell_p99": _finite_float(
            query.get("outcome_cell_tuple_consistency_residual_p99_m"),
            "coverage query outcome-cell tuple p99",
        ),
        "out_of_strict_train_support": bool(
            residual > p99 + _FLOAT_TOLERANCE
        ),
        "state_distance": state_distance,
        "state_distance_strict_train_p99": state_p99,
        "state_out_of_strict_train_support": bool(
            state_distance > state_p99 + _FLOAT_TOLERANCE
        ),
        "raw_field_residuals": {
            str(key): _finite_float(
                value,
                f"coverage query raw_field_residuals.{key}",
            )
            for key, value in raw_residuals.items()
        },
    }


def _target_crossing(
    *,
    diagnosis: Mapping[str, Any],
    trajectory: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    plan = _mapping(diagnosis.get("plan"), "diagnosis.plan")
    planned_depth = _finite_float(
        plan.get("planned_depth_m"),
        "diagnosis.plan.planned_depth_m",
    )
    cut_window = _mapping(diagnosis.get("cut_window"), "diagnosis.cut_window")
    contact_step = _integer(
        cut_window.get("contact_observation_step_id"),
        "contact_observation_step_id",
    )
    contacts = [
        row
        for row in trajectory
        if _integer(row.get("observation_step_id"), "trajectory step")
        == contact_step
    ]
    if len(contacts) != 1 or not bool(contacts[0].get("typed_bottom_contact")):
        raise ValueError("trajectory does not contain the locked typed contact")
    contact = contacts[0]
    crossing = next(
        (
            row
            for row in trajectory
            if _finite_float(
                row.get("env_state_local_penetration_m"),
                "trajectory local penetration",
            )
            >= planned_depth
        ),
        None,
    )
    if crossing is None:
        raise ValueError("trajectory never crosses the planned depth")
    crossing_step = _integer(
        crossing.get("observation_step_id"),
        "crossing observation_step_id",
    )
    if crossing_step >= contact_step:
        raise ValueError("planned depth was not crossed before bottom contact")
    return crossing, contact


def _target_crossing_evidence(
    *,
    diagnosis: Mapping[str, Any],
    crossing: Mapping[str, Any],
    contact: Mapping[str, Any],
    replay_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    plan = _mapping(diagnosis.get("plan"), "diagnosis.plan")
    crossing_step = _integer(
        crossing.get("observation_step_id"),
        "crossing observation_step_id",
    )
    contact_step = _integer(
        contact.get("observation_step_id"),
        "contact observation_step_id",
    )
    post_actions = [
        row
        for row in replay_records
        if _integer(row.get("observation_step_id"), "policy observation step")
        >= crossing_step
        and _integer(row.get("action_step_id"), "policy action step")
        <= contact_step
    ]
    if not post_actions:
        raise ValueError("policy replay lacks post-crossing cut actions")
    entry = (
        _finite_float(plan.get("entry_x_m"), "plan.entry_x_m"),
        _finite_float(plan.get("entry_z_m"), "plan.entry_z_m"),
    )
    exit_point = (
        _finite_float(plan.get("exit_x_m"), "plan.exit_x_m"),
        _finite_float(plan.get("exit_z_m"), "plan.exit_z_m"),
    )
    crossing_xz = _tip_xz(crossing)
    contact_xz = _tip_xz(contact)
    crossing_progress = _segment_progress(entry, exit_point, crossing_xz)
    contact_progress = _segment_progress(entry, exit_point, contact_xz)
    return {
        "observation_step_id": crossing_step,
        "first_post_crossing_action_step_id": _integer(
            post_actions[0].get("action_step_id"),
            "first post-crossing action step",
        ),
        "contact_observation_step_id": contact_step,
        "contact_step_delta": contact_step - crossing_step,
        "planned_depth_m": _finite_float(
            plan.get("planned_depth_m"),
            "plan.planned_depth_m",
        ),
        "actual_local_penetration_m": _finite_float(
            crossing.get("env_state_local_penetration_m"),
            "crossing local penetration",
        ),
        "bucket_tip_xz_m": list(crossing_xz),
        "planned_segment_progress_fraction": crossing_progress,
        "contact_planned_segment_progress_fraction": contact_progress,
        "crossing_to_contact_projected_progress_fraction": (
            contact_progress - crossing_progress
        ),
        "crossing_to_contact_horizontal_displacement_m": math.hypot(
            contact_xz[0] - crossing_xz[0],
            contact_xz[1] - crossing_xz[1],
        ),
    }


def _crossing_to_contact_tail(
    *,
    diagnosis: Mapping[str, Any],
    trajectory: Sequence[Mapping[str, Any]],
    crossing: Mapping[str, Any],
    contact: Mapping[str, Any],
    replay_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    crossing_step = _integer(
        crossing.get("observation_step_id"),
        "crossing observation_step_id",
    )
    contact_step = _integer(
        contact.get("observation_step_id"),
        "contact observation_step_id",
    )
    tail_rows = [
        row
        for row in trajectory
        if crossing_step
        <= _integer(row.get("observation_step_id"), "trajectory step")
        <= contact_step
    ]
    if not tail_rows:
        raise ValueError("crossing-to-contact trajectory tail is empty")
    cut_window = _mapping(diagnosis.get("cut_window"), "diagnosis.cut_window")
    last_cut_action_step = _integer(
        cut_window.get("last_cut_action_step_id"),
        "last_cut_action_step_id",
    )
    action_rows = [
        row
        for row in replay_records
        if _integer(row.get("observation_step_id"), "policy observation step")
        >= crossing_step
        and _integer(row.get("action_step_id"), "policy action step")
        <= last_cut_action_step
    ]
    if not action_rows:
        raise ValueError("crossing-to-contact ACT action tail is empty")
    plane_depths = [
        _finite_float(
            row.get("bucket_tip_plane_depth_m"),
            "trajectory bucket-tip plane depth",
        )
        for row in tail_rows
    ]
    local_depths = [
        _finite_float(
            row.get("env_state_local_penetration_m"),
            "trajectory local penetration",
        )
        for row in tail_rows
    ]
    return {
        "first_observation_step_id": crossing_step,
        "contact_observation_step_id": contact_step,
        "observation_count": len(tail_rows),
        "post_crossing_action_count": len(action_rows),
        "plane_depth_at_crossing_m": plane_depths[0],
        "plane_depth_at_contact_m": plane_depths[-1],
        "plane_depth_peak_m": max(plane_depths),
        "plane_depth_delta_m": plane_depths[-1] - plane_depths[0],
        "plane_depth_peak_minus_crossing_m": max(plane_depths) - plane_depths[0],
        "local_penetration_at_crossing_m": local_depths[0],
        "local_penetration_at_contact_m": local_depths[-1],
        "local_penetration_peak_m": max(local_depths),
        "typed_bottom_contact_at_endpoint": bool(
            contact.get("typed_bottom_contact")
        ),
        "action_direction_evidence": _action_direction_evidence(action_rows),
    }


def _action_direction_evidence(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fields = (
        "fresh_action",
        "aggregated_action",
        "nearest_train_expert_action",
        "recorded_actual_action",
    )
    summaries = {
        field: _action_summary(records, field=field)
        for field in fields
    }
    fresh_sign = summaries["fresh_action"]["mean_sign"]
    aggregate_sign = summaries["aggregated_action"]["mean_sign"]
    expert_sign = summaries["nearest_train_expert_action"]["mean_sign"]
    return {
        **summaries,
        "joint_axes_1_to_3_mean_sign_consensus": all(
            fresh_sign[index] == aggregate_sign[index] == expert_sign[index]
            for index in range(1, 4)
        ),
        "fresh_vs_aggregate_axis_sign_agreement": [
            fresh_sign[index] == aggregate_sign[index]
            for index in range(4)
        ],
        "aggregate_vs_expert_axis_sign_agreement": [
            aggregate_sign[index] == expert_sign[index]
            for index in range(4)
        ],
    }


def _action_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    field: str,
) -> dict[str, Any]:
    actions = [
        _finite_vector(row.get(field), 4, label=field)
        for row in records
    ]
    columns = list(zip(*actions, strict=True))
    means = [
        math.fsum(column) / len(column)
        for column in columns
    ]
    return {
        "sample_count": len(actions),
        "mean": means,
        "median": [statistics.median(column) for column in columns],
        "last": list(actions[-1]),
        "mean_sign": [_sign(value) for value in means],
        "positive_fraction": [
            sum(value > 0.0 for value in column) / len(column)
            for column in columns
        ],
        "negative_fraction": [
            sum(value < 0.0 for value in column) / len(column)
            for column in columns
        ],
        "zero_fraction": [
            sum(value == 0.0 for value in column) / len(column)
            for column in columns
        ],
    }


def _strict_supervision_tail(library: Mapping[str, Any]) -> dict[str, Any]:
    sample_count = _integer(
        library.get("sample_count"),
        "strict library sample_count",
    )
    if sample_count != _EXPECTED_SAMPLE_COUNT:
        raise ValueError(
            f"strict execution library must contain exactly "
            f"{_EXPECTED_SAMPLE_COUNT} samples"
        )
    audit = _mapping(library.get("tail_audit"), "strict library tail_audit")
    count = _integer(
        audit.get("local_max_minus_token_gt_0_02_count"),
        "tail count",
    )
    if count < 0 or count > sample_count:
        raise ValueError("strict supervision tail count is out of range")
    return {
        "sample_count": sample_count,
        "local_max_minus_token_gt_0_02_count": count,
        "local_max_minus_token_gt_0_02_fraction": count / sample_count,
        "execution_tail_plane_depth_reserve_m": _finite_summary(
            audit.get("execution_tail_plane_depth_reserve_m"),
            label="execution_tail_plane_depth_reserve_m",
        ),
        "local_max_minus_token_m": _finite_summary(
            audit.get("local_max_minus_token_m"),
            label="local_max_minus_token_m",
        ),
    }


def _validate_fixed_findings(
    *,
    diagnosis: Mapping[str, Any],
    tuple_evidence: Mapping[str, Any],
    target_crossing: Mapping[str, Any],
    tail: Mapping[str, Any],
    supervision_tail: Mapping[str, Any],
) -> None:
    if not bool(tuple_evidence.get("out_of_strict_train_support")):
        raise ValueError(
            "fixed synthetic_goal_tuple_joint_ood finding lacks evidence"
        )
    if (
        _integer(tail.get("post_crossing_action_count"), "tail action count")
        <= 0
        or _integer(
            supervision_tail.get("local_max_minus_token_gt_0_02_count"),
            "strict tail count",
        )
        <= 0
        or _integer(
            target_crossing.get("contact_step_delta"),
            "contact step delta",
        )
        <= 0
    ):
        raise ValueError(
            "fixed dig_goal_supervision_horizon_mismatch finding lacks evidence"
        )
    plan = _mapping(diagnosis.get("plan"), "diagnosis.plan")
    logical = _integer(plan.get("logical_cell_id"), "logical_cell_id")
    physical = {
        _integer(value, "physical cell id")
        for field in (
            "centerline_physical_cell_ids",
            "swept_physical_cell_ids",
        )
        for value in _sequence(plan.get(field), f"plan.{field}")
    }
    if logical in physical:
        raise ValueError(
            "fixed effect_outcome_cell_not_safety_geometry finding lacks evidence"
        )


def _production_replan_gate(
    *, pre: Mapping[str, Any], post: Mapping[str, Any]
) -> dict[str, Any]:
    pre_step = _replan_step_id(pre, label="production replan pre")
    post_step = _replan_step_id(post, label="production replan post")
    selected = _mapping(
        post.get("selected_candidate"),
        "production replan post.selected_candidate",
    )
    selected_fields = {**selected, "source_exemplar_id": selected.get("source_exemplar_id", selected.get("exemplar_id"))}
    checks = [
        _check("pre_replan_step_id", pre_step, _EXPECTED_REPLAN_STEP_ID),
        _check("post_replan_step_id", post_step, _EXPECTED_REPLAN_STEP_ID),
    ]
    for key, expected in _EXPECTED_REPLAN.items():
        actual = selected_fields.get(key)
        if key == "live_swept_physical_cell_ids":
            actual = [
                _integer(value, f"selected_candidate.{key}")
                for value in _sequence(actual, f"selected_candidate.{key}")
            ]
        checks.append(_check(key, actual, expected))
    passed = all(bool(item["passed"]) for item in checks)
    return {
        "status": "passed" if passed else "failed",
        "all_checks_passed": passed,
        "pre_status": pre.get("status"),
        "post_status": post.get("status"),
        "selected_candidate": selected_fields,
        "checks": checks,
    }


def _check(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    if isinstance(expected, float):
        try:
            numeric = float(actual)
        except (TypeError, ValueError):
            passed = False
        else:
            passed = math.isfinite(numeric) and math.isclose(
                numeric,
                expected,
                rel_tol=0.0,
                abs_tol=_FLOAT_TOLERANCE,
            )
    else:
        passed = actual == expected
    return {
        "name": name,
        "actual": actual,
        "expected": expected,
        "passed": bool(passed),
    }


def _validate_cycle6_source_manifest(
    *,
    diagnosis: Mapping[str, Any],
    diagnosis_path: Path,
) -> Path:
    reference = _mapping(
        diagnosis.get("source_manifest"),
        "diagnosis.source_manifest",
    )
    if str(reference.get("schema", "")) != _SOURCE_MANIFEST_SCHEMA:
        raise ValueError("cycle6 source-manifest schema is invalid")
    filename = str(reference.get("filename", "")).strip()
    expected_sha = str(reference.get("sha256", "")).strip()
    if not filename or not expected_sha:
        raise ValueError("cycle6 source-manifest reference is incomplete")
    path = _require_file(diagnosis_path.parent / filename)
    actual_sha = _sha256(path)
    if actual_sha != expected_sha:
        raise ValueError(
            "cycle6 source-manifest SHA disagrees with diagnosis"
        )
    manifest = _read_json(path)
    _require_schema(manifest, _SOURCE_MANIFEST_SCHEMA, label="source manifest")
    return path


def _validate_policy_replay_source(
    *,
    policy_replay: Mapping[str, Any],
    goal_comparison_path: Path,
) -> None:
    source_lock = _mapping(
        policy_replay.get("source_lock"),
        "policy_replay.source_lock",
    )
    comparison = _mapping(
        source_lock.get("goal_comparison"),
        "policy_replay.source_lock.goal_comparison",
    )
    expected_sha = str(comparison.get("sha256", "")).strip()
    if expected_sha != _sha256(goal_comparison_path):
        raise ValueError(
            "policy replay goal-comparison SHA disagrees with supplied artifact"
        )
    configured_path = str(comparison.get("path", "")).strip()
    if configured_path and Path(configured_path).expanduser().resolve() != (
        goal_comparison_path
    ):
        raise ValueError(
            "policy replay goal-comparison path disagrees with supplied artifact"
        )


def _validate_evidence_contracts(
    *,
    diagnosis: Mapping[str, Any],
    comparison: Mapping[str, Any],
    replay: Mapping[str, Any],
    library: Mapping[str, Any],
) -> None:
    cycle = _integer(diagnosis.get("cycle_index"), "diagnosis cycle_index")
    if cycle != 5 or _integer(comparison.get("cycle_index"), "comparison cycle") != cycle:
        raise ValueError("recovery audit requires the locked cycle index 5")
    if tuple(comparison.get("target_order", ())) != _TARGET_ORDER:
        raise ValueError("goal comparison target order is invalid")
    if tuple(replay.get("target_order", ())) != _TARGET_ORDER:
        raise ValueError("policy replay target order is invalid")
    replay_state = _mapping(
        replay.get("independent_policy_state_contract"),
        "independent_policy_state_contract",
    )
    if (
        str(replay_state.get("status")) != "passed"
        or bool(replay_state.get("shared_temporal_buffer"))
    ):
        raise ValueError("policy replay temporal states are not independent")
    if str(library.get("status")) != "completed":
        raise ValueError("strict execution library is not completed")
    lineage = _mapping(library.get("source_lineage"), "library.source_lineage")
    if str(lineage.get("partition")) != "train":
        raise ValueError("strict execution library is not train-only")
    validation_ids = [
        _integer(value, "validation source episode id")
        for value in _sequence(
            lineage.get("validation_source_episode_ids"),
            "validation_source_episode_ids",
        )
    ]
    if validation_ids != [33, 34]:
        raise ValueError("strict execution library validation exclusion changed")

    comparison_targets = _mapping(comparison.get("targets"), "comparison.targets")
    replay_targets = _mapping(replay.get("targets"), "replay.targets")
    plan = _mapping(diagnosis.get("plan"), "diagnosis.plan")
    expected_token = _finite_vector(
        plan.get("dig_cut_tokens"),
        10,
        label="diagnosis M0 token",
    )
    for label, token in (
        (
            "goal comparison M0 token",
            _mapping(comparison_targets.get("M0"), "comparison M0").get(
                "dig_cut_tokens"
            ),
        ),
        (
            "policy replay M0 token",
            _mapping(replay_targets.get("M0"), "replay M0").get(
                "dig_cut_tokens"
            ),
        ),
    ):
        candidate = _finite_vector(token, 10, label=label)
        if any(
            not math.isclose(
                left,
                right,
                rel_tol=0.0,
                abs_tol=_FLOAT_TOLERANCE,
            )
            for left, right in zip(expected_token, candidate, strict=True)
        ):
            raise ValueError(f"{label} disagrees with diagnosis")


def _validated_trajectory(
    diagnosis: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    records = _record_sequence(
        diagnosis.get("trajectory"),
        label="diagnosis.trajectory",
    )
    step_ids = [
        _integer(row.get("observation_step_id"), "trajectory step")
        for row in records
    ]
    if step_ids != sorted(step_ids) or len(step_ids) != len(set(step_ids)):
        raise ValueError("diagnosis trajectory steps are not unique and sorted")
    return records


def _replan_step_id(payload: Mapping[str, Any], *, label: str) -> int:
    value = payload.get("replan_step_id", payload.get("step_id"))
    return _integer(value, f"{label} step_id")


def _finite_summary(value: Any, *, label: str) -> dict[str, float]:
    mapping = _mapping(value, label)
    return {
        key: _finite_float(mapping.get(key), f"{label}.{key}")
        for key in ("p50", "p90", "p95", "p99", "max")
    }


def _segment_progress(
    entry: tuple[float, float], exit_point: tuple[float, float], point: tuple[float, float]
) -> float:
    delta_x = exit_point[0] - entry[0]
    delta_z = exit_point[1] - entry[1]
    denominator = delta_x * delta_x + delta_z * delta_z
    if denominator <= 1.0e-12:
        raise ValueError("M0 planned segment is degenerate")
    return (
        (point[0] - entry[0]) * delta_x
        + (point[1] - entry[1]) * delta_z
    ) / denominator


def _tip_xz(row: Mapping[str, Any]) -> tuple[float, float]:
    xyz = _finite_vector(
        row.get("bucket_tip_xyz_m"),
        3,
        label="bucket_tip_xyz_m",
    )
    return xyz[0], xyz[2]


def _record_sequence(value: Any, *, label: str) -> list[Mapping[str, Any]]:
    records = _sequence(value, label)
    if not records:
        raise ValueError(f"{label} must not be empty")
    return [
        _mapping(record, f"{label}[{index}]")
        for index, record in enumerate(records)
    ]


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path}") from exc
    return dict(_mapping(payload, str(path)))


def _require_schema(
    payload: Mapping[str, Any],
    expected: str,
    *,
    label: str,
) -> None:
    actual = str(payload.get("schema", ""))
    if actual != expected:
        raise ValueError(
            f"{label} schema mismatch: expected={expected!r}, actual={actual!r}"
        )


def _require_file(path: str | Path | None) -> Path:
    if path is None:
        raise ValueError("required artifact path is missing")
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"artifact path is not a file: {resolved}")
    return resolved


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise ValueError(f"{label} must be a sequence")
    return value


def _finite_vector(value: Any, size: int, *, label: str) -> list[float]:
    sequence = _sequence(value, label)
    if len(sequence) != size:
        raise ValueError(f"{label} must contain {size} values")
    return [
        _finite_float(item, f"{label}[{index}]")
        for index, item in enumerate(sequence)
    ]


def _finite_float(value: Any, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _integer(value: Any, label: str) -> int:
    numeric = _finite_float(value, label)
    integer = int(numeric)
    if not math.isclose(
        numeric,
        float(integer),
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise ValueError(f"{label} must be integral")
    return integer


def _sign(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
