from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.data.operator_first_v2_2 import build_live_dig_cut_tokens_from_pose
from testbed.data.dataset import get_norm_stats
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.primitives_v2_2 import (
    CARRY_ACTION_HORIZON_STEPS,
    CARRY_MIN_WINDOW_LEN,
    PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    _return_target_reject_reason,
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


REPO_ROOT = Path(__file__).resolve().parents[1]
YULONG_DIG_CUT_PRIOR_PATH = (
    REPO_ROOT
    / "testbed/configs/planner_priors/yulong_operator_first_dig_cut_prior_v1.json"
)


class TestPrimitivesV22(unittest.TestCase):
    def test_yulong_operator_prior_json_matches_committed_gold_statistics(self) -> None:
        with YULONG_DIG_CUT_PRIOR_PATH.open("r", encoding="utf-8") as handle:
            prior = json.load(handle)

        self.assertEqual(prior["prior_id"], "yulong_operator_first_dig_cut_prior_v1")
        self.assertEqual(prior["schema_version"], "v1")
        self.assertEqual(
            prior["dig_cut_token_contract"], "v2_2_operator_first_cut_v1"
        )
        self.assertEqual(len(prior["token_order"]), 10)
        source = prior["source"]
        self.assertEqual(source["source_episode_count"], 26)
        self.assertEqual(source["source_cycle_count_all"], 649)
        self.assertEqual(source["source_cycle_count_used"], 640)
        self.assertEqual(source["excluded_cycle_count"], 9)
        self.assertEqual(source["tier_filter"], "gold")
        self.assertEqual(
            source["source_lineage_git_commit"],
            "8ad9721f4ad79aaf1c5dcb7c4c28c566f5b46e7f",
        )
        self.assertEqual(source["prior_builder_git_commit"], "2568a7c")

        expected = {
            "entry_x_m": (0.4148, 0.9226, 1.3053),
            "entry_z_m": (-1.0327, -0.3382, 0.6171),
            "exit_x_m": (-0.5777, 0.0595, 0.8601),
            "exit_z_m": (-0.8376, -0.2309, 0.54),
            "cut_direction_x": (-0.9726, -0.8189, 0.2026),
            "cut_direction_z": (-0.1904, 0.0655, 0.3364),
            "cut_length_m": (0.7381, 1.1568, 1.6275),
            "cut_depth_peak_m": (0.8524, 1.0339, 1.1767),
            "payload_gain_kg": (48.3301, 59.0535, 74.2262),
            "effective_deposit_delta_kg": (42.4849, 56.7207, 68.7807),
        }
        for field_name, (p10, p50, p90) in expected.items():
            stats = prior["fields"][field_name]
            self.assertAlmostEqual(float(stats["p10"]), p10, places=4)
            self.assertAlmostEqual(float(stats["p50"]), p50, places=4)
            self.assertAlmostEqual(float(stats["p90"]), p90, places=4)

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

    def test_direct_raw_modes_support_manifest_vds_and_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            raw_dir.mkdir()
            raw_episode = _make_workskill_episode_payload(length=360)
            raw_episode["metadata"] = {"scenario_id": "s0_truck", "v2_enabled": True}
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0], dtype=np.int32),
                "start_step": np.asarray([0], dtype=np.int32),
                "end_step": np.asarray([359], dtype=np.int32),
                "cycle_success": np.asarray([1], dtype=np.uint8),
                "stage_success": np.asarray([1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0], dtype=np.float32),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            manifest_root = tmp / "primitive_manifest"
            manifest_summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=manifest_root,
                require_return=False,
                storage_mode="manifest",
            )
            self.assertEqual(manifest_summary["storage_mode"], "manifest")
            self.assertEqual(
                manifest_summary["primitives"]["dig"]["episode_count"], 1
            )
            self.assertTrue((manifest_root / "window_manifest.json").exists())
            self.assertFalse(list(manifest_root.rglob("episode_*.hdf5")))

            vds_root = tmp / "primitive_vds"
            vds_summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=vds_root,
                require_return=False,
                storage_mode="vds",
            )
            self.assertEqual(vds_summary["storage_mode"], "vds")
            dig_episode = read_episode(vds_root / "dig" / "episode_0.hdf5")
            self.assertEqual(dig_episode["qpos"].shape[0], 20)
            with h5py.File(vds_root / "dig" / "episode_0.hdf5", "r") as f:
                self.assertTrue(f["observations/qpos"].is_virtual)
                self.assertTrue(f["observations/images/fpv"].is_virtual)
                self.assertEqual(f["metadata"].attrs["storage_mode"], "vds")

            copy_root = tmp / "primitive_copy"
            copy_summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=copy_root,
                require_return=False,
                storage_mode="copy",
            )
            self.assertEqual(copy_summary["storage_mode"], "copy")
            copy_dig_episode = read_episode(copy_root / "dig" / "episode_0.hdf5")
            self.assertEqual(copy_dig_episode["qpos"].shape[0], 20)
            self.assertIn("fpv", copy_dig_episode["images"])
            with h5py.File(copy_root / "dig" / "episode_0.hdf5", "r") as f:
                self.assertFalse(f["observations/qpos"].is_virtual)
                self.assertFalse(f["observations/images/fpv"].is_virtual)

    def test_direct_raw_build_discards_cycle_overlapping_realign_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            first = _make_workskill_episode_payload(length=360)
            second = _make_workskill_episode_payload(length=360)
            raw_episode = _concat_raw_cycles(first, second)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "replay_pose_realign_steps": "100",
            }
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 360], dtype=np.int32),
                "end_step": np.asarray([359, 719], dtype=np.int32),
                "dump_end_step": np.asarray([359, 719], dtype=np.int32),
                "cycle_success": np.asarray([1, 1], dtype=np.uint8),
                "stage_success": np.asarray([1, 1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0, 420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                require_return=False,
                storage_mode="copy",
            )

            self.assertEqual(summary["primitives"]["dig"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["carry"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 1)
            self.assertEqual(
                summary["reject_counts"].get("cycle:cycle_contains_pose_realign"),
                1,
            )
            reject = next(
                item
                for item in summary["rejects"]
                if item["reason"] == "cycle_contains_pose_realign"
            )
            self.assertEqual(reject["source_cycle_id"], 0)
            self.assertEqual(reject["details"]["realign_steps_in_window"], [100])

            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            self.assertEqual(int(dig_episode["metadata"]["source_cycle_id"]), 1)
            self.assertEqual(int(dig_episode["metadata"]["source_start_step"]), 360)

    def test_direct_raw_cycle_crop_prefers_dump_end_over_next_start_end_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            raw_episode = _make_workskill_episode_payload(length=960)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
            }
            raw_episode["v2"]["step"]["cycle_id"][:] = 0
            raw_episode["v2"]["step"]["cycle_id"][600:] = 1
            raw_episode["v2"]["step"]["mode_id"][360:600] = 1
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 600], dtype=np.int32),
                "dump_end_step": np.asarray([359, -1], dtype=np.int32),
                "end_step": np.asarray([599, -1], dtype=np.int32),
                "cycle_success": np.asarray([1, 0], dtype=np.uint8),
                "stage_success": np.asarray([1, 0], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0, 0.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                require_return=False,
                storage_mode="copy",
            )

            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 1)
            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            self.assertEqual(dump_episode["qpos"].shape[0], 220)
            self.assertEqual(int(dump_episode["metadata"]["source_start_step"]), 140)
            self.assertEqual(int(dump_episode["metadata"]["source_end_step_exclusive"]), 360)
            self.assertFalse(np.any(dump_episode["v2"]["step"]["mode_id"] == 1))

    def test_direct_raw_realign_during_return_discards_full_logical_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            raw_episode = _make_workskill_episode_payload(length=960)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "replay_pose_realign_steps": "450",
            }
            work_stage_id = raw_episode["v2"]["step"]["work_stage_id"]
            work_stage_id[600:620] = WORK_STAGE_NAME_TO_ID["first_bite"]
            work_stage_id[620:740] = WORK_STAGE_NAME_TO_ID["carry"]
            work_stage_id[740:860] = WORK_STAGE_NAME_TO_ID["approach_dump"]
            work_stage_id[860:] = WORK_STAGE_NAME_TO_ID["dump"]
            raw_episode["qpos"][600:, 3] = 0.20
            raw_episode["qpos"][840:, 3] = 0.85
            raw_episode["actions"][600:840, 3] = 0.05
            raw_episode["actions"][840:860, 3] = -0.10
            raw_episode["actions"][860:, 3] = -0.55
            raw_episode["v2"]["step"]["dump_start_mask"][860] = 1
            raw_episode["v2"]["step"]["cycle_id"][:] = 0
            raw_episode["v2"]["step"]["cycle_id"][600:] = 1
            raw_episode["v2"]["step"]["mode_id"][360:600] = 1
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 600], dtype=np.int32),
                "dump_end_step": np.asarray([359, 959], dtype=np.int32),
                "end_step": np.asarray([599, 959], dtype=np.int32),
                "cycle_success": np.asarray([1, 1], dtype=np.uint8),
                "stage_success": np.asarray([1, 1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0, 420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                require_return=False,
                storage_mode="copy",
            )

            self.assertEqual(summary["primitives"]["dig"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["carry"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 1)
            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            self.assertEqual(int(dig_episode["metadata"]["source_cycle_id"]), 1)
            self.assertEqual(
                summary["reject_counts"].get("cycle:cycle_contains_pose_realign"),
                1,
            )
            reject = next(
                item
                for item in summary["rejects"]
                if item["reason"] == "cycle_contains_pose_realign"
            )
            self.assertEqual(reject["details"]["realign_steps_in_window"], [450])
            self.assertEqual(
                reject["details"]["policy"],
                "discard_full_cycle_including_return",
            )
            self.assertEqual(reject["details"]["work_end_step_exclusive"], 360)
            self.assertEqual(
                reject["details"]["realign_reject_end_step_exclusive"],
                600,
            )

    def test_direct_raw_realign_at_next_qds_belongs_to_next_cycle_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            raw_episode = _make_workskill_episode_payload(length=960)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "replay_pose_realign_steps": "600",
            }
            raw_episode["v2"]["step"]["cycle_id"][:] = 0
            raw_episode["v2"]["step"]["cycle_id"][600:] = 1
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 600], dtype=np.int32),
                "dump_end_step": np.asarray([359, 959], dtype=np.int32),
                "end_step": np.asarray([600, 959], dtype=np.int32),
                "cycle_success": np.asarray([1, 1], dtype=np.uint8),
                "stage_success": np.asarray([1, 1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0, 420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                require_return=False,
                storage_mode="copy",
            )

            self.assertEqual(summary["primitives"]["dig"]["episode_count"], 1)
            self.assertEqual(
                summary["reject_counts"].get("cycle:cycle_contains_pose_realign"),
                1,
            )
            reject = next(
                item
                for item in summary["rejects"]
                if item["reason"] == "cycle_contains_pose_realign"
            )
            self.assertEqual(reject["source_cycle_id"], 1)
            self.assertEqual(reject["details"]["realign_steps_in_window"], [600])

            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            self.assertEqual(int(dig_episode["metadata"]["source_cycle_id"]), 0)

    def test_spatial_mass_profile_splits_four_primitives_and_return_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            first = _make_workskill_episode_payload(length=360)
            second = _make_workskill_episode_payload(length=360)
            _mark_good_dump_quality(first, official_dump_start=300)
            _mark_good_dump_quality(second, official_dump_start=300)
            _pad_spatial_mass_env(first, offset=0)
            _pad_spatial_mass_env(second, offset=1)
            raw_episode = _concat_raw_cycles(first, second)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "source_episode_id": "episode_0",
            }
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 360], dtype=np.int32),
                "dump_end_step": np.asarray([359, 719], dtype=np.int32),
                "end_step": np.asarray([359, 719], dtype=np.int32),
                "cycle_success": np.asarray([1, 1], dtype=np.uint8),
                "stage_success": np.asarray([1, 1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0, 420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
                "training_tier": np.asarray(["gold", "gold"], dtype=object),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                storage_mode="copy",
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
                return_max_transition_len=512,
            )

            self.assertEqual(summary["primitive_version"], "v2_4_5_spatial_mass_4primitives")
            self.assertEqual(summary["primitives"]["dig"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["carry"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["return"]["episode_count"], 1)
            self.assertEqual(
                summary["reject_counts"].get("return:terminal_return_reject"),
                1,
            )

            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            self.assertEqual(
                dig_episode["metadata"]["dig_end_source"],
                "mass_plateau_and_dig_area_departure",
            )
            self.assertGreaterEqual(
                int(dig_episode["metadata"]["source_end_step_exclusive"]),
                80,
            )

            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            self.assertEqual(
                dump_episode["metadata"]["primitive_version"],
                "v2_4_5_spatial_mass_4primitives",
            )
            lead = int(dump_episode["metadata"]["dump_pre_release_lead_steps"])
            self.assertLessEqual(lead, 120)
            self.assertGreaterEqual(int(dump_episode["step_ids"][0]), 260)
            self.assertIn(
                dump_episode["metadata"]["dump_start_source"],
                {
                    "dump_area_committed_aiming_band",
                    "late_pre_release_aiming_fallback",
                    "release_onset_no_aiming_candidate",
                },
            )

            return_episode = read_episode(output_root / "return" / "episode_0.hdf5")
            envelope = return_episode["v2"]["step"]["return_start_envelope_tokens_v1"]
            valid_mask = return_episode["v2"]["step"]["return_start_envelope_valid_mask"]
            self.assertEqual(envelope.shape[-1], 18)
            self.assertEqual(valid_mask.shape, envelope.shape)
            self.assertTrue(np.all(valid_mask == 1))
            self.assertAlmostEqual(float(envelope[0, 0]), 0.35, places=4)
            self.assertAlmostEqual(float(envelope[0, 1]), 0.50, places=4)
            self.assertEqual(
                return_episode["metadata"]["primitive_window"],
                "dump_end_to_next_dig_start_envelope",
            )
            stats = get_norm_stats(
                output_root / "return",
                num_episodes=1,
                low_dim_keys=[
                    "qpos",
                    "qvel",
                    "return_start_envelope_tokens_v1",
                ],
            )
            self.assertEqual(stats["proprio_mean"].shape[0], 26)

    def test_spatial_mass_dump_start_waits_for_relative_aiming_band(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            episode = _make_workskill_episode_payload(length=460)
            _mark_good_dump_quality(episode, official_dump_start=340)
            _pad_spatial_mass_env(episode, offset=0)
            env = episode["env_state"]
            env[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.70
            env[:, ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 0.0
            env[:, ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 0.0
            env[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.20
            env[220:340, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.10
            env[340:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.0
            env[:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 3.0
            env[:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 3.0
            env[220:310, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = np.linspace(
                2.0,
                0.70,
                90,
                dtype=np.float32,
            )
            env[220:310, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = np.linspace(
                2.20,
                1.00,
                90,
                dtype=np.float32,
            )
            env[310:340, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = np.linspace(
                0.70,
                0.65,
                30,
                dtype=np.float32,
            )
            env[310:340, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = np.linspace(
                1.00,
                0.95,
                30,
                dtype=np.float32,
            )
            env[340:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.65
            env[340:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 0.95
            episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0], dtype=np.int32),
                "start_step": np.asarray([0], dtype=np.int32),
                "dump_end_step": np.asarray([459], dtype=np.int32),
                "end_step": np.asarray([459], dtype=np.int32),
                "cycle_success": np.asarray([1], dtype=np.uint8),
                "stage_success": np.asarray([1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0], dtype=np.int32),
                "training_tier": np.asarray(["gold"], dtype=object),
            }
            write_episode(raw_dir / "episode_0.hdf5", **episode)

            build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                require_return=False,
                storage_mode="copy",
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
            )

            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            self.assertGreaterEqual(
                int(dump_episode["metadata"]["source_start_step"]),
                309,
            )
            self.assertLess(
                int(dump_episode["metadata"]["source_start_step"]),
                340,
            )
            self.assertEqual(
                dump_episode["metadata"]["dump_start_source"],
                "dump_area_committed_aiming_band",
            )
            self.assertLessEqual(
                float(dump_episode["metadata"]["dump_start_selected_relative_x_range_m"]),
                0.25,
            )

    def test_spatial_mass_profile_uses_physical_dump_end_before_legacy_work_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            first = _make_workskill_episode_payload(length=900)
            second = _make_workskill_episode_payload(length=360)
            _mark_good_dump_quality(first, official_dump_start=300)
            _mark_good_dump_quality(second, official_dump_start=300)
            _pad_spatial_mass_env(first, offset=0)
            _pad_spatial_mass_env(second, offset=1)
            first["env_state"][:, ENV_STATE_MASS_IN_BUCKET_IDX] = 50.0
            first["env_state"][:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 0.0
            first["env_state"][:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.2
            first["env_state"][250:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.2
            first["env_state"][300:381, ENV_STATE_MASS_IN_BUCKET_IDX] = np.linspace(
                50.0,
                0.0,
                81,
                dtype=np.float32,
            )
            first["env_state"][381:, ENV_STATE_MASS_IN_BUCKET_IDX] = 0.0
            first["env_state"][300:381, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = np.linspace(
                0.0,
                60.0,
                81,
                dtype=np.float32,
            )
            first["env_state"][381:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 60.0
            raw_episode = _concat_raw_cycles(first, second)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "source_episode_id": "episode_0",
            }
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 900], dtype=np.int32),
                "dump_end_step": np.asarray([899, 1259], dtype=np.int32),
                "end_step": np.asarray([899, 1259], dtype=np.int32),
                "cycle_success": np.asarray([1, 1], dtype=np.uint8),
                "stage_success": np.asarray([1, 1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([60.0, 420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
                "training_tier": np.asarray(["gold", "gold"], dtype=object),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                storage_mode="copy",
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
                return_max_transition_len=512,
            )

            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["return"]["episode_count"], 1)
            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            self.assertLess(dump_episode["qpos"].shape[0], 220)
            self.assertGreaterEqual(int(dump_episode["step_ids"][0]), 250)
            self.assertLess(int(dump_episode["step_ids"][-1]), 450)
            self.assertEqual(
                dump_episode["metadata"]["dump_end_source"],
                "residual_mass_deposit_plateau",
            )
            self.assertEqual(int(dump_episode["metadata"]["dump_legacy_work_end_step"]), 900)

    def test_return_start_envelope_keeps_core_valid_with_partial_spatial_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            first = _make_workskill_episode_payload(length=360)
            second = _make_workskill_episode_payload(length=360)
            _mark_good_dump_quality(first, official_dump_start=300)
            _mark_good_dump_quality(second, official_dump_start=300)
            _pad_spatial_mass_env(first, offset=0)
            _pad_spatial_mass_env(second, offset=1)
            second["env_state"][:40, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 0.0
            second["env_state"][:40, ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = np.nan
            second["env_state"][:40, ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = np.nan
            second["env_state"][:40, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = np.nan
            raw_episode = _concat_raw_cycles(first, second)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "source_episode_id": "episode_0",
            }
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0, 1], dtype=np.int32),
                "start_step": np.asarray([0, 360], dtype=np.int32),
                "dump_end_step": np.asarray([359, 719], dtype=np.int32),
                "end_step": np.asarray([359, 719], dtype=np.int32),
                "cycle_success": np.asarray([1, 1], dtype=np.uint8),
                "stage_success": np.asarray([1, 1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([420.0, 420.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0, 0], dtype=np.int32),
                "training_tier": np.asarray(["gold", "gold"], dtype=object),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                storage_mode="copy",
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
                return_max_transition_len=512,
            )

            self.assertEqual(summary["return_qc"]["envelope_valid_count"], 1)
            return_episode = read_episode(output_root / "return" / "episode_0.hdf5")
            envelope = return_episode["v2"]["step"]["return_start_envelope_tokens_v1"]
            valid_mask = return_episode["v2"]["step"]["return_start_envelope_valid_mask"]
            self.assertEqual(float(envelope[0, 16]), 1.0)
            self.assertEqual(int(valid_mask[0, 0]), 0)
            self.assertTrue(np.all(valid_mask[0, 7:18] == 1))

    def test_spatial_mass_profile_splits_multi_qds_old_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw_enriched"
            output_root = tmp / "primitive_copy"
            raw_dir.mkdir()

            first = _make_workskill_episode_payload(length=360)
            second = _make_workskill_episode_payload(length=360)
            _mark_good_dump_quality(first, official_dump_start=300)
            _mark_good_dump_quality(second, official_dump_start=300)
            _pad_spatial_mass_env(first, offset=0)
            _pad_spatial_mass_env(second, offset=1)
            raw_episode = _concat_raw_cycles(first, second)
            raw_episode["metadata"] = {
                "scenario_id": "s0_truck",
                "v2_enabled": True,
                "source_episode_id": "episode_0",
            }
            raw_episode["v2"]["cycle"] = {
                "cycle_id": np.asarray([0], dtype=np.int32),
                "start_step": np.asarray([0], dtype=np.int32),
                "dump_end_step": np.asarray([719], dtype=np.int32),
                "end_step": np.asarray([719], dtype=np.int32),
                "cycle_success": np.asarray([1], dtype=np.uint8),
                "stage_success": np.asarray([1], dtype=np.uint8),
                "deposit_delta_kg": np.asarray([840.0], dtype=np.float32),
                "collision_count_delta": np.asarray([0], dtype=np.int32),
                "training_tier": np.asarray(["gold"], dtype=object),
            }
            write_episode(raw_dir / "episode_0.hdf5", **raw_episode)

            summary = build_primitive_datasets(
                raw_dirs=[raw_dir],
                output_root=output_root,
                storage_mode="copy",
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
                return_max_transition_len=512,
            )

            self.assertEqual(summary["primitives"]["dig"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["carry"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 2)
            self.assertEqual(summary["primitives"]["return"]["episode_count"], 1)
            second_dig = read_episode(output_root / "dig" / "episode_1.hdf5")
            self.assertEqual(int(second_dig["step_ids"][0]), 360)

    def test_primitive_split_preserves_source_cycle_qc_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            workskill_dir = tmp / "workskill"
            raw_dir = tmp / "raw"
            output_root = tmp / "primitives"
            workskill_dir.mkdir()
            raw_dir.mkdir()
            episode = _make_workskill_episode_payload(length=360)
            _mark_good_dump_quality(episode, official_dump_start=300)
            episode["v2"]["cycle"].update(
                {
                    "cycle_id": np.asarray([2], dtype=np.int32),
                    "stage_success": np.asarray([1], dtype=np.uint8),
                    "stage_success_flags": np.asarray([15], dtype=np.uint8),
                    "stage_failure_reason_code": np.asarray([0], dtype=np.uint8),
                    "payload_gain_kg": np.asarray([120.0], dtype=np.float32),
                    "dump_deposited_fraction": np.asarray([0.75], dtype=np.float32),
                    "cell_entry_planner_ok": np.asarray([1], dtype=np.uint8),
                }
            )
            write_episode(workskill_dir / "episode_0.hdf5", **episode)
            _write_raw_episode(raw_dir / "episode_0.hdf5")

            build_primitive_datasets(
                workskill_dir=workskill_dir,
                raw_dirs=[raw_dir],
                output_root=output_root,
            )

            dig_episode = read_episode(output_root / "dig" / "episode_0.hdf5")
            self.assertEqual(dig_episode["v2"]["cycle"]["cycle_id"].tolist(), [0])
            self.assertEqual(dig_episode["v2"]["cycle"]["stage_success"].tolist(), [1])
            self.assertEqual(int(dig_episode["metadata"]["stage_success"]), 1)
            self.assertEqual(int(dig_episode["metadata"]["stage_success_flags"]), 15)
            self.assertAlmostEqual(
                float(dig_episode["metadata"]["payload_gain_kg"]),
                120.0,
            )

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

    def test_effect_release_fallback_splits_when_approach_stage_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workskill_dir = Path(tmpdir) / "workskill"
            output_root = Path(tmpdir) / "primitives"
            workskill_dir.mkdir()
            episode = _make_workskill_episode_payload(length=360)
            work_stage_id = episode["v2"]["step"]["work_stage_id"]
            work_stage_id[work_stage_id == WORK_STAGE_NAME_TO_ID["approach_dump"]] = (
                WORK_STAGE_NAME_TO_ID["carry"]
            )
            _mark_good_dump_quality(episode, official_dump_start=300)
            write_episode(workskill_dir / "episode_0.hdf5", **episode)

            summary = build_primitive_datasets(
                workskill_dir=workskill_dir,
                raw_dirs=[],
                output_root=output_root,
                require_return=False,
                boundary_profile=PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
            )

            self.assertEqual(summary["primitives"]["carry"]["episode_count"], 1)
            self.assertEqual(summary["primitives"]["dump"]["episode_count"], 1)
            self.assertTrue(summary["dump_ownership_config"]["effect_release_fallback_enabled"])
            carry_episode = read_episode(output_root / "carry" / "episode_0.hdf5")
            dump_episode = read_episode(output_root / "dump" / "episode_0.hdf5")
            self.assertEqual(carry_episode["step_ids"][-1], 269)
            self.assertEqual(dump_episode["step_ids"][0], 270)
            self.assertEqual(
                dump_episode["metadata"]["dump_ownership_boundary_source"],
                "pre_approach_stable_curl_out_good_dump",
            )
            self.assertEqual(
                dump_episode["metadata"]["primitive_boundary_profile"],
                PRIMITIVE_BOUNDARY_PROFILE_EFFECT_RELEASE_FALLBACK,
            )
            self.assertFalse(
                bool(carry_episode["metadata"]["carry_tail_has_stable_release"])
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

    def test_4p_builder_rejects_old_env_state_without_dump_area_geometry(self) -> None:
        episode = _make_workskill_episode_payload(length=360, include_dump_area_geometry=False)

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
                and record.reason == "missing_dump_area_geometry_for_dump_intent"
                for record in rejects
            )
        )
        self.assertTrue(
            any(
                record.primitive_name == "dump"
                and record.reason == "missing_dump_area_geometry_for_dump_intent"
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

    def test_conditioned_return_rejects_terminal_target_source(self) -> None:
        episode = _make_workskill_episode_payload(length=8)
        episode["v2"]["cycle"] = {
            "cycle_id": np.asarray([0], dtype=np.int32),
            "return_target_source": np.asarray(["terminal_none"], dtype=str),
            "next_operator_cut_valid": np.asarray([0], dtype=np.uint8),
        }

        self.assertEqual(
            _return_target_reject_reason(episode=episode, source_cycle_id=0),
            "return_target_unavailable:terminal_none",
        )

        episode["v2"]["cycle"]["return_target_source"] = np.asarray(
            ["operator_next_entry"], dtype=str
        )
        episode["v2"]["cycle"]["next_operator_cut_valid"] = np.asarray(
            [1], dtype=np.uint8
        )
        self.assertIsNone(
            _return_target_reject_reason(episode=episode, source_cycle_id=0)
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

    def test_primitive_planner_supports_scripted_qpos_bootstrap(self) -> None:
        target_qpos = np.asarray([0.50, 0.58, 0.62, 0.11], dtype=np.float32)
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            bootstrap_end_mode="scripted_qpos",
            scripted_bootstrap_target_qpos=target_qpos,
            scripted_bootstrap_action_clip=[0.75, 0.35, 0.35, 0.55],
            scripted_bootstrap_hold_steps=1,
        )

        action = policy.predict(_obs(mass=0.0, dig_distance=0.20))
        self.assertEqual(policy.debug_state()["skill_name"], "bootstrap")
        self.assertGreater(float(action[0]), 0.0)
        self.assertGreater(float(action[1]), 0.0)

        obs = _obs(mass=0.0, dig_distance=0.20)
        obs["qpos"] = target_qpos.copy()
        obs["qvel"] = np.zeros(4, dtype=np.float32)
        action = policy.predict(obs)
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "bootstrap_to_dig",
        )

    def test_primitive_planner_scripted_qpos_bootstrap_action_signs(self) -> None:
        target_qpos = np.asarray([0.50, 0.58, 0.62, 0.11], dtype=np.float32)
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            bootstrap_end_mode="scripted_qpos",
            scripted_bootstrap_target_qpos=target_qpos,
            scripted_bootstrap_action_clip=[0.75, 0.35, 0.35, 0.55],
            scripted_bootstrap_action_signs=[1.0, -1.0, 1.0, 1.0],
        )

        obs = _obs(mass=0.0, dig_distance=0.20)
        obs["qpos"] = np.asarray([0.50, 0.42, 0.62, 0.50], dtype=np.float32)
        obs["qvel"] = np.zeros(4, dtype=np.float32)
        action = policy.predict(obs)

        self.assertLess(float(action[1]), 0.0)
        self.assertLess(float(action[3]), 0.0)

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

    def test_primitive_planner_injects_cell_entry_tokens_only_for_dig(self) -> None:
        dig_policy = _RecordingPolicy(0)
        carry_policy = _RecordingPolicy(1)
        policy = PrimitivePlannerACTPolicy(
            dig_policy=dig_policy,
            carry_policy=carry_policy,
            dump_policy=_RecordingPolicy(2),
            return_policy=_RecordingPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            cell_entry_enabled=True,
            dig_to_carry_min_bucket_mass_kg=20.0,
            dig_to_carry_min_distance_to_dig_area_m=0.0,
        )

        action = policy.predict(_cell_entry_obs(mass=0.0, dig_distance=0.0))
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertTrue(policy.debug_state()["cell_entry_token_injected"])
        self.assertEqual(dig_policy.last_cell_entry_tokens.shape, (10,))
        self.assertEqual(
            int(policy.debug_state()["cell_entry_selected_cell_id"]),
            2,
        )

        action = policy.predict(_cell_entry_obs(mass=50.0, dig_distance=0.1))
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertFalse(policy.debug_state()["cell_entry_token_injected"])
        self.assertIsNone(carry_policy.last_cell_entry_tokens)

    def test_primitive_planner_conservative_dig_cut_mode_matches_legacy_token(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = PrimitivePlannerACTPolicy(
            dig_policy=dig_policy,
            carry_policy=_RecordingPolicy(1),
            dump_policy=_RecordingPolicy(2),
            return_policy=_RecordingPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            dig_cut_planner={
                "enabled": True,
                "mode": "conservative_pose",
                "fallback_mode": "conservative_pose",
                "hold_token_until_skill_exit": False,
            },
        )

        pose = (0.8, 0.0, -0.3)
        policy.predict(_dig_cut_obs(mass=0.0, dig_distance=0.0, pose=pose))

        np.testing.assert_allclose(
            dig_policy.last_dig_cut_tokens,
            build_live_dig_cut_tokens_from_pose(pose),
        )
        state = policy.debug_state()
        self.assertEqual(state["dig_cut_planner_mode"], "conservative_pose")
        self.assertEqual(state["dig_cut_token_source"], "conservative_pose")
        self.assertTrue(state["dig_cut_token_injected"])

    def test_primitive_planner_operator_prior_locks_token_for_dig_cycle(self) -> None:
        dig_policy = _RecordingPolicy(0)
        carry_policy = _RecordingPolicy(1)
        policy = PrimitivePlannerACTPolicy(
            dig_policy=dig_policy,
            carry_policy=carry_policy,
            dump_policy=_RecordingPolicy(2),
            return_policy=_RecordingPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            dig_to_carry_min_bucket_mass_kg=20.0,
            dig_to_carry_min_distance_to_dig_area_m=0.0,
            dig_cut_planner={
                "enabled": True,
                "mode": "operator_prior",
                "prior_path": str(YULONG_DIG_CUT_PRIOR_PATH),
                "fallback_mode": "conservative_pose",
                "hold_token_until_skill_exit": True,
            },
        )

        policy.predict(_dig_cut_obs(mass=0.0, dig_distance=0.0, pose=(9.0, 0.0, 9.0)))
        first_token = np.asarray(dig_policy.last_dig_cut_tokens, dtype=np.float32)
        self.assertEqual(first_token.shape, (10,))
        self.assertTrue(np.all(np.isfinite(first_token)))
        self.assertEqual(float(first_token[-1]), 1.0)
        state = policy.debug_state()
        self.assertEqual(state["dig_cut_planner_mode"], "operator_prior")
        self.assertEqual(
            state["dig_cut_prior_id"], "yulong_operator_first_dig_cut_prior_v1"
        )
        self.assertEqual(state["dig_cut_token_source"], "operator_prior_pose_clamped")
        self.assertTrue(state["token_in_prior_p10_p90"])

        policy.predict(_dig_cut_obs(mass=0.0, dig_distance=0.0, pose=(-9.0, 0.0, -9.0)))
        np.testing.assert_allclose(dig_policy.last_dig_cut_tokens, first_token)

        policy.predict(_dig_cut_obs(mass=50.0, dig_distance=0.1, pose=(-9.0, 0.0, -9.0)))
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertFalse(policy.debug_state()["dig_cut_token_injected"])
        self.assertIsNone(carry_policy.last_dig_cut_tokens)

    def test_primitive_planner_operator_prior_uses_median_when_pose_missing(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = PrimitivePlannerACTPolicy(
            dig_policy=dig_policy,
            carry_policy=_RecordingPolicy(1),
            dump_policy=_RecordingPolicy(2),
            return_policy=_RecordingPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            dig_cut_planner={
                "enabled": True,
                "mode": "operator_prior",
                "prior_path": str(YULONG_DIG_CUT_PRIOR_PATH),
                "fallback_mode": "conservative_pose",
                "hold_token_until_skill_exit": True,
            },
        )

        policy.predict(_obs(mass=0.0, dig_distance=0.0))

        self.assertEqual(dig_policy.last_dig_cut_tokens.shape, (10,))
        state = policy.debug_state()
        self.assertEqual(state["dig_cut_token_source"], "operator_prior_median_pose_fallback")
        self.assertEqual(state["fallback_reason"], "missing_bucket_dig_area_pose")
        self.assertTrue(state["token_in_prior_p10_p90"])

    def test_primitive_planner_coverage_outputs_finite_token_in_prior_range(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(dig_policy=dig_policy)

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))

        token = np.asarray(dig_policy.last_dig_cut_tokens, dtype=np.float32)
        self.assertEqual(token.shape, (10,))
        self.assertTrue(np.all(np.isfinite(token)))
        self.assertEqual(float(token[-1]), 1.0)
        state = policy.debug_state()
        self.assertEqual(state["dig_cut_planner_mode"], "operator_prior_coverage")
        self.assertEqual(state["dig_cut_token_source"], "operator_prior_coverage")
        self.assertTrue(state["dig_cut_token_in_prior_p10_p90"])
        self.assertEqual(state["coverage_corridor_id"], 0)
        self.assertEqual(len(state["coverage_corridors"]), 9)
        self.assertGreaterEqual(state["coverage_entry_x_m"], 0.4148 - 1.0e-4)
        self.assertLessEqual(state["coverage_entry_x_m"], 1.3053 + 1.0e-4)
        self.assertGreaterEqual(state["coverage_entry_z_m"], -1.0327 - 1.0e-4)
        self.assertLessEqual(state["coverage_entry_z_m"], 0.6171 + 1.0e-4)

    def test_primitive_planner_coverage_first_dig_prefers_bootstrap_friendly_corridor(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            coverage_extra={
                "first_dig_strategy": "bootstrap_friendly",
                "first_dig_preferred_corridor_id": 1,
                "first_dig_preferred_bonus": 10000.0,
            },
        )

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        state = policy.debug_state()

        self.assertEqual(state["coverage_corridor_id"], 1)
        self.assertEqual(state["coverage_first_dig_strategy"], "bootstrap_friendly")
        self.assertEqual(state["coverage_first_dig_preferred_corridor_id"], 1)
        bonus_by_corridor = {
            int(item["corridor_id"]): float(item["first_dig_bonus"])
            for item in state["coverage_candidate_scores"]
        }
        self.assertGreater(bonus_by_corridor[1], 0.0)
        self.assertEqual(bonus_by_corridor[0], 0.0)

    def test_primitive_planner_coverage_first_dig_prefers_nearest_entry(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            coverage_extra={
                "first_dig_strategy": "nearest_entry",
                "first_dig_proximity_weight": 8.0,
            },
        )

        policy.predict(
            _coverage_obs(
                mass=0.0,
                dig_distance=0.0,
                bucket_pose=(-0.88, 0.0, -0.16),
            )
        )
        state = policy.debug_state()

        self.assertEqual(state["coverage_corridor_id"], 3)
        self.assertEqual(state["coverage_first_dig_strategy"], "nearest_entry")
        scores = {
            int(item["corridor_id"]): float(item["first_dig_bonus"])
            for item in state["coverage_candidate_scores"]
        }
        self.assertGreater(scores[3], scores[0])
        self.assertGreater(scores[3], scores[1])

    def test_primitive_planner_coverage_first_dig_reachability_gate(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            coverage_extra={
                "first_dig_strategy": "nearest_entry",
                "first_dig_proximity_weight": 0.0,
                "first_dig_max_entry_distance_m": 0.05,
            },
        )

        policy.predict(
            _coverage_obs(
                mass=0.0,
                dig_distance=0.0,
                bucket_pose=(0.4148, 0.0, -0.3382),
            )
        )
        state = policy.debug_state()

        self.assertEqual(state["coverage_corridor_id"], 3)
        self.assertAlmostEqual(
            float(state["coverage_first_dig_max_entry_distance_m"]),
            0.05,
            places=6,
        )
        candidate_by_id = {
            int(item["corridor_id"]): item
            for item in state["coverage_candidate_scores"]
        }
        self.assertEqual(int(candidate_by_id[3]["first_dig_reachable"]), 1)
        self.assertEqual(int(candidate_by_id[3]["first_dig_gated_out"]), 0)
        self.assertEqual(int(candidate_by_id[0]["first_dig_gate_applied"]), 1)
        self.assertEqual(int(candidate_by_id[0]["first_dig_gated_out"]), 1)

    def test_primitive_planner_coverage_first_dig_qpos_reachability_gate(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            pre_dig_align_enabled=True,
            coverage_extra={
                "first_dig_strategy": "nearest_entry",
                "first_dig_proximity_weight": 8.0,
                "first_dig_max_qpos_delta": [0.20, 0.20, 0.10, 0.20],
            },
        )

        obs = _coverage_obs(
            mass=0.0,
            dig_distance=0.0,
            bucket_pose=(-0.88, 0.0, -0.16),
        )
        obs["qpos"] = np.asarray([0.50, 0.60, 0.10, 0.20], dtype=np.float32)
        policy.predict(obs)
        state = policy.debug_state()

        self.assertEqual(state["coverage_corridor_id"], 4)
        candidate_by_id = {
            int(item["corridor_id"]): item
            for item in state["coverage_candidate_scores"]
        }
        self.assertEqual(int(candidate_by_id[3]["first_dig_entry_reachable"]), 1)
        self.assertEqual(int(candidate_by_id[3]["first_dig_qpos_reachable"]), 0)
        self.assertEqual(int(candidate_by_id[3]["first_dig_gated_out"]), 1)
        self.assertEqual(int(candidate_by_id[4]["first_dig_qpos_reachable"]), 1)
        self.assertLess(
            float(candidate_by_id[4]["first_dig_qpos_delta_norm"]),
            float(candidate_by_id[3]["first_dig_qpos_delta_norm"]),
        )

    def test_primitive_planner_coverage_can_request_deeper_payload_prior(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            coverage_extra={
                "cut_depth_percentile": "p90",
                "payload_percentile": "p90",
            },
        )
        policy._ensure_coverage_corridors()

        raw_fields = policy._coverage_raw_fields(policy._coverage_corridors[0])

        self.assertAlmostEqual(
            float(raw_fields["operator_cut_depth_peak_m"]),
            1.1767,
            places=4,
        )
        self.assertAlmostEqual(
            float(raw_fields["operator_cut_payload_gain_kg"]),
            74.2262,
            places=4,
        )

    def test_primitive_planner_coverage_locks_token_within_dig_cycle(self) -> None:
        dig_policy = _RecordingPolicy(0)
        carry_policy = _RecordingPolicy(1)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            carry_policy=carry_policy,
            dig_to_carry_min_bucket_mass_kg=20.0,
        )

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        first_token = np.asarray(dig_policy.last_dig_cut_tokens, dtype=np.float32)
        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0, removed_cell0=0.08))
        np.testing.assert_allclose(dig_policy.last_dig_cut_tokens, first_token)

        policy.predict(_coverage_obs(mass=30.0, dig_distance=0.1))
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertFalse(policy.debug_state()["dig_cut_token_injected"])
        self.assertIsNone(carry_policy.last_dig_cut_tokens)

    def test_primitive_planner_coverage_avoids_depleted_corridor(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(dig_policy=dig_policy)

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        first_corridor_id = int(policy.debug_state()["coverage_corridor_id"])
        active = policy._coverage_active_corridor()
        self.assertIsNotNone(active)
        active.depleted = True
        policy._clear_dig_cut_plan()
        policy._cycle_index += 1

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        self.assertNotEqual(
            int(policy.debug_state()["coverage_corridor_id"]),
            first_corridor_id,
        )

    def test_primitive_planner_coverage_penalizes_recent_row(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            coverage_extra={
                "use_env_removed_depth": False,
                "recent_row_selection_penalty": 1.5,
            },
        )
        policy._ensure_coverage_corridors()
        policy._coverage_last_selected_corridor_id = 1

        selected = policy._select_coverage_corridor(
            _coverage_obs(mass=0.0, dig_distance=0.0)
        )

        self.assertEqual(int(selected.corridor_id), 3)
        penalty_by_corridor = {
            int(item["corridor_id"]): float(item["recent_row_penalty"])
            for item in policy._coverage_candidate_scores
        }
        self.assertEqual(penalty_by_corridor[0], 1.5)
        self.assertEqual(penalty_by_corridor[2], 1.5)
        self.assertEqual(penalty_by_corridor[3], 0.0)

    def test_primitive_planner_coverage_attempt_limit_depletes_corridor(self) -> None:
        policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
        policy._ensure_coverage_corridors()
        corridor = policy._coverage_corridors[0]
        policy._coverage_active_corridor_id = int(corridor.corridor_id)
        policy._coverage_current_payload_gain_kg = 50.0
        policy._coverage_cycle_start_deposit_kg = 0.0

        for _ in range(policy.coverage_max_attempts_per_corridor):
            policy._complete_coverage_dump(
                _coverage_obs(mass=0.0, dig_distance=0.0),
                reason="unit_test",
            )

        self.assertTrue(corridor.depleted)
        self.assertEqual(corridor.last_reason, "attempt_limit_reached")

    def test_primitive_planner_coverage_terminal_stop_when_all_depleted(self) -> None:
        policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
        policy._ensure_coverage_corridors()
        for corridor in policy._coverage_corridors:
            corridor.depleted = True

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))

        state = policy.debug_state()
        self.assertTrue(state["planner_terminal_stop_requested"])
        self.assertEqual(state["planner_terminal_stop_reason"], "dig_area_depleted")

    def test_primitive_planner_injects_return_target_only_for_return_and_reuses_for_dig(self) -> None:
        dig_policy = _RecordingPolicy(0)
        return_policy = _RecordingPolicy(3)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            return_policy=return_policy,
            return_target_enabled=True,
            dig_to_carry_min_bucket_mass_kg=20.0,
        )

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        policy.predict(_coverage_obs(mass=200.0, dig_distance=0.1))
        for _ in range(policy.dump_ready_hold_steps):
            policy.predict(
                _coverage_obs(mass=200.0, dig_distance=0.1, dump_ready=True)
            )
        for _ in range(policy.dump_done_hold_steps):
            policy.predict(
                _coverage_obs(
                    mass=0.0,
                    dig_distance=0.1,
                    dump_ready=True,
                    deposited=45.0,
                )
            )

        self.assertEqual(policy.debug_state()["skill_name"], "return")
        self.assertIsNotNone(return_policy.last_return_target_tokens)
        return_token = np.asarray(
            return_policy.last_return_target_tokens,
            dtype=np.float32,
        )
        self.assertEqual(return_token.shape, (10,))
        self.assertEqual(float(return_token[-1]), 1.0)
        self.assertTrue(policy.debug_state()["return_target_token_injected"])
        self.assertTrue(policy.debug_state()["return_start_envelope_token_injected"])
        self.assertIsNotNone(return_policy.last_return_start_envelope_tokens)
        envelope_token = np.asarray(
            return_policy.last_return_start_envelope_tokens,
            dtype=np.float32,
        )
        self.assertEqual(envelope_token.shape, (18,))
        self.assertEqual(float(envelope_token[16]), 1.0)
        self.assertFalse(policy.debug_state()["dig_cut_token_injected"])

        policy._cycle_index += 1
        policy._set_skill("dig", "unit_test_return_to_dig")
        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        np.testing.assert_allclose(dig_policy.last_dig_cut_tokens, return_token)
        self.assertEqual(policy.debug_state()["dig_cut_token_source"], "pending_return_target")

    def test_primitive_planner_sweep_belief_does_not_depend_on_removed_depth(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            dig_cut_mode="operator_prior_sweep_belief",
            coverage_extra={"use_env_removed_depth": False},
        )

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0, removed_cell0=0.08))

        state = policy.debug_state()
        self.assertEqual(state["dig_cut_planner_mode"], "operator_prior_sweep_belief")
        self.assertFalse(state["coverage_use_env_removed_depth"])
        self.assertEqual(np.asarray(dig_policy.last_dig_cut_tokens).shape, (10,))

    def test_primitive_planner_sweep_belief_updates_corridor_on_dump(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            dig_cut_mode="operator_prior_sweep_belief",
            coverage_extra={"use_env_removed_depth": False},
        )
        policy._ensure_coverage_corridors()
        corridor = policy._coverage_corridors[0]
        policy._coverage_active_corridor_id = int(corridor.corridor_id)
        policy._coverage_current_payload_gain_kg = 8.0
        policy._coverage_cycle_start_deposit_kg = 0.0

        policy._complete_coverage_dump(
            _coverage_obs(mass=0.0, dig_distance=0.0, deposited=7.0),
            reason="unit_test_low_productivity",
        )

        self.assertEqual(corridor.attempts, 1)
        self.assertGreater(corridor.low_productivity_streak, 0)
        self.assertGreater(corridor.belief_coverage, 0.0)

    def test_primitive_planner_bad_dig_replans_without_align(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            dig_cut_mode="operator_prior_sweep_belief",
            dig_bad_replan_enabled=True,
            pre_dig_align_enabled=False,
            coverage_extra={"use_env_removed_depth": False},
        )

        for _ in range(policy.dig_bad_replan_max_steps):
            policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "dig")
        self.assertEqual(state["dig_bad_replan_count"], 1)
        self.assertEqual(state["skill_switch_reason"], "dig_retry_bad_dig_low_payload")
        self.assertFalse(state["pre_dig_align_enabled"])

    def test_primitive_planner_bad_dig_replans_when_current_mass_drops(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            dig_to_carry_min_bucket_mass_kg=100.0,
            dig_bad_replan_enabled=True,
            pre_dig_align_enabled=False,
            coverage_extra={"use_env_removed_depth": False},
        )

        policy.predict(_coverage_obs(mass=20.0, dig_distance=0.0))
        for _ in range(policy.dig_bad_replan_max_steps - 1):
            policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "dig")
        self.assertEqual(state["dig_best_mass_kg"], 0.0)
        self.assertEqual(state["dig_bad_replan_count"], 1)
        self.assertEqual(state["skill_switch_reason"], "dig_retry_bad_dig_low_payload")
        self.assertEqual(
            policy._coverage_corridors[0].last_reason,
            "bad_dig_low_payload",
        )

    def test_primitive_planner_exit_guard_replans_after_low_payload_overshoot(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            dig_to_carry_min_bucket_mass_kg=100.0,
            dig_bad_replan_enabled=False,
            dig_exit_guard_enabled=True,
            coverage_extra={"use_env_removed_depth": False},
        )
        policy._ensure_coverage_corridors()
        policy._coverage_active_corridor_id = 0
        policy._coverage_last_selected_corridor_id = 0
        policy._skill_name = "dig"
        policy._dig_step_count = policy.dig_exit_guard_min_steps

        policy.predict(
            _coverage_obs(
                mass=5.0,
                dig_distance=0.0,
                bucket_tip_pose=(-1.05, 0.0, -0.74),
            )
        )

        state = policy.debug_state()
        self.assertEqual(state["dig_exit_guard_replan_count"], 1)
        self.assertEqual(
            state["skill_switch_reason"],
            "dig_retry_exit_overshoot_low_payload",
        )
        self.assertEqual(
            policy._coverage_corridors[0].last_reason,
            "exit_overshoot_low_payload",
        )

    def test_primitive_planner_pre_dig_align_plans_before_dig(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            pre_dig_align_enabled=True,
        )

        action = policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        state = policy.debug_state()

        self.assertEqual(state["skill_name"], "pre_dig_align")
        self.assertEqual(state["coverage_corridor_id"], 0)
        self.assertEqual(state["dig_cut_token_injected"], False)
        self.assertIsNone(dig_policy.last_dig_cut_tokens)
        self.assertEqual(action.shape, (4,))
        self.assertTrue(np.all(np.isfinite(action)))
        self.assertEqual(state["pre_dig_align_controlled_dims"], [1, 1, 1, 0])
        self.assertAlmostEqual(float(action[3]), 0.0, places=6)

    def test_primitive_planner_bootstrap_policy_can_receive_dig_cut_tokens(self) -> None:
        bootstrap_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            bootstrap_policy=bootstrap_policy,
            bootstrap_end_mode="first_qualified_dig_start",
            coverage_extra={
                "first_dig_strategy": "nearest_entry",
                "first_dig_proximity_weight": 8.0,
            },
        )

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        state = policy.debug_state()

        self.assertEqual(state["skill_name"], "bootstrap")
        self.assertTrue(state["dig_cut_token_injected"])
        self.assertIsNotNone(bootstrap_policy.last_dig_cut_tokens)
        self.assertGreaterEqual(int(state["coverage_corridor_id"]), 0)

    def test_primitive_planner_uses_first_dig_policy_for_cycle_zero_only(self) -> None:
        regular_dig = _RecordingPolicy(0)
        first_dig = _RecordingPolicy(1)
        policy = _coverage_planner_policy(
            dig_policy=regular_dig,
            first_dig_policy=first_dig,
        )

        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))
        state = policy.debug_state()

        self.assertEqual(state["skill_name"], "dig")
        self.assertIsNotNone(first_dig.last_dig_cut_tokens)
        self.assertIsNone(regular_dig.last_dig_cut_tokens)
        self.assertEqual(first_dig.call_count, 1)
        self.assertEqual(regular_dig.call_count, 0)

        policy._coverage_completed_dump_count = 1
        policy._cycle_index = 1
        policy.predict(_coverage_obs(mass=0.0, dig_distance=0.0))

        self.assertEqual(regular_dig.call_count, 1)

    def test_primitive_planner_pre_dig_align_does_not_drive_bucket_axis(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            pre_dig_align_enabled=True,
        )
        obs = _coverage_obs(mass=0.0, dig_distance=0.0)
        obs["qpos"] = np.asarray([0.0, 0.0, 0.0, 0.83], dtype=np.float32)
        obs["qvel"] = np.asarray([0.0, 0.0, 0.0, 0.25], dtype=np.float32)

        target = policy._pre_dig_align_target(obs)
        action = policy.predict(obs)

        self.assertAlmostEqual(float(target[3]), 0.83, places=6)
        self.assertAlmostEqual(float(action[3]), 0.0, places=6)

    def test_primitive_planner_pre_dig_align_can_extend_bucket_to_zero(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            pre_dig_align_enabled=True,
            pre_dig_align_extra={
                "controlled_dims": [1, 1, 1, 1],
                "bucket_target_qpos": 0.0,
            },
        )
        obs = _coverage_obs(mass=0.0, dig_distance=0.0)
        obs["qpos"] = np.asarray([0.0, 0.0, 0.0, 0.83], dtype=np.float32)
        obs["qvel"] = np.zeros(4, dtype=np.float32)

        target = policy._pre_dig_align_target(obs)
        action = policy.predict(obs)

        self.assertAlmostEqual(float(target[3]), 0.0, places=6)
        self.assertLess(float(action[3]), 0.0)

    def test_primitive_planner_pre_dig_align_hands_off_to_dig(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            pre_dig_align_enabled=True,
        )
        obs = _coverage_obs(mass=0.0, dig_distance=0.0)
        target = policy._pre_dig_align_target(obs)
        obs["qpos"] = target.astype(np.float32)
        obs["qvel"] = np.zeros(4, dtype=np.float32)

        for _ in range(policy.pre_dig_align_hold_steps + 1):
            policy.predict(obs)

        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        policy.predict(obs)
        self.assertIsNotNone(dig_policy.last_dig_cut_tokens)

    def test_primitive_planner_pre_dig_align_first_dig_only_skips_after_return(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            pre_dig_align_enabled=True,
            pre_dig_align_extra={"first_dig_only": True},
        )

        self.assertEqual(policy._skill_name, "pre_dig_align")
        self.assertTrue(policy._should_pre_dig_align_before_dig())

        policy._set_skill("return", "unit_test_return")
        policy._maybe_switch_skill(
            obs=_coverage_obs(mass=0.0, dig_distance=0.0),
            boundary_event=_FakeBoundaryEvent(qualified_dig_start=True),
        )

        self.assertEqual(policy._cycle_index, 1)
        self.assertEqual(policy._skill_name, "dig")
        self.assertFalse(policy._should_pre_dig_align_before_dig())

    def test_primitive_planner_pre_dig_align_uses_start_envelope_handoff(self) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            pre_dig_align_enabled=True,
            pre_dig_align_extra={
                "controlled_dims": [1, 1, 1, 1],
                "bucket_target_qpos": 0.0,
                "max_entry_error_m": 0.10,
                "start_envelope_enabled": True,
                "start_envelope_max_entry_error_m": 0.65,
            },
        )
        obs = _coverage_obs(mass=0.0, dig_distance=0.0)
        target = policy._pre_dig_align_target(obs)
        obs["qpos"] = target.astype(np.float32)
        obs["qvel"] = np.zeros(4, dtype=np.float32)
        env_state = np.asarray(obs["env_state"], dtype=np.float32)
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.75
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = -0.85
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 0.75
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = 0.0
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = -0.85
        obs["env_state"] = env_state

        for _ in range(policy.pre_dig_align_hold_steps + 1):
            policy.predict(obs)

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "dig")
        self.assertTrue(state["pre_dig_align_start_envelope_ready"])

    def test_primitive_planner_pre_dig_align_first_dig_hands_off_on_entry_close(
        self,
    ) -> None:
        dig_policy = _RecordingPolicy(0)
        policy = _coverage_planner_policy(
            dig_policy=dig_policy,
            pre_dig_align_enabled=True,
            pre_dig_align_extra={
                "controlled_dims": [1, 1, 1, 1],
                "max_entry_error_m": 0.35,
                "first_dig_entry_close_handoff": True,
                "first_dig_entry_close_handoff_qvel_abs_max": 0.15,
            },
            coverage_extra={
                "first_dig_strategy": "nearest_entry",
                "first_dig_proximity_weight": 8.0,
            },
        )
        obs = _coverage_obs(
            mass=0.0,
            dig_distance=0.0,
            bucket_pose=(0.42, 0.0, -0.34),
        )
        obs["qpos"] = np.asarray([0.50, 0.60, 0.10, 0.20], dtype=np.float32)
        obs["qvel"] = np.asarray([0.0, 0.03, -0.10, -0.02], dtype=np.float32)

        for _ in range(policy.pre_dig_align_hold_steps + 1):
            policy.predict(obs)

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "dig")
        self.assertTrue(state["pre_dig_align_entry_close_handoff_ready"])
        self.assertIsNotNone(dig_policy.last_dig_cut_tokens)

    def test_primitive_planner_pre_dig_align_first_dig_entry_close_waits_for_qvel(
        self,
    ) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            pre_dig_align_enabled=True,
            pre_dig_align_extra={
                "controlled_dims": [1, 1, 1, 1],
                "max_entry_error_m": 0.35,
                "first_dig_entry_close_handoff": True,
                "first_dig_entry_close_handoff_qvel_abs_max": 0.15,
            },
            coverage_extra={
                "first_dig_strategy": "nearest_entry",
                "first_dig_proximity_weight": 8.0,
            },
        )
        obs = _coverage_obs(
            mass=0.0,
            dig_distance=0.0,
            bucket_pose=(0.42, 0.0, -0.34),
        )
        obs["qpos"] = np.asarray([0.50, 0.60, 0.10, 0.20], dtype=np.float32)
        obs["qvel"] = np.asarray([0.0, 0.03, -0.20, -0.02], dtype=np.float32)

        for _ in range(policy.pre_dig_align_hold_steps + 1):
            policy.predict(obs)

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "pre_dig_align")
        self.assertFalse(state["pre_dig_align_entry_close_handoff_ready"])

    def test_primitive_planner_pre_dig_align_replans_when_entry_gap_stays_large(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            pre_dig_align_enabled=True,
            pre_dig_align_extra={
                "max_entry_error_m": 0.10,
                "timeout_accept_entry_error_m": 0.10,
                "max_steps": 2,
            },
        )
        obs = _coverage_obs(mass=0.0, dig_distance=0.0)
        target = policy._pre_dig_align_target(obs)
        obs["qpos"] = target.astype(np.float32)
        obs["qvel"] = np.zeros(4, dtype=np.float32)

        for _ in range(3):
            policy.predict(obs)

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "pre_dig_align")
        self.assertGreaterEqual(state["pre_dig_align_replan_count"], 1)
        self.assertEqual(
            policy._coverage_corridors[0].last_reason,
            "align_entry_gap_timeout",
        )

    def test_primitive_planner_dig_to_carry_waits_for_target_payload(self) -> None:
        carry_policy = _RecordingPolicy(1)
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            carry_policy=carry_policy,
            dig_to_carry_min_bucket_mass_kg=15.0,
            dig_to_carry_target_bucket_mass_kg=45.0,
        )

        policy.predict(_coverage_obs(mass=20.0, dig_distance=0.0))
        self.assertEqual(policy.debug_state()["skill_name"], "dig")

        policy.predict(_coverage_obs(mass=45.0, dig_distance=0.0))
        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "carry")
        self.assertEqual(state["skill_switch_reason"], "dig_to_carry_target_payload_loaded")
        self.assertIsNone(carry_policy.last_dig_cut_tokens)

    def test_primitive_planner_bad_dig_replans_instead_of_entering_carry(self) -> None:
        policy = _coverage_planner_policy(
            dig_policy=_RecordingPolicy(0),
            dig_to_carry_min_bucket_mass_kg=15.0,
            dig_to_carry_target_bucket_mass_kg=45.0,
            dig_bad_replan_enabled=True,
            pre_dig_align_enabled=True,
        )
        policy._set_skill("dig", "unit_test_start_dig")

        for _ in range(policy.dig_bad_replan_max_steps + 1):
            policy.predict(_coverage_obs(mass=5.0, dig_distance=0.0))

        state = policy.debug_state()
        self.assertEqual(state["skill_name"], "pre_dig_align")
        self.assertGreaterEqual(state["dig_bad_replan_count"], 1)
        self.assertEqual(
            policy._coverage_corridors[0].last_reason,
            "bad_dig_low_payload",
        )

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

    def test_primitive_planner_shallow_guard_hands_return_to_dig_without_qds(
        self,
    ) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            dump_ready_hold_steps=1,
            dump_done_hold_steps=1,
            dump_done_use_boundary_event=False,
            return_to_dig_shallow_guard_enabled=True,
            return_to_dig_max_bucket_mass_kg=15.0,
            return_to_dig_touch_tolerance_m=0.05,
            return_to_dig_min_depth_m=0.02,
            return_to_dig_max_depth_m=0.12,
        )

        policy.predict(_obs(mass=0.0, dig_distance=0.02))
        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        policy.predict(_obs(mass=320.0, dig_distance=0.30, dump_ready=True))
        policy.predict(_obs(mass=0.0, dig_distance=0.30, dump_ready=True, deposited=20.0))

        action = policy.predict(
            _obs(
                mass=0.0,
                dig_distance=0.0,
                bucket_depth=0.08,
                deposited=20.0,
            )
        )

        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertTrue(policy.debug_state()["transition_completed"])
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "return_to_dig_shallow_entry_guard",
        )
        self.assertEqual(policy.rollout_summary()["completed_transition_count"], 1)

    def test_primitive_planner_return_entry_gate_blocks_far_qds(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            return_to_dig_max_entry_error_m=0.55,
        )
        policy._skill_name = "return"
        policy._cycle_index = 0
        policy._prev_action = np.zeros(4, dtype=np.float32)
        policy._pending_dig_cut_cycle_id = 1
        policy._pending_dig_cut_raw_fields = {
            "operator_entry_x_m": 0.5,
            "operator_entry_z_m": -0.5,
        }

        policy.boundary_detector = _FakeBoundaryDetector(
            [_FakeBoundaryEvent(qualified_dig_start=True)]
        )
        action = policy.predict(
            _dig_cut_obs(mass=0.0, dig_distance=0.0, pose=(-0.6, 0.0, -1.4))
        )
        self.assertEqual(float(action[0]), 3.0)
        self.assertEqual(policy.debug_state()["skill_name"], "return")
        self.assertFalse(policy.debug_state()["return_to_dig_entry_close"])

        policy._prev_action = action.copy()
        policy.boundary_detector = _FakeBoundaryDetector(
            [_FakeBoundaryEvent(qualified_dig_start=True)]
        )
        action = policy.predict(
            _dig_cut_obs(mass=0.0, dig_distance=0.0, pose=(0.45, 0.0, -0.55))
        )
        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertTrue(policy.debug_state()["return_to_dig_entry_close"])

    def test_primitive_planner_return_entry_gate_allows_moderate_depth_handoff(
        self,
    ) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector([]),
            return_to_dig_shallow_guard_enabled=True,
            return_to_dig_max_bucket_mass_kg=15.0,
            return_to_dig_touch_tolerance_m=0.05,
            return_to_dig_min_depth_m=0.02,
            return_to_dig_max_depth_m=0.12,
            return_to_dig_max_entry_error_m=0.55,
        )
        policy._skill_name = "return"
        policy._cycle_index = 0
        policy._prev_action = np.zeros(4, dtype=np.float32)
        policy._pending_dig_cut_cycle_id = 1
        policy._pending_dig_cut_raw_fields = {
            "operator_entry_x_m": 0.4,
            "operator_entry_z_m": -1.0,
        }

        action = policy.predict(
            _dig_cut_obs(
                mass=0.0,
                dig_distance=0.0,
                bucket_depth=0.20,
                pose=(0.05, 0.0, -1.15),
            )
        )

        self.assertEqual(float(action[0]), 0.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dig")
        self.assertEqual(
            policy.debug_state()["skill_switch_reason"],
            "return_to_dig_shallow_entry_guard",
        )
        self.assertTrue(policy.debug_state()["return_to_dig_entry_close"])

    def test_primitive_planner_uses_dump_area_relative_readiness_not_horizontal_only(self) -> None:
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
                dump_area_footprint_outside_distance=0.30,
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
                dump_area_footprint_outside_distance=0.03,
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
            dump_ready_position_mode="dump_area_relative",
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_max_dump_area_footprint_outside_distance_m=1.25,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                over_footprint=False,
                clearance_ok=False,
                dump_area_footprint_outside_distance=2.40,
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
                dump_area_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

    def test_primitive_planner_uses_signed_dump_area_relative_window(self) -> None:
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
            dump_ready_position_mode="dump_area_relative",
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_max_dump_area_footprint_outside_distance_m=1.35,
            dump_ready_min_dump_area_relative_x_m=-5.0,
            dump_ready_max_dump_area_relative_x_m=2.0,
            dump_ready_min_dump_area_relative_z_m=2.75,
            dump_ready_max_dump_area_relative_z_m=3.50,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                dump_area_relative_x=-6.20,
                dump_area_relative_z=3.10,
                dump_area_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                dump_area_relative_x=-3.20,
                dump_area_relative_z=2.40,
                dump_area_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.45,
                dump_area_relative_x=-3.20,
                dump_area_relative_z=3.10,
                dump_area_footprint_outside_distance=1.20,
            )
        )
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

    def test_primitive_planner_uses_tight_near_window_dump_handoff(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector(
                [_FakeBoundaryEvent(), _FakeBoundaryEvent(), _FakeBoundaryEvent()]
            ),
            dump_ready_hold_steps=2,
            dump_ready_min_height_above_rim_m=0.30,
            dump_ready_require_over_footprint=False,
            dump_ready_require_clearance=False,
            dump_ready_position_mode="dump_area_relative",
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_max_dump_area_footprint_outside_distance_m=0.45,
            dump_ready_min_dump_area_relative_x_m=0.0,
            dump_ready_max_dump_area_relative_x_m=1.2,
            dump_ready_min_dump_area_relative_z_m=1.0,
            dump_ready_max_dump_area_relative_z_m=1.8,
            dump_ready_near_window_enabled=True,
            dump_ready_near_window_x_tolerance_m=0.05,
            dump_ready_near_window_z_tolerance_m=0.05,
            dump_ready_near_window_outside_tolerance_m=0.0,
            dump_ready_near_window_require_over_footprint=True,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        near_obs = _obs(
            mass=320.0,
            dig_distance=0.30,
            height_above_rim=0.62,
            over_footprint=True,
            dump_area_relative_x=1.202,
            dump_area_relative_z=0.982,
            dump_area_footprint_outside_distance=0.0,
        )
        action = policy.predict(near_obs)
        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")
        self.assertEqual(policy.debug_state()["dump_ready_hold_count"], 1)

        action = policy.predict(near_obs)
        self.assertEqual(float(action[0]), 2.0)
        self.assertEqual(policy.debug_state()["skill_name"], "dump")

    def test_primitive_planner_near_window_does_not_accept_far_miss(self) -> None:
        policy = PrimitivePlannerACTPolicy(
            dig_policy=_ConstantPolicy(0),
            carry_policy=_ConstantPolicy(1),
            dump_policy=_ConstantPolicy(2),
            return_policy=_ConstantPolicy(3),
            boundary_detector=_FakeBoundaryDetector(
                [_FakeBoundaryEvent(), _FakeBoundaryEvent()]
            ),
            dump_ready_hold_steps=1,
            dump_ready_min_height_above_rim_m=0.30,
            dump_ready_require_over_footprint=False,
            dump_ready_require_clearance=False,
            dump_ready_position_mode="dump_area_relative",
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_max_dump_area_footprint_outside_distance_m=0.45,
            dump_ready_min_dump_area_relative_x_m=0.0,
            dump_ready_max_dump_area_relative_x_m=1.2,
            dump_ready_min_dump_area_relative_z_m=1.0,
            dump_ready_max_dump_area_relative_z_m=1.8,
            dump_ready_near_window_enabled=True,
            dump_ready_near_window_x_tolerance_m=0.05,
            dump_ready_near_window_z_tolerance_m=0.05,
            dump_ready_near_window_require_over_footprint=True,
        )

        policy.predict(_obs(mass=320.0, dig_distance=0.30))
        action = policy.predict(
            _obs(
                mass=320.0,
                dig_distance=0.30,
                height_above_rim=0.62,
                over_footprint=True,
                dump_area_relative_x=1.35,
                dump_area_relative_z=0.80,
                dump_area_footprint_outside_distance=0.0,
            )
        )

        self.assertEqual(float(action[0]), 1.0)
        self.assertEqual(policy.debug_state()["skill_name"], "carry")

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
            dump_area_footprint_outside_distance=0.03,
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


def _concat_raw_cycles(first: dict, second: dict) -> dict:
    first_len = int(len(first["actions"]))
    second_len = int(len(second["actions"]))
    result = {
        "qpos": np.concatenate([first["qpos"], second["qpos"]], axis=0),
        "qvel": np.concatenate([first["qvel"], second["qvel"]], axis=0),
        "actions": np.concatenate([first["actions"], second["actions"]], axis=0),
        "images": {
            name: np.concatenate([first["images"][name], second["images"][name]], axis=0)
            for name in first["images"]
        },
        "rewards": np.concatenate([first["rewards"], second["rewards"]], axis=0),
        "metadata": dict(first.get("metadata", {})),
        "env_state": np.concatenate([first["env_state"], second["env_state"]], axis=0),
        "step_ids": np.arange(first_len + second_len, dtype=np.int64),
        "step_ns": np.arange(first_len + second_len, dtype=np.int64) * 10,
        "action_src_types": list(first["action_src_types"]) + list(second["action_src_types"]),
        "action_src_ids": list(first["action_src_ids"]) + list(second["action_src_ids"]),
        "v2": {
            "step": {
                key: np.concatenate(
                    [
                        np.asarray(first["v2"]["step"][key]),
                        np.asarray(second["v2"]["step"][key]),
                    ],
                    axis=0,
                )
                for key in first["v2"]["step"]
            },
            "cycle": {},
        },
    }
    result["v2"]["step"]["cycle_id"] = np.concatenate(
        [
            np.zeros(first_len, dtype=np.int32),
            np.ones(second_len, dtype=np.int32),
        ],
        axis=0,
    )
    return result


def _make_workskill_episode_payload(
    length: int,
    *,
    include_dump_area_geometry: bool = True,
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

    env_state_width = 16 if include_dump_area_geometry else 13
    env_state = np.zeros((length, env_state_width), dtype=np.float32)
    env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] = 500.0
    env_state[:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 0.0
    env_state[:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.30
    env_state[:, ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.60
    env_state[:, ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.60
    env_state[:, ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 0.0
    env_state[:, ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
    if include_dump_area_geometry:
        # Approach starts outside the dump-area release zone and moves inward.
        env_state[:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = -1.50
        env_state[:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 2.80
        env_state[:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 1.00
        if approach_start < length:
            approach_len = max(1, official_dump_start - approach_start)
            env_state[
                approach_start:official_dump_start,
                ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
            ] = np.linspace(0.90, 0.30, approach_len, dtype=np.float32)
            env_state[approach_start:official_dump_start, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = np.linspace(
                2.90,
                2.35,
                approach_len,
                dtype=np.float32,
            )
        env_state[dump_intent_start:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.30
        env_state[official_dump_start:, ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.20
        env_state[official_dump_start:, ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 2.25

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


def _pad_spatial_mass_env(episode: dict, *, offset: int) -> None:
    env = np.zeros((len(episode["actions"]), 64), dtype=np.float32)
    old = np.asarray(episode["env_state"], dtype=np.float32)
    env[:, : old.shape[1]] = old
    env[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env[:, ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.25 + 0.1 * float(offset)
    env[:, ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.50
    env[:, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.0
    env[:20, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0
    env[:20, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.06
    env[:80, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.0
    env[80:, ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.25
    env[80:, ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 1.35 + 0.1 * float(offset)
    env[80:, ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 1.30
    episode["env_state"] = env


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
        self.last_cell_entry_tokens: np.ndarray | None = None
        self.last_dig_cut_tokens: np.ndarray | None = None
        self.last_return_target_tokens: np.ndarray | None = None
        self.last_return_start_envelope_tokens: np.ndarray | None = None
        self.call_count = 0

    def predict(self, obs: dict) -> np.ndarray:
        self.call_count += 1
        self.last_goal_tokens = np.asarray(obs.get("goal_tokens"), dtype=np.float32)
        self.last_cell_entry_tokens = (
            None
            if "cell_entry_tokens" not in obs
            else np.asarray(obs.get("cell_entry_tokens"), dtype=np.float32)
        )
        self.last_dig_cut_tokens = (
            None
            if "dig_cut_tokens" not in obs
            else np.asarray(obs.get("dig_cut_tokens"), dtype=np.float32)
        )
        self.last_return_target_tokens = (
            None
            if "return_target_tokens" not in obs
            else np.asarray(obs.get("return_target_tokens"), dtype=np.float32)
        )
        self.last_return_start_envelope_tokens = (
            None
            if "return_start_envelope_tokens_v1" not in obs
            else np.asarray(obs.get("return_start_envelope_tokens_v1"), dtype=np.float32)
        )
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
    bucket_depth: float = 0.0,
    dump_ready: bool = False,
    deposited: float = 0.0,
    horizontal_distance: float | None = None,
    height_above_rim: float | None = None,
    over_footprint: bool | None = None,
    clearance_ok: bool | None = None,
    dump_area_relative_x: float = 0.0,
    dump_area_relative_z: float = 0.0,
    dump_area_footprint_outside_distance: float | None = None,
) -> dict:
    env_state = np.zeros(16, dtype=np.float32)
    env_state[0] = float(mass)
    env_state[3] = float(deposited)
    env_state[7] = float(dig_distance)
    env_state[8] = float(bucket_depth)
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
    if dump_area_footprint_outside_distance is None:
        dump_area_footprint_outside_distance = 0.0 if bool(env_state[11] > 0.5) else float(env_state[9])
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = float(dump_area_relative_x)
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = float(dump_area_relative_z)
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = float(
        dump_area_footprint_outside_distance
    )
    return {
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": float(mass),
            "deposited_mass_in_target_box_kg": float(deposited),
            "min_distance_to_dig_area_m": float(dig_distance),
            "bucket_depth_below_dig_area_plane_m": float(bucket_depth),
            "target_geometry_available": 1.0,
            "target_horizontal_distance_m": float(env_state[9]),
            "bucket_height_above_target_rim_m": float(env_state[10]),
            "bucket_over_target_footprint_mask": float(env_state[11]),
            "dump_clearance_ok_mask": float(env_state[12]),
            "bucket_dump_area_relative_x_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
            ),
            "bucket_dump_area_relative_z_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
            ),
            "bucket_dump_area_footprint_outside_distance_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
            ),
        },
    }


def _cell_entry_obs(*, mass: float, dig_distance: float) -> dict:
    obs = _obs(mass=mass, dig_distance=dig_distance)
    env_state = np.zeros(28, dtype=np.float32)
    old_env_state = np.asarray(obs["env_state"], dtype=np.float32)
    env_state[: len(old_env_state)] = old_env_state
    env_state[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = -0.625
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 2.0
    obs["env_state"] = env_state
    return obs


def _dig_cut_obs(
    *,
    mass: float,
    dig_distance: float,
    bucket_depth: float = 0.0,
    pose: tuple[float, float, float],
) -> dict:
    obs = _obs(mass=mass, dig_distance=dig_distance, bucket_depth=bucket_depth)
    env_state = np.zeros(23, dtype=np.float32)
    old_env_state = np.asarray(obs["env_state"], dtype=np.float32)
    env_state[: len(old_env_state)] = old_env_state
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(pose[0])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(pose[1])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(pose[2])
    obs["env_state"] = env_state
    return obs


def _coverage_obs(
    *,
    mass: float,
    dig_distance: float,
    removed_cell0: float = 0.0,
    dump_ready: bool = False,
    deposited: float = 0.0,
    bucket_depth: float = 0.0,
    bucket_pose: tuple[float, float, float] | None = None,
    bucket_tip_pose: tuple[float, float, float] | None = None,
) -> dict:
    obs = _obs(
        mass=mass,
        dig_distance=dig_distance,
        dump_ready=dump_ready,
        deposited=deposited,
        bucket_depth=bucket_depth,
    )
    env_state = np.zeros(64, dtype=np.float32)
    old_env_state = np.asarray(obs["env_state"], dtype=np.float32)
    env_state[: len(old_env_state)] = old_env_state
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(
        obs["task_metrics"]["deposited_mass_in_target_box_kg"]
    )
    for index in range(6):
        env_state[ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + index] = 0.08
        env_state[ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + index] = 1.0
    env_state[ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX] = float(removed_cell0)
    if bucket_pose is not None:
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
        if bucket_tip_pose is None:
            bucket_tip_pose = bucket_pose
    if bucket_tip_pose is not None:
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = float(bucket_tip_pose[0])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = float(bucket_tip_pose[1])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = float(bucket_tip_pose[2])
    obs["env_state"] = env_state
    return obs


def _coverage_planner_policy(
    *,
    dig_policy: _RecordingPolicy,
    first_dig_policy: _RecordingPolicy | None = None,
    carry_policy: _RecordingPolicy | None = None,
    return_policy: _RecordingPolicy | None = None,
    bootstrap_policy: _RecordingPolicy | None = None,
    bootstrap_end_mode: str = "disabled",
    dig_to_carry_min_bucket_mass_kg: float = 20.0,
    dig_to_carry_target_bucket_mass_kg: float | None = None,
    dig_to_carry_mass_plateau_enabled: bool = False,
    dig_bad_replan_enabled: bool = False,
    dig_exit_guard_enabled: bool = False,
    return_to_dig_shallow_guard_enabled: bool = False,
    return_to_dig_max_entry_error_m: float | None = None,
    pre_dig_align_enabled: bool = False,
    pre_dig_align_extra: dict | None = None,
    return_target_enabled: bool = False,
    dig_cut_mode: str = "operator_prior_coverage",
    coverage_extra: dict | None = None,
) -> PrimitivePlannerACTPolicy:
    pre_dig_align_cfg = {
        "enabled": bool(pre_dig_align_enabled),
        "hold_steps": 2,
        "max_steps": 10,
    }
    pre_dig_align_cfg.update(dict(pre_dig_align_extra or {}))
    return PrimitivePlannerACTPolicy(
        dig_policy=dig_policy,
        first_dig_policy=first_dig_policy,
        carry_policy=carry_policy or _RecordingPolicy(1),
        dump_policy=_RecordingPolicy(2),
        return_policy=return_policy or _RecordingPolicy(3),
        bootstrap_policy=bootstrap_policy,
        bootstrap_end_mode=bootstrap_end_mode,
        boundary_detector=_FakeBoundaryDetector([]),
        dig_to_carry_min_bucket_mass_kg=dig_to_carry_min_bucket_mass_kg,
        dig_to_carry_target_bucket_mass_kg=dig_to_carry_target_bucket_mass_kg,
        dig_to_carry_mass_plateau_enabled=dig_to_carry_mass_plateau_enabled,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=25.0,
        dig_to_carry_mass_plateau_hold_steps=3,
        dig_to_carry_mass_plateau_min_steps=5,
        dig_bad_replan_enabled=dig_bad_replan_enabled,
        dig_bad_replan_max_steps=5,
        dig_bad_replan_min_bucket_mass_kg=15.0,
        dig_exit_guard_enabled=dig_exit_guard_enabled,
        dig_exit_guard_min_steps=3,
        dig_exit_guard_overshoot_m=0.20,
        dig_exit_guard_min_bucket_mass_kg=20.0,
        return_to_dig_shallow_guard_enabled=return_to_dig_shallow_guard_enabled,
        return_to_dig_max_bucket_mass_kg=15.0,
        return_to_dig_touch_tolerance_m=0.05,
        return_to_dig_min_depth_m=0.02,
        return_to_dig_max_depth_m=0.12,
        return_to_dig_max_entry_error_m=return_to_dig_max_entry_error_m,
        dig_to_carry_min_distance_to_dig_area_m=0.0,
        dig_cut_planner={
            "enabled": True,
            "mode": dig_cut_mode,
            "prior_path": str(YULONG_DIG_CUT_PRIOR_PATH),
            "fallback_mode": "conservative_pose",
            "hold_token_until_skill_exit": True,
            "coverage": dict(coverage_extra or {}),
        },
        return_target_planner={
            "enabled": bool(return_target_enabled),
            "hold_token_until_skill_exit": True,
        },
        pre_dig_align=pre_dig_align_cfg,
    )


if __name__ == "__main__":
    unittest.main()
