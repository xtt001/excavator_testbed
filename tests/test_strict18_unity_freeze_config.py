from __future__ import annotations

import json
from pathlib import Path

import yaml

CONFIG = (
    Path(__file__).parents[1]
    / "testbed/configs/eval_yulong_strict18_four_camera_4p_10cycle_freeze.yaml"
)
ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/ckpts/"
    "yulong_strict18_terrain_residual_v0"
)
PRIOR = (
    Path(__file__).parents[1]
    / "testbed/configs/planner_priors/"
    "yulong_strict18_train_surface_depth_dig_cut_prior_v1.json"
)


def test_strict18_unity_freeze_config_locks_real_gate_contract() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert config["task"]["camera_names"] == [
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    ]
    assert config["eval"]["num_rollouts"] == 3
    assert config["eval"]["no_overwrite"] is True
    assert config["eval"]["target_cycle_gate"] == 10
    assert config["eval"]["record_hdf5"] is True
    assert "record_hdf5_dir" not in config["eval"]
    assert config["eval"]["hdf5_dir"].endswith("/results/hdf5_rollouts")
    assert config["eval"]["save_rollout_logs"] is True
    assert config["policy"]["dig_low_dim_keys"] == [
        "qpos",
        "qvel",
        "dig_cut_tokens",
    ]
    assert config["policy"]["return_low_dim_keys"] == [
        "qpos",
        "qvel",
        "return_start_envelope_tokens_v1",
    ]
    assert config["policy"]["carry_low_dim_keys"] == ["qpos", "qvel"]
    assert config["policy"]["dump_low_dim_keys"] == ["qpos", "qvel"]
    assert config["policy"]["box_emptying"]["enabled"] is False
    assert config["policy"]["box_emptying"]["safety_enabled"] is True
    envelope = config["policy"]["box_emptying"]["carry_start_envelope"]
    assert envelope["enabled"] is True
    assert envelope["hold_steps"] == 3
    assert envelope["max_dig_steps"] == 500
    assert len(envelope["artifact_sha256"]) == 64
    safety = config["policy"]["box_emptying"]["safety"]
    assert safety["hard_bottom_clearance_margin_m"] == 0.02
    assert safety["hard_bottom_clearance_max_steps"] == 150
    assert safety["hard_bottom_clearance_action_clip"][0] == 0.0
    assert safety["hard_bottom_depth_increase_abort_m"] == 0.002
    assert "functional_cycle_gate" not in config["policy"]["box_emptying"]
    assert config["policy"]["act_params"]["temporal_agg_window"] == 100
    assert config["policy"]["switch"]["dig_failed_replan_next_skill"] == "dig"
    assert Path(config["policy"]["dig_cut_planner"]["prior_path"]) == PRIOR.relative_to(
        Path(__file__).parents[1]
    )
    return_envelope = config["policy"]["dig_cut_planner"][
        "return_start_envelope"
    ]
    assert return_envelope["use_cell_prior"] is True
    assert return_envelope["min_source_count"] == 20
    assert (
        config["policy"]["switch"]["return_to_dig_max_entry_error_m"]
        == 0.65
    )

    for primitive in ("dig", "return", "carry", "dump"):
        assert Path(config["policy"][f"{primitive}_ckpt_dir"]) == ROOT / primitive
        assert (
            Path(config["policy"][f"{primitive}_ckpt_path"])
            == ROOT / primitive / "policy_best.ckpt"
        )


def test_strict18_unity_freeze_config_records_runtime_provenance() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    metadata = config["eval"]["record_hdf5_metadata"]

    assert metadata["validation_schema"] == "act_unity_closed_loop_validation_v1"
    assert metadata["unity_scene_id"].startswith(
        "Assets/AGXUnity_Excavator/AGXUnity_Excavator.unity@sha256:"
    )
    assert len(metadata["unity_source_sha256"]) == 64


def test_strict18_live_prior_uses_train_partition_only() -> None:
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))

    assert prior["source"]["source_cycle_count_used"] == 374
    assert prior["source"]["episode_selection"]["partition"] == "train"
    assert prior["return_start_envelope_source"]["source_count_used"] == 358
    assert (
        prior["return_start_envelope_source"]["episode_selection"]["partition"]
        == "train"
    )
    assert prior["return_start_envelope_source_label"] == (
        "strict18_train_return_start_envelope"
    )
    assert prior["return_start_envelope_global"]["token_median"][2:7] == [
        0.0,
        0.2,
        0.0,
        0.08,
        0.0,
    ]
