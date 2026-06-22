"""Mutable primitive token runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)


@dataclass
class PrimitiveTokenRuntimeState:
    """Own mutable dig/return token and pending-token runtime state."""

    dig_cut_planned_cycle_id: int = -1
    dig_cut_tokens: np.ndarray = field(default_factory=lambda: _zeros(DIG_CUT_TOKEN_DIM))
    dig_depth_profile_tokens: np.ndarray = field(
        default_factory=lambda: _zeros(DIG_DEPTH_PROFILE_TOKEN_DIM)
    )
    dig_cut_token_source: str = "none"
    dig_cut_fallback_reason: str = ""
    dig_cut_token_in_prior_p10_p90: bool = False
    dig_depth_profile_token_source: str = "none"
    dig_depth_profile_fallback_reason: str = ""

    return_target_planned_cycle_id: int = -1
    return_target_tokens: np.ndarray = field(
        default_factory=lambda: _zeros(RETURN_TARGET_TOKEN_DIM)
    )
    return_relocate_tokens: np.ndarray = field(
        default_factory=lambda: _zeros(RETURN_TARGET_TOKEN_DIM)
    )
    return_start_envelope_tokens: np.ndarray = field(
        default_factory=lambda: _zeros(RETURN_START_ENVELOPE_TOKEN_DIM)
    )
    return_target_token_source: str = "none"
    return_target_fallback_reason: str = ""
    return_start_envelope_token_source: str = "none"
    return_start_envelope_use_prior_spatial_bounds: bool = True
    return_start_envelope_use_prior_qpos_bounds: bool = True

    pending_dig_cut_cycle_id: int = -1
    pending_dig_cut_corridor_id: int = -1
    pending_dig_cut_raw_fields: dict[str, float | int] | None = None
    pending_dig_cut_tokens: np.ndarray | None = None
    pending_dig_depth_profile_tokens: np.ndarray | None = None
    pending_dig_state_exemplar_ids: list[str] = field(default_factory=list)
    pending_dig_state_exemplar_distance: float = field(
        default_factory=lambda: float("nan")
    )

    @classmethod
    def fresh(cls) -> "PrimitiveTokenRuntimeState":
        """Return a fresh token runtime state matching reset defaults."""

        return cls()


def _zeros(size: int) -> np.ndarray:
    return np.zeros(int(size), dtype=np.float32)


__all__ = ["PrimitiveTokenRuntimeState"]
