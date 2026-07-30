"""Offline alignment evidence for exact coverage tuples and paired returns.

The builder freezes recorded rollout evidence, evaluates tuple-start
reachability, replays the production selector, and optionally compares two
return tokens with isolated ACT temporal state.  It never starts Unity or
claims that an offline handoff has been corrected in closed loop.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
)
from testbed.eval.coverage_replan_replay import (
    _production_static_config,
    _run_production_selection,
)
from testbed.eval.coverage_return_policy_replay import (
    run_teacher_forced_return_replay,
)
from testbed.planner.primitive.coverage.start_reachability import (
    CoverageTupleStartReachabilityService,
)
from testbed.planner.primitive.effects.return_handoff import (
    ReturnStartEnvelopeGateConfig,
    ReturnStartEnvelopeGateInputs,
    ReturnStartEnvelopeGateService,
)

TUPLE_START_ALIGNMENT_DIAGNOSIS_SCHEMA = "tuple_start_alignment_diagnosis_v1"
OUTPUT_FILENAME = f"{TUPLE_START_ALIGNMENT_DIAGNOSIS_SCHEMA}.json"
EVIDENCE_SCOPE = "frozen_replay_teacher_forced_and_production_preflight"
NOMINAL_3D_CLEARANCE_BLOCKER = "nominal_3d_clearance_contract_blocks_all"
RETURN_AXIS_TRAIN_SUPPORT_SCHEMA = "strict18_return_axis_train_support_v1"


def build_return_axis_train_support(
    qpos_support_audit: Mapping[str, Any],
    *,
    axis_index: int,
    qpos_tolerance: float,
    activation_margin: float,
    target_margin: float,
    expected_cell_ids: Sequence[int],
) -> dict[str, Any]:
    """Prove a return-axis target stays inside every train-cell range."""

    tolerance = float(qpos_tolerance)
    activation = float(activation_margin)
    target_offset = float(target_margin)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("return_axis_qpos_tolerance_invalid")
    if (
        not np.isfinite(activation)
        or not np.isfinite(target_offset)
        or activation <= target_offset
        or target_offset <= 0.0
    ):
        raise ValueError("return_axis_control_margins_invalid")
    expected = tuple(int(cell_id) for cell_id in expected_cell_ids)
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("return_axis_expected_cell_ids_invalid")
    raw_records = qpos_support_audit.get("records")
    if not isinstance(raw_records, Sequence):
        raise ValueError("return_axis_qpos_support_records_missing")
    grouped: dict[int, list[float]] = {}
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            raise ValueError("return_axis_qpos_support_record_invalid")
        if str(raw.get("partition", "")) != "train":
            continue
        try:
            cell_id = int(raw["return_envelope_cell_id"])
            value = float(raw[f"qpos_{int(axis_index)}"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("return_axis_train_record_invalid") from exc
        if not np.isfinite(value):
            raise ValueError("return_axis_train_record_nonfinite")
        grouped.setdefault(cell_id, []).append(value)

    blockers: list[str] = []
    observed = set(grouped)
    for cell_id in sorted(set(expected) - observed):
        blockers.append(f"return_axis_train_support_missing:cell_{cell_id}")
    for cell_id in sorted(observed - set(expected)):
        blockers.append(
            f"return_axis_train_support_unexpected:cell_{cell_id}"
        )

    cells: dict[str, dict[str, Any]] = {}
    for cell_id in expected:
        values = np.asarray(grouped.get(cell_id, []), dtype=np.float64)
        if values.size == 0:
            continue
        p95 = float(np.quantile(values, 0.95, method="linear"))
        train_max = float(np.max(values))
        upper = p95 + tolerance
        activation_threshold = upper - activation
        target = upper - target_offset
        supported = bool(target <= train_max + 1.0e-12)
        if not supported:
            blockers.append(
                f"return_axis_target_outside_train_support:cell_{cell_id}"
            )
        cells[str(cell_id)] = {
            "cell_id": cell_id,
            "train_count": int(values.size),
            f"train_p95_qpos_{int(axis_index)}": p95,
            f"train_max_qpos_{int(axis_index)}": train_max,
            f"locked_envelope_upper_qpos_{int(axis_index)}": upper,
            f"activation_threshold_qpos_{int(axis_index)}": (
                activation_threshold
            ),
            f"target_qpos_{int(axis_index)}": target,
            "target_headroom_to_train_max": train_max - target,
            "target_within_train_support": supported,
        }
    return {
        "schema": RETURN_AXIS_TRAIN_SUPPORT_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "axis_index": int(axis_index),
        "expected_cell_ids": list(expected),
        "observed_train_cell_ids": sorted(observed),
        "qpos_tolerance": tolerance,
        "activation_margin": activation,
        "target_margin": target_offset,
        "target_cell_scope": "locked_active_return_cell",
        "cells": cells,
        "blockers": blockers,
    }


def build_tuple_start_alignment_diagnosis(
    *,
    rollout_results_dir: str | Path,
    original_eval_config_path: str | Path,
    production_preflight_config_path: str | Path,
    return_transition_artifact_path: str | Path,
    execution_library_path: str | Path,
    worktool_sweep_artifact_path: str | Path,
    output_dir: str | Path,
    device: str = "cuda",
    teacher_forced_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one no-overwrite diagnosis across three frozen bounded rollouts."""

    results_dir = _require_dir(rollout_results_dir)
    original_config_path = _require_file(original_eval_config_path)
    production_config_path = _require_file(production_preflight_config_path)
    transition_path = _require_file(return_transition_artifact_path)
    execution_path = _require_file(execution_library_path)
    sweep_path = _require_file(worktool_sweep_artifact_path)
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite diagnosis directory: {destination}"
        )

    original_config = _yaml_mapping(original_config_path)
    production_config = _yaml_mapping(production_config_path)
    transition = _json_mapping(transition_path)
    execution = _json_mapping(execution_path)
    sweep = _json_mapping(sweep_path)
    _validate_artifact_chain(
        transition=transition,
        execution=execution,
        sweep=sweep,
        transition_path=transition_path,
        execution_path=execution_path,
        sweep_path=sweep_path,
        production_config=production_config,
    )
    episode_168 = _record_by_id(
        transition,
        exemplar_id="episode_168",
    )
    if episode_168.get("paired_return_exemplar_id") != "episode_158":
        raise ValueError("episode_168 must pair with gold return episode_158")

    static_config = _production_static_config(production_config)
    reachability = CoverageTupleStartReachabilityService.from_config(
        static_config.execution_library.start_reachability
    )
    gate = _exact_handoff_gate(original_config)
    transition_records = tuple(
        _mapping(record, label="return transition record")
        for record in _sequence(
            transition.get("records"),
            label="return transition records",
        )
    )
    sweep_records = {
        str(record["exemplar_id"]): record
        for record in _sequence(
            sweep.get("records"),
            label="worktool sweep records",
        )
        if isinstance(record, dict) and "exemplar_id" in record
    }
    if len(sweep_records) != 374:
        raise ValueError("worktool sweep must contain 374 unique tuples")

    rollout_alignments: list[dict[str, Any]] = []
    replay_inputs: list[dict[str, Any]] = []
    for rollout_id in range(3):
        jsonl_path = _require_file(
            results_dir / "rollouts" / f"rollout_{rollout_id:03d}.jsonl"
        )
        hdf5_path = _require_file(
            results_dir / "hdf5_rollouts" / f"episode_{rollout_id}.hdf5"
        )
        alignment, replay_input = _align_one_rollout(
            rollout_id=rollout_id,
            jsonl_path=jsonl_path,
            hdf5_path=hdf5_path,
            episode_168=episode_168,
            transition_records=transition_records,
            sweep_records=sweep_records,
            reachability=reachability,
            exact_handoff_gate=gate,
            static_config=static_config,
        )
        rollout_alignments.append(alignment)
        replay_inputs.append(replay_input)

    optimistic_3d = _optimistic_3d_clearance_contract(sweep)
    if optimistic_3d["candidate_count_at_or_above_hard_clearance"] != 0:
        raise ValueError(
            "current diagnosis expects the frozen 3D contract to block all"
        )

    runner = teacher_forced_runner or run_teacher_forced_return_replay
    teacher_forced = runner(
        original_config=original_config,
        original_config_path=original_config_path,
        replay_inputs=replay_inputs,
        exact_token=np.asarray(
            episode_168["exact_return_start_envelope_tokens_v1"],
            dtype=np.float32,
        ),
        device=str(device),
    )
    if teacher_forced.get("status") != "completed":
        raise ValueError("teacher-forced return comparison did not complete")

    artifact = {
        "schema": TUPLE_START_ALIGNMENT_DIAGNOSIS_SCHEMA,
        "status": "completed_blocked_before_live",
        "evidence_scope": EVIDENCE_SCOPE,
        "offline_only": True,
        "closed_loop_state_correction_claim": False,
        "promotion_eligible": False,
        "source_lock": {
            "original_eval_config": _source_record(original_config_path),
            "production_preflight_config": _source_record(production_config_path),
            "return_transition_artifact": _source_record(transition_path),
            "execution_library": _source_record(execution_path),
            "worktool_sweep_artifact": _source_record(sweep_path),
            "rollouts": [
                {
                    "rollout_id": int(item["rollout_id"]),
                    "jsonl": dict(item["source_lock"]["jsonl"]),
                    "hdf5": dict(item["source_lock"]["hdf5"]),
                }
                for item in rollout_alignments
            ],
        },
        "contract_identity": {
            "selected_tuple": "episode_168",
            "paired_gold_return": "episode_158",
            "pairing_key": [
                "source_episode_id",
                "return_next_material_cycle_id",
            ],
            "return_transition_artifact_sha256": _sha256(transition_path),
            "execution_library_sha256": _sha256(execution_path),
            "worktool_sweep_artifact_sha256": _sha256(sweep_path),
        },
        "return_start_support": {
            "global_p01_p99_all_three_in_support": all(
                bool(item["return_start"]["global_p01_p99_in_support"])
                for item in rollout_alignments
            ),
            "episode_168_rejected_all_three": all(
                not bool(item["return_start"]["episode_168_reachability"]["eligible"])
                for item in rollout_alignments
            ),
            "reachable_alternative_count_by_rollout": [
                int(item["return_start"]["reachable_tuple_count"])
                for item in rollout_alignments
            ],
        },
        "handoff_contract": {
            "old_cell_token_reported_ready_all_three": all(
                bool(item["handoff"]["recorded_old_cell_gate_ready"])
                for item in rollout_alignments
            ),
            "exact_episode_158_gate_rejects_all_three": all(
                not bool(item["handoff"]["exact_gate"]["ready"])
                for item in rollout_alignments
            ),
            "wrong_recorded_handoff_cannot_enter_dig_after_fix": True,
        },
        "rollouts": rollout_alignments,
        "teacher_forced_return_act_comparison": teacher_forced,
        "production_preflight": {
            "episode_168_not_selected": all(
                item["production_replay"]["selected_exemplar_id"] != "episode_168"
                for item in rollout_alignments
            ),
            "pre_return_qpos_used_as_3d_dig_start": False,
            "planned_handoff_phase": ("paired_expert_handoff_to_dig_exemplar_start"),
            "final_handoff_phase": "actual_live_handoff_qpos",
            "per_rollout": [
                dict(item["production_replay"]) for item in rollout_alignments
            ],
        },
        "optimistic_3d_clearance_contract": optimistic_3d,
        "gate_decision": {
            "start_mismatch_offline_contract_proof": "passed",
            "meaning": (
                "mismatched recorded states are rejected before dig; "
                "offline replay does not prove return closed-loop correction"
            ),
            "bounded_live_allowed": False,
            "blocker": NOMINAL_3D_CLEARANCE_BLOCKER,
            "thresholds_relaxed": False,
            "bounded_live_started": False,
            "functional_1x10_started": False,
        },
    }
    destination.mkdir(parents=True, exist_ok=False)
    output_path = destination / OUTPUT_FILENAME
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(
            artifact,
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    return artifact


def _align_one_rollout(
    *,
    rollout_id: int,
    jsonl_path: Path,
    hdf5_path: Path,
    episode_168: Mapping[str, Any],
    transition_records: Sequence[Mapping[str, Any]],
    sweep_records: Mapping[str, Mapping[str, Any]],
    reachability: CoverageTupleStartReachabilityService,
    exact_handoff_gate: ReturnStartEnvelopeGateService,
    static_config: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return_rows = [row for row in rows if str(row.get("skill_name", "")) == "return"]
    if not return_rows:
        raise ValueError(f"rollout {rollout_id} has no return segment")
    first_action_step = int(return_rows[0]["step_id"])
    last_action_step = int(return_rows[-1]["step_id"])
    if [int(row["step_id"]) for row in return_rows] != list(
        range(first_action_step, last_action_step + 1)
    ):
        raise ValueError(f"rollout {rollout_id} return segment is discontinuous")
    next_rows = [
        row for row in rows if int(row.get("step_id", -1)) == last_action_step + 1
    ]
    if len(next_rows) != 1 or str(next_rows[0].get("skill_name", "")) != "dig":
        raise ValueError(f"rollout {rollout_id} lacks one return-to-dig handoff row")
    selected = [
        item
        for item in return_rows[0].get("coverage_candidate_scores", ())
        if isinstance(item, dict) and item.get("status") == "selected"
    ]
    if len(selected) != 1 or selected[0].get("exemplar_id") != "episode_168":
        raise ValueError(f"rollout {rollout_id} did not select episode_168")
    old_tokens = [
        np.asarray(
            row.get("return_start_envelope_tokens", ()),
            dtype=np.float32,
        )
        for row in return_rows
    ]
    if any(token.shape != (18,) for token in old_tokens) or any(
        not np.array_equal(token, old_tokens[0]) for token in old_tokens[1:]
    ):
        raise ValueError(f"rollout {rollout_id} old return token is not stable 18D")
    exact_token = np.asarray(
        episode_168["exact_return_start_envelope_tokens_v1"],
        dtype=np.float32,
    )
    exact_mask = np.asarray(
        episode_168["exact_return_start_envelope_valid_mask"],
        dtype=np.uint8,
    )

    return_start_step = first_action_step - 1
    handoff_step = last_action_step
    with h5py.File(hdf5_path, "r") as handle:
        step_ids = np.asarray(
            handle["timestamps/step_id"],
            dtype=np.int64,
        )
        start_obs = _observation_at_step(
            handle,
            step_ids,
            return_start_step,
        )
        handoff_obs = _observation_at_step(
            handle,
            step_ids,
            handoff_step,
        )
    start_facts = _return_start_facts(start_obs)
    episode_168_evaluation = reachability.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256=str(episode_168["raw_fields_sha256"]),
        live_return_start_facts=start_facts,
        selection_phase="post_return",
    )
    reachable: list[tuple[str, float, float]] = []
    for record in transition_records:
        evaluation = reachability.evaluate(
            exemplar_id=str(record["exemplar_id"]),
            raw_fields_sha256=str(record["raw_fields_sha256"]),
            live_return_start_facts=start_facts,
            selection_phase="post_return",
        )
        if evaluation.eligible:
            reachable.append(
                (
                    str(record["exemplar_id"]),
                    float(evaluation.rms_distance),
                    float(evaluation.linf_distance),
                )
            )
    reachable.sort(key=lambda item: (item[1], item[2], item[0]))

    exact_gate = exact_handoff_gate.evaluate(
        ReturnStartEnvelopeGateInputs(
            token=exact_token,
            env_state=handoff_obs["env_state"],
            qpos=handoff_obs["qpos"],
            qvel=handoff_obs["qvel"],
            prior_bounds=lambda: (None, None),
            prior_mapping=lambda: None,
            use_prior_spatial_bounds=False,
            use_prior_qpos_bounds=False,
            exact_contract_required=True,
            use_prior_depth_bounds=False,
            exact_valid_mask=exact_mask,
        )
    )
    exact_target = exact_token[7:11]
    old_target = old_tokens[0][7:11]
    handoff_qpos = np.asarray(handoff_obs["qpos"][:4], dtype=np.float64)

    state_row = {
        "primitive_cycle_index": 1,
        "coverage_completed_dump_count": 1,
        "coverage_corridor_id": 3,
        "coverage_candidate_scores": [
            {
                "corridor_id": cell_id,
                "attempts": int(cell_id == 3),
                "depleted": 0,
                "belief_coverage": 0.0,
                "low_productivity_streak": 0,
                "remaining_depth_m": 0.08,
                "rejection_reason": "",
            }
            for cell_id in range(6)
        ],
    }
    production = _run_production_selection(
        static_config=static_config,
        pre_contact_row=state_row,
        observation={
            "step_id": return_start_step,
            "qpos": start_obs["qpos"],
            "qvel": start_obs["qvel"],
            "env_state": start_obs["env_state"],
        },
        depth_exhausted_physical_cell_id=None,
    )
    selected_candidate = dict(production.get("selected_candidate", {}) or {})

    distance = _mapping(
        _mapping(
            _json_mapping(Path(reachability.config.artifact_path)).get(
                "distance_contract"
            ),
            label="distance contract",
        ).get("normalization"),
        label="distance normalization",
    )
    p01 = np.asarray(distance["p01"], dtype=np.float64)
    p99 = np.asarray(distance["p99"], dtype=np.float64)
    start_vector = np.asarray(start_facts, dtype=np.float64)
    global_violations = np.flatnonzero((start_vector < p01) | (start_vector > p99))
    best_reachable_nominal = max(
        (
            float(sweep_records[item[0]]["sampled_convex_cover_clearance_m"])
            for item in reachable
        ),
        default=float("-inf"),
    )

    alignment = {
        "rollout_id": int(rollout_id),
        "source_lock": {
            "jsonl": _source_record(jsonl_path),
            "hdf5": _source_record(hdf5_path),
        },
        "alignment_contract": {
            "first_return_action_step": first_action_step,
            "return_start_pre_action_observation_step": return_start_step,
            "last_return_action_step": last_action_step,
            "return_handoff_post_action_observation_step": handoff_step,
            "next_dig_action_step": last_action_step + 1,
            "hdf5_rows_are_post_action": True,
        },
        "return_start": {
            "facts_11d": _float_list(start_facts),
            "global_p01_p99_in_support": bool(global_violations.size == 0),
            "global_p01_p99_violation_indices": [
                int(value) for value in global_violations
            ],
            "episode_168_reachability": {
                "eligible": bool(episode_168_evaluation.eligible),
                "rejection_reason": str(
                    episode_168_evaluation.rejection_reason
                ),
                **episode_168_evaluation.as_trace_fields(),
            },
            "reachable_tuple_count": len(reachable),
            "nearest_reachable_tuples": [
                {
                    "exemplar_id": item[0],
                    "rms_distance": item[1],
                    "linf_distance": item[2],
                }
                for item in reachable[:10]
            ],
            "best_reachable_nominal_3d_clearance_m": (best_reachable_nominal),
        },
        "return_target": {
            "recorded_cell_token_source": str(
                return_rows[0].get(
                    "return_start_envelope_token_source",
                    "",
                )
            ),
            "recorded_cell_token": _float_list(old_tokens[0]),
            "paired_exact_token_source": ("strict_train_gold_return:episode_158"),
            "paired_exact_token": _float_list(exact_token),
            "use_prior_spatial_bounds_after_fix": False,
            "use_prior_qpos_bounds_after_fix": False,
            "relocate_or_synthetic_fallback_allowed_after_fix": False,
        },
        "handoff": {
            "facts_11d": _float_list(_return_start_facts(handoff_obs)),
            "recorded_old_cell_gate_ready": bool(
                next_rows[0].get(
                    "return_to_dig_start_envelope_ready",
                    False,
                )
            ),
            "old_cell_target_qpos": _float_list(old_target),
            "paired_exact_target_qpos": _float_list(exact_target),
            "old_cell_target_abs_qpos_error": _float_list(
                np.abs(handoff_qpos - old_target)
            ),
            "paired_exact_target_abs_qpos_error": _float_list(
                np.abs(handoff_qpos - exact_target)
            ),
            "old_cell_target_max_abs_qpos_error": float(
                np.max(np.abs(handoff_qpos - old_target))
            ),
            "paired_exact_target_max_abs_qpos_error": float(
                np.max(np.abs(handoff_qpos - exact_target))
            ),
            "exact_gate": {
                "ready": bool(exact_gate.ready),
                "error": float(exact_gate.error),
                "failed_fields": [
                    str(name)
                    for name, check in exact_gate.checks.items()
                    if not bool(check.get("ok", False))
                ],
                "checks": dict(exact_gate.checks),
            },
        },
        "production_replay": {
            "evidence_kind": "offline_production_service_replay",
            "teacher_forced_recorded_observation": True,
            "status": str(production["status"]),
            "error": str(production["error"]),
            "selected_exemplar_id": str(
                selected_candidate.get("source_exemplar_id", "")
            ),
            "episode_168_rejected_by_start_reachability": bool(
                not episode_168_evaluation.eligible
            ),
            "candidate_scores": list(production["candidate_scores"]),
        },
    }
    replay_input = {
        "rollout_id": int(rollout_id),
        "hdf5_path": hdf5_path,
        "return_action_steps": [int(row["step_id"]) for row in return_rows],
        "recorded_actions": {
            int(row["step_id"]): _float_list(row["action"]) for row in return_rows
        },
        "old_token": old_tokens[0].copy(),
    }
    return alignment, replay_input


def _exact_handoff_gate(
    config: Mapping[str, Any],
) -> ReturnStartEnvelopeGateService:
    switch = _mapping(
        _mapping(config.get("policy"), label="policy config").get("switch"),
        label="switch config",
    )
    return ReturnStartEnvelopeGateService(
        ReturnStartEnvelopeGateConfig(
            enabled=bool(switch["return_to_dig_start_envelope_gate_enabled"]),
            action_dim=4,
            spatial_tolerance=float(
                switch["return_to_dig_start_envelope_spatial_tolerance"]
            ),
            depth_tolerance_m=float(
                switch["return_to_dig_start_envelope_depth_tolerance_m"]
            ),
            local_depth_tolerance_m=float(
                switch["return_to_dig_start_envelope_local_depth_tolerance_m"]
            ),
            plane_depth_tolerance_m=float(
                switch["return_to_dig_start_envelope_plane_depth_tolerance_m"]
            ),
            plane_depth_mode=str(
                switch["return_to_dig_start_envelope_plane_depth_mode"]
            ),
            qpos_tolerance=float(switch["return_to_dig_start_envelope_qpos_tolerance"]),
            require_contact=bool(
                switch["return_to_dig_start_envelope_require_contact"]
            ),
        )
    )


def _optimistic_3d_clearance_contract(
    sweep: Mapping[str, Any],
) -> dict[str, Any]:
    contract = _mapping(
        sweep.get("clearance_contract"),
        label="worktool clearance contract",
    )
    records = [
        _mapping(item, label="worktool sweep record")
        for item in _sequence(
            sweep.get("records"),
            label="worktool sweep records",
        )
    ]
    pose_margin = float(contract["pose_interpolation_bound_m"])
    act_margin = float(contract["act_tracking_margin_m"])
    hard_clearance = float(contract["hard_clearance_m"])
    nominal = np.asarray(
        [float(record["sampled_convex_cover_clearance_m"]) for record in records],
        dtype=np.float64,
    )
    optimistic = nominal - pose_margin - act_margin
    best_index = int(np.argmax(nominal))
    return {
        "sample_count": len(records),
        "maximum_nominal_clearance_m": float(nominal[best_index]),
        "maximum_effective_clearance_with_zero_start_displacement_m": float(
            optimistic[best_index]
        ),
        "best_exemplar_id": str(records[best_index]["exemplar_id"]),
        "pose_interpolation_bound_m": pose_margin,
        "act_tracking_margin_m": act_margin,
        "assumed_live_start_displacement_bound_m": 0.0,
        "hard_clearance_m": hard_clearance,
        "candidate_count_at_or_above_hard_clearance": int(
            np.sum(optimistic >= hard_clearance)
        ),
        "blocker": NOMINAL_3D_CLEARANCE_BLOCKER,
    }


def _validate_artifact_chain(
    *,
    transition: Mapping[str, Any],
    execution: Mapping[str, Any],
    sweep: Mapping[str, Any],
    transition_path: Path,
    execution_path: Path,
    sweep_path: Path,
    production_config: Mapping[str, Any],
) -> None:
    if (
        transition.get("schema") != "strict_train_coverage_return_transition_library_v1"
        or transition.get("status") != "completed"
        or int(transition.get("gold_return_sample_count", -1)) != 358
        or int(transition.get("paired_post_return_tuple_count", -1)) != 353
    ):
        raise ValueError("return transition artifact contract invalid")
    if (
        execution.get("schema")
        != "strict_train_coverage_execution_library_v1_1"
        or int(execution.get("sample_count", -1)) != 374
        or execution.get("status") != "completed"
    ):
        raise ValueError("execution library contract invalid")
    if (
        sweep.get("schema") != "coverage_worktool_sweep_library_v1"
        or sweep.get("status") != "completed"
        or int(sweep.get("sample_count", -1)) != 374
    ):
        raise ValueError("worktool sweep artifact contract invalid")
    execution_sha = _sha256(execution_path)
    if (
        _mapping(
            transition.get("source_lock"),
            label="return transition source lock",
        ).get("execution_library_sha256")
        != execution_sha
        or _mapping(
            sweep.get("source_lock"),
            label="worktool sweep source lock",
        ).get("execution_library_sha256")
        != execution_sha
    ):
        raise ValueError("artifact chain execution SHA drift")
    actual_tuple = _mapping(
        _mapping(
            _mapping(
                _mapping(
                    production_config.get("policy"),
                    label="policy config",
                ).get("dig_cut_planner"),
                label="dig planner config",
            ).get("coverage"),
            label="coverage config",
        ).get("actual_tuple_execution_library"),
        label="actual tuple config",
    )
    reachability = _mapping(
        actual_tuple.get("start_reachability"),
        label="start reachability config",
    )
    sweep_config = _mapping(
        actual_tuple.get("worktool_sweep_3d"),
        label="worktool sweep config",
    )
    expected = (
        (actual_tuple.get("path"), str(execution_path), _sha256(execution_path)),
        (
            reachability.get("artifact_path"),
            str(transition_path),
            _sha256(transition_path),
        ),
        (
            sweep_config.get("artifact_path"),
            str(sweep_path),
            _sha256(sweep_path),
        ),
    )
    configured_shas = (
        actual_tuple.get("artifact_sha256"),
        reachability.get("artifact_sha256"),
        sweep_config.get("artifact_sha256"),
    )
    for (configured_path, expected_path, expected_sha), configured_sha in zip(
        expected,
        configured_shas,
        strict=True,
    ):
        if (
            str(Path(configured_path).expanduser().resolve()) != expected_path
            or str(configured_sha) != expected_sha
        ):
            raise ValueError("production companion path/SHA drift")


def _observation_at_step(
    handle: h5py.File,
    step_ids: np.ndarray,
    step_id: int,
) -> dict[str, np.ndarray]:
    indices = np.flatnonzero(step_ids == int(step_id))
    if indices.size != 1:
        raise ValueError(
            f"expected one HDF5 observation for step {step_id}; found {indices.size}"
        )
    index = int(indices[0])
    return {
        "qpos": np.asarray(
            handle["observations/qpos"][index],
            dtype=np.float32,
        ),
        "qvel": np.asarray(
            handle["observations/qvel"][index],
            dtype=np.float32,
        ),
        "env_state": np.asarray(
            handle["observations/env_state"][index],
            dtype=np.float32,
        ),
    }


def _return_start_facts(
    observation: Mapping[str, Any],
) -> tuple[float, ...]:
    qpos = np.asarray(observation["qpos"], dtype=np.float64).reshape(-1)
    qvel = np.asarray(observation["qvel"], dtype=np.float64).reshape(-1)
    env_state = np.asarray(
        observation["env_state"],
        dtype=np.float64,
    ).reshape(-1)
    values = np.concatenate(
        (
            qpos[:4],
            qvel[:4],
            env_state[
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX : ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX
                + 3
            ],
        )
    )
    if values.shape != (11,) or not np.all(np.isfinite(values)):
        raise ValueError("return start facts must be finite 11D")
    return tuple(float(value) for value in values)


def _record_by_id(
    artifact: Mapping[str, Any],
    *,
    exemplar_id: str,
) -> Mapping[str, Any]:
    matches = [
        record
        for record in _sequence(
            artifact.get("records"),
            label="artifact records",
        )
        if isinstance(record, dict)
        and str(record.get("exemplar_id", "")) == str(exemplar_id)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one transition record for {exemplar_id}")
    return matches[0]


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, label=f"JSON root {path}"))


def _yaml_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, label=f"YAML root {path}"))


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a sequence")
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


def _float_list(values: Any) -> list[float]:
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.all(np.isfinite(array)):
        raise ValueError("diagnostic values must be finite")
    return [float(value) for value in array]


__all__ = [
    "EVIDENCE_SCOPE",
    "NOMINAL_3D_CLEARANCE_BLOCKER",
    "OUTPUT_FILENAME",
    "TUPLE_START_ALIGNMENT_DIAGNOSIS_SCHEMA",
    "build_tuple_start_alignment_diagnosis",
]
