"""Leakage-safe silver effect samples derived from expert replay cycles.

The executed-cut contract intentionally describes what the expert actually did.
It is separate from the planned-cut contract used to calibrate a frozen ACT.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DIG_AREA_BASELINE_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_UNIT_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_REFERENCE_PLANE_LOCAL_Y_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SHORT_AXIS_UNIT_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
    ENV_STATE_V2_3_DIM,
)
from testbed.data.v2_1 import WORK_STAGE_NAME_TO_ID
from testbed.eval.terrain_grid_volume import compute_grid_volume_change

EffectInputContract = Literal["executed_cut", "planned_cut"]
EFFECT_INPUT_SCHEMA = "terrain_effect_input_v1"
SAMPLE_SCHEMA = "executed_cut_silver_sample_v1"
SAMPLE_SET_SCHEMA = "executed_cut_silver_sample_set_v1"
EVIDENCE_TIER = "replay_derived_silver"
GRID_CELL_COUNT = 6
JOINT_STATE_DIM = 4


class LabelLeakageError(ValueError):
    """Raised when a post-execution fact appears in a planned model input."""


@dataclass(frozen=True)
class StableTerrainWindowConfig:
    """Reviewed stability contract for replay-derived pre/post snapshots."""

    window_steps: int = 10
    min_surface_valid_fraction: float = 8.0 / 9.0
    max_removed_depth_range_m: float = 0.002
    post_search_steps: int = 150
    geometry_atol: float = 1.0e-6

    def __post_init__(self) -> None:
        if self.window_steps <= 0:
            raise ValueError("window_steps must be positive.")
        if not 0.0 <= self.min_surface_valid_fraction <= 1.0:
            raise ValueError("min_surface_valid_fraction must be in [0, 1].")
        if self.max_removed_depth_range_m < 0.0:
            raise ValueError("max_removed_depth_range_m must be non-negative.")
        if self.post_search_steps < 0:
            raise ValueError("post_search_steps must be non-negative.")


_PLANNED_FORBIDDEN_KEYS = frozenset(
    {
        "actual_peak_depth_m",
        "actual_surface_penetration_peak_m",
        "actual_removed_depth_delta_grid",
        "actual_removed_depth_delta_grid_m",
        "payload_gain_kg",
        "effective_deposit_delta_kg",
        "post_terrain",
        "executed_cut",
        "dig_outcome_targets",
        "outcome",
    }
)

_TERRAIN_VECTOR_FIELDS: tuple[tuple[str, int], ...] = (
    ("surface_depth_m", 6),
    ("removed_depth_m", 6),
    ("valid_mask", 6),
    ("surface_valid_fraction", 6),
    ("baseline_depth_m", 6),
    ("grid_origin_world_m", 3),
    ("long_axis_unit_world", 3),
    ("short_axis_unit_world", 3),
    ("cell_long_size_m", 1),
    ("cell_short_size_m", 1),
    ("cell_area_m2", 1),
    ("reference_plane_local_y_m", 1),
)

_CUT_COMMON_FIELDS = (
    "entry_x_m",
    "entry_z_m",
    "exit_x_m",
    "exit_z_m",
    "direction_x",
    "direction_z",
    "length_m",
)


def build_executed_cut_silver_sample(
    *,
    env_state: np.ndarray,
    qpos: np.ndarray,
    qvel: np.ndarray,
    episode_id: str,
    cycle_id: int,
    cycle_start_step: int,
    cycle_end_step_exclusive: int,
    operator_entry_step: int,
    operator_exit_step: int,
    dump_start_step: int | None = None,
    executed_cut: Mapping[str, Any],
    payload_gain_kg: float,
    effective_deposit_delta_kg: float,
    previous_outcome: Mapping[str, Any],
    config: StableTerrainWindowConfig | None = None,
    effective_move_min_volume_m3: float | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    """Build one sample from stable terrain before and after an executed cut."""

    config = config or StableTerrainWindowConfig()
    env = np.asarray(env_state, dtype=np.float64)
    if env.ndim != 2 or env.shape[1] < ENV_STATE_V2_3_DIM:
        return _rejection("env_state_requires_agx_v2_3_89")
    n_steps = int(env.shape[0])
    qpos_array = np.asarray(qpos, dtype=np.float64)
    qvel_array = np.asarray(qvel, dtype=np.float64)
    if qpos_array.shape != (n_steps, JOINT_STATE_DIM):
        return _rejection("qpos_requires_fixed_t_by_4_contract")
    if qvel_array.shape != (n_steps, JOINT_STATE_DIM):
        return _rejection("qvel_requires_fixed_t_by_4_contract")
    cycle_start = max(0, int(cycle_start_step))
    cycle_end = min(n_steps, int(cycle_end_step_exclusive))
    entry = int(operator_entry_step)
    exit_step = int(operator_exit_step)
    if not (cycle_start <= entry <= exit_step < cycle_end):
        return _rejection("invalid_cycle_or_operator_step_bounds")

    pre_start = entry - config.window_steps
    # In the replay contract ``cycle.start_step`` is also the operator entry
    # for most cycles.  The ten settled observations immediately before that
    # boundary belong to the prior return/hold and are the intended pre-cut
    # terrain evidence.
    if pre_start < 0:
        return _rejection("pre_window_not_available")
    pre = _stable_snapshot(env, pre_start, entry, config)
    if pre is None:
        return _rejection("pre_window_not_stable")

    first_post_start = exit_step + 1
    dump_start = (
        cycle_end
        if dump_start_step is None
        else min(cycle_end, int(dump_start_step))
    )
    if dump_start <= exit_step:
        return _rejection("dump_starts_before_post_window")
    last_post_start = min(
        cycle_end - config.window_steps,
        dump_start - config.window_steps,
        first_post_start + config.post_search_steps,
    )
    post: dict[str, Any] | None = None
    post_start: int | None = None
    for candidate_start in range(first_post_start, last_post_start + 1):
        candidate = _stable_snapshot(
            env,
            candidate_start,
            candidate_start + config.window_steps,
            config,
        )
        if candidate is None or not _matching_grid_geometry(pre, candidate, config):
            continue
        post = candidate
        post_start = candidate_start
        break
    if post is None or post_start is None:
        return _rejection("post_window_not_stable_before_dump_within_search")

    try:
        normalized_cut = _normalize_cut(executed_cut, input_contract="executed_cut")
        execution_context = _build_execution_context(
            qpos=qpos_array,
            qvel=qvel_array,
            env_state=env,
            entry_step=entry,
            cycle_index=int(cycle_id),
            previous_outcome=previous_outcome,
        )
        payload = _finite_float(payload_gain_kg, "payload_gain_kg")
        deposit = _finite_float(
            effective_deposit_delta_kg,
            "effective_deposit_delta_kg",
        )
    except (TypeError, ValueError) as exc:
        return _rejection("invalid_executed_cut_or_outcome", detail=str(exc))

    valid_mask = np.asarray(pre["valid_mask"], dtype=np.float64) * np.asarray(
        post["valid_mask"], dtype=np.float64
    )
    volume = compute_grid_volume_change(
        start_removed_depth_m=pre["removed_depth_m"],
        end_removed_depth_m=post["removed_depth_m"],
        cell_area_m2=float(pre["cell_area_m2"]),
        valid_mask=valid_mask,
    )
    if effective_move_min_volume_m3 is None:
        effective_move: bool | None = None
        effective_move_status = "threshold_not_configured"
    else:
        threshold = _finite_float(
            effective_move_min_volume_m3,
            "effective_move_min_volume_m3",
        )
        if threshold < 0.0:
            raise ValueError("effective_move_min_volume_m3 must be non-negative.")
        effective_move = bool(float(volume["removed_volume_m3"]) >= threshold)
        effective_move_status = "explicit_volume_threshold"

    outcome = dict(volume)
    outcome.update(
        {
            "terrain_delta_semantics": (
                "stable_post_median_minus_stable_pre_median_net"
            ),
            "payload_gain_kg": payload,
            "effective_deposit_delta_kg": deposit,
        }
    )
    record: dict[str, Any] = {
        "schema": SAMPLE_SCHEMA,
        "source": "stable_expert_replay_effect_sample_builder",
        "evidence_tier": EVIDENCE_TIER,
        "input_contract": "executed_cut",
        "effect_input_schema": EFFECT_INPUT_SCHEMA,
        "episode_id": str(episode_id),
        "reset_group_id": str(episode_id),
        "cycle_id": int(cycle_id),
        "source_path": source_path,
        "stability_contract": asdict(config),
        "pre_window": {
            "start_step": pre_start,
            "end_step_exclusive": entry,
        },
        "post_window": {
            "start_step": post_start,
            "end_step_exclusive": post_start + config.window_steps,
            "dump_start_step": dump_start,
            "status": "stable_window_ends_before_dump",
        },
        "pre_terrain": pre,
        "post_terrain": post,
        "execution_context": execution_context,
        "executed_cut": normalized_cut,
        "outcome": outcome,
        "capability_labels": {"effective_move": effective_move},
        "capability_label_status": {
            "effective_move": effective_move_status,
        },
    }
    return {"status": "present", "record": record}


def build_executed_cut_silver_samples(
    *,
    env_state: np.ndarray,
    qpos: np.ndarray,
    qvel: np.ndarray,
    episode_id: str,
    cycle_fields: Mapping[str, Sequence[Any] | np.ndarray],
    config: StableTerrainWindowConfig | None = None,
    effective_move_min_volume_m3: float | None = None,
    source_path: str | None = None,
    end_step_is_inclusive: bool = False,
    work_stage_id: np.ndarray | Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Build eligible cycle samples without indexing trailing ineligible rows."""

    config = config or StableTerrainWindowConfig()
    eligibility = _as_vector(
        cycle_fields.get("cleaning_effect_calibration_eligible", [])
    )
    records: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    skipped = 0
    required = (
        "cycle_id",
        "start_step",
        "end_step",
        "operator_entry_step",
        "operator_exit_step",
        "operator_entry_x_m",
        "operator_entry_z_m",
        "operator_exit_x_m",
        "operator_exit_z_m",
        "operator_cut_direction_x",
        "operator_cut_direction_z",
        "operator_cut_length_m",
        "operator_cut_depth_peak_m",
        "operator_cut_depth_source",
        "operator_cut_payload_gain_kg",
        "cycle_effective_deposit_delta_kg",
        "operator_cut_valid",
    )
    previous_outcome = _empty_previous_outcome()
    stages = None
    if work_stage_id is not None:
        stages = np.asarray(work_stage_id, dtype=np.int64).reshape(-1)
        if stages.size != len(env_state):
            raise ValueError("work_stage_id must have one value per env_state step")
    for index, eligible_value in enumerate(eligibility):
        if not bool(eligible_value):
            skipped += 1
            previous_outcome = _empty_previous_outcome()
            continue
        missing = [
            key
            for key in required
            if key not in cycle_fields or index >= len(_as_vector(cycle_fields[key]))
        ]
        if missing:
            previous_outcome = _empty_previous_outcome()
            rejections.append(
                {
                    "cycle_index": index,
                    "status": "rejected",
                    "reason": "eligible_cycle_missing_required_fields",
                    "missing_fields": missing,
                }
            )
            continue

        value = lambda key: _as_vector(cycle_fields[key])[index]  # noqa: E731
        end_step = int(value("end_step")) + (1 if end_step_is_inclusive else 0)
        exit_step = int(value("operator_exit_step"))
        dump_start_step = _first_dump_start_step(
            stages,
            start=exit_step + 1,
            end=end_step,
        )
        cut = {
            "entry_x_m": value("operator_entry_x_m"),
            "entry_z_m": value("operator_entry_z_m"),
            "exit_x_m": value("operator_exit_x_m"),
            "exit_z_m": value("operator_exit_z_m"),
            "direction_x": value("operator_cut_direction_x"),
            "direction_z": value("operator_cut_direction_z"),
            "length_m": value("operator_cut_length_m"),
            "actual_surface_penetration_peak_m": value("operator_cut_depth_peak_m"),
            "depth_source": _decode_scalar(value("operator_cut_depth_source")),
            "valid": bool(value("operator_cut_valid")),
        }
        result = build_executed_cut_silver_sample(
            env_state=env_state,
            qpos=qpos,
            qvel=qvel,
            episode_id=episode_id,
            cycle_id=int(value("cycle_id")),
            cycle_start_step=int(value("start_step")),
            cycle_end_step_exclusive=end_step,
            operator_entry_step=int(value("operator_entry_step")),
            operator_exit_step=exit_step,
            dump_start_step=dump_start_step,
            executed_cut=cut,
            payload_gain_kg=float(value("operator_cut_payload_gain_kg")),
            effective_deposit_delta_kg=float(value("cycle_effective_deposit_delta_kg")),
            previous_outcome=previous_outcome,
            config=config,
            effective_move_min_volume_m3=effective_move_min_volume_m3,
            source_path=source_path,
        )
        if result["status"] == "present":
            records.append(result["record"])
            previous_outcome = {
                "signed_depth_delta_m": list(
                    result["record"]["outcome"]["signed_depth_delta_m"]
                ),
                "payload_gain_kg": float(
                    result["record"]["outcome"]["payload_gain_kg"]
                ),
                "valid": True,
            }
        else:
            previous_outcome = _empty_previous_outcome()
            rejections.append(
                {
                    "cycle_index": index,
                    "cycle_id": int(value("cycle_id")),
                    **result,
                }
            )

    eligible_count = int(np.count_nonzero(eligibility))
    return {
        "schema": SAMPLE_SET_SCHEMA,
        "source": "stable_expert_replay_effect_sample_builder",
        "status": "present" if records else "no_usable_samples",
        "evidence_tier": EVIDENCE_TIER,
        "input_contract": "executed_cut",
        "episode_id": str(episode_id),
        "source_path": source_path,
        "eligible_cycle_count": eligible_count,
        "skipped_ineligible_cycle_count": skipped,
        "record_count": len(records),
        "rejected_eligible_cycle_count": len(rejections),
        "records": records,
        "rejections": rejections,
    }


def build_executed_cut_silver_samples_from_hdf5(
    source_path: str | Path,
    *,
    episode_id: str | None = None,
    config: StableTerrainWindowConfig | None = None,
    effective_move_min_volume_m3: float | None = None,
) -> dict[str, Any]:
    """Read one replay HDF5 and build samples from its explicit eligible rows."""

    import h5py

    path = Path(source_path)
    with h5py.File(path, "r") as handle:
        env_state = np.asarray(handle["observations/env_state"])
        qpos = np.asarray(handle["observations/qpos"])
        qvel = np.asarray(handle["observations/qvel"])
        if "v2/cycle" not in handle:
            return {
                "schema": SAMPLE_SET_SCHEMA,
                "status": "missing_v2_cycle_group",
                "source_path": str(path),
                "records": [],
                "rejections": [],
            }
        cycle_group = handle["v2/cycle"]
        cycle_fields = {
            str(key): np.asarray(cycle_group[key]) for key in cycle_group.keys()
        }
        if "v2/step/work_stage_id" not in handle:
            return {
                "schema": SAMPLE_SET_SCHEMA,
                "status": "missing_work_stage_id_for_predump_bound",
                "source_path": str(path),
                "records": [],
                "rejections": [],
            }
        work_stage_id = np.asarray(handle["v2/step/work_stage_id"])
        resolved_episode_id = episode_id or _decode_scalar(
            handle.attrs.get("episode_id", path.stem)
        )
    return build_executed_cut_silver_samples(
        env_state=env_state,
        qpos=qpos,
        qvel=qvel,
        episode_id=resolved_episode_id,
        cycle_fields=cycle_fields,
        config=config,
        effective_move_min_volume_m3=effective_move_min_volume_m3,
        source_path=str(path.resolve()),
        end_step_is_inclusive=True,
        work_stage_id=work_stage_id,
    )


def _first_dump_start_step(
    work_stage_id: np.ndarray | None,
    *,
    start: int,
    end: int,
) -> int | None:
    if work_stage_id is None:
        return None
    lower = max(0, int(start))
    upper = min(int(end), int(work_stage_id.size))
    if lower >= upper:
        return upper
    dump_id = int(WORK_STAGE_NAME_TO_ID["dump"])
    matches = np.flatnonzero(work_stage_id[lower:upper] == dump_id)
    return upper if matches.size == 0 else lower + int(matches[0])


def vectorize_effect_input(
    record: Mapping[str, Any],
    *,
    input_contract: EffectInputContract,
) -> tuple[list[float], list[str]]:
    """Return the only model input allowed by the selected evidence contract."""

    if input_contract not in {"executed_cut", "planned_cut"}:
        raise ValueError(f"Unsupported input_contract: {input_contract!r}")
    if record.get("effect_input_schema") != EFFECT_INPUT_SCHEMA:
        raise ValueError(f"effect_input_schema must be {EFFECT_INPUT_SCHEMA!r}.")
    terrain = _require_mapping(record, "pre_terrain")
    execution_context = _require_mapping(record, "execution_context")
    cut = _require_mapping(record, input_contract)
    if input_contract == "planned_cut":
        leakage = _find_forbidden_planned_key(cut, path="planned_cut")
        if leakage is not None:
            raise LabelLeakageError(f"Forbidden planned input field: {leakage}")

    values: list[float] = []
    names: list[str] = []
    for field, expected_size in _TERRAIN_VECTOR_FIELDS:
        field_values = _numeric_field_values(
            terrain,
            field,
            expected_size=expected_size,
            prefix="pre_terrain",
        )
        values.extend(field_values)
        if expected_size == 1:
            names.append(f"pre_terrain.{field}")
        else:
            names.extend(
                f"pre_terrain.{field}[{index}]" for index in range(expected_size)
            )
    context_values, context_names = _vectorize_execution_context(execution_context)
    values.extend(context_values)
    names.extend(context_names)
    for field in _CUT_COMMON_FIELDS:
        values.append(_finite_float(cut.get(field), f"{input_contract}.{field}"))
        names.append(f"{input_contract}.{field}")
    depth_field = (
        "actual_surface_penetration_peak_m"
        if input_contract == "executed_cut"
        else "planned_penetration_m"
    )
    values.append(
        _finite_float(cut.get(depth_field), f"{input_contract}.{depth_field}")
    )
    names.append(f"{input_contract}.{depth_field}")
    if input_contract == "planned_cut":
        payload_target_field = "planned_payload_target_kg"
        values.append(
            _finite_float(
                cut.get(payload_target_field),
                f"{input_contract}.{payload_target_field}",
            )
        )
        names.append(f"{input_contract}.{payload_target_field}")
    values.append(float(bool(cut.get("valid", False))))
    names.append(f"{input_contract}.valid")
    return values, names


def find_planned_input_leakage(record: Mapping[str, Any]) -> list[str]:
    """Report post-execution fields that are nested inside ``planned_cut``."""

    planned = record.get("planned_cut")
    if not isinstance(planned, Mapping):
        return []
    findings: list[str] = []

    def visit(value: Any, path: str) -> None:
        if not isinstance(value, Mapping):
            return
        for raw_key, nested in value.items():
            key = str(raw_key)
            nested_path = f"{path}.{key}"
            if key in _PLANNED_FORBIDDEN_KEYS or key.startswith("actual_"):
                findings.append(nested_path)
            visit(nested, nested_path)

    visit(planned, "planned_cut")
    return findings


def _stable_snapshot(
    env: np.ndarray,
    start: int,
    end: int,
    config: StableTerrainWindowConfig,
) -> dict[str, Any] | None:
    if start < 0 or end > env.shape[0] or end - start != config.window_steps:
        return None
    window = np.asarray(env[start:end, :ENV_STATE_V2_3_DIM], dtype=np.float64)
    selected = window[:, ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:ENV_STATE_V2_3_DIM]
    if not np.isfinite(selected).all():
        return None
    valid = window[
        :,
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
        + GRID_CELL_COUNT,
    ]
    coverage = window[
        :,
        ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX : ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX
        + GRID_CELL_COUNT,
    ]
    removed = window[
        :,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX : ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        + GRID_CELL_COUNT,
    ]
    geometry = window[
        :,
        ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX : ENV_STATE_DIG_AREA_REFERENCE_PLANE_LOCAL_Y_IDX
        + 1,
    ]
    if np.any(valid < 0.5):
        return None
    if np.any(coverage < config.min_surface_valid_fraction):
        return None
    if np.any(np.ptp(removed, axis=0) > config.max_removed_depth_range_m):
        return None
    if np.any(np.ptp(geometry, axis=0) > config.geometry_atol):
        return None

    median = np.median(window, axis=0)
    return {
        "surface_depth_m": _slice_list(
            median, ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX
        ),
        "removed_depth_m": _slice_list(
            median, ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        ),
        "target_depth_m": _slice_list(
            median, ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX
        ),
        "valid_mask": (
            median[
                ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
                + GRID_CELL_COUNT
            ]
            >= 0.5
        )
        .astype(float)
        .tolist(),
        "grid_origin_world_m": median[
            ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX : ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX
            + 3
        ].tolist(),
        "long_axis_unit_world": median[
            ENV_STATE_DIG_AREA_LONG_AXIS_UNIT_WORLD_START_IDX : ENV_STATE_DIG_AREA_LONG_AXIS_UNIT_WORLD_START_IDX
            + 3
        ].tolist(),
        "short_axis_unit_world": median[
            ENV_STATE_DIG_AREA_SHORT_AXIS_UNIT_WORLD_START_IDX : ENV_STATE_DIG_AREA_SHORT_AXIS_UNIT_WORLD_START_IDX
            + 3
        ].tolist(),
        "cell_long_size_m": float(median[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX]),
        "cell_short_size_m": float(median[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX]),
        "cell_area_m2": float(median[ENV_STATE_DIG_AREA_CELL_AREA_IDX]),
        "reference_plane_local_y_m": float(
            median[ENV_STATE_DIG_AREA_REFERENCE_PLANE_LOCAL_Y_IDX]
        ),
        "baseline_depth_m": _slice_list(
            median, ENV_STATE_DIG_AREA_BASELINE_DEPTH_START_IDX
        ),
        "surface_valid_fraction": _slice_list(
            median, ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX
        ),
    }


def _matching_grid_geometry(
    pre: Mapping[str, Any],
    post: Mapping[str, Any],
    config: StableTerrainWindowConfig,
) -> bool:
    fields = (
        "grid_origin_world_m",
        "long_axis_unit_world",
        "short_axis_unit_world",
        "cell_long_size_m",
        "cell_short_size_m",
        "cell_area_m2",
        "reference_plane_local_y_m",
        "baseline_depth_m",
    )
    return all(
        np.allclose(
            np.asarray(pre[field], dtype=np.float64),
            np.asarray(post[field], dtype=np.float64),
            rtol=0.0,
            atol=config.geometry_atol,
        )
        for field in fields
    )


def _build_execution_context(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    env_state: np.ndarray,
    entry_step: int,
    cycle_index: int,
    previous_outcome: Mapping[str, Any],
) -> dict[str, Any]:
    entry_qpos = np.asarray(qpos[entry_step], dtype=np.float64).reshape(-1)
    entry_qvel = np.asarray(qvel[entry_step], dtype=np.float64).reshape(-1)
    bucket_tip = np.asarray(
        [
            env_state[entry_step, ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX],
            env_state[entry_step, ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX],
            env_state[entry_step, ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX],
        ],
        dtype=np.float64,
    )
    return build_effect_execution_context(
        cycle_index=cycle_index,
        entry_qpos=entry_qpos,
        entry_qvel=entry_qvel,
        entry_bucket_tip_xyz_m=bucket_tip,
        previous_outcome=previous_outcome,
    )


def build_effect_execution_context(
    *,
    cycle_index: int,
    entry_qpos: Sequence[float],
    entry_qvel: Sequence[float],
    entry_bucket_tip_xyz_m: Sequence[float],
    previous_outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct the fixed execution-before-cut context shared by both stages."""

    qpos = np.asarray(entry_qpos, dtype=np.float64).reshape(-1)
    qvel = np.asarray(entry_qvel, dtype=np.float64).reshape(-1)
    bucket_tip = np.asarray(entry_bucket_tip_xyz_m, dtype=np.float64).reshape(-1)
    if qpos.size != JOINT_STATE_DIM or not np.isfinite(qpos).all():
        raise ValueError("execution_context.entry_qpos must contain 4 finite values.")
    if qvel.size != JOINT_STATE_DIM or not np.isfinite(qvel).all():
        raise ValueError("execution_context.entry_qvel must contain 4 finite values.")
    if bucket_tip.size != 3 or not np.isfinite(bucket_tip).all():
        raise ValueError(
            "execution_context.entry_bucket_tip_xyz_m must contain 3 finite values."
        )
    if isinstance(cycle_index, bool) or int(cycle_index) != cycle_index:
        raise ValueError("execution_context.cycle_index must be an integer.")
    return {
        "cycle_index": int(cycle_index),
        "entry_qpos": qpos.astype(float).tolist(),
        "entry_qvel": qvel.astype(float).tolist(),
        "entry_bucket_tip_xyz_m": bucket_tip.astype(float).tolist(),
        "previous_outcome": _normalize_previous_outcome(previous_outcome),
    }


def _vectorize_execution_context(
    context: Mapping[str, Any],
) -> tuple[list[float], list[str]]:
    values = [
        _finite_float(context.get("cycle_index"), "execution_context.cycle_index")
    ]
    names = ["execution_context.cycle_index"]
    for field, size in (
        ("entry_qpos", JOINT_STATE_DIM),
        ("entry_qvel", JOINT_STATE_DIM),
        ("entry_bucket_tip_xyz_m", 3),
    ):
        field_values = _numeric_field_values(
            context,
            field,
            expected_size=size,
            prefix="execution_context",
        )
        values.extend(field_values)
        names.extend(f"execution_context.{field}[{index}]" for index in range(size))
    previous = context.get("previous_outcome")
    if not isinstance(previous, Mapping):
        raise ValueError("execution_context.previous_outcome must be an object.")
    delta = _numeric_field_values(
        previous,
        "signed_depth_delta_m",
        expected_size=GRID_CELL_COUNT,
        prefix="execution_context.previous_outcome",
    )
    values.extend(delta)
    names.extend(
        f"execution_context.previous_outcome.signed_depth_delta_m[{index}]"
        for index in range(GRID_CELL_COUNT)
    )
    values.append(
        _finite_float(
            previous.get("payload_gain_kg"),
            "execution_context.previous_outcome.payload_gain_kg",
        )
    )
    names.append("execution_context.previous_outcome.payload_gain_kg")
    valid = previous.get("valid")
    if not isinstance(valid, (bool, np.bool_)):
        raise ValueError(
            "execution_context.previous_outcome.valid must be an explicit boolean."
        )
    values.append(float(bool(valid)))
    names.append("execution_context.previous_outcome.valid")
    return values, names


def _normalize_previous_outcome(outcome: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(outcome, Mapping):
        raise ValueError("previous_outcome must be an object.")
    delta = _numeric_field_values(
        outcome,
        "signed_depth_delta_m",
        expected_size=GRID_CELL_COUNT,
        prefix="previous_outcome",
    )
    payload = _finite_float(
        outcome.get("payload_gain_kg"),
        "previous_outcome.payload_gain_kg",
    )
    valid = outcome.get("valid")
    if not isinstance(valid, (bool, np.bool_)):
        raise ValueError("previous_outcome.valid must be an explicit boolean.")
    return {
        "signed_depth_delta_m": delta,
        "payload_gain_kg": payload,
        "valid": bool(valid),
    }


def _empty_previous_outcome() -> dict[str, Any]:
    return {
        "signed_depth_delta_m": [0.0] * GRID_CELL_COUNT,
        "payload_gain_kg": 0.0,
        "valid": False,
    }


def _normalize_cut(
    cut: Mapping[str, Any],
    *,
    input_contract: EffectInputContract,
) -> dict[str, Any]:
    if input_contract == "planned_cut":
        leakage = _find_forbidden_planned_key(cut, path="planned_cut")
        if leakage:
            raise LabelLeakageError(f"Forbidden planned input field: {leakage}")
    result = {
        field: _finite_float(cut.get(field), f"{input_contract}.{field}")
        for field in _CUT_COMMON_FIELDS
    }
    depth_field = (
        "actual_surface_penetration_peak_m"
        if input_contract == "executed_cut"
        else "planned_penetration_m"
    )
    result[depth_field] = _finite_float(
        cut.get(depth_field),
        f"{input_contract}.{depth_field}",
    )
    if input_contract == "planned_cut":
        result["planned_payload_target_kg"] = _finite_float(
            cut.get("planned_payload_target_kg"),
            "planned_cut.planned_payload_target_kg",
        )
    result["valid"] = bool(cut.get("valid", False))
    if "depth_source" in cut:
        result["depth_source"] = str(cut["depth_source"])
    return result


def _find_forbidden_planned_key(value: Mapping[str, Any], *, path: str) -> str | None:
    for raw_key, nested in value.items():
        key = str(raw_key)
        nested_path = f"{path}.{key}"
        if key in _PLANNED_FORBIDDEN_KEYS or key.startswith("actual_"):
            return nested_path
        if isinstance(nested, Mapping):
            found = _find_forbidden_planned_key(nested, path=nested_path)
            if found:
                return found
    return None


def _require_mapping(record: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _numeric_field_values(
    mapping: Mapping[str, Any],
    field: str,
    *,
    expected_size: int,
    prefix: str,
) -> list[float]:
    raw = mapping.get(field)
    array = np.asarray(raw, dtype=np.float64).reshape(-1)
    if array.size != expected_size or not np.isfinite(array).all():
        raise ValueError(
            f"{prefix}.{field} must contain {expected_size} finite value(s)."
        )
    return array.astype(float).tolist()


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} must be a finite number.")
    return result


def _slice_list(array: np.ndarray, start: int) -> list[float]:
    return np.asarray(array[start : start + GRID_CELL_COUNT], dtype=float).tolist()


def _as_vector(value: Sequence[Any] | np.ndarray) -> np.ndarray:
    return np.asarray(value).reshape(-1)


def _decode_scalar(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def _rejection(reason: str, *, detail: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "rejected", "reason": reason}
    if detail is not None:
        result["detail"] = detail
    return result


__all__ = [
    "EFFECT_INPUT_SCHEMA",
    "EVIDENCE_TIER",
    "EffectInputContract",
    "LabelLeakageError",
    "SAMPLE_SCHEMA",
    "SAMPLE_SET_SCHEMA",
    "StableTerrainWindowConfig",
    "build_effect_execution_context",
    "build_executed_cut_silver_sample",
    "build_executed_cut_silver_samples",
    "build_executed_cut_silver_samples_from_hdf5",
    "find_planned_input_leakage",
    "vectorize_effect_input",
]
