from __future__ import annotations

import numpy as np
import pytest

from testbed.data.v2_1 import build_goal_tokens
from testbed.planner.primitive_tokens import GoalTokenProvider


def test_goal_token_provider_returns_none_without_goal_sequence() -> None:
    provider = GoalTokenProvider.from_inputs(goal_sequence=None)

    assert provider.tokens_for_cycle(0) is None
    assert provider.sector_id(0) == -1
    assert provider.next_sector_id(0) == -1


def test_goal_token_provider_builds_current_and_lookahead_tokens() -> None:
    provider = GoalTokenProvider.from_inputs(
        goal_sequence=["mid", "left", "right"],
        scenario_id="s0_truck",
        depth_norm=0.25,
        dump_target_norm=0.75,
    )

    token = provider.tokens_for_cycle(0)

    expected = build_goal_tokens(
        "s0_truck",
        curr_sector_id=1,
        curr_cut_depth_norm=0.25,
        next_sector_id=0,
        next_cut_depth_norm=0.25,
        dst_target_norm=0.75,
        has_lookahead=True,
    )
    assert token is not None
    np.testing.assert_allclose(token, expected)
    assert provider.sector_id(0) == 1
    assert provider.next_sector_id(0) == 0


def test_goal_token_provider_clamps_current_cycle_and_tracks_final_lookahead() -> None:
    provider = GoalTokenProvider.from_inputs(goal_sequence=[2, 0])

    assert provider.sector_id(99) == 0
    assert provider.next_sector_id(0) == 0
    assert provider.next_sector_id(1) == -1


def test_goal_token_provider_rejects_unknown_goal_sector() -> None:
    with pytest.raises(ValueError, match="Unknown primitive goal sector"):
        GoalTokenProvider.from_inputs(goal_sequence=["middle"])

    with pytest.raises(ValueError, match="Primitive goal sector id"):
        GoalTokenProvider.from_inputs(goal_sequence=[3])
