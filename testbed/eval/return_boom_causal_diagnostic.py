"""Diagnostic separation of return-policy commands and boom actuation.

The capability in this module is deliberately read-only with respect to the
planner, policy checkpoints, thresholds, and training data.  It compares one
recorded return failure with strict-18 expert transitions, and it summarizes
small paired boom pulses collected from Unity without ACT inference.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    DS_ACTION,
    DS_ENV_STATE,
    DS_QPOS,
    DS_QVEL,
    DS_V2_STEP_ACTION_LOSS_MASK,
    DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    DS_V2_STEP_RETURN_TARGET_TOKENS,
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
)
from testbed.eval.boom_actuator_diagnostic import (
    analyze_actuator_trials,
    collect_unity_boom_actuator_response,
)
from testbed.eval.return_boom_diagnostic_contract import (
    ACTUATOR_AUDIT_SCHEMA,
    BOOM_AXIS,
    DIAGNOSTIC_SCHEMA,
    EXPERT_AUDIT_SCHEMA,
    REPORT_SCHEMA,
)

__all__ = [
    "analyze_actuator_trials",
    "build_causal_report",
    "build_expert_action_support_audit",
    "candidate_similarity_metrics",
    "classify_expert_evidence",
    "collect_unity_boom_actuator_response",
    "write_causal_report",
]

RETURN_TARGET_POSITION_SCALE_M = 2.0
RETURN_TARGET_LENGTH_SCALE_M = 2.0
RETURN_TARGET_DEPTH_SCALE_M = 0.8
RETURN_TARGET_PAYLOAD_SCALE_KG = 60.0

# These are diagnostic similarity tolerances, not production safety or handoff
# thresholds.  They only decide whether an expert row is close enough to make
# a causal action comparison.
EXPERT_SIMILARITY_LIMITS = {
    "entry_distance_m": 0.15,
    "exit_distance_m": 0.15,
    "direction_angle_deg": 15.0,
    "length_abs_delta_m": 0.15,
    "depth_abs_delta_m": 0.08,
    "payload_abs_delta_kg": 20.0,
    "envelope_spatial_center_abs_delta_norm": 0.15,
    "envelope_depth_abs_delta_m": 0.02,
    "envelope_tip_radius_abs_delta_m": 0.05,
    "envelope_qpos_center_max_abs_delta": 0.05,
    "envelope_qpos_half_width_max_abs_delta": 0.05,
    "envelope_qvel_abs_max_delta": 0.05,
    "qpos_max_abs_delta": 0.05,
    "qvel_max_abs_delta": 0.10,
}
UPPER_BAND_WIDTH = 0.03
BOOM_BRAKE_ACTION_THRESHOLD = -0.05


def classify_expert_evidence(
    *,
    strict_joint_match_count: int,
    runtime_requires_contact: bool,
    expert_handoff_count: int,
    expert_contact_match_count: int,
    upper_band_example_count: int,
    upper_band_brake_count: int,
) -> str:
    """Classify expert-side evidence without inspecting Unity dynamics."""

    if (
        strict_joint_match_count <= 0
        and runtime_requires_contact
        and expert_handoff_count > 0
        and expert_contact_match_count <= 0
    ):
        return "handoff_contract_outside_expert_support"
    if strict_joint_match_count <= 0:
        return "expert_joint_support_missing"
    if (
        upper_band_example_count > 0
        and upper_band_brake_count * 2 >= upper_band_example_count
    ):
        return "act_temporal_braking_mismatch"
    return "return_target_handoff_gate_conflict"


def candidate_similarity_metrics(
    *,
    anchor: Mapping[str, Any],
    expert: Mapping[str, Any],
    limits: Mapping[str, float] = EXPERT_SIMILARITY_LIMITS,
) -> dict[str, Any]:
    """Measure one expert row against the failed return target and state."""

    anchor_token = _finite_vector(
        anchor.get("return_target_tokens"),
        width=10,
        label="anchor return_target_tokens",
    )
    expert_token = _finite_vector(
        expert.get("return_target_tokens"),
        width=10,
        label="expert return_target_tokens",
    )
    anchor_envelope = _finite_vector(
        anchor.get("return_start_envelope_tokens"),
        width=18,
        label="anchor return_start_envelope_tokens",
    )
    expert_envelope = _finite_vector(
        expert.get("return_start_envelope_tokens"),
        width=18,
        label="expert return_start_envelope_tokens",
    )
    anchor_qpos = _finite_vector(
        anchor.get("qpos"),
        width=4,
        label="anchor qpos",
    )
    anchor_qvel = _finite_vector(
        anchor.get("qvel"),
        width=4,
        label="anchor qvel",
    )
    expert_qpos = _finite_vector(
        expert.get("qpos"),
        width=4,
        label="expert qpos",
    )
    expert_qvel = _finite_vector(
        expert.get("qvel"),
        width=4,
        label="expert qvel",
    )

    entry_distance = float(
        np.linalg.norm(
            (expert_token[0:2] - anchor_token[0:2])
            * RETURN_TARGET_POSITION_SCALE_M
        )
    )
    exit_distance = float(
        np.linalg.norm(
            (expert_token[2:4] - anchor_token[2:4])
            * RETURN_TARGET_POSITION_SCALE_M
        )
    )
    direction_angle = _direction_angle_deg(
        anchor_token[4:6],
        expert_token[4:6],
    )
    length_delta = float(
        abs(expert_token[6] - anchor_token[6])
        * RETURN_TARGET_LENGTH_SCALE_M
    )
    depth_delta = float(
        abs(expert_token[7] - anchor_token[7])
        * RETURN_TARGET_DEPTH_SCALE_M
    )
    payload_delta = float(
        abs(expert_token[8] - anchor_token[8])
        * RETURN_TARGET_PAYLOAD_SCALE_KG
    )
    envelope_spatial_delta = np.abs(
        expert_envelope[0:2] - anchor_envelope[0:2]
    )
    envelope_depth_delta = np.abs(
        expert_envelope[[2, 4, 5]] - anchor_envelope[[2, 4, 5]]
    )
    envelope_tip_radius_delta = float(
        abs(expert_envelope[3] - anchor_envelope[3])
    )
    envelope_qpos_center_delta = np.abs(
        expert_envelope[7:11] - anchor_envelope[7:11]
    )
    envelope_qpos_half_width_delta = np.abs(
        expert_envelope[11:15] - anchor_envelope[11:15]
    )
    envelope_qvel_delta = float(
        abs(expert_envelope[15] - anchor_envelope[15])
    )
    qpos_delta = np.abs(expert_qpos - anchor_qpos)
    qvel_delta = np.abs(expert_qvel - anchor_qvel)
    qpos_max_delta = float(np.max(qpos_delta))
    qvel_max_delta = float(np.max(qvel_delta))
    runtime_requires_contact = bool(anchor.get("runtime_requires_contact", False))
    envelope_requires_contact = bool(anchor_envelope[6] > 0.5)
    expert_envelope_requires_contact = bool(expert_envelope[6] > 0.5)
    handoff_contact = bool(expert.get("handoff_contact", False))
    contact_match = handoff_contact == runtime_requires_contact
    envelope_contact_match = (
        expert_envelope_requires_contact == runtime_requires_contact
    )
    runtime_envelope_contact_override_conflict = bool(
        runtime_requires_contact and not envelope_requires_contact
    )
    handoff_local_depth = _finite_float(
        expert.get("handoff_local_depth_m"),
        label="expert handoff local depth",
    )
    runtime_depth_min = _finite_float(
        anchor.get("runtime_local_depth_min_m"),
        label="runtime local-depth minimum",
    )
    runtime_depth_max = _finite_float(
        anchor.get("runtime_local_depth_max_m"),
        label="runtime local-depth maximum",
    )
    depth_gate_match = bool(
        runtime_depth_min <= handoff_local_depth <= runtime_depth_max
    )

    cut_intent_close = bool(
        entry_distance <= float(limits["entry_distance_m"])
        and exit_distance <= float(limits["exit_distance_m"])
        and direction_angle <= float(limits["direction_angle_deg"])
        and length_delta <= float(limits["length_abs_delta_m"])
        and depth_delta <= float(limits["depth_abs_delta_m"])
        and payload_delta <= float(limits["payload_abs_delta_kg"])
    )
    return_envelope_close = bool(
        float(np.max(envelope_spatial_delta))
        <= float(limits["envelope_spatial_center_abs_delta_norm"])
        and float(np.max(envelope_depth_delta))
        <= float(limits["envelope_depth_abs_delta_m"])
        and envelope_tip_radius_delta
        <= float(limits["envelope_tip_radius_abs_delta_m"])
        and float(np.max(envelope_qpos_center_delta))
        <= float(limits["envelope_qpos_center_max_abs_delta"])
        and float(np.max(envelope_qpos_half_width_delta))
        <= float(limits["envelope_qpos_half_width_max_abs_delta"])
        and envelope_qvel_delta
        <= float(limits["envelope_qvel_abs_max_delta"])
        and bool(anchor_envelope[16] > 0.5)
        and bool(anchor_envelope[17] > 0.5)
        and bool(expert_envelope[16] > 0.5)
        and bool(expert_envelope[17] > 0.5)
    )
    target_close = bool(cut_intent_close and return_envelope_close)
    state_close = bool(
        qpos_max_delta <= float(limits["qpos_max_abs_delta"])
        and qvel_max_delta <= float(limits["qvel_max_abs_delta"])
    )
    score = math.sqrt(
        (entry_distance / float(limits["entry_distance_m"])) ** 2
        + (exit_distance / float(limits["exit_distance_m"])) ** 2
        + (direction_angle / float(limits["direction_angle_deg"])) ** 2
        + (length_delta / float(limits["length_abs_delta_m"])) ** 2
        + (depth_delta / float(limits["depth_abs_delta_m"])) ** 2
        + (payload_delta / float(limits["payload_abs_delta_kg"])) ** 2
        + float(
            np.mean(
                (
                    envelope_spatial_delta
                    / float(
                        limits[
                            "envelope_spatial_center_abs_delta_norm"
                        ]
                    )
                )
                ** 2
            )
        )
        + float(
            np.mean(
                (
                    envelope_depth_delta
                    / float(limits["envelope_depth_abs_delta_m"])
                )
                ** 2
            )
        )
        + float(
            np.mean(
                (
                    envelope_qpos_center_delta
                    / float(limits["envelope_qpos_center_max_abs_delta"])
                )
                ** 2
            )
        )
        + float(np.mean((qpos_delta / float(limits["qpos_max_abs_delta"])) ** 2))
        + float(np.mean((qvel_delta / float(limits["qvel_max_abs_delta"])) ** 2))
    )
    return {
        "entry_distance_m": entry_distance,
        "exit_distance_m": exit_distance,
        "direction_angle_deg": direction_angle,
        "length_abs_delta_m": length_delta,
        "depth_abs_delta_m": depth_delta,
        "payload_abs_delta_kg": payload_delta,
        "envelope_spatial_center_abs_delta_norm": (
            envelope_spatial_delta.tolist()
        ),
        "envelope_depth_abs_delta_m": envelope_depth_delta.tolist(),
        "envelope_tip_radius_abs_delta_m": envelope_tip_radius_delta,
        "envelope_qpos_center_abs_delta": (
            envelope_qpos_center_delta.tolist()
        ),
        "envelope_qpos_half_width_abs_delta": (
            envelope_qpos_half_width_delta.tolist()
        ),
        "envelope_qvel_abs_max_delta": envelope_qvel_delta,
        "qpos_abs_delta": qpos_delta.tolist(),
        "qvel_abs_delta": qvel_delta.tolist(),
        "qpos_max_abs_delta": qpos_max_delta,
        "qvel_max_abs_delta": qvel_max_delta,
        "cut_intent_close": cut_intent_close,
        "return_envelope_close": return_envelope_close,
        "target_close": target_close,
        "state_close": state_close,
        "runtime_requires_contact": runtime_requires_contact,
        "runtime_envelope_requires_contact": envelope_requires_contact,
        "expert_envelope_requires_contact": expert_envelope_requires_contact,
        "envelope_contact_requirement_match": envelope_contact_match,
        "runtime_envelope_contact_override_conflict": (
            runtime_envelope_contact_override_conflict
        ),
        "expert_handoff_contact": handoff_contact,
        "contact_requirement_match": contact_match,
        "expert_handoff_local_depth_m": handoff_local_depth,
        "runtime_local_depth_min_m": runtime_depth_min,
        "runtime_local_depth_max_m": runtime_depth_max,
        "depth_gate_match": depth_gate_match,
        "strict_joint_match": bool(
            target_close
            and state_close
            and contact_match
            and envelope_contact_match
            and depth_gate_match
        ),
        "normalized_joint_distance": score,
    }


def build_causal_report(
    *,
    expert_audit: Mapping[str, Any],
    actuator_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine the two independent checks without promoting either result."""

    if expert_audit.get("schema") != EXPERT_AUDIT_SCHEMA:
        raise ValueError("expert audit schema mismatch")
    if actuator_audit.get("schema") != ACTUATOR_AUDIT_SCHEMA:
        raise ValueError("actuator audit schema mismatch")

    expert_status = str(expert_audit.get("status", "failed"))
    actuator_status = str(actuator_audit.get("status", "failed"))
    expert_class = str(expert_audit.get("classification", ""))
    actuator_class = str(actuator_audit.get("classification", ""))
    if actuator_class == "direction_or_gain_anomaly":
        causal = "unity_actuator_mapping_or_gain"
    elif actuator_class == "normal" and expert_class == (
        "act_temporal_braking_mismatch"
    ):
        causal = "act_temporal_prediction"
    elif actuator_class == "normal" and expert_class in {
        "return_target_handoff_gate_conflict",
        "handoff_contract_outside_expert_support",
        "expert_joint_support_missing",
    }:
        causal = "return_handoff_contract_outside_expert_support"
    else:
        causal = "inconclusive"

    complete = expert_status == "passed" and actuator_status == "passed"
    evidence_summary = _build_causal_evidence_summary(
        expert_audit=expert_audit,
        actuator_audit=actuator_audit,
    )
    return {
        "schema": REPORT_SCHEMA,
        "diagnostic_schema": DIAGNOSTIC_SCHEMA,
        "status": "passed" if complete else "failed",
        "causal_classification": causal,
        "expert_classification": expert_class,
        "unity_actuator_classification": actuator_class,
        "evidence_summary": evidence_summary,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_change_allowed": False,
        "retraining_allowed": False,
        "writes_training_hdf5": False,
        "downstream_gates": {
            "continuous_predictor_allowed": False,
            "offline_e0_g1_w1_allowed": False,
            "bounded_live_allowed": False,
            "functional_1x10_allowed": False,
        },
    }


def _build_causal_evidence_summary(
    *,
    expert_audit: Mapping[str, Any],
    actuator_audit: Mapping[str, Any],
) -> dict[str, Any]:
    anchor = expert_audit.get("anchor")
    support = expert_audit.get("expert_support")
    analysis = actuator_audit.get("analysis")
    if not isinstance(anchor, Mapping):
        raise ValueError("expert audit anchor is missing")
    if not isinstance(support, Mapping):
        raise ValueError("expert audit support summary is missing")
    if not isinstance(analysis, Mapping):
        raise ValueError("actuator audit analysis is missing")

    anchor_action = _finite_vector(
        anchor.get("act_action"),
        width=4,
        label="anchor ACT action",
    )
    anchor_qvel = _finite_vector(
        anchor.get("qvel"),
        width=4,
        label="anchor qvel",
    )
    pose_summaries = analysis.get("pose_summaries")
    if not isinstance(pose_summaries, Sequence) or isinstance(
        pose_summaries,
        (str, bytes),
    ):
        raise ValueError("actuator pose summaries are missing")
    upper = next(
        (
            item
            for item in pose_summaries
            if isinstance(item, Mapping) and item.get("pose_id") == "upper"
        ),
        None,
    )
    if not isinstance(upper, Mapping):
        raise ValueError("actuator audit lacks upper-pose evidence")
    negative = upper.get("negative")
    if not isinstance(negative, Mapping):
        raise ValueError("actuator audit lacks upper negative-command trial")
    trial_command = _finite_float(
        negative.get("command"),
        label="upper negative trial command",
    )
    if abs(trial_command) <= 1.0e-9:
        raise ValueError("upper negative trial command must be non-zero")
    trial_response_sign = int(negative.get("qpos_response_sign", 0))
    if trial_response_sign not in (-1, 1):
        raise ValueError("upper negative trial response sign is invalid")
    tail_qvel = _finite_float(
        negative.get("qvel_1_tail_mean_abs"),
        label="upper negative trial tail qvel",
    )
    scaled_qvel = (
        trial_response_sign
        * tail_qvel
        * float(anchor_action[BOOM_AXIS] / trial_command)
    )
    anchor_qvel_1 = float(anchor_qvel[BOOM_AXIS])
    return {
        "expert_handoff_count": int(
            support.get("all_partition_handoff_count", 0)
        ),
        "same_cell_handoff_count": int(
            support.get("same_cell_handoff_count", 0)
        ),
        "same_cell_strict_joint_match_count": int(
            support.get("same_cell_strict_joint_match_count", 0)
        ),
        "same_cell_return_envelope_and_state_match_count": int(
            support.get(
                "same_cell_return_envelope_and_state_match_count",
                0,
            )
        ),
        "runtime_envelope_contact_override_conflict": bool(
            support.get("runtime_envelope_contact_override_conflict", False)
        ),
        "unity_cross_pose_gain_ratio": _finite_float(
            analysis.get("cross_pose_gain_ratio"),
            label="Unity cross-pose gain ratio",
        ),
        "unity_violation_count": len(analysis.get("violations", [])),
        "anchor_act_boom_action": float(anchor_action[BOOM_AXIS]),
        "anchor_qvel_1": anchor_qvel_1,
        "unity_reference_command": trial_command,
        "unity_reference_tail_qvel_1_abs": tail_qvel,
        "unity_scaled_anchor_qvel_1": scaled_qvel,
        "anchor_qvel_1_abs_error": abs(scaled_qvel - anchor_qvel_1),
    }


def build_expert_action_support_audit(
    *,
    rollout_path: str | Path,
    anchor_step_id: int,
    handoff_audit_path: str | Path,
    return_primitives_dir: str | Path,
    output_path: str | Path,
    continuation_steps: int = 10,
) -> Path:
    """Compare one failed return state with all same-cell expert returns."""

    rollout = _required_file(rollout_path, label="rollout JSONL")
    handoff_audit_file = _required_file(
        handoff_audit_path,
        label="expert handoff audit",
    )
    return_root = Path(return_primitives_dir).expanduser().resolve()
    if not return_root.is_dir():
        raise FileNotFoundError(
            f"return primitive directory missing: {return_root}"
        )
    if continuation_steps < 1:
        raise ValueError("continuation_steps must be positive")

    anchor = _read_rollout_anchor(rollout, step_id=int(anchor_step_id))
    handoff_audit = _json_mapping(handoff_audit_file)
    records = _validated_handoff_records(handoff_audit)
    source_paths = _validated_source_hdf5_paths(handoff_audit)
    planned_cell_id = int(anchor["planned_cut_cell_id"])

    candidates: list[dict[str, Any]] = []
    all_contact_count = 0
    all_token_contact_count = 0
    same_cell_contact_count = 0
    same_cell_count = 0
    for record in records:
        primitive_id = int(record["primitive_episode_id"])
        primitive_path = return_root / f"episode_{primitive_id}.hdf5"
        candidate = _read_expert_candidate(
            primitive_path=primitive_path,
            record=record,
            anchor=anchor,
        )
        all_contact_count += int(bool(candidate["handoff_contact"]))
        all_token_contact_count += int(
            bool(candidate["handoff_envelope_contact_allowed"])
        )
        if int(record["return_envelope_cell_id"]) != planned_cell_id:
            continue
        same_cell_count += 1
        same_cell_contact_count += int(bool(candidate["handoff_contact"]))
        candidates.append(candidate)

    if not candidates:
        raise ValueError(
            f"expert audit has no returns for planned cell {planned_cell_id}"
        )
    candidates.sort(
        key=lambda item: float(
            item["similarity"]["normalized_joint_distance"]
        )
    )

    qpos_upper = _finite_float(
        anchor["handoff_qpos_1_upper"],
        label="handoff qpos_1 upper",
    )
    upper_band_min = qpos_upper - UPPER_BAND_WIDTH
    upper_examples = [
        item
        for item in candidates
        if bool(item["return_target_available"])
        and float(item["handoff_qpos"][BOOM_AXIS]) >= upper_band_min
    ]
    for item in upper_examples:
        source_path = source_paths[int(item["source_episode_id"])]
        item["source_continuation"] = _read_source_continuation(
            source_path=source_path,
            handoff_source_step=int(item["handoff_source_step"]),
            continuation_steps=continuation_steps,
        )
        item["braked_before_or_at_handoff"] = bool(
            item["source_continuation"]["brake_seen_before_or_at_handoff"]
        )

    strict_count = sum(
        bool(item["similarity"]["strict_joint_match"])
        for item in candidates
    )
    target_state_count = sum(
        bool(item["similarity"]["target_close"])
        and bool(item["similarity"]["state_close"])
        for item in candidates
    )
    cut_intent_state_count = sum(
        bool(item["similarity"]["cut_intent_close"])
        and bool(item["similarity"]["state_close"])
        for item in candidates
    )
    envelope_state_count = sum(
        bool(item["similarity"]["return_envelope_close"])
        and bool(item["similarity"]["state_close"])
        for item in candidates
    )
    contact_match_count = sum(
        bool(item["similarity"]["contact_requirement_match"])
        for item in candidates
    )
    envelope_contact_match_count = sum(
        bool(item["similarity"]["envelope_contact_requirement_match"])
        for item in candidates
    )
    depth_gate_match_count = sum(
        bool(item["similarity"]["depth_gate_match"])
        for item in candidates
    )
    upper_brake_count = sum(
        bool(item["braked_before_or_at_handoff"])
        for item in upper_examples
    )
    classification = classify_expert_evidence(
        strict_joint_match_count=strict_count,
        runtime_requires_contact=bool(anchor["runtime_requires_contact"]),
        expert_handoff_count=same_cell_count,
        expert_contact_match_count=contact_match_count,
        upper_band_example_count=len(upper_examples),
        upper_band_brake_count=upper_brake_count,
    )
    expected_sign = _expert_action_to_qpos_sign(
        upper_examples if upper_examples else candidates
    )

    selected_paths = {
        int(item["primitive_episode_id"]): (
            return_root / f"episode_{int(item['primitive_episode_id'])}.hdf5"
        )
        for item in candidates[:10]
    }
    artifact = {
        "schema": EXPERT_AUDIT_SCHEMA,
        "diagnostic_schema": DIAGNOSTIC_SCHEMA,
        "status": "passed",
        "classification": classification,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_thresholds_changed": False,
        "policy_checkpoint_changed": False,
        "training_data_written": False,
        "anchor": anchor,
        "similarity_contract": {
            "limits": dict(EXPERT_SIMILARITY_LIMITS),
            "limits_role": "diagnostic_similarity_only",
            "production_thresholds_unchanged": True,
            "same_cell_required": True,
            "cut_intent_and_return_envelope_required": True,
            "contact_requirement_exact_match_required": True,
            "runtime_local_depth_gate_match_required": True,
        },
        "expert_support": {
            "all_partition_handoff_count": len(records),
            "all_partition_actual_contact_count": all_contact_count,
            "all_partition_envelope_contact_allowed_count": (
                all_token_contact_count
            ),
            "same_cell_id": planned_cell_id,
            "same_cell_handoff_count": same_cell_count,
            "same_cell_return_target_available_count": sum(
                bool(item["return_target_available"]) for item in candidates
            ),
            "same_cell_actual_contact_count": same_cell_contact_count,
            "same_cell_contact_requirement_match_count": contact_match_count,
            "same_cell_envelope_contact_requirement_match_count": (
                envelope_contact_match_count
            ),
            "same_cell_depth_gate_match_count": depth_gate_match_count,
            "same_cell_cut_intent_and_state_match_count": (
                cut_intent_state_count
            ),
            "same_cell_return_envelope_and_state_match_count": (
                envelope_state_count
            ),
            "same_cell_target_and_state_match_ignoring_contact_count": (
                target_state_count
            ),
            "same_cell_strict_joint_match_count": strict_count,
            "runtime_envelope_contact_override_conflict": bool(
                candidates[0]["similarity"][
                    "runtime_envelope_contact_override_conflict"
                ]
            ),
        },
        "boom_upper_band": {
            "handoff_qpos_1_upper": qpos_upper,
            "analysis_band_width": UPPER_BAND_WIDTH,
            "analysis_band_min": upper_band_min,
            "example_count": len(upper_examples),
            "brake_action_threshold": BOOM_BRAKE_ACTION_THRESHOLD,
            "brake_before_or_at_handoff_count": upper_brake_count,
            "continued_negative_action_count": (
                len(upper_examples) - upper_brake_count
            ),
            "expected_positive_command_qpos_sign_from_expert": expected_sign,
            "examples": upper_examples,
        },
        "closest_same_cell_candidates": candidates[:10],
        "source_lock": {
            "rollout": _file_record(rollout),
            "handoff_audit": _file_record(handoff_audit_file),
            "return_primitives_dir": str(return_root),
            "source_hdf5_count": len(source_paths),
            "source_hdf5_hash_checks": handoff_audit["source_lock"][
                "source_hdf5_hash_checks"
            ],
            "closest_primitive_files": [
                _file_record(selected_paths[primitive_id])
                for primitive_id in sorted(selected_paths)
            ],
        },
    }
    destination = _write_json_exclusive(output_path, artifact)
    return destination


def write_causal_report(
    *,
    expert_audit_path: str | Path,
    actuator_audit_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write the immutable combined conclusion from two completed audits."""

    expert_path = _required_file(expert_audit_path, label="expert audit")
    actuator_path = _required_file(
        actuator_audit_path,
        label="actuator audit",
    )
    report = build_causal_report(
        expert_audit=_json_mapping(expert_path),
        actuator_audit=_json_mapping(actuator_path),
    )
    report["source_lock"] = {
        "expert_audit": _file_record(expert_path),
        "actuator_audit": _file_record(actuator_path),
    }
    return _write_json_exclusive(output_path, report)


def _read_rollout_anchor(path: Path, *, step_id: int) -> dict[str, Any]:
    selected: Mapping[str, Any] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, Mapping):
                raise ValueError(f"rollout row {line_number} is not a mapping")
            if int(row.get("step_id", -1)) == step_id:
                selected = row
                break
    if selected is None:
        raise ValueError(f"rollout does not contain step_id={step_id}")
    if str(selected.get("skill_name", "")) != "return":
        raise ValueError("anchor step must be a return-policy step")

    checks = selected.get("return_to_dig_start_envelope_checks")
    if not isinstance(checks, Mapping):
        raise ValueError("anchor lacks return handoff checks")
    qpos_1_check = checks.get("qpos_1")
    contact_check = checks.get("dig_contact")
    local_depth_check = checks.get("local_depth_m")
    if not isinstance(qpos_1_check, Mapping):
        raise ValueError("anchor lacks qpos_1 handoff check")
    if not isinstance(contact_check, Mapping):
        raise ValueError("anchor lacks dig-contact handoff check")
    if not isinstance(local_depth_check, Mapping):
        raise ValueError("anchor lacks local-depth handoff check")

    return {
        "rollout_path": str(path),
        "step_id": step_id,
        "skill_name": "return",
        "primitive_cycle_index": int(
            selected.get("primitive_cycle_index", -1)
        ),
        "planned_cut_cell_id": int(selected.get("planned_cut_cell_id", -1)),
        "qpos": _finite_vector(
            selected.get("qpos"),
            width=4,
            label="anchor qpos",
        ).tolist(),
        "qvel": _finite_vector(
            selected.get("qvel"),
            width=4,
            label="anchor qvel",
        ).tolist(),
        "act_action": _finite_vector(
            selected.get("action"),
            width=4,
            label="anchor action",
        ).tolist(),
        "return_target_tokens": _finite_vector(
            selected.get("return_target_tokens"),
            width=10,
            label="anchor return_target_tokens",
        ).tolist(),
        "return_target_token_source": str(
            selected.get("return_target_token_source", "")
        ),
        "return_start_envelope_tokens": _finite_vector(
            selected.get("return_start_envelope_tokens"),
            width=18,
            label="anchor return_start_envelope_tokens",
        ).tolist(),
        "return_start_envelope_token_source": str(
            selected.get("return_start_envelope_token_source", "")
        ),
        "runtime_requires_contact": bool(
            contact_check.get("required_by_config", False)
        ),
        "runtime_contact_value": _finite_float(
            contact_check.get("value"),
            label="anchor contact value",
        ),
        "runtime_local_depth_m": _finite_float(
            local_depth_check.get("value"),
            label="anchor local depth",
        ),
        "runtime_local_depth_min_m": _finite_float(
            local_depth_check.get("min"),
            label="anchor local depth min",
        ),
        "runtime_local_depth_max_m": _finite_float(
            local_depth_check.get("max"),
            label="anchor local depth max",
        ),
        "handoff_qpos_1_lower": _finite_float(
            qpos_1_check.get("min"),
            label="anchor qpos_1 lower",
        ),
        "handoff_qpos_1_upper": _finite_float(
            qpos_1_check.get("max"),
            label="anchor qpos_1 upper",
        ),
        "handoff_ready": bool(
            selected.get("return_to_dig_start_envelope_ready", False)
        ),
        "handoff_error": _finite_float(
            selected.get("return_to_dig_start_envelope_error", 0.0),
            label="anchor handoff error",
        ),
    }


def _validated_handoff_records(
    payload: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    if payload.get("schema") != "strict18_return_handoff_qpos1_support_audit_v1":
        raise ValueError("expert handoff audit schema mismatch")
    if payload.get("status") != "passed":
        raise ValueError("expert handoff audit is not passed")
    rows = payload.get("records")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("expert handoff records are missing")
    result: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("expert handoff record must be a mapping")
        result.append(row)
    if len(result) != 416:
        raise ValueError(
            f"strict-18 handoff audit must contain 416 rows, got {len(result)}"
        )
    return tuple(result)


def _validated_source_hdf5_paths(
    payload: Mapping[str, Any],
) -> dict[int, Path]:
    source_lock = payload.get("source_lock")
    if not isinstance(source_lock, Mapping):
        raise ValueError("expert handoff audit lacks source lock")
    checks = source_lock.get("source_hdf5_hash_checks")
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
        raise ValueError("expert handoff audit lacks source HDF5 checks")
    paths: dict[int, Path] = {}
    for raw in checks:
        if not isinstance(raw, Mapping) or not bool(raw.get("match", False)):
            raise ValueError("expert source HDF5 hash lock is invalid")
        source_id = int(raw.get("source_episode_id", -1))
        path = _required_file(raw.get("path"), label="expert source HDF5")
        expected = str(raw.get("expected_sha256", ""))
        actual = str(raw.get("actual_sha256", ""))
        if expected != actual or len(expected) != 64:
            raise ValueError("expert source HDF5 SHA lock mismatch")
        paths[source_id] = path
    if len(paths) != 18:
        raise ValueError("strict-18 source lock must contain 18 HDF5s")
    return paths


def _read_expert_candidate(
    *,
    primitive_path: Path,
    record: Mapping[str, Any],
    anchor: Mapping[str, Any],
) -> dict[str, Any]:
    path = _required_file(primitive_path, label="return primitive")
    with h5py.File(path, "r") as handle:
        qpos = _hdf5_matrix(handle, DS_QPOS, width=4)
        qvel = _hdf5_matrix(handle, DS_QVEL, width=4)
        action = _hdf5_matrix(handle, DS_ACTION, width=4)
        env_state = _hdf5_matrix(handle, DS_ENV_STATE)
        loss_mask = np.asarray(
            handle[DS_V2_STEP_ACTION_LOSS_MASK],
            dtype=np.uint8,
        ).reshape(-1)
        target_tokens = _hdf5_matrix(
            handle,
            DS_V2_STEP_RETURN_TARGET_TOKENS,
            width=10,
        )
        envelope_tokens = _hdf5_matrix(
            handle,
            DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
            width=18,
        )
        row_count = qpos.shape[0]
        if any(
            values.shape[0] != row_count
            for values in (
                qvel,
                action,
                env_state,
                target_tokens,
                envelope_tokens,
            )
        ) or loss_mask.shape != (row_count,):
            raise ValueError(f"return primitive row mismatch: {path}")
        if not np.allclose(envelope_tokens, envelope_tokens[0], atol=1.0e-7):
            raise ValueError(f"return envelope token is not stable: {path}")

        metadata = handle.get("metadata")
        if not isinstance(metadata, h5py.Group):
            raise ValueError(f"return primitive lacks metadata: {path}")
        source_start = int(metadata.attrs["source_start_step"])
        handoff_source_step = int(metadata.attrs["return_handoff_step"])
        handoff_local = handoff_source_step - source_start
        if not 0 <= handoff_local < row_count:
            raise ValueError(f"return handoff is outside primitive: {path}")
        source_text = str(metadata.attrs["source_episode_id"])
        expected_source = int(record["source_episode_id"])
        if source_text != f"episode_{expected_source}":
            raise ValueError(f"return primitive source identity mismatch: {path}")

        target_token = target_tokens[handoff_local]
        target_available = bool(target_token[9] > 0.5)
        if target_available:
            target_valid = target_tokens[:, 9] > 0.5
            target_stable = np.all(
                np.isclose(target_tokens, target_token, atol=1.0e-7),
                axis=1,
            )
            valid_indices = np.flatnonzero(
                (loss_mask == 1) & target_valid & target_stable
            )
        else:
            valid_indices = np.flatnonzero(loss_mask == 1)
        if valid_indices.size == 0:
            raise ValueError(
                f"return primitive has no supervised rows: {path}"
            )
        anchor_qpos = _finite_vector(
            anchor.get("qpos"),
            width=4,
            label="anchor qpos",
        )
        anchor_qvel = _finite_vector(
            anchor.get("qvel"),
            width=4,
            label="anchor qvel",
        )
        state_distance = np.sqrt(
            np.mean(
                (
                    (qpos[valid_indices] - anchor_qpos)
                    / EXPERT_SIMILARITY_LIMITS["qpos_max_abs_delta"]
                )
                ** 2,
                axis=1,
            )
            + np.mean(
                (
                    (qvel[valid_indices] - anchor_qvel)
                    / EXPERT_SIMILARITY_LIMITS["qvel_max_abs_delta"]
                )
                ** 2,
                axis=1,
            )
        )
        closest_local = int(valid_indices[int(np.argmin(state_distance))])
        handoff_contact = bool(
            env_state.shape[1] > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX
            and env_state[
                handoff_local,
                ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
            ]
            > 0.5
        )
        if env_state.shape[1] <= ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
            raise ValueError(f"return primitive lacks local depth: {path}")
        handoff_local_depth = float(
            env_state[
                handoff_local,
                ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
            ]
        )
        expert = {
            "return_target_tokens": target_token.tolist(),
            "return_start_envelope_tokens": envelope_tokens[0].tolist(),
            "qpos": qpos[closest_local].tolist(),
            "qvel": qvel[closest_local].tolist(),
            "handoff_contact": handoff_contact,
            "handoff_local_depth_m": handoff_local_depth,
        }
        similarity = candidate_similarity_metrics(
            anchor=anchor,
            expert=expert,
        )
        if not target_available:
            similarity["target_close"] = False
            similarity["strict_joint_match"] = False
            similarity["normalized_joint_distance"] = 1.0e9
        return {
            "primitive_episode_id": int(record["primitive_episode_id"]),
            "source_episode_id": expected_source,
            "partition": str(record["partition"]),
            "return_envelope_cell_id": int(
                record["return_envelope_cell_id"]
            ),
            "primitive_path": str(path),
            "return_target_available": target_available,
            "return_target_tokens": target_token.tolist(),
            "handoff_envelope_tokens": envelope_tokens[0].tolist(),
            "handoff_envelope_contact_allowed": bool(
                envelope_tokens[0, 6] > 0.5
            ),
            "handoff_source_step": handoff_source_step,
            "handoff_local_index": handoff_local,
            "handoff_qpos": qpos[handoff_local].tolist(),
            "handoff_qvel": qvel[handoff_local].tolist(),
            "handoff_action": action[handoff_local].tolist(),
            "handoff_contact": handoff_contact,
            "handoff_local_depth_m": handoff_local_depth,
            "closest_local_index": closest_local,
            "closest_source_step": source_start + closest_local,
            "closest_qpos": qpos[closest_local].tolist(),
            "closest_qvel": qvel[closest_local].tolist(),
            "closest_action": action[closest_local].tolist(),
            "similarity": similarity,
        }


def _read_source_continuation(
    *,
    source_path: Path,
    handoff_source_step: int,
    continuation_steps: int,
) -> dict[str, Any]:
    with h5py.File(source_path, "r") as handle:
        qpos = handle[DS_QPOS]
        qvel = handle[DS_QVEL]
        action = handle[DS_ACTION]
        lookback_start = max(0, handoff_source_step - continuation_steps)
        end = min(qpos.shape[0], handoff_source_step + continuation_steps + 1)
        if not 0 <= handoff_source_step < end:
            raise ValueError(
                f"handoff step is outside expert source: {source_path}"
            )
        pre_handoff_steps = []
        first_pre_handoff_brake: int | None = None
        for source_step in range(lookback_start, handoff_source_step + 1):
            action_1 = float(action[source_step, BOOM_AXIS])
            if (
                first_pre_handoff_brake is None
                and action_1 >= BOOM_BRAKE_ACTION_THRESHOLD
            ):
                first_pre_handoff_brake = source_step
            pre_handoff_steps.append(
                {
                    "source_step": source_step,
                    "qpos_1": float(qpos[source_step, BOOM_AXIS]),
                    "qvel_1": float(qvel[source_step, BOOM_AXIS]),
                    "action_1": action_1,
                }
            )
        steps = []
        first_brake: int | None = None
        for source_step in range(handoff_source_step, end):
            action_1 = float(action[source_step, BOOM_AXIS])
            if (
                first_brake is None
                and action_1 >= BOOM_BRAKE_ACTION_THRESHOLD
            ):
                first_brake = source_step
            steps.append(
                {
                    "source_step": source_step,
                    "qpos_1": float(qpos[source_step, BOOM_AXIS]),
                    "qvel_1": float(qvel[source_step, BOOM_AXIS]),
                    "action_1": action_1,
                }
            )
    return {
        "source_path": str(source_path),
        "step_count": len(steps),
        "pre_handoff_step_count": len(pre_handoff_steps),
        "first_brake_before_or_at_handoff_source_step": (
            first_pre_handoff_brake
        ),
        "brake_seen_before_or_at_handoff": (
            first_pre_handoff_brake is not None
        ),
        "pre_handoff_steps": pre_handoff_steps,
        "first_brake_source_step": first_brake,
        "brake_seen": first_brake is not None,
        "steps": steps,
    }


def _expert_action_to_qpos_sign(
    candidates: Sequence[Mapping[str, Any]],
) -> int:
    products: list[float] = []
    for item in candidates:
        action = _finite_vector(
            item.get("handoff_action"),
            width=4,
            label="expert handoff action",
        )
        qvel = _finite_vector(
            item.get("handoff_qvel"),
            width=4,
            label="expert handoff qvel",
        )
        if abs(action[BOOM_AXIS]) > 0.05 and abs(qvel[BOOM_AXIS]) > 0.01:
            products.append(float(action[BOOM_AXIS] * qvel[BOOM_AXIS]))
    if not products:
        raise ValueError("expert rows do not identify boom command/qpos direction")
    result = _sign(float(np.median(products)))
    if result == 0:
        raise ValueError("expert boom command/qpos direction is ambiguous")
    return result


def _hdf5_matrix(
    handle: h5py.File,
    dataset_path: str,
    *,
    width: int | None = None,
) -> np.ndarray:
    dataset = handle.get(dataset_path)
    if not isinstance(dataset, h5py.Dataset) or dataset.ndim != 2:
        raise ValueError(f"HDF5 dataset {dataset_path} must be a matrix")
    if width is not None and dataset.shape[1] != width:
        raise ValueError(f"HDF5 dataset {dataset_path} width must be {width}")
    result = np.asarray(dataset, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError(f"HDF5 dataset {dataset_path} is non-finite")
    return result


def _required_file(value: Any, *, label: str) -> Path:
    path = Path(str(value)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    return path


def _json_mapping(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON root must be a mapping: {path}")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    resolved = _required_file(path, label="source artifact")
    return {
        "path": str(resolved),
        "sha256": _file_sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _write_json_exclusive(
    value: str | Path,
    payload: Mapping[str, Any],
) -> Path:
    path = Path(value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return path


def _finite_vector(value: Any, *, width: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).reshape(-1)
    if result.shape != (width,) or not np.isfinite(result).all():
        raise ValueError(f"{label} must be a finite {width}D vector")
    return result


def _direction_angle_deg(first: np.ndarray, second: np.ndarray) -> float:
    first_norm = float(np.linalg.norm(first))
    second_norm = float(np.linalg.norm(second))
    if first_norm <= 1.0e-12 or second_norm <= 1.0e-12:
        return 180.0
    cosine = float(
        np.clip(np.dot(first, second) / (first_norm * second_norm), -1.0, 1.0)
    )
    return math.degrees(math.acos(cosine))


def _finite_float(value: Any, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _sign(value: float, *, epsilon: float = 1.0e-9) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0
