"""Small no-overwrite I/O and numeric validators for contact evidence."""

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

_SHA_HEX = frozenset("0123456789abcdef")


class WallContactArtifactError(RuntimeError):
    """Raised when a contact-evidence artifact cannot be trusted."""


def validate_intervals(
    value: Any,
    label: str,
    path_length: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WallContactArtifactError(f"{label}_invalid")
    result = []
    for item in value:
        interval = mapping(item, label)
        start = int(interval.get("start_path_index", -1))
        end = int(interval.get("end_path_index", -1))
        if not 0 <= start <= end < path_length:
            raise WallContactArtifactError(f"{label}_index_invalid")
        start_fraction = finite(
            interval.get("start_fraction"),
            "start_fraction",
            minimum=0.0,
        )
        end_fraction = finite(
            interval.get("end_fraction"),
            "end_fraction",
            minimum=0.0,
        )
        if start_fraction > 1.0 or end_fraction > 1.0:
            raise WallContactArtifactError(f"{label}_fraction_invalid")
        result.append(dict(interval))
    return result


def validate_bucket_region_samples(
    value: Any,
    *,
    path_id: str,
    component: str,
    wall: str,
    machine_paths: Sequence[str],
    wall_paths: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WallContactArtifactError("bucket_local_contact_region_samples_invalid")
    result = []
    for raw in value:
        sample = mapping(raw, "bucket contact region sample")
        if (
            sample.get("path_id") != path_id
            or sample.get("component") != component
            or sample.get("wall_name") != wall
            or sample.get("machine_shape_path") not in machine_paths
            or sample.get("wall_shape_path") not in wall_paths
        ):
            raise WallContactArtifactError("bucket_contact_region_sample_lineage_drift")
        vector(sample.get("bucket_local_point_m"), 3, "bucket_local_point_m")
        vector(sample.get("world_point_m"), 3, "world_point_m")
        vector(sample.get("qpos"), 4, "qpos")
        int(sample.get("sample_index", -1))
        int(sample.get("source_path_index", -1))
        if not isinstance(sample.get("overlap"), bool):
            raise WallContactArtifactError("bucket_contact_region_overlap_invalid")
        result.append(dict(sample))
    return result


def validate_detailed_contact_summary(
    value: Any,
    *,
    label: str,
    allowed_walls: Sequence[str],
) -> dict[str, Any]:
    summary = dict(mapping(value, label))
    if not isinstance(summary.get("contact_observed"), bool):
        raise WallContactArtifactError(f"{label}:contact_observed_invalid")
    if not isinstance(summary.get("categories"), list):
        raise WallContactArtifactError(f"{label}:categories_invalid")
    pairs = summary.get("component_wall_summaries")
    if not isinstance(pairs, list):
        raise WallContactArtifactError(f"{label}:component_pairs_invalid")
    for pair in pairs:
        item = mapping(pair, f"{label}:component_pair")
        if (
            str(item.get("component", "")) not in {"boom", "stick", "bucket", "other"}
            or str(item.get("wall_name", "")) not in allowed_walls
        ):
            raise WallContactArtifactError(f"{label}:component_pair_lineage_invalid")
    return summary


def validate_reset_state(value: Mapping[str, Any]) -> None:
    vector(value.get("qpos"), 4, "reset.qpos")
    vector(value.get("qvel"), 4, "reset.qvel")
    vector(value.get("bucket_tip_m"), 3, "reset.bucket_tip_m")
    vector(value.get("terrain_depth_m"), 6, "reset.terrain_depth_m")
    finite(
        value.get("remaining_mass_kg"),
        "reset.remaining_mass_kg",
        minimum=0.0,
    )


def read_primitive_qpos(path: Path) -> tuple[list[list[float]], int, int]:
    with h5py.File(path, "r") as handle:
        qpos = np.asarray(handle["observations/qpos"], dtype=np.float64)
        mask = np.asarray(
            handle["v2/step/action_loss_mask"],
            dtype=np.uint8,
        ).reshape(-1)
    if (
        qpos.ndim != 2
        or qpos.shape[1] != 4
        or qpos.shape[0] != mask.size
        or not np.isfinite(qpos).all()
    ):
        raise WallContactArtifactError(f"primitive_qpos_invalid:{path}")
    valid = np.flatnonzero(mask == 1)
    if not valid.size:
        raise WallContactArtifactError(f"primitive_dig_mask_empty:{path}")
    start, end = int(valid[0]), int(valid[-1])
    return (
        [[float(value) for value in row] for row in qpos[start : end + 1]],
        start,
        end,
    )


def validate_qpos_path(value: Any) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise WallContactArtifactError("qpos_path_invalid")
    return [vector(row, 4, "qpos_path") for row in value]


def qpos_sha256(value: Sequence[Sequence[float]]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def qpos_float32_sha256(value: Sequence[Sequence[float]]) -> str:
    """Return the Unity-v2 canonical row-major little-endian float32 hash."""

    array = np.asarray(value, dtype="<f4")
    if array.ndim != 2 or array.shape[1] != 4 or not np.isfinite(array).all():
        raise WallContactArtifactError("qpos_path_float32_contract_invalid")
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_json_x(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(json_bytes(value))


def write_yaml_x(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(dict(value), handle, sort_keys=False, allow_unicode=True)


def artifact_ref(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve(strict=True)
    return {
        "path": str(source),
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
    }


def artifact_refs_aggregate_sha256(
    references: Sequence[Mapping[str, Any]],
) -> str:
    """Hash an ordered set of exact artifact references."""

    return json_sha256(
        {
            "schema": "ordered_artifact_lineage_v1",
            "artifacts": [dict(item) for item in references],
        }
    )


def locked_ref(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    path = required_file(value.get("path"), label)
    expected = sha256_value(value.get("sha256"), f"{label}.sha256")
    actual = sha256_file(path)
    if actual != expected:
        raise WallContactArtifactError(
            f"{label}_sha256_drift:expected={expected}:actual={actual}"
        )
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": actual,
    }


def load_locked_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    record = locked_ref(value, "locked_artifact")
    return load_json(Path(record["path"]))


def required_file(value: Any, label: str) -> Path:
    path = Path(str(value)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_value(value: Any, label: str) -> str:
    text = str(value).strip().lower()
    if not is_sha256(text):
        raise WallContactArtifactError(f"{label}_invalid")
    return text


def is_sha256(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(char in _SHA_HEX for char in text)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(mapping(value, str(path)))


def load_json_sequence(path: Path) -> list[Mapping[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise WallContactArtifactError(f"JSON list required:{path}")
    return [mapping(item, str(path)) for item in value]


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(mapping(value, str(path)))


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WallContactArtifactError(f"{label}_must_be_mapping")
    return value


def mapping_mut(value: dict[str, Any], key: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise WallContactArtifactError(f"{key}_must_be_mapping")
    return child


def unique_records(
    value: Any,
    *,
    key: str,
    label: str,
    integer_key: bool = False,
) -> dict[Any, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise WallContactArtifactError(f"{label}_invalid")
    result: dict[Any, Mapping[str, Any]] = {}
    for raw in value:
        item = mapping(raw, label)
        identifier: Any = item.get(key)
        if integer_key:
            identifier = int(identifier)
        else:
            identifier = str(identifier)
        if identifier in result:
            raise WallContactArtifactError(f"{label}_duplicate:{identifier}")
        result[identifier] = item
    return result


def integer_list(value: Any, label: str) -> list[int]:
    if not isinstance(value, list):
        raise WallContactArtifactError(f"{label}_invalid")
    return [int(item) for item in value]


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WallContactArtifactError(f"{label}_invalid")
    result = [str(item).strip() for item in value]
    if any(not item for item in result) or result != sorted(set(result)):
        raise WallContactArtifactError(f"{label}_not_canonical")
    return result


def finite(
    value: Any,
    label: str,
    minimum: float | None = None,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise WallContactArtifactError(f"{label}_invalid") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise WallContactArtifactError(f"{label}_invalid")
    return result


def vector(value: Any, width: int, label: str) -> list[float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != width
    ):
        raise WallContactArtifactError(f"{label}_invalid")
    return [finite(item, label) for item in value]


__all__ = [
    "WallContactArtifactError",
    "artifact_ref",
    "artifact_refs_aggregate_sha256",
    "finite",
    "integer_list",
    "is_sha256",
    "json_bytes",
    "json_sha256",
    "load_json",
    "load_json_sequence",
    "load_locked_ref",
    "load_yaml",
    "locked_ref",
    "mapping",
    "mapping_mut",
    "qpos_float32_sha256",
    "qpos_sha256",
    "read_primitive_qpos",
    "required_file",
    "sha256_file",
    "sha256_value",
    "string_list",
    "unique_records",
    "validate_bucket_region_samples",
    "validate_detailed_contact_summary",
    "validate_intervals",
    "validate_qpos_path",
    "validate_reset_state",
    "vector",
    "write_json_x",
    "write_yaml_x",
]
