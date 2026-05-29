from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.perception.lidar_heightmap import (
    LidarHeightmapConfig,
    points_to_heightmap,
    save_heightmap_npz,
)


class LidarHeightmapTests(unittest.TestCase):
    def test_points_to_heightmap_uses_max_vertical_value_per_cell(self) -> None:
        points = np.asarray(
            [
                [0.25, 0.1, 0.25],
                [0.25, 0.8, 0.25],
                [1.25, 0.4, 0.25],
            ],
            dtype=np.float32,
        )
        config = LidarHeightmapConfig(
            x_min_m=0.0,
            x_max_m=2.0,
            z_min_m=0.0,
            z_max_m=1.0,
            resolution_m=1.0,
            reference_height_m=1.0,
        )

        result = points_to_heightmap(points, config)

        self.assertEqual(result.height_m.shape, (1, 2))
        self.assertAlmostEqual(float(result.height_m[0, 0]), 0.8)
        self.assertAlmostEqual(float(result.height_m[0, 1]), 0.4)
        self.assertEqual(int(result.point_count[0, 0]), 2)
        self.assertEqual(int(result.point_count[0, 1]), 1)

    def test_depth_uses_reference_height_and_empty_cells_are_nan(self) -> None:
        points = np.asarray(
            [
                [0.25, 1.0, 0.25],
                [1.25, 0.25, 0.25],
            ],
            dtype=np.float32,
        )
        config = LidarHeightmapConfig(
            x_min_m=0.0,
            x_max_m=3.0,
            z_min_m=0.0,
            z_max_m=1.0,
            resolution_m=1.0,
            reference_height_m=1.0,
        )

        result = points_to_heightmap(points, config)

        self.assertAlmostEqual(float(result.depth_m[0, 0]), 0.0)
        self.assertAlmostEqual(float(result.depth_m[0, 1]), 0.75)
        self.assertTrue(np.isnan(result.depth_m[0, 2]))
        self.assertFalse(bool(result.valid_mask[0, 2]))

    def test_auto_reference_height_uses_highest_valid_cell(self) -> None:
        points = np.asarray(
            [
                [0.25, 0.2, 0.25],
                [1.25, 0.7, 0.25],
            ],
            dtype=np.float32,
        )
        config = LidarHeightmapConfig(
            x_min_m=0.0,
            x_max_m=2.0,
            z_min_m=0.0,
            z_max_m=1.0,
            resolution_m=1.0,
        )

        result = points_to_heightmap(points, config)

        self.assertAlmostEqual(result.reference_height_m, 0.7, places=6)
        self.assertAlmostEqual(float(result.depth_m[0, 0]), 0.5, places=6)
        self.assertAlmostEqual(float(result.depth_m[0, 1]), 0.0, places=6)

    def test_save_heightmap_npz_round_trips_core_arrays(self) -> None:
        points = np.asarray([[0.25, 0.5, 0.25]], dtype=np.float32)
        config = LidarHeightmapConfig(
            x_min_m=0.0,
            x_max_m=1.0,
            z_min_m=0.0,
            z_max_m=1.0,
            resolution_m=1.0,
        )
        result = points_to_heightmap(points, config)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_heightmap_npz(result, Path(tmpdir) / "heightmap.npz")
            loaded = np.load(path)

            np.testing.assert_allclose(loaded["height_m"], result.height_m)
            np.testing.assert_allclose(loaded["depth_m"], result.depth_m)
            np.testing.assert_array_equal(loaded["point_count"], result.point_count)

    def test_config_rejects_invalid_bounds(self) -> None:
        config = LidarHeightmapConfig(x_min_m=1.0, x_max_m=1.0)

        with self.assertRaises(ValueError):
            config.validate()


if __name__ == "__main__":
    unittest.main()
