from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.cli.label_v2_1 import _load_label_config_sections
from testbed.data.dataset import load_data
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.schema import (
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX,
)
from testbed.data.v2_1 import (
    GOAL_TOKEN_DIM,
    GOAL_TOKEN_VERSION,
    SECTOR_LEFT_MAX_SWING,
    SECTOR_MID_MAX_SWING,
    WORK_STAGE_NAME_TO_ID,
    _fill_cycle_work_stage_labels,
    build_goal_tokens,
    label_episode_v2_1,
    swing_to_sector_id,
)
from testbed.data.workskill_v2_1 import (
    CLEAN_PROFILE_STAGE5,
    CLEAN_PROFILE_STAGE5_BALANCED,
    CLEAN_PROFILE_STAGE5_CLEANEST,
    CLEAN_PROFILE_STAGE5_STRICT,
    build_workskill_dataset,
)


def _with_target_geometry(env_state: np.ndarray) -> np.ndarray:
    arr = np.asarray(env_state, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] >= 13:
        return arr
    geometry = np.zeros((arr.shape[0], 4), dtype=np.float32)
    geometry[:, 0] = arr[:, 4]
    geometry[:, 1] = 0.10
    geometry[:, 2] = 1.0
    geometry[:, 3] = 1.0
    return np.concatenate([arr, geometry], axis=1)


class TestStage3Workskill(unittest.TestCase):
    def test_label_config_sections_load_stage_success_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "teleop.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "success:",
                        "  stage_success:",
                        "    dig_min_payload_gain_kg: 15.0",
                        "    dump_min_deposit_delta_kg: 8.0",
                        "reward:",
                        "  load_mass_threshold_kg: 55.0",
                        "  qualified_dig_start_mode: contact_depth",
                    ]
                )
            )

            success_cfg, reward_cfg = _load_label_config_sections(config_path)

            self.assertEqual(
                success_cfg["stage_success"]["dig_min_payload_gain_kg"],
                15.0,
            )
            self.assertEqual(
                success_cfg["stage_success"]["dump_min_deposit_delta_kg"],
                8.0,
            )
            self.assertEqual(reward_cfg["load_mass_threshold_kg"], 55.0)

    def test_swing_to_sector_id_uses_dig_area_calibrated_thresholds(self) -> None:
        self.assertAlmostEqual(SECTOR_LEFT_MAX_SWING, 0.47333333333333333)
        self.assertAlmostEqual(SECTOR_MID_MAX_SWING, 0.5166666666666667)
        self.assertEqual(swing_to_sector_id(0.47), 0)
        self.assertEqual(swing_to_sector_id(SECTOR_LEFT_MAX_SWING), 1)
        self.assertEqual(swing_to_sector_id(0.50), 1)
        self.assertEqual(swing_to_sector_id(SECTOR_MID_MAX_SWING), 2)
        self.assertEqual(swing_to_sector_id(0.56), 2)

    def test_label_episode_infers_terminal_dump_end_from_target_dump_metadata(self) -> None:
        qpos = np.asarray(
            [
                [0.50, 0.0, 0.0, 0.0],
                [0.56, 0.0, 0.0, 0.0],
                [0.56, 0.0, 0.0, 0.0],
                [0.56, 0.0, 0.0, 0.0],
                [0.56, 0.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        actions = np.ones((5, 4), dtype=np.float32)
        env_state = np.asarray(
            [
                [0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.20, 0.00],
                [80.0, 80.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.01, 0.03],
                [300.0, 300.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.20, 0.05],
                [250.0, 300.0, 20.0, 20.0, 1.0, 0.0, 0.0, 0.20, 0.00],
                [80.0, 300.0, 320.0, 320.0, 1.0, 0.0, 0.0, 0.20, 0.00],
            ],
            dtype=np.float32,
        )

        v2_payload, _ = label_episode_v2_1(
            qpos=qpos,
            actions=actions,
            env_state=_with_target_geometry(env_state),
            metadata={
                "stop_reason": "target_dump_count_reached",
                "target_dump_count": 1,
                "completed_dump_count": 1,
                "success": 1,
            },
            scenario_id="s0_truck",
        )

        cycle = v2_payload["cycle"]
        step = v2_payload["step"]
        self.assertEqual(cycle["start_step"].tolist(), [1])
        self.assertEqual(cycle["dump_end_step"].tolist(), [4])
        self.assertEqual(cycle["end_step"].tolist(), [4])
        self.assertEqual(cycle["cycle_success"].tolist(), [1])
        self.assertEqual(cycle["dig_success"].tolist(), [1])
        self.assertEqual(cycle["carry_success"].tolist(), [1])
        self.assertEqual(cycle["dump_success"].tolist(), [1])
        self.assertEqual(cycle["return_required"].tolist(), [0])
        self.assertEqual(cycle["return_success"].tolist(), [0])
        self.assertEqual(cycle["stage_success"].tolist(), [1])
        self.assertGreater(float(cycle["payload_gain_kg"][0]), 0.0)
        self.assertGreater(float(cycle["dump_deposited_fraction"][0]), 0.0)
        self.assertEqual(step["dump_end_mask"].tolist(), [0, 0, 0, 0, 1])

    def test_label_episode_reports_stage_success_failures(self) -> None:
        qpos = np.asarray(
            [
                [0.50, 0.0, 0.0, 0.0],
                [0.50, 0.0, 0.0, 0.0],
                [0.50, 0.0, 0.0, 0.0],
                [0.50, 0.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        actions = np.ones((4, 4), dtype=np.float32)
        env_state = np.asarray(
            [
                [0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.20, 0.00],
                [5.0, 5.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.01, 0.03],
                [8.0, 8.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.20, 0.00],
                [2.0, 8.0, 2.0, 2.0, 1.0, 0.0, 0.0, 0.20, 0.00],
            ],
            dtype=np.float32,
        )

        v2_payload, metadata_updates = label_episode_v2_1(
            qpos=qpos,
            actions=actions,
            env_state=_with_target_geometry(env_state),
            metadata={"success": 1},
            scenario_id="s0_truck",
            reward_cfg={
                "load_mass_threshold_kg": 55.0,
                "qualified_dig_start_mode": "contact_depth",
            },
        )

        cycle = v2_payload["cycle"]
        self.assertEqual(metadata_updates["stage_success_version"], "v2_2_stage_success_4p")
        self.assertEqual(cycle["cycle_success"].tolist(), [1])
        self.assertEqual(cycle["dig_success"].tolist(), [0])
        self.assertEqual(cycle["stage_success"].tolist(), [0])
        self.assertEqual(cycle["stage_failure_reason_code"].tolist(), [1])

    def test_build_workskill_dataset_creates_cropped_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 6
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            actions = np.ones((length, 4), dtype=np.float32)
            actions[3, 3] = -0.50
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 4] = 0.75
            env_state[3, 4] = 0.30
            env_state = _with_target_geometry(env_state)
            source_path = dataset_dir / "episode_0.hdf5"
            write_episode(
                source_path,
                qpos=np.arange(length * 4, dtype=np.float32).reshape(length, 4),
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=actions,
                images={"fpv": np.arange(length * 4 * 4 * 3, dtype=np.uint8).reshape(length, 4, 4, 3)},
                rewards=np.arange(length, dtype=np.float32),
                metadata={
                    "scenario_id": "s0_truck",
                    "v2_enabled": True,
                    "goal_token_version": GOAL_TOKEN_VERSION,
                    "phase_version": "v2_1_mode_phase_7cls",
                },
                env_state=env_state,
                step_ids=np.arange(length, dtype=np.int64),
                step_ns=np.arange(length, dtype=np.int64) * 10,
                action_src_types=["teleop"] * length,
                action_src_ids=[f"src-{i}" for i in range(length)],
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1, 0, 0, 0, 0, -1], dtype=np.int32),
                        "mode_id": np.asarray([1, 0, 0, 0, 0, 1], dtype=np.uint8),
                        "phase_id": np.asarray([6, 0, 1, 3, 4, 6], dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1, 0, 0, 0, 0], dtype=np.uint8),
                        "dump_start_mask": np.asarray([0, 0, 0, 0, 1, 0], dtype=np.uint8),
                        "dump_end_mask": np.asarray([0, 0, 0, 0, 1, 0], dtype=np.uint8),
                        "boundary_mask": np.asarray([0, 0, 0, 0, 0, 0], dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([4], dtype=np.int32),
                        "end_step": np.asarray([5], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([140.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([25.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.08], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            written = build_workskill_dataset(dataset_dir=dataset_dir, output_dir=output_dir)
            self.assertEqual(written, 1)

            source_episode = read_episode(source_path)
            self.assertEqual(source_episode["qpos"].shape, (6, 4))

            cropped_episode = read_episode(output_dir / "episode_0.hdf5")
            self.assertEqual(cropped_episode["qpos"].shape, (4, 4))
            self.assertEqual(cropped_episode["images"]["fpv"].shape, (4, 4, 4, 3))
            self.assertEqual(cropped_episode["step_ids"].tolist(), [1, 2, 3, 4])
            self.assertEqual(cropped_episode["action_src_ids"], ["src-1", "src-2", "src-3", "src-4"])
            self.assertEqual(cropped_episode["metadata"]["recording_mode"], "workskill_relabel")
            self.assertEqual(cropped_episode["metadata"]["source_episode_id"], "episode_0")
            self.assertEqual(int(cropped_episode["metadata"]["source_cycle_id"]), 0)
            self.assertEqual(cropped_episode["metadata"]["workskill_window"], "qualified_dig_start_to_dump_end")
            self.assertEqual(cropped_episode["metadata"]["scenario_id"], "s0_truck")
            self.assertEqual(cropped_episode["v2"]["step"]["cycle_id"].tolist(), [0, 0, 0, 0])
            self.assertEqual(cropped_episode["v2"]["cycle"]["start_step"].tolist(), [0])
            self.assertEqual(cropped_episode["v2"]["cycle"]["dump_end_step"].tolist(), [3])
            self.assertEqual(cropped_episode["v2"]["cycle"]["end_step"].tolist(), [3])
            self.assertEqual(cropped_episode["v2"]["cycle"]["cycle_success"].tolist(), [1])
            self.assertEqual(cropped_episode["v2"]["step"]["goal_tokens"].shape, (4, GOAL_TOKEN_DIM))
            self.assertEqual(cropped_episode["v2"]["step"]["action_loss_mask"].tolist(), [1, 1, 1, 1])
            with open(output_dir / "summary.json") as f:
                summary = json.load(f)
            self.assertEqual(summary["kept_strong_dump_frame_count_distribution"]["max"], 1.0)
            self.assertEqual(
                summary["kept_strong_dump_near_target_frame_count_distribution"]["max"],
                1.0,
            )
            self.assertAlmostEqual(
                summary["kept_strong_dump_min_target_distance_distribution_m"]["min"],
                0.30,
                places=5,
            )
            self.assertEqual(summary["kept_action_loss_masked_frame_count_distribution"]["max"], 0.0)
            self.assertEqual(summary["action_loss_mask_policy"]["ignored_cases"], [])

    def test_build_workskill_dataset_fails_without_successful_cycles(self) -> None:
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
                        "cycle_id": np.asarray([-1, -1, -1], dtype=np.int32),
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
                        "dump_end_step": np.asarray([-1], dtype=np.int32),
                        "end_step": np.asarray([-1], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([1], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([0.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([0.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.0], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([0], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=Path(tmpdir) / "workskill",
                )

    def test_build_workskill_dataset_stage5_clean_profile_filters_bad_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v2"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 8
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 0] = np.asarray([0.0, 10.0, 120.0, 150.0, 150.0, 60.0, 15.0, 10.0], dtype=np.float32)
            env_state[:, 4] = np.asarray([2.0, 2.0, 1.8, 1.7, 1.6, 1.5, 1.6, 1.6], dtype=np.float32)
            env_state[:, 7] = np.asarray([0.20, 0.04, 0.03, 0.03, 0.03, 0.20, 0.20, 0.20], dtype=np.float32)
            env_state[:, 8] = np.asarray([0.00, 0.03, 0.40, 0.42, 0.40, 0.10, 0.02, 0.00], dtype=np.float32)

            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = np.asarray([0.00, 0.36, 0.34, 0.33, 0.32, 0.31, 0.30, 0.30], dtype=np.float32)

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1, 0, 0, 0, 0, 0, 0, -1], dtype=np.int32),
                        "mode_id": np.asarray([1, 0, 0, 0, 0, 0, 0, 1], dtype=np.uint8),
                        "phase_id": np.asarray([6, 0, 1, 1, 3, 4, 4, 6], dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1, 0, 0, 0, 0, 0, 0], dtype=np.uint8),
                        "dump_start_mask": np.asarray([0, 0, 0, 0, 0, 1, 0, 0], dtype=np.uint8),
                        "dump_end_mask": np.asarray([0, 0, 0, 0, 0, 0, 1, 0], dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([6], dtype=np.int32),
                        "end_step": np.asarray([6], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([150.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([40.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.42], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5,
                )

            summary_path = output_dir / "summary.json"
            self.assertTrue(summary_path.exists())
            self.assertIn("flat_bucket_qds", summary_path.read_text())

    def test_build_workskill_dataset_stage5_strict_filters_failed_bite_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v3"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 100
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 4] = 1.0  # target distance stays within normal dump geometry gate
            env_state[:, 7] = 0.02  # in dig area
            env_state[:, 8] = 0.05  # shallow by default
            env_state[1:15, 8] = 0.34
            env_state[15:30, 8] = 0.10
            env_state[30:80, 8] = 0.06
            env_state[1:15, 0] = np.linspace(10.0, 130.0, 14, dtype=np.float32)
            env_state[15:25, 0] = np.linspace(90.0, 5.0, 10, dtype=np.float32)
            env_state[25:80, 0] = 0.0
            env_state[90:95, 0] = 80.0

            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = 0.02

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.concatenate(
                            [np.full(1, -1, dtype=np.int32), np.zeros(length - 2, dtype=np.int32), np.full(1, -1, dtype=np.int32)]
                        ),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1] + [0] * (length - 2), dtype=np.uint8),
                        "dump_start_mask": np.asarray([0] * 90 + [1] + [0] * 9, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0] * 94 + [1] + [0] * 5, dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([94], dtype=np.int32),
                        "end_step": np.asarray([94], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([130.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([30.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.34], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5_STRICT,
                )

            summary_path = output_dir / "summary.json"
            self.assertTrue(summary_path.exists())
            self.assertIn("weak_early_load_gain", summary_path.read_text())

    def test_build_workskill_dataset_stage5_strict_filters_near_dump_start_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v3"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 16
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 0] = np.asarray(
                [0.0, 20.0, 80.0, 180.0, 260.0, 320.0, 310.0, 300.0, 290.0, 285.0, 280.0, 280.0, 280.0, 280.0, 20.0, 0.0],
                dtype=np.float32,
            )
            env_state[:, 4] = np.asarray(
                [1.8, 1.8, 1.7, 1.5, 1.3, 1.1, 0.9, 0.7, 0.6, 0.5, 0.45, 0.40, 0.36, 0.25, 0.25, 0.5],
                dtype=np.float32,
            )
            env_state[:, 7] = 0.02
            env_state[:, 8] = np.asarray(
                [0.00, 0.12, 0.24, 0.34, 0.36, 0.36, 0.34, 0.30, 0.24, 0.16, 0.10, 0.08, 0.06, 0.04, 0.00, 0.00],
                dtype=np.float32,
            )

            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = 0.04

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1] + [0] * (length - 2) + [-1], dtype=np.int32),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1] + [0] * (length - 2), dtype=np.uint8),
                        "dump_start_mask": np.asarray([0] * 13 + [1] + [0] * 2, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0] * 14 + [1] + [0], dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([14], dtype=np.int32),
                        "end_step": np.asarray([14], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([320.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([260.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.36], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5_STRICT,
                )

            summary_path = output_dir / "summary.json"
            self.assertTrue(summary_path.exists())
            self.assertIn("near_dump_start", summary_path.read_text())

    def test_fill_cycle_work_stage_labels_marks_rebite_and_approach(self) -> None:
        length = 18
        work_stage_id = np.zeros(length, dtype=np.uint8)
        dump_start_mask = np.zeros(length, dtype=np.uint8)
        dump_start_mask[15] = 1
        bucket_depth = np.asarray(
            [
                0.0,
                0.18,
                0.26,
                0.31,
                0.22,
                0.10,
                0.06,
                0.05,
                0.24,
                0.38,
                0.52,
                0.60,
                0.20,
                0.12,
                0.06,
                0.00,
                0.00,
                0.00,
            ],
            dtype=np.float32,
        )
        mass = np.asarray(
            [
                0.0,
                20.0,
                80.0,
                140.0,
                60.0,
                18.0,
                5.0,
                8.0,
                260.0,
                420.0,
                510.0,
                530.0,
                510.0,
                430.0,
                320.0,
                280.0,
                120.0,
                20.0,
            ],
            dtype=np.float32,
        )
        env_state = np.zeros((length, 9), dtype=np.float32)
        env_state[:, 4] = np.asarray(
            [2.0, 2.0, 1.9, 1.8, 1.8, 1.8, 1.7, 1.7, 1.6, 1.4, 1.3, 1.2, 1.0, 0.9, 0.7, 0.4, 0.2, 0.1],
            dtype=np.float32,
        )

        _fill_cycle_work_stage_labels(
            work_stage_id=work_stage_id,
            start_step=1,
            dump_end_step=16,
            next_start_step=None,
            dump_start_mask=dump_start_mask,
            bucket_depth=bucket_depth,
            mass_in_bucket=mass,
            env_state=_with_target_geometry(env_state),
        )

        self.assertEqual(int(work_stage_id[1]), WORK_STAGE_NAME_TO_ID["entry_to_bite"])
        self.assertEqual(int(work_stage_id[3]), WORK_STAGE_NAME_TO_ID["first_bite"])
        self.assertEqual(int(work_stage_id[6]), WORK_STAGE_NAME_TO_ID["rebite_recovery"])
        self.assertEqual(int(work_stage_id[10]), WORK_STAGE_NAME_TO_ID["carry"])
        self.assertEqual(int(work_stage_id[12]), WORK_STAGE_NAME_TO_ID["approach_dump"])
        self.assertEqual(int(work_stage_id[15]), WORK_STAGE_NAME_TO_ID["dump"])

    def test_approach_dump_uses_dump_area_top_geometry_for_new_env_state(self) -> None:
        length = 18
        work_stage_id = np.zeros(length, dtype=np.uint8)
        dump_start_mask = np.zeros(length, dtype=np.uint8)
        dump_start_mask[15] = 1
        bucket_depth = np.zeros(length, dtype=np.float32)
        mass = np.full(length, 300.0, dtype=np.float32)
        env_state = np.zeros((length, 16), dtype=np.float32)
        env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] = mass
        env_state[:, ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX] = 2.0
        env_state[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.50
        env_state[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 2.0
        env_state[11:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.20

        _fill_cycle_work_stage_labels(
            work_stage_id=work_stage_id,
            start_step=1,
            dump_end_step=16,
            next_start_step=None,
            dump_start_mask=dump_start_mask,
            bucket_depth=bucket_depth,
            mass_in_bucket=mass,
            env_state=env_state,
        )

        self.assertEqual(int(work_stage_id[10]), WORK_STAGE_NAME_TO_ID["carry"])
        self.assertEqual(int(work_stage_id[11]), WORK_STAGE_NAME_TO_ID["approach_dump"])
        self.assertEqual(int(work_stage_id[15]), WORK_STAGE_NAME_TO_ID["dump"])

    def test_build_workskill_dataset_stage5_cleanest_filters_pretarget_spill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v4"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 16
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 0] = np.asarray([0.0, 150.0, 520.0, 1300.0, 1700.0, 1650.0, 700.0, 650.0, 600.0, 550.0, 500.0, 480.0, 470.0, 460.0, 50.0, 0.0], dtype=np.float32)
            env_state[:, 4] = np.asarray([2.0, 2.0, 1.9, 1.8, 1.7, 1.6, 1.5, 1.45, 1.4, 1.35, 1.3, 1.25, 1.22, 1.0, 0.6, 0.6], dtype=np.float32)
            env_state[:, 7] = np.asarray([0.02, 0.02, 0.02, 0.03, 0.03, 0.26, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28], dtype=np.float32)
            env_state[:, 8] = np.asarray([0.00, 0.12, 0.20, 0.34, 0.36, 0.35, 0.33, 0.30, 0.27, 0.24, 0.20, 0.18, 0.16, 0.12, 0.08, 0.00], dtype=np.float32)

            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = 0.04

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1] + [0] * (length - 2) + [-1], dtype=np.int32),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1] + [0] * (length - 2), dtype=np.uint8),
                        "dump_start_mask": np.asarray([0] * 13 + [1] + [0] * 2, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0] * 14 + [1] + [0], dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([14], dtype=np.int32),
                        "end_step": np.asarray([14], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([1700.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([80.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.35], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5_CLEANEST,
                )

            summary_path = output_dir / "summary.json"
            self.assertTrue(summary_path.exists())
            self.assertIn("pretarget_spill_proxy", summary_path.read_text())

    def test_build_workskill_dataset_stage5_balanced_filters_pretarget_spill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v3b"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 16
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 0] = np.asarray([0.0, 150.0, 520.0, 1300.0, 1700.0, 1650.0, 700.0, 650.0, 600.0, 550.0, 500.0, 480.0, 470.0, 460.0, 50.0, 0.0], dtype=np.float32)
            env_state[:, 4] = np.asarray([2.0, 2.0, 1.9, 1.8, 1.7, 1.6, 1.5, 1.45, 1.4, 1.35, 1.3, 1.25, 1.22, 1.0, 0.6, 0.6], dtype=np.float32)
            env_state[:, 7] = np.asarray([0.02, 0.02, 0.02, 0.03, 0.03, 0.26, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28], dtype=np.float32)
            env_state[:, 8] = np.asarray([0.00, 0.12, 0.20, 0.34, 0.36, 0.35, 0.33, 0.30, 0.27, 0.24, 0.20, 0.18, 0.16, 0.12, 0.08, 0.00], dtype=np.float32)
            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = 0.04

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.asarray([-1] + [0] * (length - 2) + [-1], dtype=np.int32),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1] + [0] * (length - 2), dtype=np.uint8),
                        "dump_start_mask": np.asarray([0] * 13 + [1] + [0] * 2, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0] * 14 + [1] + [0], dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([14], dtype=np.int32),
                        "end_step": np.asarray([14], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([1700.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([80.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.35], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5_BALANCED,
                )

            self.assertIn("pretarget_spill_proxy", (output_dir / "summary.json").read_text())

    def test_build_workskill_dataset_stage5_cleanest_filters_probe_then_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v4"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 100
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 4] = 0.75
            env_state[:, 7] = 0.02
            env_state[:, 8] = 0.36
            env_state[:12, 0] = np.asarray([0.0, 10.0, 60.0, 45.0, 18.0, 0.0, 15.0, 35.0, 90.0, 210.0, 260.0, 280.0], dtype=np.float32)
            env_state[12:90, 0] = 260.0
            env_state[90:95, 0] = np.asarray([250.0, 200.0, 150.0, 80.0, 20.0], dtype=np.float32)

            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = 0.03

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.concatenate(
                            [np.full(1, -1, dtype=np.int32), np.zeros(length - 2, dtype=np.int32), np.full(1, -1, dtype=np.int32)]
                        ),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1] + [0] * (length - 2), dtype=np.uint8),
                        "dump_start_mask": np.asarray([0] * 90 + [1] + [0] * 9, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0] * 94 + [1] + [0] * 5, dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([94], dtype=np.int32),
                        "end_step": np.asarray([94], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([280.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([80.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.36], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5_CLEANEST,
                )

            summary_path = output_dir / "summary.json"
            self.assertTrue(summary_path.exists())
            self.assertIn("probe_then_reload", summary_path.read_text())

    def test_build_workskill_dataset_stage5_balanced_filters_probe_then_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "relabeled"
            output_dir = Path(tmpdir) / "workskill_clean_v3b"
            dataset_dir.mkdir(parents=True, exist_ok=True)

            length = 100
            goal_tokens = np.repeat(
                build_goal_tokens("s0_truck").reshape(1, -1),
                length,
                axis=0,
            ).astype(np.float32)
            env_state = np.zeros((length, 9), dtype=np.float32)
            env_state[:, 4] = 0.75
            env_state[:, 7] = 0.02
            env_state[:, 8] = 0.36
            env_state[:12, 0] = np.asarray([0.0, 10.0, 60.0, 45.0, 18.0, 0.0, 15.0, 35.0, 90.0, 210.0, 260.0, 280.0], dtype=np.float32)
            env_state[12:90, 0] = 260.0
            env_state[90:95, 0] = np.asarray([250.0, 200.0, 150.0, 80.0, 20.0], dtype=np.float32)

            qpos = np.zeros((length, 4), dtype=np.float32)
            qpos[:, 3] = 0.03

            write_episode(
                dataset_dir / "episode_0.hdf5",
                qpos=qpos,
                qvel=np.zeros((length, 4), dtype=np.float32),
                actions=np.full((length, 4), 0.08, dtype=np.float32),
                images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
                metadata={"scenario_id": "s0_truck", "v2_enabled": True},
                env_state=_with_target_geometry(env_state),
                v2={
                    "step": {
                        "cycle_id": np.concatenate(
                            [np.full(1, -1, dtype=np.int32), np.zeros(length - 2, dtype=np.int32), np.full(1, -1, dtype=np.int32)]
                        ),
                        "mode_id": np.zeros(length, dtype=np.uint8),
                        "phase_id": np.zeros(length, dtype=np.uint8),
                        "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                        "goal_tokens": goal_tokens,
                        "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                        "qualified_dig_start_mask": np.asarray([0, 1] + [0] * (length - 2), dtype=np.uint8),
                        "dump_start_mask": np.asarray([0] * 90 + [1] + [0] * 9, dtype=np.uint8),
                        "dump_end_mask": np.asarray([0] * 94 + [1] + [0] * 5, dtype=np.uint8),
                        "boundary_mask": np.zeros(length, dtype=np.uint8),
                        "pause_mask": np.zeros(length, dtype=np.uint8),
                    },
                    "cycle": {
                        "cycle_id": np.asarray([0], dtype=np.int32),
                        "start_step": np.asarray([1], dtype=np.int32),
                        "dump_end_step": np.asarray([94], dtype=np.int32),
                        "end_step": np.asarray([94], dtype=np.int32),
                        "curr_src_sector_id": np.asarray([1], dtype=np.int32),
                        "curr_cut_depth_class": np.asarray([2], dtype=np.int32),
                        "next_src_sector_id": np.asarray([-1], dtype=np.int32),
                        "next_cut_depth_class": np.asarray([-1], dtype=np.int32),
                        "dst_target_id": np.asarray([1], dtype=np.int32),
                        "fill_peak_kg": np.asarray([280.0], dtype=np.float32),
                        "deposit_delta_kg": np.asarray([80.0], dtype=np.float32),
                        "peak_bucket_depth_m": np.asarray([0.36], dtype=np.float32),
                        "collision_count_delta": np.asarray([0], dtype=np.int32),
                        "transition_source": np.asarray(["none"], dtype=str),
                        "plan_source": np.asarray(["none"], dtype=str),
                        "cycle_success": np.asarray([1], dtype=np.uint8),
                    },
                },
            )

            with self.assertRaises(RuntimeError):
                build_workskill_dataset(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    clean_profile=CLEAN_PROFILE_STAGE5_BALANCED,
                )

            self.assertIn("probe_then_reload", (output_dir / "summary.json").read_text())

    def test_load_data_num_episodes_zero_auto_discovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "dataset"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            for episode_id in (0, 2):
                write_episode(
                    dataset_dir / f"episode_{episode_id}.hdf5",
                    qpos=np.zeros((4, 4), dtype=np.float32),
                    qvel=np.zeros((4, 4), dtype=np.float32),
                    actions=np.zeros((4, 4), dtype=np.float32),
                    images={"fpv": np.zeros((4, 4, 4, 3), dtype=np.uint8)},
                    metadata={"scenario_id": "s0_truck"},
                    env_state=np.zeros((4, 9), dtype=np.float32),
                )

            train_loader, val_loader, _, _, split_info = load_data(
                dataset_dir=dataset_dir,
                num_episodes=0,
                camera_names=["fpv"],
                episode_len=4,
                batch_size_train=1,
                batch_size_val=1,
                num_workers=0,
                prefetch_factor=1,
                persistent_workers=False,
                pin_memory=False,
                split_seed=0,
                train_split_ratio=0.5,
                reuse_split=False,
                low_dim_keys=["qpos"],
            )

            self.assertEqual(sorted(split_info["available_episode_ids"]), [0, 2])
            self.assertEqual(len(train_loader.dataset.episode_ids), 1)
            self.assertEqual(len(val_loader.dataset.episode_ids), 1)

    def test_label_episode_v2_1_treats_legacy_success_as_terminal(self) -> None:
        qpos = np.asarray(
            [
                [0.50, 0.41, 0.63, 0.28],
                [0.50, 0.41, 0.63, 0.28],
                [0.50, 0.41, 0.63, 0.28],
                [0.80, 0.41, 0.63, 0.28],
                [0.80, 0.41, 0.63, 0.28],
                [0.80, 0.41, 0.63, 0.28],
            ],
            dtype=np.float32,
        )
        actions = np.asarray(
            [
                [0.0, 0.0, 0.0, 0.0],
                [0.1, 0.0, 0.0, 0.0],
                [0.1, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        env_state = np.asarray(
            [
                [0.0, 0.0, 0.0, 0.0, 1.5, 0.0, 0.0, 0.20, 0.00],
                [120.0, 10.0, 0.0, 0.0, 1.4, 0.0, 0.0, 0.04, 0.03],
                [140.0, 20.0, 0.0, 12.0, 1.0, 0.0, 0.0, 0.03, 0.04],
                [20.0, 20.0, 0.0, 12.0, 1.0, 0.0, 0.0, 0.20, 0.00],
                [10.0, 20.0, 0.0, 12.0, 1.0, 0.0, 0.0, 0.20, 0.00],
                [10.0, 20.0, 0.0, 12.0, 1.0, 0.0, 0.0, 0.20, 0.00],
            ],
            dtype=np.float32,
        )

        v2_payload, _ = label_episode_v2_1(
            qpos=qpos,
            actions=actions,
            env_state=_with_target_geometry(env_state),
            metadata={"success": 1},
            scenario_id="s0_truck",
        )

        self.assertEqual(v2_payload["cycle"]["dump_end_step"].tolist(), [5])
        self.assertEqual(v2_payload["cycle"]["end_step"].tolist(), [5])
        self.assertEqual(v2_payload["cycle"]["cycle_success"].tolist(), [1])


if __name__ == "__main__":
    unittest.main()
