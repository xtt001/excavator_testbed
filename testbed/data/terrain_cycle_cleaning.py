"""Step- and cycle-level cleaning for the approved 2026-07-17 terrain batch."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

APPROVED_TERRAIN_DATASET_ROOT = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_v2_2_pro_full_task_four_camera_jpeg_20260717"
)
EXPECTED_TERRAIN_EPISODE_COUNT = 36
CONTROLLER_EPOCH_BOUNDARY_EPISODE_ID = 22

CLEANING_SCHEMA = "terrain_cycle_cleaning_v1"
WINDOW_SCHEMA = "terrain_contamination_window_v1"
CYCLE_SCHEMA = "terrain_cycle_eligibility_v1"


@dataclass(frozen=True)
class TerrainCycleCleaningConfig:
    pause_action_l1_eps: float = 0.05
    pause_review_min_s: float = 2.0
    pause_auto_mask_s: float = 5.0
    timestamp_gap_s: float = 0.1
    qpos_jump_threshold: float = 0.05
    qvel_jump_threshold: float = 5.0
    guard_s: float = 1.0
    fallback_dt_s: float = 0.02
    deposit_fraction_min: float = 0.0
    deposit_fraction_max: float = 1.05


@dataclass
class EpisodeCleaningResult:
    episode_id: int
    controller_epoch: str
    episode_role: str
    action_loss_mask: np.ndarray
    default_action_loss_mask: np.ndarray
    windows: list[dict[str, Any]] = field(default_factory=list)
    cycles: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def validate_source_root(
    dataset_dir: str | Path,
    *,
    approved_root: str | Path = APPROVED_TERRAIN_DATASET_ROOT,
) -> Path:
    candidate = Path(dataset_dir).expanduser().resolve()
    approved = Path(approved_root).expanduser().resolve()
    if candidate != approved:
        raise ValueError(
            f"Input must equal the approved dataset root {approved}; got {candidate}."
        )
    return candidate


def resolve_approved_episode_paths(
    dataset_dir: str | Path,
    *,
    approved_root: str | Path = APPROVED_TERRAIN_DATASET_ROOT,
    expected_episode_count: int = EXPECTED_TERRAIN_EPISODE_COUNT,
) -> list[Path]:
    root = validate_source_root(dataset_dir, approved_root=approved_root)
    expected = [root / f"episode_{index}.hdf5" for index in range(expected_episode_count)]
    discovered = sorted(
        root.glob("episode_*.hdf5"),
        key=lambda path: _episode_number(path.name),
    )
    if [path.name for path in discovered] != [path.name for path in expected]:
        raise ValueError(
            "Approved root does not contain the exact episode inventory "
            f"episode_0..episode_{expected_episode_count - 1}."
        )
    for path in expected:
        realpath = path.resolve(strict=True)
        try:
            realpath.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Episode realpath is outside approved dataset root: {realpath}"
            ) from exc
        if not realpath.is_file():
            raise ValueError(f"Approved episode is not a regular file: {realpath}")
    return expected


def analyze_episode_cleaning(
    *,
    episode_id: int,
    actions: np.ndarray,
    qpos: np.ndarray,
    qvel: np.ndarray,
    step_ids: np.ndarray | None,
    step_ns: np.ndarray | None,
    v2_step: dict[str, np.ndarray],
    v2_cycle: dict[str, np.ndarray],
    camera_step_valid_mask: np.ndarray | None,
    config: TerrainCycleCleaningConfig | None = None,
) -> EpisodeCleaningResult:
    cfg = config or TerrainCycleCleaningConfig()
    action_arr = _rank2(actions, "actions")
    qpos_arr = _rank2(qpos, "qpos")
    qvel_arr = _rank2(qvel, "qvel")
    steps = int(action_arr.shape[0])
    if qpos_arr.shape[0] != steps or qvel_arr.shape[0] != steps:
        raise ValueError("actions, qpos, and qvel must share the same length.")

    timestamps = _timestamps(step_ns, steps=steps, fallback_dt_s=cfg.fallback_dt_s)
    ids = _optional_vector(step_ids, steps=steps, dtype=np.int64)
    step_cycle = _step_vector(
        v2_step.get("cycle_id"), steps=steps, dtype=np.int32, default=-1
    )
    work_stage = _step_vector(
        v2_step.get("work_stage_id"), steps=steps, dtype=np.uint8, default=0
    )
    camera_valid = (
        np.ones(steps, dtype=bool)
        if camera_step_valid_mask is None
        else _step_vector(
            camera_step_valid_mask, steps=steps, dtype=np.uint8, default=0
        ).astype(bool)
    )

    action_mask = np.ones(steps, dtype=np.uint8)
    default_mask = np.ones(steps, dtype=np.uint8)
    windows: list[dict[str, Any]] = []
    cycles = _cycle_records(
        episode_id=int(episode_id),
        step_cycle=step_cycle,
        v2_cycle=v2_cycle,
        steps=steps,
        cfg=cfg,
    )
    cycles_by_id = {int(row["cycle_id"]): row for row in cycles}

    def add_window(
        start: int,
        end: int,
        *,
        reason: str,
        severity: str,
        mask_steps: bool,
        hard_cycle_ids: set[int] | None = None,
        review_cycle_ids: set[int] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        bounded_start = max(0, min(int(start), steps))
        bounded_end = max(bounded_start, min(int(end), steps))
        if bounded_end <= bounded_start:
            return
        if mask_steps:
            action_mask[bounded_start:bounded_end] = 0
            default_mask[bounded_start:bounded_end] = 0
        hard_ids = set(hard_cycle_ids or set())
        review_ids = set(review_cycle_ids or set())
        stage_ids = sorted(
            int(value)
            for value in np.unique(work_stage[bounded_start:bounded_end])
        )
        if stage_ids and all(value == 0 for value in stage_ids):
            stage_scope = "inter_cycle_or_none"
        elif stage_ids and all(value != 0 for value in stage_ids):
            stage_scope = "active"
        else:
            stage_scope = "mixed"
        if reason == "nonfinite_state":
            treatment_decision = (
                "local_mask_cycle_reject_and_episode_diagnostic"
            )
        elif hard_ids:
            treatment_decision = "local_mask_and_containing_cycle_reject"
        elif review_ids:
            treatment_decision = "cycle_review_and_default_pool_exclusion"
        elif mask_steps:
            treatment_decision = "local_action_loss_mask_only"
        else:
            treatment_decision = "retain_without_mask"
        for cycle_id in sorted(hard_ids):
            cycle = cycles_by_id.get(cycle_id)
            if cycle is None:
                continue
            cycle["hard_reject"] = True
            _append_reason(cycle, reason)
        for cycle_id in sorted(review_ids):
            cycle = cycles_by_id.get(cycle_id)
            if cycle is None:
                continue
            cycle["review_required"] = True
            _append_reason(cycle, reason)
        windows.append(
            {
                "schema": WINDOW_SCHEMA,
                "source_episode_id": f"episode_{int(episode_id)}",
                "start_step": bounded_start,
                "end_step_exclusive": bounded_end,
                "start_time_ns": int(timestamps[bounded_start]),
                "end_time_ns": int(_interval_end_ns(timestamps, bounded_end, cfg)),
                "duration_s": float(
                    max(
                        0,
                        _interval_end_ns(timestamps, bounded_end, cfg)
                        - int(timestamps[bounded_start]),
                    )
                    / 1_000_000_000.0
                ),
                "reason": reason,
                "severity": severity,
                "mask_applied": bool(mask_steps),
                "work_stage_ids": stage_ids,
                "work_stage_scope": stage_scope,
                "treatment_decision": treatment_decision,
                "cycle_ids": sorted(
                    int(value)
                    for value in np.unique(step_cycle[bounded_start:bounded_end])
                    if int(value) >= 0
                ),
                "details": dict(details or {}),
            }
        )

    # Pause policy is time-based; rows remain physically present in every VDS.
    action_l1 = np.sum(np.abs(action_arr), axis=1)
    pause = action_l1 < float(cfg.pause_action_l1_eps)
    for start, end in _true_intervals(pause):
        duration_s = _duration_s(timestamps, start=start, end=end, cfg=cfg)
        cycle_ids = _cycle_ids(step_cycle[start:end])
        if duration_s >= float(cfg.pause_auto_mask_s):
            add_window(
                start,
                end,
                reason="long_pause",
                severity="mask",
                mask_steps=True,
                details={"pause_duration_s": duration_s},
            )
        elif duration_s >= float(cfg.pause_review_min_s) and bool(
            np.any(work_stage[start:end] != 0)
        ):
            add_window(
                start,
                end,
                reason="pause_review_active_stage",
                severity="review",
                mask_steps=False,
                review_cycle_ids=cycle_ids,
                details={"pause_duration_s": duration_s},
            )

    # Non-finite state is a hard semantic break for its containing cycle.
    nonfinite = ~(
        np.isfinite(action_arr).all(axis=1)
        & np.isfinite(qpos_arr).all(axis=1)
        & np.isfinite(qvel_arr).all(axis=1)
    )
    for start, end in _true_intervals(nonfinite):
        add_window(
            start,
            end,
            reason="nonfinite_state",
            severity="hard",
            mask_steps=True,
            hard_cycle_ids=_cycle_ids(step_cycle[start:end]),
        )

    hard_event_steps: set[int] = set()
    if steps > 1:
        qpos_delta = np.max(np.abs(np.diff(qpos_arr, axis=0)), axis=1)
        for step in (np.flatnonzero(qpos_delta >= cfg.qpos_jump_threshold) + 1).tolist():
            hard_event_steps.add(int(step))
            start, end = _guard_bounds(timestamps, int(step), cfg=cfg)
            add_window(
                start,
                end,
                reason="qpos_jump",
                severity="hard",
                mask_steps=True,
                hard_cycle_ids=_cycle_ids(step_cycle[int(step) : int(step) + 1]),
                details={"max_abs_delta": float(qpos_delta[int(step) - 1])},
            )
        qvel_delta = np.max(np.abs(np.diff(qvel_arr, axis=0)), axis=1)
        for step in (np.flatnonzero(qvel_delta >= cfg.qvel_jump_threshold) + 1).tolist():
            hard_event_steps.add(int(step))
            start, end = _guard_bounds(timestamps, int(step), cfg=cfg)
            add_window(
                start,
                end,
                reason="qvel_jump",
                severity="hard",
                mask_steps=True,
                hard_cycle_ids=_cycle_ids(step_cycle[int(step) : int(step) + 1]),
                details={"max_abs_delta": float(qvel_delta[int(step) - 1])},
            )

    if ids is not None and steps > 1:
        id_delta = np.diff(ids)
        for step in (np.flatnonzero(id_delta != 1) + 1).tolist():
            hard_event_steps.add(int(step))
            start, end = _guard_bounds(timestamps, int(step), cfg=cfg)
            add_window(
                start,
                end,
                reason="step_id_discontinuity",
                severity="hard",
                mask_steps=True,
                hard_cycle_ids=_cycle_ids(step_cycle[int(step) : int(step) + 1]),
                details={"step_id_delta": int(id_delta[int(step) - 1])},
            )

    if steps > 1:
        timestamp_delta = np.diff(timestamps)
        for step in (np.flatnonzero(timestamp_delta <= 0) + 1).tolist():
            hard_event_steps.add(int(step))
            start, end = _guard_bounds(timestamps, int(step), cfg=cfg)
            add_window(
                start,
                end,
                reason="timestamp_regression",
                severity="hard",
                mask_steps=True,
                hard_cycle_ids=_cycle_ids(step_cycle[int(step) : int(step) + 1]),
                details={"timestamp_delta_ns": int(timestamp_delta[int(step) - 1])},
            )
        threshold_ns = int(round(float(cfg.timestamp_gap_s) * 1_000_000_000.0))
        for step in (np.flatnonzero(timestamp_delta > threshold_ns) + 1).tolist():
            start, end = _guard_bounds(timestamps, int(step), cfg=cfg)
            add_window(
                start,
                end,
                reason="timestamp_gap",
                severity="mask",
                mask_steps=True,
                details={"timestamp_delta_ns": int(timestamp_delta[int(step) - 1])},
            )

    for start, end in _true_intervals(~camera_valid):
        add_window(
            start,
            end,
            reason="camera_frame_invalid",
            severity="mask",
            mask_steps=True,
        )

    all_zero_action = bool(steps == 0 or np.all(action_l1 < cfg.pause_action_l1_eps))
    complete_cycle_count = sum(bool(row["complete_cycle"]) for row in cycles)
    missing_camera_route = bool(steps > 0 and not np.any(camera_valid))
    nonfinite_numeric_present = bool(np.any(nonfinite))
    diagnostic_only = (
        all_zero_action
        or nonfinite_numeric_present
        or complete_cycle_count == 0
        or missing_camera_route
    )
    if diagnostic_only:
        default_mask[:] = 0

    # A hard/review cycle is excluded as a cycle, while neighboring cycles survive.
    for cycle in cycles:
        start = int(cycle["start_step"])
        end = int(cycle["end_step_exclusive"])
        if bool(cycle["hard_reject"]) or bool(cycle["review_required"]):
            default_mask[start:end] = 0
        cycle["act_training_eligible"] = bool(
            not diagnostic_only and np.any(default_mask[start:end] == 1)
        )
        cycle["effect_calibration_eligible"] = bool(
            cycle["complete_cycle"]
            and not cycle["hard_reject"]
            and not cycle["review_required"]
            and not diagnostic_only
        )
        cycle["replay_candidate"] = bool(
            cycle["complete_cycle"]
            and not cycle["hard_reject"]
            and not cycle["review_required"]
            and not diagnostic_only
        )
        cycle["diagnostic_only"] = bool(diagnostic_only)
        cycle.pop("hard_reject", None)

    epoch = (
        "pre_fix_candidate"
        if int(episode_id) < CONTROLLER_EPOCH_BOUNDARY_EPISODE_ID
        else "post_fix_candidate"
    )
    for cycle in cycles:
        cycle["controller_epoch"] = epoch
    role = (
        "diagnostic_only"
        if diagnostic_only
        else ("post_fix_default" if epoch == "post_fix_candidate" else "pre_fix_salvage")
    )
    return EpisodeCleaningResult(
        episode_id=int(episode_id),
        controller_epoch=epoch,
        episode_role=role,
        action_loss_mask=action_mask,
        default_action_loss_mask=default_mask,
        windows=windows,
        cycles=cycles,
        diagnostics={
            "schema": CLEANING_SCHEMA,
            "step_count": steps,
            "masked_step_count": int(np.sum(action_mask == 0)),
            "default_masked_step_count": int(np.sum(default_mask == 0)),
            "complete_cycle_count": int(complete_cycle_count),
            "all_zero_action": all_zero_action,
            "nonfinite_numeric_present": nonfinite_numeric_present,
            "missing_camera_route": missing_camera_route,
            "hard_event_step_count": len(hard_event_steps),
        },
    )


def _cycle_records(
    *,
    episode_id: int,
    step_cycle: np.ndarray,
    v2_cycle: dict[str, np.ndarray],
    steps: int,
    cfg: TerrainCycleCleaningConfig,
) -> list[dict[str, Any]]:
    cycle_ids = np.asarray(v2_cycle.get("cycle_id", []), dtype=np.int32).reshape(-1)
    starts = np.asarray(v2_cycle.get("start_step", []), dtype=np.int64).reshape(-1)
    dumps = np.asarray(v2_cycle.get("dump_end_step", []), dtype=np.int64).reshape(-1)
    ends = np.asarray(v2_cycle.get("end_step", []), dtype=np.int64).reshape(-1)
    if not (
        len(cycle_ids) == len(starts) == len(dumps) == len(ends)
    ):
        raise ValueError("v2 cycle id/start/dump/end fields must share one length.")
    fill_peak = _cycle_float(v2_cycle.get("fill_peak_kg"), len(cycle_ids))
    deposit = _cycle_float(v2_cycle.get("deposit_delta_kg"), len(cycle_ids))
    records: list[dict[str, Any]] = []
    for index, cycle_id in enumerate(cycle_ids.tolist()):
        start = int(np.clip(starts[index], 0, max(0, steps - 1))) if steps else 0
        raw_end = int(ends[index])
        if raw_end >= start:
            end = min(steps, raw_end + 1)
        else:
            positions = np.flatnonzero(step_cycle == int(cycle_id))
            end = int(positions[-1]) + 1 if positions.size else min(steps, start + 1)
        complete = bool(int(dumps[index]) >= start and raw_end >= start)
        peak = float(fill_peak[index])
        deposited = float(deposit[index])
        fraction = deposited / peak if peak > 0.0 else math.nan
        deposit_valid = bool(
            math.isfinite(fraction)
            and cfg.deposit_fraction_min <= fraction <= cfg.deposit_fraction_max
        )
        reasons: list[str] = []
        if not complete:
            reasons.append("incomplete_cycle")
        if not deposit_valid:
            reasons.append("invalid_deposit_fraction")
        records.append(
            {
                "schema": CYCLE_SCHEMA,
                "source_episode_id": f"episode_{episode_id}",
                "source_path": str(
                    APPROVED_TERRAIN_DATASET_ROOT / f"episode_{episode_id}.hdf5"
                ),
                "cycle_id": int(cycle_id),
                "cycle_index": int(index),
                "start_step": start,
                "end_step_exclusive": end,
                "dump_end_step": int(dumps[index]),
                "complete_cycle": complete,
                "review_required": False,
                "hard_reject": False,
                "deposit_label_valid": deposit_valid,
                "deposited_fraction": None if not math.isfinite(fraction) else fraction,
                "reason_codes": reasons,
            }
        )
    return records


def _append_reason(cycle: dict[str, Any], reason: str) -> None:
    reasons = cycle.setdefault("reason_codes", [])
    if reason not in reasons:
        reasons.append(reason)


def _timestamps(
    value: np.ndarray | None,
    *,
    steps: int,
    fallback_dt_s: float,
) -> np.ndarray:
    if value is None:
        return np.arange(steps, dtype=np.int64) * int(
            round(float(fallback_dt_s) * 1_000_000_000.0)
        )
    arr = np.asarray(value, dtype=np.int64).reshape(-1)
    if arr.shape != (steps,):
        raise ValueError("step_ns length does not match episode length.")
    return arr


def _interval_end_ns(
    timestamps: np.ndarray,
    end: int,
    cfg: TerrainCycleCleaningConfig,
) -> int:
    if end < len(timestamps):
        return int(timestamps[end])
    if len(timestamps) == 0:
        return 0
    positive = np.diff(timestamps)
    positive = positive[positive > 0]
    fallback = int(round(float(cfg.fallback_dt_s) * 1_000_000_000.0))
    dt = int(np.median(positive)) if positive.size else fallback
    return int(timestamps[-1]) + max(1, dt)


def _duration_s(
    timestamps: np.ndarray,
    *,
    start: int,
    end: int,
    cfg: TerrainCycleCleaningConfig,
) -> float:
    return float(
        max(0, _interval_end_ns(timestamps, end, cfg) - int(timestamps[start]))
        / 1_000_000_000.0
    )


def _guard_bounds(
    timestamps: np.ndarray,
    step: int,
    *,
    cfg: TerrainCycleCleaningConfig,
) -> tuple[int, int]:
    if len(timestamps) == 0:
        return 0, 0
    guard_ns = max(0, int(round(float(cfg.guard_s) * 1_000_000_000.0)))
    if guard_ns == 0:
        return int(step), min(len(timestamps), int(step) + 1)
    if np.all(np.diff(timestamps) >= 0):
        center = int(timestamps[int(step)])
        start = int(np.searchsorted(timestamps, center - guard_ns, side="left"))
        end = int(np.searchsorted(timestamps, center + guard_ns, side="right"))
        return start, max(start + 1, min(len(timestamps), end))
    radius = int(math.ceil(float(cfg.guard_s) / max(cfg.fallback_dt_s, 1.0e-9)))
    return max(0, int(step) - radius), min(len(timestamps), int(step) + radius + 1)


def _true_intervals(mask: np.ndarray) -> list[tuple[int, int]]:
    values = np.asarray(mask, dtype=bool).reshape(-1)
    if values.size == 0:
        return []
    padded = np.concatenate(([False], values, [False])).astype(np.int8)
    delta = np.diff(padded)
    starts = np.flatnonzero(delta == 1)
    ends = np.flatnonzero(delta == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends, strict=True)]


def _cycle_ids(values: np.ndarray) -> set[int]:
    return {int(value) for value in np.unique(values) if int(value) >= 0}


def _rank2(value: np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be rank-2, got {arr.shape}.")
    return arr


def _optional_vector(
    value: np.ndarray | None,
    *,
    steps: int,
    dtype: Any,
) -> np.ndarray | None:
    if value is None:
        return None
    arr = np.asarray(value, dtype=dtype).reshape(-1)
    if arr.shape != (steps,):
        raise ValueError("Optional step vector length does not match episode length.")
    return arr


def _step_vector(
    value: np.ndarray | None,
    *,
    steps: int,
    dtype: Any,
    default: int,
) -> np.ndarray:
    if value is None:
        return np.full(steps, default, dtype=dtype)
    arr = np.asarray(value, dtype=dtype).reshape(-1)
    if arr.shape != (steps,):
        raise ValueError("V2 step vector length does not match episode length.")
    return arr


def _cycle_float(value: np.ndarray | None, length: int) -> np.ndarray:
    if value is None:
        return np.zeros(length, dtype=np.float64)
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    if arr.shape != (length,):
        raise ValueError("V2 cycle float field length mismatch.")
    return arr


def _episode_number(name: str) -> int:
    try:
        return int(Path(name).stem.split("_", 1)[1])
    except (IndexError, ValueError):
        return 10**9


__all__ = [
    "APPROVED_TERRAIN_DATASET_ROOT",
    "CLEANING_SCHEMA",
    "CONTROLLER_EPOCH_BOUNDARY_EPISODE_ID",
    "EXPECTED_TERRAIN_EPISODE_COUNT",
    "EpisodeCleaningResult",
    "TerrainCycleCleaningConfig",
    "analyze_episode_cleaning",
    "resolve_approved_episode_paths",
    "validate_source_root",
]
