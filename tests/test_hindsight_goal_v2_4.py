from __future__ import annotations

import tempfile
from pathlib import Path

import h5py
import numpy as np
import torch

from testbed.data.dataset import _read_supervision_at_step, get_norm_stats, load_data
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.hindsight_goal_v2_4 import (
    DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH,
    DEPTH_OUTCOME_SOURCE_UNAVAILABLE,
    build_hindsight_goal_dataset,
)
from testbed.data.operator_first_v2_2 import DIG_CUT_DEPTH_SCALE_M, DIG_CUT_TOKEN_DIM
from testbed.data.primitives_v2_2 import build_primitive_v2_payload
from testbed.data.schema import (
    DS_V2_STEP_RETURN_GOAL_VALID_MASK,
    DS_V2_STEP_RETURN_OUTCOME_TARGETS,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.policies.act.adapter import ACTAdapter


def test_hindsight_goal_builder_writes_add_only_targets_and_depth_delta() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        out = root / "out"
        _write_source_episode(src / "episode_0.hdf5")

        summary = build_hindsight_goal_dataset(
            dataset_dir=src,
            output_dir=out,
            overwrite=True,
        )

        assert summary["storage_mode"] == "copy"
        assert summary["episode_count"] == 1
        assert summary["cycle_count"] == 2
        with h5py.File(out / "episode_0.hdf5", "r") as handle:
            assert not handle["observations/images/fpv"].is_virtual
            assert not handle["v2/step/dig_outcome_targets"].is_virtual
            assert handle["v2/step/dig_outcome_targets"].shape == (
                8,
                DIG_CUT_TOKEN_DIM,
            )
            assert handle["v2/step/dig_goal_valid_mask"].shape == (
                8,
                DIG_CUT_TOKEN_DIM,
            )
            delta = handle["v2/cycle/actual_removed_depth_delta_grid"][()]
            assert delta.shape == (2, 6)
            assert delta[0, 3] > 0.01
            assert int(handle["v2/cycle/dominant_removed_depth_cell_id"][0]) == 3
            outcome = handle["v2/step/dig_outcome_targets"][()]
            assert np.isclose(
                outcome[0, 7],
                float(delta[0, 3]) / float(DIG_CUT_DEPTH_SCALE_M),
            )
            assert handle["v2/step/dig_goal_valid_mask"][0, -1] == 1
            assert handle["v2/step/dig_goal_valid_mask"][4, -1] == 0
            sources = [
                value.decode() if isinstance(value, bytes) else value
                for value in handle["v2/cycle/depth_outcome_source"][()]
            ]
            assert sources == [
                DEPTH_OUTCOME_SOURCE_REMOVED_DEPTH,
                DEPTH_OUTCOME_SOURCE_UNAVAILABLE,
            ]
            assert handle["metadata"].attrs["hindsight_goal_version"]


def test_hindsight_goal_builder_can_write_image_vds_relabel_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        out = root / "out"
        _write_source_episode(src / "episode_0.hdf5")

        summary = build_hindsight_goal_dataset(
            dataset_dir=src,
            output_dir=out,
            overwrite=True,
            storage_mode="vds",
        )

        assert summary["storage_mode"] == "vds"
        with h5py.File(out / "episode_0.hdf5", "r") as handle:
            assert handle["observations/images/fpv"].is_virtual
            assert handle["observations/qpos"].is_virtual
            assert handle["v2/step/dig_cut_tokens"].is_virtual
            assert not handle["v2/step/dig_outcome_targets"].is_virtual
            assert not handle["v2/cycle/actual_removed_depth_delta_grid"].is_virtual
            assert handle["metadata"].attrs["hindsight_goal_storage_mode"] == "vds"
            assert handle["metadata"].attrs["storage_mode"] == "vds"
            np.testing.assert_array_equal(
                handle["observations/images/fpv"][()],
                np.zeros((8, 4, 4, 3), dtype=np.uint8),
            )


def test_loader_supports_supervision_dict_and_gold_filter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        out = root / "out"
        _write_source_episode(src / "episode_0.hdf5", training_tiers=("gold", "gold"))
        _write_source_episode(src / "episode_1.hdf5", training_tiers=("silver", "silver"))
        build_hindsight_goal_dataset(dataset_dir=src, output_dir=out, overwrite=True)

        train_loader, _, _, _, split_info = load_data(
            dataset_dir=out,
            num_episodes=0,
            camera_names=["fpv"],
            episode_len=8,
            batch_size_train=1,
            batch_size_val=1,
            num_workers=0,
            low_dim_keys=["qpos", "qvel", "dig_cut_tokens"],
            supervision_keys=["dig_outcome_targets"],
            metadata_filters={"training_tier": "gold"},
        )
        batch = next(iter(train_loader))
        assert set(batch) >= {
            "image",
            "proprio",
            "action",
            "is_pad",
            "outcome_target",
            "outcome_mask",
        }
        assert batch["outcome_target"].shape[-1] == DIG_CUT_TOKEN_DIM
        assert split_info["available_episode_ids"] == [0]


def test_primitive_payload_preserves_hindsight_step_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        out = root / "out"
        _write_source_episode(src / "episode_0.hdf5")
        build_hindsight_goal_dataset(dataset_dir=src, output_dir=out, overwrite=True)
        episode = read_episode(out / "episode_0.hdf5", load_images=False)

        primitive_v2 = build_primitive_v2_payload(
            source_episode=episode,
            crop=slice(0, 4),
            source_cycle_id=0,
        )

        assert "dig_outcome_targets" in primitive_v2["step"]
        assert "return_outcome_targets" in primitive_v2["step"]
        assert primitive_v2["step"]["dig_outcome_targets"].shape == (
            4,
            DIG_CUT_TOKEN_DIM,
        )


def test_mini_hindsight_primitive_pipeline_preserves_low_dim_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        hindsight = root / "hindsight"
        primitive = root / "primitive"
        _write_source_episode(src / "episode_0.hdf5")
        build_hindsight_goal_dataset(
            dataset_dir=src,
            output_dir=hindsight,
            overwrite=True,
        )
        episode = read_episode(hindsight / "episode_0.hdf5")
        crop = slice(0, 4)
        primitive_v2 = build_primitive_v2_payload(
            source_episode=episode,
            crop=crop,
            source_cycle_id=0,
        )
        write_episode(
            primitive / "episode_0.hdf5",
            qpos=episode["qpos"][crop],
            qvel=episode["qvel"][crop],
            actions=episode["actions"][crop],
            images={name: frames[crop] for name, frames in episode["images"].items()},
            metadata=episode["metadata"],
            env_state=episode["env_state"][crop],
            v2=primitive_v2,
        )

        low_dim_keys = ["qpos", "qvel", "dig_cut_tokens"]
        stats = get_norm_stats(
            primitive,
            num_episodes=1,
            low_dim_keys=low_dim_keys,
        )
        train_loader, _, _, _, split_info = load_data(
            dataset_dir=primitive,
            num_episodes=1,
            camera_names=["fpv"],
            episode_len=4,
            batch_size_train=1,
            batch_size_val=1,
            num_workers=0,
            pin_memory=False,
            low_dim_keys=low_dim_keys,
        )
        image, proprio, action, is_pad = next(iter(train_loader))
        assert image.shape == (1, 1, 3, 4, 4)
        assert proprio.shape == (1, 8 + DIG_CUT_TOKEN_DIM)
        assert action.shape == (1, 4, 4)
        assert is_pad.shape == (1, 4)
        assert split_info["low_dim_keys"] == low_dim_keys
        assert split_info["low_dim_dim"] == 8 + DIG_CUT_TOKEN_DIM

        adapter = object.__new__(ACTAdapter)
        adapter.device = torch.device("cpu")
        adapter.policy_config = {
            "equipment_model": "yulong",
            "state_dim": 8 + DIG_CUT_TOKEN_DIM,
        }
        adapter.norm_stats = stats
        adapter._low_dim_keys = low_dim_keys
        with h5py.File(primitive / "episode_0.hdf5", "r") as handle:
            obs = {
                "qpos": handle["observations/qpos"][0],
                "qvel": handle["observations/qvel"][0],
                "dig_cut_tokens": handle["v2/step/dig_cut_tokens"][0],
            }
        assert tuple(adapter._build_proprio(obs).shape) == (
            1,
            8 + DIG_CUT_TOKEN_DIM,
        )


def test_act_forward_loss_accepts_outcome_supervision_and_token_swap() -> None:
    adapter = object.__new__(ACTAdapter)
    adapter.device = torch.device("cpu")
    adapter.kl_weight = 0.0
    adapter.outcome_loss_weight = 2.0
    adapter.token_swap_outcome_loss_weight = 1.0
    adapter._normalize = torch.nn.Identity()
    adapter._model = _TinyOutcomeModel(num_queries=3, action_dim=4, outcome_dim=10)
    adapter._proprio_mean = torch.zeros(18)
    adapter._proprio_std = torch.ones(18)
    adapter._token_slice = slice(8, 18)

    proprio = torch.zeros(2, 18)
    proprio[0, 8] = 0.25
    proprio[1, 8] = -0.25
    image = torch.zeros(2, 1, 3, 4, 4)
    actions = torch.zeros(2, 3, 4)
    is_pad = torch.zeros(2, 3, dtype=torch.bool)
    target = torch.zeros(2, 10)
    target[:, 0] = torch.tensor([0.25, -0.25])
    mask = torch.ones(2, 10)

    loss = adapter.forward_loss(
        proprio,
        image,
        actions,
        is_pad,
        outcome_target=target,
        outcome_mask=mask,
    )

    assert set(loss) >= {"l1", "kl", "outcome", "token_swap", "loss"}
    assert torch.isfinite(loss["loss"])


def test_act_token_swap_resolves_all_return_conditioning_tokens() -> None:
    adapter = object.__new__(ACTAdapter)
    adapter.policy_config = {"equipment_model": "yulong"}
    adapter._low_dim_keys = [
        "qpos",
        "qvel",
        "return_start_envelope_tokens_v1",
        "return_relocate_tokens_v1",
    ]

    assert adapter._resolve_goal_token_slice() == (slice(8, 26), slice(26, 36))


def test_act_token_swap_rolls_each_goal_token_slice_together() -> None:
    adapter = object.__new__(ACTAdapter)
    adapter._token_slice = (slice(2, 4), slice(6, 8))
    adapter._proprio_mean = torch.zeros(8)
    adapter._proprio_std = torch.ones(8)
    proprio = torch.tensor(
        [
            [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
            [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0],
        ]
    )

    swapped = adapter._swap_goal_token_in_batch(proprio)

    torch.testing.assert_close(swapped[:, :2], proprio[:, :2])
    torch.testing.assert_close(swapped[:, 4:6], proprio[:, 4:6])
    torch.testing.assert_close(swapped[0, 2:4], proprio[1, 2:4])
    torch.testing.assert_close(swapped[0, 6:8], proprio[1, 6:8])
    torch.testing.assert_close(swapped[1, 2:4], proprio[0, 2:4])
    torch.testing.assert_close(swapped[1, 6:8], proprio[0, 6:8])


def test_return_relocate_supervision_masks_depth_and_payload() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "episode.hdf5"
        target = np.arange(10, dtype=np.float32).reshape(1, 10)
        target[0, 9] = 1.0
        mask = np.ones((1, 10), dtype=np.uint8)
        with h5py.File(path, "w") as handle:
            handle.create_dataset(DS_V2_STEP_RETURN_OUTCOME_TARGETS, data=target)
            handle.create_dataset(DS_V2_STEP_RETURN_GOAL_VALID_MASK, data=mask)
        with h5py.File(path, "r") as handle:
            relocate_target, relocate_mask = _read_supervision_at_step(
                handle,
                key="return_relocate_outcome_targets_v1",
                index=0,
            )

    assert relocate_target[7] == 0.0
    assert relocate_target[8] == 0.0
    assert relocate_mask[7] == 0.0
    assert relocate_mask[8] == 0.0
    np.testing.assert_allclose(relocate_target[:7], target[0, :7])
    assert relocate_target[9] == 1.0


class _TinyOutcomeModel(torch.nn.Module):
    def __init__(self, *, num_queries: int, action_dim: int, outcome_dim: int):
        super().__init__()
        self.num_queries = int(num_queries)
        self.action_dim = int(action_dim)
        self.outcome_dim = int(outcome_dim)

    def forward(self, proprio, image, env_state, actions=None, is_pad=None):
        batch = proprio.shape[0]
        token = proprio[:, 8:18]
        a_hat = torch.zeros(batch, self.num_queries, self.action_dim, device=proprio.device)
        a_hat[:, :, 0] = token[:, 0:1]
        outcome = token[:, : self.outcome_dim]
        mu = torch.zeros(batch, 1, device=proprio.device)
        logvar = torch.zeros(batch, 1, device=proprio.device)
        return a_hat, torch.zeros(batch, self.num_queries, 1, device=proprio.device), [mu, logvar], outcome


def _write_source_episode(
    path: Path,
    *,
    training_tiers: tuple[str, str] = ("gold", "silver"),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_steps = 8
    qpos = np.zeros((n_steps, 4), dtype=np.float32)
    qvel = np.zeros((n_steps, 4), dtype=np.float32)
    actions = np.zeros((n_steps, 4), dtype=np.float32)
    images = {"fpv": np.zeros((n_steps, 4, 4, 3), dtype=np.uint8)}
    env_state = np.zeros((n_steps, 64), dtype=np.float32)
    start = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
    env_state[0:4, start + 3] = np.linspace(0.0, 0.02, 4)

    dig_tokens = np.zeros((n_steps, DIG_CUT_TOKEN_DIM), dtype=np.float32)
    dig_tokens[:, 0] = 0.3
    dig_tokens[:, 2] = -0.2
    dig_tokens[:, -1] = 1.0
    return_tokens = np.zeros_like(dig_tokens)
    return_tokens[0:4] = dig_tokens[4:8] = dig_tokens[0:4]

    v2 = {
        "step": {
            "cycle_id": np.asarray([0, 0, 0, 0, 1, 1, 1, 1], dtype=np.int32),
            "dig_cut_tokens": dig_tokens,
            "return_target_tokens": return_tokens,
            "action_loss_mask": np.ones((n_steps,), dtype=np.uint8),
        },
        "cycle": {
            "cycle_id": np.asarray([0, 1], dtype=np.int32),
            "start_step": np.asarray([0, 4], dtype=np.int32),
            "end_step": np.asarray([3, 7], dtype=np.int32),
            "operator_cut_payload_gain_kg": np.asarray([60.0, 55.0], dtype=np.float32),
            "cycle_effective_deposit_delta_kg": np.asarray([58.0, 50.0], dtype=np.float32),
            "return_entry_delta_norm_m": np.asarray([0.1, np.nan], dtype=np.float32),
            "return_target_source": np.asarray(
                ["operator_next_entry", "terminal_none"],
                dtype="<U20",
            ),
            "training_tier": np.asarray(training_tiers, dtype="<U8"),
        },
    }
    write_episode(
        path,
        qpos=qpos,
        qvel=qvel,
        actions=actions,
        images=images,
        metadata={"training_tier": training_tiers[0]},
        env_state=env_state,
        v2=v2,
    )
