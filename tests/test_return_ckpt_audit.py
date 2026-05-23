from __future__ import annotations

import unittest

import numpy as np

from testbed.cli.audit_return_ckpt import (
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


if __name__ == "__main__":
    unittest.main()
