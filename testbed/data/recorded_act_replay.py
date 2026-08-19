"""Read-only data contracts for Phase-A recorded ACT replay.

The functions here only join immutable rollout inputs and strict-training
datasets.  They do not load a policy, classify a goal response, or write an
artifact.  Keeping that boundary in ``data`` prevents an evaluator from
silently choosing a different observation/action alignment or token source.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.action_loss_mask import read_action_loss_mask
from testbed.data.camera_images import camera_names_from_metadata, read_camera_rgb
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.data.schema import DS_STEP_ID


@dataclass(frozen=True)
class _RecordedTokenSpec:
    skill_name: str
    jsonl_keys: tuple[str, ...]
    jsonl_source_keys: tuple[str, ...]
    dataset_path: str | None
    model_token_key: str | None
    token_dim: int | None


_TOKEN_SPECS: dict[str, _RecordedTokenSpec] = {
    "dig": _RecordedTokenSpec(
        skill_name="dig",
        jsonl_keys=("dig_cut_tokens",),
        jsonl_source_keys=("dig_cut_token_source",),
        dataset_path="v2/step/dig_cut_tokens",
        model_token_key="dig_cut_tokens",
        token_dim=DIG_CUT_TOKEN_DIM,
    ),
    "return": _RecordedTokenSpec(
        skill_name="return",
        jsonl_keys=(
            "return_start_envelope_tokens",
            "return_start_envelope_tokens_v1",
        ),
        jsonl_source_keys=(
            "return_start_envelope_token_source",
            "return_start_envelope_tokens_v1_source",
        ),
        dataset_path="v2/step/return_start_envelope_tokens_v1",
        model_token_key="return_start_envelope_tokens_v1",
        token_dim=RETURN_START_ENVELOPE_TOKEN_DIM,
    ),
    "carry": _RecordedTokenSpec(
        skill_name="carry",
        jsonl_keys=(),
        jsonl_source_keys=(),
        dataset_path=None,
        model_token_key=None,
        token_dim=None,
    ),
    "dump": _RecordedTokenSpec(
        skill_name="dump",
        jsonl_keys=(),
        jsonl_source_keys=(),
        dataset_path=None,
        model_token_key=None,
        token_dim=None,
    ),
}


@dataclass(frozen=True)
class RecordedActReplayFrame:
    """One recorded action paired with the pre-action ACT observation."""

    jsonl_row_index: int
    action_step_id: int
    observation_step_id: int
    action_hdf5_index: int
    observation_hdf5_index: int
    skill_name: str
    primitive_cycle_index: int
    skill_switch_reason: str
    policy_restarted: bool
    policy_dispatched: bool
    qpos: np.ndarray
    qvel: np.ndarray
    action: np.ndarray
    token: np.ndarray | None
    model_token_key: str | None
    token_source: str | None


@dataclass(frozen=True)
class RecordedActReplaySegment:
    """A contiguous stable-token stream with one ACT temporal reset boundary."""

    skill_name: str
    model_token_key: str | None
    token: np.ndarray | None
    token_source: str | None
    token_sha256: str | None
    frames: tuple[RecordedActReplayFrame, ...]
    start_action_step_id: int
    end_action_step_id: int
    primitive_cycle_indices: tuple[int, ...]

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def primitive(self) -> str:
        """Evaluator-facing alias for the primitive represented by this segment."""
        return self.skill_name

    @property
    def condition_input_key(self) -> str | None:
        """Evaluator-facing model observation key for this segment's token."""
        return self.model_token_key

    @property
    def segment_id(self) -> str:
        token_id = "unconditioned" if self.token_sha256 is None else self.token_sha256[:12]
        return (
            f"{self.skill_name}:{self.start_action_step_id}-"
            f"{self.end_action_step_id}:{token_id}"
        )


@dataclass(frozen=True)
class StrictTrainNumericSupport:
    """p01/p99 bounds from source-safe, action-supervised training rows."""

    skill_name: str
    model_token_key: str
    feature_order: tuple[str, ...]
    p01: np.ndarray
    p99: np.ndarray
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    total_step_count: int
    kept_step_count: int
    masked_step_count: int

    @property
    def feature_dim(self) -> int:
        return len(self.feature_order)


@dataclass(frozen=True)
class NumericSupportViolation:
    """One feature that lies outside the frozen strict-train interval."""

    field: str
    value: float
    p01: float
    p99: float
    kind: str


@dataclass(frozen=True)
class NumericSupportAssessment:
    """Per-frame support result for one replay stream under one candidate token."""

    feature: np.ndarray
    frame_in_support: np.ndarray
    violations: tuple[tuple[NumericSupportViolation, ...], ...]

    @property
    def in_support_fraction(self) -> float:
        return float(np.mean(self.frame_in_support)) if self.frame_in_support.size else 0.0


def join_recorded_act_replay_frames(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    skills: Sequence[str] = ("dig", "return"),
) -> list[RecordedActReplayFrame]:
    """Join JSONL actions to the HDF5 observation that produced each action.

    HDF5 stores the post-step observation on the same row as an action, so the
    observation for action ``i`` is HDF5 row ``i - 1``.  The function validates
    complete step inventories and identical JSONL/HDF5 action values before
    exposing a conditionable Dig or Return frame.
    """
    requested_skills = _normalise_requested_skills(skills)
    hdf5_path = Path(rollout_hdf5_path).expanduser().resolve(strict=True)
    jsonl_path = Path(rollout_jsonl_path).expanduser().resolve(strict=True)
    rows = _read_jsonl_rows(jsonl_path)
    json_step_ids = [_integer(row.get("step_id"), label="JSONL step_id") for row in rows]
    _validate_strictly_increasing(json_step_ids, label="JSONL step_id inventory")

    with h5py.File(hdf5_path, "r") as handle:
        if DS_STEP_ID not in handle:
            raise KeyError(f"rollout HDF5 is missing {DS_STEP_ID}")
        hdf5_step_ids = np.asarray(handle[DS_STEP_ID][:], dtype=np.int64).reshape(-1)
        _validate_strictly_increasing(
            [int(value) for value in hdf5_step_ids],
            label="HDF5 step_id inventory",
        )
        if json_step_ids != [int(value) for value in hdf5_step_ids]:
            raise ValueError("JSONL and HDF5 step_id inventories disagree")
        if "action" not in handle:
            raise KeyError("rollout HDF5 is missing action")
        if "observations/qpos" not in handle or "observations/qvel" not in handle:
            raise KeyError("rollout HDF5 is missing observations/qpos or observations/qvel")
        actions = np.asarray(handle["action"][:], dtype=np.float32)
        qpos = np.asarray(handle["observations/qpos"][:], dtype=np.float32)
        qvel = np.asarray(handle["observations/qvel"][:], dtype=np.float32)
        count = int(hdf5_step_ids.size)
        if actions.shape != (count, 4):
            raise ValueError(f"rollout HDF5 action must have shape ({count}, 4), got {actions.shape}")
        if qpos.shape != (count, 4) or qvel.shape != (count, 4):
            raise ValueError("rollout HDF5 qpos/qvel must each have shape (T, 4)")
        if not np.isfinite(actions).all() or not np.isfinite(qpos).all() or not np.isfinite(qvel).all():
            raise ValueError("rollout HDF5 action/qpos/qvel contains non-finite values")

        frames: list[RecordedActReplayFrame] = []
        for row_index, row in enumerate(rows):
            skill_name = str(row.get("skill_name", "")).strip().lower()
            if skill_name not in requested_skills:
                continue
            spec = _token_spec(skill_name)
            action_step_id = json_step_ids[row_index]
            action_index = row_index
            if action_index <= 0:
                raise ValueError(
                    f"action step_id {action_step_id} has no recorded pre-action observation"
                )
            observation_index = action_index - 1
            observation_step_id = int(hdf5_step_ids[observation_index])
            if observation_step_id != action_step_id - 1:
                raise ValueError(
                    "action/pre-action observation step ids are not contiguous: "
                    f"action={action_step_id}, observation={observation_step_id}"
                )
            json_action = _finite_vector(row.get("action"), 4, label="JSONL action")
            hdf5_action = actions[action_index]
            if not np.allclose(json_action, hdf5_action, rtol=0.0, atol=1.0e-6):
                raise ValueError(
                    f"action step_id {action_step_id} JSONL action disagrees with HDF5 action"
                )
            if spec.model_token_key is None:
                token = None
                token_source = None
            else:
                token = _read_jsonl_token(
                    row,
                    spec=spec,
                    action_step_id=action_step_id,
                )
                token_source = _optional_row_text(row, spec.jsonl_source_keys)
            safety_reason = str(row.get("box_safety_reason", "")).strip()
            policy_dispatched = not (
                bool(row.get("box_safety_clearance_active", False))
                or bool(row.get("box_safety_awaiting_neutral_ack", False))
                or bool(safety_reason)
            )
            frames.append(
                RecordedActReplayFrame(
                    jsonl_row_index=row_index,
                    action_step_id=action_step_id,
                    observation_step_id=observation_step_id,
                    action_hdf5_index=action_index,
                    observation_hdf5_index=observation_index,
                    skill_name=skill_name,
                    primitive_cycle_index=_integer(
                        row.get("primitive_cycle_index", 0),
                        label="primitive_cycle_index",
                    ),
                    skill_switch_reason=str(row.get("skill_switch_reason", "")).strip(),
                    policy_restarted=bool(row.get("box_safety_policy_restarted", False)),
                    policy_dispatched=policy_dispatched,
                    qpos=qpos[observation_index].copy(),
                    qvel=qvel[observation_index].copy(),
                    action=hdf5_action.copy(),
                    token=token,
                    model_token_key=spec.model_token_key,
                    token_source=token_source,
                )
            )
    return frames


def read_recorded_act_observation(
    *,
    hdf5_file: Any,
    frame: RecordedActReplayFrame,
    camera_names: Sequence[str],
) -> dict[str, np.ndarray]:
    """Read one model-ready recorded observation, including decoded RGB images."""
    names = [str(name) for name in camera_names]
    if not names:
        raise ValueError("camera_names must not be empty")
    if len(names) != len(set(names)):
        raise ValueError(f"camera_names contains duplicates: {names!r}")
    metadata = (
        dict(hdf5_file["metadata"].attrs)
        if "metadata" in hdf5_file
        else {}
    )
    stored_camera_names = camera_names_from_metadata(metadata)
    if stored_camera_names and names != stored_camera_names:
        raise ValueError(
            "requested camera order does not match recorded camera order: "
            f"requested={names}, recorded={stored_camera_names}"
        )
    if DS_STEP_ID not in hdf5_file:
        raise KeyError(f"rollout HDF5 is missing {DS_STEP_ID}")
    stored_step_id = _integer(
        hdf5_file[DS_STEP_ID][frame.observation_hdf5_index],
        label="HDF5 observation step_id",
    )
    if stored_step_id != frame.observation_step_id:
        raise ValueError("replay frame does not belong to the supplied HDF5 file")
    stored_qpos = _finite_vector(
        hdf5_file["observations/qpos"][frame.observation_hdf5_index],
        4,
        label="HDF5 qpos",
    )
    stored_qvel = _finite_vector(
        hdf5_file["observations/qvel"][frame.observation_hdf5_index],
        4,
        label="HDF5 qvel",
    )
    if not np.allclose(stored_qpos, frame.qpos, rtol=0.0, atol=1.0e-6) or not np.allclose(
        stored_qvel,
        frame.qvel,
        rtol=0.0,
        atol=1.0e-6,
    ):
        raise ValueError("replay frame qpos/qvel disagrees with supplied HDF5 file")
    observation: dict[str, np.ndarray] = {
        "qpos": stored_qpos.copy(),
        "qvel": stored_qvel.copy(),
    }
    if frame.model_token_key is not None:
        if frame.token is None:
            raise ValueError("conditioned replay frame is missing its token")
        observation[frame.model_token_key] = frame.token.copy()
    for camera_name in names:
        observation[f"image_{camera_name}"] = read_camera_rgb(
            hdf5_file,
            camera_name,
            frame.observation_hdf5_index,
        )
    return observation


def split_stable_recorded_act_segments(
    frames: Sequence[RecordedActReplayFrame],
) -> list[RecordedActReplaySegment]:
    """Split conditionable frames at non-contiguity, token drift, or reset events."""
    ordered = list(frames)
    if not ordered:
        return []
    _validate_frame_order(ordered)
    result: list[RecordedActReplaySegment] = []
    current: list[RecordedActReplayFrame] = [ordered[0]]
    for frame in ordered[1:]:
        previous = current[-1]
        if _starts_new_segment(previous, frame):
            result.append(_build_segment(current))
            current = [frame]
        else:
            current.append(frame)
    result.append(_build_segment(current))
    return result


def deterministic_alternate_segments(
    *,
    segments: Sequence[RecordedActReplaySegment],
    baseline: RecordedActReplaySegment,
) -> list[RecordedActReplaySegment]:
    """Return one deterministic representative for every alternate real token."""
    if baseline.model_token_key is None or baseline.token_sha256 is None:
        raise ValueError(
            "deterministic alternate selection requires a conditioned baseline "
            "with a condition token"
        )
    representatives: dict[str, RecordedActReplaySegment] = {}
    for segment in segments:
        if (
            segment.skill_name != baseline.skill_name
            or segment.model_token_key != baseline.model_token_key
            or segment.token_sha256 is None
            or segment.token_sha256 == baseline.token_sha256
        ):
            continue
        existing = representatives.get(segment.token_sha256)
        if existing is None or _segment_sort_key(segment) < _segment_sort_key(existing):
            representatives[segment.token_sha256] = segment
    return sorted(representatives.values(), key=_segment_sort_key)


def select_deterministic_alternate_segment(
    *,
    segments: Sequence[RecordedActReplaySegment],
    baseline: RecordedActReplaySegment,
    alternate_index: int = 0,
) -> RecordedActReplaySegment:
    """Select one indexed alternate from the stable deterministic ordering."""
    if isinstance(alternate_index, bool) or int(alternate_index) < 0:
        raise ValueError("alternate_index must be a non-negative integer")
    candidates = deterministic_alternate_segments(
        segments=segments,
        baseline=baseline,
    )
    index = int(alternate_index)
    if index >= len(candidates):
        raise ValueError(
            f"alternate_index={index} has no alternate token; candidates={len(candidates)}"
        )
    return candidates[index]


def build_strict_train_numeric_support(
    *,
    primitive_dataset_dir: str | Path,
    split_path: str | Path,
    skill_name: str,
) -> StrictTrainNumericSupport:
    """Build p01/p99 bounds from strict source-safe ACT training rows.

    Only ``action_loss_mask == 1`` rows from the source-aware training split
    are included.  Validation sources are checked but never silently dropped,
    so an accidental source leak fails before any candidate is considered.
    """
    spec = _conditioned_token_spec(skill_name)
    dataset_dir = Path(primitive_dataset_dir).expanduser().resolve(strict=True)
    split_file = Path(split_path).expanduser().resolve(strict=True)
    split = _read_source_aware_split(split_file, dataset_dir=dataset_dir)

    feature_rows: list[np.ndarray] = []
    total_step_count = 0
    masked_step_count = 0
    split_ids = [(primitive_id, "train") for primitive_id in split.train_ids]
    split_ids.extend((primitive_id, "validation") for primitive_id in split.val_ids)
    for primitive_id, partition in split_ids:
        path = dataset_dir / f"episode_{primitive_id}.hdf5"
        if not path.is_file():
            raise FileNotFoundError(path)
        with h5py.File(path, "r") as handle:
            source_episode_id = _source_episode_id(handle)
            expected_source = split.source_by_primitive_episode_id[primitive_id]
            if source_episode_id in split.validation_source_episode_ids and partition == "train":
                raise ValueError(
                    f"train primitive {primitive_id} contains validation source "
                    f"episode {source_episode_id}"
                )
            if source_episode_id != expected_source:
                raise ValueError(
                    f"primitive {primitive_id} source metadata does not match split mapping"
                )
            if partition == "train":
                if source_episode_id not in split.train_source_episode_ids:
                    raise ValueError(
                        f"train primitive {primitive_id} source episode "
                        f"{source_episode_id} is not in the train allowlist"
                    )
            elif source_episode_id not in split.validation_source_episode_ids:
                raise ValueError(
                    f"validation primitive {primitive_id} source episode "
                    f"{source_episode_id} is not in the validation allowlist"
                )
            if partition != "train":
                continue
            qpos = np.asarray(handle["observations/qpos"][:], dtype=np.float32)
            qvel = np.asarray(handle["observations/qvel"][:], dtype=np.float32)
            token = np.asarray(handle[spec.dataset_path][:], dtype=np.float32)
            actions = np.asarray(handle["action"][:], dtype=np.float32)
            count = int(qpos.shape[0])
            if qvel.shape != (count, 4) or actions.shape != (count, 4):
                raise ValueError(f"invalid qvel/action shapes in {path}")
            if qpos.shape != (count, 4) or token.shape != (count, spec.token_dim):
                raise ValueError(f"invalid qpos/token shapes in {path}")
            mask = read_action_loss_mask(
                handle,
                expected_length=count,
                required=True,
            )
            assert mask is not None
            keep = mask == 1
            total_step_count += count
            masked_step_count += int(np.count_nonzero(~keep))
            if not np.any(keep):
                continue
            feature = _feature_matrix(
                qpos=qpos,
                qvel=qvel,
                token=token,
                spec=spec,
            )
            if not np.isfinite(actions[keep]).all() or not np.isfinite(feature[keep]).all():
                raise ValueError(f"non-finite action-supervised ACT inputs in {path}")
            feature_rows.append(feature[keep])
    if not feature_rows:
        raise ValueError("strict train support has no action_loss_mask=1 rows")
    features = np.concatenate(feature_rows, axis=0)
    return StrictTrainNumericSupport(
        skill_name=spec.skill_name,
        model_token_key=spec.model_token_key,
        feature_order=_feature_order(spec),
        p01=np.percentile(features, 1, axis=0).astype(np.float32),
        p99=np.percentile(features, 99, axis=0).astype(np.float32),
        train_source_episode_ids=split.train_source_episode_ids,
        validation_source_episode_ids=split.validation_source_episode_ids,
        total_step_count=total_step_count,
        kept_step_count=int(features.shape[0]),
        masked_step_count=masked_step_count,
    )


def assess_strict_train_numeric_support(
    support: StrictTrainNumericSupport,
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    token: np.ndarray,
) -> NumericSupportAssessment:
    """Evaluate qpos, qvel, and one candidate token against frozen bounds."""
    spec = _conditioned_token_spec(support.skill_name)
    if support.model_token_key != spec.model_token_key:
        raise ValueError("support model token key does not match its skill")
    if tuple(support.feature_order) != _feature_order(spec):
        raise ValueError("support feature order does not match its skill")
    feature = _feature_matrix(qpos=qpos, qvel=qvel, token=token, spec=spec)
    lower = np.asarray(support.p01, dtype=np.float32).reshape(-1)
    upper = np.asarray(support.p99, dtype=np.float32).reshape(-1)
    if lower.shape != (feature.shape[1],) or upper.shape != (feature.shape[1],):
        raise ValueError("support bound dimensions do not match replay features")
    if not np.isfinite(lower).all() or not np.isfinite(upper).all() or np.any(lower > upper):
        raise ValueError("support bounds are invalid")
    frame_in_support = np.logical_and(feature >= lower, feature <= upper).all(axis=1)
    violations: list[tuple[NumericSupportViolation, ...]] = []
    for row in feature:
        row_violations: list[NumericSupportViolation] = []
        for index, (value, low, high) in enumerate(zip(row, lower, upper, strict=True)):
            if value < low:
                row_violations.append(
                    NumericSupportViolation(
                        field=support.feature_order[index],
                        value=float(value),
                        p01=float(low),
                        p99=float(high),
                        kind="below_p01",
                    )
                )
            elif value > high:
                row_violations.append(
                    NumericSupportViolation(
                        field=support.feature_order[index],
                        value=float(value),
                        p01=float(low),
                        p99=float(high),
                        kind="above_p99",
                    )
                )
        violations.append(tuple(row_violations))
    return NumericSupportAssessment(
        feature=feature,
        frame_in_support=frame_in_support.astype(bool),
        violations=tuple(violations),
    )


@dataclass(frozen=True)
class _SourceAwareSplit:
    train_ids: tuple[int, ...]
    val_ids: tuple[int, ...]
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    source_by_primitive_episode_id: dict[int, int]


def _read_source_aware_split(split_path: Path, *, dataset_dir: Path) -> _SourceAwareSplit:
    payload = yaml.safe_load(split_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("source-aware split must contain a mapping")
    if str(payload.get("split_policy", "")) != "source_identity_exact_allowlist_v1":
        raise ValueError("source-aware split policy mismatch")
    recorded_dataset_dir = Path(str(payload.get("dataset_dir", ""))).expanduser()
    if recorded_dataset_dir.resolve() != dataset_dir:
        raise ValueError("source-aware split dataset_dir does not match input dataset")
    train_ids = _integer_tuple(payload.get("train_ids"), label="train_ids")
    val_ids = _integer_tuple(payload.get("val_ids"), label="val_ids")
    if not train_ids or not val_ids:
        raise ValueError("source-aware split must include non-empty train_ids and val_ids")
    if set(train_ids) & set(val_ids):
        raise ValueError("source-aware split train and validation ids overlap")
    train_sources = _integer_tuple(
        payload.get("train_source_episode_ids"),
        label="train_source_episode_ids",
    )
    val_sources = _integer_tuple(
        payload.get("val_source_episode_ids"),
        label="val_source_episode_ids",
    )
    if not train_sources or not val_sources:
        raise ValueError("source-aware split must include train and validation sources")
    if set(train_sources) & set(val_sources):
        raise ValueError("source-aware split train and validation sources overlap")
    allowed_sources = _integer_tuple(
        payload.get("allowed_source_episode_ids"),
        label="allowed_source_episode_ids",
    )
    if set(allowed_sources) != set(train_sources) | set(val_sources):
        raise ValueError("source-aware split allowlist does not match train/validation sources")
    source_mapping = payload.get("source_episode_id_by_primitive_episode_id")
    if not isinstance(source_mapping, Mapping):
        raise ValueError("source-aware split source mapping is missing")
    source_by_primitive = {
        _integer(key, label="source map primitive id"): _source_id(
            value,
            label="source map episode id",
        )
        for key, value in source_mapping.items()
    }
    required_ids = set(train_ids) | set(val_ids)
    if not required_ids <= set(source_by_primitive):
        raise ValueError("source-aware split is missing primitive source mappings")
    for primitive_id in train_ids:
        if source_by_primitive[primitive_id] not in train_sources:
            raise ValueError("source-aware split train primitive maps outside train sources")
    for primitive_id in val_ids:
        if source_by_primitive[primitive_id] not in val_sources:
            raise ValueError("source-aware split validation primitive maps outside validation sources")
    return _SourceAwareSplit(
        train_ids=train_ids,
        val_ids=val_ids,
        train_source_episode_ids=train_sources,
        validation_source_episode_ids=val_sources,
        source_by_primitive_episode_id=source_by_primitive,
    )


def _normalise_requested_skills(skills: Sequence[str]) -> tuple[str, ...]:
    names = tuple(str(value).strip().lower() for value in skills)
    if not names:
        raise ValueError("skills must not be empty")
    if len(names) != len(set(names)):
        raise ValueError("skills contains duplicates")
    for name in names:
        _token_spec(name)
    return names


def _token_spec(skill_name: str) -> _RecordedTokenSpec:
    name = str(skill_name).strip().lower()
    try:
        return _TOKEN_SPECS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported recorded ACT replay skill {skill_name!r}") from exc


def _conditioned_token_spec(skill_name: str) -> _RecordedTokenSpec:
    spec = _token_spec(skill_name)
    if (
        spec.dataset_path is None
        or spec.model_token_key is None
        or spec.token_dim is None
    ):
        raise ValueError(
            f"strict numeric support requires a conditioned Dig or Return skill, got {skill_name!r}"
        )
    return spec


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL row {line_number} in {path}") from exc
        if not isinstance(row, Mapping):
            raise ValueError(f"JSONL row {line_number} must be an object")
        rows.append(dict(row))
    if not rows:
        raise ValueError("rollout JSONL is empty")
    return rows


def _read_jsonl_token(
    row: Mapping[str, Any],
    *,
    spec: _RecordedTokenSpec,
    action_step_id: int,
) -> np.ndarray:
    for key in spec.jsonl_keys:
        if key in row and row[key] is not None:
            return _finite_vector(
                row[key],
                spec.token_dim,
                label=f"{spec.skill_name} token at action step {action_step_id}",
            )
    raise KeyError(
        f"action step {action_step_id} is missing one of {spec.jsonl_keys!r}"
    )


def _optional_row_text(row: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _validate_strictly_increasing(values: Sequence[int], *, label: str) -> None:
    if len(values) < 2:
        raise ValueError(f"{label} must contain at least two rows")
    if any(right <= left for left, right in zip(values, values[1:])):
        raise ValueError(f"{label} must be strictly increasing without duplicates")


def _validate_frame_order(frames: Sequence[RecordedActReplayFrame]) -> None:
    ids = [frame.action_step_id for frame in frames]
    if any(right <= left for left, right in zip(ids, ids[1:])):
        raise ValueError("recorded ACT replay frames must be strictly ordered")


def _starts_new_segment(
    previous: RecordedActReplayFrame,
    current: RecordedActReplayFrame,
) -> bool:
    return bool(
        current.action_step_id != previous.action_step_id + 1
        or current.skill_name != previous.skill_name
        or current.model_token_key != previous.model_token_key
        or not _same_recorded_token(current.token, previous.token)
        or current.skill_switch_reason
        or current.policy_restarted
    )


def _build_segment(frames: Sequence[RecordedActReplayFrame]) -> RecordedActReplaySegment:
    if not frames:
        raise ValueError("cannot build a stable segment without frames")
    first = frames[0]
    if any(
        frame.skill_name != first.skill_name
        or frame.model_token_key != first.model_token_key
        or not _same_recorded_token(frame.token, first.token)
        for frame in frames
    ):
        raise ValueError("stable segment contains multiple skills or tokens")
    if (first.model_token_key is None) != (first.token is None):
        raise ValueError("replay frame condition key/token presence is inconsistent")
    token = None if first.token is None else first.token.copy()
    return RecordedActReplaySegment(
        skill_name=first.skill_name,
        model_token_key=first.model_token_key,
        token=token,
        token_source=first.token_source,
        token_sha256=None if token is None else _token_sha256(token),
        frames=tuple(frames),
        start_action_step_id=first.action_step_id,
        end_action_step_id=frames[-1].action_step_id,
        primitive_cycle_indices=tuple(sorted({frame.primitive_cycle_index for frame in frames})),
    )


def _segment_sort_key(segment: RecordedActReplaySegment) -> tuple[str, int, int]:
    return (
        segment.token_sha256 or "",
        segment.start_action_step_id,
        segment.end_action_step_id,
    )


def _token_sha256(token: np.ndarray) -> str:
    value = np.ascontiguousarray(np.asarray(token, dtype=np.float32).reshape(-1))
    return hashlib.sha256(value.tobytes()).hexdigest()


def _same_recorded_token(
    left: np.ndarray | None,
    right: np.ndarray | None,
) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return bool(np.array_equal(left, right))


def _feature_order(spec: _RecordedTokenSpec) -> tuple[str, ...]:
    return (
        *(f"qpos[{index}]" for index in range(4)),
        *(f"qvel[{index}]" for index in range(4)),
        *(f"{spec.model_token_key}[{index}]" for index in range(spec.token_dim)),
    )


def _feature_matrix(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    token: np.ndarray,
    spec: _RecordedTokenSpec,
) -> np.ndarray:
    qpos_matrix = _feature_matrix_part(qpos, width=4, label="qpos")
    qvel_matrix = _feature_matrix_part(qvel, width=4, label="qvel")
    token_matrix = _feature_matrix_part(
        token,
        width=spec.token_dim,
        label=spec.model_token_key,
    )
    count = int(qpos_matrix.shape[0])
    if qvel_matrix.shape[0] != count or token_matrix.shape[0] != count:
        raise ValueError("qpos, qvel, and token frame counts must match")
    feature = np.concatenate((qpos_matrix, qvel_matrix, token_matrix), axis=1)
    if not np.isfinite(feature).all():
        raise ValueError("numeric support features must be finite")
    return feature.astype(np.float32, copy=False)


def _feature_matrix_part(values: np.ndarray, *, width: int, label: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != width:
        raise ValueError(f"{label} must have shape (T, {width}), got {array.shape}")
    return array


def _source_episode_id(handle: h5py.File) -> int:
    value: Any = None
    if "metadata" in handle:
        value = handle["metadata"].attrs.get("source_episode_id")
    if value is None:
        value = handle.attrs.get("source_episode_id")
    return _source_id(value, label="source_episode_id metadata")


def _source_id(value: Any, *, label: str) -> int:
    if isinstance(value, (bytes, np.bytes_)):
        value = bytes(value).decode("utf-8")
    text = str(value).strip()
    match = re.fullmatch(r"(?:episode_)?(\d+)", text)
    if match is None:
        raise ValueError(f"invalid {label} {value!r}")
    return int(match.group(1))


def _integer_tuple(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    result = tuple(_integer(item, label=label) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be an integer")
    try:
        parsed = int(value)
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if not np.isfinite(numeric) or numeric != float(parsed):
        raise ValueError(f"{label} must be an integer")
    return parsed


def _finite_vector(value: Any, size: int, *, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    if array.shape != (size,) or not np.isfinite(array).all():
        raise ValueError(f"{label} must be finite {size}D")
    return array


__all__ = [
    "NumericSupportAssessment",
    "NumericSupportViolation",
    "RecordedActReplayFrame",
    "RecordedActReplaySegment",
    "StrictTrainNumericSupport",
    "assess_strict_train_numeric_support",
    "build_strict_train_numeric_support",
    "deterministic_alternate_segments",
    "join_recorded_act_replay_frames",
    "read_recorded_act_observation",
    "select_deterministic_alternate_segment",
    "split_stable_recorded_act_segments",
]
