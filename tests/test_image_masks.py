import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.data.dataset import EpisodicDataset
from testbed.data.image_masks import apply_image_mask


class ImageMaskTest(unittest.TestCase):
    def test_apply_image_mask_keeps_rect_and_zeroes_outside(self) -> None:
        image = np.full((4, 4, 3), 10, dtype=np.uint8)
        masked = apply_image_mask(
            image,
            camera_name="fpv",
            mask_config={
                "enabled": True,
                "mode": "multiply",
                "cameras": {"fpv": {"rect_xyxy_px": [1, 1, 3, 3]}},
            },
        )

        self.assertEqual(masked.dtype, np.uint8)
        self.assertTrue(np.all(masked[1:3, 1:3] == 10))
        self.assertTrue(np.all(masked[0, :] == 0))
        self.assertTrue(np.all(masked[:, 0] == 0))

    def test_apply_image_mask_accepts_channel_first_float(self) -> None:
        image = np.ones((3, 4, 4), dtype=np.float32)
        masked = apply_image_mask(
            image,
            camera_name="fpv",
            mask_config={
                "enabled": True,
                "mode": "multiply",
                "cameras": {"fpv": {"rect_xyxy_norm": [0.25, 0.25, 0.75, 0.75]}},
            },
        )

        self.assertEqual(masked.shape, (3, 4, 4))
        self.assertTrue(np.allclose(masked[:, 1:3, 1:3], 1.0))
        self.assertTrue(np.allclose(masked[:, 0, :], 0.0))
        self.assertTrue(np.allclose(masked[:, :, 0], 0.0))

    def test_episodic_dataset_applies_static_camera_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_dir = Path(tmp)
            _write_episode(dataset_dir / "episode_0.hdf5")
            norm_stats = {
                "action_mean": np.zeros(4, dtype=np.float32),
                "action_std": np.ones(4, dtype=np.float32),
                "proprio_mean": np.zeros(8, dtype=np.float32),
                "proprio_std": np.ones(8, dtype=np.float32),
            }
            ds = EpisodicDataset(
                [0],
                dataset_dir,
                ["fpv"],
                norm_stats,
                episode_len=2,
                low_dim_keys=["qpos", "qvel"],
                image_mask_config={
                    "enabled": True,
                    "mode": "multiply",
                    "cameras": {"fpv": {"rect_xyxy_px": [1, 1, 3, 3]}},
                },
            )

            image_data, _, _, _ = ds[0]
            self.assertEqual(tuple(image_data.shape), (1, 3, 4, 4))
            self.assertTrue(np.allclose(image_data[0, :, 1:3, 1:3].numpy(), 10 / 255.0))
            self.assertTrue(np.allclose(image_data[0, :, 0, :].numpy(), 0.0))
            self.assertTrue(np.allclose(image_data[0, :, :, 0].numpy(), 0.0))


def _write_episode(path: Path) -> None:
    with h5py.File(path, "w") as f:
        f.attrs["sim"] = True
        obs = f.create_group("observations")
        obs.create_dataset("qpos", data=np.zeros((2, 4), dtype=np.float32))
        obs.create_dataset("qvel", data=np.zeros((2, 4), dtype=np.float32))
        images = obs.create_group("images")
        images.create_dataset("fpv", data=np.full((2, 4, 4, 3), 10, dtype=np.uint8))
        f.create_dataset("action", data=np.zeros((2, 4), dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
