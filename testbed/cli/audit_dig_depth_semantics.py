"""Audit dig primitive depth semantics against local dig-area surface fields.

The V2.4.5 planner should treat ``bucket_depth_below_dig_area_plane`` as a
coarse reference only.  This audit reconstructs a signed bucket-tip penetration
estimate from the bucket tip's dig-area-relative Y coordinate and the current
cell surface depth, then compares it with tokens, removed-depth outcomes, and
payload.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.dataset import _episode_matches_metadata_filters
from testbed.data.hdf5_io import episode_id_from_path, list_episodes
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
)
from testbed.data.schema import (
    DS_ENV_STATE,
    DS_V2_STEP_DIG_CUT_TOKENS,
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_MASS_DELTA_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
)

DEFAULT_QC6_DIG_DATASET = (
    "/fastdata/pingfan/excavator_testbed_data_hot/"
    "yulong_v2_4_removed_depth_hindsight_goal_primitives_copy_"
    "v2_4_5_process_boundary_qc6_20260522/dig"
)

CELL_COUNT = 6


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-dig-depth-semantics",
        description=(
            "Audit dig primitive depth signals by reconstructing bucket-tip "
            "surface penetration from relative Y and dig-area surface-depth grids."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        default=DEFAULT_QC6_DIG_DATASET,
        help="Dig primitive dataset root. Defaults to the qc6 materialized dig copy.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument(
        "--csv-output",
        default=None,
        help="Optional per-episode CSV output path.",
    )
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=0,
        help="Maximum filtered episodes to audit; <=0 means all matching episodes.",
    )
    parser.add_argument(
        "--training-tier",
        default="gold",
        help="Metadata training_tier to select; use 'all' to disable this filter.",
    )
    parser.add_argument(
        "--surface-source",
        choices=("current_cell", "dominant_cell"),
        default="current_cell",
        help=(
            "Which cell surface depth to use for per-step penetration. "
            "current_cell follows env_state bucket cell id with dominant-cell "
            "fallback; dominant_cell uses the cycle dominant removed-depth cell."
        ),
    )
    parser.add_argument(
        "--metadata-filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional metadata filter. Repeats are allowed.",
    )
    args = parser.parse_args()

    metadata_filters = _parse_metadata_filter_args(args.metadata_filter)
    if str(args.training_tier).lower() != "all":
        metadata_filters["training_tier"] = str(args.training_tier)
    dataset_dir = Path(args.dataset_dir)
    episode_paths = _select_episode_paths(
        dataset_dir=dataset_dir,
        metadata_filters=metadata_filters,
        max_episodes=int(args.max_episodes),
    )
    if not episode_paths:
        raise FileNotFoundError(
            f"No matching dig episodes found under {dataset_dir} with filters "
            f"{metadata_filters}."
        )

    records: list[dict[str, Any]] = []
    for index, episode_path in enumerate(episode_paths):
        print(f"[{index + 1}/{len(episode_paths)}] {episode_path.name}", flush=True)
        records.append(
            compute_episode_metrics(
                episode_path,
                surface_source=str(args.surface_source),
            )
        )

    summary = summarize_metrics(records)
    output = {
        "schema_version": "dig_depth_semantics_audit_v1",
        "dataset_dir": str(dataset_dir),
        "metadata_filters": metadata_filters,
        "surface_source": str(args.surface_source),
        "selected_episode_ids": [episode_id_from_path(path) for path in episode_paths],
        "record_count": len(records),
        "summary": summary,
        "episode_metrics": records,
        "interpretation_hint": (
            "Use peak_surface_penetration_m and surface_penetration_auc_m_s as "
            "the physical bucket-depth references. Treat plane_depth fields as "
            "diagnostics only; large plane_minus_surface_penetration offsets "
            "mean the plane signal should not drive target-depth semantics."
        ),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_jsonable(output), indent=2, sort_keys=True) + "\n")
    if args.csv_output:
        _write_csv(Path(args.csv_output), records)
    print(json.dumps(_jsonable(summary.get("headline", {})), indent=2, sort_keys=True))
    print(output_path)


def compute_episode_metrics(
    episode_path: str | Path,
    *,
    surface_source: str = "current_cell",
) -> dict[str, Any]:
    episode_path = Path(episode_path)
    with h5py.File(episode_path, "r") as handle:
        if DS_ENV_STATE not in handle:
            raise KeyError(f"{episode_path} is missing {DS_ENV_STATE}.")
        env_state = np.asarray(handle[DS_ENV_STATE][()], dtype=np.float32)
        if env_state.ndim != 2:
            raise ValueError(f"{DS_ENV_STATE} must be 2D, got {env_state.shape}.")
        metadata = _read_metadata(handle)
        dt = _finite_float(metadata.get("dt"), default=0.02)
        cycle = handle.get("v2/cycle")
        dominant_cell = _read_cycle_int(
            cycle, "dominant_removed_depth_cell_id", default=0
        )
        dominant_cell = _sanitize_cell_id(dominant_cell, fallback=0)
        cell_ids = _surface_cell_ids(
            env_state=env_state,
            dominant_cell=dominant_cell,
            surface_source=surface_source,
        )
        surface_depth = _gather_env_cell_values(
            env_state, ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX, cell_ids
        )
        current_removed_depth = _gather_env_cell_values(
            env_state, ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX, cell_ids
        )
        reference_depth = _bucket_tip_reference_depth(env_state)
        signed_surface_penetration = reference_depth - surface_depth
        positive_surface_penetration = np.maximum(signed_surface_penetration, 0.0)
        plane_depth = _read_env_column(
            env_state, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
        )
        local_surface_depth = _read_env_column(
            env_state, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX
        )
        contact_mask = _read_env_column(
            env_state, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX
        )
        bucket_mass = _read_env_column(env_state, ENV_STATE_MASS_IN_BUCKET_IDX)
        bucket_mass_delta = _read_env_column(env_state, ENV_STATE_BUCKET_MASS_DELTA_IDX)
        token = _read_first_step_token(handle)
        removed_depth_grid = _read_cycle_array(
            cycle, "actual_removed_depth_delta_grid", default_shape=(CELL_COUNT,)
        )

        peak_penetration = _nanmax(signed_surface_penetration)
        peak_index = _nanargmax(signed_surface_penetration)
        plane_minus_penetration = plane_depth - signed_surface_penetration
        local_minus_penetration = local_surface_depth - signed_surface_penetration
        entry_cell = int(cell_ids[0]) if cell_ids.size else dominant_cell
        exit_cell = int(cell_ids[-1]) if cell_ids.size else dominant_cell

        return {
            "episode_id": episode_id_from_path(episode_path),
            "path": str(episode_path),
            "training_tier": _read_cycle_text(cycle, "training_tier", metadata),
            "n_steps": int(env_state.shape[0]),
            "dt_s": float(dt),
            "surface_source": surface_source,
            "dominant_removed_depth_cell_id": int(dominant_cell),
            "entry_cell_id": entry_cell,
            "exit_cell_id": exit_cell,
            "cell_switch_count": int(np.sum(np.diff(cell_ids) != 0)) if cell_ids.size else 0,
            "entry_reference_depth_m": _first_finite(reference_depth),
            "entry_surface_depth_m": _first_finite(surface_depth),
            "entry_surface_penetration_m": _first_finite(
                signed_surface_penetration
            ),
            "peak_reference_depth_m": _value_at(reference_depth, peak_index),
            "peak_surface_depth_m": _value_at(surface_depth, peak_index),
            "peak_surface_penetration_m": peak_penetration,
            "peak_surface_penetration_step": int(peak_index),
            "exit_surface_penetration_m": _last_finite(
                signed_surface_penetration
            ),
            "positive_surface_penetration_fraction": _finite_mean(
                positive_surface_penetration > 0.0
            ),
            "surface_penetration_auc_m_steps": _nansum(
                positive_surface_penetration
            ),
            "surface_penetration_auc_m_s": _nansum(positive_surface_penetration)
            * float(dt),
            "contact_fraction": _finite_mean(contact_mask > 0.5),
            "contact_steps": int(np.nansum(contact_mask > 0.5)),
            "bucket_mass_entry_kg": _first_finite(bucket_mass),
            "bucket_mass_peak_kg": _nanmax(bucket_mass),
            "bucket_mass_exit_kg": _last_finite(bucket_mass),
            "bucket_mass_gain_from_entry_peak_kg": _nanmax(bucket_mass)
            - _first_finite(bucket_mass),
            "bucket_mass_delta_positive_sum_kg": _nansum(
                np.maximum(bucket_mass_delta, 0.0)
            ),
            "plane_depth_entry_m": _first_finite(plane_depth),
            "plane_depth_peak_m": _nanmax(plane_depth),
            "plane_depth_exit_m": _last_finite(plane_depth),
            "plane_minus_surface_penetration_median_m": _nanpercentile(
                plane_minus_penetration, 50
            ),
            "plane_minus_surface_penetration_p90_abs_m": _nanpercentile(
                np.abs(plane_minus_penetration), 90
            ),
            "local_depth_peak_m": _nanmax(local_surface_depth),
            "local_minus_surface_penetration_median_m": _nanpercentile(
                local_minus_penetration, 50
            ),
            "token_depth_target_m": _token_scaled(token, 7, DIG_CUT_DEPTH_SCALE_M),
            "token_payload_target_kg": _token_scaled(token, 8, DIG_CUT_PAYLOAD_SCALE_KG),
            "token_cut_length_m": _token_scaled(token, 6, DIG_CUT_LENGTH_SCALE_M),
            "token_valid": _token_value(token, 9),
            "operator_entry_y_m": _read_cycle_float(cycle, "operator_entry_y_m"),
            "operator_exit_y_m": _read_cycle_float(cycle, "operator_exit_y_m"),
            "operator_cut_depth_peak_m": _read_cycle_float(
                cycle, "operator_cut_depth_peak_m"
            ),
            "operator_cut_length_m": _read_cycle_float(cycle, "operator_cut_length_m"),
            "operator_cut_payload_gain_kg": _read_cycle_float(
                cycle, "operator_cut_payload_gain_kg"
            ),
            "dig_outcome_payload_gain_kg": _read_cycle_float(
                cycle, "dig_outcome_payload_gain_kg"
            ),
            "dig_outcome_effective_deposit_delta_kg": _read_cycle_float(
                cycle, "dig_outcome_effective_deposit_delta_kg"
            ),
            "actual_removed_depth_peak_m": _nanmax(removed_depth_grid),
            "actual_removed_depth_dominant_m": _value_at(
                removed_depth_grid, dominant_cell
            ),
            "current_removed_depth_entry_m": _first_finite(current_removed_depth),
            "current_removed_depth_exit_m": _last_finite(current_removed_depth),
            "depth_outcome_source": _read_cycle_text(cycle, "depth_outcome_source", metadata),
            "surface_penetration_minus_removed_depth_peak_m": peak_penetration
            - _nanmax(removed_depth_grid),
            "surface_penetration_minus_token_depth_m": peak_penetration
            - _token_scaled(token, 7, DIG_CUT_DEPTH_SCALE_M),
        }


def summarize_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_fields = [
        "peak_surface_penetration_m",
        "surface_penetration_auc_m_s",
        "actual_removed_depth_peak_m",
        "actual_removed_depth_dominant_m",
        "token_depth_target_m",
        "operator_cut_depth_peak_m",
        "dig_outcome_payload_gain_kg",
        "token_payload_target_kg",
        "token_cut_length_m",
        "plane_minus_surface_penetration_median_m",
        "plane_minus_surface_penetration_p90_abs_m",
        "contact_fraction",
        "positive_surface_penetration_fraction",
    ]
    summary = {field: _stats([record.get(field) for record in records]) for field in numeric_fields}
    by_cell: dict[str, dict[str, Any]] = {}
    for cell_id in range(CELL_COUNT):
        cell_records = [
            record
            for record in records
            if int(record.get("dominant_removed_depth_cell_id", -1)) == cell_id
        ]
        by_cell[str(cell_id)] = {
            "count": len(cell_records),
            "peak_surface_penetration_m": _stats(
                [record.get("peak_surface_penetration_m") for record in cell_records]
            ),
            "actual_removed_depth_peak_m": _stats(
                [record.get("actual_removed_depth_peak_m") for record in cell_records]
            ),
            "dig_outcome_payload_gain_kg": _stats(
                [record.get("dig_outcome_payload_gain_kg") for record in cell_records]
            ),
            "token_depth_target_m": _stats(
                [record.get("token_depth_target_m") for record in cell_records]
            ),
        }
    correlations = {
        "peak_surface_penetration_vs_payload": _pearson(
            [record.get("peak_surface_penetration_m") for record in records],
            [record.get("dig_outcome_payload_gain_kg") for record in records],
        ),
        "surface_penetration_auc_vs_payload": _pearson(
            [record.get("surface_penetration_auc_m_s") for record in records],
            [record.get("dig_outcome_payload_gain_kg") for record in records],
        ),
        "token_depth_vs_payload": _pearson(
            [record.get("token_depth_target_m") for record in records],
            [record.get("dig_outcome_payload_gain_kg") for record in records],
        ),
        "removed_depth_vs_payload": _pearson(
            [record.get("actual_removed_depth_peak_m") for record in records],
            [record.get("dig_outcome_payload_gain_kg") for record in records],
        ),
        "peak_surface_penetration_vs_removed_depth": _pearson(
            [record.get("peak_surface_penetration_m") for record in records],
            [record.get("actual_removed_depth_peak_m") for record in records],
        ),
    }
    headline = {
        "count": len(records),
        "peak_surface_penetration_p50_m": summary[
            "peak_surface_penetration_m"
        ].get("p50"),
        "peak_surface_penetration_p90_m": summary[
            "peak_surface_penetration_m"
        ].get("p90"),
        "removed_depth_peak_p50_m": summary["actual_removed_depth_peak_m"].get("p50"),
        "token_depth_p50_m": summary["token_depth_target_m"].get("p50"),
        "payload_p50_kg": summary["dig_outcome_payload_gain_kg"].get("p50"),
        "plane_offset_p50_m": summary[
            "plane_minus_surface_penetration_median_m"
        ].get("p50"),
        "corr_surface_penetration_auc_vs_payload": correlations[
            "surface_penetration_auc_vs_payload"
        ],
    }
    return {
        "headline": headline,
        "fields": summary,
        "by_dominant_cell": by_cell,
        "correlations": correlations,
    }


def _select_episode_paths(
    *,
    dataset_dir: Path,
    metadata_filters: dict[str, Any],
    max_episodes: int,
) -> list[Path]:
    selected: list[Path] = []
    for episode_path in list_episodes(dataset_dir):
        with h5py.File(episode_path, "r") as handle:
            if metadata_filters and not _episode_matches_metadata_filters(
                handle, metadata_filters
            ):
                continue
        selected.append(episode_path)
        if max_episodes > 0 and len(selected) >= max_episodes:
            break
    return selected


def _surface_cell_ids(
    *,
    env_state: np.ndarray,
    dominant_cell: int,
    surface_source: str,
) -> np.ndarray:
    if surface_source == "dominant_cell":
        return np.full(env_state.shape[0], dominant_cell, dtype=np.int64)
    if surface_source != "current_cell":
        raise ValueError(f"Unsupported surface_source: {surface_source!r}")
    if env_state.shape[1] <= ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
        return np.full(env_state.shape[0], dominant_cell, dtype=np.int64)
    raw = np.asarray(env_state[:, ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX], dtype=np.float32)
    cell_ids = np.full(raw.shape[0], dominant_cell, dtype=np.int64)
    finite = np.isfinite(raw)
    rounded = np.rint(raw[finite]).astype(np.int64)
    valid = (rounded >= 0) & (rounded < CELL_COUNT)
    finite_indices = np.nonzero(finite)[0]
    cell_ids[finite_indices[valid]] = rounded[valid]
    return cell_ids


def _bucket_tip_reference_depth(env_state: np.ndarray) -> np.ndarray:
    if env_state.shape[1] > ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX:
        tip_y = _read_env_column(env_state, ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX)
        if np.any(np.isfinite(tip_y)):
            return -tip_y
    if env_state.shape[1] > ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX:
        return -_read_env_column(env_state, ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX)
    return np.full(env_state.shape[0], np.nan, dtype=np.float32)


def _gather_env_cell_values(
    env_state: np.ndarray,
    start_idx: int,
    cell_ids: np.ndarray,
) -> np.ndarray:
    values = np.full(env_state.shape[0], np.nan, dtype=np.float32)
    if env_state.shape[1] < start_idx + CELL_COUNT:
        return values
    for cell_id in range(CELL_COUNT):
        mask = cell_ids == cell_id
        if np.any(mask):
            values[mask] = env_state[mask, start_idx + cell_id]
    return values


def _read_env_column(env_state: np.ndarray, index: int) -> np.ndarray:
    if env_state.shape[1] <= index:
        return np.full(env_state.shape[0], np.nan, dtype=np.float32)
    return np.asarray(env_state[:, index], dtype=np.float32)


def _read_first_step_token(handle: h5py.File) -> np.ndarray | None:
    if DS_V2_STEP_DIG_CUT_TOKENS not in handle:
        return None
    tokens = np.asarray(handle[DS_V2_STEP_DIG_CUT_TOKENS][()], dtype=np.float32)
    if tokens.ndim != 2 or tokens.shape[0] <= 0:
        return None
    return tokens[0]


def _read_metadata(handle: h5py.File) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if "metadata" in handle:
        metadata.update(dict(handle["metadata"].attrs))
    metadata.update(dict(handle.attrs))
    return metadata


def _read_cycle_array(
    cycle: h5py.Group | None,
    key: str,
    *,
    default_shape: tuple[int, ...],
) -> np.ndarray:
    if cycle is None or key not in cycle:
        return np.full(default_shape, np.nan, dtype=np.float32)
    arr = np.asarray(cycle[key][()], dtype=np.float32)
    if arr.ndim >= 2:
        arr = arr[0]
    return np.asarray(arr, dtype=np.float32).reshape(-1)


def _read_cycle_float(cycle: h5py.Group | None, key: str) -> float:
    if cycle is None or key not in cycle:
        return float("nan")
    value = np.asarray(cycle[key][()])
    if value.size <= 0:
        return float("nan")
    return _finite_float(value.reshape(-1)[0], default=float("nan"))


def _read_cycle_int(
    cycle: h5py.Group | None,
    key: str,
    *,
    default: int,
) -> int:
    value = _read_cycle_float(cycle, key)
    if not np.isfinite(value):
        return int(default)
    return int(round(float(value)))


def _read_cycle_text(
    cycle: h5py.Group | None,
    key: str,
    metadata: dict[str, Any],
) -> str:
    if cycle is not None and key in cycle:
        value = np.asarray(cycle[key][()])
        if value.size > 0:
            return _decode_text(value.reshape(-1)[0])
    if key in metadata:
        return _decode_text(metadata[key])
    return ""


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.bytes_):
        return value.tobytes().decode()
    if isinstance(value, np.generic):
        value = value.item()
    return str(value)


def _sanitize_cell_id(value: int, *, fallback: int) -> int:
    if 0 <= int(value) < CELL_COUNT:
        return int(value)
    return int(fallback)


def _token_scaled(token: np.ndarray | None, index: int, scale: float) -> float:
    value = _token_value(token, index)
    if not np.isfinite(value):
        return float("nan")
    return float(value) * float(scale)


def _token_value(token: np.ndarray | None, index: int) -> float:
    if token is None or token.shape[0] <= index:
        return float("nan")
    return _finite_float(token[index], default=float("nan"))


def _first_finite(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = arr[np.isfinite(arr)]
    if finite.size <= 0:
        return float("nan")
    return float(finite[0])


def _last_finite(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = arr[np.isfinite(arr)]
    if finite.size <= 0:
        return float("nan")
    return float(finite[-1])


def _value_at(values: np.ndarray, index: int) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if index < 0 or index >= arr.size:
        return float("nan")
    return _finite_float(arr[index], default=float("nan"))


def _nanargmax(values: np.ndarray) -> int:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size <= 0 or not np.any(np.isfinite(arr)):
        return 0
    return int(np.nanargmax(arr))


def _nanmax(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size <= 0 or not np.any(np.isfinite(arr)):
        return float("nan")
    return float(np.nanmax(arr))


def _nansum(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size <= 0:
        return float("nan")
    return float(np.nansum(arr))


def _nanpercentile(values: np.ndarray, q: float) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size <= 0:
        return float("nan")
    return float(np.percentile(arr, q))


def _finite_mean(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size <= 0:
        return float("nan")
    return float(np.mean(arr))


def _finite_float(value: Any, *, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(result):
        return float(default)
    return result


def _stats(values: list[Any]) -> dict[str, Any]:
    arr = np.asarray([_finite_float(value, default=float("nan")) for value in values])
    arr = arr[np.isfinite(arr)]
    if arr.size <= 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
    }


def _pearson(xs: list[Any], ys: list[Any]) -> float | None:
    x = np.asarray([_finite_float(value, default=float("nan")) for value in xs])
    y = np.asarray([_finite_float(value, default=float("nan")) for value in ys])
    mask = np.isfinite(x) & np.isfinite(y)
    if int(np.sum(mask)) < 2:
        return None
    x = x[mask]
    y = y[mask]
    if float(np.std(x)) <= 1.0e-12 or float(np.std(y)) <= 1.0e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _parse_metadata_filter_args(values: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Metadata filter must be KEY=VALUE, got {item!r}.")
        key, value = item.split("=", 1)
        filters[key.strip()] = value.strip()
    return filters


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("")
        return
    fieldnames = sorted(records[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(_jsonable(record))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


if __name__ == "__main__":
    main()
