"""Read-only primitive token status facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class TokenVectorStatus:
    """Observable state for one planner token vector."""

    injected: bool
    dim: int
    source: str
    tokens: np.ndarray
    fallback_reason: str = ""
    in_prior_p10_p90: bool = False

    @classmethod
    def from_inputs(
        cls,
        *,
        injected: bool = False,
        dim: int = 0,
        source: str = "",
        tokens: Any = None,
        fallback_reason: str = "",
        in_prior_p10_p90: bool = False,
    ) -> TokenVectorStatus:
        return cls(
            injected=bool(injected),
            dim=int(dim),
            source=str(source),
            tokens=_readonly_token_array(tokens, dim=int(dim)),
            fallback_reason=str(fallback_reason),
            in_prior_p10_p90=bool(in_prior_p10_p90),
        )


@dataclass(frozen=True)
class TokenStatus:
    """Observable token state used by reports and future planner backends."""

    cell_entry_enabled: bool
    cell_entry: TokenVectorStatus
    dig_cut: TokenVectorStatus
    dig_depth_profile_source: str
    dig_depth_profile_required: bool
    dig_depth_profile: TokenVectorStatus
    return_target: TokenVectorStatus
    return_relocate: TokenVectorStatus
    return_start_envelope: TokenVectorStatus

    @classmethod
    def from_inputs(
        cls,
        *,
        cell_entry_enabled: bool = False,
        cell_entry_token_injected: bool = False,
        cell_entry_token_dim: int = 0,
        dig_cut_token_injected: bool = False,
        dig_cut_token_dim: int = 0,
        dig_cut_token_source: str = "none",
        dig_cut_tokens: Any = None,
        dig_cut_fallback_reason: str = "",
        dig_cut_token_in_prior_p10_p90: bool = False,
        dig_depth_profile_token_injected: bool = False,
        dig_depth_profile_token_dim: int = 0,
        dig_depth_profile_source: str = "",
        dig_depth_profile_required: bool = False,
        dig_depth_profile_token_source: str = "none",
        dig_depth_profile_tokens: Any = None,
        dig_depth_profile_fallback_reason: str = "",
        return_target_token_injected: bool = False,
        return_target_token_dim: int = 0,
        return_target_token_source: str = "none",
        return_target_tokens: Any = None,
        return_target_fallback_reason: str = "",
        return_relocate_token_injected: bool = False,
        return_relocate_token_dim: int = 0,
        return_relocate_token_source: str | None = None,
        return_relocate_tokens: Any = None,
        return_start_envelope_token_injected: bool = False,
        return_start_envelope_token_dim: int = 0,
        return_start_envelope_token_source: str = "none",
        return_start_envelope_tokens: Any = None,
    ) -> TokenStatus:
        relocate_source = (
            return_target_token_source
            if return_relocate_token_source is None
            else return_relocate_token_source
        )
        return cls(
            cell_entry_enabled=bool(cell_entry_enabled),
            cell_entry=TokenVectorStatus.from_inputs(
                injected=cell_entry_token_injected,
                dim=cell_entry_token_dim,
            ),
            dig_cut=TokenVectorStatus.from_inputs(
                injected=dig_cut_token_injected,
                dim=dig_cut_token_dim,
                source=dig_cut_token_source,
                tokens=dig_cut_tokens,
                fallback_reason=dig_cut_fallback_reason,
                in_prior_p10_p90=dig_cut_token_in_prior_p10_p90,
            ),
            dig_depth_profile_source=str(dig_depth_profile_source),
            dig_depth_profile_required=bool(dig_depth_profile_required),
            dig_depth_profile=TokenVectorStatus.from_inputs(
                injected=dig_depth_profile_token_injected,
                dim=dig_depth_profile_token_dim,
                source=dig_depth_profile_token_source,
                tokens=dig_depth_profile_tokens,
                fallback_reason=dig_depth_profile_fallback_reason,
            ),
            return_target=TokenVectorStatus.from_inputs(
                injected=return_target_token_injected,
                dim=return_target_token_dim,
                source=return_target_token_source,
                tokens=return_target_tokens,
                fallback_reason=return_target_fallback_reason,
            ),
            return_relocate=TokenVectorStatus.from_inputs(
                injected=return_relocate_token_injected,
                dim=return_relocate_token_dim,
                source=relocate_source,
                tokens=return_relocate_tokens,
            ),
            return_start_envelope=TokenVectorStatus.from_inputs(
                injected=return_start_envelope_token_injected,
                dim=return_start_envelope_token_dim,
                source=return_start_envelope_token_source,
                tokens=return_start_envelope_tokens,
            ),
        )

    def to_debug_fields(self) -> dict[str, object]:
        """Return legacy debug-state keys without renaming the public surface."""

        return {
            "cell_entry_enabled": bool(self.cell_entry_enabled),
            "cell_entry_token_injected": bool(self.cell_entry.injected),
            "cell_entry_token_dim": int(self.cell_entry.dim),
            "dig_cut_token_injected": bool(self.dig_cut.injected),
            "dig_cut_token_dim": int(self.dig_cut.dim),
            "dig_depth_profile_token_injected": bool(
                self.dig_depth_profile.injected
            ),
            "dig_depth_profile_token_dim": int(self.dig_depth_profile.dim),
            "dig_depth_profile_source": str(self.dig_depth_profile_source),
            "dig_depth_profile_required": bool(self.dig_depth_profile_required),
            "dig_depth_profile_token_source": str(self.dig_depth_profile.source),
            "dig_depth_profile_fallback_reason": str(
                self.dig_depth_profile.fallback_reason
            ),
            "return_target_token_injected": bool(self.return_target.injected),
            "return_target_token_dim": int(self.return_target.dim),
            "return_target_token_source": str(self.return_target.source),
            "return_target_tokens": _debug_token_list(self.return_target.tokens),
            "return_target_fallback_reason": str(
                self.return_target.fallback_reason
            ),
            "return_relocate_token_injected": bool(self.return_relocate.injected),
            "return_relocate_token_dim": int(self.return_relocate.dim),
            "return_relocate_token_source": str(self.return_relocate.source),
            "return_relocate_tokens": _debug_token_list(self.return_relocate.tokens),
            "return_start_envelope_token_injected": bool(
                self.return_start_envelope.injected
            ),
            "return_start_envelope_token_dim": int(self.return_start_envelope.dim),
            "return_start_envelope_token_source": str(
                self.return_start_envelope.source
            ),
            "return_start_envelope_tokens": _debug_token_list(
                self.return_start_envelope.tokens
            ),
            "dig_cut_token_source": str(self.dig_cut.source),
            "dig_cut_tokens": _debug_token_list(self.dig_cut.tokens),
            "dig_depth_profile_tokens": _debug_token_list(
                self.dig_depth_profile.tokens
            ),
            "token_in_prior_p10_p90": bool(self.dig_cut.in_prior_p10_p90),
            "dig_cut_token_in_prior_p10_p90": bool(self.dig_cut.in_prior_p10_p90),
            "fallback_reason": str(self.dig_cut.fallback_reason),
            "dig_cut_fallback_reason": str(self.dig_cut.fallback_reason),
        }


def _readonly_token_array(value: Any, *, dim: int) -> np.ndarray:
    if value is None:
        array = np.zeros(max(0, int(dim)), dtype=np.float32)
    else:
        array = np.asarray(value, dtype=np.float32).reshape(-1).copy()
    array.setflags(write=False)
    return array


def _debug_token_list(value: np.ndarray) -> list[float]:
    return np.asarray(value, dtype=float).reshape(-1).tolist()


__all__ = ["TokenStatus", "TokenVectorStatus"]
