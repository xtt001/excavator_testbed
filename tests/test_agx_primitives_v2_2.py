from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.primitives_v2_2 import (
    build_primitive_datasets,
    extract_workskill_primitive_slices,
)
from testbed.data.v2_1 import GOAL_TOKEN_VERSION, WORK_STAGE_NAME_TO_ID, build_goal_tokens
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


class TestPrimitivesV22(unittest.TestCase):
    def test_build_primitive_datasets_creates_four_sibling_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workskill_dir = tmp / "workskill"
            raw_dir = tmp / "raw"
            output_root = tmp / "primitives"
            workskill_dir.mkdir()
            raw_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")
            _write_raw_episode(raw_dir / "episode_0.hdf5")

            summary = build_primitive_datasets(
                workskill_dir=workskill_dir,
                raw_dirs=[raw_dir],
                output_root=output_root,
            )

            self.assertEqual(summary["primitives"]["dig"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["carry"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["return"]["episode_count"], 1)
            self.assertTrue((output_root / "summary.json").exists())
            for primitive_name in ("dig", "carry", "dump", "return"):
                self.assertTrue((output_root / primitive_name / "episode_0.hdf5").exists())

            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            carry_episode = read_episode(output_root / "carry" / "episode_0.hdf5")
            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            return_episode = read_episode(output_root / "return" / "episode_0.hdf5")

            self.assertEqual(dig_episode["qpos"].shape[0], 3)
            self.assertEqual(carry_episode["qpos"].shape[0], 3)
            self.assertEqual(dump_episode["qpos"].shape[0], 6)
            self.assertEqual(return_episode["qpos"].shape[0], 4)
            self.assertEqual(carry_episode["step_ids"].tolist(), [13, 14, 15])
            self.assertEqual(dump_episode["step_ids"].tolist(), [16, 17, 18, 19, 20, 21])
            self.assertEqual(return_episode["step_ids"].tolist(), [3, 4, 5, 6])
            self.assertEqual(carry_episode["metadata"]["primitive_name"], "carry")
            self.assertEqual(
                carry_episode["metadata"]["primitive_window"],
                "carry_to_before_dump_intent",
            )
            self.assertEqual(int(carry_episode["metadata"]["dump_intent_step"]), 16)
            self.assertEqual(int(carry_episode["metadata"]["official_dump_start_step"]), 19)
            self.assertEqual(dump_episode["metadata"]["primitive_name"], "dump")
            self.assertEqual(return_episode["metadata"]["primitive_name"], "return")
            self.assertEqual(int(return_episode["metadata"]["source_prev_cycle_id"]), 0)
            self.assertEqual(int(return_episode["metadata"]["source_next_cycle_id"]), 1)

    def test_carry_window_excludes_dump_intent_curl_out_segment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")

            build_primitive_datasets(
                workskill_dir=workskill_dir,
                raw_dirs=[],
                output_root=output_root,
                require_return=False,
            )

            carry_episode = read_episode(output_root / "carry" / "episode_0.hdf5")
            carry_bucket_qpos = carry_episode["qpos"][:, 3]
            carry_bucket_action = carry_episode["actions"][:, 3]
            strong_dump = np.logical_and(carry_bucket_qpos >= 0.80, carry_bucket_action <= -0.45)
            self.assertFalse(bool(np.any(strong_dump)))

    def test_dump_starts_before_or_at_official_mass_based_dump_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")

            build_primitive_datasets(
                workskill_dir=workskill_dir,
                raw_dirs=[],
                output_root=output_root,
                require_return=False,
            )

            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            self.assertEqual(dump_episode["step_ids"][0], 16)
            self.assertLessEqual(
                int(dump_episode["metadata"]["dump_intent_step"]),
                int(dump_episode["metadata"]["official_dump_start_step"]),
            )

    def test_return_window_matches_dump_end_to_next_qualified_dig_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            raw_dir = Path(tmpdir) / "raw"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            raw_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")
            _write_raw_episode(raw_dir / "episode_0.hdf5")

            build_primitive_datasets(
                workskill_dir=workskill_dir,
                raw_dirs=[raw_dir],
                output_root=output_root,
            )

            return_episode = read_episode(output_root / "return" / "episode_0.hdf5")
            self.assertEqual(return_episode["step_ids"].tolist(), [3, 4, 5, 6])
            self.assertEqual(return_episode["v2"]["step"]["cycle_id"].tolist(), [0, 0, 0, 1])
            self.assertEqual(
                return_episode["metadata"]["primitive_window"],
                "dump_end_to_next_qualified_dig_start",
            )

    def test_extract_workskill_primitive_slices_rejects_invalid_windows(self) -> None:
        episode = _make_workskill_episode_payload(length=4)
        episode["v2"]["step"]["work_stage_id"] = np.full(
            4,
            WORK_STAGE_NAME_TO_ID["entry_to_bite"],
            dtype=np.uint8,
        )
        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )
        self.assertEqual(slices, [])
        self.assertTrue(any(record.reason == "missing_carry_or_approach_boundary" for record in rejects))
        self.assertTrue(any(record.primitive_name == "dump" for record in rejects))

    def test_primitive_planner_switches_on_synthetic_geometry_events(self) -> None:
        detector = _FakeBoundaryDetector(
            [
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(qualified_dig_start=True),
            ]
        )
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=detector,
            dump_ready_hold_steps=2,
            dump_done_hold_steps=2,
            return_max_steps=20,
            primitive_checkpoint_paths={
                "dig": "dig.ckpt",
                "carry": "carry.ckpt",
                "dump": "dump.ckpt",
                "return": "return.ckpt",
            },
        )

        action = policy.predict(_obs(mass=0.0, dig_distance=0.02))
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")

        action = policy.predict(_obs(mass=320.0, dig_distance=0.30))
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "dig_to_carry_loaded",
        )

        action = policy.predict(_obs(mass=320.0, dig_distance=0.30, dump_ready=True))
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertEqual(policy.debug_state()["dump_ready_hold_count"], 1)

        action = policy.predict(_obs(mass=320.0, dig_distance=0.30, dump_ready=True))
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "carry_to_dump_target_ready",
        )

        action = policy.predict(
            _obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0)
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

        action = policy.predict(
            _obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0)
        )
        self.assertEqual(float(action[0]), 3.0)
        self.assertEqual(policy.debug_state()["skill_name"], "return")
        self.assertEqual(policy.debug_state()["hybrid_mode"], "TRANSITION")

        action = policy.predict(_obs(mass=0.0, dig_distance=0.02))
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertTrue(policy.debug_state()["transition_completed"])
        self.assertEqual(policy.rollout_summary()["completed_transition_count"], 1)

    def test_primitive_planner_accepts_horizontal_target_distance_for_dump_ready(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([_FakeBoundaryEvent(), _FakeBoundaryEvent()]),
            dump_ready_hold_steps=1,
            dump_ready_max_horizontal_distance_m=0.20,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                horizontal_distance=0.15,
                height_above_rim=0.05,
                over_footprint=False,
                clearance_ok=True,
            )
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "carry_to_dump_target_ready",
        )

    def test_primitive_planner_dig_to_carry_uses_loaded_bucket_not_escape_distance(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([_FakeBoundaryEvent()]),
        )

        action = policy.predict(_obs(mass=320.0, dig_distance=0.0))
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "dig_to_carry_loaded",
        )


def _write_workskill_episode(path: Path) -> None:
    episode = _make_workskill_episode_payload(length=12)
    write_episode(path, **episode)


def _make_workskill_episode_payload(length: int) -> dict:
    goal_tokens = np.repeat(
        build_goal_tokens("s0_truck").reshape(1, -1),
        length,
        axis=0,
    ).astype(np.float32)
    qpos = np.zeros((length, 4), dtype=np.float32)
    qpos[:, 0] = 0.50
    qpos[:, 3] = 0.20
    qpos[6:, 3] = 0.85
    actions = np.full((length, 4), 0.05, dtype=np.float32)
    actions[6:8, 3] = -0.50
    actions[9:, 3] = -0.55
    work_stage_id = np.asarray(
        [
            WORK_STAGE_NAME_TO_ID["entry_to_bite"],
            WORK_STAGE_NAME_TO_ID["first_bite"],
            WORK_STAGE_NAME_TO_ID["first_bite"],
            WORK_STAGE_NAME_TO_ID["carry"],
            WORK_STAGE_NAME_TO_ID["carry"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
        ],
        dtype=np.uint8,
    )


    if length != 12:
        work_stage_id = np.resize(work_stage_id, length).astype(np.uint8)
    dump_start_mask = np.zeros(length, dtype=np.uint8)
    dump_end_mask = np.zeros(length, dtype=np.uint8)
    if length > 9:
        dump_start_mask[9] = 1
    if length > 11:
        dump_end_mask[11] = 1

    return {
        "qpos": qpos,
        "qvel": np.zeros((length, 4), dtype=np.float32),
        "actions": actions,
        "images": {"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
        "rewards": np.arange(length, dtype=np.float32),
        "metadata": {
            "scenario_id": "s0_truck",
            "v2_enabled": True,
            "goal_token_version": GOAL_TOKEN_VERSION,
            "source_episode_id": "episode_7",
            "source_cycle_id": 2,
            "source_start_step": 10,
        },
        "env_state": np.zeros((length, 13), dtype=np.float32),
        "step_ids": np.arange(10, 10 + length, dtype=np.int64),
        "step_ns": np.arange(length, dtype=np.int64) * 10,
        "action_src_types": ["teleop"] * length,
        "action_src_ids": [f"src-{i}" for i in range(length)],
        "v2": {
            "step": {
                "cycle_id": np.zeros(length, dtype=np.int32),
                "mode_id": np.zeros(length, dtype=np.uint8),
                "phase_id": np.zeros(length, dtype=np.uint8),
                "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                "work_stage_id": work_stage_id,
                "goal_tokens": goal_tokens,
                "action_loss_mask": np.ones(length, dtype=np.uint8),
                "planner_replan_mask": np.zeros(length, dtype=np.uint8),
                "qualified_dig_start_mask": np.asarray([1] + [0] * (length - 1), dtype=np.uint8),
                "dump_start_mask": dump_start_mask,
                "dump_end_mask": dump_end_mask,
                "boundary_mask": np.zeros(length, dtype=np.uint8),
                "pause_mask": np.zeros(length, dtype=np.uint8),
            },
            "cycle": {},
        },
    }


def _write_raw_episode(path: Path) -> None:
    length = 8
    goal_tokens = np.repeat(
        build_goal_tokens("s0_truck").reshape(1, -1),
        length,
        axis=0,
    ).astype(np.float32)
    write_episode(
        path,
        qpos=np.arange(length * 4, dtype=np.float32).reshape(length, 4),
        qvel=np.zeros((length, 4), dtype=np.float32),
        actions=np.ones((length, 4), dtype=np.float32),
        images={"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
        rewards=np.arange(length, dtype=np.float32),
        metadata={"scenario_id": "s0_truck", "v2_enabled": True},
        env_state=np.zeros((length, 13), dtype=np.float32),
        step_ids=np.arange(length, dtype=np.int64),
        step_ns=np.arange(length, dtype=np.int64) * 10,
        action_src_types=["teleop"] * length,
        action_src_ids=[f"raw-{i}" for i in range(length)],
        v2={
            "step": {
                "cycle_id": np.asarray([-1, 0, 0, 0, 0, 0, 1, 1], dtype=np.int32),
                "mode_id": np.asarray([1, 0, 0, 0, 1, 1, 0, 0], dtype=np.uint8),
                "phase_id": np.asarray([6, 0, 1, 4, 5, 6, 0, 1], dtype=np.uint8),
                "phase_progress": np.linspace(0.0, 1.0, length, dtype=np.float32),
                "work_stage_id": np.zeros(length, dtype=np.uint8),
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


class _ConstantPolicy(Policy):
    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryEvent:
    def __init__(
        self,
        *,
        qualified_dig_start: bool = False,
        dump_end: bool = False,
        metrics: dict | None = None,
    ) -> None:
        self.qualified_dig_start = bool(qualified_dig_start)
        self.dump_end = bool(dump_end)
        self.metrics = dict(metrics or {})


class _FakeBoundaryDetector:
    def __init__(self, events: list[_FakeBoundaryEvent]) -> None:
        self.events = list(events)

    def reset(self) -> None:
        pass

    def update(self, **kwargs) -> _FakeBoundaryEvent:
        if self.events:
            return self.events.pop(0)
        return _FakeBoundaryEvent()


def _obs(
    *,
    mass: float,
    dig_distance: float,
    dump_ready: bool = False,
    deposited: float = 0.0,
    horizontal_distance: float | None = None,
    height_above_rim: float | None = None,
    over_footprint: bool | None = None,
    clearance_ok: bool | None = None,
) -> dict:
    env_state = np.zeros(13, dtype=np.float32)
    env_state[0] = float(mass)
    env_state[3] = float(deposited)
    env_state[7] = float(dig_distance)
    env_state[9] = (
        float(horizontal_distance)
        if horizontal_distance is not None
        else (0.15 if dump_ready else 2.0)
    )
    env_state[10] = (
        float(height_above_rim)
        if height_above_rim is not None
        else (0.05 if dump_ready else -0.20)
    )
    env_state[11] = (
        float(over_footprint)
        if over_footprint is not None
        else (1.0 if dump_ready else 0.0)
    )
    env_state[12] = (
        float(clearance_ok)
        if clearance_ok is not None
        else (1.0 if dump_ready else 0.0)
    )
    return {
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": float(mass),
            "deposited_mass_in_target_box_kg": float(deposited),
            "min_distance_to_dig_area_m": float(dig_distance),
            "target_geometry_available": 1.0,
            "target_horizontal_distance_m": float(env_state[9]),
            "bucket_height_above_target_rim_m": float(env_state[10]),
            "bucket_over_target_footprint_mask": float(env_state[11]),
            "dump_clearance_ok_mask": float(env_state[12]),
        },
    }


if __name__ == "__main__":
    unittest.main()
