"""Source-safe Return data population for temporal-dispatch validation.

This module owns the *data boundary* for an offline comparison of frozen ACT
temporal-dispatch policies.  It deliberately does not load a checkpoint,
advance an ACT cache, choose a dispatch strategy, write an artifact, or accept
a Stage-A target rollout.  Its inputs are only the canonical strict Return
training configuration and the source-disjoint split named by that config.

The public population keeps complete ``qpos + qvel +
return_start_envelope_tokens_v1`` rows, expert actions, provenance, and a
read-only training-observation reader.  The reader follows the actual
``EpisodicDataset`` contract for this simulated dataset: the observation at
row ``t`` is the pre-dispatch origin for the action chunk beginning at row
``t``.  It intentionally does *not* borrow the recorded-rollout ``t - 1``
alignment rule, which belongs to a different storage contract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np
import yaml

from testbed.data.act_low_dim import assemble_act_low_dim_observation
from testbed.data.act_support_contract import (
    StrictSourceAwareSupportRows,
    SupportRowProvenance,
    load_strict_source_aware_support_rows,
)
from testbed.data.action_loss_mask import (
    ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
    read_action_loss_mask,
)
from testbed.data.camera_images import (
    JPEG_ENCODING,
    camera_names_from_metadata,
    read_camera_rgb,
    validate_exclusive_camera_layout,
)
from testbed.data.return_temporal_dispatch_reference import (
    ReturnTemporalActionReference,
    build_strict_return_temporal_action_reference,
)
from testbed.data.schema import DS_STEP_ID

RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA = "return_temporal_dispatch_validation_population_v1"
"""Stable schema for the source-safe Return temporal-dispatch population."""
RETURN_LOW_DIM_KEYS = ("qpos", "qvel", "return_start_envelope_tokens_v1")
RETURN_FEATURE_ORDER = tuple(
    [f"qpos[{index}]" for index in range(4)] + [f"qvel[{index}]" for index in range(4)]
    + [f"return_start_envelope_tokens_v1[{index}]" for index in range(18)]
)
class ReturnTemporalDispatchValidationError(ValueError):
    """Raised when the source-safe Return validation population is invalid."""


@dataclass(frozen=True)
class ReturnTemporalDispatchStorageContract:
    """Verified representation facts shared by all selected Return episodes."""

    qpos_dtype: str
    qvel_dtype: str
    token_dtype: str
    action_dtype: str
    step_id_dtype: str
    qpos_order: tuple[str, ...]
    qvel_order: tuple[str, ...]
    action_order: tuple[str, ...]
    camera_storage: Literal["raw_rgb", "jpeg"]
    observation_action_alignment: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "qpos_dtype": self.qpos_dtype,
            "qvel_dtype": self.qvel_dtype,
            "token_dtype": self.token_dtype,
            "action_dtype": self.action_dtype,
            "step_id_dtype": self.step_id_dtype,
            "qpos_order": list(self.qpos_order),
            "qvel_order": list(self.qvel_order),
            "action_order": list(self.action_order),
            "camera_storage": self.camera_storage,
            "observation_action_alignment": self.observation_action_alignment,
        }


@dataclass(frozen=True)
class ReturnTemporalDispatchFrame:
    """One action-supervised Return row and its training observation origin."""

    provenance: SupportRowProvenance
    hdf5_path: str
    action_index: int
    observation_index: int
    action_step_id: int
    observation_step_id: int
    qpos: np.ndarray
    qvel: np.ndarray
    token: np.ndarray
    expert_action: np.ndarray

    @property
    def feature(self) -> np.ndarray:
        """Return the canonical frozen 26D model input for this row."""

        return _freeze(
            assemble_act_low_dim_observation(
                qpos=self.qpos,
                qvel=self.qvel,
                return_start_envelope_tokens_v1=self.token,
                low_dim_keys=RETURN_LOW_DIM_KEYS,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "provenance": self.provenance.as_dict(),
            "hdf5_path": self.hdf5_path,
            "action_index": self.action_index,
            "observation_index": self.observation_index,
            "action_step_id": self.action_step_id,
            "observation_step_id": self.observation_step_id,
            "qpos": _float_list(self.qpos),
            "qvel": _float_list(self.qvel),
            "return_start_envelope_tokens_v1": _float_list(self.token),
            "expert_action": _float_list(self.expert_action),
        }


@dataclass(frozen=True)
class ReturnTemporalDispatchSegment:
    """A contiguous held-validation stream with a stable real Return token."""

    primitive_episode_id: int
    source_episode_id: int
    token: np.ndarray
    token_sha256: str
    frames: tuple[ReturnTemporalDispatchFrame, ...]

    @property
    def segment_id(self) -> str:
        return (
            "return-validation:"
            f"{self.primitive_episode_id}:"
            f"{self.frames[0].action_step_id}-{self.frames[-1].action_step_id}:"
            f"{self.token_sha256[:12]}"
        )

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "primitive_episode_id": self.primitive_episode_id,
            "source_episode_id": self.source_episode_id,
            "token_sha256": self.token_sha256,
            "frame_count": self.frame_count,
            "start_action_step_id": self.frames[0].action_step_id,
            "end_action_step_id": self.frames[-1].action_step_id,
        }


@dataclass(frozen=True)
class ReturnTemporalDispatchValidationPopulation:
    """Strict Return train facts plus held-validation replay rows and segments."""

    schema: str
    feature_order: tuple[str, ...]
    model_token_key: str
    camera_names: tuple[str, ...]
    storage_contract: ReturnTemporalDispatchStorageContract
    training_config_path: str
    primitive_dataset_dir: str
    split_path: str
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    train_frames: tuple[ReturnTemporalDispatchFrame, ...]
    validation_frames: tuple[ReturnTemporalDispatchFrame, ...]
    validation_segments: tuple[ReturnTemporalDispatchSegment, ...]
    action_reference: ReturnTemporalActionReference

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "skill_name": "return",
            "model_token_key": self.model_token_key,
            "feature_order": list(self.feature_order),
            "camera_names": list(self.camera_names),
            "storage_contract": self.storage_contract.as_dict(),
            "training_config_path": self.training_config_path,
            "primitive_dataset_dir": self.primitive_dataset_dir,
            "split_path": self.split_path,
            "train_source_episode_ids": list(self.train_source_episode_ids),
            "validation_source_episode_ids": list(self.validation_source_episode_ids),
            "strict_train_row_count": len(self.train_frames),
            "held_validation_row_count": len(self.validation_frames),
            "held_validation_segment_count": len(self.validation_segments),
            "action_reference": self.action_reference.as_dict(),
        }


@dataclass(frozen=True)
class ReturnValidationCounterfactualPair:
    """One held-validation segment paired with another real held token."""

    baseline_segment: ReturnTemporalDispatchSegment
    alternate_token: np.ndarray
    alternate_token_sha256: str
    alternate_token_source_episode_id: int
    alternate_token_primitive_episode_id: int
    alternate_token_segment_id: str

    @property
    def baseline_token_sha256(self) -> str:
        """Return the source-held token identity for concise evaluator use."""

        return self.baseline_segment.token_sha256

    @property
    def pair_id(self) -> str:
        return f"{self.baseline_segment.segment_id}->token:{self.alternate_token_sha256[:12]}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "baseline_segment_id": self.baseline_segment.segment_id,
            "baseline_token_sha256": self.baseline_segment.token_sha256,
            "alternate_token_sha256": self.alternate_token_sha256,
            "alternate_token_source_episode_id": self.alternate_token_source_episode_id,
            "alternate_token_primitive_episode_id": self.alternate_token_primitive_episode_id,
            "alternate_token_segment_id": self.alternate_token_segment_id,
            "alternate_token": _float_list(self.alternate_token),
        }


def load_strict_return_temporal_dispatch_validation_population(
    *,
    training_config_path: str | Path,
) -> ReturnTemporalDispatchValidationPopulation:
    """Load strict Return train facts and source-disjoint validation replay rows.

    No target rollout parameter is accepted.  The base support loader validates
    the exact split and retains only ``action_loss_mask == 1`` rows; this
    function then re-reads those same rows to add expert actions, image access,
    per-episode representation validation, and temporal continuity.
    """

    config_path = Path(training_config_path).expanduser().resolve(strict=True)
    config = _read_yaml_mapping(config_path)
    _validate_return_config(config)
    camera_names = _camera_names(config)
    numeric = load_strict_source_aware_support_rows(
        training_config_path=config_path,
        skill_name="return",
    )
    _validate_numeric_rows(numeric)
    dataset_dir = Path(numeric.primitive_dataset_dir).resolve(strict=True)

    frames_by_partition: dict[str, list[ReturnTemporalDispatchFrame]] = {
        "train": [],
        "validation": [],
    }
    contracts: list[ReturnTemporalDispatchStorageContract] = []
    for partition, expected, partition_features in (
        ("train", numeric.train_provenance, numeric.train_features),
        ("validation", numeric.validation_provenance, numeric.validation_features),
    ):
        grouped = _group_provenance_by_episode(expected)
        for primitive_episode_id, provenance in grouped:
            path = dataset_dir / f"episode_{primitive_episode_id}.hdf5"
            episode_frames, contract = _load_episode_frames(
                path=path,
                expected_provenance=provenance,
                expected_features=_features_for_provenance(
                    partition_features,
                    expected,
                    provenance,
                ),
                camera_names=camera_names,
            )
            if any(frame.provenance.partition != partition for frame in episode_frames):
                raise ReturnTemporalDispatchValidationError(
                    "Return episode provenance partition mismatch"
                )
            frames_by_partition[partition].extend(episode_frames)
            contracts.append(contract)

    train_frames = tuple(frames_by_partition["train"])
    validation_frames = tuple(frames_by_partition["validation"])
    _validate_partition_frames(
        frames=train_frames,
        expected=numeric.train_provenance,
        expected_features=numeric.train_features,
        partition="train",
        allowed_sources=numeric.train_source_episode_ids,
    )
    _validate_partition_frames(
        frames=validation_frames,
        expected=numeric.validation_provenance,
        expected_features=numeric.validation_features,
        partition="validation",
        allowed_sources=numeric.validation_source_episode_ids,
    )
    storage_contract = _shared_storage_contract(contracts)
    segments = _build_validation_segments(validation_frames)
    action_reference = build_strict_return_temporal_action_reference(train_frames)
    population = ReturnTemporalDispatchValidationPopulation(
        schema=RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA,
        feature_order=RETURN_FEATURE_ORDER,
        model_token_key="return_start_envelope_tokens_v1",
        camera_names=camera_names,
        storage_contract=storage_contract,
        training_config_path=str(config_path),
        primitive_dataset_dir=str(dataset_dir),
        split_path=numeric.split_path,
        train_source_episode_ids=numeric.train_source_episode_ids,
        validation_source_episode_ids=numeric.validation_source_episode_ids,
        train_frames=train_frames,
        validation_frames=validation_frames,
        validation_segments=segments,
        action_reference=action_reference,
    )
    _validate_population(population)
    return population


def build_return_validation_counterfactual_pairs(
    population: ReturnTemporalDispatchValidationPopulation,
) -> tuple[ReturnValidationCounterfactualPair, ...]:
    """Pair every held-validation segment with the next real held token.

    Token representatives are ordered by their first held-validation segment
    ``(primitive episode, first action index, segment id)``.  Each baseline is
    paired cyclically with the next distinct token in that frozen order.  This
    consumes no Stage-A target, no strict-train token, and no result metric.
    """

    _validate_population(population)
    representatives: dict[str, ReturnTemporalDispatchSegment] = {}
    for segment in population.validation_segments:
        current = representatives.get(segment.token_sha256)
        if current is None or _segment_sort_key(segment) < _segment_sort_key(current):
            representatives[segment.token_sha256] = segment
    ordered = tuple(sorted(representatives.values(), key=_segment_sort_key))
    if len(ordered) < 2:
        raise ReturnTemporalDispatchValidationError(
            "held Return validation requires at least two distinct real tokens "
            "for counterfactual pairing"
        )
    index_by_token = {segment.token_sha256: index for index, segment in enumerate(ordered)}
    pairs: list[ReturnValidationCounterfactualPair] = []
    for baseline in population.validation_segments:
        alternate = ordered[(index_by_token[baseline.token_sha256] + 1) % len(ordered)]
        if alternate.token_sha256 == baseline.token_sha256:
            raise AssertionError("Return alternate selection did not change token")
        pairs.append(
            ReturnValidationCounterfactualPair(
                baseline_segment=baseline,
                alternate_token=_freeze(alternate.token),
                alternate_token_sha256=alternate.token_sha256,
                alternate_token_source_episode_id=alternate.source_episode_id,
                alternate_token_primitive_episode_id=alternate.primitive_episode_id,
                alternate_token_segment_id=alternate.segment_id,
            )
        )
    return tuple(pairs)


def read_return_temporal_dispatch_observation(
    *,
    frame: ReturnTemporalDispatchFrame,
    camera_names: Sequence[str],
) -> dict[str, np.ndarray]:
    """Read one immutable Return training observation for later policy replay.

    The HDF5 file is opened read-only and every stored numeric field is checked
    against the immutable frame snapshot before images are returned.  The
    same-row relation mirrors ``EpisodicDataset`` for this simulated data:
    observation row ``t`` precedes the action chunk whose first expert action
    is row ``t``.
    """

    names = _normalise_camera_names(camera_names)
    path = Path(frame.hdf5_path).expanduser().resolve(strict=True)
    with h5py.File(path, "r") as handle:
        _require_simulated_training_alignment(handle, path)
        _validate_episode_storage(
            handle,
            path=path,
            count=_episode_count(handle, path),
            camera_names=names,
        )
        _validate_frame_against_handle(frame=frame, handle=handle, path=path)
        observation: dict[str, np.ndarray] = {
            "qpos": _freeze(handle["observations/qpos"][frame.observation_index]),
            "qvel": _freeze(handle["observations/qvel"][frame.observation_index]),
            "return_start_envelope_tokens_v1": _freeze(
                handle["v2/step/return_start_envelope_tokens_v1"][frame.observation_index]
            ),
        }
        for camera_name in names:
            observation[f"image_{camera_name}"] = _freeze(
                read_camera_rgb(handle, camera_name, frame.observation_index)
            )
    return observation


def summarize_return_temporal_dispatch_validation_feasibility(
    population: ReturnTemporalDispatchValidationPopulation,
) -> dict[str, Any]:
    """Return compact, target-free feasibility facts for a later evaluator."""

    _validate_population(population)
    pairs = build_return_validation_counterfactual_pairs(population)
    token_ids = {segment.token_sha256 for segment in population.validation_segments}
    return {
        "schema": RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA,
        "target_rollout_used_for_fit_or_selection": False,
        "fit_partition": "strict_train",
        "validation_partition": "held_out_source_disjoint",
        "strict_train": {
            "row_count": len(population.train_frames),
            "source_episode_ids": list(population.train_source_episode_ids),
            "primitive_episode_ids": _unique_primitive_episode_ids(population.train_frames),
        },
        "held_validation": {
            "row_count": len(population.validation_frames),
            "source_episode_ids": list(population.validation_source_episode_ids),
            "primitive_episode_ids": _unique_primitive_episode_ids(population.validation_frames),
            "stable_segment_count": len(population.validation_segments),
            "distinct_real_token_count": len(token_ids),
        },
        "counterfactual_pairing": {
            "pair_count": len(pairs),
            "selection": "held_validation_real_token_first_occurrence_cyclic_next",
            "uses_only_held_validation_tokens": True,
            "uses_target_rollout": False,
        },
        "training_observation_access": {
            "relation": population.storage_contract.observation_action_alignment,
            "reader": "read_return_temporal_dispatch_observation",
            "camera_order": list(population.camera_names),
        },
        "storage_contract": population.storage_contract.as_dict(),
        "strict_train_action_reference": population.action_reference.as_dict(),
    }


def _read_yaml_mapping(path: Path) -> Mapping[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ReturnTemporalDispatchValidationError("Return training config must be a mapping")
    return payload


def _validate_return_config(config: Mapping[str, Any]) -> None:
    policy = config.get("policy")
    train = config.get("train")
    if not isinstance(policy, Mapping) or not isinstance(train, Mapping):
        raise ReturnTemporalDispatchValidationError("Return training config lacks policy or train mapping")
    keys = tuple(str(value) for value in policy.get("low_dim_keys", ()))
    if keys != RETURN_LOW_DIM_KEYS:
        raise ReturnTemporalDispatchValidationError(
            f"Return low_dim_keys must be {RETURN_LOW_DIM_KEYS!r}, got {keys!r}"
        )
    scope = str(train.get("action_loss_mask_scope", "")).strip()
    if scope != ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS:
        raise ReturnTemporalDispatchValidationError(
            "Return temporal-dispatch validation requires train.action_loss_mask_scope="
            "'loss_sampling_stats'"
        )


def _camera_names(config: Mapping[str, Any]) -> tuple[str, ...]:
    task = config.get("task")
    if not isinstance(task, Mapping):
        raise ReturnTemporalDispatchValidationError("Return training config lacks task mapping")
    return _normalise_camera_names(task.get("camera_names", ()))


def _normalise_camera_names(value: Sequence[str] | Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReturnTemporalDispatchValidationError("Return camera_names must be a non-empty sequence")
    names = tuple(str(item).strip() for item in value)
    if not names or any(not item for item in names) or len(names) != len(set(names)):
        raise ReturnTemporalDispatchValidationError("Return camera_names must be non-empty and unique")
    return names


def _validate_numeric_rows(rows: StrictSourceAwareSupportRows) -> None:
    if rows.skill_name != "return" or rows.model_token_key != "return_start_envelope_tokens_v1":
        raise ReturnTemporalDispatchValidationError("Return temporal-dispatch data requires Return support rows")
    if rows.feature_order != RETURN_FEATURE_ORDER:
        raise ReturnTemporalDispatchValidationError("Return full feature order mismatch")
    if not rows.train_provenance or not rows.validation_provenance:
        raise ReturnTemporalDispatchValidationError("Return train and held validation both require valid rows")
    if set(rows.train_source_episode_ids) & set(rows.validation_source_episode_ids):
        raise ReturnTemporalDispatchValidationError("Return train and validation sources overlap")


def _group_provenance_by_episode(
    provenance: Sequence[SupportRowProvenance],
) -> tuple[tuple[int, tuple[SupportRowProvenance, ...]], ...]:
    grouped: dict[int, list[SupportRowProvenance]] = {}
    for item in provenance:
        grouped.setdefault(item.primitive_episode_id, []).append(item)
    return tuple((episode_id, tuple(items)) for episode_id, items in grouped.items())


def _features_for_provenance(
    partition_features: np.ndarray,
    partition: Sequence[SupportRowProvenance],
    requested: Sequence[SupportRowProvenance],
) -> np.ndarray:
    positions = {id(item): index for index, item in enumerate(partition)}
    try:
        values = np.stack(
            [partition_features[positions[id(item)]] for item in requested],
            axis=0,
        )
    except KeyError as exc:  # pragma: no cover - defensive against internal misuse
        raise ReturnTemporalDispatchValidationError("Return provenance row was not in its partition") from exc
    return np.asarray(values, dtype=np.float64)


def _load_episode_frames(
    *,
    path: Path,
    expected_provenance: Sequence[SupportRowProvenance],
    expected_features: np.ndarray,
    camera_names: tuple[str, ...],
) -> tuple[tuple[ReturnTemporalDispatchFrame, ...], ReturnTemporalDispatchStorageContract]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with h5py.File(path, "r") as handle:
        count = _episode_count(handle, path)
        _require_simulated_training_alignment(handle, path)
        contract = _validate_episode_storage(
            handle,
            path=path,
            count=count,
            camera_names=camera_names,
        )
        source_episode_id = _source_episode_id(handle, path)
        qpos = np.asarray(handle["observations/qpos"][:], dtype=np.float32)
        qvel = np.asarray(handle["observations/qvel"][:], dtype=np.float32)
        token = np.asarray(
            handle["v2/step/return_start_envelope_tokens_v1"][:], dtype=np.float32
        )
        action = np.asarray(handle["action"][:], dtype=np.float32)
        step_ids = np.asarray(handle[DS_STEP_ID][:], dtype=np.int64).reshape(-1)
        mask = read_action_loss_mask(handle, expected_length=count, required=True)
        assert mask is not None
    selected_indices = np.flatnonzero(mask == 1)
    expected_indices = np.asarray([item.step_index for item in expected_provenance], dtype=np.int64)
    if not np.array_equal(selected_indices, expected_indices):
        raise ReturnTemporalDispatchValidationError(
            f"{path} action_loss_mask selected rows disagree with source-aware provenance"
        )
    if source_episode_id != expected_provenance[0].source_episode_id or any(
        item.source_episode_id != source_episode_id for item in expected_provenance
    ):
        raise ReturnTemporalDispatchValidationError(
            f"{path} source_episode_id disagrees with source-aware provenance"
        )
    feature = assemble_act_low_dim_observation(
        qpos=qpos[selected_indices],
        qvel=qvel[selected_indices],
        return_start_envelope_tokens_v1=token[selected_indices],
        low_dim_keys=RETURN_LOW_DIM_KEYS,
    )
    if not np.array_equal(np.asarray(feature, dtype=np.float64), expected_features):
        raise ReturnTemporalDispatchValidationError(
            f"{path} qpos/qvel/token rows disagree with source-aware support features"
        )
    frames: list[ReturnTemporalDispatchFrame] = []
    for row_index, (index, item) in enumerate(zip(selected_indices, expected_provenance, strict=True)):
        if int(step_ids[index]) != item.step_id:
            raise ReturnTemporalDispatchValidationError(
                f"{path} step id disagrees with source-aware provenance"
            )
        if int(mask[index]) != 1 or item.action_loss_mask != 1:
            raise ReturnTemporalDispatchValidationError(
                f"{path} contains a non-action-supervised Return frame"
            )
        _ensure_finite(qpos[index], label=f"{path} qpos row {row_index}")
        _ensure_finite(qvel[index], label=f"{path} qvel row {row_index}")
        _ensure_finite(token[index], label=f"{path} token row {row_index}")
        _ensure_finite(action[index], label=f"{path} action row {row_index}")
        frames.append(
            ReturnTemporalDispatchFrame(
                provenance=item,
                hdf5_path=str(path.resolve()),
                action_index=int(index),
                observation_index=int(index),
                action_step_id=int(step_ids[index]),
                observation_step_id=int(step_ids[index]),
                qpos=_freeze(qpos[index]),
                qvel=_freeze(qvel[index]),
                token=_freeze(token[index]),
                expert_action=_freeze(action[index]),
            )
        )
    return tuple(frames), contract


def _episode_count(handle: h5py.File, path: Path) -> int:
    for dataset_path in (
        "observations/qpos",
        "observations/qvel",
        "v2/step/return_start_envelope_tokens_v1",
        "action",
        DS_STEP_ID,
    ):
        if dataset_path not in handle:
            raise ReturnTemporalDispatchValidationError(f"{path} is missing {dataset_path}")
    count = int(handle["action"].shape[0])
    if count < 1:
        raise ReturnTemporalDispatchValidationError(f"{path} has no Return rows")
    return count


def _require_simulated_training_alignment(handle: h5py.File, path: Path) -> None:
    if not bool(handle.attrs.get("sim", False)):
        raise ReturnTemporalDispatchValidationError(
            f"{path} is not simulated; its training action alignment is not same-row"
        )


def _validate_episode_storage(
    handle: h5py.File,
    *,
    path: Path,
    count: int,
    camera_names: tuple[str, ...],
) -> ReturnTemporalDispatchStorageContract:
    qpos = handle["observations/qpos"]
    qvel = handle["observations/qvel"]
    token = handle["v2/step/return_start_envelope_tokens_v1"]
    action = handle["action"]
    step_ids = handle[DS_STEP_ID]
    _require_dataset_shape_dtype(qpos, path=path, label="qpos", shape=(count, 4), dtype=np.float32)
    _require_dataset_shape_dtype(qvel, path=path, label="qvel", shape=(count, 4), dtype=np.float32)
    _require_dataset_shape_dtype(token, path=path, label="return token", shape=(count, 18), dtype=np.float32)
    _require_dataset_shape_dtype(action, path=path, label="action", shape=(count, 4), dtype=np.float32)
    _require_dataset_shape_dtype(step_ids, path=path, label="step_id", shape=(count,), dtype=np.int64)
    step_values = np.asarray(step_ids[:], dtype=np.int64).reshape(-1)
    if np.any(np.diff(step_values) <= 0):
        raise ReturnTemporalDispatchValidationError(f"{path} step_id values must be strictly increasing")
    storage = _validate_camera_storage(handle, path=path, camera_names=camera_names, count=count)
    metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
    return ReturnTemporalDispatchStorageContract(
        qpos_dtype=str(qpos.dtype),
        qvel_dtype=str(qvel.dtype),
        token_dtype=str(token.dtype),
        action_dtype=str(action.dtype),
        step_id_dtype=str(step_ids.dtype),
        qpos_order=_metadata_order(metadata, "qpos_order", path),
        qvel_order=_metadata_order(metadata, "qvel_order", path),
        action_order=_metadata_order(metadata, "action_order", path),
        camera_storage=storage,
        observation_action_alignment=(
            "training_same_row_observation_precedes_action_chunk_query0"
        ),
    )


def _validate_camera_storage(
    handle: h5py.File,
    *,
    path: Path,
    camera_names: tuple[str, ...],
    count: int,
) -> Literal["raw_rgb", "jpeg"]:
    metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
    stored_names = tuple(camera_names_from_metadata(metadata))
    if stored_names != camera_names:
        raise ReturnTemporalDispatchValidationError(
            f"{path} camera order disagrees with Return training config: "
            f"stored={stored_names!r}, configured={camera_names!r}"
        )
    raw_group = handle.get("observations/images")
    encoded_group = handle.get("observations/encoded_images")
    available = validate_exclusive_camera_layout(
        () if raw_group is None else raw_group.keys(),
        () if encoded_group is None else encoded_group.keys(),
    )
    if tuple(available) != camera_names and set(available) != set(camera_names):
        raise ReturnTemporalDispatchValidationError(
            f"{path} camera datasets disagree with configured camera order"
        )
    if raw_group is not None:
        for name in camera_names:
            dataset = raw_group[name]
            if dataset.shape[0] != count or dataset.ndim != 4 or dataset.shape[-1] != 3:
                raise ReturnTemporalDispatchValidationError(
                    f"{path} raw camera {name!r} must have shape (T,H,W,3)"
                )
            if np.dtype(dataset.dtype) != np.dtype(np.uint8):
                raise ReturnTemporalDispatchValidationError(
                    f"{path} raw camera {name!r} dtype must be uint8"
                )
        return "raw_rgb"
    if encoded_group is not None:
        for name in camera_names:
            dataset = encoded_group[name]
            encoding = dataset.attrs.get("encoding", "")
            if isinstance(encoding, bytes):
                encoding = encoding.decode("utf-8", errors="strict")
            if dataset.shape != (count,) or str(encoding).lower() != JPEG_ENCODING:
                raise ReturnTemporalDispatchValidationError(
                    f"{path} encoded camera {name!r} is not a JPEG sequence of length T"
                )
        return "jpeg"
    raise ReturnTemporalDispatchValidationError(f"{path} has no camera images")


def _require_dataset_shape_dtype(
    dataset: h5py.Dataset,
    *,
    path: Path,
    label: str,
    shape: tuple[int, ...],
    dtype: np.dtype[Any],
) -> None:
    if dataset.shape != shape:
        raise ReturnTemporalDispatchValidationError(
            f"{path} {label} must have shape {shape}, got {dataset.shape}"
        )
    if np.dtype(dataset.dtype) != np.dtype(dtype):
        raise ReturnTemporalDispatchValidationError(
            f"{path} {label} dtype must be {np.dtype(dtype)}, got {dataset.dtype}"
        )


def _metadata_order(metadata: Mapping[str, Any], field: str, path: Path) -> tuple[str, ...]:
    raw = metadata.get(field)
    if raw is None:
        raise ReturnTemporalDispatchValidationError(f"{path} metadata lacks {field}")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    values = tuple(item.strip() for item in str(raw).split(",") if item.strip())
    if len(values) != 4 or len(values) != len(set(values)):
        raise ReturnTemporalDispatchValidationError(
            f"{path} metadata {field} must name four unique axes"
        )
    return values


def _source_episode_id(handle: h5py.File, path: Path) -> int:
    if "metadata" not in handle or "source_episode_id" not in handle["metadata"].attrs:
        raise ReturnTemporalDispatchValidationError(f"{path} metadata lacks source_episode_id")
    raw = handle["metadata"].attrs["source_episode_id"]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    text = str(raw).strip().removeprefix("episode_")
    try:
        return int(text)
    except ValueError as exc:
        raise ReturnTemporalDispatchValidationError(
            f"{path} source_episode_id is not an integer"
        ) from exc


def _validate_partition_frames(
    *,
    frames: tuple[ReturnTemporalDispatchFrame, ...],
    expected: Sequence[SupportRowProvenance],
    expected_features: np.ndarray,
    partition: Literal["train", "validation"],
    allowed_sources: Sequence[int],
) -> None:
    if len(frames) != len(expected) or len(frames) != expected_features.shape[0]:
        raise ReturnTemporalDispatchValidationError(
            f"Return {partition} frame/provenance/feature counts disagree"
        )
    if not frames:
        raise ReturnTemporalDispatchValidationError(f"Return {partition} has no frames")
    for index, (frame, provenance, feature) in enumerate(zip(frames, expected, expected_features, strict=True)):
        if frame.provenance != provenance:
            raise ReturnTemporalDispatchValidationError(
                f"Return {partition} provenance order changed at row {index}"
            )
        if provenance.partition != partition or provenance.source_episode_id not in allowed_sources:
            raise ReturnTemporalDispatchValidationError(
                f"Return {partition} source provenance escaped its partition"
            )
        if provenance.action_loss_mask != 1:
            raise ReturnTemporalDispatchValidationError(
                f"Return {partition} exposed action_loss_mask=0"
            )
        if frame.action_index != provenance.step_index or frame.observation_index != frame.action_index:
            raise ReturnTemporalDispatchValidationError(
                f"Return {partition} training observation/action alignment changed"
            )
        if frame.action_step_id != provenance.step_id or frame.observation_step_id != frame.action_step_id:
            raise ReturnTemporalDispatchValidationError(
                f"Return {partition} step provenance changed"
            )
        if not np.array_equal(np.asarray(frame.feature, dtype=np.float64), feature):
            raise ReturnTemporalDispatchValidationError(
                f"Return {partition} full feature changed at row {index}"
            )


def _shared_storage_contract(
    contracts: Sequence[ReturnTemporalDispatchStorageContract],
) -> ReturnTemporalDispatchStorageContract:
    if not contracts:
        raise ReturnTemporalDispatchValidationError("Return population has no storage contracts")
    first = contracts[0]
    if any(contract != first for contract in contracts[1:]):
        raise ReturnTemporalDispatchValidationError(
            "Return selected episodes disagree on dtype, field order, camera storage, or alignment"
        )
    return first


def _build_validation_segments(
    frames: Sequence[ReturnTemporalDispatchFrame],
) -> tuple[ReturnTemporalDispatchSegment, ...]:
    if not frames:
        raise ReturnTemporalDispatchValidationError("Return held validation has no frames")
    result: list[ReturnTemporalDispatchSegment] = []
    current: list[ReturnTemporalDispatchFrame] = [frames[0]]
    for frame in frames[1:]:
        previous = current[-1]
        if _starts_new_segment(previous, frame):
            result.append(_segment_from_frames(current))
            current = [frame]
        else:
            current.append(frame)
    result.append(_segment_from_frames(current))
    return tuple(result)


def _starts_new_segment(
    previous: ReturnTemporalDispatchFrame,
    current: ReturnTemporalDispatchFrame,
) -> bool:
    return bool(
        previous.provenance.primitive_episode_id != current.provenance.primitive_episode_id
        or previous.provenance.source_episode_id != current.provenance.source_episode_id
        or current.action_index != previous.action_index + 1
        or current.action_step_id != previous.action_step_id + 1
        or not np.array_equal(previous.token, current.token)
    )


def _segment_from_frames(
    frames: Sequence[ReturnTemporalDispatchFrame],
) -> ReturnTemporalDispatchSegment:
    if not frames:
        raise AssertionError("cannot construct an empty Return validation segment")
    first = frames[0]
    token = _freeze(first.token)
    if any(
        frame.provenance.primitive_episode_id != first.provenance.primitive_episode_id
        or frame.provenance.source_episode_id != first.provenance.source_episode_id
        or not np.array_equal(frame.token, token)
        for frame in frames
    ):
        raise ReturnTemporalDispatchValidationError("Return validation segment is not stable")
    return ReturnTemporalDispatchSegment(
        primitive_episode_id=first.provenance.primitive_episode_id,
        source_episode_id=first.provenance.source_episode_id,
        token=token,
        token_sha256=_token_sha256(token),
        frames=tuple(frames),
    )


def _validate_frame_against_handle(
    *,
    frame: ReturnTemporalDispatchFrame,
    handle: h5py.File,
    path: Path,
) -> None:
    count = _episode_count(handle, path)
    if frame.observation_index != frame.action_index:
        raise ReturnTemporalDispatchValidationError("Return frame is not same-row training aligned")
    if not 0 <= frame.action_index < count:
        raise ReturnTemporalDispatchValidationError("Return frame index is outside its HDF5 episode")
    if _source_episode_id(handle, path) != frame.provenance.source_episode_id:
        raise ReturnTemporalDispatchValidationError("Return frame source episode changed on disk")
    mask = read_action_loss_mask(handle, expected_length=count, required=True)
    assert mask is not None
    if int(mask[frame.action_index]) != 1:
        raise ReturnTemporalDispatchValidationError("Return frame is no longer action-supervised")
    step_id = int(handle[DS_STEP_ID][frame.action_index])
    if step_id != frame.action_step_id or step_id != frame.observation_step_id:
        raise ReturnTemporalDispatchValidationError("Return frame step id changed on disk")
    comparisons = (
        ("qpos", handle["observations/qpos"][frame.observation_index], frame.qpos),
        ("qvel", handle["observations/qvel"][frame.observation_index], frame.qvel),
        (
            "return token",
            handle["v2/step/return_start_envelope_tokens_v1"][frame.observation_index],
            frame.token,
        ),
        ("action", handle["action"][frame.action_index], frame.expert_action),
    )
    for label, stored, expected in comparisons:
        if not np.array_equal(np.asarray(stored, dtype=np.float32), expected):
            raise ReturnTemporalDispatchValidationError(
                f"Return frame {label} no longer matches the immutable population"
            )


def _validate_population(population: ReturnTemporalDispatchValidationPopulation) -> None:
    if population.schema != RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA:
        raise ReturnTemporalDispatchValidationError("Return validation population schema mismatch")
    if population.feature_order != RETURN_FEATURE_ORDER:
        raise ReturnTemporalDispatchValidationError("Return validation feature order mismatch")
    if population.model_token_key != "return_start_envelope_tokens_v1":
        raise ReturnTemporalDispatchValidationError("Return validation token key mismatch")
    if set(population.train_source_episode_ids) & set(population.validation_source_episode_ids):
        raise ReturnTemporalDispatchValidationError("Return validation source split overlaps")
    if not population.validation_segments:
        raise ReturnTemporalDispatchValidationError("Return validation population lacks stable segments")
    for partition, frames, sources in (
        ("train", population.train_frames, population.train_source_episode_ids),
        ("validation", population.validation_frames, population.validation_source_episode_ids),
    ):
        if not frames:
            raise ReturnTemporalDispatchValidationError(f"Return {partition} population is empty")
        for frame in frames:
            if frame.provenance.partition != partition or frame.provenance.source_episode_id not in sources:
                raise ReturnTemporalDispatchValidationError(f"Return {partition} provenance is unsafe")
            if frame.provenance.action_loss_mask != 1:
                raise ReturnTemporalDispatchValidationError(f"Return {partition} has masked action row")
            if frame.qpos.shape != (4,) or frame.qvel.shape != (4,) or frame.token.shape != (18,) or frame.expert_action.shape != (4,):
                raise ReturnTemporalDispatchValidationError(f"Return {partition} frame dimensionality mismatch")
    for segment in population.validation_segments:
        if segment.source_episode_id not in population.validation_source_episode_ids:
            raise ReturnTemporalDispatchValidationError("Return segment leaves held validation sources")
        if not segment.frames or any(frame.provenance.partition != "validation" for frame in segment.frames):
            raise ReturnTemporalDispatchValidationError("Return segment is not held validation")


def _unique_primitive_episode_ids(frames: Sequence[ReturnTemporalDispatchFrame]) -> list[int]:
    return sorted({frame.provenance.primitive_episode_id for frame in frames})


def _segment_sort_key(segment: ReturnTemporalDispatchSegment) -> tuple[int, int, str]:
    return (
        segment.primitive_episode_id,
        segment.frames[0].action_index,
        segment.segment_id,
    )


def _token_sha256(token: np.ndarray) -> str:
    values = np.ascontiguousarray(np.asarray(token, dtype=np.float32).reshape(-1))
    digest = hashlib.sha256()
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _ensure_finite(values: np.ndarray, *, label: str) -> None:
    if not np.isfinite(np.asarray(values, dtype=np.float64)).all():
        raise ReturnTemporalDispatchValidationError(f"{label} contains non-finite values")


def _freeze(values: Any) -> np.ndarray:
    result = np.asarray(values).copy()
    result.setflags(write=False)
    return result


def _float_list(values: np.ndarray | Sequence[float]) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


__all__ = [
    "RETURN_FEATURE_ORDER",
    "RETURN_LOW_DIM_KEYS",
    "RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA",
    "ReturnTemporalActionReference",
    "ReturnTemporalDispatchFrame",
    "ReturnTemporalDispatchSegment",
    "ReturnTemporalDispatchStorageContract",
    "ReturnTemporalDispatchValidationError",
    "ReturnTemporalDispatchValidationPopulation",
    "ReturnValidationCounterfactualPair",
    "build_return_validation_counterfactual_pairs",
    "load_strict_return_temporal_dispatch_validation_population",
    "read_return_temporal_dispatch_observation",
    "summarize_return_temporal_dispatch_validation_feasibility",
]
