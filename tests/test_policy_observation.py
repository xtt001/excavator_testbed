from __future__ import annotations

import numpy as np

from testbed.contracts.low_dim import CELL_ENTRY_TOKEN_KEY, GOAL_TOKEN_KEY
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_KEY,
)
from testbed.planner.policy_observation import (
    PolicyObservationAssembler,
    PolicyObservationTokens,
)


def test_no_tokens_returns_original_observation_without_injection_flags() -> None:
    obs = {"qpos": np.zeros(4, dtype=np.float32)}

    assembly = PolicyObservationAssembler().assemble(obs, PolicyObservationTokens())

    assert assembly.obs is obs
    assert not assembly.cell_entry_token_injected
    assert not assembly.dig_cut_token_injected
    assert not assembly.dig_depth_profile_token_injected
    assert not assembly.return_target_token_injected
    assert not assembly.return_relocate_token_injected
    assert not assembly.return_start_envelope_token_injected


def test_goal_only_token_copies_observation_without_debug_injection_flags() -> None:
    obs = {"qpos": np.zeros(4, dtype=np.float32)}
    goal_tokens = np.arange(10, dtype=np.float32)

    assembly = PolicyObservationAssembler().assemble(
        obs,
        PolicyObservationTokens(goal_tokens=goal_tokens),
    )

    assert assembly.obs is not obs
    assert GOAL_TOKEN_KEY not in obs
    assert assembly.obs[GOAL_TOKEN_KEY] is goal_tokens
    assert not assembly.cell_entry_token_injected
    assert not assembly.dig_cut_token_injected
    assert not assembly.dig_depth_profile_token_injected
    assert not assembly.return_target_token_injected
    assert not assembly.return_relocate_token_injected
    assert not assembly.return_start_envelope_token_injected


def test_all_policy_tokens_are_merged_with_matching_injection_flags() -> None:
    obs = {"qpos": np.zeros(4, dtype=np.float32)}
    tokens = PolicyObservationTokens(
        goal_tokens=np.full(10, 1.0, dtype=np.float32),
        cell_entry_tokens=np.full(10, 2.0, dtype=np.float32),
        dig_cut_tokens=np.full(10, 3.0, dtype=np.float32),
        dig_depth_profile_tokens=np.full(12, 4.0, dtype=np.float32),
        return_target_tokens=np.full(10, 5.0, dtype=np.float32),
        return_relocate_tokens=np.full(10, 6.0, dtype=np.float32),
        return_start_envelope_tokens=np.full(18, 7.0, dtype=np.float32),
    )

    assembly = PolicyObservationAssembler().assemble(obs, tokens)

    assert assembly.obs is not obs
    assert set(obs) == {"qpos"}
    assert assembly.obs[GOAL_TOKEN_KEY] is tokens.goal_tokens
    assert assembly.obs[CELL_ENTRY_TOKEN_KEY] is tokens.cell_entry_tokens
    assert assembly.obs[DIG_CUT_TOKEN_KEY] is tokens.dig_cut_tokens
    assert assembly.obs[DIG_DEPTH_PROFILE_TOKEN_KEY] is tokens.dig_depth_profile_tokens
    assert assembly.obs[RETURN_TARGET_TOKEN_KEY] is tokens.return_target_tokens
    assert assembly.obs[RETURN_RELOCATE_TOKEN_KEY] is tokens.return_relocate_tokens
    assert (
        assembly.obs[RETURN_START_ENVELOPE_TOKEN_KEY]
        is tokens.return_start_envelope_tokens
    )
    assert assembly.cell_entry_token_injected
    assert assembly.dig_cut_token_injected
    assert assembly.dig_depth_profile_token_injected
    assert assembly.return_target_token_injected
    assert assembly.return_relocate_token_injected
    assert assembly.return_start_envelope_token_injected
