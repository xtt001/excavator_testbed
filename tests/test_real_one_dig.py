from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.dataset import load_data
from testbed.data.real_one_dig import (
    build_real_one_dig_dataset,
    find_one_dig_window,
)
from testbed.eval.offline_imitation import (
    compute_action_metrics,
    run_offline_imitation_eval,
)


def test_find_one_dig_window_drops_go_home_tail() -> None:
    raw_action = np.zeros((12, 4), dtype=np.float32)
    raw_action[3:8, 0] = 0.2
    go_home = np.zeros((12, 4), dtype=np.float32)
    go_home[9:, 1] = 0.4

    window = find_one_dig_window(
        raw_action=raw_action,
        go_home_commanded_action=go_home,
        pre_action_context_steps=1,
        go_home_margin_steps=1,
    )

    assert window.start_index == 2
    assert window.end_index_exclusive == 8
    assert window.length == 6
    assert window.raw_first_active_index == 3
    assert window.go_home_first_active_index == 9


def test_build_real_one_dig_dataset_decodes_jpeg_and_preserves_units(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    _write_source_episode(source_dir / "episode_13.hdf5", cv2=cv2)

    results = build_real_one_dig_dataset(
        source_dir=source_dir,
        output_dir=output_dir,
        episode_ids=[13],
        pre_action_context_steps=1,
        go_home_margin_steps=1,
        overwrite=True,
    )

    assert len(results) == 1
    assert results[0].source_episode_id == 13
    assert results[0].output_episode_id == 0
    assert results[0].output_steps == 6

    out_path = output_dir / "episode_0.hdf5"
    assert out_path.exists()
    with h5py.File(out_path, "r") as f:
        assert "observations/encoded_images/fpv" not in f
        assert f["observations/images/fpv"].shape == (6, 4, 5, 3)
        assert f["action"].shape == (6, 4)
        np.testing.assert_allclose(f["action"][0], np.full(4, 2, dtype=np.float32))
        assert bool(f.attrs["sim"]) is False
        assert bool(f["metadata"].attrs["sim"]) is False
        assert bool(f.attrs["is_real"]) is True
        assert f["metadata"].attrs["qvel_units"] == "rad/s"
        assert f["metadata"].attrs["image_format"] == "raw_rgb"
        assert f["metadata"].attrs["source_image_format"] == "jpeg"
        assert f["metadata"].attrs["action_order"] == "swing,boom,stick,bucket"
        assert f["diagnostics/raw_action"].shape == (6, 4)
        assert f["timestamps/step_id"][0] == 2

    assert (output_dir / "conversion_summary.json").exists()
    assert (output_dir / "conversion_summary.csv").exists()


def test_offline_imitation_eval_writes_reports(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("matplotlib")
    source_dir = tmp_path / "source"
    window_dir = tmp_path / "windows"
    output_dir = tmp_path / "offline"
    source_dir.mkdir()
    _write_source_episode(source_dir / "episode_13.hdf5", cv2=cv2)
    build_real_one_dig_dataset(
        source_dir=source_dir,
        output_dir=window_dir,
        episode_ids=[13],
        pre_action_context_steps=1,
        go_home_margin_steps=1,
        overwrite=True,
    )

    results = run_offline_imitation_eval(
        dataset_dir=window_dir,
        output_dir=output_dir,
        policy=_QposMinusOffsetPolicy(),
        episode_ids=[0],
        action_threshold=0.05,
    )

    assert len(results) == 1
    assert results[0].steps == 6
    assert results[0].overall_mae < 1e-6
    assert (output_dir / "episode_0_overlay.mp4").exists()
    assert (output_dir / "episode_0_actions.png").exists()
    assert (output_dir / "episode_0_metrics.json").exists()
    assert (output_dir / "episode_0_actions.csv").exists()
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "summary.csv").exists()


def test_real_one_dig_loader_supports_sample_repeats(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    source_dir = tmp_path / "source"
    window_dir = tmp_path / "windows"
    source_dir.mkdir()
    _write_source_episode(source_dir / "episode_13.hdf5", cv2=cv2)
    build_real_one_dig_dataset(
        source_dir=source_dir,
        output_dir=window_dir,
        episode_ids=[13],
        pre_action_context_steps=1,
        go_home_margin_steps=1,
        overwrite=True,
    )

    train_loader, val_loader, _stats, _is_sim, split_info = load_data(
        dataset_dir=window_dir,
        num_episodes=1,
        camera_names=["fpv"],
        episode_len=6,
        batch_size_train=2,
        batch_size_val=2,
        num_workers=0,
        train_sample_repeats=3,
        val_sample_repeats=2,
        low_dim_keys=["qpos", "qvel"],
    )

    assert len(train_loader.dataset) == 3
    assert len(val_loader.dataset) == 2
    assert split_info["train_sample_repeats"] == 3
    assert split_info["val_sample_repeats"] == 2


def test_offline_imitation_eval_allows_missing_diagnostics(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("matplotlib")
    source_dir = tmp_path / "source"
    window_dir = tmp_path / "windows"
    output_dir = tmp_path / "offline"
    source_dir.mkdir()
    _write_source_episode(source_dir / "episode_13.hdf5", cv2=cv2)
    build_real_one_dig_dataset(
        source_dir=source_dir,
        output_dir=window_dir,
        episode_ids=[13],
        pre_action_context_steps=1,
        go_home_margin_steps=1,
        overwrite=True,
    )
    with h5py.File(window_dir / "episode_0.hdf5", "a") as f:
        del f["diagnostics/raw_action"]
        del f["diagnostics/commanded_action"]

    results = run_offline_imitation_eval(
        dataset_dir=window_dir,
        output_dir=output_dir,
        policy=_ZeroPolicy(),
        episode_ids=[0],
        max_steps=3,
    )

    assert results[0].steps == 3
    assert results[0].missing_diagnostics == [
        "diagnostics/raw_action",
        "diagnostics/commanded_action",
    ]
    assert (output_dir / "episode_0_actions.csv").exists()


def test_compute_action_metrics_reports_active_and_idle() -> None:
    expert = np.asarray(
        [[0.0, 0.2, 0.0, -0.3], [0.0, 0.0, 0.0, 0.0]],
        dtype=np.float32,
    )
    policy = np.asarray(
        [[0.1, 0.1, 0.0, -0.2], [0.2, 0.0, 0.0, 0.0]],
        dtype=np.float32,
    )

    metrics = compute_action_metrics(
        expert_action=expert,
        policy_action=policy,
        threshold=0.05,
    )

    assert metrics["per_axis"]["boom"]["active_steps"] == 1
    assert metrics["per_axis"]["bucket"]["sign_accuracy"] == 1.0
    assert metrics["overall"]["idle_false_motion_rate"] == 1.0


class _QposMinusOffsetPolicy:
    def reset(self) -> None:
        pass

    def predict(self, obs) -> np.ndarray:
        return np.asarray(obs["qpos"], dtype=np.float32) - 0.1


class _ZeroPolicy:
    def reset(self) -> None:
        pass

    def predict(self, _obs) -> np.ndarray:
        return np.zeros(4, dtype=np.float32)


def _write_source_episode(path: Path, *, cv2) -> None:
    t = 12
    actions = np.arange(t, dtype=np.float32).reshape(t, 1).repeat(4, axis=1)
    qpos = (actions + 0.1).astype(np.float32)
    qvel = (actions + 0.2).astype(np.float32)
    env_state = np.concatenate([qpos, qvel], axis=1)
    raw_action = np.zeros((t, 4), dtype=np.float32)
    raw_action[3:8, 0] = 0.3
    go_home = np.zeros((t, 4), dtype=np.float32)
    go_home[9:, 1] = 0.7

    jpeg_dtype = h5py.vlen_dtype(np.dtype("uint8"))
    str_dtype = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as f:
        f.attrs["is_real"] = True
        meta = f.create_group("metadata")
        meta.attrs["schema_version"] = "1.2"
        meta.attrs["episode_id"] = "episode_13"
        meta.attrs["success"] = 1
        meta.attrs["control_hz"] = 50
        meta.attrs["dt"] = 0.02
        meta.attrs["action_semantics"] = "normalized_teleop_cmd_v1"
        meta.attrs["action_order"] = "swing,boom,stick,bucket"
        meta.attrs["qpos_order"] = "swing,boom,stick,bucket"
        meta.attrs["qvel_order"] = "swing,boom,stick,bucket"
        meta.attrs["qpos_units"] = "rad"
        meta.attrs["qvel_units"] = "rad/s"
        meta.attrs["image_format"] = "jpeg"
        meta.attrs["camera_names"] = "fpv"

        obs = f.create_group("observations")
        obs.create_dataset("qpos", data=qpos)
        obs.create_dataset("qvel", data=qvel)
        obs.create_dataset("env_state", data=env_state)
        encoded = obs.create_group("encoded_images")
        ds = encoded.create_dataset("fpv", shape=(t,), dtype=jpeg_dtype)
        for idx in range(t):
            rgb = np.full((4, 5, 3), idx, dtype=np.uint8)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(".jpg", bgr)
            assert ok
            ds[idx] = np.asarray(buf, dtype=np.uint8)

        f.create_dataset("action", data=actions)
        f.create_dataset("rewards", data=np.arange(t, dtype=np.float32))
        ts = f.create_group("timestamps")
        ts.create_dataset("step_id", data=np.arange(t, dtype=np.int64))
        ts.create_dataset("step_ns", data=np.arange(t, dtype=np.int64) * 10)
        src = f.create_group("action_source")
        src.create_dataset("type", data=np.asarray(["teleop"] * t, dtype=object), dtype=str_dtype)
        src.create_dataset("id", data=np.asarray(["remote"] * t, dtype=object), dtype=str_dtype)
        diag = f.create_group("diagnostics")
        diag.create_dataset("raw_action", data=raw_action)
        diag.create_dataset("commanded_action", data=actions)
        diag.create_dataset("go_home_commanded_action", data=go_home)
        diag.create_dataset("raw_low_level_command", data=np.zeros((t, 8), dtype=np.float32))
