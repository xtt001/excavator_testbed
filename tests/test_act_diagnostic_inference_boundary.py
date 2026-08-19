"""Regression coverage for diagnostic use of the public ACT inference API."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

from testbed.cli import audit_dig_ckpt, audit_return_ckpt
from testbed.policies.act.inference import ACTActionChunk


class _ChunkOnlyPolicy:
    """Minimal policy that deliberately exposes no adapter implementation state."""

    def __init__(self) -> None:
        self.chunk_calls = 0
        self.reset_calls = 0

    def predict_with_outcome(
        self,
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray]:
        return (
            np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
            np.asarray([0.5, 0.25], dtype=np.float32),
        )

    def predict(self, _obs: dict[str, np.ndarray]) -> np.ndarray:
        return np.asarray([4.0, 3.0, 2.0, 1.0], dtype=np.float32)

    def predict_action_chunk(
        self,
        _obs: dict[str, np.ndarray],
    ) -> ACTActionChunk:
        self.chunk_calls += 1
        return ACTActionChunk(
            actions=np.asarray(
                [[10.0, 20.0, 30.0, 40.0], [11.0, 21.0, 31.0, 41.0]],
                dtype=np.float32,
            ),
            outcome=np.asarray([0.75, 0.5], dtype=np.float32),
        )

    def reset(self) -> None:
        self.reset_calls += 1


def _write_dig_episode(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.create_dataset(
            "action",
            data=np.zeros((2, 4), dtype=np.float32),
        )
        handle.create_dataset(
            "observations/qpos",
            data=np.zeros((2, 4), dtype=np.float32),
        )
        handle.create_dataset(
            "observations/images/fpv",
            data=np.zeros((2, 2, 2, 3), dtype=np.uint8),
        )
        handle.create_dataset(
            "v2/step/dig_cut_tokens",
            data=np.zeros((2, 10), dtype=np.float32),
        )


def test_dig_chunk_audit_uses_public_chunk_api(tmp_path: Path) -> None:
    episode_path = tmp_path / "episode_7.hdf5"
    _write_dig_episode(episode_path)
    policy = _ChunkOnlyPolicy()

    payload = audit_dig_ckpt._audit_episode(
        episode_path=episode_path,
        policy=policy,
        camera_names=["fpv"],
        low_dim_keys=["qpos", "dig_cut_tokens"],
        max_steps=2,
        chunk_start_steps=[0],
    )

    assert policy.chunk_calls == 1
    assert policy.reset_calls == 1
    assert payload["chunk_records"][0]["pred_action"]["mean"] == [
        10.5,
        20.5,
        30.5,
        40.5,
    ]
    assert payload["chunk_records"][0]["outcome"] == [0.75, 0.5]


@pytest.mark.parametrize(
    ("loader", "uses_explicit_checkpoint_dir"),
    [
        (audit_dig_ckpt._load_policy, False),
        (audit_return_ckpt._load_policy, True),
    ],
)
def test_checkpoint_audits_delegate_loading_to_shared_inference_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loader: Any,
    uses_explicit_checkpoint_dir: bool,
) -> None:
    module = audit_return_ckpt if uses_explicit_checkpoint_dir else audit_dig_ckpt
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_build(**kwargs: Any) -> dict[str, Any]:
        captured["build"] = kwargs
        return {"shared": True}

    def fake_load(**kwargs: Any) -> object:
        captured["load"] = kwargs
        return sentinel

    monkeypatch.setattr(module, "build_act_adapter_config", fake_build)
    monkeypatch.setattr(module, "load_act_policy", fake_load)
    checkpoint = tmp_path / "policy_best.ckpt"
    kwargs: dict[str, Any] = {
        "config": {
            "train": {"lr": 2.0e-5},
            "task": {"equipment_model": "yulong", "episode_len": 321},
            "policy": {
                "act_params": {"chunk_size": 16},
                "outcome_head": {"enabled": True, "dim": 10},
                "image_mask": {"fpv": {"enabled": False}},
            },
        },
        "ckpt_path": checkpoint,
        "camera_names": ["fpv"],
        "low_dim_keys": ["qpos", "qvel"],
        "device": "cpu",
        "temporal_agg": True,
    }
    if uses_explicit_checkpoint_dir:
        kwargs["ckpt_dir"] = checkpoint.parent

    assert loader(**kwargs) is sentinel
    assert captured["build"]["low_dim_keys"] == ["qpos", "qvel"]
    assert captured["build"]["act_params"] == {"chunk_size": 16}
    assert captured["load"] == {
        "ckpt_path": checkpoint,
        "policy_config": {"shared": True},
        "norm_stats_path": checkpoint.parent / "dataset_stats.pkl",
        "temporal_agg": True,
        "device": "cpu",
    }


def test_diagnostic_call_sites_use_only_the_public_act_inference_boundary() -> None:
    root = Path(__file__).parents[1]
    paths = [
        root / "testbed/cli/audit_dig_ckpt.py",
        root / "testbed/cli/audit_return_ckpt.py",
        root / "testbed/cli/dig_token_sensitivity.py",
        root / "testbed/eval/act_regression_policy_replay.py",
        root / "testbed/eval/coverage_return_policy_replay.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "testbed.policies.act.inference"
            for alias in node.names
        }
        assert {"build_act_adapter_config", "load_act_policy"} <= imported

    dig_tree = ast.parse(paths[0].read_text(encoding="utf-8"))
    private_adapter_attributes = {
        node.attr
        for node in ast.walk(dig_tree)
        if isinstance(node, ast.Attribute)
    }
    assert not {
        "_build_proprio",
        "_model",
        "_normalize",
        "_unpack_model_output",
    } & private_adapter_attributes
