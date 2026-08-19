"""Traceable numeric evidence for recorded support-contract target diagnosis.

The support evaluator supplies an already aligned recorded segment and its
numeric feature matrix.  This helper preserves the qpos/qvel traces and the
JSONL/HDF5 pre-action lineage used to make each segment diagnosis inspectable.
It never fits, selects, or relaxes a support candidate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


def build_recorded_target_trace(
    *,
    segment: Any,
    feature: np.ndarray,
    feature_order: Sequence[str],
) -> dict[str, Any]:
    """Return immutable qpos/qvel trace values and action-observation lineage."""

    matrix = np.asarray(feature, dtype=np.float64)
    names = tuple(str(name) for name in feature_order)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != len(names):
        raise ValueError("target trace feature matrix does not match feature order")
    qpos_indices = _group_indices(names, "qpos")
    qvel_indices = _group_indices(names, "qvel")
    if len(qpos_indices) != 4 or len(qvel_indices) != 4:
        raise ValueError("target trace requires exactly four qpos and four qvel fields")
    frames = _field(segment, "frames", None)
    return {
        "shapes": {
            "frame_count": int(matrix.shape[0]),
            "feature": [int(matrix.shape[0]), int(matrix.shape[1])],
            "qpos": [int(matrix.shape[0]), len(qpos_indices)],
            "qvel": [int(matrix.shape[0]), len(qvel_indices)],
        },
        "feature_groups": {
            "qpos_fields": [names[index] for index in qpos_indices],
            "qvel_fields": [names[index] for index in qvel_indices],
            "token_fields": [
                name
                for index, name in enumerate(names)
                if index not in set(qpos_indices) | set(qvel_indices)
            ],
        },
        "qpos_trace": matrix[:, qpos_indices].tolist(),
        "qvel_trace": matrix[:, qvel_indices].tolist(),
        "frame_lineage": _frame_lineage(frames, expected_count=matrix.shape[0]),
    }


def _frame_lineage(frames: Any, *, expected_count: int) -> dict[str, Any]:
    if frames is None:
        return {"status": "preassembled_feature_matrix_no_frame_lineage", "rows": []}
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)):
        raise ValueError("recorded target frames must be a sequence")
    if len(frames) != expected_count:
        raise ValueError("recorded target frame count does not match feature rows")
    rows: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        record: dict[str, Any] = {"frame_index": index}
        for name in (
            "jsonl_row_index",
            "action_step_id",
            "observation_step_id",
            "action_hdf5_index",
            "observation_hdf5_index",
            "primitive_cycle_index",
            "skill_name",
            "model_token_key",
            "policy_dispatched",
        ):
            value = _field(frame, name, None)
            if value is not None:
                record[name] = value
        action = _field(frame, "action", None)
        if action is not None:
            array = np.asarray(action, dtype=np.float64).reshape(-1)
            if not np.isfinite(array).all():
                raise ValueError("recorded target action contains non-finite values")
            record["recorded_action"] = array.tolist()
        rows.append(record)
    return {"status": "recorded_jsonl_hdf5_pre_action_lineage", "rows": rows}


def _group_indices(feature_order: Sequence[str], group: str) -> list[int]:
    prefix = f"{group}["
    return [index for index, name in enumerate(feature_order) if name.startswith(prefix)]


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = ["build_recorded_target_trace"]
