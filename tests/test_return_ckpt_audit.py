from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import h5py
import numpy as np

from testbed.cli.audit_return_ckpt import (
    RETURN_START_TOKEN_KEY,
    _read_obs_at_step,
    apply_return_envelope_variant,
    summarize_records,
)


class ReturnCkptAuditTest(unittest.TestCase):
    def test_depth_zero_masks_only_depth_band_values(self) -> None:
        token = np.linspace(0.1, 1.8, 18, dtype=np.float32)

        masked = apply_return_envelope_variant(token, "depth_zero")

        self.assertEqual(float(masked[2]), 0.0)
        self.assertEqual(float(masked[4]), 0.0)
        self.assertEqual(float(masked[5]), 0.0)
        np.testing.assert_allclose(masked[[0, 1, 3, 6, 17]], token[[0, 1, 3, 6, 17]])
        np.testing.assert_allclose(masked[7:17], token[7:17])

    def test_qpos_envelope_only_drops_spatial_measurement_block(self) -> None:
        token = np.linspace(0.1, 1.8, 18, dtype=np.float32)

        masked = apply_return_envelope_variant(token, "qpos_envelope_only")

        np.testing.assert_allclose(masked[0:7], np.zeros(7, dtype=np.float32))
        np.testing.assert_allclose(masked[7:17], token[7:17])
        self.assertEqual(float(masked[17]), 0.0)

    def test_summary_reports_delta_against_original_by_frame(self) -> None:
        records = [
            {
                "variant": "original",
                "episode_id": 0,
                "step": 0,
                "frame_key": "0:0",
                "phase": 0.8,
                "pred": np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
                "expert": np.asarray([1.0, 1.0, 1.0, 1.0], dtype=np.float32),
                "original_token_depth_m": 0.12,
                "original_token_entry_norm": 0.7,
            },
            {
                "variant": "depth_zero",
                "episode_id": 0,
                "step": 0,
                "frame_key": "0:0",
                "phase": 0.8,
                "pred": np.asarray([2.0, 2.0, 3.0, 0.0], dtype=np.float32),
                "expert": np.asarray([1.0, 1.0, 1.0, 1.0], dtype=np.float32),
                "original_token_depth_m": 0.12,
                "original_token_entry_norm": 0.7,
            },
        ]

        summary = summarize_records(records)

        late_depth = summary["variants"]["depth_zero"]["late_p75_100"]
        self.assertEqual(late_depth["count"], 1)
        np.testing.assert_allclose(
            late_depth["delta_vs_original"]["action_delta"]["mean"],
            [1.0, 0.0, 0.0, -4.0],
        )
        self.assertAlmostEqual(
            late_depth["delta_vs_original"]["l2_mean"],
            float(np.linalg.norm(np.asarray([1.0, 0.0, 0.0, -4.0]))),
            places=6,
        )

    def test_read_obs_derives_return_relocate_tokens_from_return_target_tokens(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            episode_path = Path(tmp) / "episode.hdf5"
            return_start = np.linspace(0.1, 1.8, 18, dtype=np.float32)
            return_target = np.arange(10, dtype=np.float32)
            return_target[7] = 70.0
            return_target[8] = 80.0
            return_target[9] = 1.0
            with h5py.File(episode_path, "w") as handle:
                handle.create_dataset(
                    "observations/qpos",
                    data=np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32),
                )
                handle.create_dataset(
                    "observations/qvel",
                    data=np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32),
                )
                handle.create_dataset(
                    "observations/images/fpv",
                    data=np.zeros((1, 2, 2, 3), dtype=np.uint8),
                )
                handle.create_dataset(
                    "v2/step/return_target_tokens",
                    data=return_target.reshape(1, -1),
                )
                with h5py.File(episode_path, "r") as handle:
                    obs = _read_obs_at_step(
                        handle=handle,
                        step=0,
                        camera_names=["fpv"],
                        low_dim_keys=[
                            "qpos",
                            "qvel",
                            RETURN_START_TOKEN_KEY,
                            "return_relocate_tokens_v1",
                        ],
                        return_start_token=return_start,
                    )

            np.testing.assert_allclose(obs["return_relocate_tokens_v1"][:7], np.arange(7))
            self.assertEqual(float(obs["return_relocate_tokens_v1"][7]), 0.0)
            self.assertEqual(float(obs["return_relocate_tokens_v1"][8]), 0.0)
            self.assertEqual(float(obs["return_relocate_tokens_v1"][9]), 1.0)


if __name__ == "__main__":
    unittest.main()
