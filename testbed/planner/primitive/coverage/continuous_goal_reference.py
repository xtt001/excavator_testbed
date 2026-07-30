"""Validated v2 predictor bridge for calibrated continuous-goal references.

This module adds an offline/mainline interface without changing the frozen
legacy predictor entry point or any default planner configuration.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from testbed.data.continuous_goal_qpos_paths import (
    PATH_PROGRESS,
    PATH_PROGRESS_POINT_COUNT,
    QPOS_DIM,
    ContinuousGoalQposPathContractError,
    ContinuousGoalWorktoolSweepInputV2,
    qpos_path_sha256,
)

CONTINUOUS_GOAL_QPOS_PREDICTOR_V2_MISSING = "continuous_goal_qpos_predictor_v2_missing"
CONTINUOUS_GOAL_REFERENCE_SCHEMA = "continuous_goal_reference_v2"
CONTINUOUS_GOAL_REFERENCE_START_TOLERANCE = 1.0e-6
CONTINUOUS_GOAL_REFERENCE_COVERAGE_LEVEL = 0.95
CONTINUOUS_GOAL_REFERENCE_QPOS_ORDER = (
    "swing",
    "boom",
    "stick",
    "bucket",
)
CONTINUOUS_GOAL_REFERENCE_REQUIRED_LINEAGE = (
    "normalization_sha256",
    "checkpoint_sha256",
    "calibration_sha256",
    "predictor_code_sha256",
)


class ContinuousGoalReferencePredictor(Protocol):
    """Provider of a calibrated v2 reference prediction."""

    def predict(
        self,
        sweep_input: ContinuousGoalWorktoolSweepInputV2,
        *,
        expected_lineage: Mapping[str, str] | None = None,
    ) -> Any:
        """Return a prediction with path, uncertainty, support, and lineage."""


@dataclass(frozen=True)
class CalibratedContinuousGoalReference:
    """Planner-facing reference after independent output validation."""

    goal_sha256: str
    input_sha256: str
    handoff_qpos: tuple[float, float, float, float]
    handoff_qvel: tuple[float, float, float, float]
    path_progress: np.ndarray
    qpos_path: np.ndarray
    qpos_abs_error_bound: np.ndarray
    coverage_level: float
    support_status: str
    ood_score: float
    normalization_sha256: str
    checkpoint_sha256: str
    calibration_sha256: str
    predictor_code_sha256: str
    path_sha256: str
    schema: str = CONTINUOUS_GOAL_REFERENCE_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "goal_sha256": self.goal_sha256,
            "input_sha256": self.input_sha256,
            "handoff_qpos": list(self.handoff_qpos),
            "handoff_qvel": list(self.handoff_qvel),
            "path_progress": self.path_progress.tolist(),
            "qpos_order": list(CONTINUOUS_GOAL_REFERENCE_QPOS_ORDER),
            "qpos_path": self.qpos_path.tolist(),
            "qpos_abs_error_bound": self.qpos_abs_error_bound.tolist(),
            "coverage_level": self.coverage_level,
            "support_status": self.support_status,
            "ood_score": self.ood_score,
            "lineage": {
                "normalization_sha256": self.normalization_sha256,
                "checkpoint_sha256": self.checkpoint_sha256,
                "calibration_sha256": self.calibration_sha256,
                "goal_sha256": self.goal_sha256,
                "predictor_code_sha256": self.predictor_code_sha256,
                "path_sha256": self.path_sha256,
                "input_sha256": self.input_sha256,
            },
        }


@dataclass(frozen=True)
class ContinuousGoalReferenceResult:
    status: str
    blocker: str
    reference: CalibratedContinuousGoalReference | None

    @property
    def inference_allowed(self) -> bool:
        return (
            self.status == "passed" and not self.blocker and self.reference is not None
        )


def predict_continuous_goal_reference(
    *,
    predictor: ContinuousGoalReferencePredictor | None,
    live_handoff_state: Any,
    goal: Any,
    terrain_signature: Any,
    expected_lineage: Mapping[str, str] | None = None,
) -> ContinuousGoalReferenceResult:
    """Build input v2 once and validate every predictor output field."""

    if predictor is None:
        return _blocked(CONTINUOUS_GOAL_QPOS_PREDICTOR_V2_MISSING)
    if expected_lineage is None:
        return _blocked("expected_lineage_incomplete")
    if not isinstance(expected_lineage, Mapping):
        return _blocked("expected_lineage_invalid")
    if set(expected_lineage) != set(CONTINUOUS_GOAL_REFERENCE_REQUIRED_LINEAGE):
        return _blocked("expected_lineage_incomplete")
    try:
        for field in CONTINUOUS_GOAL_REFERENCE_REQUIRED_LINEAGE:
            _sha256(expected_lineage[field], label=field)
    except ValueError:
        return _blocked("expected_lineage_invalid")
    try:
        request = ContinuousGoalWorktoolSweepInputV2.create(
            handoff_qpos=_state_vector(live_handoff_state, key="qpos"),
            handoff_qvel=_state_vector(live_handoff_state, key="qvel"),
            continuous_goal=goal,
            terrain_signature=terrain_signature,
        )
    except (ContinuousGoalQposPathContractError, TypeError, ValueError):
        return _blocked("predictor_input_v2_invalid")
    try:
        prediction = predictor.predict(
            request,
            expected_lineage=expected_lineage,
        )
    except Exception:
        return _blocked("predictor_call_failed")

    try:
        blockers = _prediction_blockers(prediction)
    except Exception:
        return _blocked("predictor_output_contract_invalid")
    if blockers:
        return _blocked(f"predictor_blocked:{','.join(blockers)}")
    try:
        reference = _validated_reference(
            prediction=prediction,
            request=request,
            expected_lineage=expected_lineage,
        )
    except ValueError as exc:
        return _blocked(f"predictor_output_invalid:{exc}")
    return ContinuousGoalReferenceResult(
        status="passed",
        blocker="",
        reference=reference,
    )


def _prediction_blockers(prediction: Any) -> tuple[str, ...]:
    raw = getattr(prediction, "blockers", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("prediction blockers must be a sequence")
    blockers = tuple(str(value) for value in raw if str(value))
    if str(getattr(prediction, "status", "")) != "passed":
        if blockers:
            return blockers
        return ("invalid_status",)
    if getattr(prediction, "inference_allowed", False) is not True:
        return ("inference_not_allowed",)
    return blockers


def _validated_reference(
    *,
    prediction: Any,
    request: ContinuousGoalWorktoolSweepInputV2,
    expected_lineage: Mapping[str, str] | None,
) -> CalibratedContinuousGoalReference:
    progress = _finite_array(
        getattr(prediction, "path_progress", None),
        shape=(PATH_PROGRESS_POINT_COUNT,),
        label="path_progress",
    )
    if not np.array_equal(progress, PATH_PROGRESS):
        raise ValueError("path_progress_mismatch")
    path = _finite_array(
        getattr(prediction, "qpos_path", None),
        shape=(PATH_PROGRESS_POINT_COUNT, QPOS_DIM),
        label="qpos_path",
    )
    bounds = _finite_array(
        getattr(prediction, "qpos_abs_error_bound", None),
        shape=(PATH_PROGRESS_POINT_COUNT, QPOS_DIM),
        label="qpos_abs_error_bound",
    )
    if np.any(bounds < 0.0):
        raise ValueError("qpos_abs_error_bound_negative")
    handoff_qpos = tuple(float(value) for value in request.handoff_qpos)
    handoff_qvel = tuple(float(value) for value in request.handoff_qvel)
    if (
        float(np.max(np.abs(path[0] - np.asarray(handoff_qpos, dtype=np.float64))))
        > CONTINUOUS_GOAL_REFERENCE_START_TOLERANCE
    ):
        raise ValueError("path_start_handoff_mismatch")
    coverage = _finite_float(
        getattr(prediction, "coverage_level", None),
        label="coverage_level",
    )
    if coverage != CONTINUOUS_GOAL_REFERENCE_COVERAGE_LEVEL:
        raise ValueError("coverage_level_mismatch")
    if str(getattr(prediction, "support_status", "")) != "supported":
        raise ValueError("support_status_invalid")
    ood_score = _finite_float(
        getattr(prediction, "ood_score", None),
        label="ood_score",
    )
    if ood_score < 0.0:
        raise ValueError("ood_score_negative")

    normalization_sha = _sha256(
        getattr(prediction, "normalization_lineage_sha256", ""),
        label="normalization_lineage",
    )
    checkpoint_sha = _sha256(
        getattr(prediction, "checkpoint_lineage_sha256", ""),
        label="checkpoint_lineage",
    )
    calibration_sha = _sha256(
        getattr(prediction, "calibration_lineage_sha256", ""),
        label="calibration_lineage",
    )
    goal_sha = _sha256(
        getattr(prediction, "goal_lineage_sha256", ""),
        label="goal_lineage",
    )
    code_sha = _sha256(
        getattr(prediction, "predictor_code_lineage_sha256", ""),
        label="predictor_code_lineage",
    )
    path_sha = _sha256(
        getattr(prediction, "path_lineage_sha256", ""),
        label="path_lineage",
    )
    input_sha = _sha256(
        getattr(prediction, "input_lineage_sha256", ""),
        label="input_lineage",
    )
    if goal_sha != request.goal_sha256:
        raise ValueError("goal_lineage_mismatch")
    if input_sha != request.input_sha256:
        raise ValueError("input_lineage_mismatch")
    if path_sha != qpos_path_sha256(path):
        raise ValueError("path_lineage_mismatch")
    _validate_expected_lineage(
        expected_lineage,
        normalization_sha=normalization_sha,
        checkpoint_sha=checkpoint_sha,
        calibration_sha=calibration_sha,
        code_sha=code_sha,
    )
    for array in (progress, path, bounds):
        array.setflags(write=False)
    return CalibratedContinuousGoalReference(
        goal_sha256=goal_sha,
        input_sha256=input_sha,
        handoff_qpos=handoff_qpos,  # type: ignore[arg-type]
        handoff_qvel=handoff_qvel,  # type: ignore[arg-type]
        path_progress=progress,
        qpos_path=path,
        qpos_abs_error_bound=bounds,
        coverage_level=coverage,
        support_status="supported",
        ood_score=ood_score,
        normalization_sha256=normalization_sha,
        checkpoint_sha256=checkpoint_sha,
        calibration_sha256=calibration_sha,
        predictor_code_sha256=code_sha,
        path_sha256=path_sha,
    )


def _validate_expected_lineage(
    expected: Mapping[str, str],
    *,
    normalization_sha: str,
    checkpoint_sha: str,
    calibration_sha: str,
    code_sha: str,
) -> None:
    actual = {
        "normalization_sha256": normalization_sha,
        "checkpoint_sha256": checkpoint_sha,
        "calibration_sha256": calibration_sha,
        "predictor_code_sha256": code_sha,
    }
    for key in CONTINUOUS_GOAL_REFERENCE_REQUIRED_LINEAGE:
        if _sha256(expected[key], label=key) != actual[key]:
            raise ValueError("expected_lineage_mismatch")


def _state_vector(state: Any, *, key: str) -> tuple[float, ...]:
    value = state.get(key) if isinstance(state, Mapping) else getattr(state, key, None)
    array = _finite_array(value, shape=(QPOS_DIM,), label=f"handoff_{key}")
    return tuple(float(item) for item in array)


def _finite_array(
    value: Any,
    *,
    shape: tuple[int, ...],
    label: str,
) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label}_invalid") from exc
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{label}_invalid")
    return np.array(array, dtype=np.float64, copy=True)


def _finite_float(value: Any, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label}_invalid") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label}_invalid")
    return number


def _sha256(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{label}_invalid")
    return text


def _blocked(reason: str) -> ContinuousGoalReferenceResult:
    return ContinuousGoalReferenceResult(
        status="blocked",
        blocker=str(reason),
        reference=None,
    )


__all__ = [
    "CONTINUOUS_GOAL_QPOS_PREDICTOR_V2_MISSING",
    "CONTINUOUS_GOAL_REFERENCE_COVERAGE_LEVEL",
    "CONTINUOUS_GOAL_REFERENCE_QPOS_ORDER",
    "CONTINUOUS_GOAL_REFERENCE_REQUIRED_LINEAGE",
    "CONTINUOUS_GOAL_REFERENCE_SCHEMA",
    "CalibratedContinuousGoalReference",
    "ContinuousGoalReferencePredictor",
    "ContinuousGoalReferenceResult",
    "predict_continuous_goal_reference",
]
