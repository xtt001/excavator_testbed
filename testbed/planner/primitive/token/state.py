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
from testbed.planner.primitive.facts.observation import PrimitiveTokenInjectionState
from testbed.planner.primitive.token.status import TokenStatus


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
            "pending_dig_cut_corridor_id": int(self.pending_dig_cut_corridor_id),
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
    dig_cut_tokens: np.ndarray = field(
        default_factory=lambda: _zeros(DIG_CUT_TOKEN_DIM)
    )
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
    pending_dig_execution_exemplar_id: str = ""
    pending_dig_execution_raw_fields_sha256: str = ""
    pending_dig_paired_return_primitive_episode_id: int = -1
    pending_dig_paired_return_exemplar_id: str = ""
    pending_dig_return_transition_artifact_sha256: str = ""
    pending_dig_exact_start_contract_required: bool = False
    pending_dig_exact_return_envelope_valid_mask: np.ndarray | None = None
    pending_dig_locked_execution_plan: Any = None

    @classmethod
    def fresh(cls) -> PrimitiveTokenRuntimeState:
        """Return a fresh token runtime state matching reset defaults."""

        return cls()

    def commit_return_plan(
        self,
        *,
        return_target_tokens: np.ndarray,
        return_start_envelope_tokens: np.ndarray,
        return_start_envelope_token_source: str,
        return_start_envelope_use_prior_spatial_bounds: bool,
        return_start_envelope_use_prior_qpos_bounds: bool,
        return_target_token_source: str,
        return_target_fallback_reason: str,
        return_target_planned_cycle_id: int,
        pending_dig_cut_cycle_id: int,
        pending_dig_cut_raw_fields: dict[str, float | int],
        pending_dig_cut_tokens: np.ndarray,
        pending_dig_cut_corridor_id: int,
        pending_dig_execution_exemplar_id: str,
        pending_dig_execution_raw_fields_sha256: str,
        pending_dig_paired_return_primitive_episode_id: int,
        pending_dig_paired_return_exemplar_id: str,
        pending_dig_return_transition_artifact_sha256: str,
        pending_dig_exact_start_contract_required: bool,
        pending_dig_exact_return_envelope_valid_mask: np.ndarray | None,
        pending_dig_depth_profile_tokens: np.ndarray | None,
        pending_dig_state_exemplar_ids: list[str],
        pending_dig_state_exemplar_distance: float,
        pending_dig_locked_execution_plan: Any = None,
    ) -> None:
        """Validate and atomically publish a complete return/next-dig plan."""

        target = np.asarray(return_target_tokens, dtype=np.float32).reshape(-1)
        envelope = np.asarray(
            return_start_envelope_tokens,
            dtype=np.float32,
        ).reshape(-1)
        dig_tokens = np.asarray(
            pending_dig_cut_tokens,
            dtype=np.float32,
        ).reshape(-1)
        if (
            target.shape != (RETURN_TARGET_TOKEN_DIM,)
            or envelope.shape != (RETURN_START_ENVELOPE_TOKEN_DIM,)
            or dig_tokens.shape != (DIG_CUT_TOKEN_DIM,)
            or not np.all(np.isfinite(target))
            or not np.all(np.isfinite(envelope))
            or not np.all(np.isfinite(dig_tokens))
        ):
            raise ValueError("return plan token contract invalid")
        exact_mask = (
            None
            if pending_dig_exact_return_envelope_valid_mask is None
            else np.asarray(
                pending_dig_exact_return_envelope_valid_mask,
                dtype=np.uint8,
            ).reshape(-1)
        )
        if bool(pending_dig_exact_start_contract_required) and (
            exact_mask is None
            or exact_mask.shape != (RETURN_START_ENVELOPE_TOKEN_DIM,)
            or not bool(np.all(exact_mask > 0))
            or not str(pending_dig_execution_exemplar_id)
            or len(str(pending_dig_execution_raw_fields_sha256)) != 64
            or int(pending_dig_paired_return_primitive_episode_id) < 0
            or not str(pending_dig_paired_return_exemplar_id)
            or len(str(pending_dig_return_transition_artifact_sha256)) != 64
        ):
            raise ValueError(
                "exact return plan identity or valid-mask contract invalid"
            )
        locked_plan = pending_dig_locked_execution_plan
        if locked_plan is not None:
            locked_raw_fields = dict(
                getattr(locked_plan, "raw_fields", {}) or {}
            )
            locked_dig_token = np.asarray(
                getattr(locked_plan, "dig_token", []),
                dtype=np.float32,
            ).reshape(-1)
            locked_envelope = getattr(locked_plan, "return_envelope", None)
            locked_envelope_token = np.asarray(
                getattr(locked_envelope, "token", []),
                dtype=np.float32,
            ).reshape(-1)
            locked_goal_id = str(getattr(locked_plan, "goal_id", ""))
            envelope_goal_id = str(
                getattr(locked_envelope, "goal_id", "")
            )
            if (
                bool(pending_dig_exact_start_contract_required)
                or len(locked_goal_id) != 64
                or envelope_goal_id != locked_goal_id
                or locked_raw_fields != dict(pending_dig_cut_raw_fields)
                or locked_dig_token.shape != (DIG_CUT_TOKEN_DIM,)
                or not np.array_equal(locked_dig_token, dig_tokens)
                or locked_envelope_token.shape
                != (RETURN_START_ENVELOPE_TOKEN_DIM,)
                or not np.array_equal(locked_envelope_token, envelope)
                or bool(return_start_envelope_use_prior_spatial_bounds)
                or bool(return_start_envelope_use_prior_qpos_bounds)
            ):
                raise ValueError(
                    "continuous locked plan identity or content drift"
                )
        depth_profile = (
            None
            if pending_dig_depth_profile_tokens is None
            else np.asarray(
                pending_dig_depth_profile_tokens,
                dtype=np.float32,
            ).reshape(-1)
        )
        if depth_profile is not None and (
            depth_profile.shape != (DIG_DEPTH_PROFILE_TOKEN_DIM,)
            or not np.all(np.isfinite(depth_profile))
        ):
            raise ValueError("pending dig depth-profile contract invalid")
        updates = {
            "return_target_tokens": target.copy(),
            "return_start_envelope_tokens": envelope.copy(),
            "return_start_envelope_token_source": str(
                return_start_envelope_token_source
            ),
            "return_start_envelope_use_prior_spatial_bounds": bool(
                return_start_envelope_use_prior_spatial_bounds
            ),
            "return_start_envelope_use_prior_qpos_bounds": bool(
                return_start_envelope_use_prior_qpos_bounds
            ),
            "return_target_token_source": str(return_target_token_source),
            "return_target_fallback_reason": str(return_target_fallback_reason),
            "return_target_planned_cycle_id": int(return_target_planned_cycle_id),
            "pending_dig_cut_cycle_id": int(pending_dig_cut_cycle_id),
            "pending_dig_cut_raw_fields": dict(pending_dig_cut_raw_fields),
            "pending_dig_cut_tokens": dig_tokens.copy(),
            "pending_dig_cut_corridor_id": int(pending_dig_cut_corridor_id),
            "pending_dig_execution_exemplar_id": str(pending_dig_execution_exemplar_id),
            "pending_dig_execution_raw_fields_sha256": str(
                pending_dig_execution_raw_fields_sha256
            ),
            "pending_dig_paired_return_primitive_episode_id": int(
                pending_dig_paired_return_primitive_episode_id
            ),
            "pending_dig_paired_return_exemplar_id": str(
                pending_dig_paired_return_exemplar_id
            ),
            "pending_dig_return_transition_artifact_sha256": str(
                pending_dig_return_transition_artifact_sha256
            ),
            "pending_dig_exact_start_contract_required": bool(
                pending_dig_exact_start_contract_required
            ),
            "pending_dig_exact_return_envelope_valid_mask": (
                None if exact_mask is None else exact_mask.copy()
            ),
            "pending_dig_locked_execution_plan": locked_plan,
            "pending_dig_depth_profile_tokens": (
                None if depth_profile is None else depth_profile.copy()
            ),
            "pending_dig_state_exemplar_ids": list(pending_dig_state_exemplar_ids),
            "pending_dig_state_exemplar_distance": float(
                pending_dig_state_exemplar_distance
            ),
        }
        self.__dict__.update(updates)

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
            dig_cut_token_injected=bool(token_injection_state.dig_cut_token_injected),
            dig_cut_token_dim=int(DIG_CUT_TOKEN_DIM),
            dig_cut_token_source=str(self.dig_cut_token_source),
            dig_cut_tokens=self.dig_cut_tokens,
            dig_cut_fallback_reason=str(self.dig_cut_fallback_reason),
            dig_cut_token_in_prior_p10_p90=bool(self.dig_cut_token_in_prior_p10_p90),
            dig_depth_profile_token_injected=bool(
                token_injection_state.dig_depth_profile_token_injected
            ),
            dig_depth_profile_token_dim=int(DIG_DEPTH_PROFILE_TOKEN_DIM),
            dig_depth_profile_source=str(dig_depth_profile_source),
            dig_depth_profile_required=bool(dig_depth_profile_required),
            dig_depth_profile_token_source=str(self.dig_depth_profile_token_source),
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
            dig_cut_token_injected=bool(token_injection_state.dig_cut_token_injected),
            dig_cut_planner_mode=str(dig_cut_planner_mode),
            dig_cut_prior_id=str(dig_cut_prior_id),
            dig_cut_prior_path=str(dig_cut_prior_path),
            dig_cut_token_source=str(self.dig_cut_token_source),
            dig_cut_token_in_prior_p10_p90=bool(self.dig_cut_token_in_prior_p10_p90),
            dig_cut_fallback_reason=str(self.dig_cut_fallback_reason),
        )


def _zeros(size: int) -> np.ndarray:
    return np.zeros(int(size), dtype=np.float32)


__all__ = ["PrimitiveTokenReportStatus", "PrimitiveTokenRuntimeState"]
