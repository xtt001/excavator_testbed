"""Helpers for building cropped V2.1 transition-skill datasets."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.hdf5_io import episode_id_from_path, list_episodes, read_episode, write_episode
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)


TRANSITION_RECORDING_MODE = "transition_relabel"
TRANSITION_WINDOW_NAME = "dump_end_to_next_qualified_dig_start"
PAUSE_ACTION_L1_EPS = 0.05
CLEAN_PROFILE_STAGE5 = "stage5"
STAGE5_DEFAULT_MAX_TRANSITION_LEN = 420
STAGE5_MAX_PAUSE_RATIO = 0.12
STAGE5_LATE_QDS_MAX_DELAY_STEPS = 60
STAGE5_PROGRESS_MASS_THRESH_KG = 40.0
STAGE5_PROGRESS_DIG_TOUCH_TOL_M = 0.05
STAGE5_PROGRESS_BUCKET_DEPTH_TOL_M = 0.02


@dataclass(frozen=True)
class TransitionSlice:
    source_episode_id: int
    prev_cycle_id: int
    next_cycle_id: int
    dump_end_step: int
    next_start_step: int


@dataclass(frozen=True)
class TransitionRejectRecord:
    reason: str
    source_episode_id: int
    prev_cycle_id: int
    next_cycle_id: int
    window_len: int
    gap_steps: int
    pause_ratio: float
    first_progress_offset: int | None


@dataclass(frozen=True)
class _TransitionWindowDiagnostics:
    window_len: int
    gap_steps: int
    pause_ratio: float
    first_progress_offset: int | None


def build_transition_dataset(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    max_transition_len: int | None = None,
    clean_profile: str | None = None,
) -> int:
    """Build a sibling cropped transition dataset from a relabeled V2.1 dataset."""
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    clean_profile = _normalise_clean_profile(clean_profile)
    effective_max_transition_len = _effective_max_transition_len(
        max_transition_len=max_transition_len,
        clean_profile=clean_profile,
    )

    episode_paths = list_episodes(dataset_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")

    existing_outputs = list_episodes(output_dir) if output_dir.exists() else []
    if existing_outputs:
        raise FileExistsError(
            f"Output directory {output_dir} already contains episode files. "
            "Use a fresh sibling directory for transition builds."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    input_window_lengths: list[int] = []
    kept_window_lengths: list[int] = []
    input_gap_steps: list[int] = []
    kept_gap_steps: list[int] = []
    reject_reason_counts: Counter[str] = Counter()
    for source_path in episode_paths:
        episode = read_episode(source_path)
        transition_slices, rejected = extract_transition_slices(
            episode=episode,
            source_path=source_path,
            max_transition_len=effective_max_transition_len,
            clean_profile=clean_profile,
        )
        for rejected_window in rejected:
            input_window_lengths.append(int(rejected_window.window_len))
            input_gap_steps.append(int(rejected_window.gap_steps))
            reject_reason_counts.update([str(rejected_window.reason)])
        for transition_slice in transition_slices:
            input_window_lengths.append(
                int(transition_slice.next_start_step - transition_slice.dump_end_step + 1)
            )
            input_gap_steps.append(
                int(transition_slice.next_start_step - transition_slice.dump_end_step)
            )
            kept_window_lengths.append(
                int(transition_slice.next_start_step - transition_slice.dump_end_step + 1)
            )
            kept_gap_steps.append(
                int(transition_slice.next_start_step - transition_slice.dump_end_step)
            )
            target_path = output_dir / f"episode_{written}.hdf5"
            write_transition_episode(
                target_path=target_path,
                source_episode=episode,
                source_dataset_dir=dataset_dir,
                transition_slice=transition_slice,
                output_episode_id=written,
            )
            written += 1

    _write_transition_build_summary(
        output_dir=output_dir,
        dataset_dir=dataset_dir,
        output_episode_count=written,
        clean_profile=clean_profile,
        max_transition_len=effective_max_transition_len,
        input_episode_count=len(episode_paths),
        input_window_lengths=input_window_lengths,
        kept_window_lengths=kept_window_lengths,
        input_gap_steps=input_gap_steps,
        kept_gap_steps=kept_gap_steps,
        reject_reason_counts=reject_reason_counts,
    )
    if written <= 0:
        raise RuntimeError(
            f"No transition windows found under {dataset_dir}. "
            "Refusing to create an empty transition dataset."
        )
    return written


def extract_transition_slices(
    *,
    episode: dict[str, Any],
    source_path: str | Path,
    max_transition_len: int | None = None,
    clean_profile: str | None = None,
) -> tuple[list[TransitionSlice], list[TransitionRejectRecord]]:
    v2 = episode.get("v2")
    if not v2:
        raise KeyError(
            f"Episode {Path(source_path).name} is missing /v2 labels. "
            "Run tb-label-v2_1 first."
        )

    cycle_data = dict(v2.get("cycle", {}))
    required_keys = ("cycle_id", "start_step", "dump_end_step")
    missing = [key for key in required_keys if key not in cycle_data]
    if missing:
        raise KeyError(
            f"Episode {Path(source_path).name} has incomplete /v2/cycle data; "
            f"missing {missing}."
        )

    cycle_success = cycle_data.get("cycle_success")
    source_episode_id = episode_id_from_path(Path(source_path))
    cycle_ids = [int(x) for x in cycle_data["cycle_id"]]
    start_steps = [int(x) for x in cycle_data["start_step"]]
    dump_end_steps = [int(x) for x in cycle_data["dump_end_step"]]

    transition_slices: list[TransitionSlice] = []
    rejected: list[TransitionRejectRecord] = []
    for index in range(len(cycle_ids) - 1):
        prev_cycle_id = cycle_ids[index]
        next_cycle_id = cycle_ids[index + 1]
        dump_end_step = dump_end_steps[index]
        next_start_step = start_steps[index + 1]
        if cycle_success is not None and int(cycle_success[index]) != 1:
            continue
        if dump_end_step < 0 or next_start_step <= dump_end_step:
            continue
        diagnostics = _diagnose_transition_window(
            episode=episode,
            dump_end_step=dump_end_step,
            next_start_step=next_start_step,
        )
        reject_reason = _reject_reason_for_transition_window(
            diagnostics=diagnostics,
            max_transition_len=max_transition_len,
            clean_profile=clean_profile,
        )
        if reject_reason is not None:
            rejected.append(
                TransitionRejectRecord(
                    reason=reject_reason,
                    source_episode_id=source_episode_id,
                    prev_cycle_id=prev_cycle_id,
                    next_cycle_id=next_cycle_id,
                    window_len=int(diagnostics.window_len),
                    gap_steps=int(diagnostics.gap_steps),
                    pause_ratio=float(diagnostics.pause_ratio),
                    first_progress_offset=(
                        None
                        if diagnostics.first_progress_offset is None
                        else int(diagnostics.first_progress_offset)
                    ),
                )
            )
            continue
        transition_slices.append(
            TransitionSlice(
                source_episode_id=source_episode_id,
                prev_cycle_id=prev_cycle_id,
                next_cycle_id=next_cycle_id,
                dump_end_step=dump_end_step,
                next_start_step=next_start_step,
            )
        )
    return transition_slices, rejected


def write_transition_episode(
    *,
    target_path: str | Path,
    source_episode: dict[str, Any],
    source_dataset_dir: str | Path,
    transition_slice: TransitionSlice,
    output_episode_id: int,
) -> None:
    start = int(transition_slice.dump_end_step)
    end = int(transition_slice.next_start_step) + 1
    crop = slice(start, end)
    window_len = end - start
    if window_len <= 0:
        raise ValueError("Transition slice must contain at least one timestep.")

    metadata = dict(source_episode.get("metadata", {}))
    metadata.update(
        {
            "episode_id": f"episode_{output_episode_id}",
            "recording_mode": TRANSITION_RECORDING_MODE,
            "source_dataset_dir": str(Path(source_dataset_dir).resolve()),
            "source_episode_id": f"episode_{transition_slice.source_episode_id}",
            "source_prev_cycle_id": int(transition_slice.prev_cycle_id),
            "source_next_cycle_id": int(transition_slice.next_cycle_id),
            "source_dump_end_step": int(transition_slice.dump_end_step),
            "source_next_start_step": int(transition_slice.next_start_step),
            "transition_window": TRANSITION_WINDOW_NAME,
        }
    )

    images = {
        camera_name: np.asarray(camera_frames[crop])
        for camera_name, camera_frames in dict(source_episode.get("images", {})).items()
    }

    v2_payload = build_transition_v2_payload(
        source_episode=source_episode,
        prev_cycle_id=int(transition_slice.prev_cycle_id),
        crop=crop,
    )

    write_episode(
        target_path,
        qpos=np.asarray(source_episode["qpos"][crop], dtype=np.float32),
        qvel=np.asarray(source_episode["qvel"][crop], dtype=np.float32),
        actions=np.asarray(source_episode["actions"][crop], dtype=np.float32),
        images=images or None,
        rewards=_slice_optional_array(source_episode.get("rewards"), crop),
        metadata=metadata,
        env_state=_slice_optional_array(source_episode.get("env_state"), crop),
        step_ids=_slice_optional_array(source_episode.get("step_ids"), crop, dtype=np.int64),
        step_ns=_slice_optional_array(source_episode.get("step_ns"), crop, dtype=np.int64),
        action_src_types=_slice_optional_list(source_episode.get("action_src_types"), crop),
        action_src_ids=_slice_optional_list(source_episode.get("action_src_ids"), crop),
        v2=v2_payload,
    )


def build_transition_v2_payload(
    *,
    source_episode: dict[str, Any],
    prev_cycle_id: int,
    crop: slice,
) -> dict[str, dict[str, np.ndarray]]:
    v2 = source_episode.get("v2")
    if not v2:
        raise KeyError("Source episode is missing /v2 data.")

    step_payload = {
        key: np.asarray(value[crop])
        for key, value in dict(v2.get("step", {})).items()
    }
    if not step_payload:
        raise KeyError("Source episode /v2/step is empty.")
    if "cycle_id" in step_payload:
        step_payload["cycle_id"] = (
            np.asarray(step_payload["cycle_id"], dtype=np.int32) - int(prev_cycle_id)
        ).astype(np.int32)

    return {
        "step": step_payload,
        "cycle": {},
    }


def _slice_optional_array(
    value: Any,
    crop: slice,
    *,
    dtype: np.dtype | None = np.float32,
) -> np.ndarray | None:
    if value is None:
        return None
    arr = np.asarray(value[crop])
    if dtype is not None:
        arr = arr.astype(dtype)
    return arr


def _slice_optional_list(value: list[str] | None, crop: slice) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value[crop]]


def _normalise_clean_profile(clean_profile: str | None) -> str:
    value = "" if clean_profile in (None, "") else str(clean_profile).strip().lower()
    if value not in ("", CLEAN_PROFILE_STAGE5):
        raise ValueError(
            f"Unsupported clean_profile {clean_profile!r}. "
            f"Expected {CLEAN_PROFILE_STAGE5!r} or empty."
        )
    return value


def _effective_max_transition_len(
    *,
    max_transition_len: int | None,
    clean_profile: str,
) -> int | None:
    if max_transition_len is not None:
        return int(max_transition_len)
    if clean_profile == CLEAN_PROFILE_STAGE5:
        return int(STAGE5_DEFAULT_MAX_TRANSITION_LEN)
    return None


def _diagnose_transition_window(
    *,
    episode: dict[str, Any],
    dump_end_step: int,
    next_start_step: int,
) -> _TransitionWindowDiagnostics:
    start = int(dump_end_step)
    end = int(next_start_step) + 1
    crop = slice(start, end)
    window_len = int(end - start)
    gap_steps = int(next_start_step - dump_end_step)

    actions = np.asarray(episode.get("actions", np.zeros((window_len, 4), dtype=np.float32)))[crop]
    if actions.ndim != 2 or actions.shape[0] != window_len:
        actions = np.zeros((window_len, 4), dtype=np.float32)
    pause_ratio = float(np.mean(np.sum(np.abs(actions), axis=1) < PAUSE_ACTION_L1_EPS))

    env_state = episode.get("env_state")
    first_progress_offset: int | None = None
    if env_state is not None:
        env_arr = np.asarray(env_state, dtype=np.float32)[crop]
        if env_arr.ndim == 2 and env_arr.shape[0] == window_len:
            mass_in_bucket = env_arr[:, ENV_STATE_MASS_IN_BUCKET_IDX]
            min_distance_to_dig_area = env_arr[:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX]
            bucket_depth = env_arr[:, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
            progress_mask = (
                (mass_in_bucket >= STAGE5_PROGRESS_MASS_THRESH_KG)
                | (
                    (min_distance_to_dig_area <= STAGE5_PROGRESS_DIG_TOUCH_TOL_M)
                    & (bucket_depth >= STAGE5_PROGRESS_BUCKET_DEPTH_TOL_M)
                )
            )
            if window_len > 1:
                candidate_mask = progress_mask[:-1]
                if np.any(candidate_mask):
                    first_progress_offset = int(np.argmax(candidate_mask))

    return _TransitionWindowDiagnostics(
        window_len=window_len,
        gap_steps=gap_steps,
        pause_ratio=pause_ratio,
        first_progress_offset=first_progress_offset,
    )


def _reject_reason_for_transition_window(
    *,
    diagnostics: _TransitionWindowDiagnostics,
    max_transition_len: int | None,
    clean_profile: str,
) -> str | None:
    if max_transition_len is not None and diagnostics.window_len > int(max_transition_len):
        return "overlong_transition_len"

    if clean_profile != CLEAN_PROFILE_STAGE5:
        return None

    if diagnostics.pause_ratio > STAGE5_MAX_PAUSE_RATIO:
        return "high_pause_ratio"

    if diagnostics.first_progress_offset is not None:
        trailing_delay = int(diagnostics.window_len - 1 - diagnostics.first_progress_offset)
        if trailing_delay > STAGE5_LATE_QDS_MAX_DELAY_STEPS:
            return "late_qds_failure"

    return None


def _describe_distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "min": 0,
            "max": 0,
            "mean": 0.0,
            "median": 0.0,
        }
    arr = np.asarray(values, dtype=np.float32)
    return {
        "count": int(arr.size),
        "min": int(np.min(arr)),
        "max": int(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
    }


def _write_transition_build_summary(
    *,
    output_dir: Path,
    dataset_dir: Path,
    output_episode_count: int,
    clean_profile: str,
    max_transition_len: int | None,
    input_episode_count: int,
    input_window_lengths: list[int],
    kept_window_lengths: list[int],
    input_gap_steps: list[int],
    kept_gap_steps: list[int],
    reject_reason_counts: Counter[str],
) -> None:
    payload = {
        "source_dataset_dir": str(dataset_dir.resolve()),
        "output_dataset_dir": str(output_dir.resolve()),
        "input_episode_count": int(input_episode_count),
        "input_transition_window_count": int(len(input_window_lengths)),
        "output_episode_count": int(output_episode_count),
        "clean_profile": clean_profile or "none",
        "max_transition_len": None if max_transition_len is None else int(max_transition_len),
        "reject_reason_counts": dict(sorted(reject_reason_counts.items())),
        "input_length_distribution": _describe_distribution(input_window_lengths),
        "kept_length_distribution": _describe_distribution(kept_window_lengths),
        "input_gap_distribution": _describe_distribution(input_gap_steps),
        "kept_gap_distribution": _describe_distribution(kept_gap_steps),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2))
