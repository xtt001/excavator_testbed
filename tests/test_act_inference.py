from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from testbed.policies.act.adapter import ACTAdapter
from testbed.policies.act.inference import (
    ACTActionChunk,
    TemporalAggregationContract,
    build_act_adapter_config,
    describe_act_inference,
    load_act_policy,
    resolve_act_low_dim_state_dim,
)


class _FixedActModel:
    def __init__(self) -> None:
        self.eval_calls = 0

    def eval(self) -> None:
        self.eval_calls += 1

    def __call__(self, proprio, image, _actions):
        assert tuple(proprio.shape) == (1, 4)
        assert tuple(image.shape) == (1, 1, 3, 2, 2)
        return (
            torch.tensor(
                [[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]],
                dtype=torch.float32,
            ),
            None,
            (None, None),
            torch.tensor([[0.25, 0.75]], dtype=torch.float32),
        )


def _adapter() -> ACTAdapter:
    adapter = object.__new__(ACTAdapter)
    adapter.device = torch.device("cpu")
    adapter.policy_config = {
        "num_queries": 3,
        "low_dim_keys": ["qpos"],
    }
    adapter._camera_names = ["fpv"]
    adapter._low_dim_keys = ["qpos"]
    adapter._image_mask_config = {}
    adapter._normalize = lambda value: value
    adapter._proprio_mean = torch.zeros(4, dtype=torch.float32)
    adapter._proprio_std = torch.ones(4, dtype=torch.float32)
    adapter._model = _FixedActModel()
    adapter.temporal_agg = False
    adapter._num_queries = 3
    adapter._temporal_agg_window = 2
    adapter._temporal_agg_weight_order = "newest_first"
    adapter._temporal_agg_decay = 0.25
    adapter._t = 7
    adapter._all_time_actions = torch.full((3, 3, 2), 9.0)
    adapter._all_time_actions_valid = torch.ones((3, 3), dtype=torch.bool)
    adapter._cached_actions = torch.full((3, 2), 8.0)
    adapter.norm_stats = {
        "action_mean": np.asarray([10.0, 100.0], dtype=np.float32),
        "action_std": np.asarray([2.0, 10.0], dtype=np.float32),
    }
    return adapter


def _observation() -> dict[str, np.ndarray]:
    return {
        "qpos": np.zeros(4, dtype=np.float32),
        "image_fpv": np.zeros((3, 2, 2), dtype=np.float32),
    }


def test_predict_action_chunk_is_unnormalised_and_does_not_mutate_temporal_state() -> None:
    adapter = _adapter()
    before_actions = adapter._all_time_actions.clone()
    before_valid = adapter._all_time_actions_valid.clone()
    before_cached = adapter._cached_actions.clone()

    chunk = adapter.predict_action_chunk(_observation())

    assert isinstance(chunk, ACTActionChunk)
    np.testing.assert_allclose(
        chunk.actions,
        np.asarray(
            [[12.0, 120.0], [16.0, 140.0], [20.0, 160.0]],
            dtype=np.float32,
        ),
    )
    np.testing.assert_array_equal(chunk.action_chunk, chunk.actions)
    np.testing.assert_array_equal(
        chunk.first_action,
        np.asarray([12.0, 120.0], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        chunk.outcome,
        np.asarray([0.25, 0.75], dtype=np.float32),
    )
    assert adapter._t == 7
    torch.testing.assert_close(adapter._all_time_actions, before_actions)
    torch.testing.assert_close(adapter._all_time_actions_valid, before_valid)
    torch.testing.assert_close(adapter._cached_actions, before_cached)


def test_predict_with_outcome_matches_first_action_of_full_chunk() -> None:
    adapter = _adapter()

    chunk = adapter.predict_action_chunk(_observation())
    action, outcome = adapter.predict_with_outcome(_observation())

    np.testing.assert_array_equal(action, chunk.first_action)
    np.testing.assert_array_equal(outcome, chunk.outcome)
    assert adapter._t == 7


def test_predict_keeps_scheduled_state_and_matches_chunk_first_action_at_reset() -> None:
    adapter = _adapter()
    adapter._t = 0
    adapter._all_time_actions = None
    adapter._all_time_actions_valid = None
    adapter._cached_actions = None

    chunk = adapter.predict_action_chunk(_observation())
    action = adapter.predict(_observation())

    np.testing.assert_array_equal(action, chunk.first_action)
    assert adapter._t == 1
    assert adapter._cached_actions is not None


def test_temporal_predict_matches_initial_chunk_action_and_advances_once() -> None:
    adapter = _adapter()
    adapter.temporal_agg = True
    adapter._t = 0
    adapter._all_time_actions = None
    adapter._all_time_actions_valid = None
    adapter._cached_actions = None

    chunk = adapter.predict_action_chunk(_observation())
    action = adapter.predict(_observation())

    np.testing.assert_array_equal(action, chunk.first_action)
    assert adapter._t == 1
    assert adapter._all_time_actions is not None
    assert adapter._all_time_actions_valid is not None
    assert adapter._cached_actions is None


def test_temporal_contract_and_description_report_resolved_runtime_values() -> None:
    adapter = _adapter()
    adapter.temporal_agg = True

    contract = adapter.temporal_aggregation_contract
    assert contract == TemporalAggregationContract(
        enabled=True,
        num_queries=3,
        window=2,
        weight_order="newest_first",
        decay=0.25,
    )
    assert contract.as_dict() == {
        "enabled": True,
        "num_queries": 3,
        "window": 2,
        "weight_order": "newest_first",
        "decay": 0.25,
    }

    description = describe_act_inference(adapter)
    assert description["temporal_aggregation"] == contract.as_dict()
    assert description["temporal_agg"] is True
    assert description["temporal_agg_window"] == 2
    assert description["temporal_agg_weight_order"] == "newest_first"
    assert description["temporal_agg_decay"] == pytest.approx(0.25)
    assert description["num_queries"] == 3
    assert description["action_dim"] == 2
    assert description["low_dim_keys"] == ["qpos"]


def test_inference_builder_and_loader_keep_checkpoint_inputs_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = {
        "train": {"lr": 2.0e-5},
    }
    adapter_config = build_act_adapter_config(
        config=config,
        camera_names=["fpv"],
        equipment_model="yulong",
        max_episode_len=400,
        low_dim_keys=["qpos", "qvel", "dig_cut_tokens"],
        act_params={
            "chunk_size": 100,
            "temporal_agg_window": 20,
            "temporal_agg_weight_order": "newest_first",
            "temporal_agg_decay": 0.02,
        },
        outcome_head_config={"enabled": True, "dim": 10},
        image_mask_config={"fpv": {"enabled": False}},
        supervision_keys=["dig_outcome_targets"],
    )
    assert adapter_config["state_dim"] == 18
    assert adapter_config["supervision_keys"] == ["dig_outcome_targets"]
    assert adapter_config["temporal_agg_window"] == 20
    assert adapter_config["temporal_agg_weight_order"] == "newest_first"
    assert adapter_config["temporal_agg_decay"] == pytest.approx(0.02)

    captured: dict[str, object] = {}

    def _fake_from_checkpoint(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ACTAdapter, "from_checkpoint", _fake_from_checkpoint)
    loaded = load_act_policy(
        ckpt_path=tmp_path / "policy_best.ckpt",
        policy_config=adapter_config,
        norm_stats_path=tmp_path / "dataset_stats.pkl",
        temporal_agg=True,
        device="cpu",
    )

    assert loaded is not None
    assert captured["ckpt_path"] == tmp_path / "policy_best.ckpt"
    assert captured["norm_stats_path"] == tmp_path / "dataset_stats.pkl"
    assert captured["policy_config"] == adapter_config
    assert captured["temporal_agg"] is True
    assert captured["device"] == "cpu"


def test_low_dim_resolver_covers_the_shared_goal_conditioning_contract() -> None:
    assert resolve_act_low_dim_state_dim(["qpos", "qvel"], "yulong") == 8
    assert (
        resolve_act_low_dim_state_dim(
            ["qpos", "qvel", "dig_cut_tokens"], "yulong"
        )
        == 18
    )
    assert (
        resolve_act_low_dim_state_dim(
            ["qpos", "qvel", "return_start_envelope_tokens_v1"], "yulong"
        )
        == 26
    )
