"""Replay-derived primitive handoff envelopes.

This module owns the data-side contract for handoff state distributions.  It
does not decide whether an online planner should switch primitives.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

CARRY_START_ENVELOPE_SCHEMA = "carry_start_envelope_v1"
STRICT18_CARRY_TRAIN_SAMPLE_COUNT = 374
STRICT18_TRAIN_SOURCE_EPISODE_IDS = (
    3,
    6,
    7,
    8,
    9,
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
)
STRICT18_VALIDATION_SOURCE_EPISODE_IDS = (33, 34)

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
CARRY_START_ENVELOPE_FEATURE_ORDER = (
    *(f"qpos[{index}]" for index in range(4)),
    *(f"qvel[{index}]" for index in range(4)),
    "bucket_tip_dig_area_x_m",
    "bucket_tip_dig_area_y_m",
    "bucket_tip_dig_area_z_m",
    "bucket_depth_below_dig_area_plane_m",
    "bucket_depth_below_local_surface_m",
)
_FEATURE_SOURCES = (
    *(
        {"dataset": "observations/qpos", "index": index}
        for index in range(4)
    ),
    *(
        {"dataset": "observations/qvel", "index": index}
        for index in range(4)
    ),
    *(
        {"dataset": "observations/env_state", "index": index}
        for index in (28, 29, 30, 8, 31)
    ),
)
_FORBIDDEN_DATASET_PATH_MARKERS = ("partial", "layered", "salvage")
_STRICT_EVIDENCE_KINDS = (
    "strict_parent_selected_replay",
    "strict_salvage_addition",
)


def build_carry_start_envelope(
    *,
    split_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Build the strict-18 carry-start state envelope from train first frames.

    The split is a semantic input, not merely a list of files: its source
    allowlist and every selected primitive's source identity are checked before
    any output is created.  Existing outputs are always preserved.
    """

    split = Path(split_path).expanduser().resolve(strict=True)
    output = Path(output_path).expanduser().resolve()
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite carry-start envelope artifact: {output}"
        )

    split_bytes = split.read_bytes()
    payload = yaml.safe_load(split_bytes)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Carry source split must be a mapping: {split}")

    dataset_dir = _validated_dataset_dir(payload.get("dataset_dir"))
    train_ids = _unique_ids(payload.get("train_ids"), label="train_ids")
    val_ids = _unique_ids(payload.get("val_ids"), label="val_ids")
    overlap = sorted(set(train_ids) & set(val_ids))
    if overlap:
        raise ValueError(f"Carry source split train/val overlap: {overlap}")
    if len(train_ids) != STRICT18_CARRY_TRAIN_SAMPLE_COUNT:
        raise ValueError(
            "Strict-18 carry train partition must contain exactly "
            f"{STRICT18_CARRY_TRAIN_SAMPLE_COUNT} primitives; got {len(train_ids)}."
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
            "Strict-18 carry train source allowlist mismatch: "
            f"expected={list(STRICT18_TRAIN_SOURCE_EPISODE_IDS)}, "
            f"observed={list(train_sources)}."
        )
    if val_sources != STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
        raise ValueError(
            "Strict-18 carry validation source allowlist mismatch: "
            f"expected={list(STRICT18_VALIDATION_SOURCE_EPISODE_IDS)}, "
            f"observed={list(val_sources)}."
        )
    expected_allowed = tuple(sorted((*train_sources, *val_sources)))
    if allowed_sources != expected_allowed:
        raise ValueError(
            "Strict-18 carry allowed sources must equal train+validation sources."
        )
    if str(payload.get("split_policy", "")) != "source_identity_exact_allowlist_v1":
        raise ValueError("Unexpected carry source split policy.")
    if str(payload.get("required_training_tier", "")) != "gold":
        raise ValueError("Strict-18 carry envelope requires training tier 'gold'.")

    source_by_primitive = _source_mapping(
        payload.get("source_episode_id_by_primitive_episode_id")
    )
    missing_source_ids = sorted(set((*train_ids, *val_ids)) - source_by_primitive.keys())
    if missing_source_ids:
        raise ValueError(
            "Carry source split is missing source identities for primitive ids: "
            f"{missing_source_ids}."
        )
    validation_in_train = sorted(
        episode_id
        for episode_id in train_ids
        if source_by_primitive[episode_id] in set(val_sources)
    )
    if validation_in_train:
        raise ValueError(
            "Carry train partition contains a validation source (33/34): "
            f"primitive_ids={validation_in_train}."
        )
    observed_train_sources = tuple(
        sorted({source_by_primitive[episode_id] for episode_id in train_ids})
    )
    if observed_train_sources != train_sources:
        raise ValueError(
            "Carry train primitive sources do not exactly cover the strict-18 "
            f"train allowlist: observed={list(observed_train_sources)}."
        )
    observed_val_sources = tuple(
        sorted({source_by_primitive[episode_id] for episode_id in val_ids})
    )
    if observed_val_sources != val_sources:
        raise ValueError(
            "Carry validation primitive sources do not exactly cover episodes 33/34."
        )

    input_digest = hashlib.sha256()
    input_digest.update(f"{CARRY_START_ENVELOPE_SCHEMA}\0".encode())
    input_digest.update(hashlib.sha256(split_bytes).digest())
    rows: list[np.ndarray] = []
    selected_source_mapping: dict[str, int] = {}
    evidence_kind_counts: Counter[str] = Counter()
    for primitive_episode_id in train_ids:
        source_episode_id = source_by_primitive[primitive_episode_id]
        episode_path = dataset_dir / f"episode_{primitive_episode_id}.hdf5"
        vector, evidence_kind = _read_first_frame(
            episode_path,
            expected_source_episode_id=source_episode_id,
        )
        rows.append(vector)
        evidence_kind_counts[evidence_kind] += 1
        selected_source_mapping[str(primitive_episode_id)] = source_episode_id
        input_digest.update(
            f"episode_{primitive_episode_id}\0source_{source_episode_id}\0".encode()
        )
        input_digest.update(np.asarray(vector, dtype="<f4").tobytes(order="C"))

    values = np.stack(rows, axis=0)
    percentiles = {
        label: [
            round(float(value), 9)
            for value in np.percentile(values, percentile, axis=0)
        ]
        for label, percentile in (("p01", 1), ("p50", 50), ("p99", 99))
    }
    artifact: dict[str, Any] = {
        "schema": CARRY_START_ENVELOPE_SCHEMA,
        "feature_order": list(CARRY_START_ENVELOPE_FEATURE_ORDER),
        "feature_sources": list(_FEATURE_SOURCES),
        "sample_count": int(values.shape[0]),
        "percentiles": percentiles,
        "source_lineage": {
            "partition": "train",
            "split_path": str(split),
            "split_policy": "source_identity_exact_allowlist_v1",
            "dataset_dir": str(dataset_dir),
            "train_primitive_episode_ids": list(train_ids),
            "train_source_episode_ids": list(train_sources),
            "validation_source_episode_ids": list(val_sources),
            "source_episode_id_by_primitive_episode_id": selected_source_mapping,
            "strict_evidence_kind_counts": dict(sorted(evidence_kind_counts.items())),
        },
        "split_sha256": hashlib.sha256(split_bytes).hexdigest(),
        "input_sha256_contract": (
            "sha256(schema_nul + split_sha256_bytes + ordered "
            "primitive/source_ids + selected_first_frame_float32_le)"
        ),
        "input_sha256": input_digest.hexdigest(),
    }

    rendered = json.dumps(
        artifact,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
    return output


def _validated_dataset_dir(value: Any) -> Path:
    if value is None or not str(value).strip():
        raise ValueError("Carry source split is missing dataset_dir.")
    path = Path(str(value)).expanduser().resolve(strict=True)
    lowered_parts = tuple(part.lower() for part in path.parts)
    if any(
        marker in part
        for part in lowered_parts
        for marker in _FORBIDDEN_DATASET_PATH_MARKERS
    ):
        raise ValueError(
            f"Carry envelope refuses partial/layered salvage dataset paths: {path}"
        )
    if path.name != "carry" or path.parent.name != "primitives_copy":
        raise ValueError(
            "Carry envelope dataset_dir must be primitives_copy/carry: "
            f"{path}"
        )
    return path


def _read_first_frame(
    path: Path,
    *,
    expected_source_episode_id: int,
) -> tuple[np.ndarray, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Carry primitive does not exist: {path}")
    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if not isinstance(metadata, h5py.Group):
            raise ValueError(f"Carry primitive is missing metadata: {path}")
        _expect_metadata_text(metadata, "primitive_name", "carry", path)
        _expect_metadata_text(metadata, "training_tier", "gold", path)
        _expect_metadata_text(metadata, "storage_mode", "copy", path)
        evidence_kind = _expect_metadata_text_one_of(
            metadata,
            "composite_evidence_kind",
            _STRICT_EVIDENCE_KINDS,
            path,
        )
        _expect_metadata_text(
            metadata,
            "composite_view_kind",
            "combined_strict_clean_vds",
            path,
        )
        _expect_metadata_text(
            metadata,
            "source_episode_id",
            f"episode_{expected_source_episode_id}",
            path,
        )
        _validate_optional_order(metadata, "qpos_order", _QPOS_ORDER, path)
        _validate_optional_order(metadata, "qvel_order", _QVEL_ORDER, path)

        qpos = _first_dataset_row(handle, "observations/qpos", width=4, path=path)
        qvel = _first_dataset_row(handle, "observations/qvel", width=4, path=path)
        env_state = _first_dataset_row(
            handle,
            "observations/env_state",
            min_width=32,
            path=path,
        )
    vector = np.concatenate(
        (
            qpos,
            qvel,
            env_state[28:31],
            env_state[8:9],
            env_state[31:32],
        )
    ).astype(np.float32, copy=False)
    if vector.shape != (len(CARRY_START_ENVELOPE_FEATURE_ORDER),):
        raise AssertionError(f"Unexpected carry-start feature shape: {vector.shape}")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"Carry primitive first-frame features are non-finite: {path}")
    return vector, evidence_kind


def _first_dataset_row(
    handle: h5py.File,
    dataset_path: str,
    *,
    path: Path,
    width: int | None = None,
    min_width: int | None = None,
) -> np.ndarray:
    if dataset_path not in handle:
        raise ValueError(f"Carry primitive is missing {dataset_path}: {path}")
    dataset = handle[dataset_path]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"Carry primitive path is not a dataset: {dataset_path}")
    if dataset.is_virtual:
        raise ValueError(f"Carry primitive must be materialized, not VDS: {path}")
    if dataset.ndim != 2 or dataset.shape[0] < 1:
        raise ValueError(
            f"Carry primitive dataset must have at least one row: {dataset_path}"
        )
    if width is not None and dataset.shape[1] != width:
        raise ValueError(
            f"Carry primitive {dataset_path} width must be {width}: {path}"
        )
    if min_width is not None and dataset.shape[1] < min_width:
        raise ValueError(
            f"Carry primitive {dataset_path} width must be >= {min_width}: {path}"
        )
    return np.asarray(dataset[0], dtype=np.float32)


def _expect_metadata_text(
    metadata: h5py.Group,
    key: str,
    expected: str,
    path: Path,
) -> None:
    observed = _text(metadata.attrs.get(key, ""))
    if observed != expected:
        raise ValueError(
            f"Carry primitive metadata {key} must be {expected!r}, "
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
            f"Carry primitive metadata {key} must be one of {list(expected)!r}, "
            f"got {observed!r}: {path}"
        )
    return observed


def _validate_optional_order(
    metadata: h5py.Group,
    key: str,
    expected: Sequence[str],
    path: Path,
) -> None:
    if key not in metadata.attrs:
        return
    observed = tuple(
        part.strip() for part in _text(metadata.attrs[key]).split(",") if part.strip()
    )
    if observed != tuple(expected):
        raise ValueError(
            f"Carry primitive metadata {key} mismatch: "
            f"expected={list(expected)}, observed={list(observed)}: {path}"
        )


def _source_mapping(value: Any) -> dict[int, int]:
    if not isinstance(value, Mapping):
        raise ValueError(
            "Carry source split is missing "
            "source_episode_id_by_primitive_episode_id."
        )
    mapping: dict[int, int] = {}
    for raw_key, raw_value in value.items():
        key = _episode_id(raw_key, label="primitive episode id")
        source = _episode_id(raw_value, label="source episode id")
        if key in mapping:
            raise ValueError(f"Carry source mapping repeats primitive id {key}.")
        mapping[key] = source
    return mapping


def _unique_ids(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"Carry source split {label} must be a sequence.")
    ids = tuple(_episode_id(item, label=label) for item in value)
    if not ids:
        raise ValueError(f"Carry source split {label} must not be empty.")
    if len(ids) != len(set(ids)):
        raise ValueError(f"Carry source split {label} contains duplicates.")
    if ids != tuple(sorted(ids)):
        raise ValueError(f"Carry source split {label} must be sorted.")
    return ids


def _episode_id(value: Any, *, label: str) -> int:
    text = _text(value)
    if text.startswith("episode_"):
        text = text.removeprefix("episode_")
    try:
        parsed = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{label} must be non-negative: {value!r}")
    return parsed


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
    "CARRY_START_ENVELOPE_FEATURE_ORDER",
    "CARRY_START_ENVELOPE_SCHEMA",
    "STRICT18_CARRY_TRAIN_SAMPLE_COUNT",
    "STRICT18_TRAIN_SOURCE_EPISODE_IDS",
    "STRICT18_VALIDATION_SOURCE_EPISODE_IDS",
    "build_carry_start_envelope",
]
