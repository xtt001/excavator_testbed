from __future__ import annotations

import pickle
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np
import pytest
import torch

from testbed.contracts.low_dim import (
    LOW_DIM_CONTRACT_VERSION,
    SUPPORTED_LOW_DIM_KEYS as CONTRACT_SUPPORTED_LOW_DIM_KEYS,
    TOKEN_LOW_DIM_KEYS,
    assemble_low_dim_observation,
    low_dim_key_dim,
    normalize_low_dim_keys,
    resolve_low_dim_state_dim,
    resolve_token_slices,
    validate_checkpoint_state_dim_contract,
    validate_low_dim_stats_contract,
)
from testbed.contracts.primitive_tokens import (
    CUT_DEPTH_SEMANTIC_IDX,
    CUT_PAYLOAD_IDX,
    CUT_VALID_IDX,
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_DIM,
    RETURN_TARGET_TOKEN_KEY,
    primitive_token_dataset_path,
)
from testbed.data.dataset import (
    SUPPORTED_LOW_DIM_KEYS as DATASET_SUPPORTED_LOW_DIM_KEYS,
    get_norm_stats,
    load_data,
)
from testbed.data.hdf5_io import write_episode
from testbed.policies.act.adapter import ACTAdapter
from testbed.runtime._eval import (
    _resolve_low_dim_state_dim as resolve_eval_low_dim_state_dim,
)
from testbed.runtime._eval import _validate_return_start_envelope_eval_low_dim
from testbed.runtime._train import (
    _resolve_low_dim_state_dim as resolve_train_low_dim_state_dim,
)


LOW_DIM_CONTRACT_KEYS = [
    "qpos",
    "qvel",
    "dig_cut_tokens",
    "dig_depth_profile_tokens_v1",
    "return_start_envelope_tokens_v1",
    "return_relocate_tokens_v1",
]
LOW_DIM_CONTRACT_DIM = (
    4
    + 4
    + DIG_CUT_TOKEN_DIM
    + DIG_DEPTH_PROFILE_TOKEN_DIM
    + RETURN_START_ENVELOPE_TOKEN_DIM
    + RETURN_TARGET_TOKEN_DIM
)


def test_low_dim_contract_source_of_truth_keys_dims_and_facades() -> None:
    assert LOW_DIM_CONTRACT_VERSION == "v2_4_5_low_dim_v1"
    assert tuple(DATASET_SUPPORTED_LOW_DIM_KEYS) == CONTRACT_SUPPORTED_LOW_DIM_KEYS
    assert TOKEN_LOW_DIM_KEYS == (
        "goal_tokens",
        "dig_cut_tokens",
        "dig_depth_profile_tokens_v1",
        "return_target_tokens",
        "return_relocate_tokens_v1",
        "return_start_envelope_tokens_v1",
    )

    expected_dims = {
        "qpos": 4,
        "qvel": 4,
        "goal_tokens": 10,
        "cell_entry_tokens": 10,
        "dig_cut_tokens": DIG_CUT_TOKEN_DIM,
        "dig_depth_profile_tokens_v1": DIG_DEPTH_PROFILE_TOKEN_DIM,
        "return_target_tokens": RETURN_TARGET_TOKEN_DIM,
        "return_relocate_tokens_v1": RETURN_TARGET_TOKEN_DIM,
        "return_start_envelope_tokens_v1": RETURN_START_ENVELOPE_TOKEN_DIM,
    }
    for key, expected_dim in expected_dims.items():
        assert low_dim_key_dim(key, "yulong") == expected_dim

    keys = [
        "qpos",
        "qvel",
        "dig_cut_tokens",
        "dig_depth_profile_tokens_v1",
        "return_start_envelope_tokens_v1",
    ]
    expected_total = (
        8
        + DIG_CUT_TOKEN_DIM
        + DIG_DEPTH_PROFILE_TOKEN_DIM
        + RETURN_START_ENVELOPE_TOKEN_DIM
    )
    assert resolve_low_dim_state_dim(keys, "yulong") == expected_total
    assert resolve_train_low_dim_state_dim(keys, "yulong") == expected_total
    assert resolve_eval_low_dim_state_dim(keys, "yulong") == expected_total


def test_low_dim_contract_token_slices_and_adapter_facade_match() -> None:
    low_dim_keys = [
        "qpos",
        "dig_cut_tokens",
        "qvel",
        "return_start_envelope_tokens_v1",
        "cell_entry_tokens",
    ]
    expected = (
        slice(4, 4 + DIG_CUT_TOKEN_DIM),
        slice(
            8 + DIG_CUT_TOKEN_DIM,
            8 + DIG_CUT_TOKEN_DIM + RETURN_START_ENVELOPE_TOKEN_DIM,
        ),
    )

    assert resolve_token_slices(low_dim_keys, "yulong") == expected

    adapter = object.__new__(ACTAdapter)
    adapter.policy_config = {"equipment_model": "yulong"}
    adapter._low_dim_keys = list(low_dim_keys)
    assert adapter._resolve_goal_token_slice() == expected


def test_low_dim_contract_token_slices_keep_return_tokens_separate() -> None:
    low_dim_keys = [
        "qpos",
        RETURN_START_ENVELOPE_TOKEN_KEY,
        "qvel",
        RETURN_RELOCATE_TOKEN_KEY,
    ]
    expected = (
        slice(4, 4 + RETURN_START_ENVELOPE_TOKEN_DIM),
        slice(
            8 + RETURN_START_ENVELOPE_TOKEN_DIM,
            8 + RETURN_START_ENVELOPE_TOKEN_DIM + RETURN_TARGET_TOKEN_DIM,
        ),
    )

    assert resolve_token_slices(low_dim_keys, "yulong") == expected


def test_low_dim_contract_preserves_unknown_key_exception_types() -> None:
    adapter = object.__new__(ACTAdapter)
    adapter.policy_config = {"equipment_model": "yulong"}

    with pytest.raises(ValueError):
        normalize_low_dim_keys(["unknown_tokens"])
    with pytest.raises(KeyError):
        resolve_low_dim_state_dim(["qpos", "unknown_tokens"], "yulong")
    with pytest.raises(KeyError):
        resolve_train_low_dim_state_dim(["qpos", "unknown_tokens"], "yulong")
    with pytest.raises(KeyError):
        resolve_eval_low_dim_state_dim(["qpos", "unknown_tokens"], "yulong")
    with pytest.raises(ValueError):
        adapter._low_dim_key_dim("unknown_tokens")


def test_low_dim_contract_assembles_values_in_configured_order() -> None:
    values = {
        "qpos": np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
        "qvel": np.array([5.0, 6.0, 7.0, 8.0], dtype=np.float32),
        "dig_cut_tokens": np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32),
    }

    assembled = assemble_low_dim_observation(
        values,
        ["qvel", "dig_cut_tokens", "qpos"],
    )

    np.testing.assert_array_equal(
        assembled,
        np.concatenate(
            [values["qvel"], values["dig_cut_tokens"], values["qpos"]],
            axis=0,
        ),
    )


def test_low_dim_contract_validates_stats_and_checkpoint_directly() -> None:
    policy_config = _policy_config(["qpos", "qvel"], state_dim=8)
    stats = {
        "proprio_mean": np.zeros(8, dtype=np.float32),
        "proprio_std": np.ones(8, dtype=np.float32),
        "proprio_dim": 8,
        "proprio_keys": np.asarray(["qpos", "qvel"], dtype=object),
    }

    validate_low_dim_stats_contract(policy_config, stats)
    validate_checkpoint_state_dim_contract(
        {"config": {"state_dim": 8}},
        policy_config,
    )

    with pytest.raises(ValueError, match="Checkpoint state_dim"):
        validate_checkpoint_state_dim_contract(
            {"config": {"state_dim": 20}},
            policy_config,
        )


def test_low_dim_contract_spans_stats_loader_and_adapter(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    episode_path = dataset_dir / "episode_0.hdf5"
    _write_contract_episode(episode_path)

    stats = get_norm_stats(
        dataset_dir,
        num_episodes=1,
        low_dim_keys=LOW_DIM_CONTRACT_KEYS,
    )
    assert int(stats["proprio_dim"]) == LOW_DIM_CONTRACT_DIM
    assert list(stats["proprio_keys"]) == LOW_DIM_CONTRACT_KEYS
    assert stats["example_proprio"].shape == (6, LOW_DIM_CONTRACT_DIM)

    train_loader, _, loader_stats, _, split_info = load_data(
        dataset_dir=dataset_dir,
        num_episodes=1,
        camera_names=["fpv"],
        episode_len=6,
        batch_size_train=1,
        batch_size_val=1,
        num_workers=0,
        pin_memory=False,
        low_dim_keys=LOW_DIM_CONTRACT_KEYS,
    )
    image, proprio, action, is_pad = next(iter(train_loader))
    assert image.shape == (1, 1, 3, 4, 4)
    assert proprio.shape == (1, LOW_DIM_CONTRACT_DIM)
    assert action.shape == (1, 6, 4)
    assert is_pad.shape == (1, 6)
    assert int(loader_stats["proprio_dim"]) == LOW_DIM_CONTRACT_DIM
    assert split_info["low_dim_keys"] == LOW_DIM_CONTRACT_KEYS
    assert split_info["low_dim_dim"] == LOW_DIM_CONTRACT_DIM

    adapter = object.__new__(ACTAdapter)
    adapter.device = torch.device("cpu")
    adapter.policy_config = {
        "equipment_model": "yulong",
        "state_dim": LOW_DIM_CONTRACT_DIM,
    }
    adapter.norm_stats = stats
    adapter._low_dim_keys = list(LOW_DIM_CONTRACT_KEYS)
    obs = _read_contract_obs(episode_path, step=0)
    assembled = adapter._build_proprio(obs)
    assert tuple(assembled.shape) == (1, LOW_DIM_CONTRACT_DIM)


def test_token_source_of_truth_matches_schema_and_adapter_dims(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "dataset"
    episode_path = dataset_dir / "episode_0.hdf5"
    _write_contract_episode(episode_path)

    adapter = object.__new__(ACTAdapter)
    adapter.policy_config = {"equipment_model": "yulong"}

    cases = {
        DIG_CUT_TOKEN_KEY: (
            DIG_CUT_TOKEN_DIM,
            primitive_token_dataset_path(DIG_CUT_TOKEN_KEY),
        ),
        DIG_DEPTH_PROFILE_TOKEN_KEY: (
            DIG_DEPTH_PROFILE_TOKEN_DIM,
            primitive_token_dataset_path(DIG_DEPTH_PROFILE_TOKEN_KEY),
        ),
        RETURN_TARGET_TOKEN_KEY: (
            RETURN_TARGET_TOKEN_DIM,
            primitive_token_dataset_path(RETURN_TARGET_TOKEN_KEY),
        ),
        RETURN_START_ENVELOPE_TOKEN_KEY: (
            RETURN_START_ENVELOPE_TOKEN_DIM,
            primitive_token_dataset_path(RETURN_START_ENVELOPE_TOKEN_KEY),
        ),
    }

    with h5py.File(episode_path, "r") as handle:
        for key, (dim, dataset_path) in cases.items():
            assert key in CONTRACT_SUPPORTED_LOW_DIM_KEYS
            assert adapter._low_dim_key_dim(key) == dim
            assert handle[dataset_path].shape[-1] == dim
            assert int(handle["metadata"].attrs[f"{key}_dim"]) == dim


def test_return_relocate_low_dim_is_derived_without_stored_dataset(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "dataset"
    _write_contract_episode(dataset_dir / "episode_0.hdf5")

    stats = get_norm_stats(
        dataset_dir,
        num_episodes=1,
        low_dim_keys=["qpos", "return_relocate_tokens_v1"],
    )

    relocate = stats["example_proprio"][:, 4:]
    assert relocate.shape == (6, RETURN_TARGET_TOKEN_DIM)
    np.testing.assert_allclose(relocate[:, CUT_DEPTH_SEMANTIC_IDX], 0.0)
    np.testing.assert_allclose(relocate[:, CUT_PAYLOAD_IDX], 0.0)
    np.testing.assert_allclose(relocate[:, CUT_VALID_IDX], 1.0)


def test_from_checkpoint_rejects_checkpoint_state_dim_mismatch(
    tmp_path: Path,
) -> None:
    ckpt_path = tmp_path / "policy_best.ckpt"
    stats_path = tmp_path / "dataset_stats.pkl"
    _write_checkpoint(ckpt_path, state_dim=20)
    _write_stats(stats_path, dim=20, low_dim_keys=["qpos", "qvel", "dig_depth_profile_tokens_v1"])

    with pytest.raises(ValueError, match="Checkpoint state_dim"):
        ACTAdapter.from_checkpoint(
            ckpt_path=ckpt_path,
            policy_config=_policy_config(
                ["qpos", "qvel", "dig_depth_profile_tokens_v1"],
                state_dim=30,
            ),
            norm_stats_path=stats_path,
            device="cpu",
        )


def test_from_checkpoint_rejects_norm_stats_dim_mismatch(
    tmp_path: Path,
) -> None:
    ckpt_path = tmp_path / "policy_best.ckpt"
    stats_path = tmp_path / "dataset_stats.pkl"
    _write_checkpoint(ckpt_path, state_dim=20)
    _write_stats(
        stats_path,
        dim=30,
        low_dim_keys=["qpos", "qvel", "dig_depth_profile_tokens_v1"],
        proprio_dim=20,
    )

    with patch(
        "testbed.policies.act.detr.main.build_ACT_model_and_optimizer",
        side_effect=_tiny_builder,
    ):
        with pytest.raises(ValueError, match="proprio_mean/proprio_std"):
            ACTAdapter.from_checkpoint(
                ckpt_path=ckpt_path,
                policy_config=_policy_config(
                    ["qpos", "qvel", "dig_depth_profile_tokens_v1"],
                    state_dim=20,
                ),
                norm_stats_path=stats_path,
                device="cpu",
            )


def test_from_checkpoint_keeps_legacy_qpos_only_stats_explicit(
    tmp_path: Path,
) -> None:
    ckpt_path = tmp_path / "policy_best.ckpt"
    stats_path = tmp_path / "dataset_stats.pkl"
    _write_checkpoint(ckpt_path, state_dim=4)
    with open(stats_path, "wb") as handle:
        pickle.dump(
            {
                "qpos_mean": np.zeros(4, dtype=np.float32),
                "qpos_std": np.ones(4, dtype=np.float32),
                "action_mean": np.zeros(4, dtype=np.float32),
                "action_std": np.ones(4, dtype=np.float32),
            },
            handle,
        )

    with patch(
        "testbed.policies.act.detr.main.build_ACT_model_and_optimizer",
        side_effect=_tiny_builder,
    ):
        adapter = ACTAdapter.from_checkpoint(
            ckpt_path=ckpt_path,
            policy_config=_policy_config(["qpos"], state_dim=4),
            norm_stats_path=stats_path,
            device="cpu",
        )

    assert tuple(adapter._proprio_mean.shape) == (4,)
    assert adapter._low_dim_keys == ["qpos"]


def test_from_checkpoint_rejects_legacy_stats_for_composite_low_dim(
    tmp_path: Path,
) -> None:
    ckpt_path = tmp_path / "policy_best.ckpt"
    stats_path = tmp_path / "dataset_stats.pkl"
    _write_checkpoint(ckpt_path, state_dim=8)
    with open(stats_path, "wb") as handle:
        pickle.dump(
            {
                "qpos_mean": np.zeros(4, dtype=np.float32),
                "qpos_std": np.ones(4, dtype=np.float32),
                "action_mean": np.zeros(4, dtype=np.float32),
                "action_std": np.ones(4, dtype=np.float32),
            },
            handle,
        )

    with patch(
        "testbed.policies.act.detr.main.build_ACT_model_and_optimizer",
        side_effect=_tiny_builder,
    ):
        with pytest.raises(KeyError, match="proprio_mean/proprio_std"):
            ACTAdapter.from_checkpoint(
                ckpt_path=ckpt_path,
                policy_config=_policy_config(["qpos", "qvel"], state_dim=8),
                norm_stats_path=stats_path,
                device="cpu",
            )


def test_eval_config_rejects_return_envelope_gate_without_low_dim_key() -> None:
    with pytest.raises(ValueError, match="silently ignore"):
        _validate_return_start_envelope_eval_low_dim(
            policy_cfg={"return_low_dim_keys": ["qpos", "qvel"]},
            switch_cfg={"return_to_dig_start_envelope_gate_enabled": True},
            primitive_low_dim_keys=["qpos", "qvel"],
        )

    _validate_return_start_envelope_eval_low_dim(
        policy_cfg={
            "return_low_dim_keys": [
                "qpos",
                "qvel",
                "return_start_envelope_tokens_v1",
            ]
        },
        switch_cfg={"return_to_dig_start_envelope_direct_handoff_enabled": True},
        primitive_low_dim_keys=["qpos", "qvel"],
    )


class _TinyCheckpointModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(()))
        self.num_queries = 1

    def forward(self, proprio, image, env_state, actions=None, is_pad=None):
        batch = proprio.shape[0]
        action = torch.zeros(batch, 1, 4, device=proprio.device)
        pad = torch.zeros(batch, 1, 1, device=proprio.device)
        mu = torch.zeros(batch, 1, device=proprio.device)
        logvar = torch.zeros(batch, 1, device=proprio.device)
        return action, pad, [mu, logvar]


def _tiny_builder(_policy_config: dict):
    model = _TinyCheckpointModel()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.0)
    return model, optimizer


def _policy_config(low_dim_keys: list[str], *, state_dim: int) -> dict:
    return {
        "camera_names": ["fpv"],
        "equipment_model": "yulong",
        "low_dim_keys": list(low_dim_keys),
        "state_dim": int(state_dim),
        "num_queries": 1,
    }


def _write_checkpoint(path: Path, *, state_dim: int) -> None:
    model = _TinyCheckpointModel()
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": {"state_dim": int(state_dim)},
        },
        path,
    )


def _write_stats(
    path: Path,
    *,
    dim: int,
    low_dim_keys: list[str],
    proprio_dim: int | None = None,
) -> None:
    with open(path, "wb") as handle:
        pickle.dump(
            {
                "proprio_mean": np.zeros(dim, dtype=np.float32),
                "proprio_std": np.ones(dim, dtype=np.float32),
                "proprio_dim": int(dim if proprio_dim is None else proprio_dim),
                "proprio_keys": np.asarray(low_dim_keys, dtype=object),
                "action_mean": np.zeros(4, dtype=np.float32),
                "action_std": np.ones(4, dtype=np.float32),
            },
            handle,
        )


def _write_contract_episode(path: Path) -> None:
    n_steps = 6
    qpos = np.arange(n_steps * 4, dtype=np.float32).reshape(n_steps, 4) / 100.0
    qvel = qpos + 0.5
    actions = np.zeros((n_steps, 4), dtype=np.float32)
    images = {"fpv": np.zeros((n_steps, 4, 4, 3), dtype=np.uint8)}

    dig_cut_tokens = np.zeros((n_steps, DIG_CUT_TOKEN_DIM), dtype=np.float32)
    dig_cut_tokens[:, 0] = 0.2
    dig_cut_tokens[:, CUT_DEPTH_SEMANTIC_IDX] = 0.4
    dig_cut_tokens[:, CUT_PAYLOAD_IDX] = 0.6
    dig_cut_tokens[:, CUT_VALID_IDX] = 1.0

    depth_profile_tokens = np.zeros(
        (n_steps, DIG_DEPTH_PROFILE_TOKEN_DIM),
        dtype=np.float32,
    )
    depth_profile_tokens[:, 0] = 0.1
    depth_profile_tokens[:, -1] = 1.0

    return_target_tokens = np.zeros(
        (n_steps, RETURN_TARGET_TOKEN_DIM),
        dtype=np.float32,
    )
    return_target_tokens[:, : RETURN_TARGET_TOKEN_DIM] = np.arange(
        RETURN_TARGET_TOKEN_DIM,
        dtype=np.float32,
    )
    return_target_tokens[:, CUT_DEPTH_SEMANTIC_IDX] = 0.7
    return_target_tokens[:, CUT_PAYLOAD_IDX] = 0.8
    return_target_tokens[:, CUT_VALID_IDX] = 1.0

    return_start_envelope_tokens = np.zeros(
        (n_steps, RETURN_START_ENVELOPE_TOKEN_DIM),
        dtype=np.float32,
    )
    return_start_envelope_tokens[:, 0] = 0.3
    return_start_envelope_tokens[:, RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    return_start_envelope_tokens[:, RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0

    write_episode(
        path,
        qpos=qpos,
        qvel=qvel,
        actions=actions,
        images=images,
        metadata={
            "dig_cut_tokens_dim": DIG_CUT_TOKEN_DIM,
            "dig_depth_profile_tokens_v1_dim": DIG_DEPTH_PROFILE_TOKEN_DIM,
            "return_target_tokens_dim": RETURN_TARGET_TOKEN_DIM,
            "return_start_envelope_tokens_v1_dim": RETURN_START_ENVELOPE_TOKEN_DIM,
        },
        v2={
            "step": {
                "dig_cut_tokens": dig_cut_tokens,
                "dig_depth_profile_tokens_v1": depth_profile_tokens,
                "return_target_tokens": return_target_tokens,
                "return_start_envelope_tokens_v1": return_start_envelope_tokens,
            }
        },
    )


def _read_contract_obs(path: Path, *, step: int) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as handle:
        return_target = np.asarray(
            handle[primitive_token_dataset_path(RETURN_TARGET_TOKEN_KEY)][step],
            dtype=np.float32,
        )
        return_relocate = return_target.copy()
        return_relocate[CUT_DEPTH_SEMANTIC_IDX] = 0.0
        return_relocate[CUT_PAYLOAD_IDX] = 0.0
        return {
            "qpos": np.asarray(handle["observations/qpos"][step], dtype=np.float32),
            "qvel": np.asarray(handle["observations/qvel"][step], dtype=np.float32),
            "dig_cut_tokens": np.asarray(
                handle[primitive_token_dataset_path(DIG_CUT_TOKEN_KEY)][step],
                dtype=np.float32,
            ),
            "dig_depth_profile_tokens_v1": np.asarray(
                handle[primitive_token_dataset_path(DIG_DEPTH_PROFILE_TOKEN_KEY)][step],
                dtype=np.float32,
            ),
            "return_start_envelope_tokens_v1": np.asarray(
                handle[primitive_token_dataset_path(RETURN_START_ENVELOPE_TOKEN_KEY)][
                    step
                ],
                dtype=np.float32,
            ),
            "return_relocate_tokens_v1": return_relocate,
        }
