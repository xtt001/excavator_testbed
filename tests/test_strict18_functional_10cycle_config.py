from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = (
    Path(__file__).parents[1]
    / "testbed/configs/"
    "eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml"
)
ENVELOPE = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0/qc/"
    "carry_start_envelope_v1.json"
)
ENVELOPE_SHA256 = (
    "ab8e13ac8ff4565a9faf13264c96071289b8a92e3ddcf2baaced0918920b621a"
)


def test_functional_a0_config_is_independent_from_formal_freeze_gate() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    evaluation = config["eval"]
    box = config["policy"]["box_emptying"]

    assert evaluation["num_rollouts"] == 1
    assert evaluation["no_overwrite"] is True
    assert evaluation["target_cycle_gate"] is None
    assert evaluation["target_cycle_gate_terminal_hold_steps"] == 0
    assert evaluation["record_hdf5_metadata"]["validation_schema"] == (
        "act_functional_10cycle_validation_v1"
    )
    assert "/functional_10cycle_a0_wall_safe_1x10_v1/" in evaluation["results_dir"]
    assert evaluation["record_hdf5_metadata"]["temporal_variant"] == "A0"
    assert evaluation["record_hdf5_metadata"]["planner_safety_variant"] == (
        "coverage_wall_safety_v1"
    )
    assert box["enabled"] is False
    assert box["safety_enabled"] is True
    assert box["functional_cycle_gate"] == {
        "enabled": True,
        "target_cycles": 10,
        "max_bucket_mass_kg": 15.0,
    }
    assert "effect_artifact_manifest_path" not in box


def test_functional_a0_config_locks_envelope_recovery_and_temporal_contract() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    box = config["policy"]["box_emptying"]
    envelope = box["carry_start_envelope"]
    safety = box["safety"]
    act = config["policy"]["act_params"]

    assert Path(envelope["artifact_path"]) == ENVELOPE
    assert envelope["artifact_sha256"] == ENVELOPE_SHA256
    assert envelope["hold_steps"] == 3
    assert envelope["max_dig_steps"] == 500
    assert safety["hard_bottom_clearance_target_qpos"] == [
        0.513391,
        0.441393,
        0.639626,
        0.991115,
    ]
    assert safety["hard_bottom_clearance_kp"] == 2.0
    assert safety["hard_bottom_clearance_kd"] == 0.25
    assert safety["hard_bottom_clearance_action_signs"] == [
        1.0,
        -1.0,
        1.0,
        1.0,
    ]
    assert safety["hard_bottom_clearance_action_clip"] == [
        0.0,
        0.35,
        0.35,
        0.55,
    ]
    assert safety["hard_bottom_clearance_hold_steps"] == 3
    assert safety["hard_bottom_clearance_margin_m"] == 0.02
    assert safety["hard_bottom_clearance_max_steps"] == 150
    assert safety["hard_bottom_depth_increase_abort_m"] == 0.002
    assert act["temporal_agg_window"] == 100
    assert act["temporal_agg_weight_order"] == "legacy_oldest_first"
    assert act["temporal_agg_decay"] == 0.01


def test_functional_a0_wall_safety_is_the_only_new_planner_factor() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    policy = config["policy"]
    coverage = policy["dig_cut_planner"]["coverage"]
    wall_safety = coverage["wall_safety"]

    assert config["task"]["camera_names"] == [
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    ]
    assert wall_safety == {
        "enabled": True,
        "profile": "conservative_2d_worktool_swept_footprint_v1",
        "worktool_width_m": 0.70,
        "hard_clearance_m": 0.30,
        "soft_clearance_m": 0.45,
        "max_score_penalty": 1.0,
        "missing_geometry": "fail_closed",
    }
    assert policy["dig_cut_planner"]["fallback_mode"] == "raise"
    assert policy["dig_ckpt_path"].endswith(
        "/yulong_strict18_terrain_residual_v0/dig/policy_best.ckpt"
    )
    assert policy["carry_ckpt_path"].endswith(
        "/yulong_strict18_terrain_residual_v0/carry/policy_best.ckpt"
    )
    assert policy["dump_ckpt_path"].endswith(
        "/yulong_strict18_terrain_residual_v0/dump/policy_best.ckpt"
    )
    assert policy["return_ckpt_path"].endswith(
        "/yulong_strict18_terrain_residual_v0/return/policy_best.ckpt"
    )
    assert policy["switch"]["return_to_dig_start_envelope_gate_enabled"] is True
    assert policy["switch"]["return_to_dig_start_envelope_spatial_tolerance"] == 0.10
    assert policy["switch"]["return_to_dig_start_envelope_qpos_tolerance"] == 0.04
