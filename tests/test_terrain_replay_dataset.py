from __future__ import annotations

from pathlib import Path

import cv2
import h5py
import numpy as np
import pytest

from testbed.data.action_contract_calibration import (
    CURRENT_EQUIVALENT_ACTION_CONTRACT,
)
from testbed.data.hdf5_io import write_episode
from testbed.data.terrain_replay_dataset import (
    REPLAY_CAMERA_NAMES,
    apply_source_action_overlays,
    audit_recorded_replay_episode,
    replay_camera_step_valid_mask,
    safe_remove_failed_attempt_hdf5,
    select_first_passing_attempt,
)


def _jpeg(value: int) -> np.ndarray:
    rgb = np.full((8, 10, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.reshape(-1)


def _write_replay_pair(root: Path, *, replay_env_dim: int = 89) -> tuple[Path, Path]:
    steps = 5
    actions = np.arange(steps * 4, dtype=np.float32).reshape(steps, 4) / 100.0
    source = root / "source.hdf5"
    replay = root / "replay.hdf5"
    source_v2 = {
        "step": {
            "action_original": actions * 2.0,
            "action_calibration_valid_mask": np.asarray(
                [1, 1, 0, 1, 1], dtype=np.uint8
            ),
            "action_loss_mask": np.asarray([1, 0, 1, 1, 1], dtype=np.uint8),
        }
    }
    write_episode(
        source,
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        actions=actions,
        env_state=np.zeros((steps, 64), dtype=np.float32),
        metadata={"action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT},
        v2=source_v2,
    )
    encoded = {
        camera: [_jpeg(20 + index + step) for step in range(steps)]
        for index, camera in enumerate(REPLAY_CAMERA_NAMES)
    }
    write_episode(
        replay,
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        actions=actions,
        env_state=np.zeros((steps, replay_env_dim), dtype=np.float32),
        encoded_images=encoded,
        step_ids=np.arange(100, 100 + steps, dtype=np.int64),
        metadata={
            "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
            "protocol_version": "agx-sim/v2",
            "env_state_contract_version": "agx_env_state_v2_3_89",
            "runtime_build_id": "test-build",
            "terrain_state_contract_version": "terrain_state_grid_3x2_v1",
            "terrain_volume_source": "grid_depth_integral",
            "replay_control_compatibility_profile": "recording_pre_fix_v1",
        },
    )
    return source, replay


def test_recorded_replay_audit_requires_89d_four_cameras_and_exact_actions(
    tmp_path: Path,
) -> None:
    source, replay = _write_replay_pair(tmp_path)

    result = audit_recorded_replay_episode(
        replay_path=replay,
        calibrated_source_path=source,
        expected_steps=5,
    )

    assert result["pass"] is True
    assert result["env_state_dim"] == 89
    assert result["camera_names"] == list(REPLAY_CAMERA_NAMES)

    compatible = audit_recorded_replay_episode(
        replay_path=replay,
        calibrated_source_path=source,
        expected_steps=5,
        expected_control_compatibility_profile="recording_pre_fix_v1",
    )
    assert compatible["pass"] is True

    exact_build = audit_recorded_replay_episode(
        replay_path=replay,
        calibrated_source_path=source,
        expected_steps=5,
        expected_runtime_build_id="test-build",
    )
    assert exact_build["pass"] is True

    changed_build = audit_recorded_replay_episode(
        replay_path=replay,
        calibrated_source_path=source,
        expected_steps=5,
        expected_runtime_build_id="different-build",
    )
    assert changed_build["pass"] is False
    assert "metadata_mismatch:runtime_build_id" in changed_build["errors"]

    wrong_profile = audit_recorded_replay_episode(
        replay_path=replay,
        calibrated_source_path=source,
        expected_steps=5,
        expected_control_compatibility_profile="production",
    )
    assert wrong_profile["pass"] is False
    assert (
        "metadata_mismatch:replay_control_compatibility_profile"
        in wrong_profile["errors"]
    )

    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    bad_source, bad_replay = _write_replay_pair(bad_root, replay_env_dim=64)
    bad = audit_recorded_replay_episode(
        replay_path=bad_replay,
        calibrated_source_path=bad_source,
        expected_steps=5,
    )
    assert bad["pass"] is False
    assert "env_state_dim_mismatch" in bad["errors"]


def test_source_action_overlays_only_tighten_mask(tmp_path: Path) -> None:
    source, replay = _write_replay_pair(tmp_path)
    replay_qc_mask = np.asarray([1, 1, 1, 0, 1], dtype=np.uint8)

    result = apply_source_action_overlays(
        replay_path=replay,
        calibrated_source_path=source,
        replay_qc_mask=replay_qc_mask,
    )

    assert result["valid_step_count"] == 3
    with h5py.File(replay, "r") as handle:
        np.testing.assert_array_equal(
            handle["v2/step/action_loss_mask"][()],
            np.asarray([1, 0, 1, 0, 1], dtype=np.uint8),
        )
        np.testing.assert_array_equal(
            handle["v2/step/action_original"][()],
            handle["action"][()] * 2.0,
        )


def test_partial_overlay_keeps_replay_qc_and_local_cycle_masks_separate(
    tmp_path: Path,
) -> None:
    source, replay = _write_replay_pair(tmp_path)
    replay_qc = np.asarray([1, 1, 0, 1, 1], dtype=np.uint8)
    local = np.asarray([0, 1, 1, 1, 0], dtype=np.uint8)

    result = apply_source_action_overlays(
        replay_path=replay,
        calibrated_source_path=source,
        replay_qc_mask=replay_qc,
        local_cycle_mask=local,
    )

    assert result["valid_step_count"] == 1
    with h5py.File(replay, "r") as handle:
        np.testing.assert_array_equal(
            handle["v2/step/source_action_loss_mask"][()],
            np.asarray([1, 0, 1, 1, 1], dtype=np.uint8),
        )
        np.testing.assert_array_equal(
            handle["v2/step/replay_qc_mask"][()], replay_qc
        )
        np.testing.assert_array_equal(
            handle["v2/step/local_cycle_mask"][()], local
        )
        np.testing.assert_array_equal(
            handle["v2/step/action_loss_mask"][()],
            np.asarray([0, 0, 0, 1, 0], dtype=np.uint8),
        )


def test_first_pass_selection_does_not_choose_later_higher_score() -> None:
    attempts = [
        {"attempt_id": "attempt_00", "pass": False, "score": 0.99},
        {"attempt_id": "attempt_01", "pass": True, "score": 0.5},
        {"attempt_id": "attempt_02", "pass": True, "score": 1.0},
    ]
    assert select_first_passing_attempt(attempts)["attempt_id"] == "attempt_01"


def test_camera_step_validity_masks_only_the_corrupt_jpeg_step(
    tmp_path: Path,
) -> None:
    _, replay = _write_replay_pair(tmp_path)
    with h5py.File(replay, "a") as handle:
        dataset = handle["observations/encoded_images/stick_up"]
        dataset[2] = np.asarray([0, 1, 2, 3], dtype=np.uint8)

    mask, issues = replay_camera_step_valid_mask(replay)

    np.testing.assert_array_equal(mask, np.asarray([1, 1, 0, 1, 1], dtype=np.uint8))
    assert issues == [
        {"reason": "jpeg_frame_invalid", "camera": "stick_up", "step": 2}
    ]


def test_failed_hdf5_cleanup_cannot_escape_attempt_root(tmp_path: Path) -> None:
    attempts_root = tmp_path / "attempts"
    attempts_root.mkdir()
    inside = attempts_root / "episode_1" / "attempt_00" / "episode_0.hdf5"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"generated")
    outside = tmp_path / "source.hdf5"
    outside.write_bytes(b"source")

    result = safe_remove_failed_attempt_hdf5(
        path=inside,
        attempts_root=attempts_root,
    )
    assert result["removed"] is True
    assert not inside.exists()

    with pytest.raises(ValueError, match="outside attempts root"):
        safe_remove_failed_attempt_hdf5(path=outside, attempts_root=attempts_root)
    assert outside.read_bytes() == b"source"
