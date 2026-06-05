"""Policy observation assembly for primitive ACT dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.contracts.low_dim import CELL_ENTRY_TOKEN_KEY, GOAL_TOKEN_KEY
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_KEY,
)


@dataclass(frozen=True)
class PolicyObservationTokens:
    goal_tokens: Any | None = None
    cell_entry_tokens: Any | None = None
    dig_cut_tokens: Any | None = None
    dig_depth_profile_tokens: Any | None = None
    return_target_tokens: Any | None = None
    return_relocate_tokens: Any | None = None
    return_start_envelope_tokens: Any | None = None

    def all_missing(self) -> bool:
        return bool(
            self.goal_tokens is None
            and self.cell_entry_tokens is None
            and self.dig_cut_tokens is None
            and self.dig_depth_profile_tokens is None
            and self.return_target_tokens is None
            and self.return_relocate_tokens is None
            and self.return_start_envelope_tokens is None
        )


@dataclass(frozen=True)
class PolicyObservationAssembly:
    obs: dict[str, Any]
    cell_entry_token_injected: bool = False
    dig_cut_token_injected: bool = False
    dig_depth_profile_token_injected: bool = False
    return_target_token_injected: bool = False
    return_relocate_token_injected: bool = False
    return_start_envelope_token_injected: bool = False


class PolicyObservationAssembler:
    """Merges already-built planner tokens into the ACT policy observation."""

    def assemble(
        self,
        obs: dict[str, Any],
        tokens: PolicyObservationTokens,
    ) -> PolicyObservationAssembly:
        if tokens.all_missing():
            return PolicyObservationAssembly(obs=obs)

        policy_obs = dict(obs)
        if tokens.goal_tokens is not None:
            policy_obs[GOAL_TOKEN_KEY] = tokens.goal_tokens
        if tokens.cell_entry_tokens is not None:
            policy_obs[CELL_ENTRY_TOKEN_KEY] = tokens.cell_entry_tokens
        if tokens.dig_cut_tokens is not None:
            policy_obs[DIG_CUT_TOKEN_KEY] = tokens.dig_cut_tokens
        if tokens.dig_depth_profile_tokens is not None:
            policy_obs[DIG_DEPTH_PROFILE_TOKEN_KEY] = tokens.dig_depth_profile_tokens
        if tokens.return_target_tokens is not None:
            policy_obs[RETURN_TARGET_TOKEN_KEY] = tokens.return_target_tokens
        if tokens.return_relocate_tokens is not None:
            policy_obs[RETURN_RELOCATE_TOKEN_KEY] = tokens.return_relocate_tokens
        if tokens.return_start_envelope_tokens is not None:
            policy_obs[RETURN_START_ENVELOPE_TOKEN_KEY] = (
                tokens.return_start_envelope_tokens
            )

        return PolicyObservationAssembly(
            obs=policy_obs,
            cell_entry_token_injected=tokens.cell_entry_tokens is not None,
            dig_cut_token_injected=tokens.dig_cut_tokens is not None,
            dig_depth_profile_token_injected=(
                tokens.dig_depth_profile_tokens is not None
            ),
            return_target_token_injected=tokens.return_target_tokens is not None,
            return_relocate_token_injected=tokens.return_relocate_tokens is not None,
            return_start_envelope_token_injected=(
                tokens.return_start_envelope_tokens is not None
            ),
        )
