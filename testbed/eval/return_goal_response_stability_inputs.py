"""Input-contract evidence for the Return response-stability audit.

The functions in this module verify what is fed to the frozen checkpoint: the
canonical training proprio vector, pre-action qpos/qvel/image rows, configured
camera order, and the public runtime image transformation.  They do not load a
model or classify a goal response.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.act_low_dim import assemble_act_low_dim_observation
from testbed.data.recorded_act_replay import read_recorded_act_observation
from testbed.eval.return_goal_response_stability_contract import (
    ReturnGoalResponseStabilityAuditError,
    field,
    finite_vector,
    integer_field,
)


def audit_return_token_normalisation(
    *,
    observations: Sequence[Mapping[str, Any]],
    token: np.ndarray,
    low_dim_keys: Sequence[str],
    norm_stats: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare canonical training assembly with runtime ordered proprio input."""

    keys = tuple(str(value) for value in low_dim_keys)
    expected = ("qpos", "qvel", "return_start_envelope_tokens_v1")
    if keys != expected:
        raise ReturnGoalResponseStabilityAuditError(
            f"Return low_dim_keys must be {expected!r}, got {keys!r}"
        )
    stats_keys = tuple(
        _text(value)
        for value in np.asarray(norm_stats.get("proprio_keys", ())).reshape(-1)
    )
    if stats_keys != keys:
        raise ReturnGoalResponseStabilityAuditError(
            f"dataset_stats proprio_keys {stats_keys!r} disagree with Return config {keys!r}"
        )
    mean = finite_vector(norm_stats.get("proprio_mean"), label="proprio_mean")
    std = finite_vector(norm_stats.get("proprio_std"), label="proprio_std")
    if mean.shape != std.shape or np.any(std <= 0.0):
        raise ReturnGoalResponseStabilityAuditError("dataset_stats proprio std is invalid")
    if int(norm_stats.get("proprio_dim", -1)) != int(mean.size):
        raise ReturnGoalResponseStabilityAuditError("dataset_stats proprio_dim disagrees with stats vectors")
    condition = finite_vector(token, label="return alternate token")
    if condition.shape != (18,):
        raise ReturnGoalResponseStabilityAuditError(
            f"Return alternate token must have width 18, got {condition.shape}"
        )

    training_rows: list[np.ndarray] = []
    runtime_rows: list[np.ndarray] = []
    for index, observation in enumerate(observations):
        qpos = finite_vector(observation.get("qpos"), label=f"observation[{index}].qpos")
        qvel = finite_vector(observation.get("qvel"), label=f"observation[{index}].qvel")
        if qpos.shape != (4,) or qvel.shape != (4,):
            raise ReturnGoalResponseStabilityAuditError(
                "Return qpos/qvel must each have width 4"
            )
        training_rows.append(
            assemble_act_low_dim_observation(
                qpos=qpos,
                qvel=qvel,
                return_start_envelope_tokens_v1=condition,
                low_dim_keys=keys,
            )
        )
        runtime_rows.append(
            runtime_proprio_from_observation(
                observation=observation,
                token=condition,
                low_dim_keys=keys,
            )
        )
    if not training_rows:
        raise ReturnGoalResponseStabilityAuditError("Return segment has no observations")
    training = np.stack(training_rows, axis=0)
    runtime = np.stack(runtime_rows, axis=0)
    if training.shape[1] != mean.size:
        raise ReturnGoalResponseStabilityAuditError(
            "assembled Return proprio width disagrees with dataset_stats"
        )
    normalised_training = (training - mean[None, :]) / std[None, :]
    normalised_runtime = (runtime - mean[None, :]) / std[None, :]
    raw_delta = float(np.max(np.abs(training - runtime)))
    normalised_delta = float(
        np.max(np.abs(normalised_training - normalised_runtime))
    )
    token_start = 8
    token_stop = token_start + condition.size
    return {
        "status": "passed" if raw_delta == 0.0 and normalised_delta == 0.0 else "mismatch",
        "training_assembly": "testbed.data.act_low_dim.assemble_act_low_dim_observation",
        "runtime_assembly": "ACTAdapter ordered low_dim concatenation",
        "low_dim_keys": list(keys),
        "proprio_dim": int(mean.size),
        "frame_count": int(training.shape[0]),
        "token_slice": {"start": token_start, "stop": token_stop},
        "raw_proprio_max_abs_delta": raw_delta,
        "normalised_proprio_max_abs_delta": normalised_delta,
        "token_normalised_min": float(np.min(normalised_runtime[:, token_start:token_stop])),
        "token_normalised_max": float(np.max(normalised_runtime[:, token_start:token_stop])),
    }


def audit_pre_action_observation_identity(
    *,
    hdf5_file: h5py.File,
    frames: Sequence[Any],
    camera_names: Sequence[str],
    image_mask_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify every recorded model observation comes from the prior action row.

    The public ACT image preprocessor is imported lazily to keep the data-only
    alignment checks usable in environments that do not import torch.  Its
    digest records the exact post-mask/order/layout/scale/ImageNet-normalised
    tensor supplied to ACT inference.
    """

    from testbed.policies.act.image_preprocessing import (
        ACT_IMAGE_INPUT_LAYOUT_HWC,
        ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
        normalize_act_image_tensor,
        preprocess_act_observation_images,
        transform_act_camera_images,
    )

    names = tuple(str(value) for value in camera_names)
    if not names or len(names) != len(set(names)):
        raise ReturnGoalResponseStabilityAuditError("camera_names must be non-empty and unique")
    step_ids = np.asarray(hdf5_file["timestamps/step_id"][:], dtype=np.int64)
    qpos_digest = hashlib.sha256()
    qvel_digest = hashlib.sha256()
    combined_digest = hashlib.sha256()
    raw_camera_digests = {name: hashlib.sha256() for name in names}
    transformed_digest = hashlib.sha256()
    normalized_digest = hashlib.sha256()
    training_transformed_digest = hashlib.sha256()
    training_normalized_digest = hashlib.sha256()
    training_runtime_image_max_abs_delta = 0.0
    previous_action: int | None = None
    for index, frame in enumerate(frames):
        action_step = integer_field(frame, "action_step_id")
        observation_step = integer_field(frame, "observation_step_id")
        action_index = integer_field(frame, "action_hdf5_index")
        observation_index = integer_field(frame, "observation_hdf5_index")
        if observation_step != action_step - 1 or observation_index != action_index - 1:
            raise ReturnGoalResponseStabilityAuditError(
                f"frame {index} is not bound to its pre-action observation"
            )
        if previous_action is not None and action_step != previous_action + 1:
            raise ReturnGoalResponseStabilityAuditError("target Return action steps are not contiguous")
        if not (0 <= observation_index < step_ids.size and 0 <= action_index < step_ids.size):
            raise ReturnGoalResponseStabilityAuditError("replay frame has an out-of-range HDF5 index")
        if int(step_ids[observation_index]) != observation_step or int(step_ids[action_index]) != action_step:
            raise ReturnGoalResponseStabilityAuditError("HDF5 step ids disagree with replay frame")
        stored_qpos = finite_vector(
            hdf5_file["observations/qpos"][observation_index],
            label=f"frame[{index}].stored_qpos",
        )
        stored_qvel = finite_vector(
            hdf5_file["observations/qvel"][observation_index],
            label=f"frame[{index}].stored_qvel",
        )
        frame_qpos = finite_vector(field(frame, "qpos", None), label=f"frame[{index}].qpos")
        frame_qvel = finite_vector(field(frame, "qvel", None), label=f"frame[{index}].qvel")
        if not np.array_equal(stored_qpos, frame_qpos) or not np.array_equal(stored_qvel, frame_qvel):
            raise ReturnGoalResponseStabilityAuditError(
                f"frame {index} qpos/qvel do not match HDF5 pre-action row"
            )
        observation = read_recorded_act_observation(
            hdf5_file=hdf5_file,
            frame=frame,
            camera_names=names,
        )
        if not np.array_equal(np.asarray(observation["qpos"]), stored_qpos) or not np.array_equal(
            np.asarray(observation["qvel"]), stored_qvel
        ):
            raise ReturnGoalResponseStabilityAuditError(
                f"frame {index} reader did not preserve pre-action qpos/qvel"
            )
        image_result = preprocess_act_observation_images(
            observation,
            camera_names=names,
            image_mask_config=dict(image_mask_config or {}),
            method_name="Return stability image contract",
        )
        training_result = transform_act_camera_images(
            camera_images={
                name: image
                for name, image in zip(
                    names,
                    image_result.raw_camera_images,
                    strict=True,
                )
            },
            camera_names=names,
            image_mask_config=dict(image_mask_config or {}),
            method_name="Return stability training image contract",
            value_scaling=ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
            input_layout=ACT_IMAGE_INPUT_LAYOUT_HWC,
        )
        training_normalized = normalize_act_image_tensor(
            _as_torch_batch(training_result.transformed_images)
        )
        training_runtime_image_max_abs_delta = max(
            training_runtime_image_max_abs_delta,
            float(
                np.max(
                    np.abs(
                        _to_numpy(image_result.normalized_images)
                        - _to_numpy(training_normalized)
                    )
                )
            ),
        )
        _hash_array(qpos_digest, stored_qpos)
        _hash_array(qvel_digest, stored_qvel)
        _hash_array(combined_digest, np.asarray([action_step, observation_step], dtype=np.int64))
        _hash_array(combined_digest, stored_qpos)
        _hash_array(combined_digest, stored_qvel)
        for name, image in zip(names, image_result.raw_camera_images, strict=True):
            _hash_array(raw_camera_digests[name], np.asarray(image))
            _hash_array(combined_digest, np.asarray(image))
        _hash_array(transformed_digest, np.asarray(image_result.transformed_images))
        _hash_array(normalized_digest, _to_numpy(image_result.normalized_images))
        _hash_array(training_transformed_digest, np.asarray(training_result.transformed_images))
        _hash_array(training_normalized_digest, _to_numpy(training_normalized))
        previous_action = action_step
    image_parity_passed = training_runtime_image_max_abs_delta == 0.0
    return {
        "status": "passed" if image_parity_passed else "mismatch",
        "frame_count": len(frames),
        "camera_names": list(names),
        "alignment_relation": "action_observation_step_id_delta_one",
        "history_contract": "one recorded pre-action observation per dispatched action",
        "qpos_sequence_sha256": qpos_digest.hexdigest(),
        "qvel_sequence_sha256": qvel_digest.hexdigest(),
        "raw_camera_sequence_sha256": {
            name: digest.hexdigest() for name, digest in raw_camera_digests.items()
        },
        "model_input_image_sequence_sha256": {
            "post_mask_layout_scale": transformed_digest.hexdigest(),
            "post_imagenet_normalisation": normalized_digest.hexdigest(),
        },
        "training_image_sequence_sha256": {
            "post_mask_layout_scale": training_transformed_digest.hexdigest(),
            "post_imagenet_normalisation": training_normalized_digest.hexdigest(),
        },
        "training_runtime_image_max_abs_delta": training_runtime_image_max_abs_delta,
        "image_preprocessing_contract": {
            "public_helper": "testbed.policies.act.image_preprocessing.preprocess_act_observation_images",
            "camera_order": list(names),
            "steps": "mask, HWC-to-CHW, uint8-to-unit-scale, ImageNet-normalise",
            "runtime_value_scaling": image_result.value_scaling,
            "runtime_input_layout": image_result.input_layout,
            "training_value_scaling": ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
            "training_input_layout": ACT_IMAGE_INPUT_LAYOUT_HWC,
            "training_runtime_shared_helper": True,
        },
        "combined_observation_sequence_sha256": combined_digest.hexdigest(),
    }


def audit_pre_action_observation_identity_from_path(
    *,
    hdf5_path: str | Path,
    frames: Sequence[Any],
    camera_names: Sequence[str],
    image_mask_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Open one immutable HDF5 source and perform the pre-action identity audit."""

    with h5py.File(hdf5_path, "r") as handle:
        return audit_pre_action_observation_identity(
            hdf5_file=handle,
            frames=frames,
            camera_names=camera_names,
            image_mask_config=image_mask_config,
        )


def read_segment_observations_from_path(
    *,
    hdf5_path: str | Path,
    segment: Any,
    camera_names: Sequence[str],
) -> list[dict[str, np.ndarray]]:
    """Read model-ready observations in the fixed segment order, without policy state."""

    with h5py.File(hdf5_path, "r") as handle:
        return [
            read_recorded_act_observation(
                hdf5_file=handle,
                frame=frame,
                camera_names=camera_names,
            )
            for frame in segment.frames
        ]


def runtime_proprio_from_observation(
    *,
    observation: Mapping[str, Any],
    token: np.ndarray,
    low_dim_keys: Sequence[str],
) -> np.ndarray:
    """Mirror the public ACT ordered concatenation without accessing adapter internals."""

    values: list[np.ndarray] = []
    for key in low_dim_keys:
        value = token if key == "return_start_envelope_tokens_v1" else observation.get(key)
        values.append(finite_vector(value, label=f"runtime {key}"))
    return np.concatenate(values, axis=0).astype(np.float32)


def _hash_array(digest: Any, value: np.ndarray) -> None:
    array = np.ascontiguousarray(value)
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
    digest.update(array.tobytes())


def _to_numpy(value: Any) -> np.ndarray:
    detached = value.detach() if hasattr(value, "detach") else value
    cpu = detached.cpu() if hasattr(detached, "cpu") else detached
    return np.asarray(cpu)


def _as_torch_batch(value: np.ndarray):
    import torch

    return torch.from_numpy(np.asarray(value)).float().unsqueeze(0)


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


__all__ = [
    "audit_pre_action_observation_identity",
    "audit_pre_action_observation_identity_from_path",
    "audit_return_token_normalisation",
    "read_segment_observations_from_path",
    "runtime_proprio_from_observation",
]
