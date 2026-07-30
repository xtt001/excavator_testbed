"""Integrity helpers for selected, replay-derived terrain episodes.

This module owns HDF5 validation and finalization only.  Runtime orchestration and
semantic replay decisions remain in the CLI/evaluation layers.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.action_contract_calibration import (
    CURRENT_EQUIVALENT_ACTION_CONTRACT,
)
from testbed.data.camera_images import decode_jpeg_rgb

REPLAY_CAMERA_NAMES = ("stick_up", "stick_down", "eye_left", "eye_right")
REPLAY_ENV_STATE_DIM = 89
REPLAY_PROTOCOL_VERSION = "agx-sim/v2"
REPLAY_ENV_STATE_CONTRACT = "agx_env_state_v2_3_89"
REPLAY_TERRAIN_STATE_CONTRACT = "terrain_state_grid_3x2_v1"
REPLAY_TERRAIN_VOLUME_SOURCE = "grid_depth_integral"


def audit_recorded_replay_episode(
    *,
    replay_path: str | Path,
    calibrated_source_path: str | Path,
    expected_steps: int,
    expected_control_compatibility_profile: str | None = None,
    expected_replay_evidence_profile: str | None = None,
    expected_runtime_build_id: str | None = None,
) -> dict[str, Any]:
    """Validate a full replay HDF5 against its calibrated causal prefix."""

    replay = Path(replay_path).expanduser().resolve()
    source = Path(calibrated_source_path).expanduser().resolve()
    errors: list[str] = []
    expected = int(expected_steps)
    if expected <= 0:
        raise ValueError("expected_steps must be positive.")

    env_state_dim: int | None = None
    camera_names: list[str] = []
    recorded_steps: int | None = None
    metadata_summary: dict[str, str] = {}
    try:
        with (
            h5py.File(source, "r") as source_file,
            h5py.File(replay, "r") as replay_file,
        ):
            source_action = _required_dataset(source_file, "action", errors)
            replay_action = _required_dataset(replay_file, "action", errors)
            qpos = _required_dataset(replay_file, "observations/qpos", errors)
            qvel = _required_dataset(replay_file, "observations/qvel", errors)
            env_state = _required_dataset(replay_file, "observations/env_state", errors)
            step_id = _required_dataset(replay_file, "timestamps/step_id", errors)

            if replay_action is not None:
                recorded_steps = int(replay_action.shape[0])
                if recorded_steps != expected:
                    errors.append("step_count_mismatch")
                _check_finite(replay_action, "action_nonfinite", errors)
            if source_action is not None:
                if int(source_action.shape[0]) < expected:
                    errors.append("source_action_too_short")
                _check_finite(source_action, "source_action_nonfinite", errors)
            if replay_action is not None and source_action is not None:
                if replay_action.shape[1:] != source_action.shape[1:]:
                    errors.append("action_shape_mismatch")
                elif int(source_action.shape[0]) >= expected:
                    replay_values = np.asarray(replay_action[()], dtype=np.float32)
                    source_values = np.asarray(
                        source_action[:expected], dtype=np.float32
                    )
                    if not np.array_equal(replay_values, source_values):
                        errors.append("action_prefix_mismatch")

            for name, dataset in (("qpos", qpos), ("qvel", qvel)):
                if dataset is None:
                    continue
                if int(dataset.shape[0]) != expected:
                    errors.append(f"{name}_length_mismatch")
                _check_finite(dataset, f"{name}_nonfinite", errors)

            if env_state is not None:
                if env_state.ndim != 2:
                    errors.append("env_state_rank_mismatch")
                else:
                    env_state_dim = int(env_state.shape[1])
                    if env_state_dim != REPLAY_ENV_STATE_DIM:
                        errors.append("env_state_dim_mismatch")
                if int(env_state.shape[0]) != expected:
                    errors.append("env_state_length_mismatch")
                _check_finite(env_state, "env_state_nonfinite", errors)

            if step_id is not None:
                values = np.asarray(step_id[()], dtype=np.int64).reshape(-1)
                if values.shape[0] != expected:
                    errors.append("step_id_length_mismatch")
                elif values.shape[0] > 1 and not np.all(np.diff(values) == 1):
                    errors.append("step_id_not_contiguous")

            encoded = replay_file.get("observations/encoded_images")
            raw = replay_file.get("observations/images")
            if raw is not None:
                errors.append("raw_camera_layout_not_jpeg")
            if encoded is None:
                errors.append("encoded_camera_group_missing")
            else:
                camera_names = sorted(str(name) for name in encoded.keys())
                if set(camera_names) != set(REPLAY_CAMERA_NAMES):
                    errors.append("camera_set_mismatch")
                for camera in REPLAY_CAMERA_NAMES:
                    if camera not in encoded:
                        continue
                    dataset = encoded[camera]
                    if int(dataset.shape[0]) != expected:
                        errors.append(f"camera_length_mismatch:{camera}")
                        continue
                    encoding = _text(dataset.attrs.get("encoding", ""))
                    if encoding.lower() != "jpeg":
                        errors.append(f"camera_encoding_mismatch:{camera}")
                    _audit_jpeg_sentinels(dataset, camera=camera, errors=errors)

            metadata = replay_file.get("metadata")
            attrs = metadata.attrs if metadata is not None else {}
            required_metadata = {
                "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
                "protocol_version": REPLAY_PROTOCOL_VERSION,
                "env_state_contract_version": REPLAY_ENV_STATE_CONTRACT,
                "terrain_state_contract_version": REPLAY_TERRAIN_STATE_CONTRACT,
                "terrain_volume_source": REPLAY_TERRAIN_VOLUME_SOURCE,
            }
            if expected_control_compatibility_profile is not None:
                required_metadata["replay_control_compatibility_profile"] = str(
                    expected_control_compatibility_profile
                )
            if expected_replay_evidence_profile is not None:
                required_metadata["replay_evidence_profile"] = str(
                    expected_replay_evidence_profile
                )
            for key, expected_value in required_metadata.items():
                actual = _text(attrs.get(key, ""))
                metadata_summary[key] = actual
                if actual != expected_value:
                    errors.append(f"metadata_mismatch:{key}")
            runtime_build_id = _text(attrs.get("runtime_build_id", "")).strip()
            metadata_summary["runtime_build_id"] = runtime_build_id
            if not runtime_build_id:
                errors.append("runtime_build_id_missing")
            if (
                expected_runtime_build_id is not None
                and runtime_build_id != str(expected_runtime_build_id)
            ):
                errors.append("metadata_mismatch:runtime_build_id")
    except (FileNotFoundError, OSError) as exc:
        errors.append(f"hdf5_open_failed:{type(exc).__name__}")

    ordered_cameras = [
        camera for camera in REPLAY_CAMERA_NAMES if camera in set(camera_names)
    ]
    return {
        "schema": "terrain_replay_hdf5_audit_v1",
        "status": "pass" if not errors else "fail",
        "pass": not errors,
        "replay_path": str(replay),
        "calibrated_source_path": str(source),
        "expected_step_count": expected,
        "recorded_step_count": recorded_steps,
        "env_state_dim": env_state_dim,
        "camera_names": ordered_cameras,
        "metadata": metadata_summary,
        "errors": list(dict.fromkeys(errors)),
    }


def apply_source_action_overlays(
    *,
    replay_path: str | Path,
    calibrated_source_path: str | Path,
    replay_qc_mask: np.ndarray,
    local_cycle_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Attach source action lineage while allowing replay QC only to mask more."""

    replay = Path(replay_path).expanduser().resolve()
    source = Path(calibrated_source_path).expanduser().resolve()
    qc_mask = _binary_mask(replay_qc_mask, label="replay_qc_mask")
    local_mask = (
        None
        if local_cycle_mask is None
        else _binary_mask(local_cycle_mask, label="local_cycle_mask")
    )
    with h5py.File(source, "r") as source_file:
        source_action = np.asarray(source_file["action"][()], dtype=np.float32)
        source_length = int(source_action.shape[0])
        source_step = source_file.get("v2/step")
        if source_step is None:
            raise KeyError(f"Calibrated source has no /v2/step group: {source}")
        required = (
            "action_original",
            "action_calibration_valid_mask",
            "action_loss_mask",
        )
        missing = [name for name in required if name not in source_step]
        if missing:
            raise KeyError(
                f"Calibrated source is missing action overlays {missing}: {source}"
            )
        source_original = np.asarray(
            source_step["action_original"][()], dtype=np.float32
        )
        source_calibration_mask = _binary_mask(
            source_step["action_calibration_valid_mask"][()],
            label="source action_calibration_valid_mask",
        )
        source_loss_mask = _binary_mask(
            source_step["action_loss_mask"][()], label="source action_loss_mask"
        )

    with h5py.File(replay, "a") as replay_file:
        replay_action = np.asarray(replay_file["action"][()], dtype=np.float32)
        replay_length = int(replay_action.shape[0])
        if replay_length > source_length:
            raise ValueError("Replay action length exceeds calibrated source length.")
        if qc_mask.shape[0] != replay_length:
            raise ValueError("replay_qc_mask length does not match replay action.")
        if local_mask is not None and local_mask.shape[0] != replay_length:
            raise ValueError("local_cycle_mask length does not match replay action.")
        for label, values in (
            ("action_original", source_original),
            ("action_calibration_valid_mask", source_calibration_mask),
            ("action_loss_mask", source_loss_mask),
        ):
            if values.shape[0] < replay_length:
                raise ValueError(f"Source {label} is shorter than replay action.")
        if not np.array_equal(replay_action, source_action[:replay_length]):
            raise ValueError("Replay action differs from calibrated source prefix.")

        final_mask = source_loss_mask[:replay_length].astype(bool) & qc_mask.astype(
            bool
        )
        if local_mask is not None:
            final_mask &= local_mask.astype(bool)
        final_mask = final_mask.astype(np.uint8)
        step_group = replay_file.require_group("v2").require_group("step")
        payload = {
            "action_original": source_original[:replay_length],
            "action_calibration_valid_mask": source_calibration_mask[:replay_length],
            "source_action_loss_mask": source_loss_mask[:replay_length],
            "replay_qc_mask": qc_mask,
            "action_loss_mask": final_mask,
        }
        if local_mask is not None:
            payload["local_cycle_mask"] = local_mask
        collisions = [name for name in payload if name in step_group]
        if collisions:
            raise FileExistsError(
                f"Replay action overlay datasets already exist: {collisions}"
            )
        for name, values in payload.items():
            step_group.create_dataset(name, data=values)
        metadata = replay_file.require_group("metadata")
        metadata.attrs["action_loss_mask_scope"] = "loss_sampling_stats"
        metadata.attrs["source_action_mask_policy"] = (
            "source_calibrated_and_replay_qc_and_local_cycle_mask_v1"
            if local_mask is not None
            else "source_calibrated_mask_and_replay_qc_mask_v1"
        )

    return {
        "schema": "terrain_replay_action_overlay_v1",
        "step_count": replay_length,
        "valid_step_count": int(np.sum(final_mask)),
        "masked_step_count": int(replay_length - np.sum(final_mask)),
    }


def replay_camera_step_valid_mask(
    replay_path: str | Path,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Return a per-step four-camera JPEG framing mask for local salvage.

    A damaged frame masks only its timestep.  A missing route or a route-length
    mismatch remains visible in the issue list and masks every unavailable step.
    Full semantic decoding is intentionally left to consumers; this check owns
    the cheap, deterministic HDF5/JPEG framing contract used by replay cleaning.
    """

    replay = Path(replay_path).expanduser().resolve(strict=True)
    issues: list[dict[str, Any]] = []
    with h5py.File(replay, "r") as handle:
        steps = int(handle["action"].shape[0])
        valid = np.ones(steps, dtype=np.uint8)
        group = handle.get("observations/encoded_images")
        if group is None or set(group.keys()) != set(REPLAY_CAMERA_NAMES):
            valid[:] = 0
            issues.append({"reason": "missing_complete_four_camera_jpeg_route"})
            return valid, issues
        for camera in REPLAY_CAMERA_NAMES:
            dataset = group[camera]
            route_steps = int(dataset.shape[0])
            if route_steps != steps:
                valid[min(route_steps, steps) :] = 0
                issues.append(
                    {
                        "reason": "camera_length_mismatch",
                        "camera": camera,
                        "expected": steps,
                        "actual": route_steps,
                    }
                )
            for index in range(min(steps, route_steps)):
                frame = np.asarray(dataset[index], dtype=np.uint8).reshape(-1)
                if (
                    frame.size < 4
                    or bytes(frame[:2]) != b"\xff\xd8"
                    or bytes(frame[-2:]) != b"\xff\xd9"
                ):
                    valid[index] = 0
                    issues.append(
                        {
                            "reason": "jpeg_frame_invalid",
                            "camera": camera,
                            "step": index,
                        }
                    )
    return valid, issues


def select_first_passing_attempt(
    attempts: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Return the first passing attempt in execution order, without rescoring."""

    for attempt in attempts:
        if bool(attempt.get("pass", False)):
            return dict(attempt)
    return None


def annotate_selected_replay_episode(
    *,
    replay_path: str | Path,
    source_episode_id: str,
    calibrated_source_path: str | Path,
    attempt_id: str,
    selection_policy: str = "first_passing_attempt_v1",
    evidence_kind: str = "replay_derived_selected_pass",
    repeatability_status: str = "not_assessed_single_attempt",
    gold_status: str = "not_gold",
) -> dict[str, Any]:
    """Seal selected-replay lineage and evidence semantics into metadata."""

    replay = Path(replay_path).expanduser().resolve()
    calibrated = Path(calibrated_source_path).expanduser().resolve()
    with h5py.File(calibrated, "r") as source_file:
        source_metadata = source_file["metadata"].attrs
        raw_source = _text(source_metadata.get("raw_source_realpath", ""))
        clean_source = _text(source_metadata.get("vds_source_abs_path", ""))
    with h5py.File(replay, "a") as replay_file:
        metadata = replay_file.require_group("metadata")
        updates = {
            "episode_id": str(source_episode_id),
            "source_episode_id": str(source_episode_id),
            "selection_policy": str(selection_policy),
            "evidence_kind": str(evidence_kind),
            "repeatability_status": str(repeatability_status),
            "gold_status": str(gold_status),
            "selection_attempt_id": str(attempt_id),
            "calibrated_source_realpath": str(calibrated),
            "raw_source_realpath": raw_source,
            "clean_source_realpath": clean_source,
            "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
            "planner_fields_status": "missing_not_generated_by_replay",
            "volume_label_status": "derived_grid_integral",
            "direct_volume_status": "unavailable_no_sensor",
        }
        for key, value in updates.items():
            metadata.attrs[key] = value
    return {
        "schema": "terrain_replay_selected_metadata_v1",
        "source_episode_id": str(source_episode_id),
        "attempt_id": str(attempt_id),
        "replay_path": str(replay),
        "calibrated_source_realpath": str(calibrated),
        "raw_source_realpath": raw_source,
        "clean_source_realpath": clean_source,
    }


def safe_remove_failed_attempt_hdf5(
    *,
    path: str | Path,
    attempts_root: str | Path,
    expected_sha256: str | None = None,
    expected_size_bytes: int | None = None,
) -> dict[str, Any]:
    """Remove one generated failed-attempt HDF5 after strict path containment."""

    root = Path(attempts_root).expanduser().resolve(strict=True)
    target = Path(path).expanduser().resolve(strict=True)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"HDF5 is outside attempts root: {target}") from exc
    if relative == Path(".") or target.suffix.lower() != ".hdf5":
        raise ValueError(f"Refusing to remove non-attempt HDF5 target: {target}")
    if not target.is_file():
        raise ValueError(f"Failed-attempt target is not a regular file: {target}")
    size_bytes = int(target.stat().st_size)
    if expected_size_bytes is not None and size_bytes != int(expected_size_bytes):
        raise ValueError("Failed-attempt HDF5 size changed after deletion intent.")
    digest = (
        str(expected_sha256) if expected_sha256 is not None else sha256_file(target)
    )
    if expected_sha256 is not None and sha256_file(target) != str(expected_sha256):
        raise ValueError("Failed-attempt HDF5 hash changed after deletion intent.")
    target.unlink()
    return {
        "schema": "terrain_replay_failed_hdf5_removal_v1",
        "path": str(target),
        "relative_path": str(relative),
        "size_bytes": size_bytes,
        "sha256": digest,
        "removed": True,
    }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_dataset(
    handle: h5py.File, name: str, errors: list[str]
) -> h5py.Dataset | None:
    value = handle.get(name)
    if not isinstance(value, h5py.Dataset):
        errors.append(f"dataset_missing:{name}")
        return None
    if value.ndim < 1:
        errors.append(f"dataset_rank_invalid:{name}")
        return None
    return value


def _check_finite(dataset: h5py.Dataset, error: str, errors: list[str]) -> None:
    if not np.issubdtype(dataset.dtype, np.number):
        errors.append(error)
        return
    block = max(1, min(8192, int(dataset.shape[0])))
    for start in range(0, int(dataset.shape[0]), block):
        if not np.isfinite(np.asarray(dataset[start : start + block])).all():
            errors.append(error)
            return


def _audit_jpeg_sentinels(
    dataset: h5py.Dataset, *, camera: str, errors: list[str]
) -> None:
    length = int(dataset.shape[0])
    if length == 0:
        errors.append(f"camera_empty:{camera}")
        return
    indices = sorted({0, length // 2, length - 1})
    for index in indices:
        frame = np.asarray(dataset[index], dtype=np.uint8).reshape(-1)
        if frame.size == 0:
            errors.append(f"camera_jpeg_empty:{camera}:{index}")
            continue
        try:
            image = decode_jpeg_rgb(frame)
        except (TypeError, ValueError):
            errors.append(f"camera_jpeg_invalid:{camera}:{index}")
            continue
        if image.ndim != 3 or image.shape[-1] != 3:
            errors.append(f"camera_jpeg_shape_invalid:{camera}:{index}")


def _binary_mask(values: Any, *, label: str) -> np.ndarray:
    mask = np.asarray(values, dtype=np.uint8).reshape(-1)
    if not np.all((mask == 0) | (mask == 1)):
        raise ValueError(f"{label} must contain only 0 or 1.")
    return mask


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


__all__ = [
    "CURRENT_EQUIVALENT_ACTION_CONTRACT",
    "REPLAY_CAMERA_NAMES",
    "REPLAY_ENV_STATE_CONTRACT",
    "REPLAY_ENV_STATE_DIM",
    "REPLAY_PROTOCOL_VERSION",
    "REPLAY_TERRAIN_STATE_CONTRACT",
    "REPLAY_TERRAIN_VOLUME_SOURCE",
    "annotate_selected_replay_episode",
    "apply_source_action_overlays",
    "audit_recorded_replay_episode",
    "replay_camera_step_valid_mask",
    "safe_remove_failed_attempt_hdf5",
    "select_first_passing_attempt",
    "sha256_file",
]
