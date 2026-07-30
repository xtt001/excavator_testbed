"""Contracts and pure selection helpers for layered terrain replay salvage.

This module deliberately keeps salvage evidence separate from the strict selected
replay dataset.  Runtime orchestration is added below these pure helpers so the
ranking and masking contracts remain directly testable.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.terrain_replay_pilot_gate import match_monotonic_boundaries

SALVAGE_RUN_CONTRACT_SCHEMA = "terrain_replay_salvage_run_contract_v1"
SALVAGE_EPISODE_IDS = (1, 4, 9, 10, 12, 14, 20)
STRICT_REPLAY_ORDER = (4, 9, 12, 10, 1, 14, 20)
STRICT_ATTEMPT_BUDGETS = {
    4: 10,
    9: 10,
    12: 5,
    10: 5,
    1: 5,
    14: 1,
    20: 1,
}
CORRECTED_MAX_ATTEMPTS = 3
PARENT_SELECTED_EPISODE_IDS = (
    3,
    6,
    7,
    8,
    13,
    16,
    19,
    23,
    24,
    25,
    27,
    28,
    29,
    30,
    32,
    33,
    34,
)


def validate_parent_salvage_inventory(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact immutable parent result that this salvage run extends."""

    status = str(payload.get("status", ""))
    selected = tuple(sorted(int(value) for value in payload.get("selected_episode_ids", ())))
    exhausted = tuple(
        sorted(int(value) for value in payload.get("exhausted_episode_ids", ()))
    )
    if status != "partial":
        raise ValueError(f"Parent replay status must be partial, got {status!r}.")
    if selected != tuple(sorted(PARENT_SELECTED_EPISODE_IDS)):
        raise ValueError("Parent selected inventory does not match the fixed 17 episodes.")
    if exhausted != SALVAGE_EPISODE_IDS:
        raise ValueError("Parent exhausted inventory does not match the fixed 7 episodes.")
    if set(selected) & set(exhausted):
        raise ValueError("Parent selected and exhausted inventories overlap.")
    return {
        "status": status,
        "selected_episode_count": len(selected),
        "selected_episode_ids": list(selected),
        "exhausted_episode_count": len(exhausted),
        "exhausted_episode_ids": list(exhausted),
    }


def initialize_salvage_root(
    *,
    output_root: str | Path,
    contract: Mapping[str, Any],
    resume: bool,
) -> dict[str, Any]:
    """Create a no-overwrite salvage root or verify an exact resume contract."""

    root = Path(output_root).expanduser()
    contract_path = root / "run_contract.json"
    normalized = json.loads(json.dumps(dict(contract), sort_keys=True, allow_nan=False))
    if root.exists():
        if not resume:
            raise FileExistsError(
                f"Output root {root} already exists; no-overwrite is mandatory."
            )
        if not contract_path.is_file():
            raise ValueError(f"Resume root has no run contract: {contract_path}")
        stored = json.loads(contract_path.read_text(encoding="utf-8"))
        if stored != normalized:
            raise ValueError("Resume run contract mismatch; refusing mixed lineage.")
        return {"output_root": str(root.resolve()), "resumed": True}

    if resume:
        raise FileNotFoundError(f"Resume output root does not exist: {root}")
    root.mkdir(parents=True, exist_ok=False)
    for name in (
        "strict_attempts",
        "corrected_attempts",
        "strict_selected_full_hdf5",
        "partial_salvage_full_hdf5",
        "partial_sidecars",
        "postprocess_runs",
        "training_configs",
    ):
        (root / name).mkdir(exist_ok=False)
    contract_path.write_text(
        json.dumps(normalized, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {"output_root": str(root.resolve()), "resumed": False}


def select_best_local_candidate(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Choose maximum local coverage with deterministic evidence-safe ties."""

    parsed = [dict(candidate) for candidate in candidates]
    if not parsed:
        return None

    def rank(candidate: Mapping[str, Any]) -> tuple[int, int, int, int]:
        kind = str(candidate.get("attempt_kind", ""))
        pure_preference = 1 if kind == "strict" else 0
        return (
            int(candidate.get("eligible_cycle_count", 0)),
            int(candidate.get("valid_action_step_count", 0)),
            pure_preference,
            -int(candidate.get("attempt_index", 0)),
        )

    return max(parsed, key=rank)


def build_local_action_mask(
    *,
    source_mask: np.ndarray,
    replay_qc_mask: np.ndarray,
    cycle_windows: Sequence[Mapping[str, Any]],
    eligible_cycle_ids: Sequence[int],
    realign_steps: Sequence[int],
    guard_steps: int,
) -> np.ndarray:
    """Open only eligible work/return windows, then apply source and realign masks."""

    source = np.asarray(source_mask, dtype=np.uint8).reshape(-1)
    if not np.all((source == 0) | (source == 1)):
        raise ValueError("source_mask must contain only 0 or 1.")
    replay_qc = np.asarray(replay_qc_mask, dtype=np.uint8).reshape(-1)
    if replay_qc.shape != source.shape:
        raise ValueError("replay_qc_mask must match source_mask length.")
    if not np.all((replay_qc == 0) | (replay_qc == 1)):
        raise ValueError("replay_qc_mask must contain only 0 or 1.")
    guard = int(guard_steps)
    if guard < 0:
        raise ValueError("guard_steps must be nonnegative.")
    windows = sorted(
        (
            {
                "cycle_id": int(row["cycle_id"]),
                "start_step": int(row["start_step"]),
                "end_step_exclusive": int(row["end_step_exclusive"]),
                "work_end_step_exclusive": int(
                    row.get("work_end_step_exclusive", row["end_step_exclusive"])
                ),
            }
            for row in cycle_windows
        ),
        key=lambda row: (row["start_step"], row["cycle_id"]),
    )
    eligible = {int(value) for value in eligible_cycle_ids}
    cycle_ids = [int(row["cycle_id"]) for row in windows]
    if len(cycle_ids) != len(set(cycle_ids)):
        raise ValueError("cycle_windows contains duplicate cycle ids.")
    unknown = eligible - set(cycle_ids)
    if unknown:
        raise ValueError(f"eligible_cycle_ids contains unknown ids: {sorted(unknown)}")
    previous_start = -1
    for row in windows:
        start = row["start_step"]
        end = row["end_step_exclusive"]
        work_end = row["work_end_step_exclusive"]
        if start <= previous_start:
            raise ValueError("cycle window starts must be strictly increasing.")
        if start < 0 or end <= start or end > source.shape[0]:
            raise ValueError(f"Invalid cycle window: {row}")
        if work_end <= start or work_end > end:
            raise ValueError(f"Invalid cycle work boundary: {row}")
        previous_start = start
    local = np.zeros(source.shape[0], dtype=np.uint8)
    for index, row in enumerate(windows):
        start = row["start_step"]
        if row["cycle_id"] not in eligible:
            continue
        work_end = row["work_end_step_exclusive"]
        local[start:work_end] = 1
        if index + 1 >= len(windows):
            continue
        following = windows[index + 1]
        if following["cycle_id"] not in eligible:
            continue
        transition_start = work_end
        transition_end = following["start_step"]
        realign_intersects_transition = any(
            (int(step) + guard) >= transition_start
            and (int(step) - guard) < transition_end
            for step in realign_steps
        )
        if transition_end > transition_start and not realign_intersects_transition:
            local[transition_start:transition_end] = 1

    for raw_step in realign_steps:
        step = int(raw_step)
        start = max(0, step - guard)
        end = min(source.shape[0], step + guard + 1)
        local[start:end] = 0
    final = (
        source.astype(bool) & replay_qc.astype(bool) & local.astype(bool)
    ).astype(np.uint8)
    if np.any(final > source):
        raise AssertionError("Local salvage mask reopened source-masked steps.")
    if np.any(final > replay_qc):
        raise AssertionError("Local salvage mask reopened replay-QC-masked steps.")
    return final


def evaluate_local_cycle_eligibility(
    *,
    source_qpos: np.ndarray,
    source_env_state: np.ndarray,
    replay_qpos: np.ndarray,
    replay_env_state: np.ndarray,
    source_cycles: Sequence[Mapping[str, Any]],
    candidate_records: Sequence[Mapping[str, Any]],
    realign_steps: Sequence[int],
    camera_step_valid_mask: np.ndarray | None = None,
    replay_cycle_validity: Mapping[int, bool] | None = None,
    control_hz: float,
    qpos_error_limit: float = 0.02,
    valid_fraction_min: float = 0.5,
) -> dict[str, Any]:
    """Evaluate source-aligned local cycles without weakening the episode gate."""

    source_q = np.asarray(source_qpos, dtype=np.float32)
    replay_q = np.asarray(replay_qpos, dtype=np.float32)
    source_env = np.asarray(source_env_state, dtype=np.float32)
    replay_env = np.asarray(replay_env_state, dtype=np.float32)
    if source_q.ndim != 2 or replay_q.ndim != 2 or source_q.shape[1:] != (4,):
        raise ValueError("source/replay qpos must have shape (T, 4).")
    if replay_q.shape[1:] != (4,):
        raise ValueError("source/replay qpos must have shape (T, 4).")
    if source_env.ndim != 2 or replay_env.ndim != 2:
        raise ValueError("source/replay env_state must be rank 2.")
    step_count = min(len(source_q), len(replay_q), len(source_env), len(replay_env))
    if step_count <= 0:
        raise ValueError("source/replay arrays must be nonempty.")
    camera_mask = (
        np.ones(step_count, dtype=np.uint8)
        if camera_step_valid_mask is None
        else np.asarray(camera_step_valid_mask, dtype=np.uint8).reshape(-1)
    )
    if camera_mask.shape[0] < step_count:
        raise ValueError("camera_step_valid_mask is shorter than replay arrays.")
    camera_mask = camera_mask[:step_count]
    if not np.all((camera_mask == 0) | (camera_mask == 1)):
        raise ValueError("camera_step_valid_mask must contain only 0 or 1.")
    native_validity = {
        int(key): bool(value)
        for key, value in dict(replay_cycle_validity or {}).items()
    }

    source_rows = sorted(
        (dict(row) for row in source_cycles),
        key=lambda row: (
            int(row.get("dump_end_step", int(row["end_step_exclusive"]) - 1)),
            int(row["cycle_id"]),
        ),
    )
    source_boundaries = [
        (
            int(row["cycle_id"]),
            int(row.get("dump_end_step", int(row["end_step_exclusive"]) - 1)),
        )
        for row in source_rows
    ]
    grouped: dict[int, list[dict[str, Any]]] = {}
    for raw in candidate_records:
        row = dict(raw)
        grouped.setdefault(int(row["cycle_index"]), []).append(row)
    observed_boundaries = sorted(
        [
            (
            cycle_index,
            _representative_int(
                row["cycle_end_observation_index"] for row in rows
            ),
            )
            for cycle_index, rows in grouped.items()
        ],
        key=lambda item: (item[1], item[0]),
    )
    tolerance_steps = max(0, int(round(float(control_hz))))
    matches = match_monotonic_boundaries(
        source_boundaries,
        observed_boundaries,
        tolerance_steps=tolerance_steps,
    )
    source_by_id = {int(row["cycle_id"]): row for row in source_rows}
    observed_by_id = grouped
    guard_steps = tolerance_steps
    realigns = tuple(int(value) for value in realign_steps)
    expected_targets = {
        "recording_depth_0p08_full_grid_diagnostic",
        "t1_large_shallow_rectangular_pit_default",
        "t2_long_shallow_trench_default",
    }
    cycle_rows: list[dict[str, Any]] = []
    eligible_ids: list[int] = []
    matched_source_ids: set[int] = set()
    for match in matches:
        source_cycle_id = int(match["source_cycle_id"])
        observed_cycle_index = int(match["observed_cycle_index"])
        matched_source_ids.add(source_cycle_id)
        source_row = source_by_id[source_cycle_id]
        records = observed_by_id[observed_cycle_index]
        start = int(source_row["start_step"])
        end = min(int(source_row["end_step_exclusive"]), step_count)
        work_end = min(
            end,
            int(source_row.get("dump_end_step", end - 1)) + 1,
        )
        reasons: list[str] = []
        targets = {str(row.get("target_id", "")) for row in records}
        if targets != expected_targets or len(records) != len(expected_targets):
            reasons.append("replay_snapshot_target_set_incomplete")
        observed_starts = {
            int(row.get("cycle_start_observation_index", -1)) for row in records
        }
        observed_ends = {
            int(row.get("cycle_end_observation_index", -1)) for row in records
        }
        if len(observed_starts) != 1 or len(observed_ends) != 1:
            reasons.append("replay_snapshot_boundary_disagreement")
        if not native_validity.get(observed_cycle_index, True):
            reasons.append("replay_native_cycle_invalid")
        if not all(bool(row.get("grid_geometry_stable", False)) for row in records):
            reasons.append("grid_geometry_unstable")
        fractions = [
            _minimum_fraction(row.get(key))
            for row in records
            for key in ("surface_valid_fraction_start", "surface_valid_fraction_end")
        ]
        if not fractions or min(fractions) < float(valid_fraction_min):
            reasons.append("target_cell_valid_fraction_below_minimum")
        if start < 0 or end <= start:
            reasons.append("source_cycle_window_invalid")
            entry_error = None
            source_contact = None
            replay_contact = None
            contact_error = None
        else:
            entry_error = float(np.max(np.abs(source_q[start] - replay_q[start])))
            if entry_error > float(qpos_error_limit):
                reasons.append("cycle_entry_qpos_error_exceeded")
            source_contact = _first_contact_step(
                source_env, start=start, end=work_end
            )
            replay_contact = _first_contact_step(
                replay_env, start=start, end=work_end
            )
            if source_contact is None or replay_contact is None:
                contact_error = None
                reasons.append("qualified_contact_missing")
            else:
                pre_contact_end = min(
                    work_end,
                    max(int(source_contact), int(replay_contact)) + 1,
                )
                contact_error = float(
                    np.max(np.abs(source_q[start:pre_contact_end] - replay_q[start:pre_contact_end]))
                )
                if contact_error > float(qpos_error_limit):
                    reasons.append("pre_contact_qpos_error_exceeded")
        if start >= 0 and end > start and np.any(camera_mask[start:end] == 0):
            reasons.append("cycle_contains_invalid_camera_step")
        if any(
            (start - guard_steps) <= step < (work_end + guard_steps)
            for step in realigns
        ):
            reasons.append("cycle_or_guard_contains_pose_realign")
        eligible = not reasons
        if eligible:
            eligible_ids.append(source_cycle_id)
        cycle_rows.append(
            {
                "schema": "terrain_replay_local_cycle_eligibility_v1",
                "source_cycle_id": source_cycle_id,
                "observed_cycle_index": observed_cycle_index,
                "start_step": start,
                "end_step_exclusive": end,
                "work_end_step_exclusive": work_end,
                "boundary_error_steps": int(match["boundary_error_steps"]),
                "cycle_entry_qpos_error": entry_error,
                "source_first_contact_step": source_contact,
                "replay_first_contact_step": replay_contact,
                "pre_contact_qpos_error": contact_error,
                "eligible": eligible,
                "reason_codes": list(dict.fromkeys(reasons)),
            }
        )
    for source_row in source_rows:
        source_cycle_id = int(source_row["cycle_id"])
        if source_cycle_id in matched_source_ids:
            continue
        cycle_rows.append(
            {
                "schema": "terrain_replay_local_cycle_eligibility_v1",
                "source_cycle_id": source_cycle_id,
                "observed_cycle_index": None,
                "start_step": int(source_row["start_step"]),
                "end_step_exclusive": int(source_row["end_step_exclusive"]),
                "work_end_step_exclusive": min(
                    int(source_row["end_step_exclusive"]),
                    int(
                        source_row.get(
                            "dump_end_step",
                            int(source_row["end_step_exclusive"]) - 1,
                        )
                    )
                    + 1,
                ),
                "boundary_error_steps": None,
                "cycle_entry_qpos_error": None,
                "source_first_contact_step": None,
                "replay_first_contact_step": None,
                "pre_contact_qpos_error": None,
                "eligible": False,
                "reason_codes": ["source_cycle_boundary_unmatched"],
            }
        )
    cycle_rows.sort(key=lambda row: int(row["source_cycle_id"]))
    return {
        "schema": "terrain_replay_local_cycle_eligibility_summary_v1",
        "eligible_source_cycle_ids": sorted(eligible_ids),
        "eligible_cycle_count": len(eligible_ids),
        "source_cycle_count": len(source_rows),
        "matched_cycle_count": len(matches),
        "boundary_tolerance_steps": tolerance_steps,
        "qpos_error_limit": float(qpos_error_limit),
        "valid_fraction_min": float(valid_fraction_min),
        "cycle_rows": cycle_rows,
    }


def _minimum_fraction(value: Any) -> float:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parsed = [float(item) for item in value]
        return min(parsed) if parsed and all(math.isfinite(item) for item in parsed) else 0.0
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _first_contact_step(env_state: np.ndarray, *, start: int, end: int) -> int | None:
    if env_state.shape[1] <= 31:
        return None
    for step in range(max(0, int(start)), min(int(end), len(env_state))):
        penetration = float(env_state[step, 61]) if env_state.shape[1] > 61 else 0.0
        local_depth = float(env_state[step, 31])
        if penetration > 0.5 or local_depth >= 0.005:
            return step
    return None


def _representative_int(values: Sequence[Any] | Any) -> int:
    parsed = [int(value) for value in values]
    if not parsed:
        raise ValueError("Cannot choose a representative from an empty sequence.")
    counts = Counter(parsed)
    return min(parsed, key=lambda value: (-counts[value], value))


__all__ = [
    "CORRECTED_MAX_ATTEMPTS",
    "PARENT_SELECTED_EPISODE_IDS",
    "SALVAGE_EPISODE_IDS",
    "SALVAGE_RUN_CONTRACT_SCHEMA",
    "STRICT_ATTEMPT_BUDGETS",
    "STRICT_REPLAY_ORDER",
    "build_local_action_mask",
    "evaluate_local_cycle_eligibility",
    "initialize_salvage_root",
    "select_best_local_candidate",
    "validate_parent_salvage_inventory",
]
