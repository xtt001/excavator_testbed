"""Fail-closed continuous-goal qpos sweep prediction contracts.

This module owns only the Python-side handoff-to-dig reference path contract.
It deliberately provides no geometric or nearest-expert fallback predictor.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

CONTINUOUS_GOAL_3D_PREDICTOR_MISSING = (
    "continuous_goal_3d_predictor_missing"
)
CONTINUOUS_ACT_TRACKING_MARGIN_M = 0.05
CONTINUOUS_POSE_INTERPOLATION_BOUND_M = 0.01
CONTINUOUS_HARD_CLEARANCE_M = 0.24
CONTINUOUS_QPOS_PATH_START_TOLERANCE = 1.0e-6
CONTINUOUS_QPOS_ORDER = (
    "swing",
    "boom",
    "stick",
    "bucket",
)


class ContinuousGoalQposSweepContractError(ValueError):
    """Raised when continuous-goal sweep lineage cannot be trusted."""


class ContinuousGoalQposSweepPredictor(Protocol):
    """Production interface for a goal-conditioned handoff-to-dig path."""

    def predict(
        self,
        live_handoff_state: Any,
        goal: Any,
    ) -> PlannedReferenceQposSweep:
        """Predict a path beginning at the actual live handoff qpos."""


@dataclass(frozen=True)
class ContinuousWorktoolSweepMargins:
    """The immutable Python-owned clearance budget for continuous mode."""

    act_tracking_margin_m: float = CONTINUOUS_ACT_TRACKING_MARGIN_M
    pose_interpolation_bound_m: float = (
        CONTINUOUS_POSE_INTERPOLATION_BOUND_M
    )
    hard_clearance_m: float = CONTINUOUS_HARD_CLEARANCE_M

    def __post_init__(self) -> None:
        actual = (
            float(self.act_tracking_margin_m),
            float(self.pose_interpolation_bound_m),
            float(self.hard_clearance_m),
        )
        expected = (
            CONTINUOUS_ACT_TRACKING_MARGIN_M,
            CONTINUOUS_POSE_INTERPOLATION_BOUND_M,
            CONTINUOUS_HARD_CLEARANCE_M,
        )
        if actual != expected:
            raise ContinuousGoalQposSweepContractError(
                "continuous worktool sweep margins are locked to "
                "ACT=0.05m, interpolation=0.01m, hard_clearance=0.24m"
            )


@dataclass(frozen=True)
class PlannedReferenceQposSweep:
    """Immutable predictor output with byte-exact path lineage."""

    goal_id: str
    handoff_qpos: tuple[float, ...]
    handoff_qvel: tuple[float, ...]
    qpos_order: tuple[str, ...]
    qpos_path: np.ndarray
    predictor_profile: str
    predictor_version: str
    predictor_code_sha256: str
    path_sha256: str

    @classmethod
    def create(
        cls,
        *,
        goal_id: str,
        handoff_qpos: Any,
        handoff_qvel: Any,
        qpos_path: Any,
        predictor_profile: str,
        predictor_version: str,
        predictor_code_sha256: str,
        qpos_order: tuple[str, ...] | list[str] = CONTINUOUS_QPOS_ORDER,
    ) -> PlannedReferenceQposSweep:
        goal_sha = _sha256_text(goal_id, label="goal_id")
        code_sha = _sha256_text(
            predictor_code_sha256,
            label="predictor_code_sha256",
        )
        profile = str(predictor_profile).strip()
        version = str(predictor_version).strip()
        if not profile or not version:
            raise ContinuousGoalQposSweepContractError(
                "predictor profile and version must be non-empty"
            )

        order = tuple(str(value) for value in qpos_order)
        if order != CONTINUOUS_QPOS_ORDER:
            raise ContinuousGoalQposSweepContractError(
                "continuous qpos order must be "
                f"{list(CONTINUOUS_QPOS_ORDER)!r}"
            )
        handoff = _finite_vector(
            handoff_qpos,
            size=4,
            label="handoff_qpos",
        )
        velocity = _finite_vector(
            handoff_qvel,
            size=4,
            label="handoff_qvel",
        )
        path = np.asarray(qpos_path, dtype="<f4", order="C")
        if path.ndim != 2 or path.shape[0] < 2 or path.shape[1] != 4:
            raise ContinuousGoalQposSweepContractError(
                "qpos_path must have shape (N, 4) with N >= 2"
            )
        if not np.all(np.isfinite(path)):
            raise ContinuousGoalQposSweepContractError(
                "qpos_path contains non-finite values"
            )
        start_error = float(
            np.max(
                np.abs(
                    path[0].astype(np.float64)
                    - np.asarray(handoff, dtype=np.float64)
                )
            )
        )
        if start_error > CONTINUOUS_QPOS_PATH_START_TOLERANCE:
            raise ContinuousGoalQposSweepContractError(
                "qpos_path path[0] must match handoff_qpos within 1e-06; "
                f"max_abs_difference={start_error}"
            )

        immutable_path = np.array(path, dtype=np.float32, order="C", copy=True)
        path_sha = hashlib.sha256(
            np.asarray(immutable_path, dtype="<f4", order="C").tobytes(
                order="C"
            )
        ).hexdigest()
        immutable_path.setflags(write=False)
        return cls(
            goal_id=goal_sha,
            handoff_qpos=handoff,
            handoff_qvel=velocity,
            qpos_order=order,
            qpos_path=immutable_path,
            predictor_profile=profile,
            predictor_version=version,
            predictor_code_sha256=code_sha,
            path_sha256=path_sha,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the append-only Unity request lineage fields."""

        return {
            "goal_id": self.goal_id,
            "goal_sha256": self.goal_id,
            "handoff_qpos": list(self.handoff_qpos),
            "handoff_qvel": list(self.handoff_qvel),
            "predictor": {
                "profile": self.predictor_profile,
                "version": self.predictor_version,
                "code_sha256": self.predictor_code_sha256,
            },
            "qpos_order": list(self.qpos_order),
            "planned_qpos_path": self.qpos_path.tolist(),
            "path_sha256": self.path_sha256,
        }


@dataclass(frozen=True)
class ContinuousGoalQposSweepPrediction:
    """A passed sweep or the explicit missing-provider offline blocker."""

    status: str
    blocker: str
    sweep: PlannedReferenceQposSweep | None

    @property
    def act_inference_allowed(self) -> bool:
        return self.status == "passed" and self.sweep is not None


def predict_continuous_goal_qpos_sweep(
    *,
    predictor: ContinuousGoalQposSweepPredictor | None,
    live_handoff_state: Any,
    goal: Any,
) -> ContinuousGoalQposSweepPrediction:
    """Invoke the provider once, without any recorded-path fallback."""

    if predictor is None:
        return ContinuousGoalQposSweepPrediction(
            status="blocked",
            blocker=CONTINUOUS_GOAL_3D_PREDICTOR_MISSING,
            sweep=None,
        )
    sweep = predictor.predict(live_handoff_state, goal)
    if not isinstance(sweep, PlannedReferenceQposSweep):
        raise ContinuousGoalQposSweepContractError(
            "continuous qpos predictor must return PlannedReferenceQposSweep"
        )
    goal_id = str(getattr(goal, "goal_id", ""))
    if sweep.goal_id != goal_id:
        raise ContinuousGoalQposSweepContractError(
            "continuous qpos predictor goal identity drift"
        )
    live_qpos = _state_vector(live_handoff_state, key="qpos")
    live_qvel = _state_vector(live_handoff_state, key="qvel")
    if _max_abs_difference(live_qpos, sweep.handoff_qpos) > (
        CONTINUOUS_QPOS_PATH_START_TOLERANCE
    ):
        raise ContinuousGoalQposSweepContractError(
            "continuous qpos predictor handoff qpos drift"
        )
    if _max_abs_difference(live_qvel, sweep.handoff_qvel) > (
        CONTINUOUS_QPOS_PATH_START_TOLERANCE
    ):
        raise ContinuousGoalQposSweepContractError(
            "continuous qpos predictor handoff qvel drift"
        )
    return ContinuousGoalQposSweepPrediction(
        status="passed",
        blocker="",
        sweep=sweep,
    )


def _state_vector(state: Any, *, key: str) -> tuple[float, ...]:
    if isinstance(state, dict):
        value = state.get(key)
    else:
        value = getattr(state, key, None)
    return _finite_vector(value, size=4, label=f"live_handoff_state.{key}")


def _finite_vector(value: Any, *, size: int, label: str) -> tuple[float, ...]:
    try:
        array = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalQposSweepContractError(
            f"{label} must contain {size} finite values"
        ) from exc
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ContinuousGoalQposSweepContractError(
            f"{label} must contain {size} finite values"
        )
    return tuple(float(item) for item in array)


def _max_abs_difference(first: Any, second: Any) -> float:
    return float(
        np.max(
            np.abs(
                np.asarray(first, dtype=np.float64)
                - np.asarray(second, dtype=np.float64)
            )
        )
    )


def _sha256_text(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ContinuousGoalQposSweepContractError(
            f"{label} must be a lowercase SHA256"
        )
    return text


__all__ = [
    "CONTINUOUS_ACT_TRACKING_MARGIN_M",
    "CONTINUOUS_GOAL_3D_PREDICTOR_MISSING",
    "CONTINUOUS_HARD_CLEARANCE_M",
    "CONTINUOUS_POSE_INTERPOLATION_BOUND_M",
    "CONTINUOUS_QPOS_ORDER",
    "CONTINUOUS_QPOS_PATH_START_TOLERANCE",
    "ContinuousGoalQposSweepContractError",
    "ContinuousGoalQposSweepPrediction",
    "ContinuousGoalQposSweepPredictor",
    "ContinuousWorktoolSweepMargins",
    "PlannedReferenceQposSweep",
    "predict_continuous_goal_qpos_sweep",
]
