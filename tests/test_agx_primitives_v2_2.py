from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_BED_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.primitives_v2_2 import (
    CARRY_ACTION_HORIZON_STEPS,
    CARRY_MIN_WINDOW_LEN,
    build_primitive_datasets,
    build_primitive_datasets_5p,
    extract_workskill_primitive_slices,
    extract_workskill_primitive_slices_5p,
)
from testbed.data.v2_1 import GOAL_TOKEN_VERSION, WORK_STAGE_NAME_TO_ID, build_goal_tokens
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import (
    PrimitivePlannerACT5PPolicy,
    PrimitivePlannerACTPolicy,
)


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
            self.assertEqual(summary["dump_qc"]["accepted_window_count"], 1)
            self.assertFalse(summary["dump_intent_config"]["official_dump_start_fallback"])
            self.assertTrue((output_root / "summary.json").exists())
            for primitive_name in ("dig", "carry", "dump", "return"):
                self.assertTrue((output_root / primitive_name / "episode_0.hdf5").exists())

            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            carry_episode = read_episode(output_root / "carry" / "episode_0.hdf5")
            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            return_episode = read_episode(output_root / "return" / "episode_0.hdf5")

            self.assertEqual(dig_episode["qpos"].shape[0], 20)
            self.assertEqual(carry_episode["qpos"].shape[0], CARRY_MIN_WINDOW_LEN)
            self.assertEqual(dump_episode["qpos"].shape[0], 220)
            self.assertEqual(return_episode["qpos"].shape[0], 4)
            self.assertEqual(carry_episode["step_ids"][0], 30)
            self.assertEqual(carry_episode["step_ids"][-1], 149)
            self.assertEqual(dump_episode["step_ids"][0], 150)
            self.assertEqual(dump_episode["step_ids"][-1], 369)
            self.assertEqual(return_episode["step_ids"].tolist(), [3, 4, 5, 6])
            self.assertEqual(carry_episode["metadata"]["primitive_name"], "carry")
            self.assertEqual(
                carry_episode["metadata"]["primitive_window"],
                "carry_to_before_dump_ownership",
            )
            self.assertEqual(int(carry_episode["metadata"]["dump_intent_step"]), 270)
            self.assertEqual(int(carry_episode["metadata"]["official_dump_start_step"]), 310)
            self.assertEqual(dump_episode["metadata"]["primitive_name"], "dump")
            self.assertEqual(
                dump_episode["metadata"]["primitive_window"],
                "dump_approach_to_dump_end",
            )
            self.assertEqual(int(dump_episode["metadata"]["dump_ownership_start_step"]), 140)
            self.assertEqual(int(dump_episode["metadata"]["dump_approach_steps_before_intent"]), 120)
            self.assertAlmostEqual(
                float(dump_episode["metadata"]["dump_start_height_above_rim_m"]),
                0.60,
            )
            self.assertEqual(return_episode["metadata"]["primitive_name"], "return")
            self.assertEqual(int(return_episode["metadata"]["source_prev_cycle_id"]), 0)
            self.assertEqual(int(return_episode["metadata"]["source_next_cycle_id"]), 1)

    def test_build_primitive_datasets_5p_creates_five_sibling_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workskill_dir = tmp / "workskill"
            raw_dir = tmp / "raw"
            output_root = tmp / "primitives_5p"
            workskill_dir.mkdir()
            raw_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")
            _write_raw_episode(raw_dir / "episode_0.hdf5")

            summary = build_primitive_datasets_5p(
                workskill_dir=workskill_dir,
                raw_dirs=[raw_dir],
                output_root=output_root,
            )

            self.assertEqual(summary["primitive_version"], "v2_2_5primitives")
            for primitive_name in (
                "dig",
                "carry",
                "approach_dump",
                "dump_release",
                "return",
            ):
                self.assertEqual(summary["primitives"][primitive_name]["episode_count"], 1)
                self.assertTrue((output_root / primitive_name / "episode_0.hdf5").exists())
            self.assertEqual(summary["approach_dump_qc"]["accepted_window_count"], 1)

            carry_episode = read_episode(output_root / "carry" / "episode_0.hdf5")
            approach_episode = read_episode(output_root / "approach_dump" / "episode_0.hdf5")
            dump_release_episode = read_episode(output_root / "dump_release" / "episode_0.hdf5")

            self.assertEqual(carry_episode["step_ids"][0], 30)
            self.assertEqual(carry_episode["step_ids"][-1], 149)
            self.assertEqual(approach_episode["step_ids"][0], 150)
            self.assertEqual(approach_episode["step_ids"][-1], 269)
            self.assertEqual(dump_release_episode["step_ids"][0], 270)
            self.assertEqual(dump_release_episode["step_ids"][-1], 369)
            self.assertEqual(
                carry_episode["metadata"]["primitive_window"],
                "carry_to_before_approach_dump",
            )
            self.assertEqual(
                approach_episode["metadata"]["primitive_window"],
                "approach_dump_to_before_dump_release",
            )
            self.assertEqual(
                dump_release_episode["metadata"]["primitive_window"],
                "dump_release_to_dump_end_hold",
            )
            self.assertEqual(int(approach_episode["metadata"]["dump_release_step"]), 270)
            self.assertEqual(int(dump_release_episode["metadata"]["dump_end_step"]), 369)

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
            safe_dump_intent = np.logical_and(
                carry_bucket_qpos >= 0.40,
                carry_bucket_action <= -0.08,
            )
            self.assertFalse(bool(np.any(safe_dump_intent)))
            tail_actions = carry_bucket_action[-CARRY_ACTION_HORIZON_STEPS:]
            stable_tail_curl = np.convolve(
                (tail_actions <= -0.20).astype(np.int32),
                np.ones(5, dtype=np.int32),
                mode="valid",
            )
            self.assertFalse(bool(np.any(stable_tail_curl >= 5)))
            self.assertFalse(
                bool(carry_episode["metadata"]["carry_tail_has_stable_strong_curl_out"])
            )

    def test_5p_carry_excludes_approach_and_release_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")

            build_primitive_datasets_5p(
                workskill_dir=workskill_dir,
                raw_dirs=[],
                output_root=output_root,
                require_return=False,
            )

            carry_episode = read_episode(output_root / "carry" / "episode_0.hdf5")
            self.assertEqual(carry_episode["step_ids"][-1], 149)
            self.assertFalse(
                bool(carry_episode["metadata"]["carry_tail_has_stable_strong_curl_out"])
            )
            self.assertFalse(
                bool(carry_episode["metadata"]["carry_tail_has_stable_release"])
            )

    def test_5p_approach_dump_excludes_stable_release_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            _write_workskill_episode(workskill_dir / "episode_0.hdf5")

            build_primitive_datasets_5p(
                workskill_dir=workskill_dir,
                raw_dirs=[],
                output_root=output_root,
                require_return=False,
            )

            approach_episode = read_episode(output_root / "approach_dump" / "episode_0.hdf5")
            tail_actions = approach_episode["actions"][-CARRY_ACTION_HORIZON_STEPS:, 3]
            tail_qpos = approach_episode["qpos"][-CARRY_ACTION_HORIZON_STEPS:, 3]
            release_tail = np.logical_and(tail_qpos >= 0.40, tail_actions <= -0.08)
            stable_tail_release = np.convolve(
                release_tail.astype(np.int32),
                np.ones(3, dtype=np.int32),
                mode="valid",
            )
            self.assertFalse(bool(np.any(stable_tail_release >= 3)))
            self.assertFalse(
                bool(approach_episode["metadata"]["approach_dump_tail_has_stable_release"])
            )
            self.assertAlmostEqual(
                float(approach_episode["metadata"]["approach_dump_bucket_mass_loss_kg"]),
                0.0,
            )

    def test_5p_approach_dump_allows_mild_human_mixed_curl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            episode = _make_workskill_episode_payload(length=360)
            episode["qpos"][180:210, 3] = 0.55
            episode["actions"][180:210, 3] = -0.05
            write_episode(workskill_dir / "episode_0.hdf5", **episode)

            build_primitive_datasets_5p(
                workskill_dir=workskill_dir,
                raw_dirs=[],
                output_root=output_root,
                require_return=False,
            )

            approach_episode = read_episode(output_root / "approach_dump" / "episode_0.hdf5")
            mild_mixed_curl = np.logical_and(
                approach_episode["qpos"][:, 3] >= 0.50,
                approach_episode["actions"][:, 3] < 0.0,
            )
            stable_release = np.logical_and(
                approach_episode["qpos"][:, 3] >= 0.40,
                approach_episode["actions"][:, 3] <= -0.08,
            )
            self.assertTrue(bool(np.any(mild_mixed_curl)))
            self.assertFalse(bool(np.any(stable_release)))

    def test_5p_builder_rejects_approach_mass_loss_before_release(self) -> None:
        episode = _make_workskill_episode_payload(length=360)
        episode["env_state"][200:260, ENV_STATE_MASS_IN_BUCKET_IDX] = 300.0

        slices, rejects = extract_workskill_primitive_slices_5p(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "approach_dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "approach_dump"
                and record.reason == "approach_dump_mass_loss_before_release"
                for record in rejects
            )
        )

    def test_dump_owns_approach_before_release_intent(self) -> None:
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
            self.assertEqual(dump_episode["step_ids"][0], 150)
            self.assertEqual(int(dump_episode["metadata"]["dump_ownership_start_step"]), 140)
            self.assertEqual(int(dump_episode["metadata"]["dump_approach_steps_before_intent"]), 120)
            self.assertLessEqual(
                int(dump_episode["metadata"]["dump_intent_step"]),
                int(dump_episode["metadata"]["official_dump_start_step"]),
            )

    def test_carry_ownership_rejects_too_short_window(self) -> None:
        episode = _make_workskill_episode_payload(length=180)
        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "carry" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "carry"
                and record.reason == "carry_too_short_before_dump_ownership"
                for record in rejects
            )
        )
        self.assertTrue(any(item.primitive_name == "dump" for item in slices))

    def test_carry_ownership_does_not_treat_curled_in_saturation_as_dump(self) -> None:
        episode = _make_workskill_episode_payload(length=360)
        episode["qpos"][20:80, 3] = 0.0
        episode["actions"][20:80, 3] = -0.70

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        carry = next(item for item in slices if item.primitive_name == "carry")
        self.assertEqual(carry.window_len, 120)
        self.assertFalse(any(record.primitive_name == "carry" for record in rejects))

    def test_stable_curl_out_before_approach_is_rejected(self) -> None:
        episode = _make_workskill_episode_payload(length=360)
        work_stage_id = episode["v2"]["step"]["work_stage_id"]
        work_stage_id[20:180] = WORK_STAGE_NAME_TO_ID["carry"]
        work_stage_id[180:300] = WORK_STAGE_NAME_TO_ID["approach_dump"]
        episode["qpos"][150:260, 3] = 0.60
        episode["actions"][150:260, 3] = -0.25

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "carry" for item in slices))
        self.assertFalse(any(item.primitive_name == "dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "carry"
                and record.reason == "carry_release_before_approach_dump_stage"
                for record in rejects
            )
        )
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and record.reason == "release_before_approach_dump_stage"
                for record in rejects
            )
        )

    def test_4p_builder_rejects_old_env_state_without_bed_geometry(self) -> None:
        episode = _make_workskill_episode_payload(length=360, include_bed_geometry=False)

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "carry" for item in slices))
        self.assertFalse(any(item.primitive_name == "dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "carry"
                and record.reason == "missing_bed_geometry_for_dump_intent"
                for record in rejects
            )
        )
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and record.reason == "missing_bed_geometry_for_dump_intent"
                for record in rejects
            )
        )

    def test_dump_builder_rejects_instead_of_falling_back_to_official_dump_start(self) -> None:
        episode = _make_workskill_episode_payload(length=12)
        episode["actions"][:, 3] = 0.05

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and record.reason == "missing_safe_dump_intent"
                for record in rejects
            )
        )

    def test_good_dump_quality_accepts_missing_strict_safe_intent(self) -> None:
        episode = _make_workskill_episode_payload(length=360)
        episode["qpos"][:300, 3] = 0.20
        episode["actions"][:300, 3] = 0.0
        episode["qpos"][300:, 3] = 0.85
        episode["actions"][300:, 3] = -0.55
        _mark_good_dump_quality(episode, official_dump_start=300)

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        carry = next(item for item in slices if item.primitive_name == "carry")
        dump = next(item for item in slices if item.primitive_name == "dump")
        self.assertEqual(carry.end_step_exclusive, 140)
        self.assertEqual(dump.start_step, 140)
        self.assertEqual(dump.dump_intent_step, 310)
        self.assertEqual(dump.dump_qc["dump_acceptance_mode"], "good_dump_quality")
        self.assertFalse(
            any(
                record.primitive_name in {"carry", "dump"}
                and record.reason == "missing_safe_dump_intent"
                for record in rejects
            )
        )

    def test_good_dump_quality_shifts_pre_approach_release_into_dump(self) -> None:
        episode = _make_workskill_episode_payload(length=360)
        work_stage_id = episode["v2"]["step"]["work_stage_id"]
        work_stage_id[20:200] = WORK_STAGE_NAME_TO_ID["carry"]
        work_stage_id[200:300] = WORK_STAGE_NAME_TO_ID["approach_dump"]
        episode["qpos"][160:300, 3] = 0.60
        episode["actions"][160:300, 3] = -0.25
        _mark_good_dump_quality(episode, official_dump_start=300)

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        carry = next(item for item in slices if item.primitive_name == "carry")
        dump = next(item for item in slices if item.primitive_name == "dump")
        self.assertEqual(carry.end_step_exclusive, 160)
        self.assertEqual(dump.start_step, 160)
        self.assertEqual(
            dump.dump_qc["dump_ownership_boundary_source"],
            "pre_approach_stable_curl_out_good_dump",
        )
        self.assertEqual(dump.dump_qc["dump_acceptance_mode"], "good_dump_quality")
        self.assertFalse(
            any(
                record.primitive_name in {"carry", "dump"}
                and record.reason
                in {
                    "carry_release_before_approach_dump_stage",
                    "release_before_approach_dump_stage",
                }
                for record in rejects
            )
        )

    def test_dump_qc_rejects_unsafe_first20_height_or_clearance(self) -> None:
        episode = _make_workskill_episode_payload(length=12)
        episode["env_state"][9, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = -0.10

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and record.reason == "dump_first20_height_below_rim"
                for record in rejects
            )
        )

        episode = _make_workskill_episode_payload(length=12)
        episode["env_state"][9, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = -0.10
        episode["env_state"][9, ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 0.0
        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and "dump_first20_clearance_lost"
                in str((record.details or {}).get("dump_intent_reject_reasons", ""))
                for record in rejects
            )
        )

    def test_dump_qc_allows_small_rim_tolerance_without_collision(self) -> None:
        episode = _make_workskill_episode_payload(length=12)
        episode["env_state"][9, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = -0.05
        episode["env_state"][9, ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 0.0

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertTrue(any(item.primitive_name == "dump" for item in slices))
        self.assertFalse(
            any(
                record.primitive_name == "dump"
                and record.reason
                in {"dump_first20_height_below_rim", "dump_first20_clearance_lost"}
                for record in rejects
            )
        )

    def test_dump_qc_rejects_hard_collision_window(self) -> None:
        episode = _make_workskill_episode_payload(length=12)
        episode["env_state"][10:, ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX] = 1.0

        slices, rejects = extract_workskill_primitive_slices(
            episode=episode,
            source_path=Path("episode_0.hdf5"),
            source_dataset_dir=Path("."),
        )

        self.assertFalse(any(item.primitive_name == "dump" for item in slices))
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and record.reason == "dump_hard_collision"
                for record in rejects
            )
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

    def test_primitive_planner_injects_goal_tokens_for_sequence(self) -> None:
        dig_policy = _RecordingPolicy(0)
        return_policy = _RecordingPolicy(3)
        detector = _FakeBoundaryDetector(
            [
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(qualified_dig_start=True),
            ]
        )
        policy = PrimitivePlannerACTPolicy(
            dig_policy=dig_policy,
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=return_policy,
            boundary_detector=detector,
            goal_sequence=["mid", "left", "right"],
            goal_scenario_id="s0_truck",
            dump_ready_hold_steps=1,
            dump_done_hold_steps=1,
            dump_done_use_boundary_event=False,
        )

        policy.predict(_obs(mass=0.0, dig_distance=0.02))
        np.testing.assert_allclose(dig_policy.last_goal_tokens[:3], [0.0, 1.0, 0.0])
        np.testing.assert_allclose(dig_policy.last_goal_tokens[4:7], [1.0, 0.0, 0.0])

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        policy.predict(_obs(mass=320.0, dig_distance=0.30, dump_ready=True))
        policy.predict(_obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0))
        policy.predict(_obs(mass=0.0, dig_distance=0.02))
        np.testing.assert_allclose(return_policy.last_goal_tokens[:3], [0.0, 1.0, 0.0])
        np.testing.assert_allclose(return_policy.last_goal_tokens[4:7], [1.0, 0.0, 0.0])

        policy.predict(_obs(mass=0.0, dig_distance=0.02))
        np.testing.assert_allclose(dig_policy.last_goal_tokens[:3], [1.0, 0.0, 0.0])
        np.testing.assert_allclose(dig_policy.last_goal_tokens[4:7], [0.0, 0.0, 1.0])
        self.assertEqual(policy.debug_state()["primitive_goal_curr_sector_id"], 0)
        self.assertEqual(policy.debug_state()["primitive_goal_next_sector_id"], 2)

    def test_primitive_planner_can_wait_past_dump_end_boundary_for_hold(self) -> None:
        detector = _FakeBoundaryDetector(
            [
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(dump_end=True),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
            ]
        )
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=detector,
            dump_ready_hold_steps=1,
            dump_done_hold_steps=2,
            dump_done_use_boundary_event=False,
        )

        policy.predict(_obs(mass=0.0, dig_distance=0.02))
        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(_obs(mass=320.0, dig_distance=0.30, dump_ready=True))
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

        action = policy.predict(
            _obs(mass=320.0, dig_distance=0.30, dump_ready=True, deposited=0.0)
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")
        self.assertNotEqual(
            policy.debug_state()["skill_switch_reason"],
            "dump_to_return_dump_end",
        )

        action = policy.predict(
            _obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0)
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["dump_done_hold_count"], 1)

        action = policy.predict(
            _obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0)
        )
        self.assertEqual(float(action[0]), 3.0)
        self.assertEqual(policy.debug_state()["skill_name"], "return")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "dump_to_return_mass_low",
        )

    def test_primitive_planner_uses_dump_end_boundary_by_default(self) -> None:
        detector = _FakeBoundaryDetector(
            [
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(dump_end=True),
            ]
        )
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=detector,
            dump_ready_hold_steps=1,
            dump_done_hold_steps=30,
        )

        policy.predict(_obs(mass=0.0, dig_distance=0.02))
        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        policy.predict(_obs(mass=320.0, dig_distance=0.30, dump_ready=True))
        action = policy.predict(
            _obs(mass=320.0, dig_distance=0.30, dump_ready=True, deposited=0.0)
        )
        self.assertEqual(float(action[0]), 3.0)
        self.assertEqual(policy.debug_state()["skill_name"], "return")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "dump_to_return_dump_end",
        )

    def test_primitive_planner_uses_bed_relative_readiness_not_horizontal_only(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([_FakeBoundaryEvent(), _FakeBoundaryEvent()]),
            dump_ready_hold_steps=1,
            dump_ready_max_horizontal_distance_m=0.60,
            dump_ready_min_height_above_rim_m=0.45,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                horizontal_distance=0.60,
                height_above_rim=0.45,
                over_footprint=False,
                clearance_ok=True,
                bed_footprint_outside_distance=0.30,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                horizontal_distance=0.60,
                height_above_rim=0.45,
                over_footprint=False,
                clearance_ok=True,
                bed_footprint_outside_distance=0.03,
            )
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "carry_to_dump_target_ready",
        )

    def test_primitive_planner_does_not_bypass_position_when_footprint_not_required(
        self,
    ) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([_FakeBoundaryEvent(), _FakeBoundaryEvent()]),
            dump_ready_hold_steps=1,
            dump_ready_min_height_above_rim_m=0.30,
            dump_ready_require_over_footprint=False,
            dump_ready_require_clearance=False,
            dump_ready_position_mode="bed_relative",
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_max_bed_footprint_outside_distance_m=1.25,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                over_footprint=False,
                clearance_ok=False,
                bed_footprint_outside_distance=2.40,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                over_footprint=False,
                clearance_ok=False,
                bed_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

    def test_primitive_planner_uses_signed_bed_relative_window(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector(
                [_FakeBoundaryEvent(), _FakeBoundaryEvent(), _FakeBoundaryEvent()]
            ),
            dump_ready_hold_steps=1,
            dump_ready_min_height_above_rim_m=0.30,
            dump_ready_require_over_footprint=False,
            dump_ready_require_clearance=False,
            dump_ready_position_mode="bed_relative",
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_max_bed_footprint_outside_distance_m=1.35,
            dump_ready_min_bed_relative_x_m=-5.0,
            dump_ready_max_bed_relative_x_m=2.0,
            dump_ready_min_bed_relative_z_m=2.75,
            dump_ready_max_bed_relative_z_m=3.50,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                bed_relative_x=-6.20,
                bed_relative_z=3.10,
                bed_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                bed_relative_x=-3.20,
                bed_relative_z=2.40,
                bed_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                bed_relative_x=-3.20,
                bed_relative_z=3.10,
                bed_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

    def test_primitive_planner_blocks_low_height_even_when_horizontally_close(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([_FakeBoundaryEvent(), _FakeBoundaryEvent()]),
            dump_ready_hold_steps=1,
            dump_ready_max_horizontal_distance_m=0.82,
            dump_ready_min_height_above_rim_m=0.45,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                horizontal_distance=0.15,
                height_above_rim=0.20,
                over_footprint=True,
                clearance_ok=True,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

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

    def test_5p_primitive_planner_switches_on_synthetic_geometry_events(self) -> None:
        detector = _FakeBoundaryDetector(
            [
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(),
                _FakeBoundaryEvent(qualified_dig_start=True),
            ]
        )
        policy = PrimitivePlannerACT5PPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            approach_dump_policy=_ConstantPolicy(2),
            dump_release_policy=_ConstantPolicy(3),
            return_policy=_ConstantPolicy(4),
            boundary_detector=detector,
            approach_ready_hold_steps=2,
            dump_release_ready_hold_steps=2,
            dump_done_hold_steps=2,
            primitive_checkpoint_paths={
                "dig": "dig.ckpt",
                "carry": "carry.ckpt",
                "approach_dump": "approach_dump.ckpt",
                "dump_release": "dump_release.ckpt",
                "return": "return.ckpt",
            },
        )

        action = policy.predict(_obs(mass=0.0, dig_distance=0.02))
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")

        action = policy.predict(_obs(mass=320.0, dig_distance=0.30))
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        approach_obs = _obs(
            mass=320.0,
            dig_distance=0.30,
            horizontal_distance=1.20,
            height_above_rim=0.0,
            over_footprint=False,
            clearance_ok=True,
        )
        action = policy.predict(approach_obs)
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["approach_ready_hold_count"], 1)

        action = policy.predict(approach_obs)
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "approach_dump")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "carry_to_approach_dump_region_ready",
        )

        dump_ready_obs = _obs(
            mass=320.0,
            dig_distance=0.30,
            horizontal_distance=0.60,
            height_above_rim=0.45,
            over_footprint=False,
            clearance_ok=True,
            bed_footprint_outside_distance=0.03,
        )
        action = policy.predict(dump_ready_obs)
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["dump_release_ready_hold_count"], 1)

        action = policy.predict(dump_ready_obs)
        self.assertEqual(float(action[0]), 3.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump_release")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "approach_dump_to_dump_release_ready",
        )

        action = policy.predict(
            _obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0)
        )
        self.assertEqual(float(action[0]), 3.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump_release")

        action = policy.predict(
            _obs(mass=50.0, dig_distance=0.30, dump_ready=True, deposited=20.0)
        )
        self.assertEqual(float(action[0]), 4.0)
        self.assertEqual(policy.debug_state()["skill_name"], "return")

        action = policy.predict(_obs(mass=0.0, dig_distance=0.02))
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertTrue(policy.debug_state()["transition_completed"])
        self.assertEqual(policy.rollout_summary()["completed_transition_count"], 1)


def _write_workskill_episode(path: Path) -> None:
    episode = _make_workskill_episode_payload(length=360)
    write_episode(path, **episode)


def _make_workskill_episode_payload(
    length: int,
    *,
    include_bed_geometry: bool = True,
) -> dict:
    if length >= 320:
        carry_start = 20
        approach_start = 140
        dump_intent_start = 260
        official_dump_start = 300
    elif length >= 180:
        carry_start = 20
        approach_start = 60
        dump_intent_start = 120
        official_dump_start = 150
    else:
        carry_start = 3
        approach_start = 5
        dump_intent_start = 6
        official_dump_start = 9
    official_dump_start = min(official_dump_start, max(0, length - 3))
    dump_intent_start = min(dump_intent_start, max(0, official_dump_start - 3))
    approach_start = min(approach_start, max(0, dump_intent_start - 1))
    carry_start = min(carry_start, max(0, approach_start - 1))

    goal_tokens = np.repeat(
        build_goal_tokens("s0_truck").reshape(1, -1),
        length,
        axis=0,
    ).astype(np.float32)
    qpos = np.zeros((length, 4), dtype=np.float32)
    qpos[:, 0] = 0.50
    qpos[:, 3] = 0.20
    qpos[dump_intent_start:, 3] = 0.85
    actions = np.full((length, 4), 0.05, dtype=np.float32)
    actions[dump_intent_start:official_dump_start, 3] = -0.10
    actions[official_dump_start:, 3] = -0.55
    work_stage_id = np.full(
        length,
        WORK_STAGE_NAME_TO_ID["first_bite"],
        dtype=np.uint8,
    )
    work_stage_id[0] = WORK_STAGE_NAME_TO_ID["entry_to_bite"]
    work_stage_id[carry_start:approach_start] = WORK_STAGE_NAME_TO_ID["carry"]
    work_stage_id[approach_start:official_dump_start] = WORK_STAGE_NAME_TO_ID["approach_dump"]
    work_stage_id[official_dump_start:] = WORK_STAGE_NAME_TO_ID["dump"]
    dump_start_mask = np.zeros(length, dtype=np.uint8)
    dump_end_mask = np.zeros(length, dtype=np.uint8)
    dump_start_mask[official_dump_start] = 1
    dump_end_mask[length - 1] = 1

    env_state_width = 16 if include_bed_geometry else 13
    env_state = np.zeros((length, env_state_width), dtype=np.float32)
    env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] = 500.0
    env_state[:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 0.0
    env_state[:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.30
    env_state[:, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.60
    env_state[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.60
    env_state[:, ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 0.0
    env_state[:, ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
    if include_bed_geometry:
        # Approach starts outside the truck-top release zone and moves inward.
        env_state[:, ENV_STATE_BUCKET_BED_RELATIVE_X_IDX] = -1.50
        env_state[:, ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX] = 2.80
        env_state[:, ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.00
        if approach_start < length:
            approach_len = max(1, official_dump_start - approach_start)
            env_state[
                approach_start:official_dump_start,
                ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
            ] = np.linspace(0.90, 0.30, approach_len, dtype=np.float32)
            env_state[approach_start:official_dump_start, ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX] = np.linspace(
                2.90,
                2.35,
                approach_len,
                dtype=np.float32,
            )
        env_state[dump_intent_start:, ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.30
        env_state[official_dump_start:, ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.20
        env_state[official_dump_start:, ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX] = 2.25

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
        "env_state": env_state,
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


def _mark_good_dump_quality(episode: dict, *, official_dump_start: int) -> None:
    official_dump_start = int(official_dump_start)
    length = int(len(episode["actions"]))
    release_len = max(1, length - official_dump_start)
    episode["env_state"][:, ENV_STATE_MASS_IN_BUCKET_IDX] = 500.0
    episode["env_state"][official_dump_start:, ENV_STATE_MASS_IN_BUCKET_IDX] = np.linspace(
        500.0,
        0.0,
        release_len,
        dtype=np.float32,
    )
    episode["env_state"][:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 0.0
    episode["env_state"][
        official_dump_start:,
        ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ] = np.linspace(
        0.0,
        420.0,
        release_len,
        dtype=np.float32,
    )
    episode["v2"]["cycle"] = {
        "cycle_success": np.asarray([1], dtype=np.uint8),
        "deposit_delta_kg": np.asarray([420.0], dtype=np.float32),
        "collision_count_delta": np.asarray([0], dtype=np.int32),
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


class _RecordingPolicy(_ConstantPolicy):
    def __init__(self, value: float) -> None:
        super().__init__(value)
        self.last_goal_tokens: np.ndarray | None = None

    def predict(self, obs: dict) -> np.ndarray:
        self.last_goal_tokens = np.asarray(obs.get("goal_tokens"), dtype=np.float32)
        return super().predict(obs)


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
    bed_relative_x: float = 0.0,
    bed_relative_z: float = 0.0,
    bed_footprint_outside_distance: float | None = None,
) -> dict:
    env_state = np.zeros(16, dtype=np.float32)
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
        else (0.50 if dump_ready else -0.20)
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
    if bed_footprint_outside_distance is None:
        bed_footprint_outside_distance = 0.0 if bool(env_state[11] > 0.5) else float(env_state[9])
    env_state[ENV_STATE_BUCKET_BED_RELATIVE_X_IDX] = float(bed_relative_x)
    env_state[ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX] = float(bed_relative_z)
    env_state[ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = float(
        bed_footprint_outside_distance
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
            "bucket_bed_relative_x_m": float(
                env_state[ENV_STATE_BUCKET_BED_RELATIVE_X_IDX]
            ),
            "bucket_bed_relative_z_m": float(
                env_state[ENV_STATE_BUCKET_BED_RELATIVE_Z_IDX]
            ),
            "bucket_bed_footprint_outside_distance_m": float(
                env_state[ENV_STATE_BUCKET_BED_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
            ),
        },
    }


if __name__ == "__main__":
    unittest.main()
