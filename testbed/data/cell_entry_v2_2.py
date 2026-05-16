"""V2.2 Cell Entry enrichment builder.

This builder adds planned/actual/audit fields for the fixed 3x2 DigArea grid
without changing the primitive ACT inputs. Existing `/v2` labels are preserved.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.hdf5_io import list_episodes, read_episode, write_episode
from testbed.data.schema import (
    ATTR_GOAL_TOKEN_DIM,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
)
from testbed.data.vds import (
    EPISODE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    STORAGE_MODE_VDS,
    write_lineage_json,
    write_vds_episode,
)
from testbed.planner.cell_entry import (
    CELL_ENTRY_TOKEN_DIM,
    CELL_ENTRY_VERSION,
    CellEntryPlanner,
    CellGridSpec,
    PlannerDecisionAuditor,
    PrimitiveCycleOutcome,
    build_cell_entry_tokens,
)


@dataclass(frozen=True)
class CycleWindow:
    cycle_id: int
    start_step: int
    end_step_exclusive: int


def build_cell_entry_dataset(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    grid: CellGridSpec | None = None,
    overwrite: bool = False,
    storage_mode: str = STORAGE_MODE_COPY,
) -> dict[str, Any]:
    """Build a Cell Entry enriched raw dataset."""
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    grid = grid or CellGridSpec()
    grid.validate()
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

    summaries: list[dict[str, Any]] = []
    for source_path in episode_paths:
        episode = read_episode(source_path, load_images=(storage_mode == STORAGE_MODE_COPY))
        enriched_v2, summary = enrich_episode_cell_entry(
            episode=episode,
            grid=grid,
            source_episode=str(source_path),
        )
        target_path = output_dir / source_path.name
        metadata = dict(episode.get("metadata", {}) or {})
        metadata.update(
            {
                "cell_entry_version": CELL_ENTRY_VERSION,
                "cell_entry_grid_long_count": int(grid.long_count),
                "cell_entry_grid_short_count": int(grid.short_count),
                "cell_entry_token_dim": int(CELL_ENTRY_TOKEN_DIM),
                "cell_entry_storage_mode": str(storage_mode),
                ATTR_GOAL_TOKEN_DIM: metadata.get(ATTR_GOAL_TOKEN_DIM, 10),
            }
        )
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
        summaries.append(summary)

    summary_payload = _build_dataset_summary(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        grid=grid,
        episode_summaries=summaries,
        storage_mode=storage_mode,
    )
    with open(output_dir / "cell_entry_summary.json", "w") as f:
        json.dump(_jsonable(summary_payload), f, indent=2, sort_keys=True)
    write_lineage_json(
        output_dir,
        builder="tb-build-cell-entry-v2_2",
        storage_mode=storage_mode,
        source_roots=[dataset_dir],
        input_dataset_ids=[dataset_dir.name],
        schema_versions={
            "hdf5": "1.1",
            "cell_entry": CELL_ENTRY_VERSION,
        },
        extra={"grid": asdict(grid)},
    )
    return summary_payload


def enrich_episode_cell_entry(
    *,
    episode: dict[str, Any],
    grid: CellGridSpec | None = None,
    source_episode: str = "",
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    grid = grid or CellGridSpec()
    grid.validate()
    n_steps = int(np.asarray(episode["actions"]).shape[0])
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
        n_steps=n_steps, v2_step=step_existing, v2_cycle=cycle_existing
    )
    planner = CellEntryPlanner(grid=grid)
    auditor = PlannerDecisionAuditor(grid=grid)

    step_payload = _init_step_payload(n_steps)
    cycle_payload = _init_cycle_payload(len(windows))
    audit_records: list[dict[str, Any]] = []

    for cycle_index, window in enumerate(windows):
        grid_for_cycle = _grid_from_env_or_default(env_arr, window.start_step, grid)
        planner.grid = grid_for_cycle
        auditor.grid = grid_for_cycle
        goal = planner.plan(cycle_id=window.cycle_id)
        outcome = _build_outcome(
            env_state=env_arr,
            v2_step=step_existing,
            window=window,
            previous_window=windows[cycle_index - 1] if cycle_index > 0 else None,
        )
        current_pose = _bucket_pose_for_step(env_arr, outcome.actual_start_step)
        geometry_available = _cell_geometry_available(
            env_arr, outcome.actual_start_step
        )
        audit = auditor.audit(
            goal=goal,
            outcome=outcome,
            current_bucket_pose=current_pose,
            geometry_available=geometry_available,
        )
        tokens = build_cell_entry_tokens(grid=grid_for_cycle, goal=goal, audit=audit)
        planner.update(outcome)

        _fill_step_payload(
            step_payload=step_payload,
            start=window.start_step,
            end=window.end_step_exclusive,
            goal=goal,
            audit=audit,
            token=tokens,
            env_state=env_arr,
        )
        _fill_cycle_payload(
            cycle_payload=cycle_payload,
            cycle_index=cycle_index,
            window=window,
            goal=goal,
            outcome=outcome,
            audit=audit,
        )
        audit_records.append(
            {
                "goal": goal.to_dict(),
                "outcome": outcome.to_dict(),
                "audit": audit.to_dict(),
            }
        )

    computed_step_payload = dict(step_payload)
    computed_cycle_payload = dict(cycle_payload)
    step_payload = dict(step_existing)
    # Our newly computed fields should win over old versions if rerun.
    step_payload.update(_computed_step_fields(computed_step_payload))
    cycle_payload = dict(cycle_existing)
    cycle_payload.update(_computed_cycle_fields(computed_cycle_payload))

    summary = {
        "source_episode": str(source_episode),
        "episode_len": int(n_steps),
        "cycle_count": int(len(windows)),
        "planner_ok_count": int(np.sum(cycle_payload["cell_entry_planner_ok"])),
        "geometry_available_cycle_count": int(
            np.sum(cycle_payload["cell_entry_geometry_available"])
        ),
        "target_cell_match_count": int(
            np.sum(cycle_payload["cell_entry_target_cell_match"])
        ),
        "audit_records": audit_records,
    }
    return {"step": step_payload, "cycle": cycle_payload}, summary


def _computed_step_fields(step_payload: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {
        key: value
        for key, value in step_payload.items()
        if key.startswith("cell_entry_")
        or key.startswith("planned_")
        or key.startswith("current_bucket_dig_area_")
        or key.startswith("entry_delta_")
        or key.startswith("selected_")
    }


def _computed_cycle_fields(
    cycle_payload: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    return {
        key: value
        for key, value in cycle_payload.items()
        if key.startswith("cell_entry_")
        or key.startswith("actual_")
        or key.startswith("selected_")
        or key in {"payload_gain_kg", "deposit_delta_kg", "collision_count_delta"}
    }


def _init_step_payload(n_steps: int) -> dict[str, np.ndarray]:
    int_default = np.full(n_steps, -1, dtype=np.int32)
    float_default = np.full(n_steps, np.nan, dtype=np.float32)
    zero_u8 = np.zeros(n_steps, dtype=np.uint8)
    return {
        "selected_cell_id": int_default.copy(),
        "selected_long_index": int_default.copy(),
        "selected_short_index": int_default.copy(),
        "planned_entry_x_m": float_default.copy(),
        "planned_entry_y_m": float_default.copy(),
        "planned_entry_z_m": float_default.copy(),
        "planned_bite_x_m": float_default.copy(),
        "planned_bite_y_m": float_default.copy(),
        "planned_bite_z_m": float_default.copy(),
        "entry_envelope_x_min_m": float_default.copy(),
        "entry_envelope_x_max_m": float_default.copy(),
        "entry_envelope_y_min_m": float_default.copy(),
        "entry_envelope_y_max_m": float_default.copy(),
        "entry_envelope_z_min_m": float_default.copy(),
        "entry_envelope_z_max_m": float_default.copy(),
        "current_bucket_dig_area_x_m": float_default.copy(),
        "current_bucket_dig_area_y_m": float_default.copy(),
        "current_bucket_dig_area_z_m": float_default.copy(),
        "entry_delta_x_m": float_default.copy(),
        "entry_delta_y_m": float_default.copy(),
        "entry_delta_z_m": float_default.copy(),
        "inside_entry_envelope_mask": zero_u8.copy(),
        "distance_to_entry_envelope_m": float_default.copy(),
        "cell_entry_planner_ok": zero_u8.copy(),
        "cell_entry_audit_risk_flags": np.zeros(n_steps, dtype=np.int32),
        "cell_entry_audit_reason_code": np.zeros(n_steps, dtype=np.int32),
        "cell_entry_tokens": np.zeros(
            (n_steps, CELL_ENTRY_TOKEN_DIM), dtype=np.float32
        ),
    }


def _init_cycle_payload(n_cycles: int) -> dict[str, np.ndarray]:
    return {
        "cycle_id": np.full(n_cycles, -1, dtype=np.int32),
        "start_step": np.full(n_cycles, -1, dtype=np.int32),
        "end_step": np.full(n_cycles, -1, dtype=np.int32),
        "selected_cell_id": np.full(n_cycles, -1, dtype=np.int32),
        "selected_long_index": np.full(n_cycles, -1, dtype=np.int32),
        "selected_short_index": np.full(n_cycles, -1, dtype=np.int32),
        "actual_accepted_start_step": np.full(n_cycles, -1, dtype=np.int32),
        "actual_bite_step": np.full(n_cycles, -1, dtype=np.int32),
        "actual_removal_step": np.full(n_cycles, -1, dtype=np.int32),
        "actual_accepted_start_cell_id": np.full(n_cycles, -1, dtype=np.int32),
        "actual_bite_cell_id": np.full(n_cycles, -1, dtype=np.int32),
        "actual_removal_cell_id": np.full(n_cycles, -1, dtype=np.int32),
        "payload_gain_kg": np.zeros(n_cycles, dtype=np.float32),
        "deposit_delta_kg": np.zeros(n_cycles, dtype=np.float32),
        "collision_count_delta": np.zeros(n_cycles, dtype=np.int32),
        "cell_entry_geometry_available": np.zeros(n_cycles, dtype=np.uint8),
        "cell_entry_planner_ok": np.zeros(n_cycles, dtype=np.uint8),
        "cell_entry_target_cell_match": np.zeros(n_cycles, dtype=np.uint8),
        "cell_entry_audit_risk_flags": np.zeros(n_cycles, dtype=np.int32),
        "cell_entry_audit_reason_code": np.zeros(n_cycles, dtype=np.int32),
    }


def _fill_step_payload(
    *,
    step_payload: dict[str, np.ndarray],
    start: int,
    end: int,
    goal: Any,
    audit: Any,
    token: np.ndarray,
    env_state: np.ndarray,
) -> None:
    sl = slice(int(start), int(end))
    step_payload["selected_cell_id"][sl] = int(goal.selected_cell_id)
    step_payload["selected_long_index"][sl] = int(goal.selected_long_index)
    step_payload["selected_short_index"][sl] = int(goal.selected_short_index)
    for name in (
        "planned_entry_x_m",
        "planned_entry_y_m",
        "planned_entry_z_m",
        "planned_bite_x_m",
        "planned_bite_y_m",
        "planned_bite_z_m",
    ):
        step_payload[name][sl] = float(getattr(goal, name))
    envelope = goal.entry_envelope
    step_payload["entry_envelope_x_min_m"][sl] = float(envelope.x_min_m)
    step_payload["entry_envelope_x_max_m"][sl] = float(envelope.x_max_m)
    step_payload["entry_envelope_y_min_m"][sl] = float(envelope.y_min_m)
    step_payload["entry_envelope_y_max_m"][sl] = float(envelope.y_max_m)
    step_payload["entry_envelope_z_min_m"][sl] = float(envelope.z_min_m)
    step_payload["entry_envelope_z_max_m"][sl] = float(envelope.z_max_m)
    step_payload["cell_entry_planner_ok"][sl] = 1 if audit.planner_ok else 0
    step_payload["cell_entry_audit_risk_flags"][sl] = int(audit.risk_flags)
    step_payload["cell_entry_audit_reason_code"][sl] = int(audit.reason_code)
    step_payload["cell_entry_tokens"][sl] = token.reshape(1, -1)

    for step_index in range(int(start), int(end)):
        pose = _bucket_pose_for_step(env_state, step_index)
        if pose is None:
            continue
        x, y, z = pose
        step_payload["current_bucket_dig_area_x_m"][step_index] = x
        step_payload["current_bucket_dig_area_y_m"][step_index] = y
        step_payload["current_bucket_dig_area_z_m"][step_index] = z
        step_payload["entry_delta_x_m"][step_index] = x - float(goal.planned_entry_x_m)
        step_payload["entry_delta_y_m"][step_index] = y - float(goal.planned_entry_y_m)
        step_payload["entry_delta_z_m"][step_index] = z - float(goal.planned_entry_z_m)
        inside = (
            float(envelope.x_min_m) <= x <= float(envelope.x_max_m)
            and float(envelope.y_min_m) <= y <= float(envelope.y_max_m)
            and float(envelope.z_min_m) <= z <= float(envelope.z_max_m)
        )
        step_payload["inside_entry_envelope_mask"][step_index] = 1 if inside else 0
        dx = max(float(envelope.x_min_m) - x, 0.0, x - float(envelope.x_max_m))
        dy = max(float(envelope.y_min_m) - y, 0.0, y - float(envelope.y_max_m))
        dz = max(float(envelope.z_min_m) - z, 0.0, z - float(envelope.z_max_m))
        step_payload["distance_to_entry_envelope_m"][step_index] = float(
            np.sqrt(dx * dx + dy * dy + dz * dz)
        )


def _fill_cycle_payload(
    *,
    cycle_payload: dict[str, np.ndarray],
    cycle_index: int,
    window: CycleWindow,
    goal: Any,
    outcome: PrimitiveCycleOutcome,
    audit: Any,
) -> None:
    idx = int(cycle_index)
    cycle_payload["cycle_id"][idx] = int(window.cycle_id)
    cycle_payload["start_step"][idx] = int(window.start_step)
    cycle_payload["end_step"][idx] = int(window.end_step_exclusive - 1)
    cycle_payload["selected_cell_id"][idx] = int(goal.selected_cell_id)
    cycle_payload["selected_long_index"][idx] = int(goal.selected_long_index)
    cycle_payload["selected_short_index"][idx] = int(goal.selected_short_index)
    cycle_payload["actual_accepted_start_step"][idx] = int(outcome.actual_start_step)
    cycle_payload["actual_bite_step"][idx] = int(outcome.actual_bite_step)
    cycle_payload["actual_removal_step"][idx] = int(outcome.actual_removal_step)
    cycle_payload["actual_accepted_start_cell_id"][idx] = int(
        outcome.actual_start_cell_id
    )
    cycle_payload["actual_bite_cell_id"][idx] = int(outcome.actual_bite_cell_id)
    cycle_payload["actual_removal_cell_id"][idx] = int(outcome.actual_removal_cell_id)
    cycle_payload["payload_gain_kg"][idx] = float(outcome.payload_gain_kg)
    cycle_payload["deposit_delta_kg"][idx] = float(outcome.deposit_delta_kg)
    cycle_payload["collision_count_delta"][idx] = int(outcome.collision_count_delta)
    cycle_payload["cell_entry_geometry_available"][idx] = (
        1 if outcome.actual_start_cell_id >= 0 else 0
    )
    cycle_payload["cell_entry_planner_ok"][idx] = 1 if audit.planner_ok else 0
    cycle_payload["cell_entry_target_cell_match"][idx] = (
        1 if audit.target_cell_match else 0
    )
    cycle_payload["cell_entry_audit_risk_flags"][idx] = int(audit.risk_flags)
    cycle_payload["cell_entry_audit_reason_code"][idx] = int(audit.reason_code)


def _infer_cycle_windows(
    *,
    n_steps: int,
    v2_step: dict[str, np.ndarray],
    v2_cycle: dict[str, np.ndarray],
) -> list[CycleWindow]:
    if "start_step" in v2_cycle and (
        "end_step" in v2_cycle or "dump_end_step" in v2_cycle
    ):
        starts = np.asarray(v2_cycle["start_step"], dtype=np.int32)
        ends = np.asarray(
            v2_cycle.get("end_step", v2_cycle.get("dump_end_step")), dtype=np.int32
        )
        cycle_ids = np.asarray(
            v2_cycle.get("cycle_id", np.arange(len(starts))), dtype=np.int32
        )
        windows = []
        for idx, start in enumerate(starts):
            if start < 0:
                continue
            end_inclusive = (
                int(ends[idx])
                if idx < len(ends) and ends[idx] >= start
                else n_steps - 1
            )
            windows.append(
                CycleWindow(
                    cycle_id=int(cycle_ids[idx]) if idx < len(cycle_ids) else int(idx),
                    start_step=int(start),
                    end_step_exclusive=min(n_steps, int(end_inclusive) + 1),
                )
            )
        if windows:
            return windows

    if "cycle_id" in v2_step:
        cycle_ids = np.asarray(v2_step["cycle_id"], dtype=np.int32)
        windows = []
        for cycle_id in sorted(
            int(item) for item in np.unique(cycle_ids) if int(item) >= 0
        ):
            indices = np.flatnonzero(cycle_ids == cycle_id)
            if indices.size <= 0:
                continue
            windows.append(
                CycleWindow(
                    cycle_id=int(cycle_id),
                    start_step=int(indices[0]),
                    end_step_exclusive=int(indices[-1]) + 1,
                )
            )
        if windows:
            return windows

    return [CycleWindow(cycle_id=0, start_step=0, end_step_exclusive=int(n_steps))]


def _grid_from_env_or_default(
    env_state: np.ndarray, step: int, default: CellGridSpec
) -> CellGridSpec:
    if env_state.ndim != 2 or step < 0 or step >= len(env_state):
        return default
    row = env_state[step]
    if len(row) <= ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX:
        return default
    long_count = int(round(float(row[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX])))
    short_count = int(round(float(row[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX])))
    long_axis = int(round(float(row[ENV_STATE_DIG_AREA_LONG_AXIS_IDX])))
    if long_count != 3 or short_count != 2 or long_axis not in {0, 2}:
        return default
    return CellGridSpec(
        long_count=long_count,
        short_count=short_count,
        half_long_m=default.half_long_m,
        half_short_m=default.half_short_m,
        long_axis=long_axis,
        entry_margin_m=default.entry_margin_m,
        entry_y_min_m=default.entry_y_min_m,
        entry_y_max_m=default.entry_y_max_m,
    )


def _build_outcome(
    *,
    env_state: np.ndarray,
    v2_step: dict[str, np.ndarray],
    window: CycleWindow,
    previous_window: CycleWindow | None,
) -> PrimitiveCycleOutcome:
    start = int(window.start_step)
    end = int(window.end_step_exclusive)
    qds = _first_mask_step(v2_step, "qualified_dig_start_mask", start, end)
    actual_start = (
        qds if qds is not None else _first_geometry_step(env_state, start, end)
    )
    actual_bite = _first_mass_gain_step(
        env_state, actual_start if actual_start >= 0 else start, end
    )
    actual_removal = actual_bite
    start_cell = _cell_id_at(env_state, actual_start)
    bite_cell = _cell_id_at(env_state, actual_bite)
    removal_cell = _cell_id_at(env_state, actual_removal)

    mass = _env_series(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, start, end)
    payload_gain = float(np.nanmax(mass) - np.nanmin(mass)) if mass.size else 0.0
    deposit = _env_series(
        env_state, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX, start, end
    )
    deposit_delta = float(deposit[-1] - deposit[0]) if deposit.size else 0.0
    collision = _env_series(
        env_state, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX, start, end
    )
    collision_delta = (
        int(round(float(collision[-1] - collision[0]))) if collision.size else 0
    )
    return_miss = bool(previous_window is not None and actual_start < 0)
    return PrimitiveCycleOutcome(
        cycle_id=int(window.cycle_id),
        actual_start_step=int(actual_start),
        actual_bite_step=int(actual_bite),
        actual_removal_step=int(actual_removal),
        actual_start_cell_id=int(start_cell),
        actual_bite_cell_id=int(bite_cell),
        actual_removal_cell_id=int(removal_cell),
        payload_gain_kg=float(max(0.0, payload_gain)),
        deposit_delta_kg=float(max(0.0, deposit_delta)),
        collision_count_delta=int(max(0, collision_delta)),
        return_miss=return_miss,
    )


def _first_mask_step(
    v2_step: dict[str, np.ndarray],
    name: str,
    start: int,
    end: int,
) -> int | None:
    if name not in v2_step:
        return None
    mask = np.asarray(v2_step[name]).reshape(-1)
    for step in range(start, min(end, len(mask))):
        if bool(mask[step]):
            return int(step)
    return None


def _first_geometry_step(env_state: np.ndarray, start: int, end: int) -> int:
    for step in range(start, end):
        if _cell_geometry_available(env_state, step):
            return int(step)
    return -1


def _first_mass_gain_step(env_state: np.ndarray, start: int, end: int) -> int:
    if start < 0:
        start = max(0, int(start))
    if env_state.ndim != 2 or len(env_state) <= start:
        return -1
    prev = float(env_state[start, ENV_STATE_MASS_IN_BUCKET_IDX])
    for step in range(start + 1, min(end, len(env_state))):
        curr = float(env_state[step, ENV_STATE_MASS_IN_BUCKET_IDX])
        if curr > prev + 5.0:
            return int(step)
        prev = curr
    return int(start) if start < end else -1


def _env_series(env_state: np.ndarray, index: int, start: int, end: int) -> np.ndarray:
    if env_state.ndim != 2 or env_state.shape[1] <= index or start >= end:
        return np.zeros(0, dtype=np.float32)
    return np.asarray(env_state[start:end, index], dtype=np.float32)


def _cell_geometry_available(env_state: np.ndarray, step: int) -> bool:
    if env_state.ndim != 2 or step < 0 or step >= len(env_state):
        return False
    row = env_state[step]
    if len(row) <= ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
        return False
    return bool(
        float(row[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX]) > 0.5
        and int(round(float(row[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX]))) >= 0
    )


def _cell_id_at(env_state: np.ndarray, step: int) -> int:
    if not _cell_geometry_available(env_state, step):
        return -1
    return int(round(float(env_state[step, ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX])))


def _bucket_pose_for_step(
    env_state: np.ndarray, step: int
) -> tuple[float, float, float] | None:
    if env_state.ndim != 2 or step < 0 or step >= len(env_state):
        return None
    row = env_state[step]
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


def _build_dataset_summary(
    *,
    dataset_dir: Path,
    output_dir: Path,
    grid: CellGridSpec,
    episode_summaries: list[dict[str, Any]],
    storage_mode: str,
) -> dict[str, Any]:
    cycle_count = sum(int(item.get("cycle_count", 0)) for item in episode_summaries)
    planner_ok = sum(int(item.get("planner_ok_count", 0)) for item in episode_summaries)
    geometry = sum(
        int(item.get("geometry_available_cycle_count", 0)) for item in episode_summaries
    )
    matches = sum(
        int(item.get("target_cell_match_count", 0)) for item in episode_summaries
    )
    denom = max(cycle_count, 1)
    return {
        "version": CELL_ENTRY_VERSION,
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "storage_mode": str(storage_mode),
        "grid": asdict(grid),
        "episode_count": int(len(episode_summaries)),
        "cycle_count": int(cycle_count),
        "planner_ok_rate": float(planner_ok) / float(denom),
        "geometry_available_cycle_rate": float(geometry) / float(denom),
        "target_cell_match_rate": float(matches) / float(denom),
        "episodes": episode_summaries,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value
