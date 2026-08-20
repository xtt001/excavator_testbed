from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from testbed.eval import return_temporal_dispatch_forensics as forensics


def _contract() -> dict[str, object]:
    return {
        "enabled": True,
        "num_queries": 3,
        "window": 3,
        "weight_order": "legacy_oldest_first",
        "decay": 0.0,
    }


def test_pure_forensics_rank_historical_plan_that_opposes_latest_response() -> None:
    baseline = np.zeros((3, 3, 2), dtype=np.float32)
    alternate = np.asarray(
        [
            [[1.0, 0.0], [0.0, 0.0], [-2.0, 0.0]],
            [[1.0, 0.0], [-0.5, 0.0], [0.0, 0.0]],
            [[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        ],
        dtype=np.float32,
    )

    result = forensics.derive_return_temporal_dispatch_forensics(
        baseline_chunks=baseline,
        alternate_chunks=alternate,
        action_threshold=np.asarray([0.5, 0.5], dtype=np.float32),
        temporal_contract=_contract(),
        action_step_ids=[100, 101, 102],
        max_ranked_historical_contributors=2,
    )

    assert result["raw_current_query_response_fraction"] == 1.0
    assert result["temporal_aggregated_response_fraction"] == pytest.approx(1 / 3)
    assert result["latest_response_suppressed_frame_count"] == 2
    assert result["suppression_mechanism_summary"] == {
        "historical_net_opposes_latest_response_frame_count": 1,
        "latest_weight_dilution_without_net_opposition_frame_count": 1,
        "latest_query_weight_min": pytest.approx(1 / 3),
        "latest_query_weight_max": pytest.approx(1 / 2),
        "latest_query_weight_mean": pytest.approx(5 / 12),
    }
    frame = result["suppressed_frames"][1]
    assert frame["frame_index"] == 2
    assert frame["action_step_id"] == 102
    assert frame["latest_query"]["query_index"] == 0
    assert frame["latest_query"]["raw_action_delta_vector"] == [1.0, 0.0]
    assert frame["latest_query"]["weighted_contribution_vector"] == pytest.approx(
        [1.0 / 3.0, 0.0]
    )
    # source frame 0 contributes query offset 2 and is the strongest opposing
    # historical plan at the failed step.
    top = frame["historical_contributors_ranked_by_suppression"][0]
    assert top["source_frame_index"] == 0
    assert top["source_action_step_id"] == 100
    assert top["query_index"] == 2
    assert top["weight"] == pytest.approx(1.0 / 3.0)
    assert top["raw_action_delta_vector"] == [-2.0, 0.0]
    assert top["weighted_contribution_vector"] == pytest.approx([-2.0 / 3.0, 0.0])
    assert top["suppression_projection"] == pytest.approx(2.0 / 3.0)
    assert frame["historical_net_suppression_projection"] == pytest.approx(5.0 / 6.0)
    assert frame["historical_net_opposes_latest_response"] is True


def test_historical_cache_validation_rejects_changed_query_offset_or_weight() -> None:
    baseline = np.zeros((2, 3, 1), dtype=np.float32)
    alternate = np.asarray(
        [
            [[1.0], [-1.0], [0.0]],
            [[1.0], [0.0], [0.0]],
        ],
        dtype=np.float32,
    )
    historical = forensics.cache_contributor_summaries(
        baseline_chunks=baseline,
        alternate_chunks=alternate,
        action_threshold=np.asarray([0.5], dtype=np.float32),
        temporal_contract=_contract(),
    )

    passed = forensics.validate_historical_cache_reconstruction(
        historical_cache_contributors=historical,
        baseline_chunks=baseline,
        alternate_chunks=alternate,
        action_threshold=np.asarray([0.5], dtype=np.float32),
        temporal_contract=_contract(),
    )
    assert passed["passed"] is True
    assert passed["frame_count"] == 2

    historical[1]["contributors"][0]["query_index"] = 0
    rejected = forensics.validate_historical_cache_reconstruction(
        historical_cache_contributors=historical,
        baseline_chunks=baseline,
        alternate_chunks=alternate,
        action_threshold=np.asarray([0.5], dtype=np.float32),
        temporal_contract=_contract(),
    )
    assert rejected["passed"] is False
    assert "query_index" in rejected["mismatch_fields"]


def test_injectable_public_policy_stream_uses_chunk_then_stateful_predict_once_per_frame() -> (
    None
):
    class FakePolicy:
        def __init__(self) -> None:
            self.reset_count = 0
            self.chunk_count = 0
            self.predict_count = 0
            self._chunks: list[np.ndarray] = []

        def reset(self) -> None:
            self.reset_count += 1
            self._chunks = []

        def predict_action_chunk(self, observation):
            self.chunk_count += 1
            value = float(observation["token"][0])
            return SimpleNamespace(
                actions=np.asarray([[value], [value + 1.0]], dtype=np.float32)
            )

        def predict(self, observation):
            self.predict_count += 1
            chunk = self.predict_action_chunk(observation).actions
            self._chunks.append(chunk)
            step = len(self._chunks) - 1
            contributors = [
                values[step - source] for source, values in enumerate(self._chunks)
            ]
            return np.mean(np.stack(contributors), axis=0)

    policy = FakePolicy()
    result = forensics.collect_public_policy_stream(
        policy=policy,
        observations=[{"qpos": np.zeros(4)}, {"qpos": np.ones(4)}],
        token_key="token",
        token=np.asarray([2.0], dtype=np.float32),
    )

    assert policy.reset_count == 1
    # The fake's stateful method calls its own public chunk method as well;
    # the helper itself must add exactly one non-advancing query per frame.
    assert policy.chunk_count == 4
    assert policy.predict_count == 2
    assert result["chunks"].shape == (2, 2, 1)
    assert result["actions"].shape == (2, 1)


def test_proposed_strategies_are_explicitly_not_evidence_or_runtime_configuration() -> (
    None
):
    result = forensics.proposed_temporal_dispatch_strategies(
        temporal_contract=_contract()
    )

    assert result["status"] == "not_evaluated"
    assert result["runtime_change"] is False
    assert result["selection_permitted"] is False
    assert [item["candidate_id"] for item in result["candidates"]] == [
        "baseline_legacy_oldest_first",
        "same_window_newest_biased",
        "bounded_age_aggregation",
        "latest_chunk_diagnostic_only",
    ]
    assert result["candidates"][-1]["runtime_eligible"] is False
