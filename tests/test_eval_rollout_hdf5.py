from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import read_episode
from testbed.data.recorder import EpisodeRecorder
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_INDEX_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_INDEX_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_ORDER_V2_2,
    ENV_STATE_V2_2_DIM,
)
from testbed.eval.rollout_hdf5 import (
    build_rollout_v2_payload,
    enrich_rollout_hdf5_in_place,
)
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM, LONG_AXIS_Z


class EvalRolloutHdf5Tests(unittest.TestCase):
    def test_schema_order_is_add_only_64d(self) -> None:
        self.assertEqual(len(ENV_STATE_ORDER_V2_2), ENV_STATE_V2_2_DIM)
        self.assertEqual(ENV_STATE_ORDER_V2_2[0], "mass_in_bucket_kg")
        self.assertEqual(ENV_STATE_ORDER_V2_2[27], "bucket_dig_area_cell_id")
        self.assertEqual(ENV_STATE_ORDER_V2_2[28], "bucket_tip_dig_area_x_m")
        self.assertEqual(ENV_STATE_ORDER_V2_2[63], "hard_collision_count")

    def test_rollout_hdf5_writes_v2_and_cell_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            recorder = EpisodeRecorder(
                output_dir=output_dir,
                episode_idx=0,
                metadata={
                    "task_name": "agx_excavation_teleop",
                    "env_state_order": ",".join(ENV_STATE_ORDER_V2_2),
                },
                camera_names=["fpv"],
            )
            step_records = []
            for step in range(6):
                env_state = _env_state_for_step(step)
                obs = {
                    "qpos": np.zeros(4, dtype=np.float32),
                    "qvel": np.zeros(4, dtype=np.float32),
                    "env_state": env_state,
                    "images": {
                        "fpv": np.zeros((2, 2, 3), dtype=np.uint8),
                    },
                    "step_id": step,
                }
                action = np.zeros(4, dtype=np.float32)
                recorder.record(
                    obs=obs,
                    action=action,
                    reward=float(step),
                    step_id=step,
                    step_ns=1000 + step,
                    action_src_type="policy",
                    action_src_id="policy:test",
                )
                step_records.append(
                    {
                        "t": step,
                        "cycle_id": 0,
                        "mode_id": 1,
                        "reward_phase": "loading",
                        "env_state": env_state,
                        "action": action,
                        "goal_tokens": np.zeros(10, dtype=np.float32),
                        "qualified_dig_start_mask": 1 if step == 1 else 0,
                        "dump_end_mask": 1 if step == 5 else 0,
                    }
                )

            path = recorder.save(success=True, v2=build_rollout_v2_payload(step_records))
            summary = enrich_rollout_hdf5_in_place(path)
            episode = read_episode(path)

            self.assertEqual(episode["env_state"].shape, (6, ENV_STATE_V2_2_DIM))
            self.assertEqual(episode["step_ns"].tolist(), [1000, 1001, 1002, 1003, 1004, 1005])
            self.assertEqual(episode["action_src_types"], ["policy"] * 6)
            self.assertIn("cell_entry_tokens", episode["v2"]["step"])
            self.assertEqual(
                episode["v2"]["step"]["cell_entry_tokens"].shape,
                (6, CELL_ENTRY_TOKEN_DIM),
            )
            self.assertEqual(summary["cycle_count"], 1)


def _env_state_for_step(step: int) -> np.ndarray:
    env_state = np.zeros(ENV_STATE_V2_2_DIM, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(step * 40)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(max(0, step - 2) * 20)
    env_state[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env_state[ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = float(LONG_AXIS_Z)
    env_state[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    env_state[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = -0.625
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = -0.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_INDEX_IDX] = 1.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_INDEX_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 2.0
    return env_state


if __name__ == "__main__":
    unittest.main()
