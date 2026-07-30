"""Teacher-forced M0/E1/W1 goal comparison for hard-bottom diagnosis.

This module deliberately separates target/lineage evidence from ACT execution
evidence.  It can build train-only nearest-expert and OOD evidence on recorded
observations, but it does not reuse the existing cycle-1 counterfactual replay:
that replay mutates one policy instance while evaluating multiple goals and
therefore cannot prove independent temporal buffers for M0, E1, and W1.
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
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.act_regression_offline_diagnostic import (
    _SUPPORT_FEATURE_ORDER,
    _assert_strict_only_path,
    _support_feature_matrix,
    build_train_expert_index,
    join_rollout_action_frames,
    nearest_expert_action,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner

SCHEMA = "hard_bottom_goal_comparison_v1"
EVIDENCE_SCOPE = "teacher_forced_recorded_observation"
TARGET_ORDER = ("M0", "E1", "W1")
TEMPORAL_WINDOW = 100
TEMPORAL_WEIGHT_ORDER = "legacy_oldest_first"
TEMPORAL_DECAY = 0.01
DEFAULT_TARGET_CELL_ID = 4
DEFAULT_EXPECTED_EXEMPLAR_ID = "episode_354"
DEFAULT_EXPECTED_SOURCE_EPISODE_ID = 32
MANIFEST_FILENAME = "manifest.json"

_EPISODE_ID_RE = re.compile(r"(?:episode_)?(\d+)(?:\.hdf5)?$")
_RAW_FIELD_DATASETS = {
    "operator_entry_x_m": "operator_entry_x_m",
    "operator_entry_y_m": "operator_entry_y_m",
    "operator_entry_z_m": "operator_entry_z_m",
    "operator_exit_x_m": "operator_exit_x_m",
    "operator_exit_y_m": "operator_exit_y_m",
    "operator_exit_z_m": "operator_exit_z_m",
    "operator_cut_direction_x": "operator_cut_direction_x",
    "operator_cut_direction_y": "operator_cut_direction_y",
    "operator_cut_direction_z": "operator_cut_direction_z",
    "operator_cut_length_m": "operator_cut_length_m",
    "operator_cut_depth_peak_m": "operator_cut_depth_peak_m",
    "operator_cut_payload_gain_kg": "operator_cut_payload_gain_kg",
    "operator_effective_deposit_delta_kg": (
        "dig_outcome_effective_deposit_delta_kg"
    ),
    "operator_cut_valid": "operator_cut_valid",
}


def build_hard_bottom_goal_comparison(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    planner_trace_path: str | Path,
    exemplar_path: str | Path,
    dig_split_path: str | Path,
    dig_dataset_dir: str | Path,
    wall_safe_goal_path: str | Path,
    wall_safe_goal_sha256: str,
    output_dir: str | Path,
    cycle_index: int = 5,
    target_cell_id: int = DEFAULT_TARGET_CELL_ID,
    expected_exemplar_id: str = DEFAULT_EXPECTED_EXEMPLAR_ID,
    expected_source_episode_id: int = DEFAULT_EXPECTED_SOURCE_EPISODE_ID,
    compute_train_support: bool = True,
) -> dict[str, Any]:
    """Build one no-overwrite, non-live M0/E1/W1 evidence artifact."""

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"output directory already exists: {destination}")

    paths = {
        "rollout_hdf5": Path(rollout_hdf5_path).resolve(strict=True),
        "rollout_jsonl": Path(rollout_jsonl_path).resolve(strict=True),
        "planner_trace": Path(planner_trace_path).resolve(strict=True),
        "state_exemplars": Path(exemplar_path).resolve(strict=True),
        "dig_source_split": Path(dig_split_path).resolve(strict=True),
        "dig_dataset_dir": Path(dig_dataset_dir).resolve(strict=True),
        "wall_safe_goal": Path(wall_safe_goal_path).resolve(strict=True),
    }
    joined_frames = join_rollout_action_frames(
        rollout_hdf5_path=paths["rollout_hdf5"],
        rollout_jsonl_path=paths["rollout_jsonl"],
        cycle_index=int(cycle_index),
        skill_name="dig",
    )
    frames, contact_action_step_id = _through_first_bottom_contact(joined_frames)
    recorded_tokens = [frame["dig_cut_tokens"] for frame in frames]
    first_env = np.asarray(frames[0]["env_state"], dtype=np.float32).reshape(-1)
    start = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
    if first_env.size < start + 6:
        raise ValueError("recorded observation lacks the six-cell removed-depth grid")
    current_removed_depth = first_env[start : start + 6].astype(np.float32)
    if not np.isfinite(current_removed_depth).all():
        raise ValueError("recorded six-cell removed-depth grid is non-finite")

    m0 = extract_recorded_median_goal(
        planner_trace_path=paths["planner_trace"],
        recorded_tokens=recorded_tokens,
    )
    e1 = select_strict_train_exemplar(
        exemplar_path=paths["state_exemplars"],
        split_path=paths["dig_source_split"],
        dataset_dir=paths["dig_dataset_dir"],
        current_removed_depth_grid_m=current_removed_depth,
        target_cell_id=int(target_cell_id),
        expected_exemplar_id=str(expected_exemplar_id),
        expected_source_episode_id=int(expected_source_episode_id),
    )
    w1 = load_wall_safe_goal(
        artifact_path=paths["wall_safe_goal"],
        expected_sha256=str(wall_safe_goal_sha256),
    )
    targets = {"M0": m0, "E1": e1, "W1": w1}

    temporal_states = build_temporal_state_contract(TARGET_ORDER)
    temporal_validation = validate_independent_temporal_states(temporal_states)
    support: dict[str, Any]
    if compute_train_support:
        support = build_train_support_comparison(
            frames=frames,
            targets=targets,
            dataset_dir=paths["dig_dataset_dir"],
            split_path=paths["dig_source_split"],
        )
    else:
        support = {
            "status": "blocked_not_requested",
            "reason": "compute_train_support_false",
        }

    source_artifacts = {
        key: _artifact_record(path)
        for key, path in paths.items()
        if path.is_file()
    }
    source_artifacts["dig_dataset_dir"] = {
        "path": str(paths["dig_dataset_dir"]),
        "kind": "strict_train_primitive_directory",
    }
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "complete_with_policy_replay_blocked",
        "evidence_scope": EVIDENCE_SCOPE,
        "offline_only": True,
        "live_closed_loop_evidence": False,
        "promotion_eligible": False,
        "cycle_index": int(cycle_index),
        "recorded_observation_window": {
            "frame_count": len(frames),
            "joined_dig_frame_count": len(joined_frames),
            "first_action_step_id": int(frames[0]["action_step_id"]),
            "last_action_step_id": int(frames[-1]["action_step_id"]),
            "first_observation_step_id": int(frames[0]["observation_step_id"]),
            "last_observation_step_id": int(frames[-1]["observation_step_id"]),
            "first_bottom_contact_action_step_id": contact_action_step_id,
            "post_contact_clearance_excluded": contact_action_step_id is not None,
            "start_removed_depth_grid_m": _float_list(current_removed_depth),
        },
        "target_order": list(TARGET_ORDER),
        "targets": targets,
        "temporal_state_contract": {
            "states": temporal_states,
            "validation": temporal_validation,
        },
        "train_support_evidence": support,
        "policy_action_evidence": {
            "status": "blocked",
            "fresh_action_status": "blocked",
            "a0_window_100_action_status": "blocked",
            "reason": (
                "existing_cycle1_counterfactual_replay_reuses_one_mutating_policy_"
                "instance_and_cannot_prove_independent_M0_E1_W1_temporal_buffers"
            ),
            "required_followup": (
                "instantiate_three_checkpoint-identical_policy_instances, reset "
                "each independently, and replay cycle-5 observations with one "
                "fixed target per instance"
            ),
            "no_synthetic_policy_actions_emitted": True,
        },
        "source_artifacts": source_artifacts,
    }

    destination.mkdir(parents=True, exist_ok=False)
    manifest_path = destination / MANIFEST_FILENAME
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def extract_recorded_median_goal(
    *,
    planner_trace_path: str | Path,
    recorded_tokens: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Resolve M0 as the last accepted planner goal matching cycle-5 tokens."""

    path = Path(planner_trace_path).resolve(strict=True)
    token = _one_constant_token(recorded_tokens, label="recorded M0 token")
    payload = _read_mapping(path, label="planner trace")
    trace = payload.get("coverage_decision_trace")
    if not isinstance(trace, list):
        raise ValueError("planner trace lacks coverage_decision_trace")
    matches: list[tuple[int, Mapping[str, Any], dict[str, float | int]]] = []
    for index, item in enumerate(trace):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("event", "")) != "wall_safety_final_guard_accepted":
            continue
        raw = item.get("raw_fields")
        if not isinstance(raw, Mapping):
            continue
        normalized = _normalize_raw_fields(raw)
        expected = _token_from_raw_fields(normalized)
        if np.allclose(expected, token, rtol=0.0, atol=1.0e-6):
            matches.append((index, item, normalized))
    if not matches:
        raise ValueError(
            "planner trace contains no accepted raw goal matching recorded tokens"
        )
    trace_index, item, raw_fields = matches[-1]
    return {
        "target_id": "M0",
        "description": "failed_cycle6_coordinate_wise_median_goal",
        "source_kind": "recorded_planner_final_guard",
        "raw_fields": raw_fields,
        "dig_cut_tokens": _float_list(token),
        "planner_trace_index": int(trace_index),
        "planner_trace_cycle_index": int(item.get("cycle_index", -1)),
        "planner_trace_path": str(path),
        "planner_trace_sha256": _sha256(path),
    }


def select_strict_train_exemplar(
    *,
    exemplar_path: str | Path,
    split_path: str | Path,
    dataset_dir: str | Path,
    current_removed_depth_grid_m: np.ndarray,
    target_cell_id: int,
    expected_exemplar_id: str | None = None,
    expected_source_episode_id: int | None = None,
) -> dict[str, Any]:
    """Select E1 with the locked strict-train K=1 removed-depth metric."""

    exemplar_file = Path(exemplar_path)
    split_file = Path(split_path)
    dataset_root = Path(dataset_dir)
    for path in (exemplar_file, split_file, dataset_root):
        _assert_strict_only_path(path)
    exemplar_file = exemplar_file.resolve(strict=True)
    split_file = split_file.resolve(strict=True)
    dataset_root = dataset_root.resolve(strict=True)

    payload = _read_mapping(exemplar_file, label="state exemplar artifact")
    distance_contract = payload.get("distance_contract")
    if not isinstance(distance_contract, Mapping):
        raise ValueError("state exemplar artifact lacks distance_contract")
    scale = _finite_float(
        distance_contract.get("default_removed_depth_scale_m"),
        label="removed-depth scale",
    )
    target_weight = _finite_float(
        distance_contract.get("default_target_cell_weight"),
        label="target-cell weight",
    )
    if not math.isclose(scale, 0.12, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("E1 requires removed-depth distance scale=0.12")
    if not math.isclose(target_weight, 2.0, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("E1 requires target-cell weight=2.0")

    current = np.asarray(current_removed_depth_grid_m, dtype=np.float64).reshape(-1)
    if current.shape != (6,) or not np.isfinite(current).all():
        raise ValueError("current removed-depth grid must be finite 6D")
    cell_id = int(target_cell_id)
    if cell_id < 0 or cell_id >= 6:
        raise ValueError("target cell id must be in [0, 5]")
    rows = payload.get("exemplars")
    if not isinstance(rows, list):
        raise ValueError("state exemplar artifact lacks exemplars list")
    scored: list[tuple[float, str, Mapping[str, Any]]] = []
    for item in rows:
        if not isinstance(item, Mapping) or int(item.get("cell_id", -1)) != cell_id:
            continue
        exemplar_grid = np.asarray(
            item.get("start_removed_depth_grid_m", []),
            dtype=np.float64,
        ).reshape(-1)
        if exemplar_grid.shape != (6,) or not np.isfinite(exemplar_grid).all():
            raise ValueError("cell-4 exemplar has invalid removed-depth grid")
        diff = (current - exemplar_grid) / scale
        diff[cell_id] *= target_weight
        distance = float(np.sqrt(np.mean(np.square(diff))))
        exemplar_id = str(item.get("exemplar_id", "")).strip()
        if not exemplar_id:
            raise ValueError("cell-4 exemplar lacks exemplar_id")
        scored.append((distance, exemplar_id, item))
    if not scored:
        raise ValueError(f"state exemplar artifact has no cell {cell_id} rows")
    scored.sort(key=lambda item: (item[0], item[1]))
    distance, exemplar_id, selected = scored[0]
    if expected_exemplar_id and exemplar_id != str(expected_exemplar_id):
        raise ValueError(
            "E1 exemplar identity mismatch: "
            f"selected={exemplar_id}, expected={expected_exemplar_id}"
        )
    primitive_id = _episode_id(exemplar_id, label="E1 exemplar_id")
    source_name = str(selected.get("source_episode", "")).strip()
    if source_name and _episode_id(source_name, label="E1 source_episode") != primitive_id:
        raise ValueError("E1 exemplar source_episode disagrees with exemplar_id")

    split = yaml.safe_load(split_file.read_text(encoding="utf-8")) or {}
    source_episode_id = _validate_strict_train_split(
        split,
        primitive_episode_id=primitive_id,
    )
    if (
        expected_source_episode_id is not None
        and source_episode_id != int(expected_source_episode_id)
    ):
        raise ValueError(
            "E1 source episode mismatch: "
            f"selected={source_episode_id}, expected={expected_source_episode_id}"
        )
    primitive_path = (dataset_root / f"episode_{primitive_id}.hdf5").resolve(
        strict=True
    )
    _assert_strict_only_path(primitive_path)
    with h5py.File(primitive_path, "r") as handle:
        primitive_source = _source_episode_id(handle)
        if primitive_source != source_episode_id:
            raise ValueError(
                "E1 primitive metadata source episode disagrees with split"
            )
        if primitive_source in STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
            raise ValueError("E1 primitive resolves to a validation source")
        raw_fields = _normalize_raw_fields(
            selected.get("raw_fields", {}),
        )
        primitive_raw = _primitive_raw_fields(handle)
        _assert_raw_fields_close(
            raw_fields,
            primitive_raw,
            label="E1 exemplar/primitive tuple",
        )
        token_rows = np.asarray(
            handle["v2/step/dig_cut_tokens"][:],
            dtype=np.float32,
        )
        if (
            token_rows.ndim != 2
            or token_rows.shape[1] != 10
            or token_rows.shape[0] < 1
            or not np.isfinite(token_rows).all()
        ):
            raise ValueError("E1 primitive dig-cut token dataset is invalid")
        if not np.allclose(
            token_rows,
            token_rows[0],
            rtol=0.0,
            atol=1.0e-6,
        ):
            raise ValueError("E1 primitive does not contain one fixed real token")
        expected_token = _token_from_raw_fields(raw_fields)
        if not np.allclose(
            token_rows[0],
            expected_token,
            rtol=0.0,
            atol=2.0e-6,
        ):
            raise ValueError("E1 real primitive token disagrees with raw tuple")
        trajectory = _expert_trajectory(handle)

    return {
        "target_id": "E1",
        "description": "strict_train_cell4_nearest_real_exemplar_tuple",
        "source_kind": "strict_train_real_exemplar",
        "cell_id": cell_id,
        "k": 1,
        "removed_depth_scale_m": scale,
        "target_cell_weight": target_weight,
        "distance": distance,
        "exemplar_id": exemplar_id,
        "primitive_episode_id": primitive_id,
        "source_episode_id": source_episode_id,
        "raw_fields": raw_fields,
        "dig_cut_tokens": _float_list(token_rows[0]),
        "start_removed_depth_grid_m": [
            float(value)
            for value in selected["start_removed_depth_grid_m"]
        ],
        "expert_trajectory": trajectory,
        "lineage": {
            "state_exemplar_path": str(exemplar_file),
            "state_exemplar_sha256": _sha256(exemplar_file),
            "dig_split_path": str(split_file),
            "dig_split_sha256": _sha256(split_file),
            "primitive_path": str(primitive_path),
            "primitive_sha256": _sha256(primitive_path),
            "train_only": True,
            "validation_source_ids_excluded": list(
                STRICT18_VALIDATION_SOURCE_EPISODE_IDS
            ),
            "partial_or_salvage_allowed": False,
        },
    }


def load_wall_safe_goal(
    *,
    artifact_path: str | Path,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load W1 from the immutable C1 runtime-source artifact."""

    path = Path(artifact_path).resolve(strict=True)
    actual_sha = _sha256(path)
    if not expected_sha256 or actual_sha != str(expected_sha256):
        raise ValueError(
            "W1 artifact SHA256 mismatch: "
            f"actual={actual_sha}, expected={expected_sha256}"
        )
    payload = _read_mapping(path, label="W1 artifact")
    if payload.get("schema") != "residual_cut_intent_runtime_source_v1":
        raise ValueError("W1 artifact schema is invalid")
    plans = payload.get("plans")
    if not isinstance(plans, list):
        raise ValueError("W1 artifact plans must be a list")
    cycle_one = [
        item
        for item in plans
        if isinstance(item, Mapping)
        and int(item.get("cycle_index", -1)) == 1
    ]
    if len(cycle_one) != 1:
        raise ValueError("W1 artifact must contain exactly one cycle-1 plan")
    plan = cycle_one[0].get("plan")
    if not isinstance(plan, Mapping):
        raise ValueError("W1 cycle-1 plan is invalid")
    raw_fields = _normalize_raw_fields(plan.get("raw_fields", {}))
    token = np.asarray(plan.get("dig_cut_tokens", []), dtype=np.float32)
    if token.shape != (10,) or not np.isfinite(token).all():
        raise ValueError("W1 cycle-1 token must be finite 10D")
    if not np.allclose(
        token,
        _token_from_raw_fields(raw_fields),
        rtol=0.0,
        atol=1.0e-6,
    ):
        raise ValueError("W1 token disagrees with its immutable raw tuple")
    return {
        "target_id": "W1",
        "description": "validated_C1_wall_safe_goal",
        "source_kind": "immutable_C1_runtime_source",
        "raw_fields": raw_fields,
        "dig_cut_tokens": _float_list(token),
        "artifact_path": str(path),
        "artifact_sha256": actual_sha,
    }


def build_temporal_state_contract(
    target_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Declare one target-owned empty temporal state per comparison branch."""

    return [
        {
            "target_id": str(target_id),
            "state_id": f"{SCHEMA}/{target_id}/act_temporal_state",
            "buffer_owner_id": f"{SCHEMA}/{target_id}/action_buffer",
            "cached_chunk_owner_id": f"{SCHEMA}/{target_id}/cached_chunk",
            "initial_contributor_count": 0,
            "temporal_window": TEMPORAL_WINDOW,
            "weight_order": TEMPORAL_WEIGHT_ORDER,
            "decay": TEMPORAL_DECAY,
            "policy_instance_created": False,
        }
        for target_id in target_ids
    ]


def validate_independent_temporal_states(
    states: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reject any structural alias before a future model replay is allowed."""

    if not states:
        raise ValueError("temporal state contract is empty")
    target_ids = [str(item.get("target_id", "")) for item in states]
    state_ids = [str(item.get("state_id", "")) for item in states]
    buffer_owners = [str(item.get("buffer_owner_id", "")) for item in states]
    chunk_owners = [
        str(item.get("cached_chunk_owner_id", "")) for item in states
    ]
    if len(set(target_ids)) != len(target_ids) or any(not value for value in target_ids):
        raise ValueError("temporal target ids must be non-empty and unique")
    if len(set(state_ids)) != len(state_ids) or any(not value for value in state_ids):
        raise ValueError("temporal state ids must be non-empty and unique")
    if len(set(buffer_owners)) != len(buffer_owners) or any(
        not value for value in buffer_owners
    ):
        raise ValueError("temporal buffer owner ids must be non-empty and unique")
    if len(set(chunk_owners)) != len(chunk_owners) or any(
        not value for value in chunk_owners
    ):
        raise ValueError("cached chunk owner ids must be non-empty and unique")
    for item in states:
        if int(item.get("initial_contributor_count", -1)) != 0:
            raise ValueError("each temporal state must start with zero contributors")
        if int(item.get("temporal_window", -1)) != TEMPORAL_WINDOW:
            raise ValueError("three-way comparison must keep A0 window=100")
        if str(item.get("weight_order", "")) != TEMPORAL_WEIGHT_ORDER:
            raise ValueError("three-way comparison must keep A0 weight order")
        if not math.isclose(
            float(item.get("decay", float("nan"))),
            TEMPORAL_DECAY,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("three-way comparison must keep A0 decay")
    return {
        "status": "passed_structural_only",
        "target_count": len(states),
        "unique_state_ids": True,
        "unique_buffer_owner_ids": True,
        "unique_cached_chunk_owner_ids": True,
        "all_initial_contributor_counts_zero": True,
        "policy_instances_created": False,
    }


def build_train_support_comparison(
    *,
    frames: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, Any]],
    dataset_dir: str | Path,
    split_path: str | Path,
) -> dict[str, Any]:
    """Compare M0/E1/W1 against the same strict-train numeric support."""

    index = build_train_expert_index(
        dataset_dir=dataset_dir,
        split_path=split_path,
    )
    features = np.asarray(index["feature"], dtype=np.float32)
    if features.ndim != 2 or features.shape[1] != len(_SUPPORT_FEATURE_ORDER):
        raise ValueError("strict train support feature shape is invalid")
    source_ids = {
        int(value)
        for value in np.asarray(index["source_episode_id"]).reshape(-1)
    }
    if source_ids & set(STRICT18_VALIDATION_SOURCE_EPISODE_IDS):
        raise ValueError("train support contains validation source episodes")
    if not source_ids <= set(STRICT18_TRAIN_SOURCE_EPISODE_IDS):
        raise ValueError("train support contains a non-strict source episode")
    lower = np.percentile(features, 1, axis=0)
    upper = np.percentile(features, 99, axis=0)
    mean = np.mean(features, axis=0)
    std = np.std(features, axis=0)

    qpos = np.asarray([frame["qpos"] for frame in frames], dtype=np.float32)
    qvel = np.asarray([frame["qvel"] for frame in frames], dtype=np.float32)
    env_state = np.asarray(
        [frame["env_state"] for frame in frames],
        dtype=np.float32,
    )
    target_evidence: dict[str, Any] = {}
    for target_id in TARGET_ORDER:
        target = targets[target_id]
        token = np.asarray(target["dig_cut_tokens"], dtype=np.float32)
        tokens = np.repeat(token.reshape(1, 10), len(frames), axis=0)
        query = _support_feature_matrix(
            qpos=qpos,
            qvel=qvel,
            env_state=env_state,
            dig_cut_tokens=tokens,
        )
        records: list[dict[str, Any]] = []
        in_support_count = 0
        for frame, feature in zip(frames, query, strict=True):
            violation_indices = [
                int(index_)
                for index_ in np.flatnonzero(
                    (feature < lower) | (feature > upper)
                )
            ]
            if not violation_indices:
                in_support_count += 1
            nearest = nearest_expert_action(
                index,
                proprio=feature,
                mean=mean,
                std=std,
            )
            records.append(
                {
                    "action_step_id": int(frame["action_step_id"]),
                    "observation_step_id": int(frame["observation_step_id"]),
                    "p01_p99_in_support": not violation_indices,
                    "violations": [
                        {
                            "index": index_,
                            "field": _SUPPORT_FEATURE_ORDER[index_],
                            "value": float(feature[index_]),
                            "p01": float(lower[index_]),
                            "p99": float(upper[index_]),
                        }
                        for index_ in violation_indices
                    ],
                    "nearest_train_expert": {
                        "episode_id": int(nearest["episode_id"]),
                        "step": int(nearest["step"]),
                        "source_episode_id": int(
                            nearest["source_episode_id"]
                        ),
                        "distance": float(nearest["distance"]),
                        "action": [
                            float(value) for value in nearest["action"]
                        ],
                    },
                }
            )
        target_evidence[target_id] = {
            "frame_count": len(records),
            "p01_p99_in_support_count": in_support_count,
            "p01_p99_in_support_fraction": (
                float(in_support_count) / float(len(records))
                if records
                else 0.0
            ),
            "records": records,
        }
    return {
        "status": "complete",
        "evidence_scope": EVIDENCE_SCOPE,
        "index_kind": "strict_train_action_loss_mask_numeric_nearest_neighbor",
        "support_feature_order": list(_SUPPORT_FEATURE_ORDER),
        "train_source_episode_ids": list(
            STRICT18_TRAIN_SOURCE_EPISODE_IDS
        ),
        "validation_source_episode_ids_excluded": list(
            STRICT18_VALIDATION_SOURCE_EPISODE_IDS
        ),
        "total_step_count": int(index["total_step_count"]),
        "kept_step_count": int(index["kept_step_count"]),
        "masked_step_count": int(index["masked_step_count"]),
        "targets": target_evidence,
    }


def _validate_strict_train_split(
    split: Mapping[str, Any],
    *,
    primitive_episode_id: int,
) -> int:
    train_sources = tuple(
        int(value) for value in split.get("train_source_episode_ids", [])
    )
    validation_sources = tuple(
        int(value) for value in split.get("val_source_episode_ids", [])
    )
    allowed_sources = tuple(
        int(value) for value in split.get("allowed_source_episode_ids", [])
    )
    if train_sources != STRICT18_TRAIN_SOURCE_EPISODE_IDS:
        raise ValueError("split train sources do not match strict-18 train")
    if validation_sources != STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
        raise ValueError("split validation sources do not match strict-18")
    if allowed_sources != (
        *STRICT18_TRAIN_SOURCE_EPISODE_IDS,
        *STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
    ):
        raise ValueError("split allowed sources do not match strict-18")
    train_ids = {int(value) for value in split.get("train_ids", [])}
    if primitive_episode_id not in train_ids:
        raise ValueError("E1 primitive is not in the strict train split")
    source_by_primitive = {
        int(key): int(value)
        for key, value in dict(
            split.get("source_episode_id_by_primitive_episode_id", {})
            or {}
        ).items()
    }
    if primitive_episode_id not in source_by_primitive:
        raise ValueError("strict split lacks E1 primitive source mapping")
    source_episode_id = source_by_primitive[primitive_episode_id]
    if source_episode_id in validation_sources:
        raise ValueError("E1 source episode is validation, not train")
    if source_episode_id not in train_sources:
        raise ValueError("E1 source episode is outside strict train")
    return source_episode_id


def _primitive_raw_fields(handle: h5py.File) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for raw_name, dataset_name in _RAW_FIELD_DATASETS.items():
        path = f"v2/cycle/{dataset_name}"
        if path not in handle:
            raise ValueError(f"E1 primitive lacks {path}")
        values = np.asarray(handle[path][:]).reshape(-1)
        if values.size != 1:
            raise ValueError(f"E1 primitive {path} must contain one cycle")
        if raw_name == "operator_cut_valid":
            result[raw_name] = int(values[0])
        else:
            result[raw_name] = float(values[0])
    return result


def _expert_trajectory(handle: h5py.File) -> dict[str, Any]:
    env_state = np.asarray(handle["observations/env_state"][:], dtype=np.float32)
    actions = np.asarray(handle["action"][:], dtype=np.float32)
    if (
        env_state.ndim != 2
        or env_state.shape[1] <= 31
        or actions.shape != (env_state.shape[0], 4)
        or not np.isfinite(env_state[:, 28:32]).all()
        or not np.isfinite(actions).all()
    ):
        raise ValueError("E1 expert trajectory datasets are invalid")
    return {
        "step_count": int(env_state.shape[0]),
        "bucket_tip_dig_area_pose_m": [
            _float_list(row) for row in env_state[:, 28:31]
        ],
        "local_penetration_m": _float_list(env_state[:, 31]),
        "expert_actions": [_float_list(row) for row in actions],
        "peak_local_penetration_m": float(np.max(env_state[:, 31])),
    }


def _source_episode_id(handle: h5py.File) -> int:
    value: Any = None
    if "metadata" in handle:
        value = handle["metadata"].attrs.get("source_episode_id")
    if value is None:
        value = handle.attrs.get("source_episode_id")
    if isinstance(value, (bytes, np.bytes_)):
        value = bytes(value).decode("utf-8")
    return _episode_id(value, label="primitive source_episode_id")


def _normalize_raw_fields(value: Any) -> dict[str, float | int]:
    if not isinstance(value, Mapping):
        raise ValueError("dig goal raw_fields must be a mapping")
    result: dict[str, float | int] = {}
    for name in _RAW_FIELD_DATASETS:
        if name not in value:
            raise ValueError(f"dig goal raw_fields lacks {name}")
        if name == "operator_cut_valid":
            result[name] = int(value[name])
        else:
            result[name] = _finite_float(value[name], label=name)
    if int(result["operator_cut_valid"]) != 1:
        raise ValueError("diagnostic dig goal must be valid")
    return result


def _assert_raw_fields_close(
    left: Mapping[str, float | int],
    right: Mapping[str, float | int],
    *,
    label: str,
) -> None:
    for name in _RAW_FIELD_DATASETS:
        if name == "operator_cut_valid":
            matches = int(left[name]) == int(right[name])
        else:
            matches = math.isclose(
                float(left[name]),
                float(right[name]),
                rel_tol=0.0,
                abs_tol=2.0e-6,
            )
        if not matches:
            raise ValueError(f"{label} disagrees at {name}")


def _token_from_raw_fields(
    raw_fields: Mapping[str, float | int],
) -> np.ndarray:
    plan = DigCutTokenPlanner(prior={}).plan_from_raw_fields(
        dict(raw_fields),
        source=SCHEMA,
    )
    token = np.asarray(plan.token, dtype=np.float32)
    if token.shape != (10,) or not np.isfinite(token).all():
        raise ValueError("dig goal token builder returned invalid token")
    return token


def _one_constant_token(
    values: Sequence[Sequence[float]],
    *,
    label: str,
) -> np.ndarray:
    tokens = np.asarray(values, dtype=np.float32)
    if (
        tokens.ndim != 2
        or tokens.shape[0] < 1
        or tokens.shape[1] != 10
        or not np.isfinite(tokens).all()
    ):
        raise ValueError(f"{label} must contain finite 10D rows")
    if not np.allclose(tokens, tokens[0], rtol=0.0, atol=1.0e-6):
        raise ValueError(f"{label} changes within the recorded dig")
    return tokens[0]


def _through_first_bottom_contact(
    frames: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], int | None]:
    """Keep the actual cut and exclude neutral/clearance rows after contact."""

    selected: list[Mapping[str, Any]] = []
    contact_step_id: int | None = None
    for frame in frames:
        selected.append(frame)
        post_env = np.asarray(
            frame.get("post_env_state", []),
            dtype=np.float32,
        ).reshape(-1)
        index = ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX
        if (
            post_env.size > index
            and np.isfinite(post_env[index])
            and float(post_env[index]) > 0.5
        ):
            contact_step_id = int(frame["action_step_id"])
            break
    if not selected:
        raise ValueError("recorded dig window is empty")
    return selected, contact_step_id


def _episode_id(value: Any, *, label: str) -> int:
    match = _EPISODE_ID_RE.fullmatch(str(value).strip())
    if match is None:
        raise ValueError(f"{label} is invalid: {value!r}")
    return int(match.group(1))


def _finite_float(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _read_mapping(path: Path, *, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float_list(values: Any) -> list[float]:
    return [
        float(value)
        for value in np.asarray(values, dtype=np.float32).reshape(-1)
    ]


__all__ = [
    "DEFAULT_EXPECTED_EXEMPLAR_ID",
    "DEFAULT_EXPECTED_SOURCE_EPISODE_ID",
    "DEFAULT_TARGET_CELL_ID",
    "EVIDENCE_SCOPE",
    "SCHEMA",
    "TARGET_ORDER",
    "build_hard_bottom_goal_comparison",
    "build_temporal_state_contract",
    "build_train_support_comparison",
    "extract_recorded_median_goal",
    "load_wall_safe_goal",
    "select_strict_train_exemplar",
    "validate_independent_temporal_states",
]
