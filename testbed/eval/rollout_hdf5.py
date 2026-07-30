"""Helpers for turning live policy rollouts into trainable HDF5 episodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.cell_entry_v2_2 import enrich_episode_cell_entry
from testbed.data.hdf5_io import read_episode, write_v2_extension
from testbed.data.schema import (
    ATTR_GOAL_TOKEN_DIM,
    ATTR_V2_ENABLED,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM, CELL_ENTRY_VERSION

PHASE_ID_BY_LABEL = {
    "idle": 0,
    "loading": 1,
    "approaching_target": 2,
    "depositing": 3,
    "retained_success": 4,
    "unity_raw": 255,
}


def build_rollout_v2_payload(step_records: list[dict[str, object]]) -> dict[str, dict[str, np.ndarray]]:
    """Build the optional `/v2` labels available during a live eval rollout."""
    n_steps = len(step_records)
    if n_steps <= 0:
        return {"step": {}, "cycle": {}}

    goal_dim = _infer_goal_dim(step_records)
    step = {
        "cycle_id": _int_series(step_records, "cycle_id", default=0, dtype=np.int32),
        "mode_id": _int_series(step_records, "mode_id", default=0, dtype=np.uint8),
        "phase_id": _phase_id_series(step_records),
        "phase_progress": _phase_progress_series(n_steps),
        "work_stage_id": _work_stage_series(step_records),
        "goal_tokens": _goal_tokens(step_records, goal_dim=goal_dim),
        "action_loss_mask": np.ones(n_steps, dtype=np.uint8),
        "planner_replan_mask": _int_series(
            step_records, "planner_replan_mask", default=0, dtype=np.uint8
        ),
        "qualified_dig_start_mask": _int_series(
            step_records, "qualified_dig_start_mask", default=0, dtype=np.uint8
        ),
        "dump_start_mask": _int_series(
            step_records, "dump_start_mask", default=0, dtype=np.uint8
        ),
        "dump_end_mask": _int_series(step_records, "dump_end_mask", default=0, dtype=np.uint8),
        "pause_mask": _int_series(step_records, "pause_mask", default=0, dtype=np.uint8),
        "boundary_mask": _int_series(step_records, "boundary_mask", default=0, dtype=np.uint8),
    }
    return {"step": step, "cycle": _build_cycle_payload(step_records)}


def enrich_rollout_hdf5_in_place(path: str | Path) -> dict[str, Any]:
    """Attach Cell Entry planned/actual/audit fields to an already-written rollout."""
    path = Path(path)
    episode = read_episode(path)
    enriched_v2, summary = enrich_episode_cell_entry(
        episode=episode,
        source_episode=str(path),
    )
    metadata_updates = {
        ATTR_V2_ENABLED: 1,
        ATTR_GOAL_TOKEN_DIM: int(GOAL_TOKEN_DIM),
        "cell_entry_version": CELL_ENTRY_VERSION,
        "cell_entry_grid_long_count": 3,
        "cell_entry_grid_short_count": 2,
        "cell_entry_token_dim": int(CELL_ENTRY_TOKEN_DIM),
    }
    write_v2_extension(path, v2=enriched_v2, metadata_updates=metadata_updates)
    return summary


def _infer_goal_dim(step_records: list[dict[str, object]]) -> int:
    for record in step_records:
        tokens = record.get("goal_tokens")
        if tokens is None:
            continue
        arr = np.asarray(tokens, dtype=np.float32).reshape(-1)
        if arr.size > 0:
            return int(arr.size)
    return int(GOAL_TOKEN_DIM)


def _goal_tokens(step_records: list[dict[str, object]], *, goal_dim: int) -> np.ndarray:
    rows = np.zeros((len(step_records), int(goal_dim)), dtype=np.float32)
    for idx, record in enumerate(step_records):
        tokens = record.get("goal_tokens")
        if tokens is None:
            continue
        arr = np.asarray(tokens, dtype=np.float32).reshape(-1)
        if arr.size <= 0:
            continue
        rows[idx, : min(goal_dim, arr.size)] = arr[:goal_dim]
    return rows


def _int_series(
    step_records: list[dict[str, object]],
    key: str,
    *,
    default: int,
    dtype: np.dtype,
) -> np.ndarray:
    return np.asarray(
        [int(record.get(key, default)) for record in step_records],
        dtype=dtype,
    )


def _phase_id_series(step_records: list[dict[str, object]]) -> np.ndarray:
    values: list[int] = []
    for record in step_records:
        label = str(record.get("reward_phase", "idle"))
        values.append(int(PHASE_ID_BY_LABEL.get(label, 254)))
    return np.asarray(values, dtype=np.uint8)


def _phase_progress_series(n_steps: int) -> np.ndarray:
    if n_steps <= 1:
        return np.zeros(n_steps, dtype=np.float32)
    return np.linspace(0.0, 1.0, num=n_steps, dtype=np.float32)


def _work_stage_series(step_records: list[dict[str, object]]) -> np.ndarray:
    values: list[int] = []
    for record in step_records:
        skill_id = int(record.get("skill_id", -1))
        values.append(skill_id if skill_id >= 0 else int(record.get("mode_id", 0)))
    return np.asarray(values, dtype=np.uint8)


def _build_cycle_payload(step_records: list[dict[str, object]]) -> dict[str, np.ndarray]:
    cycle_ids = sorted(
        int(value)
        for value in np.unique(_int_series(step_records, "cycle_id", default=0, dtype=np.int32))
        if int(value) >= 0
    )
    if not cycle_ids:
        cycle_ids = [0]

    payload: dict[str, list[Any]] = {
        "cycle_id": [],
        "start_step": [],
        "dump_end_step": [],
        "end_step": [],
        "curr_src_sector_id": [],
        "curr_cut_depth_class": [],
        "next_src_sector_id": [],
        "next_cut_depth_class": [],
        "dst_target_id": [],
        "fill_peak_kg": [],
        "deposit_delta_kg": [],
        "peak_bucket_depth_m": [],
        "collision_count_delta": [],
        "transition_source": [],
        "plan_source": [],
        "cycle_success": [],
    }

    for cycle_id in cycle_ids:
        indices = [
            idx
            for idx, record in enumerate(step_records)
            if int(record.get("cycle_id", 0)) == cycle_id
        ]
        if not indices:
            continue
        start = indices[0]
        end = indices[-1]
        first = step_records[start]
        dump_end = next(
            (
                idx
                for idx in indices
                if int(step_records[idx].get("dump_end_mask", 0)) > 0
            ),
            end,
        )

        payload["cycle_id"].append(cycle_id)
        payload["start_step"].append(start)
        payload["dump_end_step"].append(dump_end)
        payload["end_step"].append(end)
        payload["curr_src_sector_id"].append(int(first.get("planner_current_sector_id", -1)))
        payload["curr_cut_depth_class"].append(int(first.get("planner_current_depth_class", -1)))
        payload["next_src_sector_id"].append(int(first.get("planner_next_sector_id", -1)))
        payload["next_cut_depth_class"].append(int(first.get("planner_next_depth_class", -1)))
        payload["dst_target_id"].append(0)
        payload["fill_peak_kg"].append(_max_env(indices, step_records, ENV_STATE_MASS_IN_BUCKET_IDX))
        payload["deposit_delta_kg"].append(
            max(
                0.0,
                _env_value(step_records[end], ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX)
                - _env_value(step_records[start], ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX),
            )
        )
        payload["peak_bucket_depth_m"].append(
            _max_env(indices, step_records, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX)
        )
        payload["collision_count_delta"].append(
            max(
                0,
                int(
                    round(
                        _env_value(step_records[end], ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX)
                        - _env_value(
                            step_records[start],
                            ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
                        )
                    )
                ),
            )
        )
        payload["transition_source"].append(str(first.get("transition_source", "")))
        payload["plan_source"].append(str(first.get("planner_plan_source", "")))
        has_dump_end = any(int(step_records[idx].get("dump_end_mask", 0)) > 0 for idx in indices)
        payload["cycle_success"].append(
            1 if payload["deposit_delta_kg"][-1] > 0.0 or has_dump_end else 0
        )

    return {
        "cycle_id": np.asarray(payload["cycle_id"], dtype=np.int32),
        "start_step": np.asarray(payload["start_step"], dtype=np.int32),
        "dump_end_step": np.asarray(payload["dump_end_step"], dtype=np.int32),
        "end_step": np.asarray(payload["end_step"], dtype=np.int32),
        "curr_src_sector_id": np.asarray(payload["curr_src_sector_id"], dtype=np.int32),
        "curr_cut_depth_class": np.asarray(payload["curr_cut_depth_class"], dtype=np.int32),
        "next_src_sector_id": np.asarray(payload["next_src_sector_id"], dtype=np.int32),
        "next_cut_depth_class": np.asarray(payload["next_cut_depth_class"], dtype=np.int32),
        "dst_target_id": np.asarray(payload["dst_target_id"], dtype=np.int32),
        "fill_peak_kg": np.asarray(payload["fill_peak_kg"], dtype=np.float32),
        "deposit_delta_kg": np.asarray(payload["deposit_delta_kg"], dtype=np.float32),
        "peak_bucket_depth_m": np.asarray(payload["peak_bucket_depth_m"], dtype=np.float32),
        "collision_count_delta": np.asarray(payload["collision_count_delta"], dtype=np.int32),
        "transition_source": np.asarray(payload["transition_source"], dtype=str),
        "plan_source": np.asarray(payload["plan_source"], dtype=str),
        "cycle_success": np.asarray(payload["cycle_success"], dtype=np.int8),
    }


def _max_env(
    indices: list[int],
    step_records: list[dict[str, object]],
    field_index: int,
) -> float:
    values = [_env_value(step_records[idx], field_index) for idx in indices]
    finite = [value for value in values if np.isfinite(value)]
    return float(max(finite)) if finite else 0.0


def _env_value(record: dict[str, object], field_index: int) -> float:
    env_state = record.get("env_state")
    if env_state is None:
        return 0.0
    arr = np.asarray(env_state, dtype=np.float32).reshape(-1)
    if arr.size <= field_index:
        return 0.0
    return float(arr[field_index])
