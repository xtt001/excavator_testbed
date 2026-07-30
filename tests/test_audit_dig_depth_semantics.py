from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.cli.audit_dig_depth_semantics import (
    _select_episode_paths,
    compute_episode_metrics,
    summarize_metrics,
)
from testbed.cli.build_dig_depth_profile_tokens_v1 import _write_episode_token
from testbed.data.dataset import get_norm_stats
from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    build_dig_depth_profile_token_from_metrics,
)
from testbed.data.operator_first_v2_2 import DIG_CUT_DEPTH_SCALE_M
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_MASS_DELTA_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_2_DIM,
)


class DigDepthSemanticsAuditTest(unittest.TestCase):
    def test_surface_penetration_uses_relative_tip_and_surface_not_plane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode_path = Path(tmp) / "episode_0.hdf5"
            _write_synthetic_dig_episode(episode_path, tier="gold")

            metrics = compute_episode_metrics(episode_path, surface_source="current_cell")

        self.assertEqual(metrics["dominant_removed_depth_cell_id"], 2)
        self.assertEqual(metrics["entry_cell_id"], 2)
        self.assertAlmostEqual(metrics["entry_surface_penetration_m"], 0.10, places=6)
        self.assertAlmostEqual(metrics["peak_surface_penetration_m"], 0.40, places=6)
        self.assertAlmostEqual(metrics["exit_surface_penetration_m"], 0.20, places=6)
        self.assertAlmostEqual(metrics["token_depth_target_m"], 0.05, places=6)
        self.assertAlmostEqual(
            metrics["plane_minus_surface_penetration_median_m"],
            0.70,
            places=6,
        )

    def test_metadata_filter_selects_gold_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_synthetic_dig_episode(root / "episode_0.hdf5", tier="gold")
            _write_synthetic_dig_episode(root / "episode_1.hdf5", tier="silver")

            selected = _select_episode_paths(
                dataset_dir=root,
                metadata_filters={"training_tier": "gold"},
                max_episodes=0,
            )

        self.assertEqual([path.name for path in selected], ["episode_0.hdf5"])

    def test_summary_reports_correlations_when_enough_records(self) -> None:
        records = [
            {
                "dominant_removed_depth_cell_id": 0,
                "peak_surface_penetration_m": 0.2,
                "surface_penetration_auc_m_s": 0.4,
                "actual_removed_depth_peak_m": 0.04,
                "actual_removed_depth_dominant_m": 0.04,
                "token_depth_target_m": 0.04,
                "operator_cut_depth_peak_m": 0.04,
                "dig_outcome_payload_gain_kg": 20.0,
                "token_payload_target_kg": 20.0,
                "token_cut_length_m": 0.8,
                "plane_minus_surface_penetration_median_m": 0.6,
                "plane_minus_surface_penetration_p90_abs_m": 0.6,
                "contact_fraction": 1.0,
                "positive_surface_penetration_fraction": 1.0,
            },
            {
                "dominant_removed_depth_cell_id": 1,
                "peak_surface_penetration_m": 0.5,
                "surface_penetration_auc_m_s": 0.9,
                "actual_removed_depth_peak_m": 0.08,
                "actual_removed_depth_dominant_m": 0.08,
                "token_depth_target_m": 0.08,
                "operator_cut_depth_peak_m": 0.08,
                "dig_outcome_payload_gain_kg": 55.0,
                "token_payload_target_kg": 55.0,
                "token_cut_length_m": 1.1,
                "plane_minus_surface_penetration_median_m": 0.7,
                "plane_minus_surface_penetration_p90_abs_m": 0.7,
                "contact_fraction": 1.0,
                "positive_surface_penetration_fraction": 1.0,
            },
        ]

        summary = summarize_metrics(records)

        self.assertEqual(summary["headline"]["count"], 2)
        self.assertAlmostEqual(
            summary["headline"]["peak_surface_penetration_p50_m"],
            0.35,
            places=6,
        )
        self.assertAlmostEqual(
            summary["correlations"]["surface_penetration_auc_vs_payload"],
            1.0,
            places=6,
        )

    def test_depth_profile_token_can_be_written_and_loaded_as_low_dim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode_path = root / "episode_0.hdf5"
            _write_synthetic_dig_episode(episode_path, tier="gold")
            metrics = compute_episode_metrics(episode_path, surface_source="current_cell")
            token = build_dig_depth_profile_token_from_metrics(metrics)

            _write_episode_token(episode_path, token=token, force=False)
            stats = get_norm_stats(
                root,
                num_episodes=0,
                low_dim_keys=["qpos", "qvel", "dig_depth_profile_tokens_v1"],
            )

        self.assertEqual(token.shape, (DIG_DEPTH_PROFILE_TOKEN_DIM,))
        self.assertEqual(stats["example_proprio"].shape[-1], 4 + 4 + DIG_DEPTH_PROFILE_TOKEN_DIM)
        np.testing.assert_allclose(stats["example_proprio"][0, -DIG_DEPTH_PROFILE_TOKEN_DIM:], token)


def _write_synthetic_dig_episode(path: Path, *, tier: str) -> None:
    env_state = np.zeros((3, ENV_STATE_V2_2_DIM), dtype=np.float32)
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 2
    env_state[:, ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = np.asarray(
        [-0.20, -0.50, -0.30],
        dtype=np.float32,
    )
    env_state[:, ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 2] = 0.10
    env_state[:, ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 2] = [0.0, 0.02, 0.04]
    env_state[:, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = 0.90
    env_state[:, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = [0.1, 0.4, 0.2]
    env_state[:, ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = [1.0, 1.0, 0.0]
    env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] = [0.0, 12.0, 20.0]
    env_state[:, ENV_STATE_BUCKET_MASS_DELTA_IDX] = [0.0, 12.0, 8.0]
    token = np.zeros((3, 10), dtype=np.float32)
    token[:, 6] = 0.5
    token[:, 7] = 0.05 / DIG_CUT_DEPTH_SCALE_M
    token[:, 8] = 0.5
    token[:, 9] = 1.0
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        meta = handle.create_group("metadata")
        meta.attrs["training_tier"] = tier
        meta.attrs["dt"] = 0.02
        obs = handle.create_group("observations")
        obs.create_dataset("env_state", data=env_state)
        obs.create_dataset("qpos", data=np.zeros((3, 4), dtype=np.float32))
        obs.create_dataset("qvel", data=np.zeros((3, 4), dtype=np.float32))
        handle.create_dataset("action", data=np.zeros((3, 4), dtype=np.float32))
        step = handle.create_group("v2/step")
        step.create_dataset("dig_cut_tokens", data=token)
        cycle = handle.create_group("v2/cycle")
        cycle.create_dataset("dominant_removed_depth_cell_id", data=np.asarray([2]))
        cycle.create_dataset(
            "actual_removed_depth_delta_grid",
            data=np.asarray([[0.0, 0.0, 0.04, 0.0, 0.0, 0.0]], dtype=np.float32),
        )
        cycle.create_dataset("training_tier", data=np.asarray([tier.encode()]))
        cycle.create_dataset("operator_entry_y_m", data=np.asarray([-0.2]))
        cycle.create_dataset("operator_exit_y_m", data=np.asarray([-0.5]))
        cycle.create_dataset("operator_cut_depth_peak_m", data=np.asarray([0.04]))
        cycle.create_dataset("operator_cut_length_m", data=np.asarray([1.0]))
        cycle.create_dataset("operator_cut_payload_gain_kg", data=np.asarray([30.0]))
        cycle.create_dataset("dig_outcome_payload_gain_kg", data=np.asarray([30.0]))
        cycle.create_dataset(
            "dig_outcome_effective_deposit_delta_kg",
            data=np.asarray([25.0]),
        )
        cycle.create_dataset(
            "depth_outcome_source",
            data=np.asarray([b"env_state_removed_depth_delta"]),
        )


if __name__ == "__main__":
    unittest.main()
