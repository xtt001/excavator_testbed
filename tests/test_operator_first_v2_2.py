from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.data.dataset import get_norm_stats
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    build_operator_first_dataset,
    enrich_episode_operator_first,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_2_DIM,
)
from testbed.data.v2_1 import WORK_STAGE_NAME_TO_ID


class OperatorFirstV22Tests(unittest.TestCase):
    def test_enrichment_adds_dig_cut_tokens_without_overwriting_legacy_deposit(self) -> None:
        episode = _operator_episode()

        v2, summary = enrich_episode_operator_first(episode=episode)

        self.assertEqual(summary["cycle_count"], 1)
        self.assertEqual(v2["step"]["dig_cut_tokens"].shape, (8, DIG_CUT_TOKEN_DIM))
        self.assertAlmostEqual(float(v2["cycle"]["deposit_delta_kg"][0]), 7.0)
        self.assertGreater(
            float(v2["cycle"]["cycle_effective_deposit_delta_kg"][0]),
            float(v2["cycle"]["deposit_delta_kg"][0]),
        )
        self.assertEqual(str(v2["cycle"]["training_tier"][0]), "gold")

    def test_vds_builder_and_loader_support_dig_cut_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_dir = tmp / "relabeled"
            output_dir = tmp / "operator"
            source_dir.mkdir()
            _write_operator_episode(source_dir / "episode_0.hdf5")

            summary = build_operator_first_dataset(
                dataset_dir=source_dir,
                output_dir=output_dir,
                storage_mode="vds",
            )
            self.assertEqual(summary["episode_count"], 1)
            self.assertEqual(summary["cycle_count"], 1)

            enriched = read_episode(output_dir / "episode_0.hdf5")
            self.assertEqual(
                enriched["v2"]["step"]["dig_cut_tokens"].shape,
                (8, DIG_CUT_TOKEN_DIM),
            )
            with h5py.File(output_dir / "episode_0.hdf5", "r") as f:
                self.assertTrue(f["observations/qpos"].is_virtual)
                self.assertFalse(f["v2/step/dig_cut_tokens"].is_virtual)
                self.assertEqual(f["metadata"].attrs["storage_mode"], "vds")

            stats = get_norm_stats(
                output_dir,
                num_episodes=1,
                low_dim_keys=["qpos", "qvel", "dig_cut_tokens"],
            )
            self.assertEqual(stats["proprio_mean"].shape[0], 8 + DIG_CUT_TOKEN_DIM)


def _write_operator_episode(path: Path) -> None:
    episode = _operator_episode()
    write_episode(
        path,
        qpos=episode["qpos"],
        qvel=episode["qvel"],
        actions=episode["actions"],
        images={"fpv": np.zeros((8, 2, 2, 3), dtype=np.uint8)},
        rewards=np.zeros(8, dtype=np.float32),
        env_state=episode["env_state"],
        v2=episode["v2"],
        metadata={"task_name": "agx_excavation_teleop"},
    )


def _operator_episode() -> dict:
    n_steps = 8
    env_state = np.zeros((n_steps, ENV_STATE_V2_2_DIM), dtype=np.float32)
    for step in range(n_steps):
        env_state[step, ENV_STATE_MASS_IN_BUCKET_IDX] = float(min(step, 4) * 15)
        env_state[step, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(
            max(0, step - 4) * 12
        )
        env_state[step, ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 1.0 - 0.18 * step
        env_state[step, ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = -0.05 * step
        env_state[step, ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = 0.3
        env_state[step, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = (
            0.02 * step
        )
    work_stage = np.asarray(
        [
            WORK_STAGE_NAME_TO_ID["entry_to_bite"],
            WORK_STAGE_NAME_TO_ID["first_bite"],
            WORK_STAGE_NAME_TO_ID["first_bite"],
            WORK_STAGE_NAME_TO_ID["carry"],
            WORK_STAGE_NAME_TO_ID["approach_dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
            WORK_STAGE_NAME_TO_ID["dump"],
        ],
        dtype=np.uint8,
    )
    v2 = {
        "step": {
            "cycle_id": np.zeros(n_steps, dtype=np.int32),
            "work_stage_id": work_stage,
            "dump_start_mask": np.asarray([0, 0, 0, 0, 1, 0, 0, 0], dtype=np.uint8),
        },
        "cycle": {
            "cycle_id": np.asarray([0], dtype=np.int32),
            "start_step": np.asarray([0], dtype=np.int32),
            "dump_end_step": np.asarray([7], dtype=np.int32),
            "end_step": np.asarray([7], dtype=np.int32),
            "deposit_delta_kg": np.asarray([7.0], dtype=np.float32),
            "cell_entry_target_cell_match": np.asarray([0], dtype=np.uint8),
        },
    }
    return {
        "qpos": np.zeros((n_steps, 4), dtype=np.float32),
        "qvel": np.zeros((n_steps, 4), dtype=np.float32),
        "actions": np.zeros((n_steps, 4), dtype=np.float32),
        "env_state": env_state,
        "v2": v2,
        "metadata": {},
    }


if __name__ == "__main__":
    unittest.main()
