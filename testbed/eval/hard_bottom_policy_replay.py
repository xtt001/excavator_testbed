"""Independent ACT policy replay for hard-bottom goal counterfactuals."""

from __future__ import annotations

import gc
import hashlib
import json
import math
import weakref
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import h5py
import numpy as np
import yaml

from testbed.data.camera_images import read_camera_rgb
from testbed.eval.act_regression_offline_diagnostic import (
    join_rollout_action_frames,
)
from testbed.eval.hard_bottom_goal_comparison import (
    SCHEMA as GOAL_COMPARISON_SCHEMA,
)
from testbed.eval.hard_bottom_goal_comparison import (
    TARGET_ORDER,
    _through_first_bottom_contact,
)

HARD_BOTTOM_POLICY_REPLAY_SCHEMA = "hard_bottom_goal_policy_replay_v1"
EVIDENCE_SCOPE = "teacher_forced_recorded_observation"
MANIFEST_FILENAME = "manifest.json"
CAMERA_ORDER = ("stick_up", "stick_down", "eye_left", "eye_right")


class GoalReplayPolicy(Protocol):
    """Small ACT interface required by the independent replay."""

    def reset(self) -> None: ...

    def predict_with_outcome(
        self,
        obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray | None]: ...

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray: ...


def replay_independent_goal_policy_actions(
    *,
    frames: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, Any]],
    nearest_expert_actions: Mapping[str, Mapping[int, Sequence[float]]],
    policy_factory: Callable[[str], GoalReplayPolicy],
    observation_images: Callable[
        [Mapping[str, Any]],
        Mapping[str, np.ndarray],
    ],
    branch_cleanup: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Replay each target with a separately constructed, reset ACT instance."""

    if not frames:
        raise ValueError("policy replay frames must not be empty")
    if tuple(targets) != TARGET_ORDER:
        raise ValueError(
            f"policy replay target order must be {TARGET_ORDER!r}"
        )
    prior_policy_refs: list[weakref.ReferenceType[object]] = []
    target_results: dict[str, Any] = {}
    for branch_index, target_id in enumerate(TARGET_ORDER):
        target = targets[target_id]
        token = np.asarray(
            target.get("dig_cut_tokens", []),
            dtype=np.float32,
        )
        if token.shape != (10,) or not np.isfinite(token).all():
            raise ValueError(f"{target_id} dig_cut_tokens must be finite 10D")
        policy = policy_factory(target_id)
        if any(reference() is policy for reference in prior_policy_refs):
            raise ValueError(
                "each goal branch requires a distinct policy instance"
            )
        prior_policy_refs.append(weakref.ref(policy))
        policy.reset()

        records: list[dict[str, Any]] = []
        for frame_index, frame in enumerate(frames):
            step_id = int(frame["action_step_id"])
            target_experts = nearest_expert_actions.get(target_id, {})
            if step_id not in target_experts:
                raise ValueError(
                    f"{target_id} lacks nearest-expert action at step {step_id}"
                )
            obs: dict[str, np.ndarray] = {
                "qpos": _finite_vector(frame.get("qpos"), 4, label="qpos"),
                "qvel": _finite_vector(frame.get("qvel"), 4, label="qvel"),
                "dig_cut_tokens": token.copy(),
            }
            obs.update(
                {
                    str(key): np.asarray(value)
                    for key, value in observation_images(frame).items()
                }
            )
            fresh, _ = policy.predict_with_outcome(obs)
            aggregated = policy.predict(obs)
            fresh_action = _finite_vector(
                fresh,
                4,
                label=f"{target_id} fresh action",
            )
            aggregated_action = _finite_vector(
                aggregated,
                4,
                label=f"{target_id} aggregated action",
            )
            actual_action = _finite_vector(
                frame.get("actual_action"),
                4,
                label="recorded actual action",
            )
            expert_action = _finite_vector(
                target_experts[step_id],
                4,
                label=f"{target_id} nearest-expert action",
            )
            records.append(
                {
                    "frame_index": int(frame_index),
                    "action_step_id": step_id,
                    "observation_step_id": int(
                        frame["observation_step_id"]
                    ),
                    "fresh_action": _float_list(fresh_action),
                    "aggregated_action": _float_list(aggregated_action),
                    "recorded_actual_action": _float_list(actual_action),
                    "nearest_train_expert_action": _float_list(
                        expert_action
                    ),
                    "fresh_minus_expert": _float_list(
                        fresh_action - expert_action
                    ),
                    "aggregated_minus_expert": _float_list(
                        aggregated_action - expert_action
                    ),
                    "fresh_minus_aggregated": _float_list(
                        fresh_action - aggregated_action
                    ),
                }
            )
        target_results[target_id] = {
            "state_id": (
                f"{HARD_BOTTOM_POLICY_REPLAY_SCHEMA}/"
                f"{target_id}/instance_{branch_index}"
            ),
            "reset_before_first_frame": True,
            "initial_temporal_contributor_count": 0,
            "dig_cut_tokens": _float_list(token),
            "records": records,
            "summary": _summarize_records(records),
        }
        del policy
        gc.collect()
        if branch_cleanup is not None:
            branch_cleanup()

    return {
        "schema": HARD_BOTTOM_POLICY_REPLAY_SCHEMA,
        "status": "complete",
        "evidence_scope": EVIDENCE_SCOPE,
        "offline_only": True,
        "closed_loop_claim": False,
        "promotion_eligible": False,
        "target_order": list(TARGET_ORDER),
        "independent_policy_state_contract": {
            "status": "passed",
            "construction": "one_fresh_checkpoint_instance_per_target",
            "execution": "sequential_to_bound_gpu_memory",
            "reset_before_first_frame": True,
            "shared_temporal_buffer": False,
            "branch_count": len(TARGET_ORDER),
        },
        "targets": target_results,
        "cross_target_summary": _cross_target_summary(target_results),
    }


def build_hard_bottom_policy_replay(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    goal_comparison_path: str | Path,
    eval_config_path: str | Path,
    dig_checkpoint_path: str | Path,
    dig_stats_path: str | Path,
    output_dir: str | Path,
    device: str = "cuda",
) -> dict[str, Any]:
    """Load the locked checkpoint and build a no-overwrite replay artifact."""

    paths = {
        "rollout_hdf5": _require_file(rollout_hdf5_path),
        "rollout_jsonl": _require_file(rollout_jsonl_path),
        "goal_comparison": _require_file(goal_comparison_path),
        "eval_config": _require_file(eval_config_path),
        "dig_checkpoint": _require_file(dig_checkpoint_path),
        "dig_stats": _require_file(dig_stats_path),
    }
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"output directory already exists: {destination}")
    comparison = _read_json(paths["goal_comparison"])
    if comparison.get("schema") != GOAL_COMPARISON_SCHEMA:
        raise ValueError("goal comparison schema is invalid")
    if comparison.get("evidence_scope") != EVIDENCE_SCOPE:
        raise ValueError("goal comparison evidence scope is invalid")
    raw_targets = comparison.get("targets")
    if (
        not isinstance(raw_targets, dict)
        or set(raw_targets) != set(TARGET_ORDER)
    ):
        raise ValueError("goal comparison target order is invalid")
    targets = {
        target_id: raw_targets[target_id]
        for target_id in TARGET_ORDER
    }

    config = yaml.safe_load(
        paths["eval_config"].read_text(encoding="utf-8")
    )
    if not isinstance(config, dict):
        raise ValueError("eval config must contain a mapping")
    policy_config = dict(config.get("policy", {}) or {})
    task_config = dict(config.get("task", {}) or {})
    configured_checkpoint = Path(
        policy_config.get("dig_ckpt_path", "")
    ).expanduser()
    if configured_checkpoint.resolve() != paths["dig_checkpoint"]:
        raise ValueError("dig checkpoint disagrees with eval config")
    expected_stats = paths["dig_checkpoint"].parent / "dataset_stats.pkl"
    if paths["dig_stats"] != expected_stats.resolve():
        raise ValueError("dig stats must be dataset_stats.pkl beside checkpoint")
    camera_names = list(task_config.get("camera_names", []))
    if camera_names != list(CAMERA_ORDER):
        raise ValueError("policy replay requires the locked four-camera order")
    low_dim_keys = list(policy_config.get("dig_low_dim_keys", []))
    if low_dim_keys != ["qpos", "qvel", "dig_cut_tokens"]:
        raise ValueError("policy replay dig low-dimensional contract changed")
    act_params = dict(policy_config.get("act_params", {}) or {})
    if (
        int(act_params.get("temporal_agg_window", -1)) != 100
        or str(act_params.get("temporal_agg_weight_order", ""))
        != "legacy_oldest_first"
        or not math.isclose(
            float(act_params.get("temporal_agg_decay", float("nan"))),
            0.01,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        raise ValueError("policy replay requires locked A0 temporal settings")

    cycle_index = int(comparison.get("cycle_index", 5))
    all_frames = join_rollout_action_frames(
        rollout_hdf5_path=paths["rollout_hdf5"],
        rollout_jsonl_path=paths["rollout_jsonl"],
        cycle_index=cycle_index,
        skill_name="dig",
    )
    frames, contact_step_id = _through_first_bottom_contact(all_frames)
    expected_window = comparison.get("recorded_observation_window", {})
    if not isinstance(expected_window, dict):
        raise ValueError("goal comparison recorded window is invalid")
    if (
        len(frames) != int(expected_window.get("frame_count", -1))
        or int(frames[0]["action_step_id"])
        != int(expected_window.get("first_action_step_id", -1))
        or int(frames[-1]["action_step_id"])
        != int(expected_window.get("last_action_step_id", -1))
    ):
        raise ValueError("policy replay window disagrees with goal comparison")
    nearest = _nearest_expert_actions(comparison)

    from testbed.runtime._eval import (
        _build_act_eval_policy,
        _configure_eval_torch_performance,
    )

    resolved_performance = _configure_eval_torch_performance(
        dict(config.get("eval", {}) or {}),
        device=str(device),
    )

    def policy_factory(_target_id: str) -> GoalReplayPolicy:
        return _build_act_eval_policy(
            config=config,
            ckpt_path=paths["dig_checkpoint"],
            ckpt_dir=paths["dig_stats"].parent,
            camera_names=camera_names,
            equipment_model=str(
                task_config.get("equipment_model", "yulong")
            ),
            max_episode_len=int(task_config.get("episode_len", 24000)),
            low_dim_keys=low_dim_keys,
            temporal_agg=True,
            device=str(device),
            act_params=act_params,
            outcome_head_config=dict(
                policy_config.get("dig_outcome_head", {}) or {}
            ),
            image_mask_config=dict(
                policy_config.get("image_mask", {}) or {}
            ),
        )

    def branch_cleanup() -> None:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    with h5py.File(paths["rollout_hdf5"], "r") as handle:

        def observation_images(
            frame: Mapping[str, Any],
        ) -> dict[str, np.ndarray]:
            observation_index = int(frame["observation_hdf5_index"])
            return {
                f"image_{camera_name}": read_camera_rgb(
                    handle,
                    camera_name,
                    observation_index,
                )
                for camera_name in camera_names
            }

        replay = replay_independent_goal_policy_actions(
            frames=frames,
            targets=targets,
            nearest_expert_actions=nearest,
            policy_factory=policy_factory,
            observation_images=observation_images,
            branch_cleanup=branch_cleanup,
        )

    replay.update(
        {
            "cycle_index": cycle_index,
            "recorded_observation_window": {
                "frame_count": len(frames),
                "first_action_step_id": int(
                    frames[0]["action_step_id"]
                ),
                "last_action_step_id": int(frames[-1]["action_step_id"]),
                "first_bottom_contact_action_step_id": contact_step_id,
                "post_contact_clearance_excluded": contact_step_id is not None,
            },
            "policy_contract": {
                "device": str(device),
                "camera_names": camera_names,
                "low_dim_keys": low_dim_keys,
                "temporal_agg_window": 100,
                "temporal_agg_weight_order": "legacy_oldest_first",
                "temporal_agg_decay": 0.01,
                "torch_performance": resolved_performance.as_config_dict(),
            },
            "source_lock": {
                name: _source_record(path)
                for name, path in paths.items()
            },
            "diagnostic_limits": {
                "recorded_observations_are_from_M0_execution": True,
                "counterfactual_observations_resimulated": False,
                "teacher_forced_only": True,
                "closed_loop_claim": False,
            },
        }
    )
    write_policy_replay_artifact(
        output_dir=destination,
        artifact=replay,
    )
    return replay


def write_policy_replay_artifact(
    *,
    output_dir: str | Path,
    artifact: Mapping[str, Any],
) -> Path:
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"output directory already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    output_path = destination / MANIFEST_FILENAME
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(dict(artifact), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path


def _nearest_expert_actions(
    comparison: Mapping[str, Any],
) -> dict[str, dict[int, list[float]]]:
    evidence = comparison.get("train_support_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("status") != "complete":
        raise ValueError("complete train support evidence is required")
    support_targets = evidence.get("targets")
    if not isinstance(support_targets, Mapping):
        raise ValueError("train support targets are invalid")
    result: dict[str, dict[int, list[float]]] = {}
    for target_id in TARGET_ORDER:
        target = support_targets.get(target_id)
        if not isinstance(target, Mapping):
            raise ValueError(f"train support lacks {target_id}")
        records = target.get("records")
        if not isinstance(records, list):
            raise ValueError(f"train support {target_id} records are invalid")
        by_step: dict[int, list[float]] = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise ValueError("train support record must be a mapping")
            nearest = record.get("nearest_train_expert")
            if not isinstance(nearest, Mapping):
                raise ValueError("nearest train expert record is invalid")
            by_step[int(record["action_step_id"])] = _float_list(
                _finite_vector(
                    nearest.get("action"),
                    4,
                    label="nearest train expert action",
                )
            )
        result[target_id] = by_step
    return result


def _summarize_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fresh = np.asarray([record["fresh_action"] for record in records])
    aggregated = np.asarray(
        [record["aggregated_action"] for record in records]
    )
    actual = np.asarray(
        [record["recorded_actual_action"] for record in records]
    )
    expert = np.asarray(
        [record["nearest_train_expert_action"] for record in records]
    )
    return {
        "frame_count": len(records),
        "fresh_mean": _float_list(np.mean(fresh, axis=0)),
        "aggregated_mean": _float_list(np.mean(aggregated, axis=0)),
        "recorded_actual_mean": _float_list(np.mean(actual, axis=0)),
        "nearest_train_expert_mean": _float_list(
            np.mean(expert, axis=0)
        ),
        "fresh_vs_expert_mae": _float_list(
            np.mean(np.abs(fresh - expert), axis=0)
        ),
        "aggregated_vs_expert_mae": _float_list(
            np.mean(np.abs(aggregated - expert), axis=0)
        ),
        "fresh_vs_aggregated_mae": _float_list(
            np.mean(np.abs(fresh - aggregated), axis=0)
        ),
        "fresh_expert_sign_agreement": _sign_agreement(fresh, expert),
        "aggregated_expert_sign_agreement": _sign_agreement(
            aggregated,
            expert,
        ),
    }


def _cross_target_summary(targets: Mapping[str, Any]) -> dict[str, Any]:
    return {
        target_id: targets[target_id]["summary"]
        for target_id in TARGET_ORDER
    }


def _sign_agreement(left: np.ndarray, right: np.ndarray) -> float:
    left_sign = np.sign(np.where(np.abs(left) <= 1.0e-4, 0.0, left))
    right_sign = np.sign(np.where(np.abs(right) <= 1.0e-4, 0.0, right))
    return float(np.mean(left_sign == right_sign))


def _finite_vector(
    values: Any,
    size: int,
    *,
    label: str,
) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32).reshape(-1)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"{label} must be finite {size}D")
    return result


def _float_list(values: Any) -> list[float]:
    return [
        float(value)
        for value in np.asarray(values, dtype=np.float32).reshape(-1)
    ]


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


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": int(path.stat().st_size),
    }


__all__ = [
    "HARD_BOTTOM_POLICY_REPLAY_SCHEMA",
    "build_hard_bottom_policy_replay",
    "replay_independent_goal_policy_actions",
    "write_policy_replay_artifact",
]
