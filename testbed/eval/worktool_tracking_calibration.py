"""Bounded expert-replay and same-goal ACT trajectory calibration.

This module deliberately owns a diagnostic-only experiment.  It does not use
the planner, does not produce trainable HDF5, and cannot run the functional
1x10 gate.  A trial first replays the recorded episode prefix so expert and ACT
start from the same scene/terrain history.  The target segment is then either
continued with recorded expert actions or taken over by the frozen dig ACT.
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
import yaml

from testbed.backends.agx.backend import AgxSimBackend
from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)

LIVE_MEASUREMENT_SCHEMA = "expert_act_same_goal_live_measurement_v1"
TRAJECTORY_INPUT_SCHEMA = "worktool_trajectory_measurement_input_v1"
GEOMETRY_MEASUREMENT_SCHEMA = "worktool_trajectory_geometry_measurement_v1"
RECOMMENDATION_SCHEMA = "expert_act_tracking_margin_recommendation_v2"
EXPERT_REPLAY_REPEAT_COUNT = 3
ACT_TRACKING_REPEAT_COUNT = 5
TARGET_PRIMITIVE_EPISODE_ID = 168
TARGET_SOURCE_EPISODE_ID = 24
TARGET_SOURCE_START_STEP = 899
TARGET_SOURCE_END_STEP_EXCLUSIVE = 1050
CAMERA_ORDER = ("stick_up", "stick_down", "eye_left", "eye_right")
OLD_ACT_TRACKING_MARGIN_M = 0.15
OLD_HARD_CLEARANCE_M = 0.30
POSE_INTERPOLATION_BOUND_M = 0.01
FK_CALIBRATION_ERROR_M = 0.002


def write_json_exclusive(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Write one JSON artifact with create-new/no-overwrite semantics."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contact_snapshot(env_state: Sequence[float] | np.ndarray) -> dict[str, Any]:
    """Extract the append-only typed wall/bottom contact suffix."""

    env = np.asarray(env_state, dtype=np.float64).reshape(-1)
    if env.shape != (ENV_STATE_V2_4_DIM,) or not np.isfinite(env).all():
        raise ValueError(
            "typed trajectory calibration requires finite 107D env_state"
        )
    return {
        "wall_contact": bool(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] >= 0.5
        ),
        "wall_step_max_force_n": float(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX]
        ),
        "wall_session_count": int(
            round(
                env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX]
            )
        ),
        "bottom_contact": bool(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX]
            >= 0.5
        ),
        "bottom_step_max_force_n": float(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX]
        ),
        "bottom_session_count": int(
            round(
                env[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                ]
            )
        ),
    }


def build_margin_recommendation(
    *,
    live_manifest: Mapping[str, Any],
    geometry_measurement: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the 3D gate margins from wall-relevant repeated execution.

    Full 3D cover-point displacement is retained as the requested capability
    diagnostic, but it includes along-cut motion and link rotation and is not a
    wall-normal clearance loss.  The planner margin therefore uses the
    conservative path-wise loss of minimum wall clearance between the recorded
    expert and each ACT repeat.  The hard clearance is the centimetre-rounded
    lower bound of the smallest contact-free ACT clearance after FK error.
    """

    if live_manifest.get("schema") != LIVE_MEASUREMENT_SCHEMA:
        raise ValueError("live measurement schema mismatch")
    if geometry_measurement.get("schema") != GEOMETRY_MEASUREMENT_SCHEMA:
        raise ValueError("geometry measurement schema mismatch")
    trials = list(live_manifest.get("trials", ()))
    expert_trials = [
        item for item in trials if item.get("kind") == "expert_action_replay"
    ]
    act_trials = [
        item for item in trials if item.get("kind") == "act_same_goal_repeat"
    ]
    if len(expert_trials) != EXPERT_REPLAY_REPEAT_COUNT:
        raise ValueError("recommendation requires three expert replay trials")
    if len(act_trials) != ACT_TRACKING_REPEAT_COUNT:
        raise ValueError("recommendation requires five ACT repeat trials")
    if not all(bool(item.get("neutral_ack")) for item in trials):
        raise ValueError("every live trial requires terminal neutral ack")

    base = {
        "schema": RECOMMENDATION_SCHEMA,
        "evidence_kind": "bounded_live_plus_unity_shadow_fk_measurement",
        "promotion_eligible": False,
        "formal_1x10_executed": False,
        "training_data_written": False,
        "old_contract": {
            "act_tracking_margin_m": OLD_ACT_TRACKING_MARGIN_M,
            "hard_clearance_m": OLD_HARD_CLEARANCE_M,
        },
    }
    expert_contact_free = all(
        not bool(item.get("wall_contact"))
        and not bool(item.get("bottom_contact"))
        for item in expert_trials
    )
    if not expert_contact_free:
        return {
            **base,
            "status": "blocked",
            "apply_to_planner": False,
            "reason": "expert_replay_typed_contact_present",
            "expert_replay": {
                "repeat_count": len(expert_trials),
                "all_typed_contact_free": False,
            },
        }
    act_contact_free = all(
        not bool(item.get("wall_contact"))
        and not bool(item.get("bottom_contact"))
        for item in act_trials
    )
    if not act_contact_free:
        return {
            **base,
            "status": "blocked",
            "apply_to_planner": False,
            "reason": "act_repeat_typed_contact_present",
            "act_repeat": {
                "repeat_count": len(act_trials),
                "all_typed_contact_free": False,
            },
        }

    geometry_paths = list(geometry_measurement.get("paths", ()))
    expert_geometry = [
        item
        for item in geometry_paths
        if item.get("kind") == "expert_action_replay"
    ]
    if len(expert_geometry) != EXPERT_REPLAY_REPEAT_COUNT:
        raise ValueError(
            "geometry measurement requires three expert replay paths"
        )
    expert_clearances = np.asarray(
        [item["minimum_3d_clearance_m"] for item in expert_geometry],
        dtype=np.float64,
    )
    if (
        expert_clearances.shape != (EXPERT_REPLAY_REPEAT_COUNT,)
        or not np.isfinite(expert_clearances).all()
        or np.any(expert_clearances < 0.0)
    ):
        raise ValueError("expert replay clearance values are invalid")
    act_geometry = [
        item
        for item in geometry_paths
        if item.get("kind") == "act_same_goal_repeat"
    ]
    if len(act_geometry) != ACT_TRACKING_REPEAT_COUNT:
        raise ValueError("geometry measurement requires five ACT repeat paths")
    act_clearances = np.asarray(
        [item["minimum_3d_clearance_m"] for item in act_geometry],
        dtype=np.float64,
    )
    if (
        act_clearances.shape != (ACT_TRACKING_REPEAT_COUNT,)
        or not np.isfinite(act_clearances).all()
        or np.any(act_clearances < 0.0)
    ):
        raise ValueError("ACT repeat clearance values are invalid")
    reference = dict(geometry_measurement.get("reference", {}) or {})
    reference_clearance = _finite_nonnegative(
        reference.get("minimum_3d_clearance_m"),
        label="recorded expert minimum clearance",
    )
    wall_clearance_losses = np.maximum(
        0.0,
        reference_clearance - act_clearances,
    )

    deviation = dict(
        geometry_measurement.get(
            "act_deviation_from_recorded_expert",
            {},
        )
        or {}
    )
    if deviation.get("alignment") != "monotonic_dtw":
        raise ValueError("ACT deviation must use monotonic_dtw")
    p95 = _finite_nonnegative(deviation.get("p95_m"), label="ACT P95")
    p99 = _finite_nonnegative(deviation.get("p99_m"), label="ACT P99")
    if p99 + 1.0e-12 < p95:
        raise ValueError("ACT P99 must be at least P95")

    wall_loss_p95 = float(np.quantile(wall_clearance_losses, 0.95))
    wall_loss_p99 = float(np.quantile(wall_clearance_losses, 0.99))
    maximum_wall_loss = float(np.max(wall_clearance_losses))
    tracking_margin = _ceil_centimeter(
        maximum_wall_loss + FK_CALIBRATION_ERROR_M
    )
    minimum_act_clearance = float(np.min(act_clearances))
    hard_clearance = _floor_centimeter(
        minimum_act_clearance - FK_CALIBRATION_ERROR_M
    )
    if hard_clearance <= 0.0:
        return {
            **base,
            "status": "blocked",
            "apply_to_planner": False,
            "reason": "measured_hard_clearance_nonpositive",
            "expert_replay": {
                "repeat_count": len(expert_trials),
                "all_typed_contact_free": True,
                "minimum_3d_clearance_m": float(
                    np.min(expert_clearances)
                ),
                "per_repeat_minimum_3d_clearance_m": (
                    expert_clearances.tolist()
                ),
            },
            "act_repeat": {
                "repeat_count": len(act_trials),
                "all_typed_contact_free": True,
                "minimum_3d_clearance_m": minimum_act_clearance,
                "per_repeat_minimum_3d_clearance_m": (
                    act_clearances.tolist()
                ),
            },
        }
    total = (
        tracking_margin
        + hard_clearance
        + POSE_INTERPOLATION_BOUND_M
    )
    minimum_expert_clearance = float(np.min(expert_clearances))
    recommendation = {
        **base,
        "status": "completed",
        "apply_to_planner": True,
        "reason": "measured_contract_supported",
        "expert_replay": {
            "repeat_count": len(expert_trials),
            "all_typed_contact_free": True,
            "minimum_3d_clearance_m": minimum_expert_clearance,
            "per_repeat_minimum_3d_clearance_m": expert_clearances.tolist(),
        },
        "act_repeat": {
            "repeat_count": len(act_trials),
            "all_typed_contact_free": True,
            "p95_3d_deviation_m": p95,
            "p99_3d_deviation_m": p99,
            "maximum_3d_deviation_m": _finite_nonnegative(
                deviation.get("max_m"),
                label="ACT maximum",
            ),
            "metric": str(deviation.get("metric", "")),
            "alignment": "monotonic_dtw",
            "recorded_expert_minimum_3d_clearance_m": (
                reference_clearance
            ),
            "minimum_3d_clearance_m": minimum_act_clearance,
            "per_repeat_minimum_3d_clearance_m": act_clearances.tolist(),
            "wall_clearance_loss_metric": (
                "one_sided_path_minimum_wall_clearance_loss_m"
            ),
            "wall_clearance_loss_p95_m": wall_loss_p95,
            "wall_clearance_loss_p99_m": wall_loss_p99,
            "wall_clearance_loss_max_m": maximum_wall_loss,
        },
        "derivation": {
            "tracking_basis": (
                "ceil_cm(max_wall_clearance_loss + fk_error)"
            ),
            "hard_basis": (
                "floor_cm(min_contact_free_act_clearance - fk_error)"
            ),
            "fk_error_m": FK_CALIBRATION_ERROR_M,
            "double_counted_tracking_quantile": False,
            "full_3d_deviation_role": (
                "diagnostic_not_wall_normal_margin"
            ),
        },
        "recommended_contract": {
            "act_tracking_margin_m": tracking_margin,
            "hard_clearance_m": hard_clearance,
            "pose_interpolation_bound_m": POSE_INTERPOLATION_BOUND_M,
            "total_nominal_clearance_requirement_m": total,
        },
        "calibration_target_under_recommended_contract": {
            "recorded_expert_nominal_clearance_m": reference_clearance,
            "would_pass_without_live_start_margin": bool(
                reference_clearance + 1.0e-12 >= total
            ),
        },
    }
    return recommendation


def collect_live_measurement(
    *,
    source_episode_path: str | Path,
    primitive_path: str | Path,
    eval_config_path: str | Path,
    output_dir: str | Path,
    expert_repeats: int = EXPERT_REPLAY_REPEAT_COUNT,
    act_repeats: int = ACT_TRACKING_REPEAT_COUNT,
    control_compatibility_profile: str | None = "production",
) -> dict[str, Any]:
    """Run the bounded diagnostic experiment and write no-overwrite evidence."""

    if expert_repeats != EXPERT_REPLAY_REPEAT_COUNT:
        raise ValueError("locked expert replay repeat count is 3")
    if act_repeats != ACT_TRACKING_REPEAT_COUNT:
        raise ValueError("locked ACT repeat count is 5")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    trial_dir = destination / "trials"
    trial_dir.mkdir()

    source = _load_source_contract(
        source_episode_path=source_episode_path,
        primitive_path=primitive_path,
    )
    config_path = Path(eval_config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    _validate_a0_config(config)
    policy = _build_dig_policy(config)
    agx = dict(config.get("agx", {}) or {})
    task = dict(config.get("task", {}) or {})
    backend = AgxSimBackend(
        host=str(agx.get("host", "127.0.0.1")),
        port=int(agx.get("port", 5057)),
        timeout_s=float(agx.get("timeout", 10.0)),
        task_name=str(task.get("name", "agx_excavation_teleop")),
        reset_terrain=True,
        reset_pose=True,
        scenario_id=str(task.get("scenario_id", "s0_truck")),
        control_compatibility_profile=control_compatibility_profile,
    )
    source_lock = {
        "source_episode": _source_record(Path(source_episode_path)),
        "primitive": _source_record(Path(primitive_path)),
        "eval_config": _source_record(config_path),
        "dig_checkpoint": _source_record(
            Path(config["policy"]["dig_ckpt_path"])
        ),
        "dig_stats": _source_record(
            Path(config["policy"]["dig_ckpt_dir"]) / "dataset_stats.pkl"
        ),
    }
    trials: list[dict[str, Any]] = []
    try:
        info = backend.get_info()
        if tuple(info.camera_names) != CAMERA_ORDER:
            raise ValueError("live camera order differs from locked strict A0")
        if len(info.env_state_order) != ENV_STATE_V2_4_DIM:
            raise ValueError("live Unity must advertise the 107D env-state")

        for index in range(expert_repeats):
            trial = _run_trial(
                backend=backend,
                source=source,
                policy=None,
                trial_id=f"expert_replay_{index:02d}",
                kind="expert_action_replay",
                seed=index,
            )
            write_json_exclusive(
                trial_dir / f"{trial['trial_id']}.json",
                trial,
            )
            trials.append(trial)

        for index in range(act_repeats):
            trial = _run_trial(
                backend=backend,
                source=source,
                policy=policy,
                trial_id=f"act_repeat_{index:02d}",
                kind="act_same_goal_repeat",
                seed=100 + index,
            )
            write_json_exclusive(
                trial_dir / f"{trial['trial_id']}.json",
                trial,
            )
            trials.append(trial)
    finally:
        backend.close()

    manifest = {
        "schema": LIVE_MEASUREMENT_SCHEMA,
        "status": "completed",
        "evidence_kind": "bounded_live_diagnostic",
        "promotion_eligible": False,
        "formal_1x10_executed": False,
        "training_data_written": False,
        "target": {
            "primitive_episode_id": TARGET_PRIMITIVE_EPISODE_ID,
            "source_episode_id": TARGET_SOURCE_EPISODE_ID,
            "source_start_step": TARGET_SOURCE_START_STEP,
            "source_end_step_exclusive": (
                TARGET_SOURCE_END_STEP_EXCLUSIVE
            ),
            "target_action_count": int(
                TARGET_SOURCE_END_STEP_EXCLUSIVE
                - TARGET_SOURCE_START_STEP
            ),
            "same_goal_token": source["dig_cut_tokens"].tolist(),
        },
        "experiment": {
            "expert_replay_repeat_count": expert_repeats,
            "act_same_goal_repeat_count": act_repeats,
            "prefix_replayed_before_every_trial": True,
            "prefix_end_step_exclusive": TARGET_SOURCE_START_STEP,
            "stop_on_first_typed_wall_or_bottom": True,
            "terminal_zero_action_neutral_ack": True,
        },
        "source_lock": source_lock,
        "trials": [_compact_trial(item) for item in trials],
    }
    trajectory_input = {
        "schema": TRAJECTORY_INPUT_SCHEMA,
        "status": "ready",
        "target_exemplar_id": f"episode_{TARGET_PRIMITIVE_EPISODE_ID}",
        "source_lock": source_lock,
        "reference": {
            "path_id": f"recorded_expert_episode_{TARGET_PRIMITIVE_EPISODE_ID}",
            "kind": "recorded_strict_expert",
            "qpos_path": source["reference_qpos_path"].tolist(),
        },
        "paths": [
            {
                "path_id": item["trial_id"],
                "kind": item["kind"],
                "qpos_path": item["qpos_path"],
            }
            for item in trials
        ],
    }
    write_json_exclusive(destination / "live_measurement.json", manifest)
    write_json_exclusive(
        destination / "trajectory_measurement_input.json",
        trajectory_input,
    )
    return manifest


def _run_trial(
    *,
    backend: AgxSimBackend,
    source: Mapping[str, Any],
    policy: Any | None,
    trial_id: str,
    kind: str,
    seed: int,
) -> dict[str, Any]:
    actions = np.asarray(source["actions"], dtype=np.float32)
    token = np.asarray(source["dig_cut_tokens"], dtype=np.float32)
    ts = backend.reset(seed=seed)
    initial_contact = contact_snapshot(ts.observation["env_state"])
    if initial_contact["wall_contact"] or initial_contact["bottom_contact"]:
        raise RuntimeError(f"{trial_id}:typed_contact_after_reset")

    prefix_contact: dict[str, Any] | None = None
    for step_index in range(TARGET_SOURCE_START_STEP):
        ts = backend.step(actions[step_index])
        contact = contact_snapshot(ts.observation["env_state"])
        if contact["wall_contact"] or contact["bottom_contact"]:
            prefix_contact = {
                "source_step": step_index,
                **contact,
            }
            break
    if prefix_contact is not None:
        _neutral_ack(backend)
        raise RuntimeError(
            f"{trial_id}:typed_contact_during_common_prefix:"
            f"{prefix_contact}"
        )

    source_start_qpos = np.asarray(
        source["reference_qpos_path"][0],
        dtype=np.float32,
    )
    live_start_qpos = np.asarray(
        ts.observation["qpos"],
        dtype=np.float32,
    )
    start_qpos_abs_error = np.abs(live_start_qpos - source_start_qpos)
    if policy is not None:
        policy.reset()

    qpos_path: list[list[float]] = [live_start_qpos.astype(float).tolist()]
    action_records: list[dict[str, Any]] = []
    first_contact: dict[str, Any] | None = None
    for target_offset, source_step in enumerate(
        range(
            TARGET_SOURCE_START_STEP,
            TARGET_SOURCE_END_STEP_EXCLUSIVE,
        )
    ):
        if policy is None:
            action = actions[source_step].copy()
            action_source = "recorded_expert_action"
        else:
            obs = dict(ts.observation)
            obs["dig_cut_tokens"] = token.copy()
            action = np.asarray(policy.predict(obs), dtype=np.float32)
            action_source = "frozen_strict18_dig_act_a0"
        if action.shape != (4,) or not np.isfinite(action).all():
            raise RuntimeError(f"{trial_id}:invalid_action:{action}")
        pre_qpos = np.asarray(ts.observation["qpos"], dtype=np.float32)
        ts = backend.step(action)
        post_qpos = np.asarray(ts.observation["qpos"], dtype=np.float32)
        qpos_path.append(post_qpos.astype(float).tolist())
        contact = contact_snapshot(ts.observation["env_state"])
        action_records.append(
            {
                "target_offset": target_offset,
                "source_step": source_step,
                "action_source": action_source,
                "action": action.astype(float).tolist(),
                "pre_qpos": pre_qpos.astype(float).tolist(),
                "post_qpos": post_qpos.astype(float).tolist(),
                "typed_contact": contact,
            }
        )
        if contact["wall_contact"] or contact["bottom_contact"]:
            first_contact = {
                "target_offset": target_offset,
                "source_step": source_step,
                **contact,
            }
            break

    neutral = _neutral_ack(backend)
    wall_contact = any(
        bool(row["typed_contact"]["wall_contact"]) for row in action_records
    )
    bottom_contact = any(
        bool(row["typed_contact"]["bottom_contact"]) for row in action_records
    )
    return {
        "schema": "expert_act_same_goal_live_trial_v1",
        "trial_id": trial_id,
        "kind": kind,
        "seed": seed,
        "valid": True,
        "source_start_qpos": source_start_qpos.astype(float).tolist(),
        "live_start_qpos": live_start_qpos.astype(float).tolist(),
        "start_qpos_abs_error": start_qpos_abs_error.astype(float).tolist(),
        "start_qpos_max_abs_error": float(np.max(start_qpos_abs_error)),
        "qpos_path": qpos_path,
        "executed_target_action_count": len(action_records),
        "target_horizon_action_count": int(
            TARGET_SOURCE_END_STEP_EXCLUSIVE
            - TARGET_SOURCE_START_STEP
        ),
        "wall_contact": wall_contact,
        "bottom_contact": bottom_contact,
        "first_contact": first_contact,
        "neutral_ack": bool(neutral["acknowledged"]),
        "neutral_ack_step_id": int(neutral["step_id"]),
        "action_records": action_records,
    }


def _neutral_ack(backend: AgxSimBackend) -> dict[str, Any]:
    ts = backend.step(np.zeros(4, dtype=np.float32))
    return {
        "acknowledged": True,
        "step_id": int(ts.observation["step_id"]),
        "qpos": np.asarray(
            ts.observation["qpos"],
            dtype=np.float32,
        ).astype(float).tolist(),
        "contact": contact_snapshot(ts.observation["env_state"]),
    }


def _load_source_contract(
    *,
    source_episode_path: str | Path,
    primitive_path: str | Path,
) -> dict[str, Any]:
    source_path = Path(source_episode_path)
    primitive = Path(primitive_path)
    _validate_locked_primitive_lineage(
        primitive_path=primitive,
        source_episode_path=source_path,
    )
    with h5py.File(source_path, "r") as handle:
        actions = np.asarray(handle["action"], dtype=np.float32)
        qpos = np.asarray(handle["observations/qpos"], dtype=np.float32)
    if (
        actions.ndim != 2
        or actions.shape[1] != 4
        or qpos.ndim != 2
        or qpos.shape[1] != 4
        or actions.shape[0] <= TARGET_SOURCE_END_STEP_EXCLUSIVE
        or qpos.shape[0] <= TARGET_SOURCE_END_STEP_EXCLUSIVE
    ):
        raise ValueError("source episode does not cover locked episode_168")
    with h5py.File(primitive, "r") as handle:
        primitive_qpos = np.asarray(
            handle["observations/qpos"],
            dtype=np.float32,
        )
        primitive_actions = np.asarray(handle["action"], dtype=np.float32)
        tokens = np.asarray(
            handle["v2/step/dig_cut_tokens"],
            dtype=np.float32,
        )
    expected_count = (
        TARGET_SOURCE_END_STEP_EXCLUSIVE - TARGET_SOURCE_START_STEP
    )
    if (
        primitive_qpos.shape != (expected_count, 4)
        or primitive_actions.shape != (expected_count, 4)
        or tokens.shape != (expected_count, 10)
    ):
        raise ValueError("episode_168 primitive shape/lineage mismatch")
    if not np.allclose(
        primitive_qpos,
        qpos[
            TARGET_SOURCE_START_STEP:TARGET_SOURCE_END_STEP_EXCLUSIVE
        ],
        rtol=0.0,
        atol=1.0e-7,
    ):
        raise ValueError("episode_168 qpos window differs from source episode")
    if not np.allclose(
        primitive_actions,
        actions[
            TARGET_SOURCE_START_STEP:TARGET_SOURCE_END_STEP_EXCLUSIVE
        ],
        rtol=0.0,
        atol=1.0e-7,
    ):
        raise ValueError("episode_168 action window differs from source episode")
    if not np.allclose(tokens, tokens[0], rtol=0.0, atol=1.0e-7):
        raise ValueError("episode_168 goal token changes inside primitive")
    return {
        "actions": actions,
        "dig_cut_tokens": tokens[0],
        "reference_qpos_path": qpos[
            TARGET_SOURCE_START_STEP:
            TARGET_SOURCE_END_STEP_EXCLUSIVE + 1
        ],
    }


def _validate_locked_primitive_lineage(
    *,
    primitive_path: str | Path,
    source_episode_path: str | Path,
) -> dict[str, Any]:
    """Validate episode_168 source identity from the builder manifest."""

    primitive = Path(primitive_path).expanduser().resolve()
    source = Path(source_episode_path).expanduser().resolve()
    manifest_path = primitive.parent.parent / "window_manifest.json"
    try:
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "episode_168 window manifest missing or invalid"
        ) from exc
    if not isinstance(records, list):
        raise ValueError("episode_168 window manifest must be a list")
    matches = [
        record
        for record in records
        if isinstance(record, Mapping)
        and record.get("primitive_name") == "dig"
        and int(record.get("primitive_episode_id", -1))
        == TARGET_PRIMITIVE_EPISODE_ID
    ]
    if len(matches) != 1:
        raise ValueError(
            "episode_168 primitive lineage missing or ambiguous"
        )
    lineage = dict(matches[0])
    expected = {
        "source_episode_id": f"episode_{TARGET_SOURCE_EPISODE_ID}",
        "source_start_step": TARGET_SOURCE_START_STEP,
        "source_end_step_exclusive": TARGET_SOURCE_END_STEP_EXCLUSIVE,
    }
    if (
        str(lineage.get("source_episode_id", "")) != (
            expected["source_episode_id"]
        )
        or int(lineage.get("source_start_step", -1))
        != expected["source_start_step"]
        or int(lineage.get("source_end_step_exclusive", -1))
        != expected["source_end_step_exclusive"]
        or Path(
            str(lineage.get("source_episode_path", ""))
        ).expanduser().resolve()
        != source
    ):
        raise ValueError("episode_168 primitive lineage mismatch")
    return lineage


def _validate_a0_config(config: Mapping[str, Any]) -> None:
    policy = dict(config.get("policy", {}) or {})
    task = dict(config.get("task", {}) or {})
    act = dict(policy.get("act_params", {}) or {})
    if list(task.get("camera_names", ())) != list(CAMERA_ORDER):
        raise ValueError("strict A0 camera order changed")
    if list(policy.get("dig_low_dim_keys", ())) != [
        "qpos",
        "qvel",
        "dig_cut_tokens",
    ]:
        raise ValueError("strict A0 dig low-dimensional contract changed")
    if (
        int(act.get("temporal_agg_window", -1)) != 100
        or str(act.get("temporal_agg_weight_order", ""))
        != "legacy_oldest_first"
        or not math.isclose(
            float(act.get("temporal_agg_decay", float("nan"))),
            0.01,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        raise ValueError("tracking calibration requires locked A0 aggregation")


def _build_dig_policy(config: Mapping[str, Any]) -> Any:
    policy = dict(config.get("policy", {}) or {})
    task = dict(config.get("task", {}) or {})
    eval_config = dict(config.get("eval", {}) or {})
    checkpoint = Path(policy["dig_ckpt_path"])
    checkpoint_dir = Path(policy["dig_ckpt_dir"])
    if checkpoint.parent.resolve() != checkpoint_dir.resolve():
        raise ValueError("dig checkpoint/stats directory mismatch")
    from testbed.runtime._eval import (
        _build_act_eval_policy,
        _configure_eval_torch_performance,
    )

    device = str(policy.get("device", "cuda"))
    _configure_eval_torch_performance(eval_config, device=device)
    return _build_act_eval_policy(
        config=dict(config),
        ckpt_path=checkpoint,
        ckpt_dir=checkpoint_dir,
        camera_names=list(CAMERA_ORDER),
        equipment_model=str(task.get("equipment_model", "yulong")),
        max_episode_len=int(task.get("episode_len", 24000)),
        low_dim_keys=["qpos", "qvel", "dig_cut_tokens"],
        temporal_agg=True,
        device=device,
        act_params=dict(policy.get("act_params", {}) or {}),
        outcome_head_config=dict(
            policy.get("dig_outcome_head", {}) or {}
        ),
        image_mask_config=dict(policy.get("image_mask", {}) or {}),
    )


def _source_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _compact_trial(trial: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: trial[key]
        for key in (
            "trial_id",
            "kind",
            "seed",
            "valid",
            "start_qpos_max_abs_error",
            "executed_target_action_count",
            "target_horizon_action_count",
            "wall_contact",
            "bottom_contact",
            "first_contact",
            "neutral_ack",
            "neutral_ack_step_id",
        )
    }


def _finite_nonnegative(value: Any, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _ceil_centimeter(value: float) -> float:
    # The epsilon prevents an exactly representable centimetre boundary from
    # being promoted by binary floating-point noise.
    return float(math.ceil((float(value) - 1.0e-12) * 100.0) / 100.0)


def _floor_centimeter(value: float) -> float:
    # Subtract epsilon so a boundary is never rounded upward by float noise.
    return float(math.floor((float(value) + 1.0e-12) * 100.0) / 100.0)


__all__ = [
    "ACT_TRACKING_REPEAT_COUNT",
    "EXPERT_REPLAY_REPEAT_COUNT",
    "build_margin_recommendation",
    "collect_live_measurement",
    "contact_snapshot",
    "sha256_file",
    "write_json_exclusive",
]
