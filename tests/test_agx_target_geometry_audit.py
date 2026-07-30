from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import write_episode
from testbed.data.target_geometry_audit import audit_target_geometry_dataset

LEGACY_ENV_STATE_ORDER = (
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

TARGET_GEOMETRY_ENV_STATE_ORDER = LEGACY_ENV_STATE_ORDER + (
    "target_horizontal_distance_m",
    "bucket_height_above_target_rim_m",
    "bucket_over_target_footprint_mask",
    "dump_clearance_ok_mask",
    "bucket_dump_area_relative_x_m",
    "bucket_dump_area_relative_z_m",
    "bucket_dump_area_footprint_outside_distance_m",
)


def _write_minimal_episode(
    path: Path,
    *,
    env_state: np.ndarray,
    env_state_order: tuple[str, ...],
) -> None:
    steps = int(env_state.shape[0])
    write_episode(
        path,
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        actions=np.zeros((steps, 4), dtype=np.float32),
        env_state=env_state,
        metadata={"env_state_order": ",".join(env_state_order)},
    )


class TestTargetGeometryAudit(unittest.TestCase):
    def test_legacy_dataset_is_not_usable_for_target_safety_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_dir = Path(tmp)
            env_state = np.zeros((3, 9), dtype=np.float32)
            _write_minimal_episode(
                dataset_dir / "episode_0.hdf5",
                env_state=env_state,
                env_state_order=LEGACY_ENV_STATE_ORDER,
            )

            summary = audit_target_geometry_dataset(dataset_dir)

        self.assertFalse(summary["usable_for_target_safety_training"])
        self.assertEqual(summary["legacy_only_episode_count"], 1)
        self.assertEqual(summary["episodes_with_all_target_geometry_fields"], 0)
        self.assertEqual(summary["recommendation"], "collect_new_data_with_target_geometry_contract")

    def test_geometry_dataset_is_usable_when_all_required_fields_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_dir = Path(tmp)
            env_state = np.zeros((3, 16), dtype=np.float32)
            env_state[:, 9] = [1.0, 0.8, 0.2]
            env_state[:, 10] = [0.1, 0.1, 0.2]
            env_state[:, 11] = [0.0, 0.0, 1.0]
            env_state[:, 12] = [0.0, 0.0, 1.0]
            env_state[:, 13] = [0.2, 0.1, 0.0]
            env_state[:, 14] = [0.3, 0.2, 0.1]
            env_state[:, 15] = [0.4, 0.2, 0.0]
            _write_minimal_episode(
                dataset_dir / "episode_0.hdf5",
                env_state=env_state,
                env_state_order=TARGET_GEOMETRY_ENV_STATE_ORDER,
            )

            summary = audit_target_geometry_dataset(dataset_dir)

        self.assertTrue(summary["usable_for_target_safety_training"])
        self.assertEqual(summary["legacy_only_episode_count"], 0)
        self.assertEqual(summary["episodes_with_all_target_geometry_fields"], 1)
        self.assertAlmostEqual(float(summary["target_geometry_valid_step_rate"]), 1.0)


if __name__ == "__main__":
    unittest.main()
