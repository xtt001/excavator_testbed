"""Read-only variant and observation access for the Dig dispatch diagnostic."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import h5py
import numpy as np

from testbed.data.camera_images import (
    camera_names_from_metadata,
    encoded_frame_to_uint8,
    read_camera_rgb,
)
from testbed.eval.dig_receding_horizon_lineage import (
    AuthoritativeDigDispatchLineage,
    DiagnosticLineageError,
    select_source_episode_balanced_variants,
    validate_planner_variant,
)


def read_dispatch_observation(
    hdf5_file: h5py.File,
    *,
    frame_index: int,
    camera_order: Sequence[str],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Read one model observation and hash its exact stored state/camera bytes."""
    index = int(frame_index)
    if index < 0:
        raise ValueError("observation frame index must be non-negative")
    requested = tuple(str(value) for value in camera_order)
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("requested camera order is invalid")
    metadata = dict(hdf5_file["metadata"].attrs) if "metadata" in hdf5_file else {}
    recorded = tuple(camera_names_from_metadata(metadata))
    if recorded != requested:
        raise ValueError(
            f"recorded camera order differs: recorded={recorded}, requested={requested}"
        )
    qpos = _frame_vector(hdf5_file, "observations/qpos", index)
    qvel = _frame_vector(hdf5_file, "observations/qvel", index)
    observation: dict[str, np.ndarray] = {
        "qpos": qpos.copy(),
        "qvel": qvel.copy(),
    }
    camera_hashes: dict[str, str] = {}
    camera_storage: dict[str, str] = {}
    for camera in requested:
        observation[f"image_{camera}"] = read_camera_rgb(hdf5_file, camera, index)
        camera_hashes[camera], camera_storage[camera] = _camera_frame_identity(
            hdf5_file, camera, index
        )
    components = {
        "frame_index": index,
        "low_dim_order": ["qpos", "qvel"],
        "camera_order": list(requested),
        "qpos_sha256": _array_sha256(qpos),
        "qvel_sha256": _array_sha256(qvel),
        "camera_frame_sha256": camera_hashes,
        "camera_storage": camera_storage,
    }
    return observation, {
        **components,
        "observation_sha256": _json_sha256(components),
    }


def load_and_select_supported_variants(
    lineage: AuthoritativeDigDispatchLineage,
    *,
    count: int,
    horizon: int = 100,
) -> list[dict[str, Any]]:
    """Select balanced, unique episodes after all request-local support checks."""
    if horizon != 100:
        raise ValueError("Dig dispatch observation horizon is frozen at 100")
    records_by_episode: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with lineage.variant_jsonl.path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise DiagnosticLineageError(
                    f"variant_jsonl_row_not_mapping:{line_number}"
                )
            source = int(value["source_episode_id"])
            if (
                source not in lineage.dynamics_eligible_source_ids
                or source in (33, 34)
                or value.get("variant_type") != "position_translation"
            ):
                continue
            records_by_episode[int(value["primitive_episode_id"])].append(dict(value))

    candidates: list[dict[str, Any]] = []
    for episode_id in sorted(records_by_episode):
        episode_path = lineage.dataset_dir / f"episode_{episode_id}.hdf5"
        if not episode_path.is_file():
            raise DiagnosticLineageError(f"dataset_episode_missing:{episode_path}")
        with h5py.File(episode_path, "r") as hdf5_file:
            _validate_episode_camera_inventory(hdf5_file, lineage.camera_order)
            selected = None
            for value in sorted(
                records_by_episode[episode_id], key=lambda row: str(row["variant_id"])
            ):
                start = int(value["frame_index"])
                stop = start + horizon
                qpos = np.asarray(
                    hdf5_file["observations/qpos"][start:stop], dtype=np.float32
                )
                qvel = np.asarray(
                    hdf5_file["observations/qvel"][start:stop], dtype=np.float32
                )
                if qpos.shape != (horizon, 4) or qvel.shape != (horizon, 4):
                    continue
                validation = validate_planner_variant(
                    value,
                    qpos=qpos,
                    qvel=qvel,
                    support_p01=lineage.support_p01,
                    support_p99=lineage.support_p99,
                    valid_cell_ids=lineage.valid_cell_ids,
                )
                if validation["valid"]:
                    selected = {
                        **value,
                        "request_local_validation": validation,
                        "dataset_path": str(episode_path.resolve()),
                        "observation_frame_indices": list(range(start, stop)),
                    }
                    break
            if selected is not None:
                candidates.append(selected)
    selected = select_source_episode_balanced_variants(
        candidates,
        count=count,
        eligible_source_ids=lineage.dynamics_eligible_source_ids,
        minimum_episodes_per_source=8,
    )
    if len({int(row["primitive_episode_id"]) for row in selected}) != len(selected):
        raise DiagnosticLineageError("selected_variant_episode_overlap")
    if {int(row["source_episode_id"]) for row in selected} & {33, 34}:
        raise DiagnosticLineageError("source_33_34_selected")
    return selected


def combined_state_lineage_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    values = [
        {
            "variant_id": str(row["variant_id"]),
            "arm": str(row["arm"]),
            "frame_index": int(row["frame_index"]),
            "observation_sha256": str(row["observation_sha256"]),
        }
        for row in rows
    ]
    return _json_sha256(values)


def _validate_episode_camera_inventory(
    hdf5_file: h5py.File, camera_order: Sequence[str]
) -> None:
    metadata = dict(hdf5_file["metadata"].attrs) if "metadata" in hdf5_file else {}
    recorded = tuple(camera_names_from_metadata(metadata))
    requested = tuple(str(value) for value in camera_order)
    if recorded != requested:
        raise DiagnosticLineageError("dataset_camera_order_mismatch")
    for camera in requested:
        raw = f"observations/images/{camera}" in hdf5_file
        encoded = f"observations/encoded_images/{camera}" in hdf5_file
        if raw == encoded:
            raise DiagnosticLineageError(
                f"dataset_camera_storage_invalid:{camera}:raw={raw}:encoded={encoded}"
            )


def _frame_vector(hdf5_file: h5py.File, path: str, index: int) -> np.ndarray:
    if path not in hdf5_file or index >= hdf5_file[path].shape[0]:
        raise ValueError(f"observation frame missing: {path}[{index}]")
    value = np.asarray(hdf5_file[path][index], dtype=np.float32).reshape(-1)
    if value.shape != (4,) or not np.isfinite(value).all():
        raise ValueError(f"observation frame is not finite 4D: {path}[{index}]")
    return value


def _camera_frame_identity(
    hdf5_file: h5py.File, camera: str, index: int
) -> tuple[str, str]:
    raw_path = f"observations/images/{camera}"
    encoded_path = f"observations/encoded_images/{camera}"
    if raw_path in hdf5_file and encoded_path not in hdf5_file:
        return _array_sha256(np.asarray(hdf5_file[raw_path][index])), "raw_rgb"
    if encoded_path in hdf5_file and raw_path not in hdf5_file:
        encoded = encoded_frame_to_uint8(hdf5_file[encoded_path][index])
        return hashlib.sha256(encoded.tobytes()).hexdigest(), "jpeg"
    raise ValueError(f"camera storage is missing or ambiguous: {camera}")


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "combined_state_lineage_sha256",
    "load_and_select_supported_variants",
    "read_dispatch_observation",
]
