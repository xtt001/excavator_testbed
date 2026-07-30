from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parents[1] / "testbed" / "configs"
CONFIG_NAMES = {
    "dig": "act_yulong_strict_replay18_four_camera_dig_qvel.yaml",
    "carry": "act_yulong_strict_replay18_four_camera_carry_qvel.yaml",
    "dump": "act_yulong_strict_replay18_four_camera_dump_qvel.yaml",
    "return": "act_yulong_strict_replay18_four_camera_return_envelope_qvel.yaml",
}
CAMERAS = ["stick_up", "stick_down", "eye_left", "eye_right"]
EPISODE_LENGTHS = {"dig": 1730, "carry": 298, "dump": 176, "return": 1743}
RUN_ROOT = "/data/pingfan/excavator_testbed_data/yulong_strict18_terrain_residual_v0"
CKPT_ROOT = (
    "/data/pingfan/excavator_testbed_runs/ckpts/yulong_strict18_terrain_residual_v0"
)


def test_strict_replay_act_configs_lock_data_split_and_fresh_training() -> None:
    for primitive_name, config_name in CONFIG_NAMES.items():
        config = yaml.safe_load((CONFIG_DIR / config_name).read_text(encoding="utf-8"))
        assert config["task"]["camera_names"] == CAMERAS
        assert config["task"]["episode_len"] == EPISODE_LENGTHS[primitive_name]
        assert config["task"]["dataset_dir"] == (
            f"{RUN_ROOT}/primitives_copy/{primitive_name}"
        )
        assert config["task"]["dataset_dir"].endswith(f"/{primitive_name}")
        assert config["train"]["split_path"] == (
            f"{RUN_ROOT}/splits/{primitive_name}_source_split.yaml"
        )
        assert config["train"]["reuse_split"] is True
        assert config["train"]["action_loss_mask_scope"] == "loss_sampling_stats"
        assert config["train"]["batch_size"] == 4
        assert config["train"]["num_epochs"] == 500
        assert config["train"]["metadata_filters"] == {"training_tier": "gold"}
        assert config["train"]["keep_only_best_ckpt"] is True
        assert config["train"]["ckpt_dir"] == (
            f"{CKPT_ROOT}/{primitive_name}"
        )
        assert "resume_ckpt" not in config["train"]


def test_strict_replay_act_configs_keep_primitive_conditioning_contracts() -> None:
    configs = {
        primitive_name: yaml.safe_load(
            (CONFIG_DIR / config_name).read_text(encoding="utf-8")
        )
        for primitive_name, config_name in CONFIG_NAMES.items()
    }
    assert configs["dig"]["policy"]["low_dim_keys"] == [
        "qpos",
        "qvel",
        "dig_cut_tokens",
    ]
    assert configs["carry"]["policy"]["low_dim_keys"] == ["qpos", "qvel"]
    assert configs["dump"]["policy"]["low_dim_keys"] == ["qpos", "qvel"]
    assert configs["return"]["policy"]["low_dim_keys"] == [
        "qpos",
        "qvel",
        "return_start_envelope_tokens_v1",
    ]
