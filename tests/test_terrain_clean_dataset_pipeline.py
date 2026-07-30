from __future__ import annotations

import json
from pathlib import Path

import cv2
import h5py
import numpy as np
import pytest
import yaml

from testbed.data.hdf5_io import write_episode
from testbed.data.schema import ENV_STATE_V2_2_DIM
from testbed.data.terrain_clean_dataset import build_terrain_clean_dataset
from testbed.data.terrain_cycle_cleaning import TerrainCycleCleaningConfig

CAMERAS = ("stick_up", "stick_down", "eye_left", "eye_right")


def _jpeg(value: int) -> np.ndarray:
    rgb = np.full((6, 8, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.reshape(-1)


def _write_raw_episode(path: Path) -> dict[str, list[bytes]]:
    steps = 6
    actions = np.full((steps, 4), 0.1, dtype=np.float32)
    qpos = np.full((steps, 4), 0.5, dtype=np.float32)
    env_state = np.zeros((steps, ENV_STATE_V2_2_DIM), dtype=np.float32)
    env_state[:, 4] = [1.5, 1.4, 1.2, 1.0, 1.0, 1.0]
    env_state[:, 7] = [0.2, 0.04, 0.03, 0.2, 0.2, 0.2]
    env_state[:, 8] = [0.0, 0.03, 0.04, 0.0, 0.0, 0.0]
    env_state[:, 0] = [0.0, 120.0, 140.0, 20.0, 15.0, 10.0]
    env_state[:, 1] = [0.0, 10.0, 20.0, 20.0, 20.0, 20.0]
    env_state[:, 3] = [0.0, 0.0, 0.0, 12.0, 12.0, 12.0]
    encoded = {
        camera: [_jpeg(20 + camera_index * 30 + step) for step in range(steps)]
        for camera_index, camera in enumerate(CAMERAS)
    }
    write_episode(
        path,
        qpos=qpos,
        qvel=np.zeros((steps, 4), dtype=np.float32),
        actions=actions,
        encoded_images=encoded,
        env_state=env_state,
        step_ids=np.arange(steps, dtype=np.int64),
        step_ns=np.arange(steps, dtype=np.int64) * 20_000_000,
        metadata={
            "scenario_id": "s0_baseline",
            "success": 1,
            "stop_reason": "target_dump_count_reached",
            "target_dump_count": 1,
            "completed_dump_count": 1,
            "env_state_contract_version": "agx_env_state_v2_2_64",
        },
    )
    return {
        camera: [np.asarray(frame, dtype=np.uint8).tobytes() for frame in frames]
        for camera, frames in encoded.items()
    }


def test_raw_to_clean_multilayer_vds_preserves_jpeg_and_masks(tmp_path: Path) -> None:
    source_root = tmp_path / "approved"
    output_root = tmp_path / "clean"
    source_path = source_root / "episode_0.hdf5"
    original_jpeg = _write_raw_episode(source_path)
    before = source_path.stat()

    summary = build_terrain_clean_dataset(
        dataset_dir=source_root,
        output_root=output_root,
        approved_root=source_root,
        expected_episode_count=1,
        qualified_dig_start_mode="contact_depth",
        cleaning_config=TerrainCycleCleaningConfig(
            qpos_jump_threshold=1.0,
            qvel_jump_threshold=10.0,
        ),
    )

    assert summary["processed_episode_ids"] == [0]
    assert summary["source_episode_count"] == 1
    assert (output_root / "labels_v2_1_vds/episode_0.hdf5").exists()
    assert (output_root / "operator_first_vds/episode_0.hdf5").exists()
    assert (output_root / "hindsight_vds/episode_0.hdf5").exists()
    clean_path = output_root / "clean_all_vds/episode_0.hdf5"
    salvage_path = output_root / "pre_fix_salvage_vds/episode_0.hdf5"
    assert clean_path.exists()
    assert salvage_path.exists()
    assert list((output_root / "post_fix_default_vds").glob("episode_*.hdf5")) == []

    with h5py.File(clean_path, "r") as handle:
        assert handle["observations/qpos"].is_virtual
        assert handle["observations/encoded_images/stick_up"].is_virtual
        assert not handle["v2/step/action_loss_mask"].is_virtual
        assert handle["v2/step/action_loss_mask"].shape == (6,)
        assert np.all(handle["v2/step/action_loss_mask"][()] == 1)
        assert "dig_outcome_targets" in handle["v2/step"]
        assert handle["metadata"].attrs["action_loss_mask_scope"] == "loss_sampling_stats"
        for camera in CAMERAS:
            actual = [bytes(frame) for frame in handle[f"observations/encoded_images/{camera}"]]
            assert actual == original_jpeg[camera]

    source_manifest = json.loads((output_root / "source_manifest.json").read_text())
    assert [entry["episode_id"] for entry in source_manifest["episodes"]] == [0]
    assert Path(source_manifest["episodes"][0]["realpath"]) == source_path.resolve()
    assert (output_root / "contamination_windows.jsonl").exists()
    eligibility = [
        json.loads(line)
        for line in (output_root / "cycle_eligibility.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(eligibility) == 1
    assert set(eligibility[0]) >= {
        "act_training_eligible",
        "effect_calibration_eligible",
        "replay_candidate",
        "review_required",
    }
    assert (output_root / "field_gap_report.json").exists()
    post_fix_training = yaml.safe_load(
        (output_root / "training_configs/post_fix_default_data.yaml").read_text()
    )
    pre_fix_training = yaml.safe_load(
        (output_root / "training_configs/pre_fix_salvage_ablation_data.yaml").read_text()
    )
    assert post_fix_training["default_enabled"] is True
    assert post_fix_training["task"]["dataset_dir"] == str(
        (output_root / "post_fix_default_vds").resolve()
    )
    assert post_fix_training["train"] == {
        "action_loss_mask_scope": "loss_sampling_stats",
        "metadata_filters": {"controller_epoch": "post_fix_candidate"},
    }
    assert pre_fix_training["default_enabled"] is False
    assert pre_fix_training["usage"] == "salvage_ablation_only"
    assert pre_fix_training["task"]["dataset_dir"] == str(
        (output_root / "pre_fix_salvage_vds").resolve()
    )
    assert pre_fix_training["train"]["metadata_filters"] == {
        "controller_epoch": "pre_fix_candidate"
    }
    assert post_fix_training["lineage_path"] != pre_fix_training["lineage_path"]
    after = source_path.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


def test_clean_dataset_root_is_strictly_no_overwrite(tmp_path: Path) -> None:
    source_root = tmp_path / "approved"
    output_root = tmp_path / "clean"
    _write_raw_episode(source_root / "episode_0.hdf5")
    output_root.mkdir()

    with pytest.raises(FileExistsError, match="no-overwrite"):
        build_terrain_clean_dataset(
            dataset_dir=source_root,
            output_root=output_root,
            approved_root=source_root,
            expected_episode_count=1,
        )
