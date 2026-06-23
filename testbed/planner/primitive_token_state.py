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
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.planner.primitive_observation import PrimitiveTokenInjectionState
from testbed.planner.primitive_token_status import TokenStatus


@dataclass(frozen=True)
class PrimitiveTokenReportStatus:
    """Projected token/pending/dig-cut report metadata."""

    pending_dig_cut_cycle_id: int
    pending_dig_cut_corridor_id: int
    dig_cut_token_injected: bool
    dig_cut_planner_mode: str
    dig_cut_prior_id: str
    dig_cut_prior_path: str
    dig_cut_token_source: str
    dig_cut_token_in_prior_p10_p90: bool
    dig_cut_fallback_reason: str

    def pending_debug_fields(self) -> dict[str, int]:
        return {
            "pending_dig_cut_cycle_id": int(self.pending_dig_cut_cycle_id),
            "pending_dig_cut_corridor_id": int(
                self.pending_dig_cut_corridor_id
            ),
        }

    def dig_cut_debug_fields(self) -> dict[str, str]:
        return {
            "dig_cut_planner_mode": str(self.dig_cut_planner_mode),
            "dig_cut_prior_id": str(self.dig_cut_prior_id),
        }


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

    def to_token_status(
        self,
        *,
        cell_entry_enabled: bool,
        token_injection_state: PrimitiveTokenInjectionState,
        dig_depth_profile_source: str,
        dig_depth_profile_required: bool,
    ) -> TokenStatus:
        """Project live token runtime state into the public token status facts."""

        cell_entry_runtime_enabled = bool(cell_entry_enabled)
        return TokenStatus.from_inputs(
            cell_entry_enabled=cell_entry_runtime_enabled,
            cell_entry_token_injected=bool(
                token_injection_state.cell_entry_token_injected
            )
            if cell_entry_runtime_enabled
            else False,
            cell_entry_token_dim=int(CELL_ENTRY_TOKEN_DIM)
            if cell_entry_runtime_enabled
            else 0,
            dig_cut_token_injected=bool(
                token_injection_state.dig_cut_token_injected
            ),
            dig_cut_token_dim=int(DIG_CUT_TOKEN_DIM),
            dig_cut_token_source=str(self.dig_cut_token_source),
            dig_cut_tokens=self.dig_cut_tokens,
            dig_cut_fallback_reason=str(self.dig_cut_fallback_reason),
            dig_cut_token_in_prior_p10_p90=bool(
                self.dig_cut_token_in_prior_p10_p90
            ),
            dig_depth_profile_token_injected=bool(
                token_injection_state.dig_depth_profile_token_injected
            ),
            dig_depth_profile_token_dim=int(DIG_DEPTH_PROFILE_TOKEN_DIM),
            dig_depth_profile_source=str(dig_depth_profile_source),
            dig_depth_profile_required=bool(dig_depth_profile_required),
            dig_depth_profile_token_source=str(
                self.dig_depth_profile_token_source
            ),
            dig_depth_profile_tokens=self.dig_depth_profile_tokens,
            dig_depth_profile_fallback_reason=str(
                self.dig_depth_profile_fallback_reason
            ),
            return_target_token_injected=bool(
                token_injection_state.return_target_token_injected
            ),
            return_target_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_target_token_source=str(self.return_target_token_source),
            return_target_tokens=self.return_target_tokens,
            return_target_fallback_reason=str(self.return_target_fallback_reason),
            return_relocate_token_injected=bool(
                token_injection_state.return_relocate_token_injected
            ),
            return_relocate_token_dim=int(RETURN_TARGET_TOKEN_DIM),
            return_relocate_token_source=str(self.return_target_token_source),
            return_relocate_tokens=self.return_relocate_tokens,
            return_start_envelope_token_injected=bool(
                token_injection_state.return_start_envelope_token_injected
            ),
            return_start_envelope_token_dim=int(RETURN_START_ENVELOPE_TOKEN_DIM),
            return_start_envelope_token_source=str(
                self.return_start_envelope_token_source
            ),
            return_start_envelope_tokens=self.return_start_envelope_tokens,
        )

    def to_report_status(
        self,
        *,
        token_injection_state: PrimitiveTokenInjectionState,
        dig_cut_planner_mode: str,
        dig_cut_prior_id: str,
        dig_cut_prior_path: str,
    ) -> PrimitiveTokenReportStatus:
        """Project live token report metadata from runtime state and config facts."""

        return PrimitiveTokenReportStatus(
            pending_dig_cut_cycle_id=int(self.pending_dig_cut_cycle_id),
            pending_dig_cut_corridor_id=int(self.pending_dig_cut_corridor_id),
            dig_cut_token_injected=bool(
                token_injection_state.dig_cut_token_injected
            ),
            dig_cut_planner_mode=str(dig_cut_planner_mode),
            dig_cut_prior_id=str(dig_cut_prior_id),
            dig_cut_prior_path=str(dig_cut_prior_path),
            dig_cut_token_source=str(self.dig_cut_token_source),
            dig_cut_token_in_prior_p10_p90=bool(
                self.dig_cut_token_in_prior_p10_p90
            ),
            dig_cut_fallback_reason=str(self.dig_cut_fallback_reason),
        )


def _zeros(size: int) -> np.ndarray:
    return np.zeros(int(size), dtype=np.float32)


__all__ = ["PrimitiveTokenReportStatus", "PrimitiveTokenRuntimeState"]
