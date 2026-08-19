"""Teacher-forced ACT comparison for exact and cell-level return tokens."""

from __future__ import annotations

import gc
import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.camera_images import read_camera_rgb
from testbed.policies.act.inference import (
    build_act_adapter_config,
    load_act_policy,
)

COVERAGE_RETURN_TOKEN_POLICY_REPLAY_SCHEMA = "coverage_return_token_policy_replay_v1"
CAMERA_ORDER = ("stick_up", "stick_down", "eye_left", "eye_right")


def run_teacher_forced_return_replay(
    *,
    original_config: Mapping[str, Any],
    original_config_path: Path,
    replay_inputs: Sequence[Mapping[str, Any]],
    exact_token: np.ndarray,
    device: str,
) -> dict[str, Any]:
    """Replay two tokens with independently constructed temporal state."""

    policy_config = _mapping(
        original_config.get("policy"),
        label="policy config",
    )
    task_config = _mapping(
        original_config.get("task"),
        label="task config",
    )
    camera_names = list(task_config.get("camera_names", ()))
    if camera_names != list(CAMERA_ORDER):
        raise ValueError("teacher-forced return replay camera order changed")
    low_dim_keys = list(policy_config.get("return_low_dim_keys", ()))
    if low_dim_keys != [
        "qpos",
        "qvel",
        "return_start_envelope_tokens_v1",
    ]:
        raise ValueError("teacher-forced return low-dimensional contract changed")
    act_params = _mapping(
        policy_config.get("act_params"),
        label="ACT parameters",
    )
    if (
        int(act_params.get("temporal_agg_window", -1)) != 100
        or str(act_params.get("temporal_agg_weight_order", "")) != "legacy_oldest_first"
        or not math.isclose(
            float(act_params.get("temporal_agg_decay", float("nan"))),
            0.01,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        raise ValueError("teacher-forced return replay requires locked A0")
    checkpoint = _require_file(policy_config["return_ckpt_path"])
    stats = _require_file(checkpoint.parent / "dataset_stats.pkl")

    from testbed.runtime._eval import _configure_eval_torch_performance

    _configure_eval_torch_performance(
        dict(original_config.get("eval", {}) or {}),
        device=str(device),
    )

    adapter_config = build_act_adapter_config(
        config=dict(original_config),
        camera_names=camera_names,
        equipment_model=str(task_config.get("equipment_model", "yulong")),
        max_episode_len=int(task_config.get("episode_len", 24000)),
        low_dim_keys=low_dim_keys,
        act_params=dict(act_params),
        outcome_head_config=dict(
            policy_config.get("return_outcome_head", {}) or {}
        ),
        image_mask_config=dict(policy_config.get("image_mask", {}) or {}),
    )

    def build_policy() -> Any:
        return load_act_policy(
            ckpt_path=checkpoint,
            policy_config=adapter_config,
            norm_stats_path=stats,
            temporal_agg=True,
            device=str(device),
        )

    condition_results: dict[str, Any] = {}
    for condition_index, condition_id in enumerate(
        ("recorded_cell_token", "paired_exact_token")
    ):
        policy = build_policy()
        per_rollout: list[dict[str, Any]] = []
        all_l1_to_recorded: list[float] = []
        for replay in replay_inputs:
            policy.reset()
            action_steps = [int(value) for value in replay["return_action_steps"]]
            anchors = {
                0,
                len(action_steps) // 2,
                len(action_steps) - 1,
            }
            token = (
                np.asarray(replay["old_token"], dtype=np.float32)
                if condition_id == "recorded_cell_token"
                else np.asarray(exact_token, dtype=np.float32)
            )
            records: list[dict[str, Any]] = []
            with h5py.File(replay["hdf5_path"], "r") as handle:
                step_ids = np.asarray(
                    handle["timestamps/step_id"],
                    dtype=np.int64,
                )
                index_by_step = {
                    int(step_id): int(index) for index, step_id in enumerate(step_ids)
                }
                for frame_index, action_step in enumerate(action_steps):
                    action_index = index_by_step[action_step]
                    if action_index <= 0:
                        raise ValueError("return action lacks pre-action observation")
                    observation_index = action_index - 1
                    obs = {
                        "qpos": np.asarray(
                            handle["observations/qpos"][observation_index],
                            dtype=np.float32,
                        ),
                        "qvel": np.asarray(
                            handle["observations/qvel"][observation_index],
                            dtype=np.float32,
                        ),
                        "return_start_envelope_tokens_v1": token.copy(),
                    }
                    for camera_name in camera_names:
                        obs[f"image_{camera_name}"] = read_camera_rgb(
                            handle,
                            camera_name,
                            observation_index,
                        )
                    fresh_action = None
                    if frame_index in anchors:
                        fresh_action, _ = policy.predict_with_outcome(obs)
                    aggregated = np.asarray(
                        policy.predict(obs),
                        dtype=np.float32,
                    )
                    recorded = np.asarray(
                        replay["recorded_actions"][action_step],
                        dtype=np.float32,
                    )
                    l1 = float(np.sum(np.abs(aggregated - recorded)))
                    all_l1_to_recorded.append(l1)
                    records.append(
                        {
                            "frame_index": int(frame_index),
                            "action_step_id": int(action_step),
                            "observation_step_id": int(step_ids[observation_index]),
                            "aggregated_action": _float_list(aggregated),
                            "recorded_action": _float_list(recorded),
                            "aggregated_l1_to_recorded": l1,
                            "fresh_action": (
                                None
                                if fresh_action is None
                                else _float_list(fresh_action)
                            ),
                        }
                    )
            per_rollout.append(
                {
                    "rollout_id": int(replay["rollout_id"]),
                    "policy_reset_before_segment": True,
                    "temporal_contributor_count_before_segment": 0,
                    "frame_count": len(records),
                    "records": records,
                }
            )
        condition_results[condition_id] = {
            "state_id": (
                f"{COVERAGE_RETURN_TOKEN_POLICY_REPLAY_SCHEMA}/"
                f"{condition_id}/instance_{condition_index}"
            ),
            "token_source": condition_id,
            "shared_temporal_state_with_other_condition": False,
            "rollouts": per_rollout,
            "mean_aggregated_l1_to_recorded": float(np.mean(all_l1_to_recorded)),
        }
        del policy
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    return {
        "schema": COVERAGE_RETURN_TOKEN_POLICY_REPLAY_SCHEMA,
        "status": "completed",
        "evidence_kind": "teacher_forced_recorded_observation",
        "closed_loop_claim": False,
        "promotion_eligible": False,
        "original_eval_config": _source_record(original_config_path),
        "return_checkpoint": _source_record(checkpoint),
        "return_stats": _source_record(stats),
        "camera_order": list(CAMERA_ORDER),
        "low_dim_keys": low_dim_keys,
        "temporal_aggregation": {
            "window": 100,
            "weight_order": "legacy_oldest_first",
            "decay": 0.01,
        },
        "independent_temporal_state": True,
        "conditions": condition_results,
        "cross_condition": _cross_condition(condition_results),
    }


def _cross_condition(
    condition_results: Mapping[str, Any],
) -> list[dict[str, Any]]:
    cross: list[dict[str, Any]] = []
    old_rollouts = condition_results["recorded_cell_token"]["rollouts"]
    exact_rollouts = condition_results["paired_exact_token"]["rollouts"]
    for old, exact in zip(old_rollouts, exact_rollouts, strict=True):
        action_l1: list[float] = []
        sign_disagreements = 0
        axis_count = 0
        anchors: list[dict[str, Any]] = []
        for old_record, exact_record in zip(
            old["records"],
            exact["records"],
            strict=True,
        ):
            old_action = np.asarray(
                old_record["aggregated_action"],
                dtype=np.float64,
            )
            exact_action = np.asarray(
                exact_record["aggregated_action"],
                dtype=np.float64,
            )
            action_l1.append(float(np.sum(np.abs(old_action - exact_action))))
            sign_disagreements += int(
                np.sum(np.sign(old_action) != np.sign(exact_action))
            )
            axis_count += int(old_action.size)
            if old_record["fresh_action"] is not None:
                anchors.append(
                    {
                        "action_step_id": int(old_record["action_step_id"]),
                        "recorded_cell_fresh_action": list(old_record["fresh_action"]),
                        "paired_exact_fresh_action": list(exact_record["fresh_action"]),
                    }
                )
        cross.append(
            {
                "rollout_id": int(old["rollout_id"]),
                "mean_aggregated_action_l1_delta": float(np.mean(action_l1)),
                "max_aggregated_action_l1_delta": float(np.max(action_l1)),
                "axis_sign_disagreement_fraction": float(
                    sign_disagreements / max(axis_count, 1)
                ),
                "anchor_fresh_actions": anchors,
            }
        )
    return cross


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


def _require_file(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _float_list(values: Any) -> list[float]:
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.all(np.isfinite(array)):
        raise ValueError("policy replay values must be finite")
    return [float(value) for value in array]


__all__ = [
    "CAMERA_ORDER",
    "COVERAGE_RETURN_TOKEN_POLICY_REPLAY_SCHEMA",
    "run_teacher_forced_return_replay",
]
