from pathlib import Path

import numpy as np
import torch

from testbed.data.hdf5_io import write_episode
from testbed.policies.act_graph.dataset import load_graph_data
from testbed.policies.act_graph.adapter import ACTGraphAdapter
from testbed.policies.act_graph.model import GraphEncoder, GraphEncoderConfig


def test_graph_dataloader_returns_graph_batch(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "graph_dataset"
    dataset_dir.mkdir()
    _write_graph_episode(dataset_dir / "episode_0.hdf5", length=5)

    train_loader, val_loader, norm_stats, _, split_info = load_graph_data(
        dataset_dir=dataset_dir,
        num_episodes=1,
        camera_names=["fpv"],
        episode_len=5,
        batch_size_train=1,
        batch_size_val=1,
        num_workers=0,
        pin_memory=False,
        split_path=tmp_path / "split.yaml",
        low_dim_keys=["qpos", "qvel"],
    )

    image, proprio, graph, action, is_pad = next(iter(train_loader))

    assert image.shape == (1, 1, 3, 8, 8)
    assert proprio.shape == (1, 8)
    assert graph["node_features"].shape == (1, 6, 8)
    assert graph["node_mask"].dtype is torch.bool
    assert graph["edge_indices"].shape == (1, 10, 2)
    assert graph["edge_features"].shape == (1, 10, 5)
    assert graph["graph_globals"].shape == (1, 6)
    assert action.shape == (1, 5, 4)
    assert is_pad.shape == (1, 5)
    assert int(norm_stats["proprio_dim"]) == 8
    assert split_info["uses_observation_graph"] is True
    assert next(iter(val_loader))[2]["edge_mask"].shape == (1, 10)


def test_graph_encoder_outputs_fixed_embedding() -> None:
    encoder = GraphEncoder(
        GraphEncoderConfig(
            node_feature_dim=8,
            edge_feature_dim=5,
            graph_global_dim=6,
            hidden_dim=16,
            output_dim=12,
        )
    )
    graph = {
        "node_features": np.ones((2, 6, 8), dtype=np.float32),
        "node_mask": np.asarray([[1, 1, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0]], dtype=bool),
        "edge_features": np.ones((2, 10, 5), dtype=np.float32),
        "edge_indices": np.asarray(
            [
                [[0, 1], [1, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]],
                [[0, 1], [1, 2], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]],
            ],
            dtype=np.int64,
        ),
        "edge_mask": np.asarray(
            [[1, 1, 1, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
            dtype=bool,
        ),
        "graph_globals": np.zeros((2, 6), dtype=np.float32),
    }

    output = encoder({key: torch.as_tensor(value) for key, value in graph.items()})

    assert output.shape == (2, 12)


def test_graph_encoder_uses_edge_indices_for_message_passing() -> None:
    torch.manual_seed(0)
    encoder = GraphEncoder(
        GraphEncoderConfig(
            node_feature_dim=8,
            edge_feature_dim=5,
            graph_global_dim=6,
            hidden_dim=16,
            output_dim=12,
            message_passing_steps=2,
        )
    )
    graph = {
        "node_features": torch.zeros((1, 4, 8), dtype=torch.float32),
        "node_mask": torch.ones((1, 4), dtype=torch.bool),
        "edge_indices": torch.asarray([[[0, 1], [1, 2], [2, 3]]], dtype=torch.long),
        "edge_features": torch.ones((1, 3, 5), dtype=torch.float32),
        "edge_mask": torch.ones((1, 3), dtype=torch.bool),
        "graph_globals": torch.zeros((1, 6), dtype=torch.float32),
    }
    graph["node_features"][0, :, 0] = torch.asarray([1.0, 2.0, 4.0, 8.0])
    rewired = dict(graph)
    rewired["edge_indices"] = torch.asarray([[[3, 2], [2, 1], [1, 0]]], dtype=torch.long)

    output = encoder(graph)
    rewired_output = encoder(rewired)

    assert not torch.allclose(output, rewired_output)


def test_train_policy_dispatches_act_graph(monkeypatch, tmp_path: Path) -> None:
    from testbed.runtime import _train

    calls = {}

    def fake_load_graph_data(**kwargs):
        calls["loader_kwargs"] = kwargs
        return object(), object(), _norm_stats(), True, {
            "split_path": str(tmp_path / "split.yaml"),
            "train_ids": [0],
            "val_ids": [0],
        }

    class FakeTrainer:
        def __init__(self, policy_config, config):
            calls["policy_config"] = policy_config
            calls["trainer_config"] = config

        def fit(self, train_loader, val_loader, config):
            calls["fit_called"] = True
            return 0, 0.0, {}

    monkeypatch.setattr(
        "testbed.policies.act_graph.dataset.load_graph_data",
        fake_load_graph_data,
    )
    monkeypatch.setattr(
        "testbed.policies.act_graph.trainer.ACTGraphTrainer",
        FakeTrainer,
    )

    _train.train_policy(
        {
            "task": {
                "name": "graph_smoke",
                "equipment_model": "agxunity",
                "dataset_dir": str(tmp_path / "dataset"),
                "num_episodes": 1,
                "episode_len": 5,
                "camera_names": ["fpv"],
            },
            "policy": {
                "class": "ACT_GRAPH",
                "low_dim_keys": ["qpos", "qvel"],
                "act_params": {"chunk_size": 4, "hidden_dim": 32, "dim_feedforward": 64},
                "graph_params": {"embedding_dim": 12},
            },
            "train": {
                "ckpt_dir": str(tmp_path / "ckpts"),
                "num_epochs": 1,
                "batch_size": 1,
                "num_workers": 0,
                "pin_memory": False,
                "device": "cpu",
            },
        }
    )

    assert calls["fit_called"] is True
    assert calls["policy_config"]["state_dim"] == 20
    assert calls["policy_config"]["graph_params"]["embedding_dim"] == 12
    assert calls["loader_kwargs"]["low_dim_keys"] == ["qpos", "qvel"]


def test_act_graph_adapter_predict_consumes_online_graph() -> None:
    adapter = ACTGraphAdapter.__new__(ACTGraphAdapter)
    adapter.device = torch.device("cpu")
    adapter.norm_stats = {
        "action_mean": np.zeros(4, dtype=np.float32),
        "action_std": np.ones(4, dtype=np.float32),
    }
    adapter.temporal_agg = False
    adapter._camera_names = ["fpv"]
    adapter._low_dim_keys = ["qpos", "qvel"]
    adapter._image_mask_config = {}
    adapter._num_queries = 3
    adapter._t = 0
    adapter._cached_actions = None
    adapter._all_time_actions = None
    adapter._all_time_actions_valid = None
    adapter._normalize = torch.nn.Identity()
    adapter._proprio_mean = torch.zeros(8)
    adapter._proprio_std = torch.ones(8)
    adapter._model = _DummyACTGraphModel(num_queries=3, action_dim=4)

    action = adapter.predict(
        {
            "qpos": np.zeros(4, dtype=np.float32),
            "qvel": np.ones(4, dtype=np.float32),
            "image_fpv": np.zeros((3, 8, 8), dtype=np.float32),
            "observation_graph": _online_graph(),
        }
    )

    assert action.shape == (4,)
    np.testing.assert_allclose(action, np.asarray([0.0, 1.0, 2.0, 3.0], dtype=np.float32))
    assert adapter._model.seen_graph_keys == {
        "node_features",
        "node_mask",
        "edge_indices",
        "edge_features",
        "edge_mask",
        "graph_globals",
    }


def test_act_graph_adapter_predict_requires_online_graph() -> None:
    adapter = ACTGraphAdapter.__new__(ACTGraphAdapter)
    adapter.device = torch.device("cpu")
    adapter.norm_stats = {
        "action_mean": np.zeros(4, dtype=np.float32),
        "action_std": np.ones(4, dtype=np.float32),
    }
    adapter.temporal_agg = False
    adapter._camera_names = ["fpv"]
    adapter._low_dim_keys = ["qpos"]
    adapter._image_mask_config = {}
    adapter._num_queries = 1
    adapter._t = 0
    adapter._cached_actions = None
    adapter._normalize = torch.nn.Identity()
    adapter._proprio_mean = torch.zeros(4)
    adapter._proprio_std = torch.ones(4)
    adapter._model = _DummyACTGraphModel(num_queries=1, action_dim=4)

    import pytest

    with pytest.raises(ValueError, match="missing graph observation"):
        adapter.predict(
            {
                "qpos": np.zeros(4, dtype=np.float32),
                "image_fpv": np.zeros((3, 8, 8), dtype=np.float32),
            }
        )


def test_eval_builder_supports_act_graph(monkeypatch, tmp_path: Path) -> None:
    from testbed.runtime import _eval

    calls = {}

    class FakeACTGraphAdapter:
        @classmethod
        def from_checkpoint(cls, **kwargs):
            calls.update(kwargs)
            return "policy"

    monkeypatch.setattr(
        "testbed.policies.act_graph.adapter.ACTGraphAdapter",
        FakeACTGraphAdapter,
    )

    policy = _eval._build_act_graph_eval_policy(
        config={"train": {"lr": 2e-5}},
        ckpt_path=tmp_path / "policy_best.ckpt",
        ckpt_dir=tmp_path,
        camera_names=["fpv"],
        equipment_model="agxunity",
        max_episode_len=1200,
        low_dim_keys=["qpos", "qvel"],
        temporal_agg=False,
        device="cpu",
        act_params={"chunk_size": 7, "hidden_dim": 32, "dim_feedforward": 64},
        graph_params={"embedding_dim": 12, "message_passing_steps": 2},
        image_mask_config={},
    )

    assert policy == "policy"
    assert calls["policy_config"]["state_dim"] == 20
    assert calls["policy_config"]["graph_params"]["embedding_dim"] == 12
    assert calls["policy_config"]["num_queries"] == 7


def _write_graph_episode(path: Path, *, length: int) -> None:
    graph = {
        "node_features": np.ones((length, 6, 8), dtype=np.float32),
        "node_mask": np.asarray([[1, 1, 1, 0, 0, 0]] * length, dtype=np.uint8),
        "edge_indices": np.zeros((length, 10, 2), dtype=np.int64),
        "edge_features": np.ones((length, 10, 5), dtype=np.float32),
        "edge_mask": np.asarray([[1, 1, 0, 0, 0, 0, 0, 0, 0, 0]] * length, dtype=np.uint8),
        "graph_globals": np.zeros((length, 6), dtype=np.float32),
    }
    write_episode(
        path,
        qpos=np.arange(length * 4, dtype=np.float32).reshape(length, 4),
        qvel=np.ones((length, 4), dtype=np.float32),
        actions=np.zeros((length, 4), dtype=np.float32),
        images={"fpv": np.zeros((length, 8, 8, 3), dtype=np.uint8)},
        observation_graph=graph,
    )


def _norm_stats() -> dict:
    return {
        "action_mean": np.zeros(4, dtype=np.float32),
        "action_std": np.ones(4, dtype=np.float32),
        "proprio_mean": np.zeros(8, dtype=np.float32),
        "proprio_std": np.ones(8, dtype=np.float32),
        "proprio_dim": 8,
    }


def _online_graph() -> dict:
    return {
        "node_features": np.ones((4, 8), dtype=np.float32),
        "node_mask": np.ones(4, dtype=np.uint8),
        "edge_indices": np.asarray([[0, 1], [1, 2]], dtype=np.int64),
        "edge_features": np.ones((2, 5), dtype=np.float32),
        "edge_mask": np.ones(2, dtype=np.uint8),
        "graph_globals": np.zeros(6, dtype=np.float32),
    }


class _DummyACTGraphModel(torch.nn.Module):
    def __init__(self, *, num_queries: int, action_dim: int):
        super().__init__()
        self.num_queries = int(num_queries)
        self.action_dim = int(action_dim)
        self.seen_graph_keys: set[str] = set()

    def forward(self, proprio, image, env_state, graph, actions=None, is_pad=None):
        self.seen_graph_keys = set(graph)
        base = torch.arange(self.num_queries * self.action_dim, dtype=torch.float32)
        return (
            base.reshape(1, self.num_queries, self.action_dim),
            None,
            [None, None],
        )
