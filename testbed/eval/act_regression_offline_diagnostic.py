"""Recorded-observation diagnostics for strict ACT regression rollouts.

The module owns alignment between post-step rollout storage and the
observation that produced each action.  It also owns the train-only numeric
expert support index used by the diagnostic.  It does not make online planner
decisions and all results remain teacher-forced evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
)

SCHEMA = "act_regression_offline_diagnostic_v1"
EVIDENCE_SCOPE = "teacher_forced_recorded_observation"
PLAN_MATRIX_SCHEMA = "act_regression_plan_matrix_v1"
_SOURCE_EPISODE_RE = re.compile(r"(?:episode_)?(\d+)$")
_FORBIDDEN_STRICT_PATH_MARKERS = ("partial", "layered", "salvage")
_CAMERA_ORDER = ("stick_up", "stick_down", "eye_left", "eye_right")
_TOKEN_VARIANT_IDS = ("F0", "D1", "C1", "DC1")
_SUPPORT_FEATURE_ORDER = (
    *(f"qpos[{index}]" for index in range(4)),
    *(f"qvel[{index}]" for index in range(4)),
    "bucket_tip_dig_area_x_m",
    "bucket_tip_dig_area_y_m",
    "bucket_tip_dig_area_z_m",
    *(
        f"terrain_surface_depth[{index}]"
        for index in range(6)
    ),
    *(f"dig_cut_tokens[{index}]" for index in range(10)),
)


def join_rollout_action_frames(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    cycle_index: int = 1,
    skill_name: str = "dig",
) -> list[dict[str, Any]]:
    """Join action/debug rows to the post-observation that produced the action.

    Eval HDF5 rows store ``post_obs`` together with the action that just
    produced it.  Therefore action row ``i`` must be evaluated from HDF5
    observation row ``i - 1``.  Joining by array position alone is unsafe, so
    both inventories are first matched by backend ``step_id``.
    """

    jsonl_path = Path(rollout_jsonl_path)
    hdf5_path = Path(rollout_hdf5_path)
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("rollout JSONL is empty")
    json_step_ids = [
        _integer(row.get("step_id"), name="JSONL step_id")
        for row in rows
    ]
    if len(json_step_ids) != len(set(json_step_ids)):
        raise ValueError("JSONL step_id inventory contains duplicates")
    if any(
        right <= left
        for left, right in zip(json_step_ids, json_step_ids[1:])
    ):
        raise ValueError("JSONL step_id inventory must be strictly increasing")

    with h5py.File(hdf5_path, "r") as handle:
        step_ids = np.asarray(handle["timestamps/step_id"][:], dtype=np.int64)
        if step_ids.size != len(set(int(value) for value in step_ids)):
            raise ValueError("HDF5 step_id inventory contains duplicates")
        if step_ids.size < 2 or np.any(np.diff(step_ids) <= 0):
            raise ValueError(
                "HDF5 step_id inventory must be strictly increasing"
            )
        hdf5_index = {int(step_id): index for index, step_id in enumerate(step_ids)}
        frames: list[dict[str, Any]] = []
        for row in rows:
            if int(row.get("primitive_cycle_index", -1)) != int(cycle_index):
                continue
            if str(row.get("skill_name", "")) != str(skill_name):
                continue
            action_step_id = _integer(row.get("step_id"), name="JSONL step_id")
            if action_step_id not in hdf5_index:
                raise ValueError(
                    f"JSONL step_id {action_step_id} is missing from HDF5 inventory"
                )
            action_index = hdf5_index[action_step_id]
            if action_index <= 0:
                raise ValueError(
                    f"action step_id {action_step_id} has no recorded pre-action observation"
                )
            observation_index = action_index - 1
            observation_step_id = int(step_ids[observation_index])
            if observation_step_id != action_step_id - 1:
                raise ValueError(
                    "rollout action/pre-observation step ids are not "
                    f"contiguous: action={action_step_id}, "
                    f"observation={observation_step_id}"
                )
            token = np.asarray(row.get("dig_cut_tokens", []), dtype=np.float32)
            if token.shape != (10,) or not np.isfinite(token).all():
                raise ValueError(
                    f"action step_id {action_step_id} has invalid dig_cut_tokens"
                )
            json_action = np.asarray(row.get("action", []), dtype=np.float32)
            hdf5_action = np.asarray(
                handle["action"][action_index],
                dtype=np.float32,
            ).reshape(-1)
            if json_action.shape != (4,) or not np.isfinite(json_action).all():
                raise ValueError(
                    f"action step_id {action_step_id} has invalid JSONL action"
                )
            if hdf5_action.shape != (4,) or not np.isfinite(hdf5_action).all():
                raise ValueError(
                    f"action step_id {action_step_id} has invalid HDF5 action"
                )
            if not np.allclose(
                json_action,
                hdf5_action,
                rtol=0.0,
                atol=1.0e-6,
            ):
                raise ValueError(
                    f"action step_id {action_step_id} JSONL action disagrees "
                    "with HDF5 action"
                )
            frames.append(
                {
                    "action_step_id": int(action_step_id),
                    "action_hdf5_index": int(action_index),
                    "observation_step_id": observation_step_id,
                    "observation_hdf5_index": int(observation_index),
                    "primitive_cycle_index": int(cycle_index),
                    "skill_name": str(skill_name),
                    "dig_step_count": int(row.get("dig_step_count", len(frames))),
                    "qpos": _float_list(handle["observations/qpos"][observation_index]),
                    "qvel": _float_list(handle["observations/qvel"][observation_index]),
                    "env_state": _float_list(
                        handle["observations/env_state"][observation_index]
                    ),
                    "post_env_state": _float_list(
                        handle["observations/env_state"][action_index]
                    ),
                    "dig_cut_tokens": _float_list(token),
                    "actual_action": _float_list(hdf5_action),
                    "carry_start_base_ready": bool(
                        row.get("carry_start_base_ready", False)
                    ),
                    "carry_start_envelope_ready": bool(
                        row.get("carry_start_envelope_ready", False)
                    ),
                    "carry_start_envelope_hold_count": int(
                        row.get("carry_start_envelope_hold_count", 0)
                    ),
                    "carry_start_envelope_violations": list(
                        row.get("carry_start_envelope_violations", []) or []
                    ),
                    "pre_action_safety_reason": str(
                        row.get("box_safety_reason", "")
                    ),
                    "box_safety_terminal": bool(
                        row.get("box_safety_terminal", False)
                    ),
                    "box_safety_neutral_acknowledged": bool(
                        row.get(
                            "box_safety_neutral_acknowledged",
                            False,
                        )
                    ),
                    "box_safety_awaiting_neutral_ack": bool(
                        row.get("box_safety_awaiting_neutral_ack", False)
                    ),
                    "box_safety_clearance_active": bool(
                        row.get("box_safety_clearance_active", False)
                    ),
                    "box_safety_policy_restarted": bool(
                        row.get("box_safety_policy_restarted", False)
                    ),
                    "skill_switch_reason": str(
                        row.get("skill_switch_reason", "")
                    ),
                    "policy_inference_latency_ms": float(
                        row.get("policy_inference_latency_ms", float("nan"))
                    ),
                    "transition_timeout": bool(
                        row.get("transition_timeout", False)
                    ),
                    "bounded_probe_neutral_acknowledged": bool(
                        row.get(
                            "bounded_dig_probe_stop_neutral_acknowledged",
                            False,
                        )
                    ),
                    "bounded_probe_terminal_requested": bool(
                        row.get(
                            "bounded_dig_probe_stop_terminal_requested",
                            False,
                        )
                    ),
                    "rollout_row": row,
                }
            )
    if not frames:
        raise ValueError(
            f"rollout has no cycle={cycle_index} skill={skill_name!r} action frames"
        )
    return frames


def classify_temporal_replay_frame(
    frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify whether the strict dig ACT was actually called for one row.

    Planner decisions and skill reset happen before action dispatch, so a
    switch/restart row is the first call of the newly active ACT and must reset
    the replay clock before that call. Safety pre-policy/clearance rows bypass
    ACT and must not advance the clock.
    """

    safety_short_circuit = bool(
        frame.get("box_safety_clearance_active", False)
        or frame.get("box_safety_awaiting_neutral_ack", False)
        or str(frame.get("pre_action_safety_reason", "")).strip()
    )
    action = np.asarray(frame.get("actual_action", []), dtype=np.float32)
    if (
        safety_short_circuit
        and action.shape == (4,)
        and np.allclose(action, 0.0, rtol=0.0, atol=1.0e-8)
    ):
        return {
            "policy_called": False,
            "reason": "safety_pre_policy_short_circuit",
            "reset_before_policy_call": False,
            "reset_before_next_policy_call": bool(
                frame.get("box_safety_policy_restarted", False)
                or str(frame.get("skill_switch_reason", "")).strip()
            ),
        }
    if bool(frame.get("box_safety_policy_restarted", False)):
        return {
            "policy_called": True,
            "reason": "same_skill_restart_reset_before_policy_call",
            "reset_before_policy_call": True,
            "reset_before_next_policy_call": False,
        }
    if str(frame.get("skill_switch_reason", "")).strip():
        return {
            "policy_called": True,
            "reason": "skill_switch_reset_before_policy_call",
            "reset_before_policy_call": True,
            "reset_before_next_policy_call": False,
        }
    return {
        "policy_called": True,
        "reason": "raw_policy_action_dispatched",
        "reset_before_policy_call": False,
        "reset_before_next_policy_call": False,
    }


def load_token_variant_matrix(
    artifact_path: str | Path,
    *,
    recorded_tokens: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Load and verify the exact F0/D1/C1/DC1 token counterfactual matrix."""

    path = Path(artifact_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema") != PLAN_MATRIX_SCHEMA:
        raise ValueError(
            f"token variant artifact must use schema {PLAN_MATRIX_SCHEMA!r}"
        )
    conditions = payload.get("conditions")
    if not isinstance(conditions, Mapping) or set(conditions) != set(
        _TOKEN_VARIANT_IDS
    ):
        raise ValueError(
            "token variant artifact conditions must be exactly "
            + ",".join(_TOKEN_VARIANT_IDS)
        )
    tokens: dict[str, list[float]] = {}
    for condition_id in _TOKEN_VARIANT_IDS:
        condition = conditions[condition_id]
        if not isinstance(condition, Mapping):
            raise ValueError(f"condition {condition_id} must be a mapping")
        token = condition.get("cycle_1_dig_cut_tokens")
        condition_payload: Mapping[str, Any] = condition
        runtime_source_path = condition.get("runtime_source_path")
        if token is None and runtime_source_path is not None:
            source_path = Path(str(runtime_source_path))
            expected_sha = str(
                condition.get("runtime_source_sha256", "")
            ).strip()
            actual_sha = _sha256(source_path)
            if not expected_sha or actual_sha != expected_sha:
                raise ValueError(
                    f"condition {condition_id} runtime source SHA mismatch"
                )
            loaded_source = json.loads(
                source_path.read_text(encoding="utf-8")
            )
            if (
                not isinstance(loaded_source, Mapping)
                or loaded_source.get("schema")
                != "residual_cut_intent_runtime_source_v1"
            ):
                raise ValueError(
                    f"condition {condition_id} runtime source schema invalid"
                )
            condition_payload = loaded_source
        if token is None:
            plans = condition_payload.get("plans", [])
            if not isinstance(plans, Sequence):
                raise ValueError(f"condition {condition_id} plans must be a sequence")
            cycle_one = next(
                (
                    item
                    for item in plans
                    if isinstance(item, Mapping)
                    and int(item.get("cycle_index", -1)) == 1
                ),
                None,
            )
            if cycle_one is None:
                raise ValueError(f"condition {condition_id} lacks cycle 1 plan")
            plan = cycle_one.get("plan", {})
            if not isinstance(plan, Mapping):
                raise ValueError(f"condition {condition_id} cycle 1 plan is invalid")
            token = plan.get("dig_cut_tokens")
        array = np.asarray(token, dtype=np.float32)
        if array.shape != (10,) or not np.isfinite(array).all():
            raise ValueError(f"condition {condition_id} token must be 10D finite")
        tokens[condition_id] = _float_list(array)

    f0 = np.asarray(tokens["F0"], dtype=np.float32)
    for index, recorded in enumerate(recorded_tokens):
        array = np.asarray(recorded, dtype=np.float32)
        if array.shape != (10,) or not np.allclose(
            array,
            f0,
            rtol=0.0,
            atol=1.0e-6,
        ):
            raise ValueError(
                f"recorded cycle-1 token at frame {index} does not match F0"
            )
    d1 = np.asarray(tokens["D1"], dtype=np.float32)
    c1 = np.asarray(tokens["C1"], dtype=np.float32)
    dc1 = np.asarray(tokens["DC1"], dtype=np.float32)
    if _different_indices(f0, d1) != {7}:
        raise ValueError("D1 may differ from F0 only token index 7")
    c1_diff = _different_indices(f0, c1)
    if not c1_diff or not c1_diff <= set(range(6)):
        raise ValueError("C1 may differ from F0 only token indices 0:6")
    if not np.allclose(dc1[:7], c1[:7], rtol=0.0, atol=1.0e-6):
        raise ValueError("DC1 geometry tokens must match C1")
    if not math.isclose(
        float(dc1[7]),
        float(d1[7]),
        rel_tol=0.0,
        abs_tol=1.0e-6,
    ) or not np.allclose(dc1[8:], f0[8:], rtol=0.0, atol=1.0e-6):
        raise ValueError("DC1 must be the union of C1 geometry and D1 depth")
    return {
        "artifact_path": str(path.resolve()),
        "artifact_sha256": _sha256(path),
        "schema": PLAN_MATRIX_SCHEMA,
        "tokens": tokens,
    }


def build_train_expert_index(
    *,
    dataset_dir: str | Path,
    split_path: str | Path,
) -> dict[str, Any]:
    """Build a numeric qpos/qvel/dig-token nearest-neighbor index.

    The split is enforced twice: by primitive id and by each primitive's
    ``source_episode_id`` metadata.  A validation source in ``train_ids`` is a
    hard error rather than something silently dropped.
    """

    dataset_root = Path(dataset_dir)
    split_file = Path(split_path)
    _assert_strict_only_path(dataset_root)
    _assert_strict_only_path(split_file)
    split = yaml.safe_load(split_file.read_text(encoding="utf-8")) or {}
    train_ids = [
        _integer(value, name="train primitive id")
        for value in split.get("train_ids", [])
    ]
    train_sources = tuple(
        _integer(value, name="train source episode id")
        for value in split.get("train_source_episode_ids", [])
    )
    val_sources = tuple(
        _integer(value, name="validation source episode id")
        for value in split.get("val_source_episode_ids", [])
    )
    allowed_sources = tuple(
        _integer(value, name="allowed source episode id")
        for value in split.get("allowed_source_episode_ids", [])
    )
    if not train_ids or not train_sources:
        raise ValueError("source-aware split must include train_ids and train sources")
    if train_sources != STRICT18_TRAIN_SOURCE_EPISODE_IDS:
        raise ValueError(
            "train_source_episode_ids must exactly match the strict-18 train "
            f"allowlist: got={list(train_sources)}"
        )
    if val_sources != STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
        raise ValueError(
            "val_source_episode_ids must exactly match strict validation "
            f"sources: got={list(val_sources)}"
        )
    expected_allowed = (
        *STRICT18_TRAIN_SOURCE_EPISODE_IDS,
        *STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
    )
    if allowed_sources != expected_allowed:
        raise ValueError(
            "allowed_source_episode_ids must exactly match strict-18 sources"
        )
    if set(train_sources) & set(val_sources):
        raise ValueError("train and validation source episode ids overlap")
    source_by_primitive = {
        _integer(key, name="source map primitive id"): _integer(
            value,
            name="source map episode id",
        )
        for key, value in dict(
            split.get("source_episode_id_by_primitive_episode_id", {})
            or {}
        ).items()
    }
    if any(primitive_id not in source_by_primitive for primitive_id in train_ids):
        raise ValueError(
            "source-aware split is missing train primitive source mappings"
        )

    feature_rows: list[np.ndarray] = []
    action_rows: list[np.ndarray] = []
    episode_rows: list[np.ndarray] = []
    step_rows: list[np.ndarray] = []
    source_rows: list[np.ndarray] = []
    total_step_count = 0
    masked_step_count = 0
    for primitive_id in train_ids:
        path = dataset_root / f"episode_{primitive_id}.hdf5"
        if not path.is_file():
            raise FileNotFoundError(path)
        with h5py.File(path, "r") as handle:
            source_episode_id = _source_episode_id(handle)
            if source_by_primitive[primitive_id] != source_episode_id:
                raise ValueError(
                    f"train primitive {primitive_id} source metadata does not "
                    "match split mapping"
                )
            if source_episode_id in val_sources:
                raise ValueError(
                    f"train primitive {primitive_id} contains validation source "
                    f"episode {source_episode_id}"
                )
            if source_episode_id not in train_sources:
                raise ValueError(
                    f"train primitive {primitive_id} source episode "
                    f"{source_episode_id} is not in train allowlist"
                )
            qpos = np.asarray(handle["observations/qpos"][:], dtype=np.float32)
            qvel = np.asarray(handle["observations/qvel"][:], dtype=np.float32)
            env_state = np.asarray(
                handle["observations/env_state"][:],
                dtype=np.float32,
            )
            tokens = np.asarray(
                handle["v2/step/dig_cut_tokens"][:],
                dtype=np.float32,
            )
            actions = np.asarray(handle["action"][:], dtype=np.float32)
            action_loss_mask = np.asarray(
                handle["v2/step/action_loss_mask"][:],
                dtype=np.uint8,
            ).reshape(-1)
            count = int(qpos.shape[0])
            if (
                qpos.shape != (count, 4)
                or qvel.shape != (count, 4)
                or env_state.ndim != 2
                or env_state.shape[0] != count
                or env_state.shape[1]
                < ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
                or tokens.shape != (count, 10)
                or actions.shape != (count, 4)
                or action_loss_mask.shape != (count,)
            ):
                raise ValueError(f"invalid dig primitive shapes in {path}")
            if not np.isin(action_loss_mask, [0, 1]).all():
                raise ValueError(f"non-binary action_loss_mask in {path}")
            keep = action_loss_mask == 1
            total_step_count += count
            masked_step_count += int(np.count_nonzero(~keep))
            if not np.any(keep):
                continue
            feature = _support_feature_matrix(
                qpos=qpos,
                qvel=qvel,
                env_state=env_state,
                dig_cut_tokens=tokens,
            )
            if not np.isfinite(feature).all() or not np.isfinite(actions).all():
                raise ValueError(f"non-finite dig primitive values in {path}")
            feature_rows.append(feature[keep])
            action_rows.append(actions[keep])
            episode_rows.append(
                np.full(int(np.count_nonzero(keep)), primitive_id, dtype=np.int32)
            )
            step_rows.append(np.flatnonzero(keep).astype(np.int32))
            source_rows.append(
                np.full(
                    int(np.count_nonzero(keep)),
                    source_episode_id,
                    dtype=np.int32,
                )
            )

    if not feature_rows:
        raise ValueError("strict train expert index has no action_loss_mask=1 rows")
    features = np.concatenate(feature_rows, axis=0)
    return {
        "feature": features,
        # Kept as a compatibility alias for callers that only inspect the
        # first 18 values. The canonical nearest-neighbor contract is feature.
        "proprio": features,
        "action": np.concatenate(action_rows, axis=0),
        "episode_id": np.concatenate(episode_rows, axis=0),
        "step": np.concatenate(step_rows, axis=0),
        "source_episode_id": np.concatenate(source_rows, axis=0),
        "train_source_episode_ids": sorted(train_sources),
        "validation_source_episode_ids": sorted(val_sources),
        "support_feature_order": list(_SUPPORT_FEATURE_ORDER),
        "total_step_count": int(total_step_count),
        "kept_step_count": int(features.shape[0]),
        "masked_step_count": int(masked_step_count),
    }


def nearest_expert_action(
    index: dict[str, Any],
    *,
    proprio: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
) -> dict[str, Any]:
    """Return the nearest train-only expert action in normalized proprio space."""

    query = np.asarray(proprio, dtype=np.float32).reshape(-1)
    rows = np.asarray(index["proprio"], dtype=np.float32)
    mean_arr = np.asarray(mean, dtype=np.float32).reshape(-1)
    std_arr = np.asarray(std, dtype=np.float32).reshape(-1)
    if rows.ndim != 2 or rows.shape[1] != query.size:
        raise ValueError("expert index/query proprio dimensions do not match")
    if mean_arr.shape != query.shape or std_arr.shape != query.shape:
        raise ValueError("normalization stats do not match proprio dimension")
    safe_std = np.maximum(std_arr, 1.0e-6)
    distances = np.linalg.norm((rows - query) / safe_std, axis=1)
    nearest = int(np.argmin(distances))
    return {
        "episode_id": int(np.asarray(index["episode_id"])[nearest]),
        "step": int(np.asarray(index["step"])[nearest]),
        "source_episode_id": int(
            np.asarray(index["source_episode_id"])[nearest]
        ),
        "distance": float(distances[nearest]),
        "action": _float_list(np.asarray(index["action"])[nearest]),
        "proprio": _float_list(rows[nearest]),
    }


def temporal_contributors(
    *,
    local_step: int,
    window: int,
    weight_order: str,
    decay: float,
) -> dict[str, Any]:
    """Describe the contributors used by the ACT rolling aggregator."""

    if local_step < 0 or window < 1:
        raise ValueError("local_step must be nonnegative and window positive")
    if weight_order not in {"legacy_oldest_first", "newest_first"}:
        raise ValueError(f"unsupported temporal weight order {weight_order!r}")
    if not math.isfinite(decay) or decay < 0.0:
        raise ValueError("temporal decay must be finite and nonnegative")
    count = min(local_step + 1, window)
    ages = list(range(count - 1, -1, -1))
    if weight_order == "legacy_oldest_first":
        distance = np.arange(count, dtype=np.float64)
    else:
        distance = np.asarray(ages, dtype=np.float64)
    weights = np.exp(-float(decay) * distance)
    weights /= np.sum(weights)
    return {
        "ages": ages,
        "weights": [float(value) for value in weights],
        "max_age": int(max(ages, default=0)),
        "weight_order": str(weight_order),
        "decay": float(decay),
    }


def _support_feature_matrix(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    env_state: np.ndarray,
    dig_cut_tokens: np.ndarray,
) -> np.ndarray:
    return np.concatenate(
        [
            np.asarray(qpos, dtype=np.float32),
            np.asarray(qvel, dtype=np.float32),
            np.asarray(
                env_state[
                    :,
                    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
                    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX + 1,
                ],
                dtype=np.float32,
            ),
            np.asarray(
                env_state[
                    :,
                    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
                    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6,
                ],
                dtype=np.float32,
            ),
            np.asarray(dig_cut_tokens, dtype=np.float32),
        ],
        axis=1,
    )


def _different_indices(left: np.ndarray, right: np.ndarray) -> set[int]:
    return {
        int(index)
        for index in np.flatnonzero(
            ~np.isclose(left, right, rtol=0.0, atol=1.0e-6)
        )
    }


def _assert_strict_only_path(path: Path) -> None:
    lowered = str(path.resolve()).lower()
    marker = next(
        (
            value
            for value in _FORBIDDEN_STRICT_PATH_MARKERS
            if value in lowered
        ),
        None,
    )
    if marker is not None:
        raise ValueError(
            f"strict train support path contains forbidden marker {marker!r}: "
            f"{path}"
        )


def write_json_exclusive(
    path: str | Path,
    payload: Mapping[str, Any],
) -> None:
    """Write JSON using an exclusive create while allowing an existing parent."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_episode_id(handle: h5py.File) -> int:
    value: Any = None
    if "metadata" in handle:
        value = handle["metadata"].attrs.get("source_episode_id")
    if value is None:
        value = handle.attrs.get("source_episode_id")
    if isinstance(value, (bytes, np.bytes_)):
        value = bytes(value).decode("utf-8")
    match = _SOURCE_EPISODE_RE.fullmatch(str(value).strip())
    if match is None:
        raise ValueError(f"invalid source_episode_id metadata {value!r}")
    return int(match.group(1))


def _integer(value: Any, *, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    try:
        exact = float(value)
    except (TypeError, ValueError):
        exact = float(parsed)
    if not math.isfinite(exact) or not math.isclose(exact, float(parsed)):
        raise ValueError(f"{name} must be an integer")
    return parsed


def _float_list(value: Any) -> list[float]:
    return [
        float(item)
        for item in np.asarray(value, dtype=np.float32).reshape(-1)
    ]


__all__ = [
    "EVIDENCE_SCOPE",
    "SCHEMA",
    "build_train_expert_index",
    "classify_temporal_replay_frame",
    "join_rollout_action_frames",
    "load_token_variant_matrix",
    "nearest_expert_action",
    "temporal_contributors",
    "write_json_exclusive",
]
