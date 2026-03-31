from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from testbed.backends.agx.protocol import CameraDescriptor, GetInfoResponse
from testbed.cli.record_teleop import (
    _build_episode_metadata,
    _should_stop_on_success,
    _validate_requested_cameras,
)
from testbed.data.dataset import load_data
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.qc import run_dataset_qc
from testbed.data.recorder import EpisodeRecorder
from testbed.eval.suite import EvalSuite
from testbed.policies.act.adapter import ACTAdapter
from testbed.runtime.experiment_record import (
    append_experiment_registry,
    build_experiment_record,
    write_experiment_record,
)
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
                "mode": "dump_complete_final_hold",
                "signal_name": "deposited_mass_in_target_box_kg",
                "mass_thresh": 125.0,
                "hold_steps": 17,
                "residual_bucket_mass_thresh": 88.0,
                "env_state_idx": 3,
            },
            "reward": {
                "load_mass_threshold_kg": 90.0,
                "target_approach_distance_m": 1.5,
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
        self.assertEqual(suite_kwargs["mass_thresh"], 125.0)
        self.assertEqual(suite_kwargs["hold_steps"], 17)
        self.assertEqual(suite_kwargs["agx_success_mode"], "dump_complete_final_hold")
        self.assertEqual(suite_kwargs["residual_bucket_mass_thresh"], 88.0)
        self.assertEqual(
            suite_kwargs["success_signal_name"],
            "deposited_mass_in_target_box_kg",
        )
        self.assertEqual(suite_kwargs["env_state_index"], 3)
        self.assertEqual(
            suite_kwargs["reward_overrides"],
            {
                "load_mass_threshold_kg": 90.0,
                "target_approach_distance_m": 1.5,
            },
        )
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
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
            ),
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
                "metadata": {
                    "operator_id": "alice",
                    "session_id": "sess-001",
                    "notes": "baseline teleop",
                },
                "joystick": {
                    "joystick_ids": [1, 0, 1, 0],
                    "deadzone": 0.05,
                    "scale": 1.0,
                    "clip": 1.0,
                    "axis_map": [1, 2, 2, 1],
                    "invert": [False, True, True, False],
                    "response_profile": {
                        "enabled": True,
                        "attack_rate": 4.0,
                        "release_rate": 6.0,
                        "recenter_rate": 7.0,
                        "exponent": 1.0,
                    },
                }
            },
            input_device="joystick",
            camera_names=["fpv"],
            config_path=Path("/tmp/teleop_v0.yaml"),
            record_config_yaml="task:\n  task_name: agx_excavation_teleop\n",
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
        np.testing.assert_array_equal(metadata["axis_map"], np.array([1, 2, 2, 1], dtype=np.int32))
        np.testing.assert_array_equal(metadata["joystick_ids"], np.array([1, 0, 1, 0], dtype=np.int32))
        np.testing.assert_array_equal(
            metadata["invert"],
            np.array([False, True, True, False], dtype=np.bool_),
        )
        self.assertEqual(metadata["response_profile_enabled"], 1)
        self.assertEqual(metadata["operator_id"], "alice")
        self.assertEqual(metadata["session_id"], "sess-001")
        self.assertEqual(metadata["notes"], "baseline teleop")
        self.assertEqual(metadata["record_config_path"], "/tmp/teleop_v0.yaml")
        self.assertIn("task_name: agx_excavation_teleop", metadata["record_config_yaml"])
        np.testing.assert_allclose(
            metadata["response_profile_attack_rate"],
            np.full(4, 4.0, dtype=np.float32),
        )
        np.testing.assert_allclose(
            metadata["response_profile_release_rate"],
            np.full(4, 6.0, dtype=np.float32),
        )
        np.testing.assert_allclose(
            metadata["response_profile_recenter_rate"],
            np.full(4, 7.0, dtype=np.float32),
        )
        np.testing.assert_allclose(
            metadata["response_profile_exponent"],
            np.ones(4, dtype=np.float32),
        )

    def test_validate_requested_cameras_rejects_missing_camera(self) -> None:
        with self.assertRaises(KeyError):
            _validate_requested_cameras(("fpv",), ["fpv", "side"])

    def test_stop_on_success_helper_respects_flag(self) -> None:
        self.assertTrue(
            _should_stop_on_success(episode_success=True, stop_on_success=True)
        )
        self.assertFalse(
            _should_stop_on_success(episode_success=False, stop_on_success=True)
        )
        self.assertFalse(
            _should_stop_on_success(episode_success=True, stop_on_success=False)
        )

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
        self.assertEqual(policy_kwargs["policy_config"]["max_episode_len"], 1000)

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
                    return_value=("train_loader", "val_loader", {}, True, {"train_ids": [0], "val_ids": [1]}),
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

    def test_eval_suite_writes_rollout_logs_and_manifest(self) -> None:
        class FakePolicy:
            def reset(self) -> None:
                pass

            def predict(self, _obs) -> np.ndarray:
                return np.zeros(4, dtype=np.float32)

        class FakeTimeStep:
            def __init__(self, observation, reward: float, info: dict[str, object]) -> None:
                self.observation = observation
                self.reward = reward
                self.info = info

        class FakeEnv:
            dt = 0.02

            def __init__(self) -> None:
                self._index = 0

            def reset(self, seed=None):
                self._index = 0
                return FakeTimeStep(
                    observation={
                        "qpos": np.zeros(4, dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": np.zeros(9, dtype=np.float32),
                        "step_id": 0,
                        "sim_time_ns": 0,
                    },
                    reward=0.0,
                    info={},
                )

            def step(self, action):
                self._index += 1
                success = self._index >= 2
                failures = ["load_outside_dig_area"] if self._index == 1 else []
                return FakeTimeStep(
                    observation={
                        "qpos": np.full(4, self._index, dtype=np.float32),
                        "qvel": np.full(4, 0.1 * self._index, dtype=np.float32),
                        "images": {},
                        "env_state": np.full(9, self._index, dtype=np.float32),
                        "step_id": self._index,
                        "sim_time_ns": self._index * 20_000_000,
                    },
                    reward=float(self._index),
                    info={
                        "sim_time_ns": self._index * 20_000_000,
                        "reward_phase": "loading" if self._index == 1 else "depositing",
                        "task_success": success,
                        "task_step_successes": ["good_dig_start"] if self._index == 2 else [],
                        "task_step_failures": failures,
                        "task_metrics": {"mass_in_bucket_kg": float(self._index)},
                        "warnings": [],
                    },
                )

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = EvalSuite(
                policy=FakePolicy(),
                task_name="agx_excavation_teleop",
                num_rollouts=1,
                save_video=False,
                results_dir=Path(tmpdir) / "results",
                save_rollout_logs=True,
                rollout_log_dir=Path(tmpdir) / "results" / "rollouts",
            )
            suite.task_def = replace(suite.task_def, episode_len=3)
            suite._make_env = lambda _task: FakeEnv()

            metrics = suite.run()

            self.assertEqual(metrics.n_rollouts, 1)
            jsonl_path = Path(tmpdir) / "results" / "rollouts" / "rollout_000.jsonl"
            summary_path = Path(tmpdir) / "results" / "rollouts" / "rollout_000_summary.json"
            manifest_path = Path(tmpdir) / "results" / "rollout_manifest.json"
            self.assertTrue(jsonl_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(manifest_path.exists())
            with open(summary_path) as f:
                summary = json.load(f)
            self.assertIn("failure_counts", summary)
            self.assertEqual(summary["first_failure_step"], 0)
            with open(manifest_path) as f:
                manifest = json.load(f)
            self.assertEqual(manifest["n_rollouts"], 1)
            self.assertEqual(len(manifest["rollouts"]), 1)

    def test_eval_suite_prints_step_progress_at_interval(self) -> None:
        class FakePolicy:
            def reset(self) -> None:
                pass

            def predict(self, _obs) -> np.ndarray:
                return np.zeros(4, dtype=np.float32)

        class FakeTimeStep:
            def __init__(self, observation, reward: float, info: dict[str, object]) -> None:
                self.observation = observation
                self.reward = reward
                self.info = info

        class FakeEnv:
            dt = 0.02

            def __init__(self) -> None:
                self._index = 0

            def reset(self, seed=None):
                self._index = 0
                return FakeTimeStep(
                    observation={
                        "qpos": np.zeros(4, dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": np.zeros(9, dtype=np.float32),
                        "step_id": 0,
                        "sim_time_ns": 0,
                    },
                    reward=0.0,
                    info={},
                )

            def step(self, action):
                self._index += 1
                return FakeTimeStep(
                    observation={
                        "qpos": np.zeros(4, dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": np.zeros(9, dtype=np.float32),
                        "step_id": self._index,
                        "sim_time_ns": self._index * 20_000_000,
                    },
                    reward=0.0,
                    info={
                        "sim_time_ns": self._index * 20_000_000,
                        "reward_phase": "idle",
                        "task_success": False,
                        "task_step_successes": [],
                        "task_step_failures": [],
                        "task_metrics": {},
                        "warnings": [],
                    },
                )

            def close(self) -> None:
                pass

        suite = EvalSuite(
            policy=FakePolicy(),
            task_name="agx_excavation_teleop",
            num_rollouts=1,
            save_video=False,
            save_rollout_logs=False,
            step_log_interval=2,
        )
        suite.task_def = replace(suite.task_def, episode_len=5)
        suite._make_env = lambda _task: FakeEnv()

        with patch("builtins.print") as mock_print:
            suite.run()

        printed = [" ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list]
        self.assertTrue(any("rollout 000  step 2 / 5" in line for line in printed))
        self.assertTrue(any("rollout 000  step 4 / 5" in line for line in printed))
        self.assertTrue(any("rollout 000  step 5 / 5" in line for line in printed))

    def test_eval_suite_reports_agx_success_modes(self) -> None:
        class FakePolicy:
            def reset(self) -> None:
                pass

            def predict(self, _obs) -> np.ndarray:
                return np.zeros(4, dtype=np.float32)

        class FakeTimeStep:
            def __init__(self, observation, reward: float, info: dict[str, object]) -> None:
                self.observation = observation
                self.reward = reward
                self.info = info

        class FakeEnv:
            dt = 0.02

            def __init__(self) -> None:
                self._index = 0
                self._signal = [0.0, 120.0, 120.0, 0.0]

            def reset(self, seed=None):
                self._index = 0
                return FakeTimeStep(
                    observation={
                        "qpos": np.zeros(4, dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": np.array([0.0, 0.0, 0.0, self._signal[0], 0, 0, 0, 0, 0], dtype=np.float32),
                        "step_id": 0,
                        "sim_time_ns": 0,
                    },
                    reward=0.0,
                    info={},
                )

            def step(self, action):
                self._index += 1
                value = self._signal[self._index]
                return FakeTimeStep(
                    observation={
                        "qpos": np.zeros(4, dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": np.array([0.0, 0.0, 0.0, value, 0, 0, 0, 0, 0], dtype=np.float32),
                        "step_id": self._index,
                        "sim_time_ns": self._index * 20_000_000,
                    },
                    reward=1.0,
                    info={
                        "sim_time_ns": self._index * 20_000_000,
                        "reward_phase": "depositing",
                        "task_success": self._index in (1, 2),
                        "task_step_successes": [],
                        "task_step_failures": ["spill_before_target"] if self._index == 2 else [],
                        "task_metrics": {
                            "deposited_mass_in_target_box_kg": value,
                        },
                        "warnings": [],
                    },
                )

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = EvalSuite(
                policy=FakePolicy(),
                task_name="agx_excavation_teleop",
                num_rollouts=1,
                save_video=False,
                results_dir=Path(tmpdir) / "results",
                save_rollout_logs=True,
                rollout_log_dir=Path(tmpdir) / "results" / "rollouts",
                mass_thresh=100.0,
                hold_steps=2,
                env_state_index=3,
                agx_success_mode="final_hold",
                strict_max_failures={"spill_before_target": 0},
            )
            suite.task_def = replace(suite.task_def, episode_len=3)
            suite._make_env = lambda _task: FakeEnv()

            metrics = suite.run()

            self.assertEqual(metrics.n_success, 0)
            self.assertEqual(metrics.extra["success_mode"], "final_hold")
            self.assertEqual(metrics.extra["legacy_success_rate"], 1.0)
            self.assertEqual(metrics.extra["final_hold_success_rate"], 0.0)
            self.assertEqual(metrics.extra["strict_final_hold_success_rate"], 0.0)

            summary_path = Path(tmpdir) / "results" / "rollouts" / "rollout_000_summary.json"
            with open(summary_path) as f:
                summary = json.load(f)
            self.assertTrue(summary["legacy_success"])
            self.assertFalse(summary["final_hold_success"])
            self.assertFalse(summary["strict_final_hold_success"])
            self.assertEqual(summary["first_task_success_step"], 0)
            self.assertEqual(summary["first_hold_success_step"], 1)
            self.assertEqual(summary["strict_blocking_failures"], {"spill_before_target": 1})

    def test_dump_complete_success_requires_low_final_bucket_mass(self) -> None:
        class FakeEnv:
            def get_info(self):
                class Info:
                    env_state_order = (
                        "mass_in_bucket_kg",
                        "excavated_mass_kg",
                        "mass_in_target_box_kg",
                        "deposited_mass_in_target_box_kg",
                        "min_distance_to_target_m",
                        "target_hard_collision_count",
                        "target_contact_max_normal_force_n",
                        "min_distance_to_dig_area_m",
                        "bucket_depth_below_dig_area_plane_m",
                    )

                return Info()

        suite = EvalSuite(
            policy=object(),
            task_name="agx_excavation_teleop",
            save_video=False,
            save_rollout_logs=False,
            mass_thresh=300.0,
            hold_steps=2,
            agx_success_mode="dump_complete_final_hold",
            residual_bucket_mass_thresh=100.0,
        )

        env_states = [
            np.array([350.0, 0.0, 0.0, 320.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            np.array([220.0, 0.0, 0.0, 320.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            np.array([180.0, 0.0, 0.0, 320.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
        ]
        summary = suite._evaluate_agx_success(
            env=FakeEnv(),
            env_states=env_states,
            success_flags=[False, False, False],
            step_records=[],
        )

        self.assertTrue(summary["final_hold_success"])
        self.assertFalse(summary["dump_complete_final_hold_success"])
        self.assertFalse(summary["success"])
        self.assertEqual(summary["final_bucket_mass"], 180.0)
        self.assertEqual(summary["residual_bucket_mass_thresh"], 100.0)

    def test_strict_dump_complete_blocks_spill_or_collision(self) -> None:
        class FakeEnv:
            def get_info(self):
                class Info:
                    env_state_order = (
                        "mass_in_bucket_kg",
                        "excavated_mass_kg",
                        "mass_in_target_box_kg",
                        "deposited_mass_in_target_box_kg",
                        "min_distance_to_target_m",
                        "target_hard_collision_count",
                        "target_contact_max_normal_force_n",
                        "min_distance_to_dig_area_m",
                        "bucket_depth_below_dig_area_plane_m",
                    )

                return Info()

        suite = EvalSuite(
            policy=object(),
            task_name="agx_excavation_teleop",
            save_video=False,
            save_rollout_logs=False,
            mass_thresh=300.0,
            hold_steps=2,
            agx_success_mode="strict_dump_complete",
            strict_max_failures={"spill_before_target": 0, "hard_target_collision": 0},
            residual_bucket_mass_thresh=100.0,
        )

        env_states = [
            np.array([90.0, 0.0, 0.0, 320.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            np.array([80.0, 0.0, 0.0, 330.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
        ]
        step_records = [
            {"task_step_failures": []},
            {"task_step_failures": ["spill_before_target"]},
        ]
        summary = suite._evaluate_agx_success(
            env=FakeEnv(),
            env_states=env_states,
            success_flags=[False, False],
            step_records=step_records,
        )

        self.assertTrue(summary["dump_complete_final_hold_success"])
        self.assertFalse(summary["strict_dump_complete_success"])
        self.assertFalse(summary["success"])
        self.assertEqual(summary["strict_blocking_failures"], {"spill_before_target": 1})

    def test_dataset_qc_handles_legacy_episode_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "dataset"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=np.zeros((3, 4), dtype=np.float32),
                qvel=np.zeros((3, 4), dtype=np.float32),
                actions=np.zeros((3, 4), dtype=np.float32),
                images={"fpv": np.zeros((3, 8, 8, 3), dtype=np.uint8)},
                rewards=np.zeros(3, dtype=np.float32),
                metadata={"success": 1, "env_state_order": "a,b,c"},
                env_state=np.zeros((3, 3), dtype=np.float32),
                step_ids=np.array([0, 1, 2], dtype=np.int64),
                step_ns=np.array([1, 2, 3], dtype=np.int64),
            )
            write_episode(
                dataset_dir / "episode_1.hdf5",
                qpos=np.ones((2, 4), dtype=np.float32),
                qvel=np.ones((2, 4), dtype=np.float32),
                actions=np.ones((2, 4), dtype=np.float32),
                images=None,
                rewards=np.ones(2, dtype=np.float32),
                metadata={"success": 0},
            )
            (dataset_dir / "episode_2.hdf5").write_text("not a valid hdf5 file")

            result = run_dataset_qc(dataset_dir=dataset_dir)

            summary_path = Path(result["summary_path"])
            episodes_csv_path = Path(result["episodes_csv_path"])
            self.assertTrue(summary_path.exists())
            self.assertTrue(episodes_csv_path.exists())
            self.assertTrue((dataset_dir / "qc" / "episode_length_hist.png").exists())
            self.assertTrue((dataset_dir / "qc" / "action_distribution.png").exists())
            self.assertTrue((dataset_dir / "qc" / "state_ranges.png").exists())

            with open(summary_path) as f:
                summary = json.load(f)
            self.assertEqual(summary["n_episodes"], 3)
            self.assertIn("episode_1", summary["warnings"]["missing_env_state_ids"])
            self.assertIn("episode_1", summary["warnings"]["missing_image_ids"])
            self.assertIn("episode_2", summary["warnings"]["unreadable_episode_ids"])

    def test_load_data_supports_variable_length_success_truncated_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "dataset"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            lengths = [5, 7, 6]
            for episode_id, length in enumerate(lengths):
                write_episode(
                    dataset_dir / f"episode_{episode_id}.hdf5",
                    qpos=np.full((length, 4), episode_id, dtype=np.float32),
                    qvel=np.zeros((length, 4), dtype=np.float32),
                    actions=np.full((length, 4), 0.1 * (episode_id + 1), dtype=np.float32),
                    images={"fpv": np.zeros((length, 8, 8, 3), dtype=np.uint8)},
                    rewards=np.zeros(length, dtype=np.float32),
                    metadata={"success": 1},
                    env_state=np.zeros((length, 9), dtype=np.float32),
                    step_ids=np.arange(length, dtype=np.int64),
                    step_ns=np.arange(length, dtype=np.int64),
                )

            train_loader, val_loader, norm_stats, _, split_info = load_data(
                dataset_dir=dataset_dir,
                num_episodes=3,
                camera_names=["fpv"],
                episode_len=10,
                batch_size_train=2,
                batch_size_val=1,
                num_workers=0,
                prefetch_factor=1,
                persistent_workers=False,
                pin_memory=False,
                split_seed=0,
                train_split_ratio=0.67,
                reuse_split=False,
            )

            self.assertEqual(norm_stats["qpos_mean"].shape, (4,))
            self.assertEqual(norm_stats["action_mean"].shape, (4,))
            self.assertEqual(split_info["dataset_max_episode_len"], 7)
            self.assertEqual(split_info["loader_episode_len"], 10)

            image_data, qpos_data, action_data, is_pad = next(iter(train_loader))
            self.assertEqual(image_data.shape[1:], (1, 3, 8, 8))
            self.assertEqual(qpos_data.shape[1:], (4,))
            self.assertEqual(action_data.shape[1:], (10, 4))
            self.assertEqual(is_pad.shape[1:], (10,))
            self.assertGreaterEqual(len(train_loader), 1)
            self.assertGreaterEqual(len(val_loader), 1)

    def test_episode_recorder_preserves_demo_metadata_attrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = EpisodeRecorder(
                output_dir=tmpdir,
                episode_idx=7,
                metadata={
                    "operator_id": "alice",
                    "session_id": "sess-001",
                    "notes": "test note",
                    "record_config_path": "/tmp/teleop_v0.yaml",
                    "record_config_yaml": "task:\n  task_name: agx_excavation_teleop\n",
                },
                camera_names=["fpv"],
            )
            obs = {
                "qpos": np.zeros(4, dtype=np.float32),
                "qvel": np.zeros(4, dtype=np.float32),
                "env_state": np.zeros(9, dtype=np.float32),
                "images": {"fpv": np.zeros((8, 8, 3), dtype=np.uint8)},
            }
            recorder.record(obs, np.zeros(4, dtype=np.float32), reward=0.0, step_id=0)
            path = recorder.save(success=True)

            episode = read_episode(path)
            metadata = episode["metadata"]
            self.assertEqual(metadata["episode_id"], "episode_7")
            self.assertEqual(metadata["operator_id"], "alice")
            self.assertEqual(metadata["session_id"], "sess-001")
            self.assertEqual(metadata["notes"], "test note")
            self.assertEqual(metadata["record_config_path"], "/tmp/teleop_v0.yaml")
            self.assertIn("task_name: agx_excavation_teleop", metadata["record_config_yaml"])

    def test_experiment_record_collects_train_eval_and_qc_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            train_ckpt_dir = tmp / "ckpts" / "run_a"
            eval_results_dir = tmp / "eval" / "run_a" / "results"
            dataset_dir = tmp / "data" / "dataset_a"
            (dataset_dir / "qc").mkdir(parents=True, exist_ok=True)
            train_ckpt_dir.mkdir(parents=True, exist_ok=True)
            eval_results_dir.mkdir(parents=True, exist_ok=True)

            (train_ckpt_dir / "run_metadata.json").write_text(json.dumps({
                "training_result": {"best_epoch": 42, "best_val_loss": 0.321},
                "command": "tb-train --config x.yaml",
                "paths": {"dataset_dir": str(dataset_dir)},
                "split": {"train_ids": [0, 1], "val_ids": [2]},
            }))
            (train_ckpt_dir / "resolved_config.yaml").write_text("task:\n  dataset_dir: data/dataset_a\n")
            (eval_results_dir / "metrics.json").write_text(json.dumps({
                "ckpt_path": "runs/ckpts/run_a/policy_best.ckpt",
                "n_rollouts": 10,
                "n_success": 2,
                "success_rate": 0.2,
                "avg_return": 123.4,
                "avg_episode_len": 1000.0,
                "extra": {
                    "success_mode": "dump_complete_final_hold",
                    "avg_final_success_signal": 210.0,
                    "avg_max_success_signal": 420.0,
                    "avg_final_bucket_mass": 88.0,
                },
            }))
            (eval_results_dir / "rollout_manifest.json").write_text(json.dumps({
                "success_rates_by_mode": {
                    "legacy_success": 0.3,
                    "final_hold_success": 0.2,
                    "strict_final_hold_success": 0.1,
                    "dump_complete_final_hold_success": 0.1,
                    "strict_dump_complete_success": 0.0,
                },
                "success_counts_by_mode": {
                    "legacy_success": 3,
                    "final_hold_success": 2,
                    "strict_final_hold_success": 1,
                    "dump_complete_final_hold_success": 1,
                    "strict_dump_complete_success": 0,
                },
                "rollouts": [
                    {"failure_counts": {"spill_before_target": 2, "hard_target_collision": 1}},
                    {"failure_counts": {"spill_before_target": 0, "unsafe_target_distance": 3}},
                ],
            }))
            (dataset_dir / "qc" / "summary.json").write_text(json.dumps({
                "n_episodes": 20,
                "success_rate": 1.0,
                "episode_length": {"mean": [704.25], "std": [70.7]},
            }))

            record = build_experiment_record(
                train_ckpt_dir=train_ckpt_dir,
                eval_results_dir=eval_results_dir,
                dataset_dir=dataset_dir,
                experiment_name="fulltest_round1",
                notes="first baseline",
            )
            json_path, md_path = write_experiment_record(
                record=record,
                output_root=tmp / "experiments",
            )
            registry_path = append_experiment_registry(
                record,
                tmp / "experiments" / "experiment_registry.csv",
            )

            self.assertEqual(record["experiment_name"], "fulltest_round1")
            self.assertEqual(record["train"]["best_epoch"], 42)
            self.assertEqual(record["eval"]["primary_success_rate"], 0.2)
            self.assertEqual(record["eval"]["legacy_success_rate"], 0.3)
            self.assertEqual(record["eval"]["dump_complete_final_hold_success_rate"], 0.1)
            self.assertEqual(record["eval"]["strict_dump_complete_success_rate"], 0.0)
            self.assertEqual(record["eval"]["avg_final_bucket_mass"], 88.0)
            self.assertEqual(record["eval"]["mean_failure_counts"]["spill_before_target"], 1.0)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(registry_path.exists())
            self.assertIn("fulltest_round1", md_path.read_text())


if __name__ == "__main__":
    unittest.main()
