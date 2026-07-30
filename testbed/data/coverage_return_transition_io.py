"""Validated strict primitive inputs for coverage return transitions."""

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

from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.data.schema import (
    DS_ENV_STATE,
    DS_QPOS,
    DS_QVEL,
    DS_V2_STEP_ACTION_LOSS_MASK,
    DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
)

RETURN_START_FACTS_SCHEMA = "return_start_facts_11d_v1"
RETURN_START_ENVELOPE_SCHEMA = "return_start_envelope_tokens_v1"
RETURN_START_ENVELOPE_TOKEN_DIM = 18
RETURN_START_FACTS_FEATURE_ORDER = (
    *(f"qpos[{index}]" for index in range(4)),
    *(f"qvel[{index}]" for index in range(4)),
    "bucket_tip_dig_area_x_m",
    "bucket_tip_dig_area_y_m",
    "bucket_tip_dig_area_z_m",
)
_QPOS_ORDER = (
    "swing_position_norm",
    "boom_position_norm",
    "stick_position_norm",
    "bucket_position_norm",
)
_QVEL_ORDER = (
    "swing_speed",
    "boom_speed",
    "stick_speed",
    "bucket_speed",
)
_FORBIDDEN_PATH_MARKERS = ("partial", "layered", "salvage")
_STRICT_EVIDENCE_KINDS = (
    "strict_parent_selected_replay",
    "strict_salvage_addition",
)
_SHA256_HEX_LENGTH = 64


def read_return_transition(
    path: Path,
    *,
    primitive_episode_id: int,
    expected_source_episode_id: int,
) -> dict[str, Any]:
    """Read one official gold return transition and exact handoff token."""

    source_sha256 = file_sha256(path, label="gold return primitive")
    with h5py.File(path, "r") as handle:
        metadata = _metadata(handle, path)
        _validate_primitive_metadata(
            metadata,
            primitive_name="return",
            source_episode_id=expected_source_episode_id,
            path=path,
        )
        source_cycle_id = _metadata_int(
            metadata,
            "source_cycle_id",
            path=path,
        )
        target_source_cycle_id = _metadata_int(
            metadata,
            "source_next_cycle_id",
            path=path,
        )
        if target_source_cycle_id <= source_cycle_id:
            raise ValueError(
                "Gold return must target a later material cycle: "
                f"{path}"
            )

        qpos, qvel, env_state, action_mask = _state_arrays(handle, path)
        if not np.any(action_mask == 1):
            raise ValueError(
                f"Gold return has no valid action supervision: {path}"
            )
        # The transition starts at the primitive boundary.  Loss masks are a
        # training statistic and must never shift the initial observation.
        start_local_index = 0
        source_start_step = _metadata_int(
            metadata,
            "source_start_step",
            path=path,
        )
        handoff_source_step = _metadata_int(
            metadata,
            "return_handoff_step",
            path=path,
        )
        handoff_local_index = handoff_source_step - source_start_step
        if not 0 <= handoff_local_index < qpos.shape[0]:
            raise ValueError(
                f"Return handoff step is outside the primitive: {path}"
            )

        tokens = _matrix(
            handle,
            DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
            width=RETURN_START_ENVELOPE_TOKEN_DIM,
            row_count=qpos.shape[0],
            dtype=np.float32,
            path=path,
        )
        valid_mask = _matrix(
            handle,
            DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK,
            width=RETURN_START_ENVELOPE_TOKEN_DIM,
            row_count=qpos.shape[0],
            dtype=np.uint8,
            path=path,
        )
        token = tokens[handoff_local_index]
        token_valid = valid_mask[handoff_local_index]
        if not np.all(tokens == token):
            raise ValueError(
                f"Return start-envelope token is not broadcast-stable: {path}"
            )
        if not np.all(valid_mask == token_valid):
            raise ValueError(
                f"Return start-envelope valid mask is not stable: {path}"
            )
        if _metadata_text(
            metadata,
            "return_start_envelope_schema",
            path=path,
        ) != RETURN_START_ENVELOPE_SCHEMA:
            raise ValueError(
                f"Unexpected return start-envelope schema: {path}"
            )
        if int(np.sum(token_valid == 1)) != RETURN_START_ENVELOPE_TOKEN_DIM:
            raise ValueError(
                f"Gold return requires a fully valid 18D envelope: {path}"
            )

        start_facts = _facts(
            qpos[start_local_index],
            qvel[start_local_index],
            env_state[start_local_index],
            path=path,
        )
        handoff_facts = _facts(
            qpos[handoff_local_index],
            qvel[handoff_local_index],
            env_state[handoff_local_index],
            path=path,
        )
    token_sha256 = hashlib.sha256(
        np.asarray(token, dtype="<f4").tobytes(order="C")
        + np.asarray(token_valid, dtype=np.uint8).tobytes(order="C")
    ).hexdigest()
    return {
        "paired_return_exemplar_id": f"episode_{primitive_episode_id}",
        "paired_return_primitive_episode_id": primitive_episode_id,
        "paired_return_source_sha256": source_sha256,
        "source_episode_id": expected_source_episode_id,
        "paired_return_source_cycle_id": source_cycle_id,
        "target_source_cycle_id": target_source_cycle_id,
        "return_start_local_index": start_local_index,
        "return_start_source_step": source_start_step + start_local_index,
        "return_handoff_local_index": handoff_local_index,
        "return_handoff_source_step": handoff_source_step,
        "return_start_facts_11d": float_list(start_facts),
        "expert_return_handoff_facts_11d": float_list(handoff_facts),
        "exact_return_start_envelope_tokens_v1": float_list(token),
        "exact_return_start_envelope_valid_mask": [
            int(value) for value in token_valid
        ],
        "exact_return_start_envelope_sha256": token_sha256,
    }


def read_dig_start(
    path: Path,
    *,
    primitive_episode_id: int,
    expected_source_episode_id: int,
    execution_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Read one exact dig tuple's immutable start observation."""

    source_sha256 = file_sha256(path, label="gold dig primitive")
    recorded_source_sha256 = sha256_text(
        execution_record.get("source_sha256"),
        label="execution record source_sha256",
    )
    if source_sha256 != recorded_source_sha256:
        raise ValueError(
            "Dig primitive SHA disagrees with execution library: "
            f"episode_{primitive_episode_id}"
        )
    if int(execution_record.get("source_episode_id", -1)) != (
        expected_source_episode_id
    ):
        raise ValueError(
            "Dig primitive source disagrees with execution library: "
            f"episode_{primitive_episode_id}"
        )
    raw_fields = execution_record.get("raw_fields")
    if not isinstance(raw_fields, Mapping):
        raise ValueError(
            "Execution library record lacks raw_fields: "
            f"episode_{primitive_episode_id}"
        )

    with h5py.File(path, "r") as handle:
        metadata = _metadata(handle, path)
        _validate_primitive_metadata(
            metadata,
            primitive_name="dig",
            source_episode_id=expected_source_episode_id,
            path=path,
        )
        source_cycle_id = _metadata_int(
            metadata,
            "source_cycle_id",
            path=path,
        )
        qpos, qvel, env_state, action_mask = _state_arrays(handle, path)
        valid = np.flatnonzero(action_mask == 1)
        if valid.size == 0:
            raise ValueError(
                f"Gold dig has no valid action supervision: {path}"
            )
        start_local_index = int(valid[0])
        source_start_step = _metadata_int(
            metadata,
            "source_start_step",
            path=path,
        )
        start_facts = _facts(
            qpos[start_local_index],
            qvel[start_local_index],
            env_state[start_local_index],
            path=path,
        )
    return {
        "exemplar_id": f"episode_{primitive_episode_id}",
        "primitive_episode_id": primitive_episode_id,
        "source_episode_id": expected_source_episode_id,
        "source_cycle_id": source_cycle_id,
        "raw_fields_sha256": canonical_mapping_sha256(raw_fields),
        "dig_source_sha256": source_sha256,
        "dig_start_local_index": start_local_index,
        "dig_start_source_step": source_start_step + start_local_index,
        "expert_dig_start_facts_11d": float_list(start_facts),
    }


def validate_source_split(
    payload: Mapping[str, Any],
    *,
    primitive_name: str,
    dataset_dir: Path,
    expected_train_count: int,
) -> dict[str, Any]:
    """Validate the strict source split without opening val/non-gold rows."""

    if str(payload.get("split_policy", "")) != (
        "source_identity_exact_allowlist_v1"
    ):
        raise ValueError(f"Unexpected {primitive_name} source split policy.")
    if str(payload.get("required_training_tier", "")) != "gold":
        raise ValueError(
            f"Strict {primitive_name} source split must require gold rows."
        )
    recorded_dir = Path(str(payload.get("dataset_dir", ""))).resolve()
    if recorded_dir != dataset_dir:
        raise ValueError(
            f"{primitive_name} split dataset_dir mismatch: "
            f"split={recorded_dir}, requested={dataset_dir}"
        )
    train_ids = _integer_tuple(payload.get("train_ids"), label="train_ids")
    val_ids = _integer_tuple(payload.get("val_ids"), label="val_ids")
    if set(train_ids).intersection(val_ids):
        raise ValueError(
            f"{primitive_name} train/validation primitive ids overlap."
        )
    if len(train_ids) != expected_train_count:
        raise ValueError(
            f"Strict {primitive_name} train partition must contain "
            f"{expected_train_count} rows; got {len(train_ids)}."
        )
    train_sources = _integer_tuple(
        payload.get("train_source_episode_ids"),
        label="train_source_episode_ids",
    )
    val_sources = _integer_tuple(
        payload.get("val_source_episode_ids"),
        label="val_source_episode_ids",
    )
    if train_sources != STRICT18_TRAIN_SOURCE_EPISODE_IDS:
        raise ValueError(
            f"Strict {primitive_name} train source allowlist mismatch."
        )
    if val_sources != STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
        raise ValueError(
            f"Strict {primitive_name} validation sources must be [33, 34]."
        )
    allowed_sources = _integer_tuple(
        payload.get("allowed_source_episode_ids"),
        label="allowed_source_episode_ids",
    )
    if allowed_sources != tuple(sorted((*train_sources, *val_sources))):
        raise ValueError(
            f"Strict {primitive_name} allowed source list is invalid."
        )
    source_by_primitive = _source_mapping(
        payload.get("source_episode_id_by_primitive_episode_id")
    )
    missing = set((*train_ids, *val_ids)) - source_by_primitive.keys()
    if missing:
        raise ValueError(
            f"{primitive_name} source split lacks source ids: "
            f"{sorted(missing)}"
        )
    observed_train_sources = tuple(
        sorted({source_by_primitive[item] for item in train_ids})
    )
    observed_val_sources = tuple(
        sorted({source_by_primitive[item] for item in val_ids})
    )
    if primitive_name == "dig" and observed_train_sources != train_sources:
        raise ValueError(
            "dig train rows do not cover the strict source allowlist."
        )
    if not set(observed_train_sources).issubset(train_sources):
        raise ValueError(
            f"{primitive_name} train rows contain a non-train source."
        )
    if observed_val_sources != val_sources:
        raise ValueError(
            f"{primitive_name} validation rows do not cover sources 33/34."
        )
    return {
        "train_ids": train_ids,
        "val_ids": val_ids,
        "source_by_primitive": source_by_primitive,
    }


def execution_records(
    payload: Mapping[str, Any],
    *,
    expected_schema: str,
    expected_ids: Sequence[int],
) -> dict[int, Mapping[str, Any]]:
    """Index and lock the frozen execution library's exact tuple rows."""

    if (
        str(payload.get("schema", "")) != expected_schema
        or str(payload.get("status", "")) != "completed"
    ):
        raise ValueError("Coverage execution library schema/status mismatch.")
    rows = payload.get("records")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("Coverage execution library records are missing.")
    records: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Coverage execution record must be a mapping.")
        primitive_id = int(row.get("primitive_episode_id", -1))
        if primitive_id in records:
            raise ValueError(
                f"Coverage execution library repeats episode_{primitive_id}."
            )
        records[primitive_id] = row
    if tuple(sorted(records)) != tuple(sorted(int(item) for item in expected_ids)):
        raise ValueError(
            "Coverage execution library and strict dig split disagree."
        )
    return records


def strict_primitive_root(
    value: str | Path,
    *,
    primitive_name: str,
) -> Path:
    path = Path(value).expanduser().resolve()
    _reject_forbidden_path(path, label=f"{primitive_name} primitive directory")
    if not path.is_dir():
        raise FileNotFoundError(
            f"{primitive_name} primitive directory missing: {path}"
        )
    if path.name != primitive_name or path.parent.name != "primitives_copy":
        raise ValueError(
            f"{primitive_name} input must be primitives_copy/{primitive_name}: "
            f"{path}"
        )
    return path


def strict_file(value: str | Path, *, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    _reject_forbidden_path(path, label=label)
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    return path


def yaml_mapping(value: bytes, *, label: str) -> Mapping[str, Any]:
    parsed = yaml.safe_load(value)
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{label} root must be a mapping.")
    return parsed


def json_mapping(value: bytes, *, label: str) -> Mapping[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{label} root must be a mapping.")
    return parsed


def file_sha256(path: Path, *, label: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_mapping_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def sha256_text(value: Any, *, label: str) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != _SHA256_HEX_LENGTH or any(
        item not in "0123456789abcdef" for item in digest
    ):
        raise ValueError(f"{label} must be a lowercase SHA256.")
    return digest


def float_list(values: Sequence[Any]) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Artifact vector contains non-finite values.")
    return result


def _validate_primitive_metadata(
    metadata: h5py.Group,
    *,
    primitive_name: str,
    source_episode_id: int,
    path: Path,
) -> None:
    expected = {
        "primitive_name": primitive_name,
        "training_tier": "gold",
        "primitive_storage_mode": "copy",
        "composite_view_kind": "combined_strict_clean_vds",
        "source_episode_id": f"episode_{source_episode_id}",
    }
    for key, value in expected.items():
        observed = _metadata_text(metadata, key, path=path)
        if observed != value:
            raise ValueError(
                f"{primitive_name} metadata {key} must be {value!r}, "
                f"got {observed!r}: {path}"
            )
    evidence_kind = _metadata_text(
        metadata,
        "composite_evidence_kind",
        path=path,
    )
    if evidence_kind not in _STRICT_EVIDENCE_KINDS:
        raise ValueError(
            f"Unexpected strict evidence kind {evidence_kind!r}: {path}"
        )
    _validate_optional_order(metadata, "qpos_order", _QPOS_ORDER, path)
    _validate_optional_order(metadata, "qvel_order", _QVEL_ORDER, path)


def _state_arrays(
    handle: h5py.File,
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    qpos = _matrix(
        handle,
        DS_QPOS,
        width=4,
        dtype=np.float32,
        path=path,
    )
    qvel = _matrix(
        handle,
        DS_QVEL,
        width=4,
        row_count=qpos.shape[0],
        dtype=np.float32,
        path=path,
    )
    env_state = _matrix(
        handle,
        DS_ENV_STATE,
        min_width=ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3,
        row_count=qpos.shape[0],
        dtype=np.float32,
        path=path,
    )
    action_mask = _vector(
        handle,
        DS_V2_STEP_ACTION_LOSS_MASK,
        row_count=qpos.shape[0],
        dtype=np.uint8,
        path=path,
    )
    if np.any(qpos < -1.0e-6) or np.any(qpos > 1.0 + 1.0e-6):
        raise ValueError(f"Normalized qpos is outside [0,1]: {path}")
    return qpos, qvel, env_state, action_mask


def _facts(
    qpos: np.ndarray,
    qvel: np.ndarray,
    env_state: np.ndarray,
    *,
    path: Path,
) -> np.ndarray:
    facts = np.concatenate(
        (
            qpos,
            qvel,
            env_state[
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX :
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
            ],
        )
    ).astype(np.float32, copy=False)
    if facts.shape != (len(RETURN_START_FACTS_FEATURE_ORDER),):
        raise AssertionError(f"Unexpected return-start fact shape: {facts.shape}")
    if not np.isfinite(facts).all():
        raise ValueError(f"Return transition facts are non-finite: {path}")
    return facts


def _matrix(
    handle: h5py.File,
    dataset_path: str,
    *,
    dtype: np.dtype[Any],
    path: Path,
    width: int | None = None,
    min_width: int | None = None,
    row_count: int | None = None,
) -> np.ndarray:
    dataset = handle.get(dataset_path)
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"Primitive is missing {dataset_path}: {path}")
    if dataset.is_virtual:
        raise ValueError(f"Primitive must be materialized, not VDS: {path}")
    if dataset.ndim != 2 or dataset.shape[0] < 1:
        raise ValueError(f"{dataset_path} must have shape (T,D): {path}")
    if width is not None and dataset.shape[1] != width:
        raise ValueError(f"{dataset_path} width must be {width}: {path}")
    if min_width is not None and dataset.shape[1] < min_width:
        raise ValueError(f"{dataset_path} width is too small: {path}")
    if row_count is not None and dataset.shape[0] != row_count:
        raise ValueError(f"{dataset_path} row count mismatch: {path}")
    values = np.asarray(dataset, dtype=dtype)
    if not np.isfinite(values).all():
        raise ValueError(f"{dataset_path} contains non-finite values: {path}")
    return values


def _vector(
    handle: h5py.File,
    dataset_path: str,
    *,
    dtype: np.dtype[Any],
    path: Path,
    row_count: int,
) -> np.ndarray:
    dataset = handle.get(dataset_path)
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"Primitive is missing {dataset_path}: {path}")
    if dataset.is_virtual:
        raise ValueError(f"Primitive must be materialized, not VDS: {path}")
    if dataset.ndim != 1 or dataset.shape[0] != row_count:
        raise ValueError(f"{dataset_path} must have shape (T,): {path}")
    return np.asarray(dataset, dtype=dtype)


def _reject_forbidden_path(path: Path, *, label: str) -> None:
    if any(
        marker in part.lower()
        for part in path.parts
        for marker in _FORBIDDEN_PATH_MARKERS
    ):
        raise ValueError(
            f"{label} may not use partial/layered/salvage input: {path}"
        )


def _metadata(handle: h5py.File, path: Path) -> h5py.Group:
    metadata = handle.get("metadata")
    if not isinstance(metadata, h5py.Group):
        raise ValueError(f"Primitive metadata group is missing: {path}")
    return metadata


def _metadata_text(metadata: h5py.Group, key: str, *, path: Path) -> str:
    if key not in metadata.attrs:
        raise ValueError(f"Primitive metadata {key} is missing: {path}")
    return _text(metadata.attrs[key])


def _metadata_int(metadata: h5py.Group, key: str, *, path: Path) -> int:
    text = _metadata_text(metadata, key, path=path)
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(
            f"Primitive metadata {key} is not an integer: {path}"
        ) from exc
    if value < 0:
        raise ValueError(f"Primitive metadata {key} is negative: {path}")
    return value


def _validate_optional_order(
    metadata: h5py.Group,
    key: str,
    expected: Sequence[str],
    path: Path,
) -> None:
    if key not in metadata.attrs:
        return
    observed = tuple(
        item.strip()
        for item in _text(metadata.attrs[key]).split(",")
        if item.strip()
    )
    if observed != tuple(expected):
        raise ValueError(
            f"Primitive {key} mismatch: expected={list(expected)}, "
            f"observed={list(observed)}: {path}"
        )


def _integer_tuple(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence.")
    result = tuple(_episode_id(item, label=label) for item in value)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{label} must be non-empty and unique.")
    if result != tuple(sorted(result)):
        raise ValueError(f"{label} must be sorted.")
    return result


def _source_mapping(value: Any) -> dict[int, int]:
    if not isinstance(value, Mapping):
        raise ValueError("Source split primitive/source mapping is missing.")
    result: dict[int, int] = {}
    for key, source in value.items():
        primitive_id = _episode_id(key, label="primitive episode id")
        if primitive_id in result:
            raise ValueError(
                f"Source split repeats primitive episode {primitive_id}."
            )
        result[primitive_id] = _episode_id(
            source,
            label="source episode id",
        )
    return result


def _episode_id(value: Any, *, label: str) -> int:
    text = _text(value)
    if text.startswith("episode_"):
        text = text.removeprefix("episode_")
    try:
        result = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    if result < 0:
        raise ValueError(f"{label} must be non-negative: {value!r}")
    return result


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "item"):
        try:
            return _text(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


__all__ = [
    "RETURN_START_ENVELOPE_SCHEMA",
    "RETURN_START_ENVELOPE_TOKEN_DIM",
    "RETURN_START_FACTS_FEATURE_ORDER",
    "RETURN_START_FACTS_SCHEMA",
    "execution_records",
    "float_list",
    "json_mapping",
    "read_dig_start",
    "read_return_transition",
    "strict_file",
    "strict_primitive_root",
    "validate_source_split",
    "yaml_mapping",
]
