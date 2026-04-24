from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.transition_v2_1 import CLEAN_PROFILE_STAGE5, build_transition_dataset
from testbed.data.v2_1 import GOAL_TOKEN_DIM, GOAL_TOKEN_VERSION, build_goal_tokens


class TestTransitionDataset(unittest.TestCase):
    def test_build_transition_dataset_creates_cropped_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "transition"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 8
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            source_path = dataset_dir / "episode_0.hdf5"
            write_episode(
                source_path,
                qpos=np.arange(length * 4, dtype=np.float32).reshape(length, 4),
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.ones((length, 4), dtype=np.float32),
                images={"fpv": np.arange(length * 4 * 4 * 3, dtype=np.uint8).reshape(length, 4, 4, 3)},
                rewards=np.arange(length, dtype=np.float32),
                metadata={
                    "scenario_id": "s0_truck",
                    "v2_enabled": True,
                    "goal_token_version": GOAL_TOKEN_VERSION,
                },
                env_state=np.zeros((length, 9), dtype=np.float32),
                step_ids=np.arange(length, dtype=np.int64),
                step_ns=np.arange(length, dtype=np.int64) * 10,
                action_src_types=["teleop"] * length,
                action_src_ids=[f"src-{i}" for i in range(length)],
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1, 0, 0, 0, 0, 0, 1, 1], dtype=np.int32),
                        "mode_id": np.asarray([1, 0, 0, 0, 1, 1, 0, 0], dtype=np.uint8),
                        "phase_id": np.asarray([6, 0, 1, 4, 5, 6, 0, 1], dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.asarray([0, 0, 0, 0, 1, 0, 0, 0], dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1, 0, 0, 0, 0, 1, 0], dtype=np.uint8),
                        "dump_start_mask": np.asarray([0, 0, 0, 1, 0, 0, 0, 0], dtype=np.uint8),
                        "dump_end_mask": np.asarray([0, 0, 0, 1, 0, 0, 0, 0], dtype=np.uint8),
                        "boundary_mask": np.asarray([0, 0, 0, 0, 0, 0, 1, 0], dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0, 1], dtype=np.int32),
                        "start_step": np.asarray([1, 6], dtype=np.int32),
                        "dump_end_step": np.asarray([3, -1], dtype=np.int32),
                        "end_step": np.asarray([5, -1], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1, 0], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2, 2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([0, -1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([1, -1], dtype=np.int32),
                        "dst_target_id": np.asarray([1, 1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([140.0, 0.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([25.0, 0.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.08, 0.0], dtype=np.float32),
                        "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
                        "transition_source": np.asarray(["none", "none"], dtype=str),
                        "plan_source": np.asarray(["none", "none"], dtype=str),
                        "cycle_success": np.asarray([1, 0], dtype=np.uint8),
                    },
                },
            )

            written = build_transition_dataset(dataset_dir=dataset_dir, output_dir=output_dir)
            self.assertEqual(written, 1)
            self.assertTrue((output_dir / "summary.json").exists())

            cropped_episode = read_episode(output_dir / "episode_0.hdf5")
            self.assertEqual(cropped_episode["qpos"].shape, (4, 4))
            self.assertEqual(cropped_episode["step_ids"].tolist(), [3, 4, 5, 6])
            self.assertEqual(cropped_episode["metadata"]["recording_mode"], "transition_relabel")
            self.assertEqual(cropped_episode["metadata"]["source_episode_id"], "episode_0")
            self.assertEqual(int(cropped_episode["metadata"]["source_prev_cycle_id"]), 0)
            self.assertEqual(int(cropped_episode["metadata"]["source_next_cycle_id"]), 1)
            self.assertEqual(cropped_episode["metadata"]["transition_window"], "dump_end_to_next_qualified_dig_start")
            self.assertEqual(cropped_episode["metadata"]["scenario_id"], "s0_truck")
            self.assertEqual(cropped_episode["v2"]["step"]["cycle_id"].tolist(), [0, 0, 0, 1])
            self.assertEqual(cropped_episode["v2"]["step"]["goal_tokens"].shape, (4, GOAL_TOKEN_DIM))
            self.assertTrue("cycle" not in (cropped_episode["v2"] or {}))

    def test_build_transition_dataset_fails_without_transition_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=np.zeros((3, 4), dtype=np.float32),
                qvel=np.zeros((3, 4), dtype=np.float32),
                actions=np.zeros((3, 4), dtype=np.float32),
                images={"fpv": np.zeros((3, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=np.zeros((3, 9), dtype=np.float32),
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1, 0, 0], dtype=np.int32),
                        "mode_id": np.ones(3, dtype=np.uint8),
                        "phase_id": np.full(3, 6, dtype=np.uint8),
                        "phase_progress": np.zeros(3, dtype=np.float32),
                        "goal_tokens": np.repeat(
                            build_goal_tokens("s0_truck").reshape(1, -1),
                            3,
                            axis=0,
                        ).astype(np.float32),
                        "planner_replan_mask": np.zeros(3, dtype=np.uint8),
                        "qualified_dig_start_mask": np.zeros(3, dtype=np.uint8),
                        "dump_start_mask": np.zeros(3, dtype=np.uint8),
                        "dump_end_mask": np.zeros(3, dtype=np.uint8),
                        "boundary_mask": np.zeros(3, dtype=np.uint8),
                        "pause_mask": np.zeros(3, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([2], dtype=np.int32),
                        "end_step": np.asarray([2], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([1], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([10.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([1.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.01], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_transition_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=Path(tmpdir) / "transition",
                )

    def test_build_transition_dataset_can_filter_out_overlong_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "transition"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 10
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=np.arange(length * 4, dtype=np.float32).reshape(length, 4),
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.ones((length, 4), dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=np.zeros((length, 9), dtype=np.float32),
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1, 0, 0, 0, 0, 0, 0, 0, 1, 1], dtype=np.int32),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1, 0, 0, 0, 0, 0, 0, 1, 0], dtype=np.uint8),
                        "dump_start_mask": np.zeros(length, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0, 0, 0, 1, 0, 0, 0, 0, 0, 0], dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0, 1], dtype=np.int32),
                        "start_step": np.asarray([1, 8], dtype=np.int32),
                        "dump_end_step": np.asarray([3, -1], dtype=np.int32),
                        "end_step": np.asarray([7, -1], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1, 0], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([1, 1], dtype=np.int32),
                        "next_src_sector_id": np.asarray([0, -1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([1, -1], dtype=np.int32),
                        "dst_target_id": np.asarray([1, 1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([200.0, 0.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([200.0, 0.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.08, 0.0], dtype=np.float32),
                        "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
                        "transition_source": np.asarray(["none", "none"], dtype=str),
                        "plan_source": np.asarray(["none", "none"], dtype=str),
                        "cycle_success": np.asarray([1, 0], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_transition_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    max_transition_len=5,
                )

    def test_stage5_clean_profile_writes_summary_and_filters_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "transition_clean_v2"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 90
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 7] = 0.20
            env_state[:, 8] = 0.0
            env_state[10:20, 0] = 45.0
            env_state[10:20, 7] = 0.04
            env_state[10:20, 8] = 0.03
            actions = np.full((length, 4), 0.08, dtype=np.float32)
            actions[8:, :] = 0.08

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=np.arange(length * 4, dtype=np.float32).reshape(length, 4),
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=actions,
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=env_state,
                v2={
                    "step": {
                        "cycle_id": np.concatenate(
                            [
                                np.asarray([-1], dtype=np.int32),
                                np.zeros(83, dtype=np.int32),
                                np.ones(6, dtype=np.int32),
                            ]
                        ),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.concatenate(
                            [
                                np.asarray([0, 1], dtype=np.uint8),
                                np.zeros(82, dtype=np.uint8),
                                np.asarray([1], dtype=np.uint8),
                                np.zeros(5, dtype=np.uint8),
                            ]
                        ),
                        "dump_start_mask": np.zeros(length, dtype=np.uint8),
                        "dump_end_mask": np.concatenate(
                            [
                                np.asarray([0, 0, 0, 1], dtype=np.uint8),
                                np.zeros(length - 4, dtype=np.uint8),
                            ]
                        ),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0, 1], dtype=np.int32),
                        "start_step": np.asarray([1, 84], dtype=np.int32),
                        "dump_end_step": np.asarray([3, -1], dtype=np.int32),
                        "end_step": np.asarray([83, -1], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1, 0], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([1, 1], dtype=np.int32),
                        "next_src_sector_id": np.asarray([0, -1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([1, -1], dtype=np.int32),
                        "dst_target_id": np.asarray([1, 1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([200.0, 0.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([200.0, 0.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.08, 0.0], dtype=np.float32),
                        "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
                        "transition_source": np.asarray(["none", "none"], dtype=str),
                        "plan_source": np.asarray(["none", "none"], dtype=str),
                        "cycle_success": np.asarray([1, 0], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_transition_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5,
                )

            summary_path = output_dir / "summary.json"
            self.assertTrue(summary_path.exists())
            summary = summary_path.read_text()
            self.assertIn("late_qds_failure", summary)


if __name__ == "__main__":
    unittest.main()
