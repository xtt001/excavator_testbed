from __future__ import annotations

import numpy as np
import pytest

from testbed.eval.temporal_dispatch_contract import (
    REQUIRED_RESPONSE_ACTIVE_FRACTION,
    TemporalDispatchContractError,
    TemporalDispatchMetricContract,
    evaluate_temporal_dispatch_metrics,
    pre_registered_temporal_dispatch_strategies,
    reconstruct_temporal_dispatch,
)


def _chunks(frame_count: int, *, action_dim: int = 1) -> np.ndarray:
    return np.zeros((frame_count, 100, action_dim), dtype=np.float32)


def _metric_contract(action_dim: int = 1) -> TemporalDispatchMetricContract:
    return TemporalDispatchMetricContract(
        response_threshold=np.full(action_dim, 0.5, dtype=np.float32),
        action_scale=np.full(action_dim, 2.0, dtype=np.float32),
        envelope_lower=np.full(action_dim, -3.0, dtype=np.float32),
        envelope_upper=np.full(action_dim, 3.0, dtype=np.float32),
        jitter_mean_abs_limit=np.full(action_dim, 1.0, dtype=np.float32),
        discontinuity_threshold=np.full(action_dim, 0.75, dtype=np.float32),
    )


def test_pre_registered_strategies_are_fixed_and_latest_is_diagnostic_only() -> None:
    strategies = pre_registered_temporal_dispatch_strategies()

    assert tuple(strategies) == (
        "legacy_100_oldest_first_decay_0p01",
        "newest_first_100_decay_0p01",
        "newest_first_max_age_20_decay_0p01",
        "latest_current_chunk_diagnostic",
    )
    legacy = strategies["legacy_100_oldest_first_decay_0p01"]
    assert legacy.num_queries == 100
    assert legacy.maximum_contributor_age == 99
    assert legacy.weight_order == "legacy_oldest_first"
    assert legacy.decay == pytest.approx(0.01)
    assert legacy.promotion_eligible is False

    latest = strategies["latest_current_chunk_diagnostic"]
    assert latest.dispatch_mode == "latest_current_chunk"
    assert latest.diagnostic_only is True
    assert latest.promotion_eligible is False
    assert latest.maximum_contributor_age == 0


def test_legacy_reconstruction_reports_query_indices_weights_and_reset_boundary() -> None:
    chunks = _chunks(4)
    chunks[0, 2, 0] = 10.0
    chunks[1, 1, 0] = 20.0
    chunks[2, 0, 0] = 30.0
    chunks[3, 0, 0] = 40.0
    strategy = pre_registered_temporal_dispatch_strategies()[
        "legacy_100_oldest_first_decay_0p01"
    ]

    trace = reconstruct_temporal_dispatch(
        chunks=chunks,
        strategy=strategy,
        reset_frame_indices=(0, 3),
    )

    contributors = trace.contributors[2]
    assert [value.source_frame_index for value in contributors] == [0, 1, 2]
    assert [value.query_index for value in contributors] == [2, 1, 0]
    assert [value.age for value in contributors] == [2, 1, 0]
    assert sum(value.weight for value in contributors) == pytest.approx(1.0)
    assert contributors[0].weight > contributors[1].weight > contributors[2].weight
    expected_weights = np.exp(-0.01 * np.arange(3))
    expected = np.dot(
        np.asarray([10.0, 20.0, 30.0]), expected_weights / expected_weights.sum()
    )
    assert trace.actions[2, 0] == pytest.approx(expected)

    assert len(trace.contributors[3]) == 1
    assert trace.contributors[3][0].source_frame_index == 3
    assert trace.contributors[3][0].query_index == 0
    assert trace.actions[3, 0] == pytest.approx(40.0)


def test_newest_first_and_maximum_age_use_exact_pre_registered_semantics() -> None:
    chunks = _chunks(22)
    chunks[0, 20, 0] = 100.0
    chunks[19, 1, 0] = 20.0
    chunks[20, 0, 0] = 30.0
    strategies = pre_registered_temporal_dispatch_strategies()

    newest = reconstruct_temporal_dispatch(
        chunks=chunks,
        strategy=strategies["newest_first_100_decay_0p01"],
    )
    newest_weights = newest.contributors[20]
    assert newest_weights[-1].source_frame_index == 20
    assert newest_weights[-1].weight > newest_weights[0].weight

    bounded = reconstruct_temporal_dispatch(
        chunks=chunks,
        strategy=strategies["newest_first_max_age_20_decay_0p01"],
    )
    assert bounded.contributors[20][0].source_frame_index == 0
    assert bounded.contributors[20][0].query_index == 20
    assert bounded.contributors[21][0].source_frame_index == 1
    assert all(item.source_frame_index != 0 for item in bounded.contributors[21])


def test_latest_current_chunk_never_uses_history_and_serialises_json_ready_trace() -> None:
    chunks = _chunks(3, action_dim=2)
    chunks[:, 0, :] = np.asarray([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    chunks[0, 2, :] = -99.0
    strategy = pre_registered_temporal_dispatch_strategies()[
        "latest_current_chunk_diagnostic"
    ]

    trace = reconstruct_temporal_dispatch(chunks=chunks, strategy=strategy)

    np.testing.assert_array_equal(trace.actions, chunks[:, 0, :])
    assert [[item.query_index for item in frame] for frame in trace.contributors] == [
        [0],
        [0],
        [0],
    ]
    assert all(frame[0].weight == 1.0 for frame in trace.contributors)
    serialised = trace.as_dict()
    assert serialised["strategy"]["diagnostic_only"] is True
    assert serialised["actions"] == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]


def test_metrics_keep_fixed_80_percent_gate_and_report_quality_diagnostics() -> None:
    baseline_chunks = _chunks(4)
    alternate_chunks = _chunks(4)
    alternate_chunks[:, 0, 0] = np.asarray([1.0, 1.0, 0.0, 1.0])
    strategy = pre_registered_temporal_dispatch_strategies()[
        "latest_current_chunk_diagnostic"
    ]
    baseline = reconstruct_temporal_dispatch(chunks=baseline_chunks, strategy=strategy)
    alternate = reconstruct_temporal_dispatch(chunks=alternate_chunks, strategy=strategy)

    result = evaluate_temporal_dispatch_metrics(
        baseline=baseline,
        alternate=alternate,
        metric_contract=_metric_contract(),
        reference_actions=baseline.actions,
    )

    assert result["response"]["active_frame_fraction"] == pytest.approx(0.75)
    assert result["response"]["required_active_frame_fraction"] == pytest.approx(
        REQUIRED_RESPONSE_ACTIVE_FRACTION
    )
    assert result["response"]["passes_fixed_gate"] is False
    quality = result["alternate_action_quality"]
    assert quality["first_difference"]["discontinuity_transition_count"] == 2
    assert quality["first_difference"]["passes_jitter_limit"] is True
    assert quality["envelope"]["within_frozen_envelope"] is True
    assert quality["reference_delta"]["max_abs"] == pytest.approx(1.0)
    assert quality["action_scale"]["max_abs_over_scale"] == pytest.approx([0.5])


def test_metric_contract_rejects_any_response_gate_other_than_fixed_80_percent() -> None:
    with pytest.raises(TemporalDispatchContractError, match="fixed at 0.80"):
        TemporalDispatchMetricContract(
            response_threshold=np.asarray([0.5], dtype=np.float32),
            action_scale=np.asarray([1.0], dtype=np.float32),
            envelope_lower=np.asarray([-1.0], dtype=np.float32),
            envelope_upper=np.asarray([1.0], dtype=np.float32),
            jitter_mean_abs_limit=np.asarray([1.0], dtype=np.float32),
            discontinuity_threshold=np.asarray([1.0], dtype=np.float32),
            required_active_frame_fraction=0.79,
        )


def test_reconstruction_rejects_nonzero_initial_reset_and_wrong_query_width() -> None:
    strategy = pre_registered_temporal_dispatch_strategies()[
        "legacy_100_oldest_first_decay_0p01"
    ]
    with pytest.raises(TemporalDispatchContractError, match="must include frame 0"):
        reconstruct_temporal_dispatch(
            chunks=_chunks(2),
            strategy=strategy,
            reset_frame_indices=(1,),
        )
    with pytest.raises(TemporalDispatchContractError, match="query width"):
        reconstruct_temporal_dispatch(
            chunks=np.zeros((2, 99, 1), dtype=np.float32),
            strategy=strategy,
        )
