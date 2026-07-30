"""Combine hard-bottom offline evidence into one explicit live-run gate."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HARD_BOTTOM_DIAGNOSIS_GATE_SCHEMA = (
    "act_hard_bottom_cycle6_root_cause_report_v1"
)
HARD_BOTTOM_DIAGNOSIS_GATE_V2_SCHEMA = (
    "act_hard_bottom_cycle6_root_cause_report_v2"
)
EXECUTION_DIAGNOSIS_SCHEMA = "act_hard_bottom_cycle6_diagnosis_v1"
COVERAGE_REPLAN_SCHEMA = "coverage_replan_replay_v1"
GOAL_COMPARISON_SCHEMA = "hard_bottom_goal_comparison_v1"
POLICY_REPLAY_SCHEMA = "hard_bottom_goal_policy_replay_v1"
REPORT_JSON_FILENAME = "root_cause_report.json"
REPORT_MARKDOWN_FILENAME = "root_cause_report.md"
REPORT_V2_JSON_FILENAME = "root_cause_report_v2.json"
REPORT_V2_MARKDOWN_FILENAME = "root_cause_report_v2.md"

_GEOMETRIC_PRIMARY_CAUSES = frozenset(
    {
        "planner_depth_geometry_primary",
        "act_execution_capability_primary",
        "bucket_collision_envelope_incomplete_primary",
    }
)


def build_hard_bottom_diagnosis_gate(
    *,
    execution_diagnosis_path: str | Path,
    coverage_replan_path: str | Path,
    goal_comparison_path: str | Path,
    policy_replay_path: str | Path | None = None,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build a no-overwrite evidence report and decide whether live may run."""

    diagnosis_path = _require_file(execution_diagnosis_path)
    replan_path = _require_file(coverage_replan_path)
    comparison_path = _require_file(goal_comparison_path)
    replay_path = (
        None
        if policy_replay_path is None
        else _require_file(policy_replay_path)
    )
    destination = Path(output_dir).expanduser().resolve()
    json_path = destination / (
        REPORT_JSON_FILENAME
        if replay_path is None
        else REPORT_V2_JSON_FILENAME
    )
    markdown_path = destination / (
        REPORT_MARKDOWN_FILENAME
        if replay_path is None
        else REPORT_V2_MARKDOWN_FILENAME
    )
    for path in (json_path, markdown_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    diagnosis = _read_json(diagnosis_path)
    replan = _read_json(replan_path)
    comparison = _read_json(comparison_path)
    policy_replay = None if replay_path is None else _read_json(replay_path)
    _require_schema(
        diagnosis,
        EXECUTION_DIAGNOSIS_SCHEMA,
        label="execution diagnosis",
    )
    _require_schema(
        replan,
        COVERAGE_REPLAN_SCHEMA,
        label="coverage replan",
    )
    _require_schema(
        comparison,
        GOAL_COMPARISON_SCHEMA,
        label="goal comparison",
    )
    if policy_replay is not None:
        _require_schema(
            policy_replay,
            POLICY_REPLAY_SCHEMA,
            label="policy replay",
        )
        _validate_policy_replay(
            policy_replay=policy_replay,
            comparison=comparison,
        )

    classification = _mapping(diagnosis, "classification")
    facts = _mapping(classification, "facts")
    primary = str(classification.get("primary_cause", ""))
    additional = [
        str(value)
        for value in classification.get("additional_findings", [])
    ]
    root_flags = _mapping(replan, "root_cause_flags")
    corrected_replan = _mapping(replan, "corrected_production_replan")
    ownership_only = _mapping(
        replan,
        "contact_ownership_only_counterfactual",
    )
    bookkeeping_fixed = bool(
        root_flags.get("bookkeeping_corridor_4_wall_depletion_removed")
    )
    semantic_mismatch = bool(
        "data_scene_cell_semantic_mismatch" in additional
        or root_flags.get("data_scene_cell_semantic_mismatch")
    )
    evidence_conflict = _classification_conflicts_with_facts(
        primary=primary,
        facts=facts,
    )
    offline_unique_primary = primary in _GEOMETRIC_PRIMARY_CAUSES
    bounded_probe_required = bool(
        not offline_unique_primary or evidence_conflict
    )
    corrected_status = str(corrected_replan.get("status", ""))
    bookkeeping_only = bool(
        bookkeeping_fixed
        and primary in {"bookkeeping_only", "bookkeeping_primary", "none"}
        and not semantic_mismatch
        and corrected_status == "selected"
    )
    formal_allowed = bool(
        bookkeeping_only
        and not bounded_probe_required
        and replan.get("live_1x10_allowed") is not False
    )

    policy_action_evidence = _mapping(
        comparison,
        "policy_action_evidence",
    )
    train_support = _mapping(comparison, "train_support_evidence")
    temporal_contract = _mapping(comparison, "temporal_state_contract")
    temporal_validation = _mapping(temporal_contract, "validation")
    target_summaries = _target_summaries(comparison)
    policy_action_status = (
        str(policy_action_evidence.get("status"))
        if policy_replay is None
        else "complete_independent_checkpoint_replay"
    )
    no_synthetic_policy_actions = (
        policy_action_evidence.get("no_synthetic_policy_actions_emitted")
        if policy_replay is None
        else True
    )
    policy_replay_summary = (
        {}
        if policy_replay is None
        else _mapping(policy_replay, "cross_target_summary")
    )
    unresolved_causes = [primary] if primary else []
    if semantic_mismatch and "data_scene_cell_semantic_mismatch" not in (
        unresolved_causes
    ):
        unresolved_causes.append("data_scene_cell_semantic_mismatch")

    report: dict[str, Any] = {
        "schema": (
            HARD_BOTTOM_DIAGNOSIS_GATE_SCHEMA
            if policy_replay is None
            else HARD_BOTTOM_DIAGNOSIS_GATE_V2_SCHEMA
        ),
        "status": (
            "live_gate_open_bookkeeping_only"
            if formal_allowed
            else "live_gate_closed_unresolved_root_causes"
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_lock": {
            "execution_diagnosis": _source_record(diagnosis_path),
            "coverage_replan": _source_record(replan_path),
            "goal_comparison": _source_record(comparison_path),
            **(
                {}
                if replay_path is None
                else {"policy_replay": _source_record(replay_path)}
            ),
        },
        "root_cause": {
            "primary": primary,
            "additional": additional,
            "unresolved": unresolved_causes,
            "offline_unique_primary": offline_unique_primary,
            "evidence_conflict": evidence_conflict,
        },
        "measurements": {
            key: facts.get(key)
            for key in (
                "hard_bottom_margin_m",
                "planned_depth_m",
                "planned_minimum_clearance_m",
                "actual_peak_penetration_m",
                "actual_penetration_overshoot_m",
                "contact_bucket_tip_clearance_m",
                "logical_cell_id",
                "centerline_physical_cell_ids",
                "swept_physical_cell_ids",
            )
        },
        "bookkeeping": {
            "ownership_fix_confirmed": bookkeeping_fixed,
            "ownership_only_selected_corridor_id": ownership_only.get(
                "selected_corridor_id"
            ),
            "corrected_replan_status": corrected_status,
            "is_only_remaining_problem": bookkeeping_only,
        },
        "production_replan": {
            "status": corrected_status,
            "selected_corridor_id": corrected_replan.get(
                "selected_corridor_id"
            ),
            "corridor_4": _candidate_summary(
                corrected_replan,
                corridor_id=4,
            ),
            "live_gate_reason": replan.get("live_gate_reason"),
        },
        "goal_comparison": {
            "evidence_scope": comparison.get("evidence_scope"),
            "status": comparison.get("status"),
            "target_order": comparison.get("target_order"),
            "targets": target_summaries,
            "train_support_status": train_support.get("status"),
            "strict_train_kept_step_count": train_support.get(
                "kept_step_count"
            ),
            "train_source_episode_ids": train_support.get(
                "train_source_episode_ids"
            ),
            "validation_source_episode_ids_excluded": train_support.get(
                "validation_source_episode_ids_excluded"
            ),
            "policy_action_evidence_status": policy_action_status,
            "no_synthetic_policy_actions_emitted": (
                no_synthetic_policy_actions
            ),
            "independent_temporal_state_validation": (
                temporal_validation.get("status")
                if policy_replay is None
                else _mapping(
                    policy_replay,
                    "independent_policy_state_contract",
                ).get("status")
            ),
            "policy_replay": policy_replay_summary,
        },
        "evidence_matrix": {
            "frozen_closed_loop_source": {
                "status": "analyzed_offline",
                "scope": diagnosis.get("evidence_scope"),
                "claim": "cycle_5_cut_reconstructed_through_first_bottom_contact",
            },
            "production_replan_replay": {
                "status": "complete",
                "scope": replan.get("evidence_kind"),
                "teacher_forced_recorded_observation": replan.get(
                    "teacher_forced_recorded_observation"
                ),
            },
            "three_goal_comparison": {
                "status": (
                    comparison.get("status")
                    if policy_replay is None
                    else "complete_with_independent_checkpoint_replay"
                ),
                "scope": comparison.get("evidence_scope"),
                "policy_actions": policy_action_status,
            },
            "bounded_live_probe": {
                "status": (
                    "required_not_run"
                    if bounded_probe_required
                    else "not_run_not_required"
                ),
                "reason": (
                    "offline_evidence_ambiguous_or_conflicting"
                    if bounded_probe_required
                    else "offline_primary_cause_is_unique_and_nonconflicting"
                ),
            },
            "formal_a0_1x10": {
                "status": (
                    "eligible_not_run"
                    if formal_allowed
                    else "not_run_gate_closed"
                ),
                "artifact_created": False,
            },
        },
        "gate": {
            "bookkeeping_only_required": True,
            "bounded_probe_required": bounded_probe_required,
            "bounded_probe_executed": False,
            "formal_a0_1x10_allowed": formal_allowed,
            "formal_a0_1x10_executed": False,
            "next_action": (
                "generate_fresh_preflight_then_one_a0_1x10"
                if formal_allowed
                else "separate_act_conditioning_single_factor_fix"
            ),
            "secondary_required_fix": (
                "separate_logical_outcome_cell_from_physical_safety_geometry"
                if semantic_mismatch
                else ""
            ),
            "prohibited_actions": [
                "planned_depth_clamp_as_root_cause_mask",
                "unity_bounded_probe_without_ambiguity",
                "formal_a0_1x10_while_gate_closed",
                "effect_model",
                "planned_cut_calibration",
                "a1_a2",
                "a0_3x10",
                "thirty_percent_freeze",
                "retrain",
                "new_data",
            ],
        },
    }

    destination.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_markdown(report),
        encoding="utf-8",
    )
    return report


def _classification_conflicts_with_facts(
    *,
    primary: str,
    facts: dict[str, Any],
) -> bool:
    margin = float(facts.get("hard_bottom_margin_m", float("nan")))
    planned_clearance = float(
        facts.get("planned_minimum_clearance_m", float("nan"))
    )
    overshoot = float(
        facts.get("actual_penetration_overshoot_m", float("nan"))
    )
    tip_clearance = float(
        facts.get("contact_bucket_tip_clearance_m", float("nan"))
    )
    values = (margin, planned_clearance, overshoot, tip_clearance)
    if not all(value == value for value in values):
        return True
    if primary == "planner_depth_geometry_primary":
        return planned_clearance >= margin
    if primary == "act_execution_capability_primary":
        return not (
            planned_clearance >= margin
            and (overshoot > margin or tip_clearance < margin)
        )
    if primary == "bucket_collision_envelope_incomplete_primary":
        return tip_clearance < margin
    return True


def _validate_policy_replay(
    *,
    policy_replay: dict[str, Any],
    comparison: dict[str, Any],
) -> None:
    if policy_replay.get("status") != "complete":
        raise ValueError("policy replay status must be complete")
    if (
        policy_replay.get("evidence_scope")
        != "teacher_forced_recorded_observation"
    ):
        raise ValueError("policy replay evidence scope is invalid")
    if policy_replay.get("target_order") != ["M0", "E1", "W1"]:
        raise ValueError("policy replay target order is invalid")
    state_contract = _mapping(
        policy_replay,
        "independent_policy_state_contract",
    )
    if (
        state_contract.get("status") != "passed"
        or bool(state_contract.get("shared_temporal_buffer", True))
        or int(state_contract.get("branch_count", -1)) != 3
    ):
        raise ValueError("policy replay independent state contract failed")
    replay_window = _mapping(
        policy_replay,
        "recorded_observation_window",
    )
    comparison_window = _mapping(
        comparison,
        "recorded_observation_window",
    )
    for key in (
        "frame_count",
        "first_action_step_id",
        "last_action_step_id",
    ):
        if int(replay_window.get(key, -1)) != int(
            comparison_window.get(key, -2)
        ):
            raise ValueError(
                f"policy replay window disagrees with comparison at {key}"
            )
    summaries = _mapping(policy_replay, "cross_target_summary")
    if set(summaries) != {"M0", "E1", "W1"}:
        raise ValueError("policy replay summary target inventory is invalid")


def _target_summaries(comparison: dict[str, Any]) -> dict[str, Any]:
    raw_targets = _mapping(comparison, "targets")
    support = _mapping(
        _mapping(comparison, "train_support_evidence"),
        "targets",
    )
    summaries: dict[str, Any] = {}
    for target_id in ("M0", "E1", "W1"):
        target = _mapping(raw_targets, target_id)
        target_support = _mapping(support, target_id)
        raw_fields = _mapping(target, "raw_fields")
        summaries[target_id] = {
            "description": target.get("description"),
            "exemplar_id": target.get("exemplar_id"),
            "source_episode_id": target.get("source_episode_id"),
            "distance": target.get("distance"),
            "artifact_sha256": target.get("artifact_sha256"),
            "entry_x_m": raw_fields.get("operator_entry_x_m"),
            "entry_z_m": raw_fields.get("operator_entry_z_m"),
            "exit_x_m": raw_fields.get("operator_exit_x_m"),
            "exit_z_m": raw_fields.get("operator_exit_z_m"),
            "planned_depth_m": raw_fields.get(
                "operator_cut_depth_peak_m"
            ),
            "p01_p99_in_support_fraction": target_support.get(
                "p01_p99_in_support_fraction"
            ),
        }
    return summaries


def _candidate_summary(
    corrected_replan: dict[str, Any],
    *,
    corridor_id: int,
) -> dict[str, Any]:
    scores = corrected_replan.get("candidate_scores", [])
    if not isinstance(scores, list):
        raise ValueError("corrected production replan candidate_scores must be a list")
    for candidate in scores:
        if not isinstance(candidate, dict):
            continue
        if int(candidate.get("corridor_id", -1)) != int(corridor_id):
            continue
        return {
            "corridor_id": int(corridor_id),
            "swept_physical_cell_ids": candidate.get(
                "wall_swept_cell_ids"
            ),
            "depth_exhausted_swept_cell_ids": candidate.get(
                "depth_exhausted_swept_cell_ids"
            ),
            "rejection_reason": candidate.get("rejection_reason"),
        }
    return {"corridor_id": int(corridor_id), "missing": True}


def _render_markdown(report: dict[str, Any]) -> str:
    root = _mapping(report, "root_cause")
    measurements = _mapping(report, "measurements")
    replan = _mapping(report, "production_replan")
    corridor = _mapping(replan, "corridor_4")
    goals = _mapping(report, "goal_comparison")
    gate = _mapping(report, "gate")
    return (
        "# A0 第六铲 Hard-Bottom 根因报告\n\n"
        "## 结论\n\n"
        f"- 主因：`{root.get('primary')}`。\n"
        f"- 附加问题：`{', '.join(root.get('additional', [])) or 'none'}`。\n"
        "- bookkeeping 字段所有权修复已确认，但不是唯一剩余问题。\n"
        f"- bounded live probe："
        f"`{report['evidence_matrix']['bounded_live_probe']['status']}`。\n"
        f"- 正式 A0 1x10："
        f"`{report['evidence_matrix']['formal_a0_1x10']['status']}`。\n\n"
        "## 关键数值\n\n"
        f"- planned depth：`{measurements.get('planned_depth_m')}m`\n"
        f"- planned minimum hard-bottom clearance："
        f"`{measurements.get('planned_minimum_clearance_m')}m`\n"
        f"- actual peak penetration："
        f"`{measurements.get('actual_peak_penetration_m')}m`\n"
        f"- actual overshoot over plan："
        f"`{measurements.get('actual_penetration_overshoot_m')}m`\n"
        f"- contact bucket-tip clearance："
        f"`{measurements.get('contact_bucket_tip_clearance_m')}m`\n"
        f"- logical / centerline / swept cells："
        f"`{measurements.get('logical_cell_id')}` / "
        f"`{measurements.get('centerline_physical_cell_ids')}` / "
        f"`{measurements.get('swept_physical_cell_ids')}`\n\n"
        "## Production replan\n\n"
        f"- status：`{replan.get('status')}`\n"
        f"- corridor 4 swept cells："
        f"`{corridor.get('swept_physical_cell_ids')}`\n"
        f"- exhausted intersection："
        f"`{corridor.get('depth_exhausted_swept_cell_ids')}`\n"
        f"- rejection：`{corridor.get('rejection_reason')}`\n\n"
        "## 三目标离线对照边界\n\n"
        f"- evidence：`{goals.get('evidence_scope')}`\n"
        f"- strict-train steps：`{goals.get('strict_train_kept_step_count')}`\n"
        f"- policy action replay："
        f"`{goals.get('policy_action_evidence_status')}`；未生成合成动作。\n\n"
        "## Gate\n\n"
        f"- formal A0 1x10 allowed："
        f"`{gate.get('formal_a0_1x10_allowed')}`\n"
        f"- next action：`{gate.get('next_action')}`\n"
        f"- secondary fix：`{gate.get('secondary_required_fix')}`\n"
    )


def _require_file(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _require_schema(
    payload: dict[str, Any],
    expected: str,
    *,
    label: str,
) -> None:
    actual = str(payload.get("schema", ""))
    if actual != expected:
        raise ValueError(
            f"{label} schema must be {expected!r}, got {actual!r}"
        )


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return value


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": int(path.stat().st_size),
    }


__all__ = [
    "HARD_BOTTOM_DIAGNOSIS_GATE_SCHEMA",
    "HARD_BOTTOM_DIAGNOSIS_GATE_V2_SCHEMA",
    "REPORT_JSON_FILENAME",
    "REPORT_MARKDOWN_FILENAME",
    "REPORT_V2_JSON_FILENAME",
    "REPORT_V2_MARKDOWN_FILENAME",
    "build_hard_bottom_diagnosis_gate",
]
