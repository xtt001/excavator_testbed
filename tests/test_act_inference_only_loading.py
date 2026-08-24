from __future__ import annotations

import numpy as np
import pytest
import torch

from testbed.policies.act import inference
from testbed.policies.act.adapter import ACTAdapter


class _TinyModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1))


def test_act_model_only_builder_never_constructs_optimizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testbed.policies.act.detr import main

    model = _TinyModel()
    monkeypatch.setattr(main, "build_ACT_model", lambda _args: model)
    monkeypatch.setattr(
        torch.optim,
        "AdamW",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("optimizer constructed")
        ),
    )

    result = main.build_ACT_model_for_inference({"hidden_dim": 8})

    assert result is model


def test_adapter_inference_only_mode_has_no_optimizer_and_freezes_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testbed.policies.act.detr import main

    monkeypatch.setattr(
        main, "build_ACT_model_for_inference", lambda _cfg: _TinyModel()
    )
    policy = ACTAdapter(
        policy_config={
            "num_queries": 4,
            "camera_names": [],
            "low_dim_keys": ["qpos"],
            "equipment_model": "yulong",
        },
        norm_stats={
            "qpos_mean": np.zeros(4, dtype=np.float32),
            "qpos_std": np.ones(4, dtype=np.float32),
            "action_mean": np.zeros(4, dtype=np.float32),
            "action_std": np.ones(4, dtype=np.float32),
        },
        temporal_agg=True,
        device="cpu",
        create_optimizer=False,
    )

    assert policy._optimizer is None
    assert all(
        parameter.requires_grad is False for parameter in policy._model.parameters()
    )


def test_shared_loader_forwards_no_optimizer_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_from_checkpoint(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ACTAdapter, "from_checkpoint", fake_from_checkpoint)

    inference.load_act_policy(
        ckpt_path="checkpoint.ckpt",
        norm_stats_path="stats.pkl",
        policy_config={},
        temporal_agg=True,
        device="cpu",
        create_optimizer=False,
    )

    assert captured["create_optimizer"] is False
