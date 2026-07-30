from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from testbed.policies.act.adapter import ACTAdapter
from testbed.runtime._eval import _build_act_eval_policy


def _adapter(
    *,
    num_queries: int,
    window: int | None = None,
    weight_order: str = "legacy_oldest_first",
    decay: float = 0.01,
) -> ACTAdapter:
    adapter = object.__new__(ACTAdapter)
    adapter.device = torch.device("cpu")
    adapter._num_queries = num_queries
    adapter._temporal_agg_window = num_queries if window is None else window
    adapter._temporal_agg_weight_order = weight_order
    adapter._temporal_agg_decay = decay
    adapter._t = 0
    adapter._all_time_actions = None
    adapter._all_time_actions_valid = None
    adapter._cached_actions = None
    return adapter


def _aggregate_at(
    adapter: ACTAdapter,
    *,
    step: int,
    query_values: list[float],
) -> float:
    adapter._t = step
    chunk = torch.tensor(query_values, dtype=torch.float32).reshape(1, -1, 1)
    return float(ACTAdapter._aggregate(adapter, chunk)[0])


def test_temporal_agg_window_20_excludes_contributor_at_age_20() -> None:
    adapter = _adapter(num_queries=100, window=20)

    first_chunk = [0.0] * 100
    first_chunk[20] = 1000.0
    _aggregate_at(adapter, step=0, query_values=first_chunk)
    for step in range(1, 21):
        value = _aggregate_at(adapter, step=step, query_values=[0.0] * 100)

    assert value == pytest.approx(0.0)


def test_newest_first_weights_latest_contributor_highest() -> None:
    adapter = _adapter(
        num_queries=3,
        window=3,
        weight_order="newest_first",
        decay=0.5,
    )

    _aggregate_at(adapter, step=0, query_values=[0.0, 0.0, 1.0])
    _aggregate_at(adapter, step=1, query_values=[0.0, 2.0, 0.0])
    actual = _aggregate_at(adapter, step=2, query_values=[3.0, 0.0, 0.0])

    ages = np.asarray([2.0, 1.0, 0.0])
    weights = np.exp(-0.5 * ages)
    expected = float(np.dot(np.asarray([1.0, 2.0, 3.0]), weights / weights.sum()))
    assert actual == pytest.approx(expected)
    assert weights[2] > weights[1] > weights[0]


def test_default_temporal_contract_preserves_legacy_oldest_first_weights() -> None:
    resolved = ACTAdapter._resolve_temporal_aggregation_config(
        {"num_queries": 3},
        num_queries=3,
    )
    assert resolved == (3, "legacy_oldest_first", 0.01)

    adapter = _adapter(num_queries=3)
    _aggregate_at(adapter, step=0, query_values=[0.0, 0.0, 1.0])
    _aggregate_at(adapter, step=1, query_values=[0.0, 2.0, 0.0])
    actual = _aggregate_at(adapter, step=2, query_values=[3.0, 0.0, 0.0])

    weights = np.exp(-0.01 * np.arange(3))
    expected = float(np.dot(np.asarray([1.0, 2.0, 3.0]), weights / weights.sum()))
    assert actual == pytest.approx(expected)
    assert weights[0] > weights[1] > weights[2]


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"temporal_agg_window": 0}, "temporal_agg_window"),
        ({"temporal_agg_window": 4}, "temporal_agg_window"),
        ({"temporal_agg_window": True}, "temporal_agg_window"),
        ({"temporal_agg_weight_order": "reverse"}, "temporal_agg_weight_order"),
        ({"temporal_agg_weight_order": []}, "temporal_agg_weight_order"),
        ({"temporal_agg_decay": -0.1}, "temporal_agg_decay"),
        ({"temporal_agg_decay": float("inf")}, "temporal_agg_decay"),
    ],
)
def test_temporal_contract_rejects_invalid_values(
    override: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        ACTAdapter._resolve_temporal_aggregation_config(
            {"num_queries": 3, **override},
            num_queries=3,
        )


def test_invalid_temporal_contract_fails_before_model_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testbed.policies.act.detr import main as detr_main

    model_build_called = False

    def _fake_build(_policy_config):
        nonlocal model_build_called
        model_build_called = True
        raise AssertionError("model build must not run for an invalid contract")

    monkeypatch.setattr(detr_main, "build_ACT_model_and_optimizer", _fake_build)

    with pytest.raises(ValueError, match="temporal_agg_window"):
        ACTAdapter(
            policy_config={
                "num_queries": 3,
                "temporal_agg_window": 0,
            },
            norm_stats={},
            device="cpu",
        )
    assert model_build_called is False


def test_reset_clears_all_temporal_and_chunk_state() -> None:
    adapter = _adapter(num_queries=3)
    _aggregate_at(adapter, step=0, query_values=[100.0, 100.0, 100.0])
    _aggregate_at(adapter, step=1, query_values=[100.0, 100.0, 100.0])
    adapter._cached_actions = torch.ones((3, 1))

    adapter.reset()

    assert adapter._t == 0
    assert adapter._all_time_actions is None
    assert adapter._all_time_actions_valid is None
    assert adapter._cached_actions is None
    assert _aggregate_at(
        adapter,
        step=0,
        query_values=[7.0, 8.0, 9.0],
    ) == pytest.approx(7.0)


def test_eval_policy_builder_forwards_temporal_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_from_checkpoint(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ACTAdapter, "from_checkpoint", _fake_from_checkpoint)

    _build_act_eval_policy(
        config={"train": {"lr": 1e-5}},
        ckpt_path=tmp_path / "policy_best.ckpt",
        ckpt_dir=tmp_path,
        camera_names=["fpv"],
        equipment_model="yulong",
        max_episode_len=400,
        low_dim_keys=["qpos"],
        temporal_agg=True,
        device="cpu",
        act_params={
            "chunk_size": 100,
            "temporal_agg_window": 20,
            "temporal_agg_weight_order": "newest_first",
            "temporal_agg_decay": 0.02,
        },
    )

    policy_config = captured["policy_config"]
    assert isinstance(policy_config, dict)
    assert policy_config["temporal_agg_window"] == 20
    assert policy_config["temporal_agg_weight_order"] == "newest_first"
    assert policy_config["temporal_agg_decay"] == pytest.approx(0.02)
