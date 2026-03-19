from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from testbed.backends.agx.protocol import CameraDescriptor, GetInfoResponse
from testbed.cli.record_teleop import _build_episode_metadata, _validate_requested_cameras
from testbed.policies.act.adapter import ACTAdapter
from testbed.runtime._train import train_policy
from testbed.runtime._eval import eval_policy


class _FakeMetrics:
    def __init__(self) -> None:
        self.saved_json: Path | None = None

    def to_json(self, path: Path | str) -> None:
        self.saved_json = Path(path)


class RepoAAgxIntegrationTests(unittest.TestCase):
    def test_eval_policy_uses_agx_and_success_config(self) -> None:
        captured: dict[str, object] = {}
        fake_metrics = _FakeMetrics()

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                return fake_metrics

        config = {
            "agx": {
                "host": "10.0.0.2",
                "port": 6001,
                "timeout": 12.5,
            },
            "task": {
                "name": "agx_excavation_teleop",
            },
            "eval": {
                "num_rollouts": 3,
                "save_video": False,
            },
            "success": {
                "mass_thresh": 2.5,
                "hold_steps": 17,
                "env_state_idx": 3,
            },
            "policy": {
                "name": "dummy",
                "action_dim": 4,
                "mode": "random",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["eval"]["results_dir"] = tmpdir
            with (
                patch("testbed.eval.suite.EvalSuite", FakeSuite),
                patch("testbed.eval.metrics.EvalMetrics.append_to_csv") as append_csv,
            ):
                eval_policy(config)

        suite_kwargs = captured["suite_kwargs"]
        self.assertEqual(suite_kwargs["task_name"], "agx_excavation_teleop")
        self.assertEqual(suite_kwargs["agx_host"], "10.0.0.2")
        self.assertEqual(suite_kwargs["agx_port"], 6001)
        self.assertEqual(suite_kwargs["agx_timeout"], 12.5)
        self.assertEqual(suite_kwargs["mass_thresh"], 2.5)
        self.assertEqual(suite_kwargs["hold_steps"], 17)
        self.assertEqual(suite_kwargs["env_state_index"], 3)
        self.assertEqual(suite_kwargs["num_rollouts"], 3)
        self.assertFalse(suite_kwargs["save_video"])
        self.assertEqual(type(suite_kwargs["policy"]).__name__, "DummyPolicy")
        self.assertEqual(suite_kwargs["policy"].mode, "random")
        self.assertIsNotNone(fake_metrics.saved_json)
        append_csv.assert_called_once()

    def test_build_episode_metadata_uses_runtime_info_and_teleop_settings(self) -> None:
        info = GetInfoResponse(
            success=True,
            error="",
            protocol_version="agx-sim/v0",
            dt=0.02,
            control_hz=50.0,
            action_semantics="actuator_speed_cmd",
            action_order=(
                "swing_speed_cmd",
                "boom_speed_cmd",
                "stick_speed_cmd",
                "bucket_speed_cmd",
            ),
            qpos_order=(
                "swing_position_norm",
                "boom_position_norm",
                "stick_position_norm",
                "bucket_position_norm",
            ),
            qvel_order=("swing_speed", "boom_speed", "stick_speed", "bucket_speed"),
            env_state_order=("mass_in_bucket_kg",),
            camera_names=("fpv",),
            supports_reset_pose=True,
            supports_images=True,
            cameras=(
                CameraDescriptor(
                    name="fpv",
                    width=512,
                    height=288,
                    fps=50.0,
                    pixel_format="raw_rgb",
                    row_order="top_to_bottom",
                ),
            ),
            warnings=(),
        )
        metadata = _build_episode_metadata(
            info=info,
            task_cfg={"task_name": "agx_excavation_teleop", "param_version": "v0"},
            teleop_cfg={
                "joystick": {
                    "deadzone": 0.05,
                    "scale": 1.0,
                    "clip": 1.0,
                    "axis_map": [0, 1, 3, 4],
                    "invert": [False, True, False, True],
                }
            },
            input_device="joystick",
            camera_names=["fpv"],
        )

        self.assertEqual(metadata["protocol_version"], "agx-sim/v0")
        self.assertEqual(metadata["control_hz"], 50)
        self.assertEqual(metadata["dt"], 0.02)
        self.assertEqual(metadata["camera_width"], 512)
        self.assertEqual(metadata["camera_height"], 288)
        self.assertEqual(metadata["camera_fps"], 50.0)
        self.assertEqual(metadata["camera_row_order"], "top_to_bottom")
        self.assertEqual(
            metadata["qpos_order"],
            "swing_position_norm,boom_position_norm,stick_position_norm,bucket_position_norm",
        )
        np.testing.assert_allclose(metadata["deadzone"], np.full(4, 0.05, dtype=np.float32))
        np.testing.assert_allclose(metadata["scale"], np.ones(4, dtype=np.float32))
        np.testing.assert_allclose(metadata["limit"], np.ones(4, dtype=np.float32))
        np.testing.assert_array_equal(metadata["axis_map"], np.array([0, 1, 3, 4], dtype=np.int32))
        np.testing.assert_array_equal(
            metadata["invert"],
            np.array([False, True, False, True], dtype=np.bool_),
        )

    def test_validate_requested_cameras_rejects_missing_camera(self) -> None:
        with self.assertRaises(KeyError):
            _validate_requested_cameras(("fpv",), ["fpv", "side"])

    def test_eval_policy_uses_task_defaults_for_act_camera_setup(self) -> None:
        captured: dict[str, object] = {}
        fake_metrics = _FakeMetrics()

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                return fake_metrics

        class FakePolicy:
            def reset(self) -> None:
                pass

        def _fake_from_checkpoint(**kwargs):
            captured["policy_kwargs"] = kwargs
            return FakePolicy()

        config = {
            "task": {
                "name": "agx_excavation_teleop",
            },
            "eval": {
                "save_video": False,
                "results_dir": None,
            },
            "policy": {
                "name": "act",
                "ckpt_path": "/tmp/fake.ckpt",
                "device": "cpu",
            },
            "train": {
                "ckpt_dir": "/tmp/fake_ckpts",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["eval"]["results_dir"] = tmpdir
            with (
                patch("testbed.eval.suite.EvalSuite", FakeSuite),
                patch("testbed.eval.metrics.EvalMetrics.append_to_csv"),
                patch(
                    "testbed.policies.act.adapter.ACTAdapter.from_checkpoint",
                    side_effect=_fake_from_checkpoint,
                ),
            ):
                eval_policy(config)

        policy_kwargs = captured["policy_kwargs"]
        self.assertEqual(policy_kwargs["policy_config"]["camera_names"], ["fpv"])
        self.assertEqual(policy_kwargs["policy_config"]["equipment_model"], "agxunity")
        self.assertEqual(policy_kwargs["policy_config"]["max_episode_len"], 500)

    def test_train_policy_accepts_policy_name_and_propagates_device(self) -> None:
        captured: dict[str, object] = {}

        class FakeTrainer:
            def __init__(self, policy_config, config) -> None:
                captured["policy_config"] = policy_config
                captured["config"] = config

            def fit(self, train_loader, val_loader, config):
                captured["fit_config"] = config
                return 0, 0.0, {}

        config = {
            "task": {
                "name": "agx_excavation_teleop",
                "dataset_dir": None,
                "num_episodes": 2,
                "camera_names": ["fpv"],
                "equipment_model": "agxunity",
            },
            "policy": {
                "name": "act",
                "device": "cpu",
                "act_params": {
                    "chunk_size": 32,
                },
            },
            "train": {
                "num_epochs": 1,
                "device": "cpu",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["task"]["dataset_dir"] = tmpdir
            config["train"]["ckpt_dir"] = tmpdir
            with (
                patch("testbed.data.dataset.get_norm_stats", return_value={"qpos_mean": np.zeros(4)}),
                patch(
                    "testbed.data.dataset.load_data",
                    return_value=("train_loader", "val_loader", {}, True),
                ),
                patch("testbed.policies.act.trainer.ACTTrainer", FakeTrainer),
            ):
                train_policy(config)

        self.assertEqual(captured["config"]["device"], "cpu")
        self.assertEqual(captured["policy_config"]["num_queries"], 32)
        self.assertEqual(captured["fit_config"]["device"], "cpu")

    def test_act_temporal_aggregation_grows_past_400_steps(self) -> None:
        adapter = object.__new__(ACTAdapter)
        adapter.device = torch.device("cpu")
        adapter._num_queries = 2
        adapter._t = 400
        adapter._all_time_actions = None
        adapter._max_episode_len = 400

        action = ACTAdapter._aggregate(
            adapter,
            torch.ones((1, 2, 4), dtype=torch.float32),
        )

        self.assertEqual(action.shape, (4,))
        self.assertGreaterEqual(adapter._all_time_actions.shape[0], 402)


if __name__ == "__main__":
    unittest.main()
