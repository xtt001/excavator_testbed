"""Stage-3/5 helpers for building cropped V2.1 work-skill datasets."""

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
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)


WORKSKILL_RECORDING_MODE = "workskill_relabel"
WORKSKILL_WINDOW_NAME = "qualified_dig_start_to_dump_end"
CLEAN_PROFILE_STAGE5 = "stage5"
CLEAN_PROFILE_STAGE5_STRICT = "stage5_strict"
CLEAN_PROFILE_STAGE5_BALANCED = "stage5_balanced"
CLEAN_PROFILE_STAGE5_CLEANEST = "stage5_cleanest"
PAUSE_ACTION_L1_EPS = 0.05
STAGE5_MAX_WORKSKILL_PAUSE_RATIO = 0.12
STAGE5_MAX_QDS_BUCKET_QPOS = 0.20
STAGE5_MIN_PEAK_BUCKET_DEPTH_M = 0.25
STAGE5_MAX_DUMP_START_DISTANCE_M = 1.25
STAGE5_STRICT_MIN_DUMP_START_DISTANCE_M = 0.35
STAGE5_MIN_CARRY_EFFICIENCY = 0.40
STAGE5_MAX_DUMP_END_RESIDUAL_BUCKET_MASS_KG = 250.0
STAGE5_EARLY_DIG_ESCAPE_MIN_LOAD_READY_MASS_KG = 300.0
STAGE5_EARLY_DIG_ESCAPE_LOAD_READY_RATIO = 0.60
STAGE5_EARLY_DIG_ESCAPE_DISTANCE_M = 0.35
STAGE5_EARLY_DIG_ESCAPE_MIN_STREAK = 5
STAGE5_STRICT_MAX_QDS_BUCKET_QPOS = 0.12
STAGE5_STRICT_EARLY_WINDOW_STEPS = 80
STAGE5_STRICT_MIN_EARLY_PEAK_MASS_KG = 150.0
STAGE5_STRICT_MIN_EARLY_PEAK_DEPTH_M = 0.30
STAGE5_STRICT_CONTACT_LOSS_DISTANCE_M = 0.12
STAGE5_STRICT_CONTACT_LOSS_MIN_STREAK = 5
STAGE5_STRICT_LOAD_READY_MASS_KG = 200.0
STAGE5_STRICT_MASS_DROP_PEAK_KG = 100.0
STAGE5_STRICT_MASS_DROP_RETURN_KG = 20.0
STAGE5_STRICT_MIN_CARRY_EFFICIENCY = 0.45
STAGE5_BALANCED_MAX_DUMP_START_DISTANCE_M = 1.10
STAGE5_CLEANEST_MAX_QDS_BUCKET_QPOS = 0.10
STAGE5_CLEANEST_MAX_DUMP_START_DISTANCE_M = 0.95
STAGE5_CLEANEST_MIN_CARRY_EFFICIENCY = 0.55
STAGE5_CLEANEST_PRETARGET_SPILL_DISTANCE_M = 1.20
STAGE5_CLEANEST_PRETARGET_SPILL_DIG_ESCAPE_DISTANCE_M = 0.25
STAGE5_CLEANEST_PRETARGET_SPILL_MIN_PEAK_MASS_KG = 1200.0
STAGE5_CLEANEST_PRETARGET_SPILL_DROP_KG = 650.0
STAGE5_CLEANEST_PRETARGET_SPILL_MAX_MASS_RATIO = 0.45
STAGE5_CLEANEST_PRETARGET_SPILL_MIN_STREAK = 6
STAGE5_CLEANEST_PROBE_LOAD_MIN_MASS_KG = 40.0
STAGE5_CLEANEST_PROBE_EMPTY_RETURN_MASS_KG = 20.0
STAGE5_CLEANEST_PROBE_RELOAD_MIN_MASS_KG = 200.0
STAGE5_CLEANEST_PROBE_MAX_STEPS = 30
STAGE5_STRONG_DUMP_BUCKET_ACTION = -0.45
STAGE5_STRONG_DUMP_NEAR_TARGET_DISTANCE_M = STAGE5_STRICT_MIN_DUMP_START_DISTANCE_M


@dataclass(frozen=True)
class WorkskillSlice:
    source_episode_id: int
    source_cycle_id: int
    start_step: int
    dump_end_step: int
    window_len: int
    pause_ratio: float
    qds_bucket_qpos: float | None
    peak_bucket_depth_m: float | None
    dump_start_distance_m: float | None
    carry_efficiency: float | None
    dump_end_residual_bucket_mass_kg: float | None
    early_dig_escape: bool
    collision_count_delta: int
    strong_dump_frame_count: int
    strong_dump_near_target_frame_count: int
    strong_dump_min_target_distance_m: float | None
    strong_dump_first_target_distance_m: float | None
    strong_dump_first_height_above_rim_m: float | None
    action_loss_masked_frame_count: int
    action_loss_masked_frame_ratio: float


@dataclass(frozen=True)
class WorkskillRejectRecord:
    reason: str
    source_episode_id: int
    source_cycle_id: int
    window_len: int
    pause_ratio: float
    qds_bucket_qpos: float | None
    peak_bucket_depth_m: float | None
    dump_start_distance_m: float | None
    carry_efficiency: float | None
    dump_end_residual_bucket_mass_kg: float | None
    early_dig_escape: bool
    collision_count_delta: int
    strong_dump_frame_count: int
    strong_dump_near_target_frame_count: int
    strong_dump_min_target_distance_m: float | None
    strong_dump_first_target_distance_m: float | None
    strong_dump_first_height_above_rim_m: float | None
    action_loss_masked_frame_count: int
    action_loss_masked_frame_ratio: float


@dataclass(frozen=True)
class _WorkskillCycleDiagnostics:
    window_len: int
    pause_ratio: float
    qds_bucket_qpos: float | None
    peak_bucket_depth_m: float | None
    dump_start_distance_m: float | None
    carry_efficiency: float | None
    dump_end_residual_bucket_mass_kg: float | None
    early_dig_escape: bool
    collision_count_delta: int
    early_window_len: int
    early_peak_mass_kg: float | None
    early_peak_bucket_depth_m: float | None
    early_final_mass_kg: float | None
    early_contact_loss: bool
    early_mass_returned_to_zero: bool
    pretarget_spill_proxy: bool
    probe_then_reload: bool
    target_geometry_available: bool
    strong_dump_frame_count: int
    strong_dump_near_target_frame_count: int
    strong_dump_min_target_distance_m: float | None
    strong_dump_first_target_distance_m: float | None
    strong_dump_first_height_above_rim_m: float | None
    action_loss_masked_frame_count: int
    action_loss_masked_frame_ratio: float


def build_workskill_dataset(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    clean_profile: str | None = None,
) -> int:
    """Build a sibling cropped work-skill dataset from a relabeled V2.1 dataset."""
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    clean_profile = _normalise_clean_profile(clean_profile)

    episode_paths = list_episodes(dataset_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")

    existing_outputs = list_episodes(output_dir) if output_dir.exists() else []
    if existing_outputs:
        raise FileExistsError(
            f"Output directory {output_dir} already contains episode files. "
            "Use a fresh sibling directory for Stage-3 workskill builds."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    input_window_lengths: list[int] = []
    kept_window_lengths: list[int] = []
    input_pause_ratios: list[float] = []
    kept_pause_ratios: list[float] = []
    input_qds_bucket_qpos: list[float] = []
    kept_qds_bucket_qpos: list[float] = []
    input_peak_bucket_depth_m: list[float] = []
    kept_peak_bucket_depth_m: list[float] = []
    input_dump_start_distance_m: list[float] = []
    kept_dump_start_distance_m: list[float] = []
    input_carry_efficiency: list[float] = []
    kept_carry_efficiency: list[float] = []
    input_dump_end_residual_bucket_mass_kg: list[float] = []
    kept_dump_end_residual_bucket_mass_kg: list[float] = []
    input_strong_dump_frame_counts: list[int] = []
    kept_strong_dump_frame_counts: list[int] = []
    input_strong_dump_near_target_frame_counts: list[int] = []
    kept_strong_dump_near_target_frame_counts: list[int] = []
    input_strong_dump_min_target_distance_m: list[float] = []
    kept_strong_dump_min_target_distance_m: list[float] = []
    input_strong_dump_first_target_distance_m: list[float] = []
    kept_strong_dump_first_target_distance_m: list[float] = []
    input_strong_dump_first_height_above_rim_m: list[float] = []
    kept_strong_dump_first_height_above_rim_m: list[float] = []
    input_action_loss_masked_frame_counts: list[int] = []
    kept_action_loss_masked_frame_counts: list[int] = []
    input_action_loss_masked_frame_ratios: list[float] = []
    kept_action_loss_masked_frame_ratios: list[float] = []
    input_early_dig_escape_count = 0
    kept_early_dig_escape_count = 0
    input_collision_cycle_count = 0
    kept_collision_cycle_count = 0
    reject_reason_counts: Counter[str] = Counter()
    for source_path in episode_paths:
        episode = read_episode(source_path)
        workskill_slices, rejected = extract_successful_workskill_slices(
            episode=episode,
            source_path=source_path,
            clean_profile=clean_profile,
        )
        for rejected_cycle in rejected:
            _append_workskill_diagnostics(
                diagnostics=rejected_cycle,
                window_lengths=input_window_lengths,
                pause_ratios=input_pause_ratios,
                qds_bucket_qpos_values=input_qds_bucket_qpos,
                peak_bucket_depth_values=input_peak_bucket_depth_m,
                dump_start_distance_values=input_dump_start_distance_m,
                carry_efficiency_values=input_carry_efficiency,
                dump_end_residual_mass_values=input_dump_end_residual_bucket_mass_kg,
                strong_dump_frame_counts=input_strong_dump_frame_counts,
                strong_dump_near_target_frame_counts=input_strong_dump_near_target_frame_counts,
                strong_dump_min_target_distance_values=input_strong_dump_min_target_distance_m,
                strong_dump_first_target_distance_values=input_strong_dump_first_target_distance_m,
                strong_dump_first_height_values=input_strong_dump_first_height_above_rim_m,
                action_loss_masked_frame_counts=input_action_loss_masked_frame_counts,
                action_loss_masked_frame_ratios=input_action_loss_masked_frame_ratios,
            )
            input_early_dig_escape_count += int(rejected_cycle.early_dig_escape)
            input_collision_cycle_count += int(rejected_cycle.collision_count_delta > 0)
            reject_reason_counts.update([str(rejected_cycle.reason)])
        for workskill_slice in workskill_slices:
            _append_workskill_diagnostics(
                diagnostics=workskill_slice,
                window_lengths=input_window_lengths,
                pause_ratios=input_pause_ratios,
                qds_bucket_qpos_values=input_qds_bucket_qpos,
                peak_bucket_depth_values=input_peak_bucket_depth_m,
                dump_start_distance_values=input_dump_start_distance_m,
                carry_efficiency_values=input_carry_efficiency,
                dump_end_residual_mass_values=input_dump_end_residual_bucket_mass_kg,
                strong_dump_frame_counts=input_strong_dump_frame_counts,
                strong_dump_near_target_frame_counts=input_strong_dump_near_target_frame_counts,
                strong_dump_min_target_distance_values=input_strong_dump_min_target_distance_m,
                strong_dump_first_target_distance_values=input_strong_dump_first_target_distance_m,
                strong_dump_first_height_values=input_strong_dump_first_height_above_rim_m,
                action_loss_masked_frame_counts=input_action_loss_masked_frame_counts,
                action_loss_masked_frame_ratios=input_action_loss_masked_frame_ratios,
            )
            _append_workskill_diagnostics(
                diagnostics=workskill_slice,
                window_lengths=kept_window_lengths,
                pause_ratios=kept_pause_ratios,
                qds_bucket_qpos_values=kept_qds_bucket_qpos,
                peak_bucket_depth_values=kept_peak_bucket_depth_m,
                dump_start_distance_values=kept_dump_start_distance_m,
                carry_efficiency_values=kept_carry_efficiency,
                dump_end_residual_mass_values=kept_dump_end_residual_bucket_mass_kg,
                strong_dump_frame_counts=kept_strong_dump_frame_counts,
                strong_dump_near_target_frame_counts=kept_strong_dump_near_target_frame_counts,
                strong_dump_min_target_distance_values=kept_strong_dump_min_target_distance_m,
                strong_dump_first_target_distance_values=kept_strong_dump_first_target_distance_m,
                strong_dump_first_height_values=kept_strong_dump_first_height_above_rim_m,
                action_loss_masked_frame_counts=kept_action_loss_masked_frame_counts,
                action_loss_masked_frame_ratios=kept_action_loss_masked_frame_ratios,
            )
            input_early_dig_escape_count += int(workskill_slice.early_dig_escape)
            kept_early_dig_escape_count += int(workskill_slice.early_dig_escape)
            input_collision_cycle_count += int(workskill_slice.collision_count_delta > 0)
            kept_collision_cycle_count += int(workskill_slice.collision_count_delta > 0)
            target_path = output_dir / f"episode_{written}.hdf5"
            write_workskill_episode(
                target_path=target_path,
                source_episode=episode,
                source_dataset_dir=dataset_dir,
                workskill_slice=workskill_slice,
                output_episode_id=written,
            )
            written += 1

    _write_workskill_build_summary(
        output_dir=output_dir,
        dataset_dir=dataset_dir,
        output_episode_count=written,
        clean_profile=clean_profile,
        input_episode_count=len(episode_paths),
        input_window_lengths=input_window_lengths,
        kept_window_lengths=kept_window_lengths,
        input_pause_ratios=input_pause_ratios,
        kept_pause_ratios=kept_pause_ratios,
        input_qds_bucket_qpos=input_qds_bucket_qpos,
        kept_qds_bucket_qpos=kept_qds_bucket_qpos,
        input_peak_bucket_depth_m=input_peak_bucket_depth_m,
        kept_peak_bucket_depth_m=kept_peak_bucket_depth_m,
        input_dump_start_distance_m=input_dump_start_distance_m,
        kept_dump_start_distance_m=kept_dump_start_distance_m,
        input_carry_efficiency=input_carry_efficiency,
        kept_carry_efficiency=kept_carry_efficiency,
        input_dump_end_residual_bucket_mass_kg=input_dump_end_residual_bucket_mass_kg,
        kept_dump_end_residual_bucket_mass_kg=kept_dump_end_residual_bucket_mass_kg,
        input_strong_dump_frame_counts=input_strong_dump_frame_counts,
        kept_strong_dump_frame_counts=kept_strong_dump_frame_counts,
        input_strong_dump_near_target_frame_counts=input_strong_dump_near_target_frame_counts,
        kept_strong_dump_near_target_frame_counts=kept_strong_dump_near_target_frame_counts,
        input_strong_dump_min_target_distance_m=input_strong_dump_min_target_distance_m,
        kept_strong_dump_min_target_distance_m=kept_strong_dump_min_target_distance_m,
        input_strong_dump_first_target_distance_m=input_strong_dump_first_target_distance_m,
        kept_strong_dump_first_target_distance_m=kept_strong_dump_first_target_distance_m,
        input_strong_dump_first_height_above_rim_m=input_strong_dump_first_height_above_rim_m,
        kept_strong_dump_first_height_above_rim_m=kept_strong_dump_first_height_above_rim_m,
        input_action_loss_masked_frame_counts=input_action_loss_masked_frame_counts,
        kept_action_loss_masked_frame_counts=kept_action_loss_masked_frame_counts,
        input_action_loss_masked_frame_ratios=input_action_loss_masked_frame_ratios,
        kept_action_loss_masked_frame_ratios=kept_action_loss_masked_frame_ratios,
        input_early_dig_escape_count=input_early_dig_escape_count,
        kept_early_dig_escape_count=kept_early_dig_escape_count,
        input_collision_cycle_count=input_collision_cycle_count,
        kept_collision_cycle_count=kept_collision_cycle_count,
        reject_reason_counts=reject_reason_counts,
    )
    if written <= 0:
        raise RuntimeError(
            f"No successful workskill cycles found under {dataset_dir}. "
            "Refusing to create an empty workskill dataset."
        )

    return written


def extract_successful_workskill_slices(
    *,
    episode: dict[str, Any],
    source_path: str | Path,
    clean_profile: str | None = None,
) -> tuple[list[WorkskillSlice], list[WorkskillRejectRecord]]:
    v2 = episode.get("v2")
    if not v2:
        raise KeyError(
            f"Episode {Path(source_path).name} is missing /v2 labels. "
            "Run tb-label-v2_1 first."
        )

    cycle_data = dict(v2.get("cycle", {}))
    required_keys = ("cycle_id", "start_step", "dump_end_step", "cycle_success")
    missing = [key for key in required_keys if key not in cycle_data]
    if missing:
        raise KeyError(
            f"Episode {Path(source_path).name} has incomplete /v2/cycle data; "
            f"missing {missing}."
        )

    source_episode_id = episode_id_from_path(Path(source_path))
    workskill_slices: list[WorkskillSlice] = []
    rejected: list[WorkskillRejectRecord] = []
    for cycle_index, start_step, dump_end_step, cycle_success in zip(
        cycle_data["cycle_id"],
        cycle_data["start_step"],
        cycle_data["dump_end_step"],
        cycle_data["cycle_success"],
    ):
        start = int(start_step)
        dump_end = int(dump_end_step)
        if int(cycle_success) != 1 or dump_end < start:
            continue
        diagnostics = _diagnose_workskill_cycle(
            episode=episode,
            cycle_data=cycle_data,
            cycle_index=int(cycle_index),
            start_step=start,
            dump_end_step=dump_end,
        )
        reject_reason = _reject_reason_for_workskill_cycle(
            diagnostics=diagnostics,
            clean_profile=clean_profile or "",
        )
        if reject_reason is not None:
            rejected.append(
                WorkskillRejectRecord(
                    reason=reject_reason,
                    source_episode_id=source_episode_id,
                    source_cycle_id=int(cycle_index),
                    window_len=int(diagnostics.window_len),
                    pause_ratio=float(diagnostics.pause_ratio),
                    qds_bucket_qpos=diagnostics.qds_bucket_qpos,
                    peak_bucket_depth_m=diagnostics.peak_bucket_depth_m,
                    dump_start_distance_m=diagnostics.dump_start_distance_m,
                    carry_efficiency=diagnostics.carry_efficiency,
                    dump_end_residual_bucket_mass_kg=diagnostics.dump_end_residual_bucket_mass_kg,
                    early_dig_escape=bool(diagnostics.early_dig_escape),
                    collision_count_delta=int(diagnostics.collision_count_delta),
                    strong_dump_frame_count=int(diagnostics.strong_dump_frame_count),
                    strong_dump_near_target_frame_count=int(diagnostics.strong_dump_near_target_frame_count),
                    strong_dump_min_target_distance_m=diagnostics.strong_dump_min_target_distance_m,
                    strong_dump_first_target_distance_m=diagnostics.strong_dump_first_target_distance_m,
                    strong_dump_first_height_above_rim_m=diagnostics.strong_dump_first_height_above_rim_m,
                    action_loss_masked_frame_count=int(diagnostics.action_loss_masked_frame_count),
                    action_loss_masked_frame_ratio=float(diagnostics.action_loss_masked_frame_ratio),
                )
            )
            continue
        workskill_slices.append(
            WorkskillSlice(
                source_episode_id=source_episode_id,
                source_cycle_id=int(cycle_index),
                start_step=start,
                dump_end_step=dump_end,
                window_len=int(diagnostics.window_len),
                pause_ratio=float(diagnostics.pause_ratio),
                qds_bucket_qpos=diagnostics.qds_bucket_qpos,
                peak_bucket_depth_m=diagnostics.peak_bucket_depth_m,
                dump_start_distance_m=diagnostics.dump_start_distance_m,
                carry_efficiency=diagnostics.carry_efficiency,
                dump_end_residual_bucket_mass_kg=diagnostics.dump_end_residual_bucket_mass_kg,
                early_dig_escape=bool(diagnostics.early_dig_escape),
                collision_count_delta=int(diagnostics.collision_count_delta),
                strong_dump_frame_count=int(diagnostics.strong_dump_frame_count),
                strong_dump_near_target_frame_count=int(diagnostics.strong_dump_near_target_frame_count),
                strong_dump_min_target_distance_m=diagnostics.strong_dump_min_target_distance_m,
                strong_dump_first_target_distance_m=diagnostics.strong_dump_first_target_distance_m,
                strong_dump_first_height_above_rim_m=diagnostics.strong_dump_first_height_above_rim_m,
                action_loss_masked_frame_count=int(diagnostics.action_loss_masked_frame_count),
                action_loss_masked_frame_ratio=float(diagnostics.action_loss_masked_frame_ratio),
            )
        )
    return workskill_slices, rejected


def write_workskill_episode(
    *,
    target_path: str | Path,
    source_episode: dict[str, Any],
    source_dataset_dir: str | Path,
    workskill_slice: WorkskillSlice,
    output_episode_id: int,
) -> None:
    start = int(workskill_slice.start_step)
    end = int(workskill_slice.dump_end_step) + 1
    crop = slice(start, end)
    window_len = end - start
    if window_len <= 0:
        raise ValueError("Workskill slice must contain at least one timestep.")

    metadata = dict(source_episode.get("metadata", {}))
    metadata.update(
        {
            "episode_id": f"episode_{output_episode_id}",
            "recording_mode": WORKSKILL_RECORDING_MODE,
            "source_dataset_dir": str(Path(source_dataset_dir).resolve()),
            "source_episode_id": f"episode_{workskill_slice.source_episode_id}",
            "source_cycle_id": int(workskill_slice.source_cycle_id),
            "source_start_step": int(workskill_slice.start_step),
            "source_dump_end_step": int(workskill_slice.dump_end_step),
            "workskill_window": WORKSKILL_WINDOW_NAME,
        }
    )

    images = {
        camera_name: np.asarray(camera_frames[crop])
        for camera_name, camera_frames in dict(source_episode.get("images", {})).items()
    }

    v2_payload = build_workskill_v2_payload(
        source_episode=source_episode,
        source_cycle_id=int(workskill_slice.source_cycle_id),
        crop=crop,
        window_len=window_len,
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


def build_workskill_v2_payload(
    *,
    source_episode: dict[str, Any],
    source_cycle_id: int,
    crop: slice,
    window_len: int,
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
    if "cycle_id" not in step_payload:
        raise KeyError("Source episode /v2/step is missing cycle_id.")

    step_payload["cycle_id"] = np.zeros(window_len, dtype=np.int32)
    step_payload["action_loss_mask"] = _build_workskill_action_loss_mask(
        actions=np.asarray(source_episode["actions"][crop], dtype=np.float32),
        env_state=_slice_optional_array(source_episode.get("env_state"), crop),
        dump_start_mask=step_payload.get("dump_start_mask"),
    )

    cycle_section = dict(v2.get("cycle", {}))
    if not cycle_section:
        raise KeyError("Source episode /v2/cycle is empty.")

    cycle_payload: dict[str, np.ndarray] = {}
    for key, value in cycle_section.items():
        item = value[source_cycle_id]
        if key == "cycle_id":
            cycle_payload[key] = np.asarray([0], dtype=np.int32)
        elif key == "start_step":
            cycle_payload[key] = np.asarray([0], dtype=np.int32)
        elif key == "dump_end_step":
            cycle_payload[key] = np.asarray([window_len - 1], dtype=np.int32)
        elif key == "end_step":
            cycle_payload[key] = np.asarray([window_len - 1], dtype=np.int32)
        elif isinstance(item, bytes):
            cycle_payload[key] = np.asarray([item.decode()], dtype=str)
        elif isinstance(item, str):
            cycle_payload[key] = np.asarray([item], dtype=str)
        elif np.asarray(item).dtype.kind in {"U", "S", "O"}:
            cycle_payload[key] = np.asarray([str(item)], dtype=str)
        else:
            cycle_payload[key] = np.asarray([item])

    return {
        "step": step_payload,
        "cycle": cycle_payload,
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
    if value not in (
        "",
        CLEAN_PROFILE_STAGE5,
        CLEAN_PROFILE_STAGE5_STRICT,
        CLEAN_PROFILE_STAGE5_BALANCED,
        CLEAN_PROFILE_STAGE5_CLEANEST,
    ):
        raise ValueError(
            f"Unsupported clean_profile {clean_profile!r}. "
            f"Expected {CLEAN_PROFILE_STAGE5!r}, {CLEAN_PROFILE_STAGE5_STRICT!r}, "
            f"{CLEAN_PROFILE_STAGE5_BALANCED!r}, "
            f"{CLEAN_PROFILE_STAGE5_CLEANEST!r} or empty."
        )
    return value


def _safe_env_scalar(
    env_state: np.ndarray | None,
    step_idx: int,
    env_index: int,
) -> float | None:
    if env_state is None or step_idx < 0 or step_idx >= int(env_state.shape[0]):
        return None
    if env_state.ndim != 2 or env_index < 0 or env_index >= int(env_state.shape[1]):
        return None
    value = float(env_state[step_idx, env_index])
    if not np.isfinite(value):
        return None
    return value


def _env_state_has_target_geometry(env_state: np.ndarray | None) -> bool:
    if env_state is None or env_state.ndim != 2:
        return False
    required_indices = (
        ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    )
    if env_state.shape[1] <= max(required_indices):
        return False
    values = env_state[:, required_indices]
    return bool(
        values.size > 0
        and np.all(np.isfinite(values))
        and np.all(env_state[:, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] >= 0.0)
    )


def _detect_early_dig_escape(
    env_state: np.ndarray | None,
    *,
    start_step: int,
    end_step: int,
) -> bool:
    if env_state is None:
        return False

    mass_window = env_state[start_step : end_step + 1, ENV_STATE_MASS_IN_BUCKET_IDX]
    if mass_window.size <= 0:
        return False
    max_mass = float(np.max(mass_window))
    if max_mass <= 1.0e-6:
        return False
    load_ready_thresh = max(
        STAGE5_EARLY_DIG_ESCAPE_MIN_LOAD_READY_MASS_KG,
        STAGE5_EARLY_DIG_ESCAPE_LOAD_READY_RATIO * max_mass,
    )
    load_ready_step = end_step
    for step_idx in range(start_step, end_step + 1):
        mass = _safe_env_scalar(env_state, step_idx, ENV_STATE_MASS_IN_BUCKET_IDX)
        if mass is not None and mass >= load_ready_thresh:
            load_ready_step = step_idx
            break

    streak = 0
    for step_idx in range(start_step, load_ready_step + 1):
        dig_distance = _safe_env_scalar(env_state, step_idx, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX)
        if dig_distance is not None and dig_distance > STAGE5_EARLY_DIG_ESCAPE_DISTANCE_M:
            streak += 1
            if streak >= STAGE5_EARLY_DIG_ESCAPE_MIN_STREAK:
                return True
        else:
            streak = 0
    return False


def _diagnose_workskill_cycle(
    *,
    episode: dict[str, Any],
    cycle_data: dict[str, Any],
    cycle_index: int,
    start_step: int,
    dump_end_step: int,
) -> _WorkskillCycleDiagnostics:
    window_len = int(dump_end_step - start_step + 1)

    actions = np.asarray(
        episode.get("actions", np.zeros((window_len, 4), dtype=np.float32)),
        dtype=np.float32,
    )
    if actions.ndim != 2 or actions.shape[0] <= dump_end_step:
        pause_ratio = 0.0
    else:
        action_window = actions[start_step : dump_end_step + 1]
        pause_ratio = float(np.mean(np.sum(np.abs(action_window), axis=1) < PAUSE_ACTION_L1_EPS))

    qpos = np.asarray(episode.get("qpos", np.zeros((window_len, 4), dtype=np.float32)), dtype=np.float32)
    qds_bucket_qpos: float | None = None
    if qpos.ndim == 2 and qpos.shape[0] > start_step and qpos.shape[1] >= 4:
        qds_bucket_qpos = float(qpos[start_step, 3])
        if not np.isfinite(qds_bucket_qpos):
            qds_bucket_qpos = None

    env_state = None
    if episode.get("env_state") is not None:
        env_state = np.asarray(episode["env_state"], dtype=np.float32)
    target_geometry_available = _env_state_has_target_geometry(env_state)

    peak_bucket_depth_m = None
    if "peak_bucket_depth_m" in cycle_data:
        peak_bucket_depth_m = float(cycle_data["peak_bucket_depth_m"][cycle_index])
        if not np.isfinite(peak_bucket_depth_m):
            peak_bucket_depth_m = None
    if peak_bucket_depth_m is None and env_state is not None:
        depth_window = env_state[start_step : dump_end_step + 1, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
        if depth_window.size > 0:
            peak_bucket_depth_m = float(np.max(depth_window))

    dump_start_distance_m: float | None = None
    carry_efficiency: float | None = None
    dump_start_idx = _find_dump_start_idx(episode=episode, start_step=start_step, dump_end_step=dump_end_step)
    if dump_start_idx is not None:
        dump_start_distance_m = _safe_env_scalar(
            env_state,
            dump_start_idx,
            ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
        )
        if env_state is not None:
            mass_window = env_state[start_step : dump_start_idx + 1, ENV_STATE_MASS_IN_BUCKET_IDX]
            if mass_window.size > 0:
                max_pre_dump_mass = float(np.max(mass_window))
                dump_start_mass = float(mass_window[-1])
                if max_pre_dump_mass > 1.0e-6:
                    carry_efficiency = float(np.clip(dump_start_mass / max_pre_dump_mass, 0.0, 1.0))

    dump_end_residual_bucket_mass_kg = _safe_env_scalar(
        env_state,
        dump_end_step,
        ENV_STATE_MASS_IN_BUCKET_IDX,
    )

    early_dig_escape = False
    if dump_start_idx is not None:
        early_dig_escape = _detect_early_dig_escape(
            env_state,
            start_step=start_step,
            end_step=dump_start_idx,
        )

    collision_count_delta = 0
    if "collision_count_delta" in cycle_data:
        collision_count_delta = int(cycle_data["collision_count_delta"][cycle_index])

    early_window_len = 0
    early_peak_mass_kg: float | None = None
    early_peak_bucket_depth_m: float | None = None
    early_final_mass_kg: float | None = None
    early_contact_loss = False
    early_mass_returned_to_zero = False
    pretarget_spill_proxy = False
    probe_then_reload = False
    if env_state is not None:
        early_end_step = min(dump_end_step, start_step + STAGE5_STRICT_EARLY_WINDOW_STEPS - 1)
        early_window_len = max(0, int(early_end_step - start_step + 1))
        if early_window_len > 0:
            mass_window = env_state[start_step : early_end_step + 1, ENV_STATE_MASS_IN_BUCKET_IDX]
            dig_distance_window = env_state[start_step : early_end_step + 1, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX]
            depth_window = env_state[
                start_step : early_end_step + 1,
                ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
            ]
            if mass_window.size > 0:
                early_peak_mass_kg = float(np.max(mass_window))
                early_final_mass_kg = float(mass_window[-1])
                peak_idx = int(np.argmax(mass_window))
                if (
                    early_peak_mass_kg >= STAGE5_STRICT_MASS_DROP_PEAK_KG
                    and peak_idx + 1 < mass_window.size
                ):
                    post_peak = mass_window[peak_idx + 1 :]
                    early_mass_returned_to_zero = bool(
                        np.any(post_peak <= STAGE5_STRICT_MASS_DROP_RETURN_KG)
                    )
                first_loaded_idx: int | None = None
                for local_idx, mass in enumerate(mass_window):
                    if float(mass) >= STAGE5_CLEANEST_PROBE_LOAD_MIN_MASS_KG:
                        first_loaded_idx = int(local_idx)
                        break
                if first_loaded_idx is not None:
                    probe_end = min(first_loaded_idx + STAGE5_CLEANEST_PROBE_MAX_STEPS, int(mass_window.size - 1))
                    empty_return_idx: int | None = None
                    for local_idx in range(first_loaded_idx + 1, probe_end + 1):
                        if float(mass_window[local_idx]) <= STAGE5_CLEANEST_PROBE_EMPTY_RETURN_MASS_KG:
                            empty_return_idx = int(local_idx)
                            break
                    if empty_return_idx is not None and empty_return_idx + 1 < mass_window.size:
                        reload_window = mass_window[empty_return_idx + 1 :]
                        probe_then_reload = bool(
                            np.any(reload_window >= STAGE5_CLEANEST_PROBE_RELOAD_MIN_MASS_KG)
                        )
            if depth_window.size > 0:
                early_peak_bucket_depth_m = float(np.max(depth_window))

            load_ready_idx: int | None = None
            if mass_window.size > 0:
                for local_idx, mass in enumerate(mass_window):
                    if float(mass) >= STAGE5_STRICT_LOAD_READY_MASS_KG:
                        load_ready_idx = int(local_idx)
                        break
            loss_streak = 0
            search_end = load_ready_idx if load_ready_idx is not None else int(dig_distance_window.size - 1)
            for local_idx in range(0, search_end + 1):
                dig_distance = float(dig_distance_window[local_idx])
                if dig_distance > STAGE5_STRICT_CONTACT_LOSS_DISTANCE_M:
                    loss_streak += 1
                    if loss_streak >= STAGE5_STRICT_CONTACT_LOSS_MIN_STREAK:
                        early_contact_loss = True
                        break
                else:
                    loss_streak = 0

    if env_state is not None and dump_start_idx is not None:
        running_peak_mass = 0.0
        spill_streak = 0
        for step_idx in range(start_step, dump_start_idx + 1):
            mass = _safe_env_scalar(env_state, step_idx, ENV_STATE_MASS_IN_BUCKET_IDX)
            target_distance = _safe_env_scalar(
                env_state,
                step_idx,
                ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
            )
            dig_distance = _safe_env_scalar(env_state, step_idx, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX)
            if mass is None or target_distance is None or dig_distance is None:
                spill_streak = 0
                continue
            running_peak_mass = max(running_peak_mass, float(mass))
            if running_peak_mass < STAGE5_CLEANEST_PRETARGET_SPILL_MIN_PEAK_MASS_KG:
                spill_streak = 0
                continue
            if target_distance <= STAGE5_CLEANEST_PRETARGET_SPILL_DISTANCE_M:
                spill_streak = 0
                continue
            if dig_distance <= STAGE5_CLEANEST_PRETARGET_SPILL_DIG_ESCAPE_DISTANCE_M:
                spill_streak = 0
                continue
            if (
                float(mass) <= running_peak_mass - STAGE5_CLEANEST_PRETARGET_SPILL_DROP_KG
                and float(mass) <= running_peak_mass * STAGE5_CLEANEST_PRETARGET_SPILL_MAX_MASS_RATIO
            ):
                spill_streak += 1
                if spill_streak >= STAGE5_CLEANEST_PRETARGET_SPILL_MIN_STREAK:
                    pretarget_spill_proxy = True
                    break
            else:
                spill_streak = 0

    (
        strong_dump_frame_count,
        strong_dump_near_target_frame_count,
        strong_dump_min_target_distance_m,
        strong_dump_first_target_distance_m,
        strong_dump_first_height_above_rim_m,
    ) = _diagnose_strong_dump_geometry(
        actions=actions,
        env_state=env_state,
        start_step=start_step,
        dump_end_step=dump_end_step,
    )
    action_loss_mask = _build_workskill_action_loss_mask(
        actions=actions[start_step : dump_end_step + 1],
        env_state=None if env_state is None else env_state[start_step : dump_end_step + 1],
        dump_start_mask=_relative_dump_start_mask(
            episode=episode,
            start_step=start_step,
            dump_end_step=dump_end_step,
        ),
    )
    action_loss_masked_frame_count = int(np.sum(action_loss_mask == 0))
    action_loss_masked_frame_ratio = (
        float(action_loss_masked_frame_count / max(1, int(action_loss_mask.shape[0])))
    )

    return _WorkskillCycleDiagnostics(
        window_len=window_len,
        pause_ratio=float(pause_ratio),
        qds_bucket_qpos=qds_bucket_qpos,
        peak_bucket_depth_m=peak_bucket_depth_m,
        dump_start_distance_m=dump_start_distance_m,
        carry_efficiency=carry_efficiency,
        dump_end_residual_bucket_mass_kg=dump_end_residual_bucket_mass_kg,
        early_dig_escape=bool(early_dig_escape),
        collision_count_delta=int(collision_count_delta),
        early_window_len=int(early_window_len),
        early_peak_mass_kg=early_peak_mass_kg,
        early_peak_bucket_depth_m=early_peak_bucket_depth_m,
        early_final_mass_kg=early_final_mass_kg,
        early_contact_loss=bool(early_contact_loss),
        early_mass_returned_to_zero=bool(early_mass_returned_to_zero),
        pretarget_spill_proxy=bool(pretarget_spill_proxy),
        probe_then_reload=bool(probe_then_reload),
        target_geometry_available=bool(target_geometry_available),
        strong_dump_frame_count=int(strong_dump_frame_count),
        strong_dump_near_target_frame_count=int(strong_dump_near_target_frame_count),
        strong_dump_min_target_distance_m=strong_dump_min_target_distance_m,
        strong_dump_first_target_distance_m=strong_dump_first_target_distance_m,
        strong_dump_first_height_above_rim_m=strong_dump_first_height_above_rim_m,
        action_loss_masked_frame_count=int(action_loss_masked_frame_count),
        action_loss_masked_frame_ratio=float(action_loss_masked_frame_ratio),
    )


def _relative_dump_start_mask(
    *,
    episode: dict[str, Any],
    start_step: int,
    dump_end_step: int,
) -> np.ndarray:
    v2 = episode.get("v2") or {}
    step_section = dict(v2.get("step", {}))
    dump_start_mask = step_section.get("dump_start_mask")
    length = int(dump_end_step - start_step + 1)
    if dump_start_mask is None:
        return np.zeros(length, dtype=np.uint8)
    mask = np.asarray(dump_start_mask, dtype=np.uint8)
    if mask.ndim != 1 or mask.shape[0] <= dump_end_step:
        return np.zeros(length, dtype=np.uint8)
    return np.asarray(mask[start_step : dump_end_step + 1], dtype=np.uint8)


def _build_workskill_action_loss_mask(
    *,
    actions: np.ndarray,
    env_state: np.ndarray | None,
    dump_start_mask: np.ndarray | None,
) -> np.ndarray:
    action_arr = np.asarray(actions, dtype=np.float32)
    length = int(action_arr.shape[0]) if action_arr.ndim >= 1 else 0
    mask = np.ones(length, dtype=np.uint8)
    return mask


def _diagnose_strong_dump_geometry(
    *,
    actions: np.ndarray,
    env_state: np.ndarray | None,
    start_step: int,
    dump_end_step: int,
) -> tuple[int, int, float | None, float | None, float | None]:
    if (
        actions.ndim != 2
        or actions.shape[0] <= dump_end_step
        or actions.shape[1] < 4
        or not _env_state_has_target_geometry(env_state)
    ):
        return 0, 0, None, None, None

    action_window = actions[start_step : dump_end_step + 1]
    strong_local = np.flatnonzero(action_window[:, 3] <= STAGE5_STRONG_DUMP_BUCKET_ACTION)
    if strong_local.size <= 0:
        return 0, 0, None, None, None

    strong_steps = strong_local + int(start_step)
    distances = np.asarray(
        env_state[strong_steps, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX],
        dtype=np.float32,
    )
    heights = np.asarray(
        env_state[strong_steps, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX],
        dtype=np.float32,
    )
    finite_distance = np.isfinite(distances)
    finite_height = np.isfinite(heights)

    first_distance = None
    min_distance = None
    near_count = 0
    if np.any(finite_distance):
        finite_distances = distances[finite_distance]
        first_distance = float(distances[int(np.flatnonzero(finite_distance)[0])])
        min_distance = float(np.min(finite_distances))
        near_count = int(np.sum(finite_distances < STAGE5_STRONG_DUMP_NEAR_TARGET_DISTANCE_M))

    first_height = None
    if np.any(finite_height):
        first_height = float(heights[int(np.flatnonzero(finite_height)[0])])

    return int(strong_local.size), int(near_count), min_distance, first_distance, first_height


def _find_dump_start_idx(
    *,
    episode: dict[str, Any],
    start_step: int,
    dump_end_step: int,
) -> int | None:
    v2 = episode.get("v2") or {}
    step_section = dict(v2.get("step", {}))
    dump_start_mask = step_section.get("dump_start_mask")
    if dump_start_mask is None:
        return None
    mask = np.asarray(dump_start_mask, dtype=np.uint8)
    if mask.ndim != 1 or mask.shape[0] <= dump_end_step:
        return None
    for step_idx in range(start_step, dump_end_step + 1):
        if bool(mask[step_idx]):
            return int(step_idx)
    return None


def _reject_reason_for_workskill_cycle(
    *,
    diagnostics: _WorkskillCycleDiagnostics,
    clean_profile: str,
) -> str | None:
    if clean_profile not in (
        CLEAN_PROFILE_STAGE5,
        CLEAN_PROFILE_STAGE5_STRICT,
        CLEAN_PROFILE_STAGE5_BALANCED,
        CLEAN_PROFILE_STAGE5_CLEANEST,
    ):
        return None

    if diagnostics.collision_count_delta > 0:
        return "collision_in_cycle"
    if not diagnostics.target_geometry_available:
        return "missing_target_geometry"
    if clean_profile == CLEAN_PROFILE_STAGE5_CLEANEST:
        max_qds_bucket_qpos = STAGE5_CLEANEST_MAX_QDS_BUCKET_QPOS
    elif clean_profile in (CLEAN_PROFILE_STAGE5_STRICT, CLEAN_PROFILE_STAGE5_BALANCED):
        max_qds_bucket_qpos = STAGE5_STRICT_MAX_QDS_BUCKET_QPOS
    else:
        max_qds_bucket_qpos = STAGE5_MAX_QDS_BUCKET_QPOS
    if diagnostics.qds_bucket_qpos is not None and diagnostics.qds_bucket_qpos > max_qds_bucket_qpos:
        return "flat_bucket_qds"
    if clean_profile in (CLEAN_PROFILE_STAGE5_BALANCED, CLEAN_PROFILE_STAGE5_CLEANEST) and diagnostics.pretarget_spill_proxy:
        return "pretarget_spill_proxy"
    if (
        diagnostics.peak_bucket_depth_m is not None
        and diagnostics.peak_bucket_depth_m < STAGE5_MIN_PEAK_BUCKET_DEPTH_M
    ):
        return "shallow_peak_bucket_depth"
    if (
        clean_profile
        in (CLEAN_PROFILE_STAGE5_STRICT, CLEAN_PROFILE_STAGE5_BALANCED, CLEAN_PROFILE_STAGE5_CLEANEST)
        and diagnostics.dump_start_distance_m is not None
        and diagnostics.dump_start_distance_m < STAGE5_STRICT_MIN_DUMP_START_DISTANCE_M
    ):
        return "near_dump_start"
    if (
        diagnostics.dump_start_distance_m is not None
        and diagnostics.dump_start_distance_m
        > (
            STAGE5_CLEANEST_MAX_DUMP_START_DISTANCE_M
            if clean_profile == CLEAN_PROFILE_STAGE5_CLEANEST
            else STAGE5_BALANCED_MAX_DUMP_START_DISTANCE_M
            if clean_profile == CLEAN_PROFILE_STAGE5_BALANCED
            else STAGE5_MAX_DUMP_START_DISTANCE_M
        )
    ):
        return "far_dump_start"
    if clean_profile == CLEAN_PROFILE_STAGE5_CLEANEST:
        min_carry_efficiency = STAGE5_CLEANEST_MIN_CARRY_EFFICIENCY
    elif clean_profile in (CLEAN_PROFILE_STAGE5_STRICT, CLEAN_PROFILE_STAGE5_BALANCED):
        min_carry_efficiency = STAGE5_STRICT_MIN_CARRY_EFFICIENCY
    else:
        min_carry_efficiency = STAGE5_MIN_CARRY_EFFICIENCY
    if (
        diagnostics.carry_efficiency is not None
        and diagnostics.carry_efficiency < min_carry_efficiency
    ):
        return "low_carry_efficiency"
    if (
        diagnostics.dump_end_residual_bucket_mass_kg is not None
        and diagnostics.dump_end_residual_bucket_mass_kg > STAGE5_MAX_DUMP_END_RESIDUAL_BUCKET_MASS_KG
    ):
        return "high_residual_bucket_mass"
    if diagnostics.early_dig_escape:
        return "early_dig_escape"
    if diagnostics.pause_ratio > STAGE5_MAX_WORKSKILL_PAUSE_RATIO:
        return "high_pause_ratio"
    if clean_profile in (
        CLEAN_PROFILE_STAGE5_STRICT,
        CLEAN_PROFILE_STAGE5_BALANCED,
        CLEAN_PROFILE_STAGE5_CLEANEST,
    ):
        if (
            diagnostics.early_peak_mass_kg is not None
            and diagnostics.early_peak_mass_kg < STAGE5_STRICT_MIN_EARLY_PEAK_MASS_KG
        ):
            return "weak_early_load_gain"
        if (
            diagnostics.early_peak_bucket_depth_m is not None
            and diagnostics.early_peak_bucket_depth_m < STAGE5_STRICT_MIN_EARLY_PEAK_DEPTH_M
        ):
            return "weak_early_cut_depth"
        if clean_profile in (CLEAN_PROFILE_STAGE5_BALANCED, CLEAN_PROFILE_STAGE5_CLEANEST) and diagnostics.probe_then_reload:
            return "probe_then_reload"
        if diagnostics.early_contact_loss:
            return "early_contact_loss"
        if diagnostics.early_mass_returned_to_zero:
            return "early_mass_returned_to_zero"
    return None


def _append_workskill_diagnostics(
    *,
    diagnostics: WorkskillSlice | WorkskillRejectRecord,
    window_lengths: list[int],
    pause_ratios: list[float],
    qds_bucket_qpos_values: list[float],
    peak_bucket_depth_values: list[float],
    dump_start_distance_values: list[float],
    carry_efficiency_values: list[float],
    dump_end_residual_mass_values: list[float],
    strong_dump_frame_counts: list[int],
    strong_dump_near_target_frame_counts: list[int],
    strong_dump_min_target_distance_values: list[float],
    strong_dump_first_target_distance_values: list[float],
    strong_dump_first_height_values: list[float],
    action_loss_masked_frame_counts: list[int],
    action_loss_masked_frame_ratios: list[float],
) -> None:
    window_lengths.append(int(diagnostics.window_len))
    pause_ratios.append(float(diagnostics.pause_ratio))
    if diagnostics.qds_bucket_qpos is not None:
        qds_bucket_qpos_values.append(float(diagnostics.qds_bucket_qpos))
    if diagnostics.peak_bucket_depth_m is not None:
        peak_bucket_depth_values.append(float(diagnostics.peak_bucket_depth_m))
    if diagnostics.dump_start_distance_m is not None:
        dump_start_distance_values.append(float(diagnostics.dump_start_distance_m))
    if diagnostics.carry_efficiency is not None:
        carry_efficiency_values.append(float(diagnostics.carry_efficiency))
    if diagnostics.dump_end_residual_bucket_mass_kg is not None:
        dump_end_residual_mass_values.append(float(diagnostics.dump_end_residual_bucket_mass_kg))
    strong_dump_frame_counts.append(int(diagnostics.strong_dump_frame_count))
    strong_dump_near_target_frame_counts.append(int(diagnostics.strong_dump_near_target_frame_count))
    if diagnostics.strong_dump_min_target_distance_m is not None:
        strong_dump_min_target_distance_values.append(
            float(diagnostics.strong_dump_min_target_distance_m)
        )
    if diagnostics.strong_dump_first_target_distance_m is not None:
        strong_dump_first_target_distance_values.append(
            float(diagnostics.strong_dump_first_target_distance_m)
        )
    if diagnostics.strong_dump_first_height_above_rim_m is not None:
        strong_dump_first_height_values.append(float(diagnostics.strong_dump_first_height_above_rim_m))
    action_loss_masked_frame_counts.append(int(diagnostics.action_loss_masked_frame_count))
    action_loss_masked_frame_ratios.append(float(diagnostics.action_loss_masked_frame_ratio))


def _describe_distribution(values: list[int | float]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
        }
    arr = np.asarray(values, dtype=np.float32)
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
    }


def _write_workskill_build_summary(
    *,
    output_dir: Path,
    dataset_dir: Path,
    output_episode_count: int,
    clean_profile: str,
    input_episode_count: int,
    input_window_lengths: list[int],
    kept_window_lengths: list[int],
    input_pause_ratios: list[float],
    kept_pause_ratios: list[float],
    input_qds_bucket_qpos: list[float],
    kept_qds_bucket_qpos: list[float],
    input_peak_bucket_depth_m: list[float],
    kept_peak_bucket_depth_m: list[float],
    input_dump_start_distance_m: list[float],
    kept_dump_start_distance_m: list[float],
    input_carry_efficiency: list[float],
    kept_carry_efficiency: list[float],
    input_dump_end_residual_bucket_mass_kg: list[float],
    kept_dump_end_residual_bucket_mass_kg: list[float],
    input_strong_dump_frame_counts: list[int],
    kept_strong_dump_frame_counts: list[int],
    input_strong_dump_near_target_frame_counts: list[int],
    kept_strong_dump_near_target_frame_counts: list[int],
    input_strong_dump_min_target_distance_m: list[float],
    kept_strong_dump_min_target_distance_m: list[float],
    input_strong_dump_first_target_distance_m: list[float],
    kept_strong_dump_first_target_distance_m: list[float],
    input_strong_dump_first_height_above_rim_m: list[float],
    kept_strong_dump_first_height_above_rim_m: list[float],
    input_action_loss_masked_frame_counts: list[int],
    kept_action_loss_masked_frame_counts: list[int],
    input_action_loss_masked_frame_ratios: list[float],
    kept_action_loss_masked_frame_ratios: list[float],
    input_early_dig_escape_count: int,
    kept_early_dig_escape_count: int,
    input_collision_cycle_count: int,
    kept_collision_cycle_count: int,
    reject_reason_counts: Counter[str],
) -> None:
    payload = {
        "source_dataset_dir": str(dataset_dir.resolve()),
        "output_dataset_dir": str(output_dir.resolve()),
        "input_episode_count": int(input_episode_count),
        "input_workskill_window_count": int(len(input_window_lengths)),
        "output_episode_count": int(output_episode_count),
        "clean_profile": clean_profile or "none",
        "reject_reason_counts": dict(sorted(reject_reason_counts.items())),
        "input_length_distribution": _describe_distribution(input_window_lengths),
        "kept_length_distribution": _describe_distribution(kept_window_lengths),
        "input_pause_ratio_distribution": _describe_distribution(input_pause_ratios),
        "kept_pause_ratio_distribution": _describe_distribution(kept_pause_ratios),
        "input_qds_bucket_qpos_distribution": _describe_distribution(input_qds_bucket_qpos),
        "kept_qds_bucket_qpos_distribution": _describe_distribution(kept_qds_bucket_qpos),
        "input_peak_bucket_depth_distribution_m": _describe_distribution(input_peak_bucket_depth_m),
        "kept_peak_bucket_depth_distribution_m": _describe_distribution(kept_peak_bucket_depth_m),
        "input_dump_start_distance_distribution_m": _describe_distribution(input_dump_start_distance_m),
        "kept_dump_start_distance_distribution_m": _describe_distribution(kept_dump_start_distance_m),
        "input_carry_efficiency_distribution": _describe_distribution(input_carry_efficiency),
        "kept_carry_efficiency_distribution": _describe_distribution(kept_carry_efficiency),
        "input_dump_end_residual_bucket_mass_distribution_kg": _describe_distribution(
            input_dump_end_residual_bucket_mass_kg
        ),
        "kept_dump_end_residual_bucket_mass_distribution_kg": _describe_distribution(
            kept_dump_end_residual_bucket_mass_kg
        ),
        "strong_dump_bucket_action_threshold": float(STAGE5_STRONG_DUMP_BUCKET_ACTION),
        "strong_dump_near_target_distance_m": float(STAGE5_STRONG_DUMP_NEAR_TARGET_DISTANCE_M),
        "input_strong_dump_frame_count_distribution": _describe_distribution(input_strong_dump_frame_counts),
        "kept_strong_dump_frame_count_distribution": _describe_distribution(kept_strong_dump_frame_counts),
        "input_strong_dump_near_target_frame_count_distribution": _describe_distribution(
            input_strong_dump_near_target_frame_counts
        ),
        "kept_strong_dump_near_target_frame_count_distribution": _describe_distribution(
            kept_strong_dump_near_target_frame_counts
        ),
        "input_strong_dump_min_target_distance_distribution_m": _describe_distribution(
            input_strong_dump_min_target_distance_m
        ),
        "kept_strong_dump_min_target_distance_distribution_m": _describe_distribution(
            kept_strong_dump_min_target_distance_m
        ),
        "input_strong_dump_first_target_distance_distribution_m": _describe_distribution(
            input_strong_dump_first_target_distance_m
        ),
        "kept_strong_dump_first_target_distance_distribution_m": _describe_distribution(
            kept_strong_dump_first_target_distance_m
        ),
        "input_strong_dump_first_height_above_rim_distribution_m": _describe_distribution(
            input_strong_dump_first_height_above_rim_m
        ),
        "kept_strong_dump_first_height_above_rim_distribution_m": _describe_distribution(
            kept_strong_dump_first_height_above_rim_m
        ),
        "action_loss_mask_policy": {
            "valid_value": 1,
            "ignored_value": 0,
            "ignored_cases": [],
            "note": (
                "default workskill builds keep action_loss_mask as all ones; "
                "pre-dump bucket action onset is reported as diagnostics instead "
                "of being masked automatically"
            ),
        },
        "input_action_loss_masked_frame_count_distribution": _describe_distribution(
            input_action_loss_masked_frame_counts
        ),
        "kept_action_loss_masked_frame_count_distribution": _describe_distribution(
            kept_action_loss_masked_frame_counts
        ),
        "input_action_loss_masked_frame_ratio_distribution": _describe_distribution(
            input_action_loss_masked_frame_ratios
        ),
        "kept_action_loss_masked_frame_ratio_distribution": _describe_distribution(
            kept_action_loss_masked_frame_ratios
        ),
        "input_early_dig_escape_count": int(input_early_dig_escape_count),
        "kept_early_dig_escape_count": int(kept_early_dig_escape_count),
        "input_collision_cycle_count": int(input_collision_cycle_count),
        "kept_collision_cycle_count": int(kept_collision_cycle_count),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2))
