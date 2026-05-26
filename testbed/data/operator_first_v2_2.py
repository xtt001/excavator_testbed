"""Operator-first V2.2 enrichment for YuLong professional data.

This builder is intentionally add-only.  It keeps the scripted Cell Entry
planner fields as legacy diagnostics and adds an operator cut corridor that is
derived from the actual professional cycle labels already present in `/v2`.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.hdf5_io import list_episodes, read_episode, write_episode
from testbed.data.schema import (
    ATTR_GOAL_TOKEN_DIM,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_2_DIM,
)
from testbed.data.vds import (
    EPISODE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    STORAGE_MODE_VDS,
    write_lineage_json,
    write_vds_episode,
)
from testbed.data.v2_1 import WORK_STAGE_NAME_TO_ID


DIG_CUT_TOKEN_DIM = 10
RETURN_TARGET_TOKEN_DIM = DIG_CUT_TOKEN_DIM
RETURN_START_ENVELOPE_TOKEN_DIM = 18
OPERATOR_FIRST_VERSION = "v2_4_operator_first_removed_depth_cut_v3"
DIG_CUT_TOKEN_CONTRACT = "v2_4_removed_depth_cut_v3"

DIG_CUT_POSITION_SCALE_M = 2.0
DIG_CUT_LENGTH_SCALE_M = 2.0
DIG_CUT_DEPTH_SCALE_M = 0.80
DIG_CUT_PAYLOAD_SCALE_KG = 60.0
REMOVED_DEPTH_DELTA_EPS_M = 1.0e-4
REMOVED_DEPTH_GRID_CELL_COUNT = 6


@dataclass(frozen=True)
class CycleWindow:
    cycle_id: int
    start_step: int
    end_step_exclusive: int
    dump_end_step: int


def build_operator_first_dataset(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
    storage_mode: str = STORAGE_MODE_VDS,
) -> dict[str, Any]:
    """Build an operator-first relabel root from an existing relabeled dataset."""
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    storage_mode = str(storage_mode).strip().lower()
    if storage_mode not in EPISODE_STORAGE_MODES:
        raise ValueError(
            f"Unsupported storage_mode {storage_mode!r}. "
            f"Expected one of {', '.join(EPISODE_STORAGE_MODES)}."
        )

    episode_paths = list_episodes(dataset_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")
    if output_dir.exists() and list(output_dir.glob("episode_*.hdf5")):
        if not overwrite:
            raise FileExistsError(
                f"Output directory {output_dir} already contains episode files."
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_summaries: list[dict[str, Any]] = []
    for source_path in episode_paths:
        episode = read_episode(
            source_path,
            load_images=(storage_mode == STORAGE_MODE_COPY),
        )
        enriched_v2, summary = enrich_episode_operator_first(
            episode=episode,
            source_episode=str(source_path),
        )
        metadata = dict(episode.get("metadata", {}) or {})
        metadata.update(
            {
                "operator_first_version": OPERATOR_FIRST_VERSION,
                "operator_first_storage_mode": storage_mode,
                "storage_mode": storage_mode,
                "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
                "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
                "dig_cut_token_contract": (
                    "entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
                    "length,cut_depth_semantic,payload,valid; normalized"
                ),
                "return_target_token_contract": (
                    "next entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
                    "length,cut_depth_semantic,payload,valid; normalized"
                ),
                "dig_cut_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
                "dig_cut_depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
                "legacy_cell_entry_use": "diagnostic_only",
                ATTR_GOAL_TOKEN_DIM: metadata.get(ATTR_GOAL_TOKEN_DIM, 10),
            }
        )
        target_path = output_dir / source_path.name
        if storage_mode == STORAGE_MODE_VDS:
            write_vds_episode(
                target_path,
                source_path=source_path,
                crop=slice(0, int(np.asarray(episode["actions"]).shape[0])),
                metadata=metadata,
                v2_step_overlay=_computed_step_fields(
                    dict(enriched_v2.get("step", {}) or {})
                ),
                v2_cycle_payload=dict(enriched_v2.get("cycle", {}) or {}),
                action_src_types=episode.get("action_src_types"),
                action_src_ids=episode.get("action_src_ids"),
            )
        else:
            write_episode(
                target_path,
                qpos=np.asarray(episode["qpos"], dtype=np.float32),
                qvel=np.asarray(episode["qvel"], dtype=np.float32),
                actions=np.asarray(episode["actions"], dtype=np.float32),
                images=dict(episode.get("images", {}) or {}) or None,
                rewards=episode.get("rewards"),
                metadata=metadata,
                env_state=episode.get("env_state"),
                step_ids=episode.get("step_ids"),
                step_ns=episode.get("step_ns"),
                action_src_types=episode.get("action_src_types"),
                action_src_ids=episode.get("action_src_ids"),
                v2=enriched_v2,
            )
        episode_summaries.append(summary)

    summary_payload = _build_dataset_summary(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        storage_mode=storage_mode,
        episode_summaries=episode_summaries,
    )
    with open(output_dir / "operator_first_summary.json", "w") as f:
        json.dump(_jsonable(summary_payload), f, indent=2, sort_keys=True)
    write_lineage_json(
        output_dir,
        builder="tb-build-operator-first-v2_2",
        storage_mode=storage_mode,
        source_roots=[dataset_dir],
        input_dataset_ids=[dataset_dir.name],
        schema_versions={
            "hdf5": "1.1",
            "operator_first": OPERATOR_FIRST_VERSION,
        },
        extra={
            "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
            "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
            "dig_cut_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
            "dig_cut_depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
            "legacy_cell_entry_use": "diagnostic_only",
        },
    )
    return summary_payload


def enrich_episode_operator_first(
    *,
    episode: dict[str, Any],
    source_episode: str = "",
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    """Return add-only operator-first `/v2` fields for one episode."""
    actions = np.asarray(episode["actions"], dtype=np.float32)
    n_steps = int(actions.shape[0])
    env_state = episode.get("env_state")
    env_arr = (
        np.asarray(env_state, dtype=np.float32)
        if env_state is not None
        else np.zeros((n_steps, 0), dtype=np.float32)
    )
    v2_existing = dict(episode.get("v2") or {})
    step_existing = {
        str(key): np.asarray(value)
        for key, value in dict(v2_existing.get("step", {}) or {}).items()
    }
    cycle_existing = {
        str(key): np.asarray(value)
        for key, value in dict(v2_existing.get("cycle", {}) or {}).items()
    }
    windows = _infer_cycle_windows(
        n_steps=n_steps,
        v2_step=step_existing,
        v2_cycle=cycle_existing,
    )

    dig_cut_tokens = np.zeros((n_steps, DIG_CUT_TOKEN_DIM), dtype=np.float32)
    return_target_tokens = np.zeros(
        (n_steps, RETURN_TARGET_TOKEN_DIM),
        dtype=np.float32,
    )
    cycle_payload = dict(cycle_existing)
    computed_cycle = _init_cycle_payload(len(windows))
    for idx, window in enumerate(windows):
        fields = _derive_cycle_fields(
            env_state=env_arr,
            v2_step=step_existing,
            v2_cycle=cycle_existing,
            window=window,
            cycle_index=idx,
        )
        _fill_cycle_payload(computed_cycle, idx, window, fields)
        token = _build_dig_cut_token(fields)
        start = max(0, min(n_steps, int(window.start_step)))
        end = max(start, min(n_steps, int(window.end_step_exclusive)))
        dig_cut_tokens[start:end] = token.reshape(1, -1)

    _fill_return_targets(computed_cycle, env_arr)
    _fill_return_target_tokens(
        return_target_tokens=return_target_tokens,
        windows=windows,
        cycle_payload=computed_cycle,
        n_steps=n_steps,
    )

    step_payload = dict(step_existing)
    step_payload.update(
        {
            "dig_cut_tokens": dig_cut_tokens,
            "return_target_tokens": return_target_tokens,
        }
    )
    cycle_payload.update(computed_cycle)

    summary = _build_episode_summary(
        source_episode=source_episode,
        n_steps=n_steps,
        windows=windows,
        cycle_payload=computed_cycle,
        old_cycle=cycle_existing,
    )
    return {"step": step_payload, "cycle": cycle_payload}, summary


def build_live_dig_cut_tokens_from_pose(
    pose_xyz: tuple[float, float, float] | None,
    *,
    cut_length_m: float = 1.2,
    cut_depth_peak_m: float = 0.08,
    payload_gain_kg: float = 55.0,
) -> np.ndarray:
    """Build a live planner token from the current bucket pose.

    The live token is a conservative operator-style prior: enter near the
    current/far-side bucket pose, then cut toward smaller local x while keeping
    z approximately stable.  Offline training still uses measured pro data.
    """
    if pose_xyz is None:
        return np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    entry_x, entry_y, entry_z = (float(pose_xyz[0]), float(pose_xyz[1]), float(pose_xyz[2]))
    exit_x = entry_x - abs(float(cut_length_m))
    exit_y = entry_y
    exit_z = entry_z
    fields = {
        "operator_entry_x_m": entry_x,
        "operator_entry_y_m": entry_y,
        "operator_entry_z_m": entry_z,
        "operator_exit_x_m": exit_x,
        "operator_exit_y_m": exit_y,
        "operator_exit_z_m": exit_z,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": abs(float(cut_length_m)),
        "operator_cut_depth_peak_m": float(cut_depth_peak_m),
        "operator_cut_payload_gain_kg": float(payload_gain_kg),
        "operator_cut_valid": 1,
    }
    return _build_dig_cut_token(fields)


def _computed_step_fields(step_payload: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {
        key: value
        for key, value in step_payload.items()
        if key in {"dig_cut_tokens", "return_target_tokens"}
    }


def _init_cycle_payload(n_cycles: int) -> dict[str, np.ndarray]:
    float_default = np.full(n_cycles, np.nan, dtype=np.float32)
    int_default = np.full(n_cycles, -1, dtype=np.int32)
    return {
        "cycle_effective_deposit_delta_kg": float_default.copy(),
        "legacy_dump_end_deposit_delta_kg": float_default.copy(),
        "dump_window_deposit_delta_kg": float_default.copy(),
        "operator_entry_step": int_default.copy(),
        "operator_exit_step": int_default.copy(),
        "operator_entry_x_m": float_default.copy(),
        "operator_entry_y_m": float_default.copy(),
        "operator_entry_z_m": float_default.copy(),
        "operator_exit_x_m": float_default.copy(),
        "operator_exit_y_m": float_default.copy(),
        "operator_exit_z_m": float_default.copy(),
        "operator_cut_direction_x": float_default.copy(),
        "operator_cut_direction_y": float_default.copy(),
        "operator_cut_direction_z": float_default.copy(),
        "operator_cut_length_m": float_default.copy(),
        "operator_cut_depth_peak_m": float_default.copy(),
        "operator_cut_depth_source": np.asarray(["none"] * n_cycles, dtype=object),
        "operator_cut_payload_gain_kg": float_default.copy(),
        "operator_cut_valid": np.zeros(n_cycles, dtype=np.uint8),
        "next_operator_entry_step": int_default.copy(),
        "next_operator_entry_x_m": float_default.copy(),
        "next_operator_entry_y_m": float_default.copy(),
        "next_operator_entry_z_m": float_default.copy(),
        "next_operator_exit_step": int_default.copy(),
        "next_operator_exit_x_m": float_default.copy(),
        "next_operator_exit_y_m": float_default.copy(),
        "next_operator_exit_z_m": float_default.copy(),
        "next_operator_cut_direction_x": float_default.copy(),
        "next_operator_cut_direction_y": float_default.copy(),
        "next_operator_cut_direction_z": float_default.copy(),
        "next_operator_cut_length_m": float_default.copy(),
        "next_operator_cut_depth_peak_m": float_default.copy(),
        "next_operator_cut_depth_source": np.asarray(
            ["none"] * n_cycles,
            dtype=object,
        ),
        "next_operator_cut_payload_gain_kg": float_default.copy(),
        "next_operator_cut_valid": np.zeros(n_cycles, dtype=np.uint8),
        "return_entry_delta_x_m": float_default.copy(),
        "return_entry_delta_y_m": float_default.copy(),
        "return_entry_delta_z_m": float_default.copy(),
        "return_entry_delta_norm_m": float_default.copy(),
        "return_target_source": np.asarray(["none"] * n_cycles, dtype=object),
        "training_tier": np.asarray(["silver"] * n_cycles, dtype=str),
    }


def _fill_cycle_payload(
    cycle_payload: dict[str, np.ndarray],
    idx: int,
    window: CycleWindow,
    fields: dict[str, float | int | str],
) -> None:
    for key, value in fields.items():
        if key not in cycle_payload:
            continue
        if key in {
            "return_target_source",
            "training_tier",
            "operator_cut_depth_source",
            "next_operator_cut_depth_source",
        }:
            cycle_payload[key][idx] = str(value)
        elif cycle_payload[key].dtype.kind in {"i", "u"}:
            cycle_payload[key][idx] = int(value)
        else:
            cycle_payload[key][idx] = float(value)
    cycle_payload["operator_entry_step"][idx] = int(fields.get("operator_entry_step", window.start_step))
    cycle_payload["operator_exit_step"][idx] = int(fields.get("operator_exit_step", window.start_step))


def _derive_cycle_fields(
    *,
    env_state: np.ndarray,
    v2_step: dict[str, np.ndarray],
    v2_cycle: dict[str, np.ndarray],
    window: CycleWindow,
    cycle_index: int,
) -> dict[str, float | int | str]:
    n_steps = int(env_state.shape[0]) if env_state.ndim == 2 else 0
    start = max(0, min(n_steps - 1, int(window.start_step))) if n_steps else 0
    end = max(start + 1, min(n_steps, int(window.end_step_exclusive))) if n_steps else 0
    entry_step = _cycle_scalar_int(
        v2_cycle,
        "actual_accepted_start_step",
        cycle_index,
        default=start,
    )
    if entry_step < start or entry_step >= end:
        entry_step = start
    exit_step = _infer_operator_exit_step(
        v2_step=v2_step,
        start=start,
        end=end,
        fallback_end=max(start, end - 1),
    )
    entry_pose = _bucket_pose_for_step(env_state, entry_step)
    exit_pose = _bucket_pose_for_step(env_state, exit_step)
    valid = entry_pose is not None and exit_pose is not None
    if entry_pose is None:
        entry_pose = (np.nan, np.nan, np.nan)
    if exit_pose is None:
        exit_pose = (np.nan, np.nan, np.nan)

    direction = _direction(entry_pose, exit_pose)
    cut_length = _distance(entry_pose, exit_pose)
    surface_depth_peak, depth_source = _cut_depth_semantic_peak(
        env_state,
        start,
        max(start + 1, exit_step + 1),
    )
    depth_peak = surface_depth_peak
    payload_gain = _mass_delta(
        env_state,
        start,
        end,
        ENV_STATE_MASS_IN_BUCKET_IDX,
    )
    effective_deposit = _deposit_delta(
        env_state,
        start,
        end,
        preferred_idx=ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    )
    dump_start = _first_mask_step(
        v2_step.get("dump_start_mask"),
        start=start,
        end=end,
        default=_cycle_scalar_int(v2_cycle, "dump_start_step", cycle_index, default=-1),
    )
    dump_window_start = dump_start if dump_start >= start else start
    dump_window_deposit = _deposit_delta(
        env_state,
        dump_window_start,
        end,
        preferred_idx=ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    )
    legacy_deposit = _cycle_scalar_float(
        v2_cycle,
        "deposit_delta_kg",
        cycle_index,
        default=np.nan,
    )
    if not np.isfinite(legacy_deposit):
        legacy_deposit = _deposit_delta(
            env_state,
            start,
            min(n_steps, max(start + 1, int(window.dump_end_step) + 1)),
            preferred_idx=ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
        )

    return {
        "cycle_effective_deposit_delta_kg": max(0.0, effective_deposit),
        "legacy_dump_end_deposit_delta_kg": max(0.0, legacy_deposit),
        "dump_window_deposit_delta_kg": max(0.0, dump_window_deposit),
        "operator_entry_step": int(entry_step),
        "operator_exit_step": int(exit_step),
        "operator_entry_x_m": float(entry_pose[0]),
        "operator_entry_y_m": float(entry_pose[1]),
        "operator_entry_z_m": float(entry_pose[2]),
        "operator_exit_x_m": float(exit_pose[0]),
        "operator_exit_y_m": float(exit_pose[1]),
        "operator_exit_z_m": float(exit_pose[2]),
        "operator_cut_direction_x": float(direction[0]),
        "operator_cut_direction_y": float(direction[1]),
        "operator_cut_direction_z": float(direction[2]),
        "operator_cut_length_m": max(0.0, cut_length),
        "operator_cut_depth_peak_m": max(0.0, depth_peak),
        "operator_cut_depth_source": depth_source,
        "operator_cut_payload_gain_kg": max(0.0, payload_gain),
        "operator_cut_valid": 1 if valid else 0,
        "training_tier": _training_tier(
            payload_gain_kg=max(0.0, payload_gain),
            effective_deposit_delta_kg=max(0.0, effective_deposit),
            cut_length_m=max(0.0, cut_length),
            cut_depth_peak_m=max(0.0, depth_peak),
            depth_reliable=depth_source == "env_state_surface_penetration",
            valid=bool(valid),
        ),
    }


def _fill_return_targets(
    cycle_payload: dict[str, np.ndarray],
    env_state: np.ndarray,
) -> None:
    n_cycles = len(cycle_payload["operator_entry_step"])
    for idx in range(n_cycles - 1):
        next_entry_step = int(cycle_payload["operator_entry_step"][idx + 1])
        next_pose = (
            float(cycle_payload["operator_entry_x_m"][idx + 1]),
            float(cycle_payload["operator_entry_y_m"][idx + 1]),
            float(cycle_payload["operator_entry_z_m"][idx + 1]),
        )
        before_next_pose = _bucket_pose_for_step(env_state, max(0, next_entry_step - 1))
        if before_next_pose is None:
            before_next_pose = next_pose
        delta = tuple(before_next_pose[axis] - next_pose[axis] for axis in range(3))
        cycle_payload["next_operator_entry_step"][idx] = int(next_entry_step)
        cycle_payload["next_operator_entry_x_m"][idx] = float(next_pose[0])
        cycle_payload["next_operator_entry_y_m"][idx] = float(next_pose[1])
        cycle_payload["next_operator_entry_z_m"][idx] = float(next_pose[2])
        cycle_payload["next_operator_exit_step"][idx] = int(
            cycle_payload["operator_exit_step"][idx + 1]
        )
        cycle_payload["next_operator_exit_x_m"][idx] = float(
            cycle_payload["operator_exit_x_m"][idx + 1]
        )
        cycle_payload["next_operator_exit_y_m"][idx] = float(
            cycle_payload["operator_exit_y_m"][idx + 1]
        )
        cycle_payload["next_operator_exit_z_m"][idx] = float(
            cycle_payload["operator_exit_z_m"][idx + 1]
        )
        cycle_payload["next_operator_cut_direction_x"][idx] = float(
            cycle_payload["operator_cut_direction_x"][idx + 1]
        )
        cycle_payload["next_operator_cut_direction_y"][idx] = float(
            cycle_payload["operator_cut_direction_y"][idx + 1]
        )
        cycle_payload["next_operator_cut_direction_z"][idx] = float(
            cycle_payload["operator_cut_direction_z"][idx + 1]
        )
        cycle_payload["next_operator_cut_length_m"][idx] = float(
            cycle_payload["operator_cut_length_m"][idx + 1]
        )
        cycle_payload["next_operator_cut_depth_peak_m"][idx] = float(
            cycle_payload["operator_cut_depth_peak_m"][idx + 1]
        )
        cycle_payload["next_operator_cut_depth_source"][idx] = str(
            cycle_payload["operator_cut_depth_source"][idx + 1]
        )
        cycle_payload["next_operator_cut_payload_gain_kg"][idx] = float(
            cycle_payload["operator_cut_payload_gain_kg"][idx + 1]
        )
        cycle_payload["next_operator_cut_valid"][idx] = int(
            cycle_payload["operator_cut_valid"][idx + 1]
        )
        cycle_payload["return_entry_delta_x_m"][idx] = float(delta[0])
        cycle_payload["return_entry_delta_y_m"][idx] = float(delta[1])
        cycle_payload["return_entry_delta_z_m"][idx] = float(delta[2])
        cycle_payload["return_entry_delta_norm_m"][idx] = float(_norm(delta))
        cycle_payload["return_target_source"][idx] = "operator_next_entry"
    if n_cycles > 0:
        cycle_payload["return_target_source"][n_cycles - 1] = "terminal_none"


def _fill_return_target_tokens(
    *,
    return_target_tokens: np.ndarray,
    windows: list[CycleWindow],
    cycle_payload: dict[str, np.ndarray],
    n_steps: int,
) -> None:
    for idx in range(max(0, len(windows) - 1)):
        if int(cycle_payload["next_operator_cut_valid"][idx]) <= 0:
            continue
        token = _build_return_target_token(cycle_payload, idx)
        start = max(0, min(n_steps, int(windows[idx].dump_end_step)))
        end = max(
            start,
            min(n_steps, int(cycle_payload["next_operator_entry_step"][idx]) + 1),
        )
        if end <= start:
            continue
        return_target_tokens[start:end] = token.reshape(1, -1)


def _infer_cycle_windows(
    *,
    n_steps: int,
    v2_step: dict[str, np.ndarray],
    v2_cycle: dict[str, np.ndarray],
) -> list[CycleWindow]:
    if "start_step" in v2_cycle and (
        "end_step" in v2_cycle or "dump_end_step" in v2_cycle
    ):
        starts = np.asarray(v2_cycle["start_step"], dtype=np.int32).reshape(-1)
        ends = np.asarray(
            v2_cycle.get("end_step", v2_cycle.get("dump_end_step")),
            dtype=np.int32,
        ).reshape(-1)
        dump_ends = np.asarray(
            v2_cycle.get("dump_end_step", ends),
            dtype=np.int32,
        ).reshape(-1)
        cycle_ids = np.asarray(
            v2_cycle.get("cycle_id", np.arange(len(starts))),
            dtype=np.int32,
        ).reshape(-1)
        count = min(len(starts), len(ends), len(cycle_ids), len(dump_ends))
        windows: list[CycleWindow] = []
        for idx in range(count):
            start = int(starts[idx])
            end_inclusive = int(ends[idx])
            if start < 0 or end_inclusive < start:
                continue
            windows.append(
                CycleWindow(
                    cycle_id=int(cycle_ids[idx]),
                    start_step=max(0, min(n_steps - 1, start)),
                    end_step_exclusive=max(
                        1,
                        min(n_steps, int(end_inclusive) + 1),
                    ),
                    dump_end_step=max(0, min(n_steps - 1, int(dump_ends[idx]))),
                )
            )
        return windows

    cycle_id = np.asarray(v2_step.get("cycle_id", []), dtype=np.int32).reshape(-1)
    if cycle_id.size == n_steps and n_steps > 0:
        windows = []
        for cid in sorted(int(value) for value in np.unique(cycle_id) if value >= 0):
            indices = np.flatnonzero(cycle_id == cid)
            if indices.size <= 0:
                continue
            windows.append(
                CycleWindow(
                    cycle_id=int(cid),
                    start_step=int(indices[0]),
                    end_step_exclusive=int(indices[-1]) + 1,
                    dump_end_step=int(indices[-1]),
                )
            )
        return windows
    return []


def _infer_operator_exit_step(
    *,
    v2_step: dict[str, np.ndarray],
    start: int,
    end: int,
    fallback_end: int,
) -> int:
    work_stage = np.asarray(v2_step.get("work_stage_id", []), dtype=np.int32).reshape(-1)
    if work_stage.size >= end:
        carry_like = {
            WORK_STAGE_NAME_TO_ID["carry"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
        }
        for step in range(int(start), int(end)):
            if int(work_stage[step]) in carry_like:
                return max(int(start), int(step) - 1)
    return int(fallback_end)


def _bucket_pose_for_step(
    env_state: np.ndarray,
    step: int,
) -> tuple[float, float, float] | None:
    if env_state.ndim != 2 or step < 0 or step >= len(env_state):
        return None
    row = env_state[int(step)]
    if len(row) > ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX:
        values = (
            float(row[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX]),
            float(row[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX]),
            float(row[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX]),
        )
        if all(np.isfinite(value) for value in values):
            return values
    if len(row) <= ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX:
        return None
    values = (
        float(row[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX]),
        float(row[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX]),
        float(row[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX]),
    )
    if not all(np.isfinite(value) for value in values):
        return None
    return values


def _build_dig_cut_token(fields: dict[str, float | int | str]) -> np.ndarray:
    entry_x = float(fields.get("operator_entry_x_m", 0.0))
    entry_z = float(fields.get("operator_entry_z_m", 0.0))
    exit_x = float(fields.get("operator_exit_x_m", 0.0))
    exit_z = float(fields.get("operator_exit_z_m", 0.0))
    token = np.asarray(
        [
            _clip_norm(entry_x, DIG_CUT_POSITION_SCALE_M),
            _clip_norm(entry_z, DIG_CUT_POSITION_SCALE_M),
            _clip_norm(exit_x, DIG_CUT_POSITION_SCALE_M),
            _clip_norm(exit_z, DIG_CUT_POSITION_SCALE_M),
            float(fields.get("operator_cut_direction_x", 0.0)),
            float(fields.get("operator_cut_direction_z", 0.0)),
            _clip_norm(float(fields.get("operator_cut_length_m", 0.0)), DIG_CUT_LENGTH_SCALE_M),
            _clip_norm(float(fields.get("operator_cut_depth_peak_m", 0.0)), DIG_CUT_DEPTH_SCALE_M),
            _clip_norm(float(fields.get("operator_cut_payload_gain_kg", 0.0)), DIG_CUT_PAYLOAD_SCALE_KG),
            1.0 if int(fields.get("operator_cut_valid", 0)) > 0 else 0.0,
        ],
        dtype=np.float32,
    )
    token[~np.isfinite(token)] = 0.0
    return token


def _build_return_target_token(
    cycle_payload: dict[str, np.ndarray],
    idx: int,
) -> np.ndarray:
    fields = {
        "operator_entry_x_m": float(cycle_payload["next_operator_entry_x_m"][idx]),
        "operator_entry_y_m": float(cycle_payload["next_operator_entry_y_m"][idx]),
        "operator_entry_z_m": float(cycle_payload["next_operator_entry_z_m"][idx]),
        "operator_exit_x_m": float(cycle_payload["next_operator_exit_x_m"][idx]),
        "operator_exit_y_m": float(cycle_payload["next_operator_exit_y_m"][idx]),
        "operator_exit_z_m": float(cycle_payload["next_operator_exit_z_m"][idx]),
        "operator_cut_direction_x": float(
            cycle_payload["next_operator_cut_direction_x"][idx]
        ),
        "operator_cut_direction_y": float(
            cycle_payload["next_operator_cut_direction_y"][idx]
        ),
        "operator_cut_direction_z": float(
            cycle_payload["next_operator_cut_direction_z"][idx]
        ),
        "operator_cut_length_m": float(
            cycle_payload["next_operator_cut_length_m"][idx]
        ),
        "operator_cut_depth_peak_m": float(
            cycle_payload["next_operator_cut_depth_peak_m"][idx]
        ),
        "operator_cut_payload_gain_kg": float(
            cycle_payload["next_operator_cut_payload_gain_kg"][idx]
        ),
        "operator_cut_valid": int(cycle_payload["next_operator_cut_valid"][idx]),
    }
    return _build_dig_cut_token(fields)


def _training_tier(
    *,
    payload_gain_kg: float,
    effective_deposit_delta_kg: float,
    cut_length_m: float,
    cut_depth_peak_m: float,
    depth_reliable: bool,
    valid: bool,
) -> str:
    if not valid or not depth_reliable:
        return "silver"
    if (
        payload_gain_kg >= 35.0
        and effective_deposit_delta_kg >= 5.0
        and cut_length_m >= 0.20
        and cut_depth_peak_m >= 0.02
    ):
        return "gold"
    return "silver"


def _actual_removed_depth_delta_max(
    env_state: np.ndarray,
    start: int,
    end: int,
) -> tuple[float, str]:
    if env_state.ndim != 2 or env_state.shape[1] < ENV_STATE_V2_2_DIM:
        return 0.0, "unavailable_or_legacy_zero"
    start = int(np.clip(start, 0, max(0, env_state.shape[0] - 1)))
    end = int(np.clip(end, start + 1, env_state.shape[0]))
    sl = slice(
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + REMOVED_DEPTH_GRID_CELL_COUNT,
    )
    baseline = np.asarray(env_state[start, sl], dtype=np.float32)
    peak = np.nanmax(np.asarray(env_state[start:end, sl], dtype=np.float32), axis=0)
    delta = np.maximum(0.0, peak - baseline)
    if not np.isfinite(delta).all():
        return 0.0, "unavailable_or_legacy_zero"
    value = float(np.max(delta))
    if value <= REMOVED_DEPTH_DELTA_EPS_M:
        return 0.0, "unavailable_or_legacy_zero"
    return value, "env_state_removed_depth_delta"


def _cut_depth_semantic_peak(
    env_state: np.ndarray,
    start: int,
    end: int,
) -> tuple[float, str]:
    """Return the compact dig depth command carried by dig_cut_tokens[7].

    The command depth is a surface-relative penetration target when the repaired
    Unity geometry exposes it. Removed-depth deltas remain outcome/audit fields;
    they are no longer the default command-depth source.
    """
    local_surface = _range_max_single(
        env_state,
        start,
        end,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    )
    if np.isfinite(local_surface) and local_surface > REMOVED_DEPTH_DELTA_EPS_M:
        return float(local_surface), "env_state_surface_penetration"

    plane_depth = _range_max_single(
        env_state,
        start,
        end,
        ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    )
    if np.isfinite(plane_depth) and plane_depth > REMOVED_DEPTH_DELTA_EPS_M:
        return float(plane_depth), "env_state_plane_penetration_fallback"

    removed_depth, source = _actual_removed_depth_delta_max(env_state, start, end)
    if source == "env_state_removed_depth_delta":
        return float(removed_depth), "env_state_removed_depth_delta_fallback"
    return 0.0, "unavailable_or_legacy_zero"


def _range_max(
    env_state: np.ndarray,
    start: int,
    end: int,
    idx: int,
    *,
    fallback_idx: int | None = None,
) -> float:
    value = _range_max_single(env_state, start, end, idx)
    if np.isfinite(value):
        return value
    if fallback_idx is not None:
        return _range_max_single(env_state, start, end, fallback_idx)
    return 0.0


def _range_max_single(env_state: np.ndarray, start: int, end: int, idx: int) -> float:
    if env_state.ndim != 2 or env_state.shape[1] <= idx or end <= start:
        return np.nan
    values = np.asarray(env_state[start:end, idx], dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size <= 0:
        return np.nan
    return float(np.max(values))


def _mass_delta(env_state: np.ndarray, start: int, end: int, idx: int) -> float:
    if env_state.ndim != 2 or env_state.shape[1] <= idx or end <= start:
        return 0.0
    values = np.asarray(env_state[start:end, idx], dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size <= 0:
        return 0.0
    return float(np.max(values) - values[0])


def _deposit_delta(
    env_state: np.ndarray,
    start: int,
    end: int,
    *,
    preferred_idx: int,
) -> float:
    value = _mass_delta(env_state, start, end, preferred_idx)
    if value > 0.0:
        return value
    if env_state.ndim == 2 and env_state.shape[1] > ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX:
        return _mass_delta(
            env_state,
            start,
            end,
            ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
        )
    return value


def _first_mask_step(
    mask: np.ndarray | None,
    *,
    start: int,
    end: int,
    default: int,
) -> int:
    if mask is None:
        return int(default)
    arr = np.asarray(mask).reshape(-1)
    if arr.size < end:
        return int(default)
    indices = np.flatnonzero(arr[start:end] > 0)
    if indices.size <= 0:
        return int(default)
    return int(start + indices[0])


def _cycle_scalar_float(
    cycle: dict[str, np.ndarray],
    key: str,
    idx: int,
    *,
    default: float,
) -> float:
    if key not in cycle:
        return float(default)
    arr = np.asarray(cycle[key]).reshape(-1)
    if idx < 0 or idx >= arr.size:
        return float(default)
    try:
        return float(arr[idx])
    except (TypeError, ValueError):
        return float(default)


def _cycle_scalar_int(
    cycle: dict[str, np.ndarray],
    key: str,
    idx: int,
    *,
    default: int,
) -> int:
    value = _cycle_scalar_float(cycle, key, idx, default=float(default))
    if not np.isfinite(value):
        return int(default)
    return int(round(value))


def _direction(
    entry_pose: tuple[float, float, float],
    exit_pose: tuple[float, float, float],
) -> tuple[float, float, float]:
    delta = tuple(float(exit_pose[axis]) - float(entry_pose[axis]) for axis in range(3))
    norm = _norm(delta)
    if not np.isfinite(norm) or norm <= 1e-6:
        return (0.0, 0.0, 0.0)
    return tuple(float(value) / norm for value in delta)


def _distance(
    entry_pose: tuple[float, float, float],
    exit_pose: tuple[float, float, float],
) -> float:
    return _norm(
        tuple(float(exit_pose[axis]) - float(entry_pose[axis]) for axis in range(3))
    )


def _norm(values: tuple[float, ...]) -> float:
    arr = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(arr)):
        return float("nan")
    return float(np.linalg.norm(arr))


def _clip_norm(value: float, scale: float) -> float:
    if not np.isfinite(value):
        return 0.0
    if scale <= 0.0:
        return 0.0
    return float(np.clip(float(value) / float(scale), -1.0, 1.0))


def _build_episode_summary(
    *,
    source_episode: str,
    n_steps: int,
    windows: list[CycleWindow],
    cycle_payload: dict[str, np.ndarray],
    old_cycle: dict[str, np.ndarray],
) -> dict[str, Any]:
    legacy_matches = int(
        np.sum(np.asarray(old_cycle.get("cell_entry_target_cell_match", []), dtype=np.uint8))
    )
    tier_counts = Counter(str(value) for value in cycle_payload["training_tier"])
    return_target_source_counts = Counter(
        str(value) for value in cycle_payload["return_target_source"]
    )
    return {
        "source_episode": str(source_episode),
        "episode_len": int(n_steps),
        "cycle_count": int(len(windows)),
        "legacy_cell_entry_target_cell_match_count": int(legacy_matches),
        "training_tier_counts": dict(sorted(tier_counts.items())),
        "return_target_source_counts": dict(
            sorted(return_target_source_counts.items())
        ),
        "effective_deposit_delta_kg": _numeric_stats(
            cycle_payload["cycle_effective_deposit_delta_kg"]
        ),
        "legacy_dump_end_deposit_delta_kg": _numeric_stats(
            cycle_payload["legacy_dump_end_deposit_delta_kg"]
        ),
        "operator_cut_payload_gain_kg": _numeric_stats(
            cycle_payload["operator_cut_payload_gain_kg"]
        ),
        "operator_cut_length_m": _numeric_stats(cycle_payload["operator_cut_length_m"]),
        "operator_cut_depth_peak_m": _numeric_stats(
            cycle_payload["operator_cut_depth_peak_m"]
        ),
        "operator_cut_depth_source_counts": dict(
            sorted(
                Counter(
                    str(value) for value in cycle_payload["operator_cut_depth_source"]
                ).items()
            )
        ),
        "operator_cut_depth_token_stats": _depth_token_stats(
            cycle_payload["operator_cut_depth_peak_m"]
        ),
    }


def _build_dataset_summary(
    *,
    dataset_dir: Path,
    output_dir: Path,
    storage_mode: str,
    episode_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    cycle_count = sum(int(item.get("cycle_count", 0)) for item in episode_summaries)
    tier_counts: Counter[str] = Counter()
    for item in episode_summaries:
        tier_counts.update(dict(item.get("training_tier_counts", {}) or {}))
    return {
        "version": OPERATOR_FIRST_VERSION,
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "storage_mode": str(storage_mode),
        "episode_count": int(len(episode_summaries)),
        "cycle_count": int(cycle_count),
        "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
        "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "dig_cut_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
        "dig_cut_depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
        "training_tier_counts": dict(sorted(tier_counts.items())),
        "operator_cut_depth_source_counts": _aggregate_counter(
            episode_summaries,
            "operator_cut_depth_source_counts",
        ),
        "operator_cut_depth_token_stats": _aggregate_depth_token_stats(
            episode_summaries,
            "operator_cut_depth_token_stats",
        ),
        "return_target_source_counts": _aggregate_counter(
            episode_summaries,
            "return_target_source_counts",
        ),
        "effective_deposit_delta_kg": _aggregate_numeric(
            episode_summaries,
            "effective_deposit_delta_kg",
        ),
        "legacy_rule_alignment": {
            "cell_entry_fields_preserved": True,
            "cell_entry_is_reject_gate": False,
            "deposit_delta_kg_overwritten": False,
        },
        "episodes": episode_summaries,
    }


def _numeric_stats(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size <= 0:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "median": None,
            "p90": None,
            "max": None,
        }
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "p10": float(np.percentile(arr, 10)),
        "median": float(np.median(arr)),
        "p90": float(np.percentile(arr, 90)),
        "max": float(np.max(arr)),
    }


def _depth_token_stats(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size <= 0:
        return {
            "count": 0,
            "scale_m": float(DIG_CUT_DEPTH_SCALE_M),
            "p10": None,
            "p50": None,
            "p90": None,
            "saturation_rate": None,
        }
    norm = np.clip(arr / float(DIG_CUT_DEPTH_SCALE_M), -1.0, 1.0)
    return {
        "count": int(arr.size),
        "scale_m": float(DIG_CUT_DEPTH_SCALE_M),
        "p10": float(np.percentile(norm, 10)),
        "p50": float(np.percentile(norm, 50)),
        "p90": float(np.percentile(norm, 90)),
        "saturation_rate": float(np.mean(np.abs(norm) >= 0.999)),
    }


def _aggregate_numeric(
    episode_summaries: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    count = sum(int(item.get(key, {}).get("count", 0)) for item in episode_summaries)
    medians = [
        float(item[key]["median"])
        for item in episode_summaries
        if item.get(key, {}).get("median") is not None
    ]
    max_values = [
        float(item[key]["max"])
        for item in episode_summaries
        if item.get(key, {}).get("max") is not None
    ]
    return {
        "count": int(count),
        "episode_median_of_medians": None
        if not medians
        else float(np.median(np.asarray(medians, dtype=np.float32))),
        "episode_max": None
        if not max_values
        else float(np.max(np.asarray(max_values, dtype=np.float32))),
    }


def _aggregate_depth_token_stats(
    episode_summaries: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    values = [
        float(item[key][name])
        for item in episode_summaries
        if item.get(key, {}).get("count", 0)
        for name in ("p10", "p50", "p90", "saturation_rate")
        if item.get(key, {}).get(name) is not None
    ]
    if not values:
        return {
            "scale_m": float(DIG_CUT_DEPTH_SCALE_M),
            "episode_count": 0,
        }
    summaries = [item[key] for item in episode_summaries if item.get(key, {}).get("count", 0)]
    return {
        "scale_m": float(DIG_CUT_DEPTH_SCALE_M),
        "episode_count": int(len(summaries)),
        "episode_median_p10": float(np.median([float(s["p10"]) for s in summaries])),
        "episode_median_p50": float(np.median([float(s["p50"]) for s in summaries])),
        "episode_median_p90": float(np.median([float(s["p90"]) for s in summaries])),
        "episode_max_saturation_rate": float(
            np.max([float(s["saturation_rate"]) for s in summaries])
        ),
    }


def _aggregate_counter(
    episode_summaries: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in episode_summaries:
        counts.update(dict(item.get(key, {}) or {}))
    return {str(name): int(value) for name, value in sorted(counts.items())}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value
