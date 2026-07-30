"""Strict-train normalized joint paths for conservative Unity sweep queries.

The artifact built here is data-only.  It binds every immutable coverage
execution tuple to the complete normalized qpos path supervised by the dig
checkpoint, including the post-peak extraction tail.  Unity owns kinematics and
collision-distance evaluation; this module never makes an online plan.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.coverage_execution_library import (
    COVERAGE_EXECUTION_LIBRARY_SCHEMA,
    STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT,
)
from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.data.schema import (
    DS_QPOS,
    DS_V2_STEP_ACTION_LOSS_MASK,
)

COVERAGE_POSE_PATH_LIBRARY_SCHEMA = "strict_train_coverage_pose_paths_v1"
QPOS_ORDER = (
    "swing_position_norm",
    "boom_position_norm",
    "stick_position_norm",
    "bucket_position_norm",
)
_FORBIDDEN_PATH_MARKERS = ("partial", "layered", "salvage")
_SHA256_HEX_LENGTH = 64


def build_coverage_pose_path_library(
    *,
    dig_primitives_dir: str | Path,
    split_path: str | Path,
    execution_library_path: str | Path,
    normalization_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Build the immutable 374-record qpos-path companion artifact."""

    output = Path(output_path).expanduser().resolve()
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite coverage pose-path library: {output}"
        )
    dig_root = _strict_input_path(
        dig_primitives_dir,
        label="dig primitives",
        directory=True,
    )
    if dig_root.name != "dig" or dig_root.parent.name != "primitives_copy":
        raise ValueError(
            "coverage pose paths require materialized primitives_copy/dig"
        )
    split = _strict_input_path(split_path, label="split", directory=False)
    execution = _strict_input_path(
        execution_library_path,
        label="execution library",
        directory=False,
    )
    normalization = _strict_input_path(
        normalization_path,
        label="normalization",
        directory=False,
        reject_markers=False,
    )

    split_bytes = split.read_bytes()
    split_payload = yaml.safe_load(split_bytes)
    if not isinstance(split_payload, Mapping):
        raise ValueError("dig source split root must be a mapping")
    execution_bytes = execution.read_bytes()
    execution_payload = json.loads(execution_bytes)
    if not isinstance(execution_payload, Mapping):
        raise ValueError("execution library root must be a mapping")
    normalization_bytes = normalization.read_bytes()
    normalization_payload = json.loads(normalization_bytes)
    if not isinstance(normalization_payload, Mapping):
        raise ValueError("YuLong normalization root must be a mapping")

    train_ids, source_by_primitive = _validate_lineage(
        split_payload=split_payload,
        execution_payload=execution_payload,
        dig_root=dig_root,
    )
    qpos_contract = _qpos_contract(normalization_payload)
    records_by_id = _execution_records_by_id(execution_payload)
    records: list[dict[str, Any]] = []
    input_digest = hashlib.sha256()
    input_digest.update(f"{COVERAGE_POSE_PATH_LIBRARY_SCHEMA}\0".encode())
    input_digest.update(hashlib.sha256(split_bytes).digest())
    input_digest.update(hashlib.sha256(execution_bytes).digest())
    input_digest.update(hashlib.sha256(normalization_bytes).digest())

    for primitive_episode_id in train_ids:
        primitive_path = (
            dig_root / f"episode_{int(primitive_episode_id)}.hdf5"
        )
        if not primitive_path.is_file():
            raise FileNotFoundError(
                f"strict dig primitive missing: {primitive_path}"
            )
        source_episode_id = int(source_by_primitive[primitive_episode_id])
        execution_record = records_by_id.get(primitive_episode_id)
        if execution_record is None:
            raise ValueError(
                "execution library missing primitive "
                f"{primitive_episode_id}"
            )
        record = _read_pose_path_record(
            primitive_path=primitive_path,
            primitive_episode_id=primitive_episode_id,
            source_episode_id=source_episode_id,
            execution_record=execution_record,
        )
        records.append(record)
        input_digest.update(bytes.fromhex(record["source_sha256"]))

    if len(records) != STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT:
        raise ValueError(
            "coverage pose-path sample count must be "
            f"{STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT}, got {len(records)}"
        )
    artifact: dict[str, Any] = {
        "schema": COVERAGE_POSE_PATH_LIBRARY_SCHEMA,
        "status": "completed",
        "sample_count": len(records),
        "qpos_contract": qpos_contract,
        "source_lineage": {
            "partition": "train",
            "split_policy": "source_identity_exact_allowlist_v1",
            "dig_primitives_dir": str(dig_root),
            "train_primitive_episode_ids": list(train_ids),
            "train_source_episode_ids": list(
                STRICT18_TRAIN_SOURCE_EPISODE_IDS
            ),
            "validation_source_episode_ids": list(
                STRICT18_VALIDATION_SOURCE_EPISODE_IDS
            ),
            "validation_rows_read": 0,
            "partial_layered_salvage_input_views_allowed": False,
        },
        "source_lock": {
            "split": {
                "path": str(split),
                "sha256": hashlib.sha256(split_bytes).hexdigest(),
            },
            "execution_library": {
                "path": str(execution),
                "sha256": hashlib.sha256(execution_bytes).hexdigest(),
            },
            "normalization": {
                "path": str(normalization),
                "sha256": hashlib.sha256(normalization_bytes).hexdigest(),
            },
            "input_sha256": input_digest.hexdigest(),
        },
        "path_contract": {
            "start": "first action_loss_mask==1 dig row",
            "end": "last action_loss_mask==1 dig row",
            "includes_token_peak": True,
            "includes_extraction_tail": True,
            "interpolation": "piecewise_linear_normalized_qpos",
        },
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(
            artifact,
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    return output


def _read_pose_path_record(
    *,
    primitive_path: Path,
    primitive_episode_id: int,
    source_episode_id: int,
    execution_record: Mapping[str, Any],
) -> dict[str, Any]:
    source_bytes = primitive_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    recorded_source_sha256 = _sha256(
        execution_record.get("source_sha256"),
        label="execution source_sha256",
    )
    if source_sha256 != recorded_source_sha256:
        raise ValueError(
            "primitive SHA disagrees with execution library:"
            f"episode_{primitive_episode_id}"
        )
    if int(execution_record.get("source_episode_id", -1)) != source_episode_id:
        raise ValueError(
            "primitive source episode disagrees with execution library:"
            f"episode_{primitive_episode_id}"
        )
    raw_fields = execution_record.get("raw_fields")
    if not isinstance(raw_fields, Mapping):
        raise ValueError(
            f"execution raw fields missing: episode_{primitive_episode_id}"
        )
    raw_fields_sha256 = _canonical_mapping_sha256(raw_fields)

    with h5py.File(primitive_path, "r") as source:
        if DS_QPOS not in source or DS_V2_STEP_ACTION_LOSS_MASK not in source:
            raise ValueError(
                f"primitive qpos/loss mask missing: {primitive_path}"
            )
        qpos = np.asarray(source[DS_QPOS], dtype=np.float64)
        mask = np.asarray(
            source[DS_V2_STEP_ACTION_LOSS_MASK],
            dtype=np.uint8,
        ).reshape(-1)
    if qpos.ndim != 2 or qpos.shape[1] != len(QPOS_ORDER):
        raise ValueError(
            f"primitive qpos must have shape (T,4): {primitive_path}"
        )
    if qpos.shape[0] != mask.size or not np.isfinite(qpos).all():
        raise ValueError(
            f"primitive qpos/mask contract invalid: {primitive_path}"
        )
    if np.any(qpos < -1.0e-6) or np.any(qpos > 1.0 + 1.0e-6):
        raise ValueError(
            f"primitive normalized qpos outside [0,1]: {primitive_path}"
        )
    valid = np.flatnonzero(mask == 1)
    if valid.size == 0:
        raise ValueError(f"primitive has no valid dig supervision: {primitive_path}")
    first_valid = int(valid[0])
    last_valid = int(valid[-1])
    token_peak_local_index = int(
        execution_record.get("token_peak_local_index", -1)
    )
    if not 0 <= token_peak_local_index < qpos.shape[0]:
        raise ValueError(
            f"token peak outside primitive qpos path: {primitive_path}"
        )
    path_start = min(first_valid, token_peak_local_index)
    path_end = max(last_valid, token_peak_local_index)
    path = qpos[path_start : path_end + 1]
    path_list = [[float(value) for value in row] for row in path]
    path_sha256 = hashlib.sha256(
        json.dumps(
            path_list,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "exemplar_id": f"episode_{primitive_episode_id}",
        "primitive_episode_id": int(primitive_episode_id),
        "source_episode_id": int(source_episode_id),
        "raw_fields_sha256": raw_fields_sha256,
        "source_path": str(primitive_path),
        "source_sha256": source_sha256,
        "first_valid_local_index": first_valid,
        "last_valid_local_index": last_valid,
        "path_start_local_index": path_start,
        "path_end_local_index": path_end,
        "token_peak_local_index": token_peak_local_index,
        "token_peak_path_index": token_peak_local_index - path_start,
        "supervised_path_step_count": int(path.shape[0]),
        "path_includes_extraction_tail": bool(
            last_valid > token_peak_local_index
        ),
        "exemplar_start_qpos": path_list[0],
        "qpos_path_sha256": path_sha256,
        "qpos_path": path_list,
    }


def _validate_lineage(
    *,
    split_payload: Mapping[str, Any],
    execution_payload: Mapping[str, Any],
    dig_root: Path,
) -> tuple[tuple[int, ...], dict[int, int]]:
    if str(split_payload.get("split_policy", "")) != (
        "source_identity_exact_allowlist_v1"
    ):
        raise ValueError("dig split policy mismatch")
    if Path(str(split_payload.get("dataset_dir", ""))).resolve() != dig_root:
        raise ValueError("dig split dataset_dir mismatch")
    train_ids = _integer_tuple(split_payload.get("train_ids"), "train_ids")
    val_ids = _integer_tuple(split_payload.get("val_ids"), "val_ids")
    if set(train_ids).intersection(val_ids):
        raise ValueError("dig train/validation primitive overlap")
    if len(train_ids) != STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT:
        raise ValueError("strict dig train split must contain 374 primitives")
    train_sources = _integer_tuple(
        split_payload.get("train_source_episode_ids"),
        "train_source_episode_ids",
    )
    val_sources = _integer_tuple(
        split_payload.get("val_source_episode_ids"),
        "val_source_episode_ids",
    )
    if train_sources != tuple(STRICT18_TRAIN_SOURCE_EPISODE_IDS):
        raise ValueError("strict train source allowlist mismatch")
    if val_sources != tuple(STRICT18_VALIDATION_SOURCE_EPISODE_IDS):
        raise ValueError("strict validation source allowlist mismatch")
    mapping_value = split_payload.get(
        "source_episode_id_by_primitive_episode_id"
    )
    if not isinstance(mapping_value, Mapping):
        raise ValueError("dig split source mapping missing")
    source_by_primitive = {
        int(key): int(value) for key, value in mapping_value.items()
    }
    actual_sources = {
        source_by_primitive[primitive_episode_id]
        for primitive_episode_id in train_ids
    }
    if actual_sources != set(STRICT18_TRAIN_SOURCE_EPISODE_IDS):
        raise ValueError("strict train primitive source mapping mismatch")
    if set(actual_sources).intersection(
        STRICT18_VALIDATION_SOURCE_EPISODE_IDS
    ):
        raise ValueError("validation source leaked into strict train paths")

    if (
        str(execution_payload.get("schema", ""))
        != COVERAGE_EXECUTION_LIBRARY_SCHEMA
        or str(execution_payload.get("status", "")) != "completed"
    ):
        raise ValueError("execution library schema/status mismatch")
    execution_ids = tuple(sorted(_execution_records_by_id(execution_payload)))
    if execution_ids != tuple(sorted(train_ids)):
        raise ValueError("execution library and strict train split disagree")
    return train_ids, source_by_primitive


def _execution_records_by_id(
    execution_payload: Mapping[str, Any],
) -> dict[int, Mapping[str, Any]]:
    records = execution_payload.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("execution library records missing")
    result: dict[int, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("execution library record must be a mapping")
        primitive_id = int(record.get("primitive_episode_id", -1))
        if primitive_id in result:
            raise ValueError(f"duplicate execution primitive {primitive_id}")
        result[primitive_id] = record
    return result


def _qpos_contract(normalization: Mapping[str, Any]) -> dict[str, Any]:
    order = tuple(
        item.strip()
        for item in str(normalization.get("qpos_order", "")).split(",")
    )
    if order != QPOS_ORDER:
        raise ValueError("YuLong qpos order mismatch")
    minimum: list[float] = []
    maximum: list[float] = []
    raw_range: list[float] = []
    for name in ("swing", "boom", "stick", "bucket"):
        axis = normalization.get(name)
        if not isinstance(axis, Mapping):
            raise ValueError(f"YuLong normalization axis missing: {name}")
        lo = float(axis.get("min", float("nan")))
        hi = float(axis.get("max", float("nan")))
        if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
            raise ValueError(
                f"YuLong normalization axis invalid: {name}"
            )
        minimum.append(lo)
        maximum.append(hi)
        raw_range.append(hi - lo)
    return {
        "order": list(QPOS_ORDER),
        "dim": len(QPOS_ORDER),
        "units": "normalized_[0,1]",
        "raw_units": "radians",
        "raw_min_rad": minimum,
        "raw_max_rad": maximum,
        "raw_range_rad": raw_range,
    }


def _strict_input_path(
    value: str | Path,
    *,
    label: str,
    directory: bool,
    reject_markers: bool = True,
) -> Path:
    path = Path(value).expanduser().resolve()
    if reject_markers and any(
        marker in str(path).lower() for marker in _FORBIDDEN_PATH_MARKERS
    ):
        raise ValueError(f"{label} may not use partial/layered/salvage input")
    if directory and not path.is_dir():
        raise FileNotFoundError(f"{label} directory missing: {path}")
    if not directory and not path.is_file():
        raise FileNotFoundError(f"{label} file missing: {path}")
    return path


def _integer_tuple(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    result = tuple(int(item) for item in value)
    if len(set(result)) != len(result) or any(item < 0 for item in result):
        raise ValueError(f"{label} contains duplicate/negative ids")
    return result


def _canonical_mapping_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return digest


__all__ = [
    "COVERAGE_POSE_PATH_LIBRARY_SCHEMA",
    "QPOS_ORDER",
    "build_coverage_pose_path_library",
]
