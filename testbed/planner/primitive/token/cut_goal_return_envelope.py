"""Prior-independent 18D return envelope derived from one continuous goal."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_POSITION_SCALE_M,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.planner.primitive.coverage.continuous_goal import ContinuousCutGoal

CUT_GOAL_RETURN_ENVELOPE_SCHEMA = "cut_goal_return_envelope_v1"


class CutGoalReturnEnvelopeContractError(ValueError):
    """Raised when a continuous return envelope is not fully derivable."""


@dataclass(frozen=True)
class CanonicalHandoffReference:
    """Motion-predictor-owned handoff facts required by the 18D token."""

    goal_id: str
    qpos: tuple[float, ...]
    qpos_half_width: tuple[float, ...]
    qvel_abs_max: float
    spatial_half_width_norm: float
    expected_contact: bool
    predictor_profile: str
    predictor_version: str
    predictor_code_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "qpos",
            tuple(float(value) for value in self.qpos),
        )
        object.__setattr__(
            self,
            "qpos_half_width",
            tuple(float(value) for value in self.qpos_half_width),
        )


@dataclass(frozen=True)
class CutGoalReturnEnvelope:
    """Immutable same-goal return handoff envelope and derivation lineage."""

    goal_id: str
    token: np.ndarray
    terrain_local_depth_m: float
    terrain_plane_depth_m: float
    handoff_reference: CanonicalHandoffReference
    schema: str = CUT_GOAL_RETURN_ENVELOPE_SCHEMA
    derivation: str = "continuous_cut_goal"

    @property
    def source_uses_prior(self) -> bool:
        return False

    @property
    def source_uses_live_current_fallback(self) -> bool:
        return False

    @property
    def source_uses_relocate_conditioning(self) -> bool:
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "goal_id": self.goal_id,
            "derivation": self.derivation,
            "token": self.token.tolist(),
            "prior_independent_local_depth_m": (
                self.terrain_local_depth_m
            ),
            "prior_independent_plane_depth_m": (
                self.terrain_plane_depth_m
            ),
            "handoff_reference": {
                "goal_id": self.handoff_reference.goal_id,
                "qpos": list(self.handoff_reference.qpos),
                "qpos_half_width": list(
                    self.handoff_reference.qpos_half_width
                ),
                "qvel_abs_max": self.handoff_reference.qvel_abs_max,
                "spatial_half_width_norm": (
                    self.handoff_reference.spatial_half_width_norm
                ),
                "expected_contact": bool(
                    self.handoff_reference.expected_contact
                ),
                "predictor_profile": (
                    self.handoff_reference.predictor_profile
                ),
                "predictor_version": (
                    self.handoff_reference.predictor_version
                ),
                "predictor_code_sha256": (
                    self.handoff_reference.predictor_code_sha256
                ),
            },
        }


@dataclass(frozen=True)
class CutGoalReturnEnvelopeService:
    """Derive a complete 18D envelope without legacy fallback sources."""

    def derive(
        self,
        *,
        goal: ContinuousCutGoal,
        terrain_local_depth_m: float,
        terrain_plane_depth_m: float,
        handoff_reference: CanonicalHandoffReference,
    ) -> CutGoalReturnEnvelope:
        if not isinstance(goal, ContinuousCutGoal):
            raise CutGoalReturnEnvelopeContractError(
                "goal must be a locked ContinuousCutGoal"
            )
        if handoff_reference.goal_id != goal.goal_id:
            raise CutGoalReturnEnvelopeContractError(
                "return envelope goal identity drift"
            )
        local_depth = _finite_nonnegative(
            terrain_local_depth_m,
            label="terrain_local_depth_m",
        )
        plane_depth = _finite_nonnegative(
            terrain_plane_depth_m,
            label="terrain_plane_depth_m",
        )
        qpos = _finite_vector(
            handoff_reference.qpos,
            size=4,
            label="canonical handoff qpos",
        )
        half_width = _finite_vector(
            handoff_reference.qpos_half_width,
            size=4,
            label="canonical handoff qpos_half_width",
            nonnegative=True,
        )
        qvel_abs_max = _finite_nonnegative(
            handoff_reference.qvel_abs_max,
            label="canonical handoff qvel_abs_max",
        )
        spatial_half_width = _finite_nonnegative(
            handoff_reference.spatial_half_width_norm,
            label="canonical handoff spatial_half_width_norm",
        )
        profile = str(handoff_reference.predictor_profile).strip()
        version = str(handoff_reference.predictor_version).strip()
        if not profile or not version:
            raise CutGoalReturnEnvelopeContractError(
                "canonical handoff predictor profile/version is missing"
            )
        _sha256_text(
            handoff_reference.predictor_code_sha256,
            label="canonical handoff predictor_code_sha256",
        )

        token = np.zeros(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float32,
        )
        token[0] = _clip_position(goal.entry_xz_m[0])
        token[1] = _clip_position(goal.entry_xz_m[1])
        token[2] = local_depth
        token[3] = spatial_half_width
        token[4] = min(local_depth, plane_depth)
        token[5] = max(local_depth, plane_depth)
        token[6] = float(bool(handoff_reference.expected_contact))
        token[7:11] = qpos
        token[11:15] = half_width
        token[15] = qvel_abs_max
        token[16] = 1.0
        token[17] = 1.0
        if token.shape != (18,) or not np.all(np.isfinite(token)):
            raise CutGoalReturnEnvelopeContractError(
                "return envelope must be a complete finite 18D token"
            )
        token.setflags(write=False)
        return CutGoalReturnEnvelope(
            goal_id=goal.goal_id,
            token=token,
            terrain_local_depth_m=local_depth,
            terrain_plane_depth_m=plane_depth,
            handoff_reference=handoff_reference,
        )


def _clip_position(value: float) -> float:
    return float(
        np.clip(
            float(value) / float(DIG_CUT_POSITION_SCALE_M),
            -1.0,
            1.0,
        )
    )


def _finite_vector(
    value: Any,
    *,
    size: int,
    label: str,
    nonnegative: bool = False,
) -> tuple[float, ...]:
    try:
        array = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise CutGoalReturnEnvelopeContractError(
            f"{label} must contain {size} finite values"
        ) from exc
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise CutGoalReturnEnvelopeContractError(
            f"{label} must contain {size} finite values"
        )
    if nonnegative and np.any(array < 0.0):
        raise CutGoalReturnEnvelopeContractError(
            f"{label} must be non-negative"
        )
    return tuple(float(item) for item in array)


def _finite_nonnegative(value: Any, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CutGoalReturnEnvelopeContractError(
            f"{label} must be finite and non-negative"
        ) from exc
    if not math.isfinite(number) or number < 0.0:
        raise CutGoalReturnEnvelopeContractError(
            f"{label} must be finite and non-negative"
        )
    return number


def _sha256_text(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise CutGoalReturnEnvelopeContractError(
            f"{label} must be a lowercase SHA256"
        )
    return text


__all__ = [
    "CUT_GOAL_RETURN_ENVELOPE_SCHEMA",
    "CanonicalHandoffReference",
    "CutGoalReturnEnvelope",
    "CutGoalReturnEnvelopeContractError",
    "CutGoalReturnEnvelopeService",
]
