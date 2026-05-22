"""V2.4 outcome-grounded hindsight goal enrichment.

The professional YuLong data was recorded naturally, without live goal tokens.
This builder therefore keeps the original operator-first targets intact and
adds hindsight outcome targets derived from what the operator actually did.
Those fields can be written either into materialized copy HDF5 episodes or into
image-VDS wrappers.  The VDS path is preferred for intermediate relabel roots:
it writes only the add-only hindsight fields locally while keeping large image
datasets backed by the canonical source episodes.
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
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_CONTRACT,
    OPERATOR_FIRST_VERSION,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.schema import (
    ATTR_GOAL_TOKEN_DIM,
    DS_V2_CYCLE_ACTUAL_REMOVED_DEPTH_DELTA_GRID,
    DS_V2_CYCLE_DEPTH_OUTCOME_SOURCE,
    DS_V2_CYCLE_DIG_OUTCOME_EFFECTIVE_DEPOSIT_DELTA_KG,
    DS_V2_CYCLE_DIG_OUTCOME_PAYLOAD_GAIN_KG,
    DS_V2_CYCLE_DOMINANT_REMOVED_DEPTH_CELL_ID,
    DS_V2_CYCLE_HANDOFF_OUTCOME_SOURCE,
    DS_V2_CYCLE_RETURN_OUTCOME_ENTRY_DELTA_NORM_M,
    DS_V2_STEP_DIG_GOAL_VALID_MASK,
    DS_V2_STEP_DIG_OUTCOME_TARGETS,
    DS_V2_STEP_RETURN_GOAL_VALID_MASK,
    DS_V2_STEP_RETURN_OUTCOME_TARGETS,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_V2_2_DIM,
)
from testbed.data.vds import STORAGE_MODE_COPY, STORAGE_MODE_VDS, write_lineage_json, write_vds_episode


HINDSIGHT_GOAL_VERSION = "v2_4_hindsight_goal_v1"
HINDSIGHT_GOAL_TOKEN_CONTRACT = DIG_CUT_TOKEN_CONTRACT
DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH = "env_state_removed_depth_delta"
DEPTH_OUTCOME_SOURCE_UNAVAILABLE = "unavailable_or_legacy_zero"
HANDOFF_OUTCOME_SOURCE_OPERATOR_FIRST = "operator_first_cycle_fields"

_GRID_CELL_COUNT = 6
_DEPTH_DELTA_EPS_M = 1.0e-4


@dataclass(frozen=True)
class CycleWindow:
    cycle_id: int
    index: int
    start_step: int
    end_step_exclusive: int


def build_hindsight_goal_dataset(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
    storage_mode: str = STORAGE_MODE_COPY,
) -> dict[str, Any]:
    """Build a V2.4 hindsight-goal relabel root."""
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    storage_mode = str(storage_mode).strip().lower()
    if storage_mode not in {STORAGE_MODE_COPY, STORAGE_MODE_VDS}:
        raise ValueError(
            f"Unsupported storage_mode {storage_mode!r}; expected copy or vds."
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
        episode = read_episode(source_path, load_images=(storage_mode == STORAGE_MODE_COPY))
        enriched_v2, summary = enrich_episode_hindsight_goal(
            episode=episode,
            source_episode=str(source_path),
        )
        metadata = dict(episode.get("metadata", {}) or {})
        metadata.update(
            {
                "hindsight_goal_version": HINDSIGHT_GOAL_VERSION,
                "hindsight_goal_storage_mode": storage_mode,
                "storage_mode": storage_mode,
                "hindsight_goal_token_contract": HINDSIGHT_GOAL_TOKEN_CONTRACT,
                "dig_cut_depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
                "dig_outcome_target_dim": int(DIG_CUT_TOKEN_DIM),
                "return_outcome_target_dim": int(RETURN_TARGET_TOKEN_DIM),
                "operator_first_version": metadata.get(
                    "operator_first_version",
                    OPERATOR_FIRST_VERSION,
                ),
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
                v2_step_overlay=_hindsight_step_overlay(enriched_v2),
                v2_cycle_payload=dict(enriched_v2.get("cycle", {})),
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
        episode_summaries=episode_summaries,
        storage_mode=storage_mode,
    )
    with open(output_dir / "hindsight_goal_summary.json", "w") as f:
        json.dump(_jsonable(summary_payload), f, indent=2, sort_keys=True)
    with open(output_dir / "summary.json", "w") as f:
        json.dump(_jsonable(summary_payload), f, indent=2, sort_keys=True)
    write_lineage_json(
        output_dir,
        builder="tb-build-hindsight-goal-v2_4",
        storage_mode=storage_mode,
        source_roots=[dataset_dir],
        input_dataset_ids=[dataset_dir.name],
        schema_versions={
            "hdf5": "1.1",
            "operator_first": OPERATOR_FIRST_VERSION,
            "hindsight_goal": HINDSIGHT_GOAL_VERSION,
        },
        extra={
            "hindsight_goal_token_contract": HINDSIGHT_GOAL_TOKEN_CONTRACT,
            "dig_cut_depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
            "dig_outcome_target_dim": int(DIG_CUT_TOKEN_DIM),
            "return_outcome_target_dim": int(RETURN_TARGET_TOKEN_DIM),
            "depth_delta_supervision": (
                "enabled only when env_state removed_depth delta is nonzero"
            ),
        },
    )
    return summary_payload


def _hindsight_step_overlay(v2_payload: dict[str, dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    """Return only add-only step fields that must be materialized locally."""
    step = dict(v2_payload.get("step", {}) or {})
    overlay: dict[str, np.ndarray] = {}
    for path in (
        DS_V2_STEP_DIG_OUTCOME_TARGETS,
        DS_V2_STEP_RETURN_OUTCOME_TARGETS,
        DS_V2_STEP_DIG_GOAL_VALID_MASK,
        DS_V2_STEP_RETURN_GOAL_VALID_MASK,
    ):
        key = str(path).rsplit("/", 1)[-1]
        if key in step:
            overlay[key] = step[key]
    return overlay


def enrich_episode_hindsight_goal(
    *,
    episode: dict[str, Any],
    source_episode: str = "",
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    """Return add-only V2.4 hindsight outcome fields for one episode."""
    actions = np.asarray(episode["actions"], dtype=np.float32)
    n_steps = int(actions.shape[0])
    v2_existing = dict(episode.get("v2") or {})
    step_existing = {
        str(key): np.asarray(value)
        for key, value in dict(v2_existing.get("step", {}) or {}).items()
    }
    cycle_existing = {
        str(key): np.asarray(value)
        for key, value in dict(v2_existing.get("cycle", {}) or {}).items()
    }
    if not step_existing:
        raise KeyError(f"{source_episode or '<episode>'} is missing /v2/step labels.")

    env_state = episode.get("env_state")
    env_arr = (
        np.asarray(env_state, dtype=np.float32)
        if env_state is not None
        else np.zeros((n_steps, 0), dtype=np.float32)
    )
    windows = _infer_cycle_windows(
        n_steps=n_steps,
        v2_step=step_existing,
        v2_cycle=cycle_existing,
    )

    dig_targets = _normalise_token_array(
        step_existing.get("dig_cut_tokens"),
        n_steps=n_steps,
        dim=DIG_CUT_TOKEN_DIM,
    )
    return_targets = _normalise_token_array(
        step_existing.get("return_target_tokens"),
        n_steps=n_steps,
        dim=RETURN_TARGET_TOKEN_DIM,
    )
    dig_valid = _token_valid_mask(dig_targets)
    return_valid = _token_valid_mask(return_targets)

    cycle_payload = dict(cycle_existing)
    depth_grid = np.zeros((len(windows), _GRID_CELL_COUNT), dtype=np.float32)
    dominant_cell = np.full((len(windows),), -1, dtype=np.int32)
    depth_source = np.full(
        (len(windows),),
        DEPTH_OUTCOME_SOURCE_UNAVAILABLE,
        dtype=f"<U{max(len(DEPTH_OUTCOME_SOURCE_UNAVAILABLE), len(DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH))}",
    )
    for idx, window in enumerate(windows):
        delta, source = _removed_depth_delta_for_window(env_arr, window)
        depth_grid[idx] = delta
        if source == DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH:
            dominant_cell[idx] = int(np.argmax(delta))
        depth_source[idx] = source
    _apply_actual_removed_depth_to_targets(
        dig_targets=dig_targets,
        return_targets=return_targets,
        windows=windows,
        depth_grid=depth_grid,
        depth_source=depth_source,
    )
    dig_valid = _token_valid_mask(dig_targets)
    return_valid = _token_valid_mask(return_targets)

    step_payload = dict(step_existing)
    step_payload.update(
        {
            "dig_outcome_targets": dig_targets,
            "return_outcome_targets": return_targets,
            "dig_goal_valid_mask": dig_valid,
            "return_goal_valid_mask": return_valid,
        }
    )
    cycle_payload.update(
        {
            "actual_removed_depth_delta_grid": depth_grid,
            "dominant_removed_depth_cell_id": dominant_cell,
            "depth_outcome_source": depth_source,
            "dig_outcome_payload_gain_kg": _cycle_float_field(
                cycle_existing,
                "operator_cut_payload_gain_kg",
                fallback="payload_gain_kg",
                length=len(windows),
            ),
            "dig_outcome_effective_deposit_delta_kg": _cycle_float_field(
                cycle_existing,
                "cycle_effective_deposit_delta_kg",
                fallback="deposit_delta_kg",
                length=len(windows),
            ),
            "return_outcome_entry_delta_norm_m": _cycle_float_field(
                cycle_existing,
                "return_entry_delta_norm_m",
                fallback=None,
                length=len(windows),
                default=np.nan,
            ),
            "handoff_outcome_source": np.full(
                (len(windows),),
                HANDOFF_OUTCOME_SOURCE_OPERATOR_FIRST,
                dtype=f"<U{len(HANDOFF_OUTCOME_SOURCE_OPERATOR_FIRST)}",
            ),
        }
    )

    summary = {
        "source_episode": source_episode,
        "n_steps": int(n_steps),
        "cycle_count": int(len(windows)),
        "dig_goal_valid_steps": int((dig_valid[:, 0] > 0).sum()),
        "return_goal_valid_steps": int((return_valid[:, 0] > 0).sum()),
        "depth_outcome_source_counts": dict(
            Counter(str(value) for value in depth_source.tolist())
        ),
        "dominant_removed_depth_cell_counts": dict(
            Counter(int(value) for value in dominant_cell.tolist())
        ),
        "training_tier_counts": _training_tier_counts(cycle_existing),
    }
    return {"step": step_payload, "cycle": cycle_payload}, summary


def _infer_cycle_windows(
    *,
    n_steps: int,
    v2_step: dict[str, np.ndarray],
    v2_cycle: dict[str, np.ndarray],
) -> list[CycleWindow]:
    cycle_ids = np.asarray(v2_cycle.get("cycle_id", []), dtype=np.int32).reshape(-1)
    starts = np.asarray(v2_cycle.get("start_step", []), dtype=np.int32).reshape(-1)
    ends = np.asarray(v2_cycle.get("end_step", []), dtype=np.int32).reshape(-1)
    if len(cycle_ids) and len(starts) == len(cycle_ids) and len(ends) == len(cycle_ids):
        windows: list[CycleWindow] = []
        for idx, cycle_id in enumerate(cycle_ids):
            start = int(np.clip(starts[idx], 0, max(0, n_steps - 1)))
            end = int(np.clip(ends[idx] + 1, start + 1, n_steps))
            windows.append(
                CycleWindow(
                    cycle_id=int(cycle_id),
                    index=int(idx),
                    start_step=start,
                    end_step_exclusive=end,
                )
            )
        return windows

    step_cycle = np.asarray(v2_step.get("cycle_id", []), dtype=np.int32).reshape(-1)
    windows = []
    for idx, cycle_id in enumerate(sorted(int(c) for c in np.unique(step_cycle) if c >= 0)):
        positions = np.flatnonzero(step_cycle == cycle_id)
        if len(positions) == 0:
            continue
        windows.append(
            CycleWindow(
                cycle_id=int(cycle_id),
                index=int(idx),
                start_step=int(positions[0]),
                end_step_exclusive=int(positions[-1]) + 1,
            )
        )
    return windows


def _normalise_token_array(
    value: Any,
    *,
    n_steps: int,
    dim: int,
) -> np.ndarray:
    if value is None:
        return np.zeros((n_steps, dim), dtype=np.float32)
    arr = np.asarray(value, dtype=np.float32)
    if arr.shape != (n_steps, dim):
        raise ValueError(f"Expected token shape {(n_steps, dim)}, got {arr.shape}.")
    return arr.copy()


def _token_valid_mask(tokens: np.ndarray) -> np.ndarray:
    valid = np.isfinite(tokens).all(axis=1) & (tokens[:, -1] > 0.5)
    mask = np.zeros(tokens.shape, dtype=np.uint8)
    mask[valid] = 1
    return mask


def _apply_actual_removed_depth_to_targets(
    *,
    dig_targets: np.ndarray,
    return_targets: np.ndarray,
    windows: list[CycleWindow],
    depth_grid: np.ndarray,
    depth_source: np.ndarray,
) -> None:
    for idx, window in enumerate(windows):
        start = max(0, min(int(window.start_step), dig_targets.shape[0]))
        end = max(start, min(int(window.end_step_exclusive), dig_targets.shape[0]))
        reliable = (
            idx < len(depth_source)
            and str(depth_source[idx]) == DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH
        )
        if reliable:
            depth_m = float(np.max(depth_grid[idx]))
            depth_norm = _clip_depth_norm(depth_m)
            dig_targets[start:end, 7] = depth_norm
        else:
            dig_targets[start:end, -1] = 0.0

        if idx > 0:
            prev = windows[idx - 1]
            prev_start = max(0, min(int(prev.start_step), return_targets.shape[0]))
            prev_end = max(
                prev_start,
                min(int(prev.end_step_exclusive), return_targets.shape[0]),
            )
            if reliable:
                return_targets[prev_start:prev_end, 7] = _clip_depth_norm(
                    float(np.max(depth_grid[idx]))
                )
            else:
                return_targets[prev_start:prev_end, -1] = 0.0


def _clip_depth_norm(depth_m: float) -> float:
    if not np.isfinite(depth_m) or DIG_CUT_DEPTH_SCALE_M <= 0:
        return 0.0
    return float(np.clip(float(depth_m) / float(DIG_CUT_DEPTH_SCALE_M), -1.0, 1.0))


def _removed_depth_delta_for_window(
    env_state: np.ndarray,
    window: CycleWindow,
) -> tuple[np.ndarray, str]:
    delta = np.zeros((_GRID_CELL_COUNT,), dtype=np.float32)
    if env_state.ndim != 2 or env_state.shape[1] < ENV_STATE_V2_2_DIM:
        return delta, DEPTH_OUTCOME_SOURCE_UNAVAILABLE
    start = int(np.clip(window.start_step, 0, max(0, env_state.shape[0] - 1)))
    end = int(np.clip(window.end_step_exclusive, start + 1, env_state.shape[0]))
    sl = slice(
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + _GRID_CELL_COUNT,
    )
    baseline = np.asarray(env_state[start, sl], dtype=np.float32)
    peak = np.nanmax(np.asarray(env_state[start:end, sl], dtype=np.float32), axis=0)
    delta = np.maximum(0.0, peak - baseline).astype(np.float32)
    if not np.isfinite(delta).all() or float(np.max(delta)) <= _DEPTH_DELTA_EPS_M:
        return np.zeros((_GRID_CELL_COUNT,), dtype=np.float32), DEPTH_OUTCOME_SOURCE_UNAVAILABLE
    return delta, DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH


def _cycle_float_field(
    cycle: dict[str, np.ndarray],
    name: str,
    *,
    fallback: str | None,
    length: int,
    default: float = 0.0,
) -> np.ndarray:
    source = cycle.get(name)
    if source is None and fallback is not None:
        source = cycle.get(fallback)
    if source is None:
        return np.full((length,), float(default), dtype=np.float32)
    arr = np.asarray(source, dtype=np.float32).reshape(-1)
    out = np.full((length,), float(default), dtype=np.float32)
    take = min(length, int(arr.shape[0]))
    if take:
        out[:take] = arr[:take]
    return out


def _training_tier_counts(cycle: dict[str, np.ndarray]) -> dict[str, int]:
    if "training_tier" not in cycle:
        return {}
    values = np.asarray(cycle["training_tier"]).reshape(-1)
    return dict(Counter(str(value) for value in values.tolist()))


def _build_dataset_summary(
    *,
    dataset_dir: Path,
    output_dir: Path,
    episode_summaries: list[dict[str, Any]],
    storage_mode: str,
) -> dict[str, Any]:
    depth_counter: Counter[str] = Counter()
    tier_counter: Counter[str] = Counter()
    dominant_counter: Counter[int] = Counter()
    for summary in episode_summaries:
        depth_counter.update(summary.get("depth_outcome_source_counts", {}))
        tier_counter.update(summary.get("training_tier_counts", {}))
        dominant_counter.update(summary.get("dominant_removed_depth_cell_counts", {}))
    return {
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "storage_mode": str(storage_mode),
        "hindsight_goal_version": HINDSIGHT_GOAL_VERSION,
        "hindsight_goal_token_contract": HINDSIGHT_GOAL_TOKEN_CONTRACT,
        "dig_cut_depth_scale_m": float(DIG_CUT_DEPTH_SCALE_M),
        "episode_count": int(len(episode_summaries)),
        "cycle_count": int(sum(s.get("cycle_count", 0) for s in episode_summaries)),
        "dig_goal_valid_steps": int(
            sum(s.get("dig_goal_valid_steps", 0) for s in episode_summaries)
        ),
        "return_goal_valid_steps": int(
            sum(s.get("return_goal_valid_steps", 0) for s in episode_summaries)
        ),
        "depth_outcome_source_counts": dict(depth_counter),
        "dominant_removed_depth_cell_counts": {
            str(key): int(value) for key, value in dominant_counter.items()
        },
        "training_tier_counts": dict(tier_counter),
        "episodes": episode_summaries,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value
