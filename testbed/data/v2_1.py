"""Stage-1 V2.1 helpers for multicycle `/v2` labeling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ATTR_GOAL_TOKEN_DIM,
    ATTR_GOAL_TOKEN_VERSION,
    ATTR_PHASE_VERSION,
    ATTR_SCENARIO_ID,
    ATTR_SCENARIO_MANIFEST_VERSION,
    ATTR_TRANSITION_SOURCE,
    ATTR_V2_ENABLED,
    ATTR_WORK_STAGE_VERSION,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
)
from testbed.planner.boundary_detector import (
    MODE_TRANSITION,
    MODE_WORK,
    BoundaryDetector,
    build_boundary_detector_from_config,
)


GOAL_TOKEN_DIM = 10
GOAL_TOKEN_VERSION = "v2_1c_sector10d_digarea13"
PHASE_VERSION = "v2_1_mode_phase_7cls"
WORK_STAGE_VERSION = "v2_1_work_stage_7cls"
SCENARIO_MANIFEST_VERSION = "v2_1b"
TRANSITION_SOURCE_NONE = "none"
PLAN_SOURCE_NONE = "none"
TERMINAL_STOP_REASON = "target_dump_count_reached"

SECTOR_DIG_AREA_LEFT_SWING = 0.43
SECTOR_DIG_AREA_CENTER_SWING = 0.50
SECTOR_DIG_AREA_RIGHT_SWING = 0.56
SECTOR_DIG_AREA_WIDTH = SECTOR_DIG_AREA_RIGHT_SWING - SECTOR_DIG_AREA_LEFT_SWING
SECTOR_LEFT_MAX_SWING = SECTOR_DIG_AREA_LEFT_SWING + SECTOR_DIG_AREA_WIDTH / 3.0
SECTOR_MID_MAX_SWING = SECTOR_DIG_AREA_LEFT_SWING + 2.0 * SECTOR_DIG_AREA_WIDTH / 3.0

PHASE_NAMES = (
    "dig_contact",
    "cut_fill",
    "lift_clear",
    "transport",
    "dump",
    "transition_corridor",
    "transition_wait_next_dig",
)
PHASE_NAME_TO_ID = {name: index for index, name in enumerate(PHASE_NAMES)}

WORK_STAGE_NAMES = (
    "none",
    "entry_to_bite",
    "first_bite",
    "rebite_recovery",
    "carry",
    "approach_dump",
    "dump",
)
WORK_STAGE_NAME_TO_ID = {name: index for index, name in enumerate(WORK_STAGE_NAMES)}

FIRST_BITE_ENTRY_STEPS = 12
FIRST_BITE_ENTRY_MIN_STEPS = 2
FIRST_BITE_EARLY_WINDOW_STEPS = 80
FIRST_BITE_ENTRY_SIGNAL_MASS_KG = 60.0
FIRST_BITE_ENTRY_SIGNAL_DEPTH_M = 0.24
FIRST_BITE_LOAD_READY_MASS_KG = 250.0
FIRST_BITE_FAILURE_PEAK_MASS_KG = 120.0
FIRST_BITE_FAILURE_RETURN_MASS_KG = 20.0
APPROACH_DUMP_TARGET_DISTANCE_M = 1.15
APPROACH_DUMP_MIN_MASS_KG = 150.0


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    dst_target_id: int
    dst_target_norm: float
    active_target_index: int
    reset_terrain: bool
    reset_pose: bool
    default_curr_sector_id: int = 1
    default_curr_cut_depth_class: int = 1
    default_curr_cut_depth_norm: float = 0.5
    default_next_sector_id: int = -1
    default_next_cut_depth_class: int = -1
    default_next_cut_depth_norm: float = 0.0
    default_has_lookahead: float = 0.0


_SCENARIO_SPECS: dict[str, ScenarioSpec] = {
    "s0_baseline": ScenarioSpec(
        scenario_id="s0_baseline",
        dst_target_id=0,
        dst_target_norm=0.0,
        active_target_index=0,
        reset_terrain=True,
        reset_pose=True,
    ),
    "s0_truck": ScenarioSpec(
        scenario_id="s0_truck",
        dst_target_id=1,
        dst_target_norm=1.0,
        active_target_index=1,
        reset_terrain=True,
        reset_pose=True,
    ),
    "s1_pose_jitter": ScenarioSpec(
        scenario_id="s1_pose_jitter",
        dst_target_id=0,
        dst_target_norm=0.0,
        active_target_index=0,
        reset_terrain=True,
        reset_pose=True,
    ),
}


def resolve_scenario_spec(scenario_id: str) -> ScenarioSpec:
    try:
        return _SCENARIO_SPECS[str(scenario_id)]
    except KeyError as exc:
        raise KeyError(
            f"Unknown scenario_id {scenario_id!r}. Available: {sorted(_SCENARIO_SPECS)}."
        ) from exc


def build_v2_1_metadata_attrs(*, scenario_id: str) -> dict[str, Any]:
    return {
        ATTR_SCENARIO_ID: str(scenario_id),
        ATTR_GOAL_TOKEN_DIM: int(GOAL_TOKEN_DIM),
        ATTR_GOAL_TOKEN_VERSION: GOAL_TOKEN_VERSION,
        ATTR_PHASE_VERSION: PHASE_VERSION,
        ATTR_WORK_STAGE_VERSION: WORK_STAGE_VERSION,
        ATTR_SCENARIO_MANIFEST_VERSION: SCENARIO_MANIFEST_VERSION,
    }


def build_goal_tokens(
    scenario_id: str,
    *,
    curr_sector_id: int | None = None,
    curr_cut_depth_norm: float | None = None,
    next_sector_id: int | None = None,
    next_cut_depth_norm: float | None = None,
    dst_target_norm: float | None = None,
    has_lookahead: float | bool | None = None,
) -> np.ndarray:
    spec = resolve_scenario_spec(scenario_id)
    curr_sector_id = spec.default_curr_sector_id if curr_sector_id is None else int(curr_sector_id)
    curr_cut_depth_norm = (
        spec.default_curr_cut_depth_norm
        if curr_cut_depth_norm is None
        else float(curr_cut_depth_norm)
    )
    next_sector_id = spec.default_next_sector_id if next_sector_id is None else int(next_sector_id)
    next_cut_depth_norm = (
        spec.default_next_cut_depth_norm
        if next_cut_depth_norm is None
        else float(next_cut_depth_norm)
    )
    dst_target_norm = spec.dst_target_norm if dst_target_norm is None else float(dst_target_norm)
    has_lookahead = (
        spec.default_has_lookahead if has_lookahead is None else float(bool(has_lookahead))
    )

    goal = np.zeros(GOAL_TOKEN_DIM, dtype=np.float32)
    if 0 <= curr_sector_id <= 2:
        goal[curr_sector_id] = 1.0
    goal[3] = _clip01(curr_cut_depth_norm)
    if 0 <= next_sector_id <= 2:
        goal[4 + next_sector_id] = 1.0
    goal[7] = _clip01(next_cut_depth_norm)
    goal[8] = _clip01(dst_target_norm)
    goal[9] = 1.0 if float(has_lookahead) > 0.0 else 0.0
    return goal


def swing_to_sector_id(swing_position_norm: float) -> int:
    swing = float(np.clip(swing_position_norm, 0.0, 1.0))
    if swing < SECTOR_LEFT_MAX_SWING:
        return 0
    if swing < SECTOR_MID_MAX_SWING:
        return 1
    return 2


def peak_bucket_depth_to_depth_class(depth_m: float) -> int:
    depth = max(0.0, float(depth_m))
    if depth < 0.04:
        return 0
    if depth < 0.08:
        return 1
    return 2


def peak_bucket_depth_to_depth_norm(depth_m: float) -> float:
    return _clip01(float(depth_m) / 0.12)


def label_episode_v2_1(
    *,
    qpos: np.ndarray,
    actions: np.ndarray,
    env_state: np.ndarray,
    metadata: dict[str, Any] | None = None,
    scenario_id: str,
    pause_action_eps: float = 0.05,
    reward_cfg: dict[str, Any] | None = None,
    success_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    qpos_arr = np.asarray(qpos, dtype=np.float32)
    actions_arr = np.asarray(actions, dtype=np.float32)
    env_state_arr = np.asarray(env_state, dtype=np.float32)
    metadata_dict = dict(metadata or {})

    if qpos_arr.ndim != 2 or actions_arr.ndim != 2 or env_state_arr.ndim != 2:
        raise ValueError("label_episode_v2_1 expects rank-2 qpos/actions/env_state arrays.")
    if not (len(qpos_arr) == len(actions_arr) == len(env_state_arr)):
        raise ValueError("qpos/actions/env_state must share the same timestep length.")
    if env_state_arr.shape[1] <= ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX:
        raise ValueError(
            "env_state must contain the AGX indices through bucket_depth_below_dig_area_plane_m."
        )

    spec = resolve_scenario_spec(scenario_id)
    detector = build_boundary_detector_from_config(
        reward_cfg=reward_cfg,
        success_cfg=success_cfg,
        pause_action_eps=pause_action_eps,
    )

    n_steps = len(actions_arr)
    step_cycle_id = np.full(n_steps, -1, dtype=np.int32)
    mode_id = np.full(n_steps, MODE_TRANSITION, dtype=np.uint8)
    phase_id = np.full(n_steps, PHASE_NAME_TO_ID["transition_wait_next_dig"], dtype=np.uint8)
    phase_progress = np.zeros(n_steps, dtype=np.float32)
    work_stage_id = np.full(n_steps, WORK_STAGE_NAME_TO_ID["none"], dtype=np.uint8)
    planner_replan_mask = np.zeros(n_steps, dtype=np.uint8)
    qualified_dig_start_mask = np.zeros(n_steps, dtype=np.uint8)
    dump_start_mask = np.zeros(n_steps, dtype=np.uint8)
    dump_end_mask = np.zeros(n_steps, dtype=np.uint8)
    pause_mask = np.zeros(n_steps, dtype=np.uint8)

    events = []
    for step_index in range(n_steps):
        event = detector.update(
            env_state=env_state_arr[step_index],
            action=actions_arr[step_index],
            qpos=qpos_arr[step_index],
        )
        events.append(event)
        step_cycle_id[step_index] = int(event.cycle_id)
        mode_id[step_index] = np.uint8(event.mode_id)
        qualified_dig_start_mask[step_index] = np.uint8(event.qualified_dig_start)
        dump_start_mask[step_index] = np.uint8(event.dump_start)
        dump_end_mask[step_index] = np.uint8(event.dump_end)
        pause_mask[step_index] = np.uint8(event.pause)

    cycle_starts = np.flatnonzero(qualified_dig_start_mask.astype(bool))
    cycle_payload: dict[str, list[Any]] = {
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
        "cycle_success": [],
        "plan_source": [],
    }
    goal_tokens_by_cycle: dict[int, np.ndarray] = {}
    boundary_mask = np.zeros(n_steps, dtype=np.uint8)
    stop_reason = str(metadata_dict.get("stop_reason", "")).strip()
    legacy_terminal_success = bool(metadata_dict.get("success", False))
    completed_dump_count = _metadata_int(metadata_dict.get("completed_dump_count"), default=0)
    target_dump_count = _metadata_int(metadata_dict.get("target_dump_count"), default=0)
    terminal_target_reached = (
        stop_reason == TERMINAL_STOP_REASON
        and completed_dump_count > 0
        and (target_dump_count <= 0 or completed_dump_count >= target_dump_count)
    )

    mass_in_bucket = env_state_arr[:, ENV_STATE_MASS_IN_BUCKET_IDX]
    deposited_mass = env_state_arr[:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX]
    bucket_depth = env_state_arr[:, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
    hard_collision_count = env_state_arr[:, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX]

    for cycle_index, start_step in enumerate(cycle_starts.tolist()):
        next_start_step = (
            int(cycle_starts[cycle_index + 1])
            if cycle_index + 1 < len(cycle_starts)
            else None
        )
        dump_end_candidates = np.flatnonzero(dump_end_mask[start_step:].astype(bool))
        dump_end_step = (
            start_step + int(dump_end_candidates[0])
            if len(dump_end_candidates) > 0
            and (next_start_step is None or start_step + int(dump_end_candidates[0]) < next_start_step)
            else -1
        )

        if (
            dump_end_step < 0
            and next_start_step is None
            and cycle_index == len(cycle_starts) - 1
            and n_steps > start_step
            and (
                legacy_terminal_success
                or (terminal_target_reached and completed_dump_count >= cycle_index + 1)
            )
        ):
            terminal_step = n_steps - 1
            if (
                terminal_target_reached
                or float(deposited_mass[terminal_step] - deposited_mass[start_step]) > 0.0
            ):
                dump_end_step = int(terminal_step)
                dump_end_mask[terminal_step] = np.uint8(1)

        if next_start_step is not None:
            end_step = int(next_start_step)
        elif dump_end_step >= 0 and (
            stop_reason == TERMINAL_STOP_REASON or legacy_terminal_success
        ):
            end_step = int(dump_end_step)
        else:
            end_step = -1

        if end_step >= 0:
            boundary_mask[max(0, end_step - 1) : min(n_steps, end_step + 2)] = 1

        cycle_slice_end = (
            dump_end_step + 1
            if dump_end_step >= 0
            else (next_start_step if next_start_step is not None else n_steps)
        )
        window = slice(start_step, max(start_step + 1, cycle_slice_end))
        transition_end = next_start_step if next_start_step is not None else end_step

        curr_sector_id = swing_to_sector_id(float(qpos_arr[start_step, 0]))
        peak_bucket_depth_m = float(np.max(bucket_depth[window]))
        curr_cut_depth_class = peak_bucket_depth_to_depth_class(peak_bucket_depth_m)
        curr_cut_depth_norm = peak_bucket_depth_to_depth_norm(peak_bucket_depth_m)

        if next_start_step is not None:
            next_sector_id = swing_to_sector_id(float(qpos_arr[next_start_step, 0]))
            next_peak_depth = float(
                np.max(
                    bucket_depth[
                        next_start_step : min(n_steps, next_start_step + max(1, cycle_slice_end - start_step))
                    ]
                )
            )
            next_cut_depth_class = peak_bucket_depth_to_depth_class(next_peak_depth)
            next_cut_depth_norm = peak_bucket_depth_to_depth_norm(next_peak_depth)
            has_lookahead = 1.0
        else:
            next_sector_id = -1
            next_cut_depth_class = -1
            next_cut_depth_norm = 0.0
            has_lookahead = 0.0

        goal_tokens_by_cycle[cycle_index] = build_goal_tokens(
            scenario_id,
            curr_sector_id=curr_sector_id,
            curr_cut_depth_norm=curr_cut_depth_norm,
            next_sector_id=next_sector_id,
            next_cut_depth_norm=next_cut_depth_norm,
            dst_target_norm=spec.dst_target_norm,
            has_lookahead=has_lookahead,
        )

        fill_peak_kg = float(np.max(mass_in_bucket[window]))
        terminal_index = dump_end_step if dump_end_step >= 0 else (cycle_slice_end - 1)
        deposit_delta_kg = float(
            deposited_mass[terminal_index] - deposited_mass[start_step]
        )
        collision_count_delta = int(
            round(hard_collision_count[terminal_index] - hard_collision_count[start_step])
        )
        cycle_success = int(
            dump_end_step >= 0 and end_step >= 0 and deposit_delta_kg > 0.0
        )

        cycle_payload["cycle_id"].append(int(cycle_index))
        cycle_payload["start_step"].append(int(start_step))
        cycle_payload["dump_end_step"].append(int(dump_end_step))
        cycle_payload["end_step"].append(int(end_step))
        cycle_payload["curr_src_sector_id"].append(int(curr_sector_id))
        cycle_payload["curr_cut_depth_class"].append(int(curr_cut_depth_class))
        cycle_payload["next_src_sector_id"].append(int(next_sector_id))
        cycle_payload["next_cut_depth_class"].append(int(next_cut_depth_class))
        cycle_payload["dst_target_id"].append(int(spec.dst_target_id))
        cycle_payload["fill_peak_kg"].append(float(fill_peak_kg))
        cycle_payload["deposit_delta_kg"].append(float(deposit_delta_kg))
        cycle_payload["peak_bucket_depth_m"].append(float(peak_bucket_depth_m))
        cycle_payload["collision_count_delta"].append(int(collision_count_delta))
        cycle_payload["transition_source"].append(TRANSITION_SOURCE_NONE)
        cycle_payload["cycle_success"].append(int(cycle_success))
        cycle_payload["plan_source"].append(PLAN_SOURCE_NONE)

        _fill_cycle_phase_labels(
            phase_id=phase_id,
            mode_id=mode_id,
            dump_start_mask=dump_start_mask,
            dump_end_step=dump_end_step,
            start_step=start_step,
            next_start_step=next_start_step,
            bucket_depth=bucket_depth,
            mass_in_bucket=mass_in_bucket,
            env_state=env_state_arr,
        )
        _fill_cycle_work_stage_labels(
            work_stage_id=work_stage_id,
            start_step=start_step,
            dump_end_step=dump_end_step,
            next_start_step=next_start_step,
            dump_start_mask=dump_start_mask,
            bucket_depth=bucket_depth,
            mass_in_bucket=mass_in_bucket,
            env_state=env_state_arr,
        )

        if dump_end_step >= 0 and next_start_step is not None:
            _fill_transition_phase_labels(
                phase_id=phase_id,
                mode_id=mode_id,
                start_step=dump_end_step + 1,
                end_step=next_start_step,
            )

    goal_tokens = np.zeros((n_steps, GOAL_TOKEN_DIM), dtype=np.float32)
    for step_index in range(n_steps):
        cycle_id = int(step_cycle_id[step_index])
        if cycle_id < 0 or cycle_id not in goal_tokens_by_cycle:
            goal_tokens[step_index] = build_goal_tokens(scenario_id)
        else:
            goal_tokens[step_index] = goal_tokens_by_cycle[cycle_id]

    _fill_phase_progress(phase_id=phase_id, phase_progress=phase_progress)

    v2_payload = {
        "step": {
            "cycle_id": step_cycle_id,
            "mode_id": mode_id,
            "phase_id": phase_id,
            "phase_progress": phase_progress,
            "work_stage_id": work_stage_id,
            "goal_tokens": goal_tokens,
            "planner_replan_mask": planner_replan_mask,
            "qualified_dig_start_mask": qualified_dig_start_mask,
            "dump_start_mask": dump_start_mask,
            "dump_end_mask": dump_end_mask,
            "boundary_mask": boundary_mask,
            "pause_mask": pause_mask,
        },
        "cycle": {
            "cycle_id": np.asarray(cycle_payload["cycle_id"], dtype=np.int32),
            "start_step": np.asarray(cycle_payload["start_step"], dtype=np.int32),
            "dump_end_step": np.asarray(cycle_payload["dump_end_step"], dtype=np.int32),
            "end_step": np.asarray(cycle_payload["end_step"], dtype=np.int32),
            "curr_src_sector_id": np.asarray(
                cycle_payload["curr_src_sector_id"], dtype=np.int32
            ),
            "curr_cut_depth_class": np.asarray(
                cycle_payload["curr_cut_depth_class"], dtype=np.int32
            ),
            "next_src_sector_id": np.asarray(
                cycle_payload["next_src_sector_id"], dtype=np.int32
            ),
            "next_cut_depth_class": np.asarray(
                cycle_payload["next_cut_depth_class"], dtype=np.int32
            ),
            "dst_target_id": np.asarray(cycle_payload["dst_target_id"], dtype=np.int32),
            "fill_peak_kg": np.asarray(cycle_payload["fill_peak_kg"], dtype=np.float32),
            "deposit_delta_kg": np.asarray(
                cycle_payload["deposit_delta_kg"], dtype=np.float32
            ),
            "peak_bucket_depth_m": np.asarray(
                cycle_payload["peak_bucket_depth_m"], dtype=np.float32
            ),
            "collision_count_delta": np.asarray(
                cycle_payload["collision_count_delta"], dtype=np.int32
            ),
            "transition_source": np.asarray(
                cycle_payload["transition_source"], dtype="<U16"
            ),
            "cycle_success": np.asarray(cycle_payload["cycle_success"], dtype=np.uint8),
            "plan_source": np.asarray(cycle_payload["plan_source"], dtype="<U16"),
        },
    }

    metadata_updates = build_v2_1_metadata_attrs(scenario_id=scenario_id)
    metadata_updates.update(
        {
            ATTR_V2_ENABLED: True,
            ATTR_TRANSITION_SOURCE: TRANSITION_SOURCE_NONE,
        }
    )
    return v2_payload, metadata_updates


def _fill_cycle_phase_labels(
    *,
    phase_id: np.ndarray,
    mode_id: np.ndarray,
    dump_start_mask: np.ndarray,
    dump_end_step: int,
    start_step: int,
    next_start_step: int | None,
    bucket_depth: np.ndarray,
    mass_in_bucket: np.ndarray,
    env_state: np.ndarray,
) -> None:
    if dump_end_step >= 0:
        work_end_exclusive = dump_end_step + 1
    elif next_start_step is not None:
        work_end_exclusive = next_start_step
    else:
        work_end_exclusive = len(phase_id)

    for step_index in range(start_step, work_end_exclusive):
        mode_id[step_index] = MODE_WORK
        if dump_start_mask[step_index]:
            phase_id[step_index] = PHASE_NAME_TO_ID["dump"]
            continue
        if dump_end_step >= 0 and step_index > start_step and np.any(dump_start_mask[start_step:step_index]):
            phase_id[step_index] = PHASE_NAME_TO_ID["dump"]
            continue

        depth = float(bucket_depth[step_index])
        bucket_mass = float(mass_in_bucket[step_index])
        min_distance_to_target = float(env_state[step_index, 4]) if env_state.shape[1] > 4 else 0.0
        min_distance_to_dig_area = float(env_state[step_index, 7]) if env_state.shape[1] > 7 else 0.0

        if depth >= 0.02 and bucket_mass < 100.0:
            phase_id[step_index] = PHASE_NAME_TO_ID["dig_contact"]
        elif depth >= 0.02:
            phase_id[step_index] = PHASE_NAME_TO_ID["cut_fill"]
        elif bucket_mass >= 100.0 and min_distance_to_dig_area > 0.05 and min_distance_to_target > 1.25:
            phase_id[step_index] = PHASE_NAME_TO_ID["lift_clear"]
        elif bucket_mass >= 100.0:
            phase_id[step_index] = PHASE_NAME_TO_ID["transport"]
        else:
            phase_id[step_index] = PHASE_NAME_TO_ID["dig_contact"]


def _fill_cycle_work_stage_labels(
    *,
    work_stage_id: np.ndarray,
    start_step: int,
    dump_end_step: int,
    next_start_step: int | None,
    dump_start_mask: np.ndarray,
    bucket_depth: np.ndarray,
    mass_in_bucket: np.ndarray,
    env_state: np.ndarray,
) -> None:
    if dump_end_step >= 0:
        work_end_exclusive = dump_end_step + 1
    elif next_start_step is not None:
        work_end_exclusive = next_start_step
    else:
        work_end_exclusive = len(work_stage_id)
    if start_step >= work_end_exclusive:
        return

    dump_start_idx = _find_first_mask_index(
        mask=dump_start_mask,
        start_step=start_step,
        end_step_exclusive=work_end_exclusive,
    )
    pre_dump_end = dump_start_idx if dump_start_idx is not None else work_end_exclusive

    if dump_start_idx is not None:
        work_stage_id[dump_start_idx:work_end_exclusive] = WORK_STAGE_NAME_TO_ID["dump"]

    approach_start_idx = _find_approach_dump_start(
        env_state=env_state,
        mass_in_bucket=mass_in_bucket,
        start_step=start_step,
        end_step_exclusive=pre_dump_end,
    )
    approach_end = pre_dump_end
    if approach_start_idx is not None and approach_start_idx < approach_end:
        work_stage_id[approach_start_idx:approach_end] = WORK_STAGE_NAME_TO_ID["approach_dump"]
    else:
        approach_start_idx = approach_end

    bite_window_end = min(approach_start_idx, start_step + FIRST_BITE_EARLY_WINDOW_STEPS)
    load_ready_idx = _find_load_ready_step(
        mass_in_bucket=mass_in_bucket,
        start_step=start_step,
        end_step_exclusive=approach_start_idx,
    )
    first_bite_scan_end = (
        load_ready_idx
        if load_ready_idx is not None and load_ready_idx > start_step + 1
        else bite_window_end
    )
    first_bite_return_idx = _find_first_bite_return_step(
        mass_in_bucket=mass_in_bucket,
        start_step=start_step,
        end_step_exclusive=first_bite_scan_end,
    )
    rebite_start_idx = None
    if (
        first_bite_return_idx is not None
        and load_ready_idx is not None
        and load_ready_idx > first_bite_return_idx + 1
    ):
        rebite_start_idx = int(first_bite_return_idx + 1)

    entry_signal_idx = _find_entry_signal_step(
        mass_in_bucket=mass_in_bucket,
        bucket_depth=bucket_depth,
        start_step=start_step,
        end_step_exclusive=min(approach_start_idx, bite_window_end),
    )
    if entry_signal_idx is None:
        entry_end = min(approach_start_idx, start_step + FIRST_BITE_ENTRY_STEPS)
    else:
        entry_end = min(
            approach_start_idx,
            max(start_step + FIRST_BITE_ENTRY_MIN_STEPS, entry_signal_idx),
        )
    if entry_end > start_step:
        work_stage_id[start_step:entry_end] = WORK_STAGE_NAME_TO_ID["entry_to_bite"]

    if first_bite_return_idx is not None:
        first_bite_end = max(entry_end, min(first_bite_return_idx + 1, approach_start_idx))
    elif load_ready_idx is not None:
        first_bite_end = max(entry_end, min(load_ready_idx, approach_start_idx))
    else:
        first_bite_end = max(entry_end, min(bite_window_end, approach_start_idx))

    if first_bite_end > entry_end:
        work_stage_id[entry_end:first_bite_end] = WORK_STAGE_NAME_TO_ID["first_bite"]

    carry_start_idx = None
    if rebite_start_idx is not None:
        rebite_end = load_ready_idx if load_ready_idx is not None and load_ready_idx > rebite_start_idx else approach_start_idx
        rebite_end = min(rebite_end, approach_start_idx)
        if rebite_end > first_bite_end:
            work_stage_id[first_bite_end:rebite_end] = WORK_STAGE_NAME_TO_ID["rebite_recovery"]
        carry_start_idx = rebite_end
    elif load_ready_idx is not None:
        carry_start_idx = max(load_ready_idx, first_bite_end)
    else:
        carry_start_idx = first_bite_end

    carry_start_idx = min(max(carry_start_idx, first_bite_end), approach_start_idx)
    if approach_start_idx > carry_start_idx:
        work_stage_id[carry_start_idx:approach_start_idx] = WORK_STAGE_NAME_TO_ID["carry"]


def _fill_transition_phase_labels(
    *,
    phase_id: np.ndarray,
    mode_id: np.ndarray,
    start_step: int,
    end_step: int,
) -> None:
    if start_step >= end_step:
        return
    transition_len = end_step - start_step
    split = start_step + max(1, transition_len // 2)
    for step_index in range(start_step, end_step):
        mode_id[step_index] = MODE_TRANSITION
        phase_id[step_index] = (
            PHASE_NAME_TO_ID["transition_corridor"]
            if step_index < split
            else PHASE_NAME_TO_ID["transition_wait_next_dig"]
        )


def _fill_phase_progress(*, phase_id: np.ndarray, phase_progress: np.ndarray) -> None:
    if len(phase_id) == 0:
        return
    span_start = 0
    for step_index in range(1, len(phase_id) + 1):
        if step_index < len(phase_id) and phase_id[step_index] == phase_id[span_start]:
            continue
        span_len = max(1, step_index - span_start)
        if span_len == 1:
            phase_progress[span_start] = 1.0
        else:
            phase_progress[span_start:step_index] = np.linspace(
                0.0,
                1.0,
                num=span_len,
                endpoint=True,
                dtype=np.float32,
            )
        span_start = step_index


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _metadata_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _find_first_mask_index(
    *,
    mask: np.ndarray,
    start_step: int,
    end_step_exclusive: int,
) -> int | None:
    for step_index in range(start_step, end_step_exclusive):
        if bool(mask[step_index]):
            return int(step_index)
    return None


def _find_load_ready_step(
    *,
    mass_in_bucket: np.ndarray,
    start_step: int,
    end_step_exclusive: int,
) -> int | None:
    for step_index in range(start_step, end_step_exclusive):
        if float(mass_in_bucket[step_index]) >= FIRST_BITE_LOAD_READY_MASS_KG:
            return int(step_index)
    return None


def _find_entry_signal_step(
    *,
    mass_in_bucket: np.ndarray,
    bucket_depth: np.ndarray,
    start_step: int,
    end_step_exclusive: int,
) -> int | None:
    for step_index in range(start_step, end_step_exclusive):
        if (
            float(mass_in_bucket[step_index]) >= FIRST_BITE_ENTRY_SIGNAL_MASS_KG
            or float(bucket_depth[step_index]) >= FIRST_BITE_ENTRY_SIGNAL_DEPTH_M
        ):
            return int(step_index)
    return None


def _find_first_bite_return_step(
    *,
    mass_in_bucket: np.ndarray,
    start_step: int,
    end_step_exclusive: int,
) -> int | None:
    if end_step_exclusive - start_step <= 1:
        return None
    window = np.asarray(mass_in_bucket[start_step:end_step_exclusive], dtype=np.float32)
    if window.size <= 1:
        return None
    peak_idx = int(np.argmax(window))
    peak_mass = float(window[peak_idx])
    if peak_mass < FIRST_BITE_FAILURE_PEAK_MASS_KG or peak_idx + 1 >= window.size:
        return None
    post_peak = window[peak_idx + 1 :]
    returned = np.flatnonzero(post_peak <= FIRST_BITE_FAILURE_RETURN_MASS_KG)
    if returned.size <= 0:
        return None
    return int(start_step + peak_idx + 1 + int(returned[0]))


def _find_approach_dump_start(
    *,
    env_state: np.ndarray,
    mass_in_bucket: np.ndarray,
    start_step: int,
    end_step_exclusive: int,
) -> int | None:
    if env_state.ndim != 2 or end_step_exclusive <= start_step:
        return None
    for step_index in range(start_step, end_step_exclusive):
        target_distance = float(env_state[step_index, ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX])
        bucket_mass = float(mass_in_bucket[step_index])
        if (
            bucket_mass >= APPROACH_DUMP_MIN_MASS_KG
            and target_distance <= APPROACH_DUMP_TARGET_DISTANCE_M
        ):
            return int(step_index)
    return None
