"""Teacher-forced strict ACT replay and report generation.

This module owns model loading, faithful temporal-clock replay, fresh-action
counterfactuals, and report summaries.  Artifact alignment, strict-train
support indexing, and token-matrix validation remain in
``act_regression_offline_diagnostic``.
"""

from __future__ import annotations

import hashlib
import math
import pickle
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.camera_images import read_camera_rgb
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.act_regression_offline_diagnostic import (
    _CAMERA_ORDER,
    _SUPPORT_FEATURE_ORDER,
    EVIDENCE_SCOPE,
    SCHEMA,
    _float_list,
    _sha256,
    build_train_expert_index,
    classify_temporal_replay_frame,
    join_rollout_action_frames,
    load_token_variant_matrix,
    nearest_expert_action,
    temporal_contributors,
    write_json_exclusive,
)


def run_recorded_observation_diagnosis(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    eval_config_path: str | Path,
    dig_checkpoint_path: str | Path,
    dig_stats_path: str | Path,
    train_dataset_dir: str | Path,
    train_split_path: str | Path,
    token_variants_artifact_path: str | Path,
    output_path: str | Path,
    device: str = "cuda",
) -> dict[str, Any]:
    """Replay one saved cycle-one dig stream without making a live claim."""

    destination = Path(output_path)
    config_path = Path(eval_config_path)
    checkpoint_path = Path(dig_checkpoint_path)
    stats_path = Path(dig_stats_path)
    expected_stats_path = checkpoint_path.parent / "dataset_stats.pkl"
    if stats_path.resolve() != expected_stats_path.resolve():
        raise ValueError(
            "dig_stats_path must be the exact dataset_stats.pkl loaded beside "
            f"the checkpoint: expected={expected_stats_path}"
        )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    policy_cfg = dict(config.get("policy", {}) or {})
    task_cfg = dict(config.get("task", {}) or {})
    configured_checkpoint = Path(
        policy_cfg.get("dig_ckpt_path", checkpoint_path)
    )
    if configured_checkpoint.resolve() != checkpoint_path.resolve():
        raise ValueError(
            "diagnostic checkpoint does not match eval config dig_ckpt_path"
        )
    configured_checkpoint_dir = Path(
        policy_cfg.get("dig_ckpt_dir", checkpoint_path.parent)
    )
    if configured_checkpoint_dir.resolve() != checkpoint_path.parent.resolve():
        raise ValueError(
            "diagnostic checkpoint directory does not match eval config"
        )
    camera_names = list(task_cfg.get("camera_names", []))
    if camera_names != list(_CAMERA_ORDER):
        raise ValueError(
            "strict regression diagnosis requires the locked four-camera order"
        )
    low_dim_keys = list(policy_cfg.get("dig_low_dim_keys", []))
    if low_dim_keys != ["qpos", "qvel", "dig_cut_tokens"]:
        raise ValueError(
            "strict regression diagnosis has unexpected dig low-dim keys"
        )
    act_params = dict(policy_cfg.get("act_params", {}) or {})
    temporal_window = int(act_params.get("temporal_agg_window", -1))
    temporal_weight_order = str(
        act_params.get("temporal_agg_weight_order", "")
    )
    temporal_decay = float(
        act_params.get("temporal_agg_decay", float("nan"))
    )
    if (
        temporal_window not in {20, 100}
        or temporal_weight_order
        != "legacy_oldest_first"
        or not math.isclose(
            temporal_decay,
            0.01,
            abs_tol=1.0e-12,
        )
    ):
        raise ValueError(
            "offline diagnosis requires locked A0/A1 temporal aggregation"
        )

    frames = join_rollout_action_frames(
        rollout_hdf5_path=rollout_hdf5_path,
        rollout_jsonl_path=rollout_jsonl_path,
        cycle_index=1,
        skill_name="dig",
    )
    token_matrix = load_token_variant_matrix(
        token_variants_artifact_path,
        recorded_tokens=[frame["dig_cut_tokens"] for frame in frames],
    )
    normalized_variants = token_matrix["tokens"]
    expert_index = build_train_expert_index(
        dataset_dir=train_dataset_dir,
        split_path=train_split_path,
    )
    with stats_path.open("rb") as handle:
        stats = pickle.load(handle)
    proprio_mean = np.asarray(
        stats["proprio_mean"],
        dtype=np.float32,
    ).reshape(-1)
    proprio_std = np.asarray(
        stats["proprio_std"],
        dtype=np.float32,
    ).reshape(-1)
    if proprio_mean.shape != (18,) or proprio_std.shape != (18,):
        raise ValueError(
            "dig dataset stats must contain 18D proprio normalization"
        )

    from testbed.runtime._eval import (
        _build_act_eval_policy,
        _configure_eval_torch_performance,
    )

    resolved_performance = _configure_eval_torch_performance(
        dict(config.get("eval", {}) or {}),
        device=str(device),
    )
    policy = _build_act_eval_policy(
        config=config,
        ckpt_path=checkpoint_path,
        ckpt_dir=stats_path.parent,
        camera_names=camera_names,
        equipment_model=str(task_cfg.get("equipment_model", "yulong")),
        max_episode_len=int(task_cfg.get("episode_len", 24000)),
        low_dim_keys=low_dim_keys,
        temporal_agg=True,
        device=str(device),
        act_params=act_params,
        outcome_head_config=dict(
            policy_cfg.get("dig_outcome_head", {}) or {}
        ),
        image_mask_config=dict(policy_cfg.get("image_mask", {}) or {}),
    )
    policy.reset()

    train_features = np.asarray(expert_index["feature"], dtype=np.float32)
    train_p01 = np.percentile(train_features, 1, axis=0)
    train_p99 = np.percentile(train_features, 99, axis=0)
    train_mean = np.mean(train_features, axis=0)
    train_std = np.std(train_features, axis=0)
    records: list[dict[str, Any]] = []
    replay_policy_call_index = 0
    replay_segment_index = 0
    reset_before_next_policy_call = True
    previous_policy_dig_step: int | None = None
    with h5py.File(rollout_hdf5_path, "r") as handle:
        for local_step, frame in enumerate(frames):
            observation_index = int(frame["observation_hdf5_index"])
            env_state = np.asarray(frame["env_state"], dtype=np.float32)
            obs = {
                "qpos": np.asarray(frame["qpos"], dtype=np.float32),
                "qvel": np.asarray(frame["qvel"], dtype=np.float32),
                "dig_cut_tokens": np.asarray(
                    frame["dig_cut_tokens"],
                    dtype=np.float32,
                ),
            }
            camera_sha: dict[str, str] = {}
            for camera_name in camera_names:
                image = read_camera_rgb(
                    handle,
                    camera_name,
                    observation_index,
                )
                obs[f"image_{camera_name}"] = image
                camera_sha[camera_name] = hashlib.sha256(
                    np.ascontiguousarray(image).tobytes()
                ).hexdigest()

            fresh_action, _ = policy.predict_with_outcome(obs)
            variant_actions: dict[str, list[float]] = {}
            for condition_id, token in normalized_variants.items():
                variant_obs = dict(obs)
                variant_obs["dig_cut_tokens"] = np.asarray(
                    token,
                    dtype=np.float32,
                )
                variant_action, _ = policy.predict_with_outcome(variant_obs)
                variant_actions[condition_id] = _float_list(variant_action)

            act_execution = classify_temporal_replay_frame(frame)
            if act_execution["reset_before_next_policy_call"]:
                reset_before_next_policy_call = True
                previous_policy_dig_step = None
            aggregated_action: np.ndarray | None = None
            contributor_evidence: dict[str, Any] | None = None
            if bool(act_execution["policy_called"]):
                dig_step_count = int(frame["dig_step_count"])
                if (
                    reset_before_next_policy_call
                    or act_execution["reset_before_policy_call"]
                ):
                    policy.reset()
                    replay_policy_call_index = 0
                    replay_segment_index += 1
                    reset_before_next_policy_call = False
                if (
                    previous_policy_dig_step is not None
                    and dig_step_count != previous_policy_dig_step + 1
                ):
                    raise ValueError(
                        "dig temporal replay clock is discontinuous: "
                        f"previous={previous_policy_dig_step}, "
                        f"current={dig_step_count}, "
                        f"step_id={frame['action_step_id']}"
                    )
                aggregated_action = np.asarray(
                    policy.predict(obs),
                    dtype=np.float32,
                )
                contributor_evidence = temporal_contributors(
                    local_step=replay_policy_call_index,
                    window=temporal_window,
                    weight_order=temporal_weight_order,
                    decay=temporal_decay,
                )
                act_execution = {
                    **act_execution,
                    "temporal_replay_available": True,
                    "temporal_replay_segment_index": replay_segment_index,
                    "temporal_policy_call_index": replay_policy_call_index,
                }
                replay_policy_call_index += 1
                previous_policy_dig_step = dig_step_count
            else:
                act_execution = {
                    **act_execution,
                    "temporal_replay_available": False,
                    "temporal_replay_segment_index": replay_segment_index,
                    "temporal_policy_call_index": None,
                }

            support_feature = _support_feature_vector(
                qpos=obs["qpos"],
                qvel=obs["qvel"],
                env_state=env_state,
                dig_cut_tokens=obs["dig_cut_tokens"],
            )
            nearest = nearest_expert_action(
                expert_index,
                proprio=support_feature,
                mean=train_mean,
                std=train_std,
            )
            actual = np.asarray(frame["actual_action"], dtype=np.float32)
            expert = np.asarray(nearest["action"], dtype=np.float32)
            violations = _support_violations(
                support_feature,
                lower=train_p01,
                upper=train_p99,
            )
            post_env = np.asarray(frame["post_env_state"], dtype=np.float32)
            typed_contact = _typed_contact_evidence(post_env)
            comparison: dict[str, Any] = {
                "actual_action_is_raw_policy_dispatch": bool(
                    act_execution["policy_called"]
                ),
                "fresh_minus_actual": _float_list(fresh_action - actual),
                "fresh_minus_expert": _float_list(fresh_action - expert),
                "actual_minus_expert": _float_list(actual - expert),
                "fresh_expert_sign_agreement": _sign_agreement(
                    fresh_action,
                    expert,
                ),
            }
            if aggregated_action is not None:
                comparison.update(
                    {
                        "aggregated_minus_actual": _float_list(
                            aggregated_action - actual
                        ),
                        "aggregated_minus_expert": _float_list(
                            aggregated_action - expert
                        ),
                        "fresh_minus_aggregated": _float_list(
                            fresh_action - aggregated_action
                        ),
                        "aggregated_expert_sign_agreement": _sign_agreement(
                            aggregated_action,
                            expert,
                        ),
                    }
                )
            records.append(
                {
                    "local_dig_step": int(local_step),
                    "dig_step_count": int(frame["dig_step_count"]),
                    "action_step_id": int(frame["action_step_id"]),
                    "observation_step_id": int(frame["observation_step_id"]),
                    "camera_sha256": camera_sha,
                    "qpos": _float_list(obs["qpos"]),
                    "qvel": _float_list(obs["qvel"]),
                    "dig_cut_tokens": _float_list(obs["dig_cut_tokens"]),
                    "actual_action": _float_list(actual),
                    "fresh_action": _float_list(fresh_action),
                    "aggregated_action": (
                        None
                        if aggregated_action is None
                        else _float_list(aggregated_action)
                    ),
                    "token_counterfactual_fresh_actions": variant_actions,
                    "nearest_train_expert": nearest,
                    "action_comparison": comparison,
                    "act_execution": act_execution,
                    "support": {
                        "p01_p99_in_support": not violations,
                        "violations": violations,
                        "normalized_distance_to_nearest_train": float(
                            nearest["distance"]
                        ),
                    },
                    "support_feature": _float_list(support_feature),
                    "temporal_contributors": contributor_evidence,
                    "carry_start_base_ready": bool(
                        frame["carry_start_base_ready"]
                    ),
                    "carry_start_envelope_ready": bool(
                        frame["carry_start_envelope_ready"]
                    ),
                    "carry_start_envelope_hold_count": int(
                        frame["carry_start_envelope_hold_count"]
                    ),
                    "carry_start_envelope_violations": list(
                        frame["carry_start_envelope_violations"]
                    ),
                    "state_diagnostics": {
                        "bucket_tip_dig_area_pose_m": _float_list(
                            env_state[
                                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
                                ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX + 1
                            ]
                        ),
                        "bucket_depth_below_dig_area_plane_m": float(
                            env_state[
                                ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
                            ]
                        ),
                        "bucket_depth_below_local_surface_m": float(
                            env_state[
                                ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX
                            ]
                        ),
                        "terrain_surface_depth_m": _float_list(
                            env_state[
                                ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
                                ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
                            ]
                        ),
                    },
                    "typed_contact_post_action": typed_contact,
                    "pre_action_safety_reason": str(
                        frame["pre_action_safety_reason"]
                    ),
                    "safety_runtime": {
                        "stuck": str(
                            frame["pre_action_safety_reason"]
                        ).startswith("stuck"),
                        "timeout": bool(frame["transition_timeout"])
                        or str(
                            frame["pre_action_safety_reason"]
                        ).endswith("_timeout"),
                        "terminal": bool(frame["box_safety_terminal"]),
                        "neutral_acknowledged": bool(
                            frame["box_safety_neutral_acknowledged"]
                        ),
                        "bounded_probe_neutral_acknowledged": bool(
                            frame["bounded_probe_neutral_acknowledged"]
                        ),
                        "bounded_probe_terminal_requested": bool(
                            frame["bounded_probe_terminal_requested"]
                        ),
                    },
                }
            )

    result = {
        "schema": SCHEMA,
        "status": "present",
        "evidence_scope": EVIDENCE_SCOPE,
        "closed_loop_claim": False,
        "promotion_eligible": False,
        "rollout": {
            "hdf5_path": str(Path(rollout_hdf5_path).resolve()),
            "hdf5_sha256": _sha256(Path(rollout_hdf5_path)),
            "jsonl_path": str(Path(rollout_jsonl_path).resolve()),
            "jsonl_sha256": _sha256(Path(rollout_jsonl_path)),
            "cycle_index": 1,
            "skill_name": "dig",
        },
        "policy_contract": {
            "eval_config_path": str(config_path.resolve()),
            "eval_config_sha256": _sha256(config_path),
            "checkpoint_path": str(checkpoint_path.resolve()),
            "checkpoint_sha256": _sha256(checkpoint_path),
            "stats_path": str(stats_path.resolve()),
            "stats_sha256": _sha256(stats_path),
            "camera_names": camera_names,
            "low_dim_keys": low_dim_keys,
            "temporal_agg_window": temporal_window,
            "temporal_agg_weight_order": temporal_weight_order,
            "temporal_agg_decay": temporal_decay,
            "torch_performance": resolved_performance.as_config_dict(),
            "unity_lineage": {
                key: value
                for key, value in dict(
                    config.get("eval", {}).get(
                        "record_hdf5_metadata",
                        {},
                    )
                    or {}
                ).items()
                if str(key).startswith("unity_")
            },
        },
        "train_support": {
            "dataset_dir": str(Path(train_dataset_dir).resolve()),
            "split_path": str(Path(train_split_path).resolve()),
            "split_sha256": _sha256(Path(train_split_path)),
            "sample_count": int(train_features.shape[0]),
            "total_step_count": int(expert_index["total_step_count"]),
            "masked_step_count": int(expert_index["masked_step_count"]),
            "action_loss_mask_scope": "loss_sampling_stats",
            "train_source_episode_ids": list(
                expert_index["train_source_episode_ids"]
            ),
            "validation_source_episode_ids_excluded": list(
                expert_index["validation_source_episode_ids"]
            ),
            "feature_order": list(_SUPPORT_FEATURE_ORDER),
            "feature_p01": _float_list(train_p01),
            "feature_p99": _float_list(train_p99),
        },
        "token_variant_matrix": token_matrix,
        "records": records,
        "summary": summarize_records(records),
        "handoff_shadow": _handoff_shadow(records),
        "diagnostic_limits": {
            "nearest_expert_kind": "numeric_train_only_nearest_neighbor",
            "nearest_expert_scaling": "train_empirical_zscore",
            "counterfactual_resimulated": False,
            "live_gate_changed": False,
            "temporal_replay_requires_policy_called_evidence": True,
        },
    }
    write_json_exclusive(destination, result)
    return result


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize only frames for which the dig ACT temporal call is known."""

    if not records:
        return {"count": 0}
    policy_records = [
        record
        for record in records
        if bool(record.get("act_execution", {}).get("policy_called", False))
        and record.get("aggregated_action") is not None
    ]
    if not policy_records:
        raise ValueError(
            "no raw-policy-dispatched frames available for summary"
        )
    actual = np.asarray(
        [record["actual_action"] for record in policy_records],
        dtype=np.float32,
    )
    fresh = np.asarray(
        [record["fresh_action"] for record in policy_records],
        dtype=np.float32,
    )
    aggregated = np.asarray(
        [record["aggregated_action"] for record in policy_records],
        dtype=np.float32,
    )
    expert = np.asarray(
        [
            record["nearest_train_expert"]["action"]
            for record in policy_records
        ],
        dtype=np.float32,
    )
    wall_steps = [
        int(record["action_step_id"])
        for record in records
        if bool(record["typed_contact_post_action"]["wall_mask"])
        or str(record["pre_action_safety_reason"]).startswith("wall_contact")
    ]
    bottom_steps = [
        int(record["action_step_id"])
        for record in records
        if bool(record["typed_contact_post_action"]["bottom_mask"])
    ]
    first_wall_step = None if not wall_steps else min(wall_steps)
    prewall_records = [
        record
        for record in policy_records
        if first_wall_step is None
        or int(record["action_step_id"]) < first_wall_step
    ]
    return {
        "count": int(len(records)),
        "raw_policy_dispatched_count": int(len(policy_records)),
        "policy_bypassed_count": int(len(records) - len(policy_records)),
        "first_action_step_id": int(records[0]["action_step_id"]),
        "last_action_step_id": int(records[-1]["action_step_id"]),
        "fresh_vs_actual_mae": _float_list(
            np.mean(np.abs(fresh - actual), axis=0)
        ),
        "aggregated_vs_actual_mae": _float_list(
            np.mean(np.abs(aggregated - actual), axis=0)
        ),
        "fresh_vs_nearest_expert_mae": _float_list(
            np.mean(np.abs(fresh - expert), axis=0)
        ),
        "aggregated_vs_nearest_expert_mae": _float_list(
            np.mean(np.abs(aggregated - expert), axis=0)
        ),
        "actual_vs_nearest_expert_mae": _float_list(
            np.mean(np.abs(actual - expert), axis=0)
        ),
        "fresh_vs_aggregated_mae": _float_list(
            np.mean(np.abs(fresh - aggregated), axis=0)
        ),
        "numeric_support_ood_count": int(
            sum(
                not record["support"]["p01_p99_in_support"]
                for record in policy_records
            )
        ),
        "first_base_ready_step_id": _first_step(
            records,
            "carry_start_base_ready",
        ),
        "first_envelope_ready_step_id": _first_step(
            records,
            "carry_start_envelope_ready",
        ),
        "first_wall_step_id": first_wall_step,
        "first_bottom_step_id": None if not bottom_steps else min(bottom_steps),
        "prewall_frame_count": int(len(prewall_records)),
        "prewall_last_10": _window_summary(prewall_records[-10:]),
        "prewall_last_250": _window_summary(prewall_records[-250:]),
        "early_first_10": _window_summary(policy_records[:10]),
    }


def _support_violations(
    feature: np.ndarray,
    *,
    lower: np.ndarray,
    upper: np.ndarray,
) -> list[dict[str, Any]]:
    if len(_SUPPORT_FEATURE_ORDER) != int(np.asarray(feature).size):
        raise ValueError(
            "support feature names do not match feature dimension"
        )
    violations: list[dict[str, Any]] = []
    for index, (value, low, high) in enumerate(
        zip(feature, lower, upper, strict=True)
    ):
        if value < low:
            violations.append(
                {
                    "field": _SUPPORT_FEATURE_ORDER[index],
                    "kind": "below_p01",
                    "value": float(value),
                    "bound": float(low),
                }
            )
        elif value > high:
            violations.append(
                {
                    "field": _SUPPORT_FEATURE_ORDER[index],
                    "kind": "above_p99",
                    "value": float(value),
                    "bound": float(high),
                }
            )
    return violations


def _sign_agreement(
    left: Any,
    right: Any,
    *,
    epsilon: float = 1.0e-4,
) -> float:
    left_arr = np.asarray(left, dtype=np.float32).reshape(-1)
    right_arr = np.asarray(right, dtype=np.float32).reshape(-1)
    if left_arr.shape != right_arr.shape:
        raise ValueError("sign agreement vectors do not match")
    left_sign = np.where(
        np.abs(left_arr) <= epsilon,
        0,
        np.sign(left_arr),
    )
    right_sign = np.where(
        np.abs(right_arr) <= epsilon,
        0,
        np.sign(right_arr),
    )
    return float(np.mean(left_sign == right_sign))


def _window_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    actual = np.asarray([record["actual_action"] for record in records])
    fresh = np.asarray([record["fresh_action"] for record in records])
    aggregated = np.asarray(
        [record["aggregated_action"] for record in records]
    )
    expert = np.asarray(
        [record["nearest_train_expert"]["action"] for record in records]
    )
    return {
        "count": int(len(records)),
        "first_action_step_id": int(records[0]["action_step_id"]),
        "last_action_step_id": int(records[-1]["action_step_id"]),
        "actual_mean": _float_list(np.mean(actual, axis=0)),
        "fresh_mean": _float_list(np.mean(fresh, axis=0)),
        "aggregated_mean": _float_list(np.mean(aggregated, axis=0)),
        "nearest_expert_mean": _float_list(np.mean(expert, axis=0)),
        "fresh_minus_aggregated_mean": _float_list(
            np.mean(fresh - aggregated, axis=0)
        ),
        "aggregated_minus_expert_mean": _float_list(
            np.mean(aggregated - expert, axis=0)
        ),
    }


def _first_step(
    records: list[dict[str, Any]],
    key: str,
) -> int | None:
    for record in records:
        if bool(record[key]):
            return int(record["action_step_id"])
    return None


def _handoff_shadow(records: list[dict[str, Any]]) -> dict[str, Any]:
    base_steps = [
        int(record["action_step_id"])
        for record in records
        if bool(record["carry_start_base_ready"])
    ]
    envelope_steps = [
        int(record["action_step_id"])
        for record in records
        if bool(record["carry_start_envelope_ready"])
    ]
    wall_steps = [
        int(record["action_step_id"])
        for record in records
        if bool(record["typed_contact_post_action"]["wall_mask"])
        or str(record["pre_action_safety_reason"]).startswith("wall_contact")
    ]
    first_base = min(base_steps) if base_steps else None
    first_wall = min(wall_steps) if wall_steps else None
    return {
        "mode": "observe_only",
        "live_gate_changed": False,
        "first_base_ready_step_id": first_base,
        "first_envelope_ready_step_id": (
            min(envelope_steps) if envelope_steps else None
        ),
        "first_wall_step_id": first_wall,
        "base_ready_before_wall": bool(
            first_base is not None
            and first_wall is not None
            and first_base < first_wall
        ),
        "counterfactual_not_resimulated": True,
        "causal_claim": False,
    }


def _support_feature_vector(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    env_state: np.ndarray,
    dig_cut_tokens: np.ndarray,
) -> np.ndarray:
    return np.concatenate(
        [
            np.asarray(qpos, dtype=np.float32).reshape(4),
            np.asarray(qvel, dtype=np.float32).reshape(4),
            np.asarray(
                env_state[
                    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
                    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX + 1
                ],
                dtype=np.float32,
            ),
            np.asarray(
                env_state[
                    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
                    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
                ],
                dtype=np.float32,
            ),
            np.asarray(dig_cut_tokens, dtype=np.float32).reshape(10),
        ]
    )


def _typed_contact_evidence(post_env: np.ndarray) -> dict[str, Any]:
    env = np.asarray(post_env, dtype=np.float32).reshape(-1)
    if env.size < ENV_STATE_V2_4_DIM:
        raise ValueError(
            "typed contact diagnosis requires 107D post-action env_state"
        )
    values = {
        "wall_mask": bool(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] >= 0.5
        ),
        "wall_force_n": float(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX]
        ),
        "wall_session_count": float(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX]
        ),
        "bottom_mask": bool(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX] >= 0.5
        ),
        "bottom_force_n": float(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX]
        ),
        "bottom_session_count": float(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX]
        ),
    }
    numeric = np.asarray(
        [
            values["wall_force_n"],
            values["wall_session_count"],
            values["bottom_force_n"],
            values["bottom_session_count"],
        ],
        dtype=np.float64,
    )
    if not np.isfinite(numeric).all() or np.any(numeric < 0.0):
        raise ValueError(
            "typed contact force/session values must be finite nonnegative"
        )
    for name in ("wall_session_count", "bottom_session_count"):
        value = float(values[name])
        if not value.is_integer():
            raise ValueError(f"typed contact {name} must be integral")
        values[name] = int(value)
    return values


__all__ = [
    "run_recorded_observation_diagnosis",
    "summarize_records",
]
