"""Strict-train coverage execution exemplars and supervision-tail evidence.

This module owns an offline data artifact.  It deliberately keeps hindsight
effect labels separate from stable exemplar identities: ``effect_outcome_cell_id``
is a six-cell outcome label, while ``corridor_id`` is an append-only numeric
identity in a disjoint range.  Online candidate selection remains planner-owned.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
)
from testbed.data.schema import (
    DS_ACTION,
    DS_ENV_STATE,
    DS_V2_STEP_ACTION_LOSS_MASK,
    DS_V2_STEP_DIG_CUT_TOKENS,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.planner.primitive.coverage.swept_cells import (
    CoverageSweptFootprint,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
    CoverageWallGeometry,
)

COVERAGE_EXECUTION_LIBRARY_SCHEMA = (
    "strict_train_coverage_execution_library_v1_1"
)
STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT = 374
CORRIDOR_ID_BASE = 1_000_000
REMOVED_DEPTH_SCALE_M = 0.12
TARGET_CELL_WEIGHT = 2.0
SOURCE_ENV_STATE_CONTRACT = "agx_env_state_v2_3_89"
SOURCE_ENV_STATE_DIM = 89
LIVE_ENV_STATE_CONTRACT = "agx_env_state_v2_4_107"
LIVE_WORKTOOL_WIDTH_M = 0.70

_FORBIDDEN_PATH_MARKERS = ("partial", "layered", "salvage")
_STRICT_EVIDENCE_KINDS = (
    "strict_parent_selected_replay",
    # These rows were admitted into the final strict composite and therefore
    # remain strict records.  The builder still rejects a partial/layered/
    # salvage *input view*.
    "strict_salvage_addition",
)
_RAW_FIELD_NAMES = (
    "operator_entry_x_m",
    "operator_entry_y_m",
    "operator_entry_z_m",
    "operator_exit_x_m",
    "operator_exit_y_m",
    "operator_exit_z_m",
    "operator_cut_direction_x",
    "operator_cut_direction_y",
    "operator_cut_direction_z",
    "operator_cut_length_m",
    "operator_cut_depth_peak_m",
    "operator_cut_payload_gain_kg",
    "operator_effective_deposit_delta_kg",
    "operator_cut_valid",
)


def build_coverage_execution_library(
    *,
    dig_primitives_dir: str | Path,
    split_path: str | Path,
    output_path: str | Path,
    coverage_prior_path: str | Path | None = None,
) -> Path:
    """Build the immutable strict-train coverage execution library.

    Only the exact 374-row strict train partition is read.  Validation
    primitives and alternate partial/layered/salvage views are rejected before
    any output is created.
    """

    output = Path(output_path).expanduser().resolve()
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite coverage execution library: {output}"
        )

    dig_root = _validated_input_path(
        dig_primitives_dir,
        label="dig primitive directory",
        require_dir=True,
    )
    if dig_root.name != "dig" or dig_root.parent.name != "primitives_copy":
        raise ValueError(
            "Strict coverage execution input must be primitives_copy/dig: "
            f"{dig_root}"
        )
    split = _validated_input_path(
        split_path,
        label="dig source split",
        require_dir=False,
    )
    split_bytes = split.read_bytes()
    split_payload = yaml.safe_load(split_bytes)
    if not isinstance(split_payload, Mapping):
        raise ValueError(f"Dig source split must be a mapping: {split}")
    split_contract = _validate_split(
        split_payload,
        dig_primitives_dir=dig_root,
    )

    prior_geometry, prior_lock = _load_prior_geometry(coverage_prior_path)
    input_digest = hashlib.sha256()
    input_digest.update(f"{COVERAGE_EXECUTION_LIBRARY_SCHEMA}\0".encode())
    input_digest.update(hashlib.sha256(split_bytes).digest())
    if prior_lock is not None:
        input_digest.update(bytes.fromhex(str(prior_lock["sha256"])))

    records: list[dict[str, Any]] = []
    geometry_rows: list[dict[str, Any]] = []
    evidence_kind_counts: Counter[str] = Counter()
    source_mapping = split_contract["source_episode_id_by_primitive_episode_id"]
    for primitive_episode_id in split_contract["train_ids"]:
        source_episode_id = int(source_mapping[int(primitive_episode_id)])
        primitive_path = dig_root / f"episode_{primitive_episode_id}.hdf5"
        record, evidence_kind, geometry_row = _read_primitive(
            primitive_path,
            primitive_episode_id=int(primitive_episode_id),
            expected_source_episode_id=source_episode_id,
            prior_geometry=prior_geometry,
        )
        records.append(record)
        geometry_rows.append(geometry_row)
        evidence_kind_counts[evidence_kind] += 1
        input_digest.update(
            (
                f"episode_{primitive_episode_id}\0"
                f"source_{source_episode_id}\0"
            ).encode()
        )
        input_digest.update(bytes.fromhex(str(record["source_sha256"])))

    records.sort(key=lambda item: int(item["primitive_episode_id"]))
    cell_summary = _annotate_leave_one_out(records)
    tail_audit = _tail_audit(records)
    tuple_audit = _tuple_consistency_audit(records)
    geometry_contract = _geometry_contract(geometry_rows)

    source_lineage = {
        "partition": "train",
        "split_path": str(split),
        "split_policy": "source_identity_exact_allowlist_v1",
        "dataset_dir": str(dig_root),
        "train_primitive_episode_ids": list(split_contract["train_ids"]),
        "train_source_episode_ids": list(
            STRICT18_TRAIN_SOURCE_EPISODE_IDS
        ),
        "validation_primitive_episode_ids": list(split_contract["val_ids"]),
        "validation_source_episode_ids": list(
            STRICT18_VALIDATION_SOURCE_EPISODE_IDS
        ),
        "source_episode_id_by_primitive_episode_id": {
            str(primitive_episode_id): int(source_mapping[primitive_episode_id])
            for primitive_episode_id in split_contract["train_ids"]
        },
        "strict_evidence_kind_counts": dict(
            sorted(evidence_kind_counts.items())
        ),
        "validation_rows_read": 0,
        "partial_layered_salvage_input_views_allowed": False,
    }
    source_lock: dict[str, Any] = {
        "split": {
            "path": str(split),
            "sha256": hashlib.sha256(split_bytes).hexdigest(),
        },
        "coverage_prior": prior_lock,
        "input_sha256_contract": (
            "sha256(schema_nul + split_sha256_bytes + optional_prior_sha256_bytes "
            "+ ordered primitive/source ids + full primitive file sha256 bytes)"
        ),
        "input_sha256": input_digest.hexdigest(),
        "manifest_sha256": input_digest.hexdigest(),
    }
    artifact: dict[str, Any] = {
        "schema": COVERAGE_EXECUTION_LIBRARY_SCHEMA,
        "status": "completed",
        "sample_count": len(records),
        "env_state_contract": LIVE_ENV_STATE_CONTRACT,
        "source_contract": {
            "env_state_contract": SOURCE_ENV_STATE_CONTRACT,
            "env_state_dim": SOURCE_ENV_STATE_DIM,
            "primitive_name": "dig",
            "primitive_storage_mode": "copy",
            "training_tier": "gold",
            "dig_cut_token_contract": "v2_4_removed_depth_cut_v3",
            "dig_cut_token_dim": DIG_CUT_TOKEN_DIM,
        },
        "live_selection_contract": {
            "requires_env_state": LIVE_ENV_STATE_CONTRACT,
            "geometry_profile": (
                "conservative_2d_worktool_swept_footprint_v1"
            ),
            "worktool_width_m": LIVE_WORKTOOL_WIDTH_M,
            "removed_depth_scale_m": REMOVED_DEPTH_SCALE_M,
            "target_cell_weight": TARGET_CELL_WEIGHT,
            "strict_library_env_state_is_replay_89d": True,
        },
        "geometry_contract": geometry_contract,
        "corridor_id_contract": {
            "base": CORRIDOR_ID_BASE,
            "formula": "1000000 + primitive_episode_id",
            "legacy_outcome_cell_id_range": [0, 5],
            "purpose": (
                "stable exemplar corridor identity disjoint from outcome cells"
            ),
        },
        "return_envelope_mapping_contract": {
            "available": prior_geometry is not None,
            "source": (
                None
                if prior_geometry is None
                else "nearest_prior_coverage_cell_by_operator_entry"
            ),
            "missing_value": None,
        },
        "distance_contract": {
            "state_vector": "start_removed_depth_grid_m cells 0..5",
            "distance": (
                "sqrt(mean(weighted((query-reference)/scale)^2))"
            ),
            "removed_depth_scale_m": REMOVED_DEPTH_SCALE_M,
            "target_cell_weight": TARGET_CELL_WEIGHT,
            "target_cell": "effect_outcome_cell_id",
            "leave_one_out": True,
            "tie_break": "distance_then_primitive_episode_id",
        },
        "tuple_consistency_contract": {
            "formula": (
                "norm((exit_xyz-entry_xyz)-direction_xyz*cut_length_m)"
            ),
            "unit": "m",
        },
        "tail_audit": tail_audit,
        "tuple_consistency_audit": tuple_audit,
        "cell_summary": cell_summary,
        "source_lineage": source_lineage,
        "source_lock": source_lock,
        "records": records,
    }
    if len(records) != STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT:
        raise AssertionError(
            "Strict coverage execution library row count changed after load."
        )
    rendered = json.dumps(
        _jsonable(artifact),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
    return output


def cut_tuple_consistency_residual_m(
    raw_fields: Mapping[str, Any],
) -> float:
    """Return the geometric residual inside one entry/exit/direction tuple."""

    entry = np.asarray(
        [
            _finite_mapping_float(raw_fields, "operator_entry_x_m"),
            _finite_mapping_float(raw_fields, "operator_entry_y_m"),
            _finite_mapping_float(raw_fields, "operator_entry_z_m"),
        ],
        dtype=np.float64,
    )
    exit_point = np.asarray(
        [
            _finite_mapping_float(raw_fields, "operator_exit_x_m"),
            _finite_mapping_float(raw_fields, "operator_exit_y_m"),
            _finite_mapping_float(raw_fields, "operator_exit_z_m"),
        ],
        dtype=np.float64,
    )
    direction = np.asarray(
        [
            _finite_mapping_float(raw_fields, "operator_cut_direction_x"),
            _finite_mapping_float(raw_fields, "operator_cut_direction_y"),
            _finite_mapping_float(raw_fields, "operator_cut_direction_z"),
        ],
        dtype=np.float64,
    )
    length_m = _finite_mapping_float(raw_fields, "operator_cut_length_m")
    return float(np.linalg.norm((exit_point - entry) - direction * length_m))


def evaluate_coverage_execution_query(
    artifact: Mapping[str, Any],
    *,
    effect_outcome_cell_id: int,
    start_removed_depth_grid_m: Sequence[float],
    raw_fields: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one query against the locked strict execution support."""

    if str(artifact.get("schema", "")) != COVERAGE_EXECUTION_LIBRARY_SCHEMA:
        raise ValueError("Coverage execution query requires the v1 library.")
    cell_id = _cell_id(effect_outcome_cell_id, label="effect outcome cell")
    query_grid = _finite_grid(start_removed_depth_grid_m)
    records = artifact.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("Coverage execution library records must be a sequence.")
    candidates = [
        item
        for item in records
        if isinstance(item, Mapping)
        and int(item.get("effect_outcome_cell_id", -1)) == cell_id
    ]
    if not candidates:
        raise ValueError(
            f"Coverage execution library has no outcome cell {cell_id} records."
        )
    scored = [
        (
            _removed_depth_distance(
                query_grid,
                _finite_grid(item.get("start_removed_depth_grid_m", [])),
                target_cell_id=cell_id,
            ),
            int(item.get("primitive_episode_id", -1)),
            item,
        )
        for item in candidates
    ]
    scored.sort(key=lambda item: (item[0], item[1]))
    distance, _, selected = scored[0]

    cell_summary = artifact.get("cell_summary")
    if not isinstance(cell_summary, Mapping):
        raise ValueError("Coverage execution library lacks cell_summary.")
    summary = cell_summary.get(str(cell_id))
    if not isinstance(summary, Mapping):
        raise ValueError(f"Coverage execution library lacks cell {cell_id} summary.")
    tuple_audit = artifact.get("tuple_consistency_audit")
    if not isinstance(tuple_audit, Mapping):
        raise ValueError("Coverage execution library lacks tuple audit.")
    residual_stats = tuple_audit.get("residual_m")
    if not isinstance(residual_stats, Mapping):
        raise ValueError("Coverage execution library tuple audit is malformed.")

    tuple_residual = cut_tuple_consistency_residual_m(raw_fields)
    state_p99 = _finite_mapping_float(
        summary,
        "leave_one_out_nearest_neighbor_distance_p99",
    )
    global_tuple_p99 = _finite_mapping_float(residual_stats, "p99")
    cell_tuple_p99 = _finite_mapping_float(
        summary,
        "tuple_consistency_residual_p99_m",
    )
    selected_raw = selected.get("raw_fields")
    if not isinstance(selected_raw, Mapping):
        raise ValueError("Selected coverage execution exemplar lacks raw_fields.")
    raw_residuals = {
        name: (
            int(
                round(
                    _finite_mapping_float(raw_fields, name)
                    - _finite_mapping_float(selected_raw, name)
                )
            )
            if name == "operator_cut_valid"
            else float(
                _finite_mapping_float(raw_fields, name)
                - _finite_mapping_float(selected_raw, name)
            )
        )
        for name in _RAW_FIELD_NAMES
    }
    return {
        "effect_outcome_cell_id": cell_id,
        "nearest_exemplar_id": str(selected.get("exemplar_id", "")),
        "nearest_primitive_episode_id": int(
            selected.get("primitive_episode_id", -1)
        ),
        "nearest_corridor_id": int(selected.get("corridor_id", -1)),
        "nearest_return_envelope_cell_id": selected.get(
            "return_envelope_cell_id"
        ),
        "removed_depth_distance": float(distance),
        "removed_depth_distance_p99": float(state_p99),
        "removed_depth_in_support": bool(distance <= state_p99),
        "tuple_consistency_residual_m": float(tuple_residual),
        "tuple_consistency_residual_p99_m": float(global_tuple_p99),
        "outcome_cell_tuple_consistency_residual_p99_m": float(
            cell_tuple_p99
        ),
        "tuple_consistency_in_global_support": bool(
            tuple_residual <= global_tuple_p99
        ),
        "tuple_consistency_in_outcome_cell_support": bool(
            tuple_residual <= cell_tuple_p99
        ),
        "raw_field_residuals_from_nearest_exemplar": raw_residuals,
    }


def _validate_split(
    payload: Mapping[str, Any],
    *,
    dig_primitives_dir: Path,
) -> dict[str, Any]:
    dataset_dir = _validated_input_path(
        payload.get("dataset_dir"),
        label="split dataset_dir",
        require_dir=True,
    )
    if dataset_dir != dig_primitives_dir:
        raise ValueError(
            "Dig source split dataset_dir does not match requested primitive "
            f"directory: split={dataset_dir}, requested={dig_primitives_dir}"
        )
    if str(payload.get("split_policy", "")) != (
        "source_identity_exact_allowlist_v1"
    ):
        raise ValueError("Unexpected dig source split policy.")
    if str(payload.get("required_training_tier", "")) != "gold":
        raise ValueError("Strict coverage execution library requires gold rows.")

    train_ids = _unique_ids(payload.get("train_ids"), label="train_ids")
    val_ids = _unique_ids(payload.get("val_ids"), label="val_ids")
    if set(train_ids) & set(val_ids):
        raise ValueError("Dig source split train/validation ids overlap.")
    if len(train_ids) != STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT:
        raise ValueError(
            "Strict-18 dig train partition must contain exactly "
            f"{STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT} primitives; "
            f"got {len(train_ids)}."
        )

    train_sources = _unique_ids(
        payload.get("train_source_episode_ids"),
        label="train_source_episode_ids",
    )
    val_sources = _unique_ids(
        payload.get("val_source_episode_ids"),
        label="val_source_episode_ids",
    )
    allowed_sources = _unique_ids(
        payload.get("allowed_source_episode_ids"),
        label="allowed_source_episode_ids",
    )
    if train_sources != STRICT18_TRAIN_SOURCE_EPISODE_IDS:
        raise ValueError(
            "Strict-18 train source allowlist mismatch: "
            f"observed={list(train_sources)}"
        )
    if val_sources != STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
        raise ValueError(
            "Strict-18 validation source allowlist must be [33, 34]."
        )
    expected_allowed = tuple(sorted((*train_sources, *val_sources)))
    if allowed_sources != expected_allowed:
        raise ValueError(
            "Strict-18 allowed sources must equal train+validation sources."
        )

    source_mapping = _source_mapping(
        payload.get("source_episode_id_by_primitive_episode_id")
    )
    missing = sorted(set((*train_ids, *val_ids)) - source_mapping.keys())
    if missing:
        raise ValueError(
            "Dig source split is missing primitive source identities: "
            f"{missing}"
        )
    validation_leaks = [
        primitive_id
        for primitive_id in train_ids
        if source_mapping[primitive_id] in set(val_sources)
    ]
    if validation_leaks:
        raise ValueError(
            "Strict train partition contains a validation source: "
            f"{validation_leaks}"
        )
    observed_train_sources = tuple(
        sorted({source_mapping[primitive_id] for primitive_id in train_ids})
    )
    if observed_train_sources != train_sources:
        raise ValueError(
            "Strict train primitives do not exactly cover the 16-source "
            f"allowlist: observed={list(observed_train_sources)}"
        )
    observed_val_sources = tuple(
        sorted({source_mapping[primitive_id] for primitive_id in val_ids})
    )
    if observed_val_sources != val_sources:
        raise ValueError(
            "Validation primitives do not exactly cover sources 33/34."
        )
    return {
        "train_ids": train_ids,
        "val_ids": val_ids,
        "source_episode_id_by_primitive_episode_id": source_mapping,
    }


def _read_primitive(
    path: Path,
    *,
    primitive_episode_id: int,
    expected_source_episode_id: int,
    prior_geometry: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Strict dig primitive does not exist: {path}")
    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if not isinstance(metadata, h5py.Group):
            raise ValueError(f"Dig primitive is missing metadata: {path}")
        _expect_metadata_text(metadata, "primitive_name", "dig", path)
        _expect_metadata_text(metadata, "training_tier", "gold", path)
        _expect_metadata_text(metadata, "storage_mode", "copy", path)
        _expect_metadata_text(
            metadata,
            "composite_view_kind",
            "combined_strict_clean_vds",
            path,
        )
        evidence_kind = _expect_metadata_text_one_of(
            metadata,
            "composite_evidence_kind",
            _STRICT_EVIDENCE_KINDS,
            path,
        )
        _expect_metadata_text(
            metadata,
            "source_episode_id",
            f"episode_{expected_source_episode_id}",
            path,
        )
        _expect_metadata_text(
            metadata,
            "env_state_contract_version",
            SOURCE_ENV_STATE_CONTRACT,
            path,
        )

        env_state = _required_matrix(
            handle,
            DS_ENV_STATE,
            width=SOURCE_ENV_STATE_DIM,
            path=path,
        )
        action = _required_matrix(
            handle,
            DS_ACTION,
            width=4,
            path=path,
        )
        if action.shape[0] != env_state.shape[0]:
            raise ValueError(f"Dig primitive action/env length mismatch: {path}")
        step_count = int(action.shape[0])
        mask = _required_vector(
            handle,
            DS_V2_STEP_ACTION_LOSS_MASK,
            length=step_count,
            path=path,
            dtype=np.uint8,
        )
        if np.any((mask != 0) & (mask != 1)) or not np.any(mask == 1):
            raise ValueError(
                f"Dig primitive action-loss mask must be binary and nonempty: {path}"
            )
        tokens = _required_matrix(
            handle,
            DS_V2_STEP_DIG_CUT_TOKENS,
            width=DIG_CUT_TOKEN_DIM,
            path=path,
        )
        if tokens.shape[0] != step_count:
            raise ValueError(f"Dig primitive token length mismatch: {path}")
        if not np.allclose(tokens, tokens[0], rtol=0.0, atol=1.0e-6):
            raise ValueError(f"Dig primitive must contain one fixed token: {path}")

        raw_fields = _raw_fields(handle)
        expected_token = _token_from_raw_fields(raw_fields)
        if not np.allclose(
            tokens[0],
            expected_token,
            rtol=0.0,
            atol=2.0e-6,
        ):
            raise ValueError(
                f"Dig primitive token disagrees with complete raw fields: {path}"
            )
        outcome_cell_id = _cell_id(
            round(_scalar(handle, "dominant_removed_depth_cell_id")),
            label="effect outcome cell",
        )
        removed_grid = _finite_grid(
            env_state[
                0,
                ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX:
                ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 6,
            ]
        )
        geometry = CoverageWallGeometry.from_env_state(env_state[0])
        footprint = CoverageSweptFootprint.from_segment(
            geometry=geometry,
            entry_x_m=float(raw_fields["operator_entry_x_m"]),
            entry_z_m=float(raw_fields["operator_entry_z_m"]),
            exit_x_m=float(raw_fields["operator_exit_x_m"]),
            exit_z_m=float(raw_fields["operator_exit_z_m"]),
            worktool_width_m=LIVE_WORKTOOL_WIDTH_M,
        )
        token_peak_index = _token_peak_local_index(
            handle,
            env_state=env_state,
            raw_depth_m=float(raw_fields["operator_cut_depth_peak_m"]),
            path=path,
        )
        valid_indices = np.flatnonzero(mask == 1)
        tail_indices = valid_indices[valid_indices >= token_peak_index]
        plane_depth = env_state[
            :,
            ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
        ].astype(np.float64)
        local_depth = env_state[
            :,
            ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        ].astype(np.float64)
        if not (
            np.all(np.isfinite(plane_depth[valid_indices]))
            and np.all(np.isfinite(local_depth[valid_indices]))
        ):
            raise ValueError(f"Dig primitive depth evidence is non-finite: {path}")
        plane_tail_reserve = (
            0.0
            if tail_indices.size == 0
            else max(
                0.0,
                float(
                    np.max(plane_depth[tail_indices])
                    - plane_depth[token_peak_index]
                ),
            )
        )
        local_max_minus_token = max(
            0.0,
            float(
                np.max(local_depth[valid_indices])
                - float(raw_fields["operator_cut_depth_peak_m"])
            ),
        )

    source_sha256 = _sha256(path)
    return_envelope_cell_id = _return_envelope_cell_id(
        raw_fields,
        prior_geometry=prior_geometry,
    )
    record = {
        "exemplar_id": f"episode_{primitive_episode_id}",
        "primitive_episode_id": int(primitive_episode_id),
        "source_episode_id": int(expected_source_episode_id),
        "effect_outcome_cell_id": int(outcome_cell_id),
        "corridor_id": int(CORRIDOR_ID_BASE + primitive_episode_id),
        "return_envelope_cell_id": return_envelope_cell_id,
        "raw_fields": raw_fields,
        "dig_cut_tokens": [float(value) for value in tokens[0]],
        "start_removed_depth_grid_m": [
            float(value) for value in removed_grid
        ],
        "token_peak_local_index": int(token_peak_index),
        "execution_tail_action_loss_valid_count": int(tail_indices.size),
        "execution_tail_plane_depth_reserve_m": float(plane_tail_reserve),
        "local_max_minus_token_m": float(local_max_minus_token),
        "tuple_consistency_residual_m": float(
            cut_tuple_consistency_residual_m(raw_fields)
        ),
        "expected_centerline_physical_cell_ids": [
            int(value) for value in footprint.centerline_cell_ids
        ],
        "expected_swept_physical_cell_ids": [
            int(value) for value in footprint.swept_cell_ids
        ],
        "source_sha256": source_sha256,
    }
    geometry_row = {
        "long_axis": int(geometry.long_axis),
        "grid_long_count": int(geometry.grid_long_count),
        "grid_short_count": int(geometry.grid_short_count),
        "cell_long_size_m": float(geometry.cell_long_size_m),
        "cell_short_size_m": float(geometry.cell_short_size_m),
    }
    return record, evidence_kind, geometry_row


def _token_peak_local_index(
    handle: h5py.File,
    *,
    env_state: np.ndarray,
    raw_depth_m: float,
    path: Path,
) -> int:
    source_start = int(round(_scalar(handle, "source_start_step")))
    operator_entry = int(round(_scalar(handle, "operator_entry_step")))
    operator_exit = int(round(_scalar(handle, "operator_exit_step")))
    if operator_exit < operator_entry:
        raise ValueError(f"Dig primitive operator window is reversed: {path}")
    local_start = max(0, operator_entry - source_start)
    local_end = min(int(env_state.shape[0]) - 1, operator_exit - source_start)
    if local_end < local_start:
        raise ValueError(
            f"Dig primitive operator window misses primitive rows: {path}"
        )
    candidates = np.flatnonzero(
        (np.arange(env_state.shape[0]) >= local_start)
        & (np.arange(env_state.shape[0]) <= local_end)
    )
    if candidates.size == 0:
        raise ValueError(
            f"Dig primitive has no token-window rows: {path}"
        )
    local_depth = env_state[
        :,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ].astype(np.float64)
    values = local_depth[candidates]
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Dig primitive token-window depth is non-finite: {path}")
    peak_index = int(candidates[int(np.argmax(values))])
    observed_peak = float(local_depth[peak_index])
    if not np.isclose(
        observed_peak,
        float(raw_depth_m),
        rtol=0.0,
        atol=2.0e-4,
    ):
        raise ValueError(
            "Dig primitive token depth does not equal operator-window peak: "
            f"token={raw_depth_m}, observed={observed_peak}, path={path}"
        )
    return peak_index


def _annotate_leave_one_out(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_cell: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_cell[int(record["effect_outcome_cell_id"])].append(record)
    if set(by_cell) != set(range(6)):
        raise ValueError(
            "Strict execution library must cover all six outcome cells."
        )

    summary: dict[str, dict[str, Any]] = {}
    for cell_id in range(6):
        rows = sorted(
            by_cell[cell_id],
            key=lambda item: int(item["primitive_episode_id"]),
        )
        if len(rows) < 2:
            raise ValueError(
                f"Outcome cell {cell_id} needs at least two LOO exemplars."
            )
        distances: list[float] = []
        for query in rows:
            query_grid = _finite_grid(query["start_removed_depth_grid_m"])
            candidates: list[tuple[float, int, dict[str, Any]]] = []
            for reference in rows:
                if int(reference["primitive_episode_id"]) == int(
                    query["primitive_episode_id"]
                ):
                    continue
                distance = _removed_depth_distance(
                    query_grid,
                    _finite_grid(reference["start_removed_depth_grid_m"]),
                    target_cell_id=cell_id,
                )
                candidates.append(
                    (
                        distance,
                        int(reference["primitive_episode_id"]),
                        reference,
                    )
                )
            candidates.sort(key=lambda item: (item[0], item[1]))
            distance, _, nearest = candidates[0]
            distances.append(float(distance))
            query["leave_one_out_nearest_neighbor"] = {
                "exemplar_id": str(nearest["exemplar_id"]),
                "primitive_episode_id": int(
                    nearest["primitive_episode_id"]
                ),
                "corridor_id": int(nearest["corridor_id"]),
                "distance": float(distance),
            }
        distance_p99 = _percentile(distances, 99)
        tuple_residuals = [
            float(row["tuple_consistency_residual_m"]) for row in rows
        ]
        tuple_p99 = _percentile(tuple_residuals, 99)
        for row in rows:
            row["outcome_cell_loo_nearest_distance_p99"] = float(
                distance_p99
            )
        summary[str(cell_id)] = {
            "sample_count": len(rows),
            "leave_one_out_nearest_neighbor_distance": _stats(distances),
            "leave_one_out_nearest_neighbor_distance_p99": float(
                distance_p99
            ),
            "tuple_consistency_residual_m": _stats(tuple_residuals),
            "tuple_consistency_residual_p99_m": float(tuple_p99),
        }
    return summary


def _removed_depth_distance(
    query: np.ndarray,
    reference: np.ndarray,
    *,
    target_cell_id: int,
) -> float:
    diff = (
        np.asarray(query, dtype=np.float64).reshape(6)
        - np.asarray(reference, dtype=np.float64).reshape(6)
    ) / REMOVED_DEPTH_SCALE_M
    diff[int(target_cell_id)] *= TARGET_CELL_WEIGHT
    return float(np.sqrt(np.mean(np.square(diff))))


def _tail_audit(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    local = [float(item["local_max_minus_token_m"]) for item in records]
    plane = [
        float(item["execution_tail_plane_depth_reserve_m"])
        for item in records
    ]
    count = sum(value > 0.02 for value in local)
    return {
        "sample_count": len(records),
        "local_max_minus_token_threshold_m": 0.02,
        "local_max_minus_token_gt_0_02_count": int(count),
        "local_max_minus_token_gt_0_02_fraction": float(
            count / max(1, len(records))
        ),
        "local_max_minus_token_m": _stats(local),
        "execution_tail_plane_depth_reserve_m": _stats(plane),
    }


def _tuple_consistency_audit(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    residuals = [
        float(item["tuple_consistency_residual_m"]) for item in records
    ]
    return {
        "sample_count": len(records),
        "residual_m": _stats(residuals),
    }


def _geometry_contract(
    geometry_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(geometry_rows) != STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT:
        raise ValueError(
            "Coverage geometry evidence must contain exactly 374 rows."
        )
    field_names = (
        "long_axis",
        "grid_long_count",
        "grid_short_count",
        "cell_long_size_m",
        "cell_short_size_m",
    )
    first = {
        name: (
            int(geometry_rows[0][name])
            if name in {"long_axis", "grid_long_count", "grid_short_count"}
            else float(geometry_rows[0][name])
        )
        for name in field_names
    }
    mismatches: list[int] = []
    for index, row in enumerate(geometry_rows):
        if any(
            not np.isclose(
                float(row[name]),
                float(first[name]),
                rtol=0.0,
                atol=1.0e-9,
            )
            for name in field_names
        ):
            mismatches.append(index)
    if mismatches:
        raise ValueError(
            "Strict primitive first-frame geometry is not constant: "
            f"row_indices={mismatches[:20]}"
        )
    return {
        **first,
        "worktool_width_m": LIVE_WORKTOOL_WIDTH_M,
        "profile": CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
        "source": "primitive_first_frame_env_state",
        "source_env_state_indices": {
            "long_axis": ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
            "grid_long_count": ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
            "grid_short_count": ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
            "cell_long_size_m": ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
            "cell_short_size_m": ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
        },
        "sample_count": len(geometry_rows),
        "all_rows_identical": True,
    }


def _load_prior_geometry(
    coverage_prior_path: str | Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if coverage_prior_path is None or not str(coverage_prior_path).strip():
        return None, None
    path = _validated_input_path(
        coverage_prior_path,
        label="coverage prior",
        require_dir=False,
    )
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Coverage prior must be a mapping: {path}")
    raw_cells = payload.get("coverage_cells")
    if not isinstance(raw_cells, Sequence) or isinstance(
        raw_cells,
        (str, bytes),
    ):
        raise ValueError("Coverage prior lacks coverage_cells.")
    cells: list[dict[str, Any]] = []
    for item in raw_cells:
        if not isinstance(item, Mapping):
            raise ValueError("Coverage prior cell must be a mapping.")
        cell_id = _cell_id(item.get("cell_id"), label="prior coverage cell")
        entry = item.get("entry")
        if not isinstance(entry, Mapping):
            raise ValueError(f"Coverage prior cell {cell_id} lacks entry.")
        cells.append(
            {
                "cell_id": cell_id,
                "entry_x_m": _finite_mapping_float(entry, "x_m"),
                "entry_z_m": _finite_mapping_float(entry, "z_m"),
            }
        )
    cells.sort(key=lambda item: int(item["cell_id"]))
    if [int(item["cell_id"]) for item in cells] != list(range(6)):
        raise ValueError("Coverage prior must contain cells 0..5 exactly once.")
    raw_return_cells = payload.get("return_start_envelope_cells", [])
    if not isinstance(raw_return_cells, Sequence) or isinstance(
        raw_return_cells,
        (str, bytes),
    ):
        raise ValueError("Coverage prior return envelope cells must be a list.")
    return_cell_ids = {
        _cell_id(item.get("cell_id"), label="return envelope cell")
        for item in raw_return_cells
        if isinstance(item, Mapping)
    }
    geometry = {
        "coverage_cells": cells,
        "return_envelope_cell_ids": return_cell_ids,
    }
    lock = {
        "path": str(path),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }
    return geometry, lock


def _return_envelope_cell_id(
    raw_fields: Mapping[str, Any],
    *,
    prior_geometry: dict[str, Any] | None,
) -> int | None:
    if prior_geometry is None:
        return None
    entry_x = _finite_mapping_float(raw_fields, "operator_entry_x_m")
    entry_z = _finite_mapping_float(raw_fields, "operator_entry_z_m")
    scored = [
        (
            float(
                (entry_x - float(item["entry_x_m"])) ** 2
                + (entry_z - float(item["entry_z_m"])) ** 2
            ),
            int(item["cell_id"]),
        )
        for item in prior_geometry["coverage_cells"]
    ]
    scored.sort(key=lambda item: (item[0], item[1]))
    cell_id = int(scored[0][1])
    if cell_id not in prior_geometry["return_envelope_cell_ids"]:
        return None
    return cell_id


def _raw_fields(handle: h5py.File) -> dict[str, float | int]:
    effective_deposit = _scalar(
        handle,
        "cycle_effective_deposit_delta_kg",
        _scalar(
            handle,
            "dig_outcome_effective_deposit_delta_kg",
            _scalar(handle, "operator_cut_payload_gain_kg"),
        ),
    )
    values: dict[str, float | int] = {
        name: _scalar(handle, name)
        for name in _RAW_FIELD_NAMES
        if name not in {
            "operator_effective_deposit_delta_kg",
            "operator_cut_valid",
        }
    }
    values["operator_effective_deposit_delta_kg"] = effective_deposit
    values["operator_cut_valid"] = int(
        round(_scalar(handle, "operator_cut_valid"))
    )
    for name, value in values.items():
        if not np.isfinite(float(value)):
            raise ValueError(f"Dig primitive raw field {name} is non-finite.")
    if int(values["operator_cut_valid"]) != 1:
        raise ValueError("Strict coverage execution row must have a valid cut.")
    return values


def _token_from_raw_fields(raw_fields: Mapping[str, Any]) -> np.ndarray:
    def clipped(name: str, scale: float) -> float:
        return float(
            np.clip(
                _finite_mapping_float(raw_fields, name) / float(scale),
                -1.0,
                1.0,
            )
        )

    return np.asarray(
        [
            clipped("operator_entry_x_m", DIG_CUT_POSITION_SCALE_M),
            clipped("operator_entry_z_m", DIG_CUT_POSITION_SCALE_M),
            clipped("operator_exit_x_m", DIG_CUT_POSITION_SCALE_M),
            clipped("operator_exit_z_m", DIG_CUT_POSITION_SCALE_M),
            _finite_mapping_float(
                raw_fields,
                "operator_cut_direction_x",
            ),
            _finite_mapping_float(
                raw_fields,
                "operator_cut_direction_z",
            ),
            clipped("operator_cut_length_m", DIG_CUT_LENGTH_SCALE_M),
            clipped("operator_cut_depth_peak_m", DIG_CUT_DEPTH_SCALE_M),
            clipped("operator_cut_payload_gain_kg", DIG_CUT_PAYLOAD_SCALE_KG),
            1.0,
        ],
        dtype=np.float32,
    )


def _required_matrix(
    handle: h5py.File,
    dataset_path: str,
    *,
    width: int,
    path: Path,
) -> np.ndarray:
    if dataset_path not in handle:
        raise ValueError(f"Dig primitive is missing {dataset_path}: {path}")
    dataset = handle[dataset_path]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"Dig primitive path is not a dataset: {dataset_path}")
    if dataset.is_virtual:
        raise ValueError(f"Dig primitive must be materialized, not VDS: {path}")
    if (
        dataset.ndim != 2
        or dataset.shape[0] < 1
        or dataset.shape[1] != width
    ):
        raise ValueError(
            f"Dig primitive {dataset_path} must have shape (T,{width}): {path}"
        )
    values = np.asarray(dataset[()], dtype=np.float32)
    if not np.all(np.isfinite(values)):
        raise ValueError(
            f"Dig primitive {dataset_path} contains non-finite values: {path}"
        )
    return values


def _required_vector(
    handle: h5py.File,
    dataset_path: str,
    *,
    length: int,
    path: Path,
    dtype: Any,
) -> np.ndarray:
    if dataset_path not in handle:
        raise ValueError(f"Dig primitive is missing {dataset_path}: {path}")
    dataset = handle[dataset_path]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"Dig primitive path is not a dataset: {dataset_path}")
    if dataset.is_virtual:
        raise ValueError(f"Dig primitive must be materialized, not VDS: {path}")
    values = np.asarray(dataset[()], dtype=dtype).reshape(-1)
    if values.shape != (int(length),):
        raise ValueError(
            f"Dig primitive {dataset_path} length mismatch: {path}"
        )
    return values


def _validated_input_path(
    value: Any,
    *,
    label: str,
    require_dir: bool,
) -> Path:
    if value is None or not str(value).strip():
        raise ValueError(f"Missing {label}.")
    path = Path(str(value)).expanduser().resolve(strict=True)
    if require_dir and not path.is_dir():
        raise ValueError(f"{label} must be a directory: {path}")
    if not require_dir and not path.is_file():
        raise ValueError(f"{label} must be a file: {path}")
    lowered_parts = tuple(part.lower() for part in path.parts)
    if any(
        marker in part
        for part in lowered_parts
        for marker in _FORBIDDEN_PATH_MARKERS
    ):
        raise ValueError(
            f"{label} refuses partial/layered/salvage input paths: {path}"
        )
    return path


def _source_mapping(value: Any) -> dict[int, int]:
    if not isinstance(value, Mapping):
        raise ValueError(
            "Dig source split lacks source_episode_id_by_primitive_episode_id."
        )
    result: dict[int, int] = {}
    for raw_key, raw_value in value.items():
        key = _episode_id(raw_key, label="primitive episode id")
        source = _episode_id(raw_value, label="source episode id")
        if key in result:
            raise ValueError(f"Duplicate primitive source mapping id {key}.")
        result[key] = source
    return result


def _unique_ids(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"Dig source split {label} must be a sequence.")
    values = tuple(_episode_id(item, label=label) for item in value)
    if not values:
        raise ValueError(f"Dig source split {label} must not be empty.")
    if len(values) != len(set(values)):
        raise ValueError(f"Dig source split {label} contains duplicates.")
    if values != tuple(sorted(values)):
        raise ValueError(f"Dig source split {label} must be sorted.")
    return values


def _episode_id(value: Any, *, label: str) -> int:
    text = _text(value)
    if text.startswith("episode_"):
        text = text.removeprefix("episode_")
    try:
        parsed = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{label} must be non-negative.")
    return parsed


def _scalar(
    handle: h5py.File,
    name: str,
    default: float = float("nan"),
) -> float:
    metadata = handle.get("metadata")
    if isinstance(metadata, h5py.Group) and name in metadata.attrs:
        try:
            return float(metadata.attrs[name])
        except (TypeError, ValueError):
            pass
    dataset_path = f"v2/cycle/{name}"
    if dataset_path in handle:
        values = np.asarray(handle[dataset_path][()]).reshape(-1)
        if values.size:
            try:
                return float(values[0])
            except (TypeError, ValueError):
                pass
    return float(default)


def _expect_metadata_text(
    metadata: h5py.Group,
    key: str,
    expected: str,
    path: Path,
) -> None:
    observed = _text(metadata.attrs.get(key, ""))
    if observed != expected:
        raise ValueError(
            f"Dig primitive metadata {key} must be {expected!r}, "
            f"got {observed!r}: {path}"
        )


def _expect_metadata_text_one_of(
    metadata: h5py.Group,
    key: str,
    expected: Sequence[str],
    path: Path,
) -> str:
    observed = _text(metadata.attrs.get(key, ""))
    if observed not in expected:
        raise ValueError(
            f"Dig primitive metadata {key} must be one of {list(expected)}, "
            f"got {observed!r}: {path}"
        )
    return observed


def _finite_mapping_float(mapping: Mapping[str, Any], key: str) -> float:
    try:
        value = float(mapping[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Missing or invalid finite field {key}.") from exc
    if not np.isfinite(value):
        raise ValueError(f"Field {key} must be finite.")
    return value


def _finite_grid(value: Any) -> np.ndarray:
    grid = np.asarray(value, dtype=np.float64).reshape(-1)
    if grid.shape != (6,) or not np.all(np.isfinite(grid)):
        raise ValueError("Removed-depth grid must be finite 6D.")
    return grid


def _cell_id(value: Any, *, label: str) -> int:
    try:
        cell_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    if cell_id < 0 or cell_id > 5:
        raise ValueError(f"{label} must be in [0, 5]: {value!r}")
    return cell_id


def _stats(values: Sequence[float]) -> dict[str, float]:
    return {
        key: _percentile(values, percentile)
        for key, percentile in (
            ("p50", 50),
            ("p90", 90),
            ("p95", 95),
            ("p99", 99),
            ("max", 100),
        )
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("Percentile input must be finite and nonempty.")
    return float(np.percentile(array, percentile))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "item"):
        try:
            return _text(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


__all__ = [
    "CORRIDOR_ID_BASE",
    "COVERAGE_EXECUTION_LIBRARY_SCHEMA",
    "LIVE_ENV_STATE_CONTRACT",
    "LIVE_WORKTOOL_WIDTH_M",
    "REMOVED_DEPTH_SCALE_M",
    "SOURCE_ENV_STATE_CONTRACT",
    "STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT",
    "TARGET_CELL_WEIGHT",
    "build_coverage_execution_library",
    "cut_tuple_consistency_residual_m",
    "evaluate_coverage_execution_query",
]
