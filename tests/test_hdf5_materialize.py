from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.data.hdf5_io import write_episode
from testbed.data.materialize import materialize_dataset, materialize_episode
from testbed.data.vds import write_vds_episode


class Hdf5MaterializeTests(unittest.TestCase):
    def test_materialize_episode_resolves_vds_and_chunks_images_by_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_path = tmp / "raw" / "episode_0.hdf5"
            wrapper_path = tmp / "vds" / "episode_0.hdf5"
            output_path = tmp / "copy" / "episode_0.hdf5"

            images = np.arange(4 * 4 * 5 * 3, dtype=np.uint8).reshape(4, 4, 5, 3)
            write_episode(
                source_path,
                qpos=np.arange(16, dtype=np.float32).reshape(4, 4),
                qvel=np.ones((4, 4), dtype=np.float32),
                actions=np.full((4, 4), 2.0, dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(4, dtype=np.float32),
                metadata={"dataset_id": "raw"},
            )
            write_vds_episode(
                wrapper_path,
                source_path=source_path,
                crop=slice(1, 3),
                metadata={"dataset_id": "wrapper"},
            )

            stats = materialize_episode(wrapper_path, output_path)

            self.assertEqual(stats.image_dataset_count, 1)
            with h5py.File(output_path, "r") as f:
                image_ds = f["observations/images/fpv"]
                self.assertFalse(image_ds.is_virtual)
                self.assertEqual(image_ds.compression, "lzf")
                self.assertEqual(image_ds.chunks, (1, 4, 5, 3))
                np.testing.assert_array_equal(image_ds[()], images[1:3])
                np.testing.assert_array_equal(
                    f["observations/qpos"][()],
                    np.arange(16, dtype=np.float32).reshape(4, 4)[1:3],
                )
                self.assertEqual(f["metadata"].attrs["storage_mode"], "copy")
                self.assertEqual(
                    f["metadata"].attrs["materialized_source_storage_mode"],
                    "vds",
                )

    def test_materialize_dataset_filters_episode_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "src"
            output_dir = Path(tmpdir) / "out"
            for episode_id in range(3):
                write_episode(
                    source_dir / f"episode_{episode_id}.hdf5",
                    qpos=np.zeros((2, 4), dtype=np.float32),
                    qvel=np.zeros((2, 4), dtype=np.float32),
                    actions=np.zeros((2, 4), dtype=np.float32),
                    images={"fpv": np.zeros((2, 2, 2, 3), dtype=np.uint8)},
                    rewards=np.zeros(2, dtype=np.float32),
                )

            stats = materialize_dataset(source_dir, output_dir, episode_ids=[1])

            self.assertEqual(len(stats), 1)
            self.assertFalse((output_dir / "episode_0.hdf5").exists())
            self.assertTrue((output_dir / "episode_1.hdf5").exists())
            self.assertFalse((output_dir / "episode_2.hdf5").exists())

    def test_materialize_dataset_recursive_preserves_primitive_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_path = root / "raw" / "episode_0.hdf5"
            vds_path = root / "vds" / "dig" / "episode_0.hdf5"
            out_dir = root / "copy"
            images = np.arange(3 * 2 * 2 * 3, dtype=np.uint8).reshape(3, 2, 2, 3)
            write_episode(
                raw_path,
                qpos=np.zeros((3, 4), dtype=np.float32),
                qvel=np.zeros((3, 4), dtype=np.float32),
                actions=np.zeros((3, 4), dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(3, dtype=np.float32),
            )
            write_vds_episode(
                vds_path,
                source_path=raw_path,
                crop=slice(0, 2),
                metadata={"primitive_name": "dig"},
            )

            stats = materialize_dataset(
                root / "vds",
                out_dir,
                recursive=True,
                workers=2,
            )

            self.assertEqual(len(stats), 1)
            with h5py.File(out_dir / "dig" / "episode_0.hdf5", "r") as f:
                self.assertFalse(f["observations/images/fpv"].is_virtual)
                np.testing.assert_array_equal(f["observations/images/fpv"][()], images[:2])


if __name__ == "__main__":
    unittest.main()
