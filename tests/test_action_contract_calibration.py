from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.data.action_contract_calibration import (
    ACTION_AXIS_ORDER,
    ACTION_CALIBRATION_SCHEMA,
    CURRENT_EQUIVALENT_ACTION_CONTRACT,
    CURRENT_CONTROLLER_PROFILE,
    DEFAULT_CALIBRATED_OUTPUT_ROOT,
    EARLY_BOOM_TUNED_CONTROLLER_PROFILE,
    EARLY_CONTROLLER_PROFILE,
    INTERMEDIATE_CONTROLLER_PROFILE,
    build_action_calibrated_dataset,
    calibrate_actions_to_current_contract,
    controller_profile_for_episode,
)
from testbed.data.hdf5_io import write_episode


def test_controller_profiles_lock_the_four_recording_epochs() -> None:
    assert ACTION_AXIS_ORDER == ("swing", "boom", "stick", "bucket")
    assert controller_profile_for_episode(0) is EARLY_CONTROLLER_PROFILE
    assert controller_profile_for_episode(2) is EARLY_CONTROLLER_PROFILE
    assert controller_profile_for_episode(3) is EARLY_BOOM_TUNED_CONTROLLER_PROFILE
    assert controller_profile_for_episode(17) is EARLY_BOOM_TUNED_CONTROLLER_PROFILE
    assert controller_profile_for_episode(18) is INTERMEDIATE_CONTROLLER_PROFILE
    assert controller_profile_for_episode(20) is INTERMEDIATE_CONTROLLER_PROFILE
    assert controller_profile_for_episode(21) is CURRENT_CONTROLLER_PROFILE
    assert controller_profile_for_episode(35) is CURRENT_CONTROLLER_PROFILE
    with pytest.raises(ValueError, match="outside the approved episode range"):
        controller_profile_for_episode(36)


@pytest.mark.parametrize(
    ("episode_id", "expected_scale"),
    [
        (1, [0.5 / 0.7, 0.05 / 0.1, 0.05 / 0.1, 0.1 / 0.2]),
        (3, [0.5 / 0.7, 0.07 / 0.1, 0.05 / 0.1, 0.1 / 0.2]),
        (19, [0.6 / 0.7, 0.07 / 0.1, 0.07 / 0.1, 0.15 / 0.2]),
        (24, [1.0, 1.0, 1.0, 1.0]),
    ],
)
def test_action_calibration_preserves_physical_target_speed(
    episode_id: int,
    expected_scale: list[float],
) -> None:
    actions = np.asarray(
        [[-1.0, -0.5, 0.25, 1.0], [0.0, 0.2, -0.8, 0.4]],
        dtype=np.float32,
    )
    calibrated, scale = calibrate_actions_to_current_contract(
        actions,
        episode_id=episode_id,
    )
    profile = controller_profile_for_episode(episode_id)

    np.testing.assert_allclose(scale, expected_scale, rtol=0.0, atol=1.0e-7)
    np.testing.assert_allclose(
        calibrated * CURRENT_CONTROLLER_PROFILE.max_target_speed,
        actions * profile.max_target_speed,
        rtol=0.0,
        atol=1.0e-7,
    )
    assert np.max(np.abs(calibrated)) <= 1.0


def test_corrected_calibration_contract_uses_a_new_no_overwrite_root() -> None:
    assert ACTION_CALIBRATION_SCHEMA == "yulong_action_contract_calibration_v2"
    assert CURRENT_EQUIVALENT_ACTION_CONTRACT == (
        "yulong_current_equivalent_normalized_speed_v2"
    )
    assert DEFAULT_CALIBRATED_OUTPUT_ROOT.name.endswith(
        "_cycle_action_calibrated_v2"
    )


def test_action_calibration_rejects_nonfinite_or_wrong_axis_order() -> None:
    with pytest.raises(ValueError, match=r"shape \(T, 4\)"):
        calibrate_actions_to_current_contract(np.zeros((3, 3)), episode_id=1)
    actions = np.zeros((2, 4), dtype=np.float32)
    actions[0, 2] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        calibrate_actions_to_current_contract(actions, episode_id=1)


def _write_clean_episode(
    path: Path,
    *,
    actions: np.ndarray,
    qvel: np.ndarray,
    mask: np.ndarray | None = None,
) -> None:
    steps = int(actions.shape[0])
    write_episode(
        path,
        qpos=np.full((steps, 4), 0.5, dtype=np.float32),
        qvel=np.asarray(qvel, dtype=np.float32),
        actions=np.asarray(actions, dtype=np.float32),
        env_state=np.zeros((steps, 64), dtype=np.float32),
        step_ids=np.arange(steps, dtype=np.int64),
        step_ns=np.arange(steps, dtype=np.int64) * 20_000_000,
        metadata={
            "action_order": "swing_speed_cmd,boom_speed_cmd,stick_speed_cmd,bucket_speed_cmd",
            "action_semantics": "actuator_speed_cmd",
            "episode_id": path.stem,
        },
    )
    with h5py.File(path, "r+") as handle:
        step = handle.require_group("v2/step")
        step.create_dataset(
            "action_loss_mask",
            data=np.ones(steps, dtype=np.uint8) if mask is None else mask,
        )
        step.create_dataset("work_stage_id", data=np.zeros(steps, dtype=np.uint8))
        cycle = handle.require_group("v2/cycle")
        cycle.create_dataset("cycle_id", data=np.asarray([0], dtype=np.int32))
        cycle.create_dataset(
            "cleaning_act_training_eligible",
            data=np.asarray([1], dtype=np.uint8),
        )


def test_build_action_calibrated_dataset_writes_uniform_training_contract(
    tmp_path: Path,
) -> None:
    clean_root = tmp_path / "clean"
    pre_root = clean_root / "pre_fix_salvage_vds"
    post_root = clean_root / "post_fix_default_vds"
    steps = 12
    early_action = np.tile([0.7, 0.6, -0.4, 0.8], (steps, 1)).astype(np.float32)
    intermediate_action = np.tile([0.5, -0.5, 0.7, -0.6], (steps, 1)).astype(np.float32)
    post_action = np.tile([0.3, 0.2, -0.1, 0.4], (steps, 1)).astype(np.float32)
    # Leave neutral reference samples for every axis.  One legacy stick sample
    # is deliberately outside that support and must be masked locally.
    post_action[:4] = 0.0
    post_qvel = np.zeros((steps, 4), dtype=np.float32)
    pre_qvel = np.zeros((steps, 4), dtype=np.float32)
    early_action[3, 2] = 0.0
    pre_qvel[3, 2] = 0.8
    _write_clean_episode(
        pre_root / "episode_1.hdf5",
        actions=early_action,
        qvel=pre_qvel,
    )
    _write_clean_episode(
        pre_root / "episode_19.hdf5",
        actions=intermediate_action,
        qvel=np.zeros_like(intermediate_action),
    )
    _write_clean_episode(
        post_root / "episode_22.hdf5",
        actions=post_action,
        qvel=post_qvel,
    )
    output_root = tmp_path / "calibrated"

    summary = build_action_calibrated_dataset(
        clean_root=clean_root,
        output_root=output_root,
        pre_episode_ids=(1, 19),
        post_episode_ids=(22,),
        neutral_qvel_min_samples=1,
        anomaly_guard_steps=0,
    )

    mixed_root = output_root / "mixed_current_equivalent_vds"
    assert summary["status"] == "passed"
    assert summary["pre_calibrated_episode_count"] == 2
    assert summary["post_reference_episode_count"] == 1
    with h5py.File(mixed_root / "episode_1.hdf5", "r") as handle:
        expected, scale = calibrate_actions_to_current_contract(
            early_action,
            episode_id=1,
        )
        np.testing.assert_allclose(handle["action"][()], expected)
        np.testing.assert_allclose(
            handle["v2/step/action_original"][()], early_action
        )
        assert not handle["action"].is_virtual
        assert handle["observations/qpos"].is_virtual
        assert handle["v2/step/action_loss_mask"][3] == 0
        assert handle["v2/step/action_calibration_valid_mask"][3] == 0
        assert (
            handle["metadata"].attrs["action_contract"]
            == CURRENT_EQUIVALENT_ACTION_CONTRACT
        )
        np.testing.assert_allclose(
            handle["metadata"].attrs["action_calibration_scale"], scale
        )
    with h5py.File(mixed_root / "episode_22.hdf5", "r") as handle:
        np.testing.assert_array_equal(handle["action"][()], post_action)
        np.testing.assert_array_equal(
            handle["v2/step/action_original"][()], post_action
        )
        assert np.all(handle["v2/step/action_calibration_valid_mask"][()] == 1)

    manifest = json.loads((output_root / "calibration_manifest.json").read_text())
    assert [row["episode_id"] for row in manifest["episodes"]] == [1, 19, 22]
    assert manifest["episodes"][0]["source_profile"] == "early_controller"
    assert manifest["episodes"][1]["source_profile"] == "intermediate_tuning"
    assert manifest["episodes"][2]["source_profile"] == "current_controller"
    config = yaml.safe_load(
        (output_root / "training_configs/mixed_current_equivalent_data.yaml").read_text()
    )
    assert config["task"]["dataset_dir"] == str(mixed_root.resolve())
    assert config["train"]["action_loss_mask_scope"] == "loss_sampling_stats"
    assert config["train"]["metadata_filters"] == {
        "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT
    }
    assert (output_root / "calibration_acceptance_report.json").exists()


def test_action_calibrated_output_root_is_no_overwrite(tmp_path: Path) -> None:
    clean_root = tmp_path / "clean"
    output_root = tmp_path / "calibrated"
    output_root.mkdir()
    with pytest.raises(FileExistsError, match="no-overwrite"):
        build_action_calibrated_dataset(
            clean_root=clean_root,
            output_root=output_root,
            pre_episode_ids=(),
            post_episode_ids=(),
        )
