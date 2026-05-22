from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.data.hdf5_io import write_episode
from testbed.data.materialize import materialize_episode
from testbed.data.vds import write_vds_episode
from testbed.data.virtualize_images import (
    SourcePrefixRewrite,
    virtualize_dataset_images,
    virtualize_episode_images,
)


class Hdf5VirtualizeImagesTests(unittest.TestCase):
    def test_virtualize_episode_keeps_lowdim_local_and_images_virtual(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_path = tmp / "raw" / "episode_0.hdf5"
            wrapper_path = tmp / "vds" / "episode_0.hdf5"
            copy_path = tmp / "copy" / "episode_0.hdf5"
            archive_path = tmp / "archive" / "episode_0.hdf5"

            images = np.arange(5 * 3 * 4 * 3, dtype=np.uint8).reshape(5, 3, 4, 3)
            qpos = np.arange(20, dtype=np.float32).reshape(5, 4)
            write_episode(
                source_path,
                qpos=qpos,
                qvel=np.ones((5, 4), dtype=np.float32),
                actions=np.full((5, 4), 2.0, dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(5, dtype=np.float32),
                metadata={"dataset_id": "raw"},
            )
            write_vds_episode(
                wrapper_path,
                source_path=source_path,
                crop=slice(1, 4),
                metadata={"dataset_id": "wrapper"},
            )
            materialize_episode(wrapper_path, copy_path)

            stats = virtualize_episode_images(copy_path, archive_path)

            self.assertEqual(stats.image_dataset_count, 1)
            self.assertGreater(stats.virtualized_image_bytes, 0)
            with h5py.File(archive_path, "r") as f:
                image_ds = f["observations/images/fpv"]
                qpos_ds = f["observations/qpos"]
                self.assertTrue(image_ds.is_virtual)
                self.assertFalse(qpos_ds.is_virtual)
                np.testing.assert_array_equal(image_ds[()], images[1:4])
                np.testing.assert_array_equal(qpos_ds[()], qpos[1:4])
                self.assertEqual(f["metadata"].attrs["storage_mode"], "vds")
                self.assertEqual(f["metadata"].attrs["image_storage_mode"], "vds")
                self.assertEqual(
                    f["metadata"].attrs["image_virtualized_lowdim_storage_mode"],
                    "copy",
                )
                self.assertEqual(
                    image_ds.attrs["image_vds_source_start_step"],
                    1,
                )

    def test_virtualize_dataset_recurses_and_rewrites_source_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_root = tmp / "old"
            new_root = tmp / "new"
            source_path = new_root / "raw" / "episode_2.hdf5"
            copy_path = tmp / "copy" / "dig" / "episode_2.hdf5"
            archive_dir = tmp / "archive"

            images = np.arange(4 * 2 * 3 * 3, dtype=np.uint8).reshape(4, 2, 3, 3)
            write_episode(
                source_path,
                qpos=np.zeros((4, 4), dtype=np.float32),
                qvel=np.zeros((4, 4), dtype=np.float32),
                actions=np.zeros((4, 4), dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(4, dtype=np.float32),
            )
            write_episode(
                copy_path,
                qpos=np.zeros((2, 4), dtype=np.float32),
                qvel=np.zeros((2, 4), dtype=np.float32),
                actions=np.zeros((2, 4), dtype=np.float32),
                images={"fpv": images[1:3]},
                rewards=np.zeros(2, dtype=np.float32),
                metadata={
                    "storage_mode": "copy",
                    "vds_source_abs_path": str(old_root / "raw" / "episode_2.hdf5"),
                    "vds_source_start_step": 1,
                    "vds_source_end_step_exclusive": 3,
                },
            )
            (tmp / "copy" / "summary.json").write_text('{"ok": true}\n')

            stats = virtualize_dataset_images(
                tmp / "copy",
                archive_dir,
                recursive=True,
                source_prefix_rewrites=[
                    SourcePrefixRewrite(old=old_root, new=new_root)
                ],
            )

            self.assertEqual(len(stats), 1)
            self.assertTrue((archive_dir / "summary.json").exists())
            with h5py.File(archive_dir / "dig" / "episode_2.hdf5", "r") as f:
                image_ds = f["observations/images/fpv"]
                self.assertTrue(image_ds.is_virtual)
                np.testing.assert_array_equal(image_ds[()], images[1:3])
                self.assertEqual(
                    Path(image_ds.attrs["image_vds_source_abs_path"]).resolve(),
                    source_path.resolve(),
                )


    def test_virtualize_episode_uses_source_dataset_dir_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw"
            crop_path = tmp / "workskill" / "episode_7.hdf5"
            archive_path = tmp / "archive" / "episode_7.hdf5"

            images = np.arange(6 * 2 * 3 * 3, dtype=np.uint8).reshape(6, 2, 3, 3)
            write_episode(
                raw_dir / "episode_7.hdf5",
                qpos=np.zeros((6, 4), dtype=np.float32),
                qvel=np.zeros((6, 4), dtype=np.float32),
                actions=np.zeros((6, 4), dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(6, dtype=np.float32),
            )
            write_episode(
                crop_path,
                qpos=np.zeros((3, 4), dtype=np.float32),
                qvel=np.zeros((3, 4), dtype=np.float32),
                actions=np.zeros((3, 4), dtype=np.float32),
                images={"fpv": images[2:5]},
                rewards=np.zeros(3, dtype=np.float32),
                metadata={
                    "source_dataset_dir": str(raw_dir),
                    "source_episode_id": "episode_7",
                    "source_start_step": 2,
                },
            )

            virtualize_episode_images(crop_path, archive_path)

            with h5py.File(archive_path, "r") as f:
                image_ds = f["observations/images/fpv"]
                self.assertTrue(image_ds.is_virtual)
                np.testing.assert_array_equal(image_ds[()], images[2:5])

    def test_virtualize_episode_uses_fallback_source_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw"
            relabeled_path = tmp / "relabeled" / "episode_1.hdf5"
            archive_path = tmp / "archive" / "episode_1.hdf5"

            images = np.arange(3 * 2 * 2 * 3, dtype=np.uint8).reshape(3, 2, 2, 3)
            write_episode(
                raw_dir / "episode_1.hdf5",
                qpos=np.zeros((3, 4), dtype=np.float32),
                qvel=np.zeros((3, 4), dtype=np.float32),
                actions=np.zeros((3, 4), dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(3, dtype=np.float32),
            )
            write_episode(
                relabeled_path,
                qpos=np.zeros((3, 4), dtype=np.float32),
                qvel=np.zeros((3, 4), dtype=np.float32),
                actions=np.zeros((3, 4), dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(3, dtype=np.float32),
                metadata={"episode_id": "episode_1"},
            )

            virtualize_episode_images(
                relabeled_path,
                archive_path,
                fallback_source_dir=raw_dir,
            )

            with h5py.File(archive_path, "r") as f:
                image_ds = f["observations/images/fpv"]
                self.assertTrue(image_ds.is_virtual)
                np.testing.assert_array_equal(image_ds[()], images)

    def test_virtualize_episode_chases_image_vds_archive_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_dir = tmp / "raw"
            relabeled_path = tmp / "relabeled" / "episode_1.hdf5"
            relabeled_archive = tmp / "relabeled_vds" / "episode_1.hdf5"
            workskill_path = tmp / "workskill" / "episode_1.hdf5"
            workskill_archive = tmp / "workskill_vds" / "episode_1.hdf5"

            images = np.arange(6 * 2 * 2 * 3, dtype=np.uint8).reshape(6, 2, 2, 3)
            for path, frames, metadata in (
                (raw_dir / "episode_1.hdf5", images, {}),
                (
                    relabeled_path,
                    images,
                    {"episode_id": "episode_1", "storage_mode": "copy"},
                ),
                (
                    workskill_path,
                    images[2:5],
                    {
                        "source_dataset_dir": str(tmp / "relabeled"),
                        "source_episode_id": "episode_1",
                        "source_start_step": 2,
                        "storage_mode": "copy",
                    },
                ),
            ):
                write_episode(
                    path,
                    qpos=np.zeros((len(frames), 4), dtype=np.float32),
                    qvel=np.zeros((len(frames), 4), dtype=np.float32),
                    actions=np.zeros((len(frames), 4), dtype=np.float32),
                    images={"fpv": frames},
                    rewards=np.zeros(len(frames), dtype=np.float32),
                    metadata=metadata,
                )

            virtualize_episode_images(
                relabeled_path,
                relabeled_archive,
                fallback_source_dir=raw_dir,
            )
            virtualize_episode_images(
                workskill_path,
                workskill_archive,
                source_prefix_rewrites=[
                    SourcePrefixRewrite(
                        old=tmp / "relabeled",
                        new=tmp / "relabeled_vds",
                    )
                ],
            )

            with h5py.File(workskill_archive, "r") as f:
                image_ds = f["observations/images/fpv"]
                self.assertTrue(image_ds.is_virtual)
                np.testing.assert_array_equal(image_ds[()], images[2:5])
                self.assertEqual(
                    Path(image_ds.attrs["image_vds_source_abs_path"]).resolve(),
                    (raw_dir / "episode_1.hdf5").resolve(),
                )

    def test_virtualize_episode_handles_source_absolute_range_into_vds_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_path = tmp / "raw" / "episode_0.hdf5"
            workskill_path = tmp / "workskill" / "episode_0.hdf5"
            primitive_path = tmp / "primitive" / "episode_0.hdf5"
            workskill_archive = tmp / "workskill_vds" / "episode_0.hdf5"
            primitive_archive = tmp / "primitive_vds" / "episode_0.hdf5"

            images = np.arange(8 * 2 * 2 * 3, dtype=np.uint8).reshape(8, 2, 2, 3)
            write_episode(
                raw_path,
                qpos=np.zeros((8, 4), dtype=np.float32),
                qvel=np.zeros((8, 4), dtype=np.float32),
                actions=np.zeros((8, 4), dtype=np.float32),
                images={"fpv": images},
                rewards=np.zeros(8, dtype=np.float32),
            )
            write_episode(
                workskill_path,
                qpos=np.zeros((4, 4), dtype=np.float32),
                qvel=np.zeros((4, 4), dtype=np.float32),
                actions=np.zeros((4, 4), dtype=np.float32),
                images={"fpv": images[2:6]},
                rewards=np.zeros(4, dtype=np.float32),
                metadata={
                    "source_dataset_dir": str(raw_path.parent),
                    "source_episode_id": "episode_0",
                    "source_start_step": 2,
                },
            )
            write_episode(
                primitive_path,
                qpos=np.zeros((2, 4), dtype=np.float32),
                qvel=np.zeros((2, 4), dtype=np.float32),
                actions=np.zeros((2, 4), dtype=np.float32),
                images={"fpv": images[4:6]},
                rewards=np.zeros(2, dtype=np.float32),
                metadata={
                    "source_dataset_dir": str(workskill_path.parent),
                    "source_episode_id": "episode_0",
                    "source_start_step": 4,
                    "source_end_step_exclusive": 6,
                },
            )

            virtualize_episode_images(workskill_path, workskill_archive)
            virtualize_episode_images(
                primitive_path,
                primitive_archive,
                source_prefix_rewrites=[
                    SourcePrefixRewrite(
                        old=workskill_path.parent,
                        new=workskill_archive.parent,
                    )
                ],
            )

            with h5py.File(primitive_archive, "r") as f:
                image_ds = f["observations/images/fpv"]
                self.assertTrue(image_ds.is_virtual)
                np.testing.assert_array_equal(image_ds[()], images[4:6])
                self.assertEqual(image_ds.attrs["image_vds_source_start_step"], 4)
                self.assertEqual(image_ds.attrs["image_vds_source_end_step_exclusive"], 6)


if __name__ == "__main__":
    unittest.main()
