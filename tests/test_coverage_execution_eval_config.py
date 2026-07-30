from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from testbed.eval.coverage_execution_eval_config import (
    PURPOSE_BOUNDED_ONE_DIG,
    PURPOSE_FUNCTIONAL_1X10,
    PURPOSE_FUNCTIONAL_3X10,
    build_coverage_execution_eval_config,
)

ROOT = Path(__file__).parents[1]
BASE_CONFIG = (
    ROOT
    / "testbed/configs/"
    "eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml"
)
LIBRARY = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0/qc/"
    "strict_train_coverage_execution_library_v1_1.json"
)
LIBRARY_SHA256 = (
    "b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614"
)
SWEEP_LIBRARY = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0/"
    "unity_3d_worktool_sweep_v1/"
    "coverage_worktool_sweep_library_v1_1.json"
)
SWEEP_LIBRARY_SHA256 = (
    "e29be1667731f537af8b4d66f931869467dfc9a6dfc53471a0d09b07ee9fbc21"
)
POSE_LIBRARY_SHA256 = (
    "cf93063fb47b81dc2083a8fd56dc696d1f0f6911ac385c5331414653190f16a2"
)
RETURN_TRANSITION_LIBRARY = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0/qc/"
    "strict_train_coverage_return_transition_library_v1.json"
)
RETURN_TRANSITION_LIBRARY_SHA256 = (
    "65952a2932a1d1373a74b825eb4d79c24d43224ca3e2449abcd7515395ab1e86"
)


@pytest.mark.parametrize(
    ("purpose", "rollouts", "functional_enabled", "bounded_enabled"),
    [
        (PURPOSE_BOUNDED_ONE_DIG, 3, False, True),
        (PURPOSE_FUNCTIONAL_1X10, 1, True, False),
        (PURPOSE_FUNCTIONAL_3X10, 3, True, False),
    ],
)
def test_actual_tuple_eval_config_changes_only_the_execution_contract_and_gate(
    tmp_path: Path,
    purpose: str,
    rollouts: int,
    functional_enabled: bool,
    bounded_enabled: bool,
) -> None:
    output = tmp_path / purpose / "resolved_input.yaml"
    run_root = tmp_path / purpose / "run"
    config = build_coverage_execution_eval_config(
        base_config_path=BASE_CONFIG,
        output_path=output,
        run_root=run_root,
        strict_execution_library_path=LIBRARY,
        strict_execution_library_sha256=LIBRARY_SHA256,
        worktool_sweep_artifact_path=SWEEP_LIBRARY,
        worktool_sweep_artifact_sha256=SWEEP_LIBRARY_SHA256,
        worktool_sweep_pose_library_sha256=POSE_LIBRARY_SHA256,
        return_transition_artifact_path=RETURN_TRANSITION_LIBRARY,
        return_transition_artifact_sha256=(
            RETURN_TRANSITION_LIBRARY_SHA256
        ),
        purpose=purpose,
    )
    base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))

    assert config["eval"]["num_rollouts"] == rollouts
    assert config["eval"]["results_dir"] == str(run_root / "results")
    assert config["eval"]["hdf5_dir"] == str(
        run_root / "results/hdf5_rollouts"
    )
    assert config["eval"]["rollout_log_dir"] == str(
        run_root / "results/rollouts"
    )
    assert config["eval"]["record_hdf5_metadata"][
        "worktool_tracking_calibration_profile"
    ] == "episode_168_bounded_live_wall_clearance_loss_v1"
    assert config["eval"]["record_hdf5_metadata"][
        "worktool_tracking_calibration_sha256"
    ] == "1a2164c345b60fdae6c211b2152fd3d22246282615857edea6785a90283e025e"
    actual_tuple = config["policy"]["dig_cut_planner"]["coverage"][
        "actual_tuple_execution_library"
    ]
    assert actual_tuple == {
        "enabled": True,
        "path": str(LIBRARY),
        "artifact_sha256": LIBRARY_SHA256,
        "mode": "exact_k1",
        "missing_contract": "fail_closed",
        "hard_bottom_margin_m": 0.02,
        "first_plan_pose_stability": {
            "enabled": True,
            "hold_steps": 3,
            "max_step_delta_m": 0.05,
            "max_wait_steps": 30,
        },
        "worktool_sweep_3d": {
            "enabled": True,
            "profile": "unity_kinematic_convex_cover_worktool_sweep_v1",
            "hard_clearance_m": 0.24,
            "act_tracking_margin_m": 0.05,
            "pose_interpolation_bound_m": 0.01,
            "artifact_path": str(SWEEP_LIBRARY),
            "artifact_sha256": SWEEP_LIBRARY_SHA256,
            "execution_library_sha256": LIBRARY_SHA256,
            "pose_library_sha256": POSE_LIBRARY_SHA256,
            "missing_contract": "fail_closed",
        },
        "start_reachability": {
            "enabled": True,
            "profile": "strict_train_return_start_reachability_11d_v1",
            "artifact_path": str(RETURN_TRANSITION_LIBRARY),
            "artifact_sha256": RETURN_TRANSITION_LIBRARY_SHA256,
            "execution_library_sha256": LIBRARY_SHA256,
            "missing_contract": "fail_closed",
        },
    }
    box = config["policy"]["box_emptying"]
    assert box["functional_cycle_gate"]["enabled"] is functional_enabled
    assert bool(
        box.get("bounded_dig_probe_stop", {}).get("enabled", False)
    ) is bounded_enabled

    assert config["task"]["camera_names"] == base["task"]["camera_names"]
    assert config["policy"]["act_params"] == base["policy"]["act_params"]
    assert config["policy"]["switch"] == base["policy"]["switch"]
    assert (
        config["policy"]["dig_cut_planner"]["coverage"]["wall_safety"]
        == base["policy"]["dig_cut_planner"]["coverage"]["wall_safety"]
    )
    assert (
        config["policy"]["box_emptying"]["carry_start_envelope"]
        == base["policy"]["box_emptying"]["carry_start_envelope"]
    )
    assert (
        config["policy"]["box_emptying"]["safety"]
        == base["policy"]["box_emptying"]["safety"]
    )
    assert config["boundary"] == base["boundary"]
    for primitive in ("dig", "carry", "dump", "return"):
        assert config["policy"][f"{primitive}_ckpt_path"] == (
            base["policy"][f"{primitive}_ckpt_path"]
        )
    assert output.is_file()


def test_actual_tuple_eval_config_is_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "config.yaml"
    kwargs = {
        "base_config_path": BASE_CONFIG,
        "output_path": output,
        "run_root": tmp_path / "run",
        "strict_execution_library_path": LIBRARY,
        "strict_execution_library_sha256": LIBRARY_SHA256,
        "worktool_sweep_artifact_path": SWEEP_LIBRARY,
        "worktool_sweep_artifact_sha256": SWEEP_LIBRARY_SHA256,
        "worktool_sweep_pose_library_sha256": POSE_LIBRARY_SHA256,
        "return_transition_artifact_path": RETURN_TRANSITION_LIBRARY,
        "return_transition_artifact_sha256": (
            RETURN_TRANSITION_LIBRARY_SHA256
        ),
        "purpose": PURPOSE_FUNCTIONAL_1X10,
    }
    build_coverage_execution_eval_config(**kwargs)

    with pytest.raises(FileExistsError):
        build_coverage_execution_eval_config(**kwargs)
