"""Build V2.4.5 surface-depth planner priors from primitive copies.

The dig coverage prior is keyed by dominant removed-depth cells.  Return-start
envelopes, however, describe the start state of the *next* dig primitive, so
cell-conditioned return priors must be grouped by the next operator entry target
instead of by the envelope token's instantaneous long/short bucket position.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)

DEPTH_SCALE_M = 0.80
CELL_COUNT = 6
RETURN_ENVELOPE_MATCH_SOURCE = "nearest_qc6_coverage_cell_by_next_operator_entry"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-surface-depth-planner-prior",
        description=(
            "Build a V2.4.5 dig-cut planner prior and state exemplars from a "
            "materialized primitive copy."
        ),
    )
    parser.add_argument("--copy-root", required=True, help="Primitive copy root.")
    parser.add_argument("--prior-path", required=True, help="Output prior JSON path.")
    parser.add_argument(
        "--state-exemplar-path",
        required=True,
        help="Output state-exemplar JSON path.",
    )
    parser.add_argument("--tag", default="", help="Prior id tag.")
    parser.add_argument(
        "--depth-scale-m",
        type=float,
        default=DEPTH_SCALE_M,
        help="Normalization scale for dig cut depth tokens.",
    )
    parser.add_argument(
        "--split-dir",
        default="",
        help=(
            "Optional directory containing dig_source_split.yaml and "
            "return_source_split.yaml."
        ),
    )
    parser.add_argument(
        "--split-partition",
        choices=("train", "val"),
        default="train",
        help="Primitive split partition used when --split-dir is set.",
    )
    parser.add_argument(
        "--return-source-label",
        default="",
        help=(
            "Optional debug provenance prefix for return envelope tokens. "
            "Legacy priors without this field keep the qc6 prefix."
        ),
    )
    args = parser.parse_args()

    copy_root = Path(args.copy_root)
    dig_episode_ids: tuple[int, ...] | None = None
    return_episode_ids: tuple[int, ...] | None = None
    dig_selection: dict[str, Any] | None = None
    return_selection: dict[str, Any] | None = None
    if str(args.split_dir).strip():
        split_dir = Path(args.split_dir)
        dig_episode_ids, dig_selection = load_split_episode_ids(
            split_dir / "dig_source_split.yaml",
            partition=str(args.split_partition),
        )
        return_episode_ids, return_selection = load_split_episode_ids(
            split_dir / "return_source_split.yaml",
            partition=str(args.split_partition),
        )
    prior, state_payload = build_surface_depth_planner_prior(
        copy_root=copy_root,
        tag=str(args.tag or copy_root.name),
        depth_scale_m=float(args.depth_scale_m),
        dig_episode_ids=dig_episode_ids,
        return_episode_ids=return_episode_ids,
        dig_episode_selection=dig_selection,
        return_episode_selection=return_selection,
        return_source_label=str(args.return_source_label).strip(),
    )
    prior_path = Path(args.prior_path)
    state_exemplar_path = Path(args.state_exemplar_path)
    write_surface_depth_planner_prior_outputs(
        prior=prior,
        state_payload=state_payload,
        prior_path=prior_path,
        state_exemplar_path=state_exemplar_path,
    )
    print(
        json.dumps(
            {
                "prior": str(prior_path),
                "state_exemplars": str(state_exemplar_path),
                "gold_dig": int(prior["source"]["source_cycle_count_used"]),
                "return_envelope_cells": [
                    int(cell["cell_id"])
                    for cell in prior.get("return_start_envelope_cells", [])
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def build_surface_depth_planner_prior(
    *,
    copy_root: Path,
    tag: str,
    depth_scale_m: float = DEPTH_SCALE_M,
    dig_episode_ids: Iterable[int] | None = None,
    return_episode_ids: Iterable[int] | None = None,
    dig_episode_selection: dict[str, Any] | None = None,
    return_episode_selection: dict[str, Any] | None = None,
    return_source_label: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = _load_gold_dig_records(
        copy_root / "dig",
        episode_ids=dig_episode_ids,
    )
    if not records:
        raise FileNotFoundError(f"no gold dig records in {copy_root / 'dig'}")

    by_cell: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_cell[int(record["cell_id"])].append(record)

    field_names = [
        ("entry_x_m", "operator_entry_x_m"),
        ("entry_z_m", "operator_entry_z_m"),
        ("exit_x_m", "operator_exit_x_m"),
        ("exit_z_m", "operator_exit_z_m"),
        ("cut_direction_x", "operator_cut_direction_x"),
        ("cut_direction_z", "operator_cut_direction_z"),
        ("cut_length_m", "operator_cut_length_m"),
        ("cut_depth_peak_m", "operator_cut_depth_peak_m"),
        ("payload_gain_kg", "operator_cut_payload_gain_kg"),
        ("effective_deposit_delta_kg", "operator_effective_deposit_delta_kg"),
    ]
    fields = {
        public: _stats([float(record["raw"][raw_name]) for record in records])
        for public, raw_name in field_names
    }
    coverage_cells = _build_coverage_cells(by_cell, len(records))
    return_prior = _build_return_start_envelope_prior(
        copy_root / "return",
        coverage_cells=coverage_cells,
        episode_ids=return_episode_ids,
        episode_selection=return_episode_selection,
        source_label=return_source_label,
    )

    prior: dict[str, Any] = {
        "prior_id": f"yulong_surface_depth_dig_cut_prior_{tag}",
        "schema_version": "v3",
        "dig_cut_token_contract": "v2_4_removed_depth_cut_v3",
        "dig_cut_depth_semantic": "bucket_depth_below_local_surface_peak_m",
        "dig_cut_depth_scale_m": float(depth_scale_m),
        "token_order": [
            "entry_x",
            "entry_z",
            "exit_x",
            "exit_z",
            "cut_direction_x",
            "cut_direction_z",
            "cut_length",
            "cut_depth_semantic",
            "payload_gain",
            "valid",
        ],
        "source": {
            "source_dataset": str(copy_root / "dig"),
            "source_cycle_count_used": len(records),
            "tier_filter": "gold",
            "notes": (
                "Generated from repaired DigArea geometry replay. "
                "cut_depth_peak_m is surface-relative bucket penetration; "
                "removed-depth grids remain planner terrain state."
            ),
        },
        "fields": fields,
        "coverage_cells": coverage_cells,
    }
    if dig_episode_selection is not None:
        prior["source"]["episode_selection"] = dict(dig_episode_selection)
    prior.update(return_prior)
    state_payload = _build_state_exemplar_payload(records, by_cell)
    return prior, state_payload


def match_return_envelope_cell_by_next_entry(
    *,
    next_entry_x_m: float,
    next_entry_z_m: float,
    coverage_cells: Iterable[dict[str, Any]],
) -> int | None:
    """Return the nearest coverage-cell id for a next-dig entry point."""

    if not (np.isfinite(next_entry_x_m) and np.isfinite(next_entry_z_m)):
        return None
    best_cell: int | None = None
    best_distance = float("inf")
    for cell in coverage_cells:
        entry = dict(cell.get("entry", {}) or {})
        cell_id = int(cell.get("cell_id", -1))
        entry_x = float(entry.get("x_m", float("nan")))
        entry_z = float(entry.get("z_m", float("nan")))
        if not (np.isfinite(entry_x) and np.isfinite(entry_z)):
            continue
        distance = float((next_entry_x_m - entry_x) ** 2 + (next_entry_z_m - entry_z) ** 2)
        if distance < best_distance:
            best_distance = distance
            best_cell = cell_id
    return best_cell


def _build_coverage_cells(
    by_cell: dict[int, list[dict[str, Any]]],
    record_count: int,
) -> list[dict[str, Any]]:
    coverage_cells = []
    for cell_id in range(CELL_COUNT):
        rows = by_cell.get(cell_id, [])
        if not rows:
            continue
        entry_x_values = [r["raw"]["operator_entry_x_m"] for r in rows]
        entry_z_values = [r["raw"]["operator_entry_z_m"] for r in rows]
        exit_x_values = [r["raw"]["operator_exit_x_m"] for r in rows]
        exit_z_values = [r["raw"]["operator_exit_z_m"] for r in rows]
        cut_depth_values = [r["raw"]["operator_cut_depth_peak_m"] for r in rows]
        coverage_cells.append(
            {
                "cell_id": cell_id,
                "source_count": len(rows),
                "source_fraction": round(len(rows) / max(1, record_count), 6),
                "entry": {
                    "x_m": round(
                        _percentile(entry_x_values, 50),
                        6,
                    ),
                    "z_m": round(
                        _percentile(entry_z_values, 50),
                        6,
                    ),
                },
                "exit": {
                    "x_m": round(
                        _percentile(exit_x_values, 50),
                        6,
                    ),
                    "z_m": round(
                        _percentile(exit_z_values, 50),
                        6,
                    ),
                },
                "entry_stats": {
                    "x_m": _stats_05_50_95(entry_x_values),
                    "z_m": _stats_05_50_95(entry_z_values),
                    "radial_error_m": _radial_stats_50_75_95(
                        rows,
                        x_key="operator_entry_x_m",
                        z_key="operator_entry_z_m",
                    ),
                },
                "exit_stats": {
                    "x_m": _stats_05_50_95(exit_x_values),
                    "z_m": _stats_05_50_95(exit_z_values),
                    "radial_error_m": _radial_stats_50_75_95(
                        rows,
                        x_key="operator_exit_x_m",
                        z_key="operator_exit_z_m",
                    ),
                },
                "cut_depth_peak_m": round(
                    _percentile(cut_depth_values, 50),
                    6,
                ),
                "cut_depth_peak_m_stats": _stats_05_50_95(cut_depth_values),
                "payload_gain_kg": round(
                    _percentile([r["raw"]["operator_cut_payload_gain_kg"] for r in rows], 50),
                    6,
                ),
                "effective_deposit_delta_kg": round(
                    _percentile(
                        [r["raw"]["operator_effective_deposit_delta_kg"] for r in rows],
                        50,
                    ),
                    6,
                ),
                "dig_start_plane_depth_m": _stats_05_50_95(
                    [r["start_plane_depth_m"] for r in rows]
                ),
                "dig_start_local_depth_m": _stats_05_50_95(
                    [r["start_local_depth_m"] for r in rows]
                ),
            }
        )
    return coverage_cells


def _build_return_start_envelope_prior(
    return_root: Path,
    *,
    coverage_cells: list[dict[str, Any]],
    episode_ids: Iterable[int] | None = None,
    episode_selection: dict[str, Any] | None = None,
    source_label: str = "",
) -> dict[str, Any]:
    return_tokens: list[np.ndarray] = []
    return_tokens_by_cell: dict[int, list[np.ndarray]] = defaultdict(list)
    coverage_by_cell = {int(cell["cell_id"]): cell for cell in coverage_cells}
    skipped_missing_next_entry = 0
    for path in _episode_paths(return_root, episode_ids=episode_ids):
        with h5py.File(path, "r") as handle:
            if _text_scalar(handle, "training_tier") != "gold":
                continue
            if "v2/step/return_start_envelope_tokens_v1" not in handle:
                continue
            token = np.asarray(
                handle["v2/step/return_start_envelope_tokens_v1"][0],
                dtype=np.float32,
            ).reshape(-1)
            if (
                token.size != RETURN_START_ENVELOPE_TOKEN_DIM
                or not np.all(np.isfinite(token))
                or float(token[16]) <= 0.5
            ):
                continue
            return_tokens.append(token)
            cell_id = match_return_envelope_cell_by_next_entry(
                next_entry_x_m=_scalar(handle, "next_operator_entry_x_m"),
                next_entry_z_m=_scalar(handle, "next_operator_entry_z_m"),
                coverage_cells=coverage_cells,
            )
            if cell_id is None:
                skipped_missing_next_entry += 1
                continue
            return_tokens_by_cell[int(cell_id)].append(token)

    if not return_tokens:
        return {}

    source = {
        "source_dataset": str(return_root),
        "source_count_used": len(return_tokens),
        "tier_filter": "gold",
        "match_source": RETURN_ENVELOPE_MATCH_SOURCE,
        "skipped_missing_next_entry_count": skipped_missing_next_entry,
        "notes": (
            "Cell-conditioned return-start envelope priors are grouped by "
            "the next operator entry's nearest coverage cell. The envelope "
            "token's own long/short values describe the start state and are "
            "not used as the cell assignment key."
        ),
    }
    if episode_selection is not None:
        source["episode_selection"] = dict(episode_selection)
    payload = {
        "return_start_envelope_token_contract": "return_start_envelope_tokens_v1",
        "return_start_envelope_source": source,
        "return_start_envelope_global": _token_summary(return_tokens, len(return_tokens)),
        "return_start_envelope_cells": [
            _return_envelope_cell_summary(
                cell_id=cell_id,
                tokens=tokens,
                total_count=len(return_tokens),
                coverage_cell=coverage_by_cell.get(int(cell_id), {}),
            )
            for cell_id, tokens in sorted(return_tokens_by_cell.items())
            if tokens
        ],
    }
    if source_label:
        payload["return_start_envelope_source_label"] = source_label
    return payload


def _load_gold_dig_records(
    dig_root: Path,
    *,
    episode_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _episode_paths(dig_root, episode_ids=episode_ids):
        with h5py.File(path, "r") as handle:
            if _text_scalar(handle, "training_tier") != "gold":
                continue
            raw = {
                "operator_entry_x_m": _scalar(handle, "operator_entry_x_m"),
                "operator_entry_y_m": _scalar(handle, "operator_entry_y_m"),
                "operator_entry_z_m": _scalar(handle, "operator_entry_z_m"),
                "operator_exit_x_m": _scalar(handle, "operator_exit_x_m"),
                "operator_exit_y_m": _scalar(handle, "operator_exit_y_m"),
                "operator_exit_z_m": _scalar(handle, "operator_exit_z_m"),
                "operator_cut_direction_x": _scalar(handle, "operator_cut_direction_x"),
                "operator_cut_direction_y": _scalar(handle, "operator_cut_direction_y"),
                "operator_cut_direction_z": _scalar(handle, "operator_cut_direction_z"),
                "operator_cut_length_m": _scalar(handle, "operator_cut_length_m"),
                "operator_cut_depth_peak_m": _scalar(
                    handle,
                    "operator_cut_depth_peak_m",
                ),
                "operator_cut_payload_gain_kg": _scalar(
                    handle,
                    "operator_cut_payload_gain_kg",
                ),
                "operator_effective_deposit_delta_kg": _scalar(
                    handle,
                    "cycle_effective_deposit_delta_kg",
                    _scalar(
                        handle,
                        "dig_outcome_effective_deposit_delta_kg",
                        _scalar(handle, "operator_cut_payload_gain_kg"),
                    ),
                ),
                "operator_cut_valid": int(
                    round(_scalar(handle, "operator_cut_valid", 1.0))
                ),
            }
            if not all(
                np.isfinite(float(raw[key]))
                for key in raw
                if key != "operator_cut_valid"
            ):
                continue
            env = np.asarray(handle["observations/env_state"], dtype=np.float32)
            qpos = np.asarray(handle["observations/qpos"][0], dtype=np.float32).reshape(-1)[:4]
            qvel = np.asarray(handle["observations/qvel"][0], dtype=np.float32).reshape(-1)[:4]
            profile_token = None
            if "v2/step/dig_depth_profile_tokens_v1" in handle:
                profile_token = np.asarray(
                    handle["v2/step/dig_depth_profile_tokens_v1"][0],
                    dtype=np.float32,
                ).reshape(-1)
            records.append(
                {
                    "path": path,
                    "cell_id": int(
                        np.clip(round(_scalar(handle, "dominant_removed_depth_cell_id", 0)), 0, 5)
                    ),
                    "raw": raw,
                    "start_removed_depth_grid_m": env[
                        0,
                        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX :
                        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + CELL_COUNT,
                    ].astype(float).tolist(),
                    "start_target_depth_grid_m": env[
                        0,
                        ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX :
                        ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + CELL_COUNT,
                    ].astype(float).tolist(),
                    "start_plane_depth_m": _env_scalar(
                        env,
                        ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
                    ),
                    "start_local_depth_m": _env_scalar(
                        env,
                        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
                    ),
                    "start_qpos": qpos.astype(float).tolist(),
                    "start_qvel": qvel.astype(float).tolist(),
                    "profile_token": (
                        None if profile_token is None else profile_token.astype(float).tolist()
                    ),
                    "source_length": int(
                        handle["action"].shape[0]
                        if "action" in handle
                        else handle["actions"].shape[0]
                    ),
                    "peak_bucket_mass_kg": _scalar(
                        handle,
                        "dig_peak_bucket_mass_kg",
                        _scalar(handle, "operator_cut_payload_gain_kg"),
                    ),
                }
            )
    return records


def _build_state_exemplar_payload(
    records: list[dict[str, Any]],
    by_cell: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    exemplars = []
    for record in records:
        raw = dict(record["raw"])
        exemplar = {
            "exemplar_id": record["path"].stem,
            "source_episode": record["path"].name,
            "source_length": record["source_length"],
            "cell_id": record["cell_id"],
            "peak_bucket_mass_kg": round(float(record["peak_bucket_mass_kg"]), 6),
            "raw_fields": {
                key: (
                    int(value)
                    if key == "operator_cut_valid"
                    else round(float(value), 6)
                )
                for key, value in raw.items()
            },
            "start_removed_depth_grid_m": [
                round(float(value), 6)
                for value in record["start_removed_depth_grid_m"]
            ],
            "start_target_depth_grid_m": [
                round(float(value), 6)
                for value in record["start_target_depth_grid_m"]
            ],
            "start_qpos": [round(float(value), 6) for value in record["start_qpos"]],
            "start_qvel": [round(float(value), 6) for value in record["start_qvel"]],
        }
        if record["profile_token"] is not None:
            exemplar["dig_depth_profile_token"] = [
                round(float(value), 6) for value in record["profile_token"]
            ]
        exemplars.append(exemplar)
    return {
        "exemplar_count": len(exemplars),
        "cell_summary": {
            str(cell_id): {"count": len(by_cell.get(cell_id, []))}
            for cell_id in range(CELL_COUNT)
        },
        "distance_contract": {
            "state_vector": "env_state removed_depth grid cells 0..5 at dig primitive start",
            "raw_fields_contract": "v2_4_removed_depth_cut_v3",
            "raw_fields_depth_semantic": "bucket_depth_below_local_surface_peak_m",
            "default_removed_depth_scale_m": 0.12,
            "default_target_cell_weight": 2.0,
        },
        "exemplars": exemplars,
    }


def _token_summary(tokens: list[np.ndarray], total_count: int) -> dict[str, Any]:
    stacked = np.stack(tokens, axis=0)
    return {
        "source_count": int(stacked.shape[0]),
        "source_fraction": round(float(stacked.shape[0] / max(1, total_count)), 6),
        "token_median": np.percentile(stacked, 50, axis=0).round(6).astype(float).tolist(),
        "token_p05": np.percentile(stacked, 5, axis=0).round(6).astype(float).tolist(),
        "token_p95": np.percentile(stacked, 95, axis=0).round(6).astype(float).tolist(),
    }


def _return_envelope_cell_summary(
    *,
    cell_id: int,
    tokens: list[np.ndarray],
    total_count: int,
    coverage_cell: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "cell_id": int(cell_id),
        "match_source": RETURN_ENVELOPE_MATCH_SOURCE,
        **_token_summary(tokens, total_count),
    }
    for key in ("dig_start_plane_depth_m", "dig_start_local_depth_m"):
        stats = coverage_cell.get(key)
        if isinstance(stats, dict):
            summary[key] = dict(stats)
    return summary


def _env_scalar(env: np.ndarray, index: int) -> float:
    if env.ndim != 2 or env.shape[0] <= 0 or env.shape[1] <= index:
        return 0.0
    value = float(env[0, index])
    return value if np.isfinite(value) else 0.0


def _episode_paths(
    path: Path,
    *,
    episode_ids: Iterable[int] | None = None,
) -> list[Path]:
    available = {
        int(candidate.stem.split("_")[-1]): candidate
        for candidate in path.glob("episode_*.hdf5")
    }
    if episode_ids is None:
        selected_ids = sorted(available)
    else:
        selected_ids = sorted({int(value) for value in episode_ids})
        missing = [episode_id for episode_id in selected_ids if episode_id not in available]
        if missing:
            raise FileNotFoundError(
                f"selected primitive episodes missing from {path}: {missing}"
            )
    return [available[episode_id] for episode_id in selected_ids]


def load_split_episode_ids(
    split_path: str | Path,
    *,
    partition: str,
) -> tuple[tuple[int, ...], dict[str, Any]]:
    """Load an exact primitive episode partition with overlap checks."""

    path = Path(split_path)
    if partition not in {"train", "val"}:
        raise ValueError(f"unsupported split partition: {partition}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"split payload must be a mapping: {path}")
    train_ids = tuple(int(value) for value in payload.get("train_ids", []))
    val_ids = tuple(int(value) for value in payload.get("val_ids", []))
    if len(set(train_ids)) != len(train_ids) or len(set(val_ids)) != len(val_ids):
        raise ValueError(f"split_partition_duplicates:{path}")
    overlap = sorted(set(train_ids) & set(val_ids))
    if overlap:
        raise ValueError(f"split_partition_overlap:{path}:{overlap}")
    selected = train_ids if partition == "train" else val_ids
    if not selected:
        raise ValueError(f"split_partition_empty:{path}:{partition}")
    return selected, {
        "split_path": str(path.resolve()),
        "partition": partition,
        "primitive_episode_count": len(selected),
        "split_policy": str(payload.get("split_policy", "")),
    }


def write_surface_depth_planner_prior_outputs(
    *,
    prior: dict[str, Any],
    state_payload: dict[str, Any],
    prior_path: str | Path,
    state_exemplar_path: str | Path,
) -> None:
    """Write generated artifacts once; existing outputs are never replaced."""

    prior_output = Path(prior_path)
    state_output = Path(state_exemplar_path)
    existing = [path for path in (prior_output, state_output) if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite surface-depth planner artifacts: "
            + ", ".join(str(path) for path in existing)
        )
    prior_output.parent.mkdir(parents=True, exist_ok=True)
    state_output.parent.mkdir(parents=True, exist_ok=True)
    with prior_output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(_jsonable(prior), indent=2, sort_keys=True) + "\n")
    with state_output.open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(_jsonable(state_payload), indent=2, sort_keys=True) + "\n"
        )


def _scalar(handle: h5py.File, name: str, default: float = float("nan")) -> float:
    if "metadata" in handle and name in handle["metadata"].attrs:
        try:
            return float(handle["metadata"].attrs[name])
        except Exception:
            pass
    path = f"v2/cycle/{name}"
    if path in handle and handle[path].shape[0] > 0:
        try:
            return float(handle[path][0])
        except Exception:
            pass
    return float(default)


def _text_scalar(handle: h5py.File, name: str, default: str = "") -> str:
    if "metadata" in handle and name in handle["metadata"].attrs:
        return _h5_text(handle["metadata"].attrs[name])
    path = f"v2/cycle/{name}"
    if path in handle and handle[path].shape[0] > 0:
        return _h5_text(handle[path][0])
    return default


def _h5_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return _h5_text(value.item())
        except Exception:
            pass
    return str(value)


def _percentile(values: list[float], q: float) -> float:
    arr = np.asarray(values, dtype=np.float32)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0
    return float(np.percentile(arr, q))


def _stats(values: list[float]) -> dict[str, float]:
    return {
        key: round(_percentile(values, q), 6)
        for key, q in (("p10", 10), ("p50", 50), ("p90", 90))
    }


def _stats_05_50_95(values: list[float]) -> dict[str, float]:
    return {
        key: round(_percentile(values, q), 6)
        for key, q in (("p05", 5), ("p50", 50), ("p95", 95))
    }


def _radial_stats_50_75_95(
    rows: list[dict[str, Any]],
    *,
    x_key: str,
    z_key: str,
) -> dict[str, float]:
    xs = [float(row["raw"][x_key]) for row in rows]
    zs = [float(row["raw"][z_key]) for row in rows]
    center_x = _percentile(xs, 50)
    center_z = _percentile(zs, 50)
    distances = [
        float(np.hypot(float(x) - center_x, float(z) - center_z))
        for x, z in zip(xs, zs, strict=False)
    ]
    return {
        key: round(_percentile(distances, q), 6)
        for key, q in (("p50", 50), ("p75", 75), ("p95", 95))
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


if __name__ == "__main__":
    main()
