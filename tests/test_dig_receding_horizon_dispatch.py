from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from testbed.eval.dig_receding_horizon_dispatch import (
    LatestChunkRecedingHorizonDispatcher,
    LegacyTemporalAggregationDispatcher,
    assess_action_support,
    make_independent_arm_dispatchers,
    summarise_contributing_chunk_ages,
)
from testbed.policies.act.inference import ACTActionChunk


@dataclass(frozen=True)
class _TemporalContract:
    enabled: bool = True
    num_queries: int = 4
    window: int = 4
    weight_order: str = "legacy_oldest_first"
    decay: float = 0.01


class _FakePolicy:
    def __init__(self) -> None:
        self.reset_count = 0
        self.chunk_calls = 0
        self.predict_calls = 0
        self.cache: list[np.ndarray] = []
        self.temporal_aggregation_contract = _TemporalContract()

    def reset(self) -> None:
        self.reset_count += 1
        self.cache.clear()

    def predict_action_chunk(self, observation: dict) -> ACTActionChunk:
        self.chunk_calls += 1
        frame = float(observation["frame"])
        goal = float(np.asarray(observation["dig_cut_tokens"])[0])
        chunk = np.asarray(
            [[frame + query, goal, query, -query] for query in range(4)],
            dtype=np.float32,
        )
        return ACTActionChunk(actions=chunk)

    def predict(self, observation: dict) -> np.ndarray:
        self.predict_calls += 1
        action = np.asarray(
            [
                float(observation["frame"]),
                float(np.asarray(observation["dig_cut_tokens"])[0]),
                99.0,
                -99.0,
            ],
            dtype=np.float32,
        )
        self.cache.append(action.copy())
        return action


def _goal(value: float) -> np.ndarray:
    result = np.zeros(10, dtype=np.float32)
    result[0] = value
    result[-1] = 1.0
    return result


def test_latest_strategy_uses_only_each_new_chunks_first_action() -> None:
    policy = _FakePolicy()
    dispatcher = LatestChunkRecedingHorizonDispatcher(policy)

    first = dispatcher.dispatch({"frame": 3}, _goal(0.25))
    second = dispatcher.dispatch({"frame": 4}, _goal(0.25))

    np.testing.assert_array_equal(first.dispatched_action, first.raw_action_chunk[0])
    np.testing.assert_array_equal(second.dispatched_action, second.raw_action_chunk[0])
    assert first.contributing_chunk_ages == (0,)
    assert second.contributing_chunk_ages == (0,)
    assert policy.chunk_calls == 2
    assert policy.predict_calls == 0


def test_legacy_strategy_is_public_predict_byte_compatible() -> None:
    policy = _FakePolicy()
    dispatcher = LegacyTemporalAggregationDispatcher(policy)

    record = dispatcher.dispatch({"frame": 7}, _goal(0.5))

    expected = np.asarray([7.0, 0.5, 99.0, -99.0], dtype=np.float32)
    assert record.dispatched_action.tobytes() == expected.tobytes()
    assert policy.predict_calls == 1
    assert record.contributing_chunk_ages == (0,)


def test_goal_sha_change_resets_cache_but_same_goal_does_not() -> None:
    policy = _FakePolicy()
    dispatcher = LatestChunkRecedingHorizonDispatcher(policy)

    first = dispatcher.dispatch({"frame": 0}, _goal(0.1))
    second = dispatcher.dispatch({"frame": 1}, _goal(0.1))
    changed = dispatcher.dispatch({"frame": 2}, _goal(0.2))

    assert first.cache_reset is True
    assert second.cache_reset is False
    assert changed.cache_reset is True
    assert first.goal_sha256 == second.goal_sha256
    assert changed.goal_sha256 != first.goal_sha256
    assert policy.reset_count == 2


def test_new_request_resets_even_when_goal_sha_repeats() -> None:
    policy = _FakePolicy()
    dispatcher = LatestChunkRecedingHorizonDispatcher(policy)
    dispatcher.dispatch({"frame": 0}, _goal(0.1))

    dispatcher.begin_request()
    repeated = dispatcher.dispatch({"frame": 0}, _goal(0.1))

    assert repeated.cache_reset is True
    assert policy.reset_count == 2


def test_two_arms_have_independent_policy_and_cache_identity() -> None:
    dispatchers = make_independent_arm_dispatchers(
        policy_factory=_FakePolicy,
        dispatcher_type=LatestChunkRecedingHorizonDispatcher,
    )

    assert dispatchers["baseline"].policy is not dispatchers["alternate"].policy
    assert (
        dispatchers["baseline"].policy.cache
        is not dispatchers["alternate"].policy.cache
    )
    dispatchers["baseline"].dispatch({"frame": 0}, _goal(0.1))
    assert dispatchers["alternate"].policy.reset_count == 0


def test_chunk_age_summary_counts_every_contributor() -> None:
    policy = _FakePolicy()
    dispatcher = LegacyTemporalAggregationDispatcher(policy)
    rows = [dispatcher.dispatch({"frame": frame}, _goal(0.1)) for frame in range(3)]

    summary = summarise_contributing_chunk_ages(rows)

    assert summary["count_by_age"] == {"0": 3, "1": 2, "2": 1}
    assert summary["maximum_age"] == 2
    assert summary["contributor_count_by_frame"] == [1, 2, 3]


def test_action_support_detects_bounds_and_nonfinite_without_clipping() -> None:
    actions = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0],
            [1.1, 0.0, 0.0, 0.0],
            [np.nan, 0.0, 0.0, 0.0],
        ],
        dtype=np.float32,
    )

    result = assess_action_support(
        actions,
        p01=np.full(4, -1.0, dtype=np.float32),
        p99=np.full(4, 1.0, dtype=np.float32),
    )

    assert result["row_count"] == 3
    assert result["support_violation_count"] == 1
    assert result["nonfinite_count"] == 1
    assert result["clipping_applied"] is False
    assert result["support_violation_by_axis"] == [1, 0, 0, 0]
