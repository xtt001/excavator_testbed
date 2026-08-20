"""Strict-train expert-action reference facts for Return dispatch diagnostics.

This module is intentionally data-only.  It derives action scale, axis bounds,
first differences, and second-difference jitter from complete
``action_loss_mask == 1`` strict-training rows.  It does not see held
validation outcomes, a checkpoint, a target replay, or a runtime strategy.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

if TYPE_CHECKING:
    from testbed.data.return_temporal_dispatch_validation import (
        ReturnTemporalDispatchFrame,
    )


_ACTION_STD_FLOOR = 1.0e-2


class ReturnTemporalDispatchReferenceError(ValueError):
    """Raised when strict-train expert action facts cannot be computed."""


@dataclass(frozen=True)
class ReturnTemporalActionReference:
    """Strict-train expert-action facts frozen before candidate comparison."""

    fit_partition: Literal["strict_train"]
    action_row_count: int
    source_episode_ids: tuple[int, ...]
    action_mean: np.ndarray
    action_scale: np.ndarray
    action_p01: np.ndarray
    action_p99: np.ndarray
    action_min: np.ndarray
    action_max: np.ndarray
    action_delta_row_count: int
    action_delta_abs_p50: np.ndarray
    action_delta_abs_p95: np.ndarray
    action_delta_abs_p99: np.ndarray
    action_delta_abs_max: np.ndarray
    action_delta_l2_p50: float
    action_delta_l2_p95: float
    action_delta_l2_p99: float
    action_delta_l2_max: float
    jitter_row_count: int
    jitter_abs_p50: np.ndarray
    jitter_abs_p95: np.ndarray
    jitter_abs_p99: np.ndarray
    jitter_abs_max: np.ndarray
    jitter_l2_p50: float
    jitter_l2_p95: float
    jitter_l2_p99: float
    jitter_l2_max: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fit_partition": self.fit_partition,
            "action_row_count": self.action_row_count,
            "source_episode_ids": list(self.source_episode_ids),
            "action_mean": _float_list(self.action_mean),
            "action_scale": _float_list(self.action_scale),
            "action_scale_definition": (
                "strict_train_sample_standard_deviation_ddof1_clamped_to_0p01"
            ),
            "action_p01": _float_list(self.action_p01),
            "action_p99": _float_list(self.action_p99),
            "action_min": _float_list(self.action_min),
            "action_max": _float_list(self.action_max),
            "action_boundary_definition": "strict_train_axis_p01_p99",
            "action_delta_row_count": self.action_delta_row_count,
            "action_delta_definition": (
                "expert_action_t_minus_expert_action_t_minus_1 within one "
                "primitive episode and consecutive action_loss_mask_equals_1 rows"
            ),
            "action_delta_abs_p50": _float_list(self.action_delta_abs_p50),
            "action_delta_abs_p95": _float_list(self.action_delta_abs_p95),
            "action_delta_abs_p99": _float_list(self.action_delta_abs_p99),
            "action_delta_abs_max": _float_list(self.action_delta_abs_max),
            "action_delta_l2_p50": self.action_delta_l2_p50,
            "action_delta_l2_p95": self.action_delta_l2_p95,
            "action_delta_l2_p99": self.action_delta_l2_p99,
            "action_delta_l2_max": self.action_delta_l2_max,
            "jitter_row_count": self.jitter_row_count,
            "jitter_definition": (
                "difference between consecutive expert-action deltas across "
                "three consecutive action_loss_mask_equals_1 rows"
            ),
            "jitter_abs_p50": _float_list(self.jitter_abs_p50),
            "jitter_abs_p95": _float_list(self.jitter_abs_p95),
            "jitter_abs_p99": _float_list(self.jitter_abs_p99),
            "jitter_abs_max": _float_list(self.jitter_abs_max),
            "jitter_l2_p50": self.jitter_l2_p50,
            "jitter_l2_p95": self.jitter_l2_p95,
            "jitter_l2_p99": self.jitter_l2_p99,
            "jitter_l2_max": self.jitter_l2_max,
        }


def build_strict_return_temporal_action_reference(
    frames: Sequence[ReturnTemporalDispatchFrame],
) -> ReturnTemporalActionReference:
    """Freeze strict-train action scale, bounds, deltas, and jitter facts."""

    actions = np.stack([frame.expert_action for frame in frames], axis=0).astype(np.float64)
    if actions.shape[0] < 2:
        raise ReturnTemporalDispatchReferenceError(
            "strict Return train needs at least two action rows"
        )
    if not np.isfinite(actions).all():
        raise ReturnTemporalDispatchReferenceError(
            "strict Return expert actions contain non-finite values"
        )
    sample_std = np.std(actions, axis=0, ddof=1)
    deltas, jitters = _contiguous_train_dynamics(frames)
    if not deltas.size:
        raise ReturnTemporalDispatchReferenceError(
            "strict Return train has no consecutive action rows"
        )
    if not jitters.size:
        raise ReturnTemporalDispatchReferenceError(
            "strict Return train has no three-row jitter windows"
        )
    delta_summary = _absolute_matrix_summary(deltas)
    jitter_summary = _absolute_matrix_summary(jitters)
    return ReturnTemporalActionReference(
        fit_partition="strict_train",
        action_row_count=int(actions.shape[0]),
        source_episode_ids=tuple(
            sorted({frame.provenance.source_episode_id for frame in frames})
        ),
        action_mean=_freeze(np.mean(actions, axis=0)),
        action_scale=_freeze(np.maximum(sample_std, _ACTION_STD_FLOOR)),
        action_p01=_freeze(_quantile(actions, 0.01, axis=0)),
        action_p99=_freeze(_quantile(actions, 0.99, axis=0)),
        action_min=_freeze(np.min(actions, axis=0)),
        action_max=_freeze(np.max(actions, axis=0)),
        action_delta_row_count=int(deltas.shape[0]),
        action_delta_abs_p50=delta_summary["axis_p50"],
        action_delta_abs_p95=delta_summary["axis_p95"],
        action_delta_abs_p99=delta_summary["axis_p99"],
        action_delta_abs_max=delta_summary["axis_max"],
        action_delta_l2_p50=delta_summary["l2_p50"],
        action_delta_l2_p95=delta_summary["l2_p95"],
        action_delta_l2_p99=delta_summary["l2_p99"],
        action_delta_l2_max=delta_summary["l2_max"],
        jitter_row_count=int(jitters.shape[0]),
        jitter_abs_p50=jitter_summary["axis_p50"],
        jitter_abs_p95=jitter_summary["axis_p95"],
        jitter_abs_p99=jitter_summary["axis_p99"],
        jitter_abs_max=jitter_summary["axis_max"],
        jitter_l2_p50=jitter_summary["l2_p50"],
        jitter_l2_p95=jitter_summary["l2_p95"],
        jitter_l2_p99=jitter_summary["l2_p99"],
        jitter_l2_max=jitter_summary["l2_max"],
    )


def _contiguous_train_dynamics(
    frames: Sequence[ReturnTemporalDispatchFrame],
) -> tuple[np.ndarray, np.ndarray]:
    by_episode: dict[int, list[ReturnTemporalDispatchFrame]] = defaultdict(list)
    for frame in frames:
        by_episode[frame.provenance.primitive_episode_id].append(frame)
    all_deltas: list[np.ndarray] = []
    all_jitters: list[np.ndarray] = []
    for episode_frames in by_episode.values():
        run: list[ReturnTemporalDispatchFrame] = []
        for frame in episode_frames:
            if run and (
                frame.action_index != run[-1].action_index + 1
                or frame.action_step_id != run[-1].action_step_id + 1
            ):
                _append_dynamics_run(run, all_deltas, all_jitters)
                run = []
            run.append(frame)
        _append_dynamics_run(run, all_deltas, all_jitters)
    delta = np.concatenate(all_deltas, axis=0) if all_deltas else np.zeros((0, 4))
    jitter = np.concatenate(all_jitters, axis=0) if all_jitters else np.zeros((0, 4))
    return delta, jitter


def _append_dynamics_run(
    frames: Sequence[ReturnTemporalDispatchFrame],
    deltas: list[np.ndarray],
    jitters: list[np.ndarray],
) -> None:
    if len(frames) < 2:
        return
    action = np.stack([frame.expert_action for frame in frames], axis=0).astype(np.float64)
    delta = np.diff(action, axis=0)
    deltas.append(delta)
    if delta.shape[0] >= 2:
        jitters.append(np.diff(delta, axis=0))


def _absolute_matrix_summary(values: np.ndarray) -> dict[str, np.ndarray | float]:
    matrix = np.asarray(values, dtype=np.float64)
    absolute = np.abs(matrix)
    l2 = np.sqrt(np.sum(matrix * matrix, axis=1))
    return {
        "axis_p50": _freeze(_quantile(absolute, 0.50, axis=0)),
        "axis_p95": _freeze(_quantile(absolute, 0.95, axis=0)),
        "axis_p99": _freeze(_quantile(absolute, 0.99, axis=0)),
        "axis_max": _freeze(np.max(absolute, axis=0)),
        "l2_p50": float(_quantile(l2, 0.50, axis=None)),
        "l2_p95": float(_quantile(l2, 0.95, axis=None)),
        "l2_p99": float(_quantile(l2, 0.99, axis=None)),
        "l2_max": float(np.max(l2)),
    }


def _quantile(values: np.ndarray, quantile: float, *, axis: int | None) -> np.ndarray:
    try:
        return np.quantile(values, quantile, axis=axis, method="linear")
    except TypeError:  # pragma: no cover - compatibility with old NumPy only
        return np.quantile(values, quantile, axis=axis, interpolation="linear")


def _freeze(values: Any) -> np.ndarray:
    result = np.asarray(values).copy()
    result.setflags(write=False)
    return result


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


__all__ = [
    "ReturnTemporalActionReference",
    "ReturnTemporalDispatchReferenceError",
    "build_strict_return_temporal_action_reference",
]
