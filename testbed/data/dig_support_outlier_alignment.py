"""Read-only data-integrity audit for one Dig numeric-support outlier.

This module deliberately stops before policy inference, support-rule fitting, or
runtime decisions.  It answers a narrower question: does a recorded Dig
segment use the same pre-action qpos/qvel representation as the strict-train
numeric support population?  That separation prevents an indexing or feature
contract defect from being reported as a frozen ACT capability limitation.

The public helpers are JSON-ready and dependency-free apart from the existing
recorded-replay data API.  They are also usable with temporary HDF5 fixtures,
so the audit's alignment checks do not need a CUDA model or a no-overwrite
experiment artifact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.action_loss_mask import (
    ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
    read_action_loss_mask,
)
from testbed.data.recorded_act_replay import (
    RecordedActReplaySegment,
    StrictTrainNumericSupport,
    assess_strict_train_numeric_support,
    build_strict_train_numeric_support,
    join_recorded_act_replay_frames,
    split_stable_recorded_act_segments,
)
from testbed.data.schema import DS_QPOS, DS_QVEL

DIG_SUPPORT_OUTLIER_ALIGNMENT_SCHEMA = "dig_support_outlier_alignment_audit_v1"
"""Schema for the read-only alignment result returned by this module."""

EXPECTED_DIG_LOW_DIM_KEYS = ("qpos", "qvel", "dig_cut_tokens")


class DigSupportOutlierAlignmentError(ValueError):
    """Raised when a requested data-alignment audit cannot be trusted."""


@dataclass(frozen=True)
class Hdf5QposQvelContract:
    """Storage facts relevant to qpos/qvel support alignment.

    ``qvel_specific_scale_metadata`` is deliberately limited to a metadata
    field named ``qvel_scale``.  A generic ``metadata/scale`` can describe a
    different field (for example teleoperation action scaling), so this audit
    never treats it as velocity-unit evidence.
    """

    qpos_dtype: str
    qvel_dtype: str
    qpos_order: tuple[str, ...]
    qvel_order: tuple[str, ...]
    qvel_specific_scale_metadata: tuple[float, ...] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "qpos_dtype": self.qpos_dtype,
            "qvel_dtype": self.qvel_dtype,
            "qpos_order": list(self.qpos_order),
            "qvel_order": list(self.qvel_order),
            "qvel_specific_scale_metadata": (
                None
                if self.qvel_specific_scale_metadata is None
                else list(self.qvel_specific_scale_metadata)
            ),
        }


@dataclass(frozen=True)
class DigTrainingInputPaths:
    """Canonical Dig train inputs resolved from its YAML configuration."""

    config_path: Path
    primitive_dataset_dir: Path
    split_path: Path
    train_episode_paths: tuple[Path, ...]
    action_loss_mask_scope: str


def build_dig_support_outlier_frame_rows(
    *,
    segment: RecordedActReplaySegment,
    support: StrictTrainNumericSupport,
) -> list[dict[str, Any]]:
    """Return every pre-action feature row and every frozen v1 bound.

    The stored action at step ``i`` is paired with the observation at ``i-1``
    by :func:`join_recorded_act_replay_frames`.  This function retains those
    separate step ids in each row rather than relabelling the observation as
    the action step.  It does not modify or refit ``support``.
    """

    _validate_dig_segment(segment)
    _validate_dig_support(support)
    qpos = np.stack([frame.qpos for frame in segment.frames], axis=0)
    qvel = np.stack([frame.qvel for frame in segment.frames], axis=0)
    token = np.stack([_required_token(frame) for frame in segment.frames], axis=0)
    assessment = assess_strict_train_numeric_support(
        support,
        qpos=qpos,
        qvel=qvel,
        token=token,
    )
    bounds = {
        field: {"p01": float(lower), "p99": float(upper)}
        for field, lower, upper in zip(
            support.feature_order,
            support.p01,
            support.p99,
            strict=True,
        )
    }
    result: list[dict[str, Any]] = []
    for index, frame in enumerate(segment.frames):
        violations = [
            {
                "field": violation.field,
                "kind": violation.kind,
                "value": violation.value,
                "p01": violation.p01,
                "p99": violation.p99,
            }
            for violation in assessment.violations[index]
        ]
        result.append(
            {
                "jsonl_row_index": frame.jsonl_row_index,
                "action_hdf5_index": frame.action_hdf5_index,
                "observation_hdf5_index": frame.observation_hdf5_index,
                "action_step_id": frame.action_step_id,
                "observation_step_id": frame.observation_step_id,
                "qpos": _float_list(frame.qpos),
                "qvel": _float_list(frame.qvel),
                "token": _float_list(_required_token(frame)),
                "v1_bounds": bounds,
                "in_v1_support": bool(assessment.frame_in_support[index]),
                "violations": violations,
            }
        )
    return result


def inspect_recorded_dig_segment_integrity(
    segment: RecordedActReplaySegment,
) -> dict[str, Any]:
    """Verify frame/step continuity without interpreting a trajectory physically."""

    _validate_dig_segment(segment)
    frames = segment.frames
    pre_action = []
    action_index_identity = []
    action_step_contiguous = []
    observation_step_contiguous = []
    jsonl_index_contiguous = []
    action_hdf5_contiguous = []
    observation_hdf5_contiguous = []
    internal_skill_switches: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        frame_pre_action = (
            frame.action_hdf5_index > 0
            and frame.observation_hdf5_index == frame.action_hdf5_index - 1
            and frame.observation_step_id == frame.action_step_id - 1
        )
        pre_action.append(frame_pre_action)
        action_index_identity.append(frame.action_hdf5_index == frame.jsonl_row_index)
        if index:
            previous = frames[index - 1]
            action_step_contiguous.append(
                frame.action_step_id == previous.action_step_id + 1
            )
            observation_step_contiguous.append(
                frame.observation_step_id == previous.observation_step_id + 1
            )
            jsonl_index_contiguous.append(
                frame.jsonl_row_index == previous.jsonl_row_index + 1
            )
            action_hdf5_contiguous.append(
                frame.action_hdf5_index == previous.action_hdf5_index + 1
            )
            observation_hdf5_contiguous.append(
                frame.observation_hdf5_index == previous.observation_hdf5_index + 1
            )
            if frame.skill_switch_reason:
                internal_skill_switches.append(
                    {
                        "action_step_id": frame.action_step_id,
                        "skill_switch_reason": frame.skill_switch_reason,
                    }
                )
    if not all(pre_action):
        raise DigSupportOutlierAlignmentError(
            "Dig segment contains an action that is not paired with its immediate "
            "pre-action observation"
        )
    if not all(action_index_identity):
        raise DigSupportOutlierAlignmentError(
            "Dig segment JSONL row indices do not match HDF5 action indices"
        )
    if not all(
        action_step_contiguous
        + observation_step_contiguous
        + jsonl_index_contiguous
        + action_hdf5_contiguous
        + observation_hdf5_contiguous
    ):
        raise DigSupportOutlierAlignmentError(
            "Dig segment has a non-contiguous JSONL/HDF5/step inventory"
        )
    token = _required_token(frames[0])
    token_stable = all(
        np.array_equal(_required_token(frame), token) for frame in frames
    )
    if not token_stable:
        raise DigSupportOutlierAlignmentError(
            "Dig segment token changes within the segment"
        )
    qvel = np.stack([frame.qvel for frame in frames], axis=0)
    return {
        "all_actions_use_immediate_pre_action_observation": True,
        "jsonl_hdf5_action_index_identity": True,
        "action_step_ids_contiguous": True,
        "observation_step_ids_contiguous": True,
        "jsonl_row_indices_contiguous": True,
        "action_hdf5_indices_contiguous": True,
        "observation_hdf5_indices_contiguous": True,
        "entry_skill_switch_reason": frames[0].skill_switch_reason or None,
        "internal_skill_switches": internal_skill_switches,
        "policy_restart_action_step_ids": [
            frame.action_step_id for frame in frames if frame.policy_restarted
        ],
        "token_stable": token_stable,
        "qvel_first_difference": _qvel_difference_dict(np.diff(qvel, axis=0)),
        "qvel_second_difference": _qvel_difference_dict(np.diff(qvel, n=2, axis=0)),
        "single_frame_local_extremum_candidates": _local_qvel_extrema(frames, qvel),
        "spike_interpretation": (
            "not_inferred_from_velocity_trace_alone; inspect the complete "
            "per-frame trace and contiguous support violations"
        ),
    }


def compare_dig_qvel_feature_contracts(
    *,
    replay: Hdf5QposQvelContract,
    training: Sequence[Hdf5QposQvelContract],
) -> dict[str, Any]:
    """Compare storage representation without guessing physical qvel units."""

    contracts = tuple(training)
    if not contracts:
        raise DigSupportOutlierAlignmentError(
            "at least one strict-train HDF5 contract is required"
        )
    same_qpos_dtype = all(item.qpos_dtype == replay.qpos_dtype for item in contracts)
    same_qvel_dtype = all(item.qvel_dtype == replay.qvel_dtype for item in contracts)
    same_qpos_order = all(item.qpos_order == replay.qpos_order for item in contracts)
    same_qvel_order = all(item.qvel_order == replay.qvel_order for item in contracts)
    same_qvel_scale = all(
        item.qvel_specific_scale_metadata == replay.qvel_specific_scale_metadata
        for item in contracts
    )
    same_raw_qvel = same_qvel_dtype and same_qvel_order and same_qvel_scale
    same_full_observation = same_qpos_dtype and same_qpos_order and same_raw_qvel
    return {
        "replay": replay.as_dict(),
        "replay_qvel_index_metadata": _index_metadata(
            replay.qvel_order,
            prefix="qvel",
        ),
        "strict_train_contract_count": len(contracts),
        "strict_train_unique_qpos_dtypes": sorted(
            {item.qpos_dtype for item in contracts}
        ),
        "strict_train_unique_qvel_dtypes": sorted(
            {item.qvel_dtype for item in contracts}
        ),
        "strict_train_unique_qpos_orders": _unique_orders(
            item.qpos_order for item in contracts
        ),
        "strict_train_unique_qvel_orders": _unique_orders(
            item.qvel_order for item in contracts
        ),
        "same_qpos_dtype": same_qpos_dtype,
        "same_qvel_dtype": same_qvel_dtype,
        "same_qpos_order": same_qpos_order,
        "same_qvel_order": same_qvel_order,
        "same_qvel_specific_scale_metadata": same_qvel_scale,
        "same_raw_qvel_representation": same_raw_qvel,
        "same_full_qpos_qvel_representation": same_full_observation,
        "qvel_scale_evidence": (
            "raw_hdf5_float32_identity"
            if replay.qvel_dtype == "float32"
            else "raw_hdf5_identity_without_qvel_specific_scale_metadata"
        ),
        "generic_metadata_scale_used_as_qvel_evidence": False,
        "physical_unit_inference": "not_attempted",
    }


def audit_dig_support_outlier_alignment_from_paths(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    dig_training_config_path: str | Path,
    target_segment_id: str,
) -> dict[str, Any]:
    """Run the read-only Dig alignment audit from immutable source paths.

    This convenience entry point creates no files.  It resolves only the
    canonical Dig configuration, derives the historical v1 p01/p99 support
    using the existing public data API, and returns a JSON-ready result for a
    caller that owns artifact creation.
    """

    rollout_hdf5 = Path(rollout_hdf5_path).expanduser().resolve(strict=True)
    rollout_jsonl = Path(rollout_jsonl_path).expanduser().resolve(strict=True)
    training = resolve_dig_training_input_paths(dig_training_config_path)
    support = build_strict_train_numeric_support(
        primitive_dataset_dir=training.primitive_dataset_dir,
        split_path=training.split_path,
        skill_name="dig",
    )
    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=rollout_hdf5,
        rollout_jsonl_path=rollout_jsonl,
        skills=("dig",),
    )
    segments = split_stable_recorded_act_segments(frames)
    segment = _select_target_segment(segments, target_segment_id=target_segment_id)
    frame_table = build_dig_support_outlier_frame_rows(segment=segment, support=support)
    alignment = inspect_recorded_dig_segment_integrity(segment)
    replay_contract = read_hdf5_qpos_qvel_contract(rollout_hdf5)
    train_contracts = tuple(
        read_hdf5_qpos_qvel_contract(path) for path in training.train_episode_paths
    )
    feature_contract = compare_dig_qvel_feature_contracts(
        replay=replay_contract,
        training=train_contracts,
    )
    mask = inspect_strict_train_action_loss_mask(
        episode_paths=training.train_episode_paths,
        support=support,
        action_loss_mask_scope=training.action_loss_mask_scope,
    )
    alignment_valid = (
        feature_contract["same_full_qpos_qvel_representation"]
        and mask["only_action_loss_mask_one_used"]
    )
    return {
        "schema": DIG_SUPPORT_OUTLIER_ALIGNMENT_SCHEMA,
        "status": "completed" if alignment_valid else "alignment_invalid",
        "diagnostic_only": True,
        "runtime_support_change": False,
        "threshold_change": False,
        "training_change": False,
        "target_rollout_used_to_tune_support": False,
        "target_segment_id": segment.segment_id,
        "source_paths": {
            "rollout_hdf5": str(rollout_hdf5),
            "rollout_jsonl": str(rollout_jsonl),
            "dig_training_config": str(training.config_path),
            "strict_train_primitive_dataset_dir": str(training.primitive_dataset_dir),
            "strict_train_split": str(training.split_path),
        },
        "frame_table": frame_table,
        "v1_out_of_support_runs": _summarize_out_of_support_runs(frame_table),
        "alignment": alignment,
        "feature_contract": feature_contract,
        "training_action_loss_mask": mask,
        "causal_boundary": {
            "alignment_valid": alignment_valid,
            "if_alignment_valid": (
                "this result only excludes the audited storage/index mismatch; "
                "it does not establish whether strict-train coverage is sufficient"
            ),
            "if_alignment_invalid": (
                "do not interpret the numeric support rejection as a model or "
                "training-coverage limitation until the data contract is repaired"
            ),
        },
    }


def resolve_dig_training_input_paths(
    dig_training_config_path: str | Path,
) -> DigTrainingInputPaths:
    """Resolve the strict-train Dig paths and require its frozen feature order."""

    config_path = Path(dig_training_config_path).expanduser().resolve(strict=True)
    config = _read_yaml_mapping(config_path, label="Dig training config")
    task = _required_mapping(config, "task", label="Dig training config")
    policy = _required_mapping(config, "policy", label="Dig training config")
    train = _required_mapping(config, "train", label="Dig training config")
    low_dim_keys = tuple(
        str(item) for item in _required_sequence(policy, "low_dim_keys")
    )
    if low_dim_keys != EXPECTED_DIG_LOW_DIM_KEYS:
        raise DigSupportOutlierAlignmentError(
            "Dig training low_dim_keys do not match the frozen qpos/qvel/dig token contract"
        )
    scope = str(train.get("action_loss_mask_scope", "")).strip()
    if scope != ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS:
        raise DigSupportOutlierAlignmentError(
            "Dig training action_loss_mask_scope must be loss_sampling_stats"
        )
    dataset_dir = _resolve_config_path(
        task.get("dataset_dir"),
        config_path=config_path,
        label="Dig task.dataset_dir",
    )
    split_path = _resolve_config_path(
        train.get("split_path"),
        config_path=config_path,
        label="Dig train.split_path",
    )
    split = _read_yaml_mapping(split_path, label="Dig source-aware split")
    if split.get("split_policy") != "source_identity_exact_allowlist_v1":
        raise DigSupportOutlierAlignmentError("Dig source split policy mismatch")
    train_ids = _integer_sequence(split.get("train_ids"), label="Dig split train_ids")
    if not train_ids:
        raise DigSupportOutlierAlignmentError(
            "Dig source split has no strict-train episodes"
        )
    paths = tuple(
        dataset_dir / f"episode_{episode_id}.hdf5" for episode_id in train_ids
    )
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"strict-train Dig episodes are missing: {missing!r}")
    return DigTrainingInputPaths(
        config_path=config_path,
        primitive_dataset_dir=dataset_dir,
        split_path=split_path,
        train_episode_paths=paths,
        action_loss_mask_scope=scope,
    )


def read_hdf5_qpos_qvel_contract(path: str | Path) -> Hdf5QposQvelContract:
    """Read only qpos/qvel storage metadata; no policy or action is loaded."""

    hdf5_path = Path(path).expanduser().resolve(strict=True)
    with h5py.File(hdf5_path, "r") as handle:
        for dataset_path in (DS_QPOS, DS_QVEL):
            if dataset_path not in handle:
                raise DigSupportOutlierAlignmentError(
                    f"{hdf5_path} is missing {dataset_path}"
                )
            dataset = handle[dataset_path]
            if dataset.ndim != 2 or dataset.shape[1] != 4:
                raise DigSupportOutlierAlignmentError(
                    f"{hdf5_path} {dataset_path} must have shape (T, 4)"
                )
        metadata = handle.get("metadata")
        if not isinstance(metadata, h5py.Group):
            raise DigSupportOutlierAlignmentError(f"{hdf5_path} is missing metadata")
        return Hdf5QposQvelContract(
            qpos_dtype=str(handle[DS_QPOS].dtype),
            qvel_dtype=str(handle[DS_QVEL].dtype),
            qpos_order=_metadata_order(metadata, "qpos_order", path=hdf5_path),
            qvel_order=_metadata_order(metadata, "qvel_order", path=hdf5_path),
            qvel_specific_scale_metadata=_qvel_specific_scale(metadata, path=hdf5_path),
        )


def inspect_strict_train_action_loss_mask(
    *,
    episode_paths: Sequence[str | Path],
    support: StrictTrainNumericSupport,
    action_loss_mask_scope: str,
) -> dict[str, Any]:
    """Prove the v1 support population is counted from mask==1 train rows."""

    if action_loss_mask_scope != ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS:
        raise DigSupportOutlierAlignmentError(
            "strict numeric support audit requires loss_sampling_stats mask scope"
        )
    paths = tuple(
        Path(path).expanduser().resolve(strict=True) for path in episode_paths
    )
    if not paths:
        raise DigSupportOutlierAlignmentError(
            "strict-train mask audit needs episode paths"
        )
    total_step_count = 0
    kept_step_count = 0
    masked_step_count = 0
    episode_records: list[dict[str, Any]] = []
    for path in paths:
        with h5py.File(path, "r") as handle:
            if DS_QPOS not in handle:
                raise DigSupportOutlierAlignmentError(f"{path} is missing {DS_QPOS}")
            count = int(handle[DS_QPOS].shape[0])
            mask = read_action_loss_mask(handle, expected_length=count, required=True)
            assert mask is not None
            kept = int(np.count_nonzero(mask == 1))
            masked = int(np.count_nonzero(mask == 0))
        total_step_count += count
        kept_step_count += kept
        masked_step_count += masked
        episode_records.append(
            {
                "path": str(path),
                "step_count": count,
                "action_loss_mask_one_count": kept,
                "action_loss_mask_zero_count": masked,
            }
        )
    count_matches_support = (
        total_step_count == support.total_step_count
        and kept_step_count == support.kept_step_count
        and masked_step_count == support.masked_step_count
    )
    return {
        "action_loss_mask_scope": action_loss_mask_scope,
        "episode_count": len(paths),
        "total_step_count": total_step_count,
        "kept_step_count": kept_step_count,
        "masked_step_count": masked_step_count,
        "support_counts_match_strict_train_mask_inventory": count_matches_support,
        "only_action_loss_mask_one_used": count_matches_support,
        "episodes": episode_records,
    }


def _select_target_segment(
    segments: Sequence[RecordedActReplaySegment],
    *,
    target_segment_id: str,
) -> RecordedActReplaySegment:
    matches = [
        segment for segment in segments if segment.segment_id == target_segment_id
    ]
    if len(matches) != 1:
        available = [segment.segment_id for segment in segments]
        raise DigSupportOutlierAlignmentError(
            f"target Dig segment {target_segment_id!r} was not uniquely found; "
            f"available={available!r}"
        )
    return matches[0]


def _summarize_out_of_support_runs(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    open_runs: dict[str, dict[str, Any]] = {}
    result: list[dict[str, Any]] = []
    for row in rows:
        step_id = _required_int(row.get("action_step_id"), label="frame action_step_id")
        present = {
            str(violation["field"])
            for violation in _required_sequence(row, "violations")
            if isinstance(violation, Mapping)
        }
        for field in list(open_runs):
            current = open_runs[field]
            if field not in present or step_id != current["end_action_step_id"] + 1:
                result.append(current)
                del open_runs[field]
        for field in sorted(present):
            if field not in open_runs:
                open_runs[field] = {
                    "field": field,
                    "start_action_step_id": step_id,
                    "end_action_step_id": step_id,
                    "frame_count": 1,
                }
            else:
                open_runs[field]["end_action_step_id"] = step_id
                open_runs[field]["frame_count"] += 1
    result.extend(open_runs.values())
    return sorted(
        result,
        key=lambda item: (str(item["field"]), int(item["start_action_step_id"])),
    )


def _validate_dig_segment(segment: RecordedActReplaySegment) -> None:
    if segment.skill_name != "dig":
        raise DigSupportOutlierAlignmentError(
            "outlier alignment only accepts a Dig segment"
        )
    if segment.model_token_key != "dig_cut_tokens":
        raise DigSupportOutlierAlignmentError("Dig segment model token key mismatch")
    if not segment.frames:
        raise DigSupportOutlierAlignmentError(
            "Dig segment must contain at least one frame"
        )
    if (
        segment.start_action_step_id != segment.frames[0].action_step_id
        or segment.end_action_step_id != segment.frames[-1].action_step_id
    ):
        raise DigSupportOutlierAlignmentError(
            "Dig segment step range does not match frames"
        )


def _validate_dig_support(support: StrictTrainNumericSupport) -> None:
    if support.skill_name != "dig" or support.model_token_key != "dig_cut_tokens":
        raise DigSupportOutlierAlignmentError(
            "support is not the Dig v1 support contract"
        )
    expected = tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"dig_cut_tokens[{index}]" for index in range(10)]
    )
    if support.feature_order != expected:
        raise DigSupportOutlierAlignmentError("Dig support feature order mismatch")


def _required_token(frame: Any) -> np.ndarray:
    token = frame.token
    if token is None:
        raise DigSupportOutlierAlignmentError("Dig replay frame is missing its token")
    result = np.asarray(token, dtype=np.float32).reshape(-1)
    if result.shape != (10,) or not np.isfinite(result).all():
        raise DigSupportOutlierAlignmentError("Dig replay token must be finite 10D")
    return result


def _qvel_difference_dict(difference: np.ndarray) -> dict[str, list[float]]:
    matrix = np.asarray(difference, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1:] != (4,):
        raise AssertionError(f"unexpected qvel difference shape {matrix.shape}")
    return {f"qvel[{axis}]": _float_list(matrix[:, axis]) for axis in range(4)}


def _local_qvel_extrema(
    frames: Sequence[Any],
    qvel: np.ndarray,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index in range(1, qvel.shape[0] - 1):
        for axis in range(4):
            previous = float(qvel[index - 1, axis])
            current = float(qvel[index, axis])
            following = float(qvel[index + 1, axis])
            if current > max(previous, following) or current < min(previous, following):
                result.append(
                    {
                        "action_step_id": int(frames[index].action_step_id),
                        "field": f"qvel[{axis}]",
                        "value": current,
                        "previous_value": previous,
                        "next_value": following,
                    }
                )
    return result


def _metadata_order(
    metadata: h5py.Group,
    key: str,
    *,
    path: Path,
) -> tuple[str, ...]:
    value = metadata.attrs.get(key)
    if value is None:
        raise DigSupportOutlierAlignmentError(f"{path} is missing metadata/{key}")
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    fields = tuple(part.strip() for part in str(value).split(",") if part.strip())
    if len(fields) != 4:
        raise DigSupportOutlierAlignmentError(
            f"{path} metadata/{key} must name exactly four fields"
        )
    return fields


def _qvel_specific_scale(
    metadata: h5py.Group, *, path: Path
) -> tuple[float, ...] | None:
    value = metadata.attrs.get("qvel_scale")
    if value is None:
        return None
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if array.shape != (4,) or not np.isfinite(array).all():
        raise DigSupportOutlierAlignmentError(
            f"{path} metadata/qvel_scale must be finite length 4"
        )
    return tuple(float(item) for item in array)


def _unique_orders(orders: Any) -> list[list[str]]:
    unique = sorted({tuple(order) for order in orders})
    return [list(order) for order in unique]


def _index_metadata(order: Sequence[str], *, prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "feature": f"{prefix}[{index}]",
            "metadata_field": field,
            "physical_unit": "not_inferred",
        }
        for index, field in enumerate(order)
    ]


def _read_yaml_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise DigSupportOutlierAlignmentError(f"{label} must contain a mapping")
    return payload


def _required_mapping(
    mapping: Mapping[str, Any],
    key: str,
    *,
    label: str,
) -> Mapping[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise DigSupportOutlierAlignmentError(f"{label} is missing mapping {key!r}")
    return value


def _required_sequence(mapping: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = mapping.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DigSupportOutlierAlignmentError(f"mapping is missing sequence {key!r}")
    return value


def _resolve_config_path(value: Any, *, config_path: Path, label: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise DigSupportOutlierAlignmentError(f"{label} must be a non-empty path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = config_path.parent / candidate
    return candidate.resolve(strict=True)


def _integer_sequence(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DigSupportOutlierAlignmentError(f"{label} must be a sequence")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise DigSupportOutlierAlignmentError(f"{label} contains a non-integer")
        try:
            parsed = int(item)
        except (TypeError, ValueError) as exc:
            raise DigSupportOutlierAlignmentError(
                f"{label} contains a non-integer"
            ) from exc
        if parsed != item:
            raise DigSupportOutlierAlignmentError(f"{label} contains a non-integer")
        result.append(parsed)
    if len(result) != len(set(result)):
        raise DigSupportOutlierAlignmentError(f"{label} contains duplicates")
    return tuple(result)


def _required_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise DigSupportOutlierAlignmentError(f"{label} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DigSupportOutlierAlignmentError(f"{label} must be an integer") from exc


def _float_list(values: Any) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


__all__ = [
    "DIG_SUPPORT_OUTLIER_ALIGNMENT_SCHEMA",
    "EXPECTED_DIG_LOW_DIM_KEYS",
    "DigSupportOutlierAlignmentError",
    "DigTrainingInputPaths",
    "Hdf5QposQvelContract",
    "audit_dig_support_outlier_alignment_from_paths",
    "build_dig_support_outlier_frame_rows",
    "compare_dig_qvel_feature_contracts",
    "inspect_recorded_dig_segment_integrity",
    "inspect_strict_train_action_loss_mask",
    "read_hdf5_qpos_qvel_contract",
    "resolve_dig_training_input_paths",
]
