from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from testbed.data.cell_entry_v2_2 import (
    build_cell_entry_dataset,
    enrich_episode_cell_entry,
)
from testbed.data.dataset import get_norm_stats
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.primitives_v2_2 import build_primitive_v2_payload
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
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_2_DIM,
)
from testbed.planner.cell_entry import (
    AUDIT_REASON_GEOMETRY_UNAVAILABLE,
    AUDIT_REASON_TARGET_CELL_MISS,
    AUDIT_REASON_TO_ID,
    CELL_ENTRY_TOKEN_DIM,
    LONG_AXIS_Z,
    CellEntryPlanner,
    CellGridSpec,
    PlannerDecisionAuditor,
    PrimitiveCycleOutcome,
)


class TestCellEntryV22(unittest.TestCase):
    def test_grid_mapping_uses_long_major_cell_ids(self) -> None:
        grid = CellGridSpec(long_axis=LONG_AXIS_Z)

        self.assertEqual(grid.cell_id(long_index=0, short_index=0), 0)
        self.assertEqual(grid.cell_id(long_index=1, short_index=0), 2)
        self.assertEqual(grid.cell_id(long_index=2, short_index=1), 5)
        self.assertEqual(grid.indices_from_cell_id(5), (2, 1))

        x_m, y_m, z_m = grid.local_center(long_index=1, short_index=0)
        self.assertAlmostEqual(x_m, -0.625)
        self.assertAlmostEqual(y_m, 0.0)
        self.assertAlmostEqual(z_m, 0.0)

        self.assertEqual(grid.cell_from_norm(long_norm=1.0, short_norm=1.0), (2, 1, 5))
        self.assertEqual(
            grid.cell_from_norm(long_norm=1.01, short_norm=0.0), (-1, -1, -1)
        )

    def test_planner_initial_choice_and_audit_reasons(self) -> None:
        grid = CellGridSpec(long_axis=LONG_AXIS_Z)
        planner = CellEntryPlanner(grid=grid)
        goal = planner.plan(cycle_id=0)

        self.assertEqual(goal.selected_long_index, 1)
        self.assertEqual(goal.selected_cell_id, 2)

        ok_outcome = PrimitiveCycleOutcome(
            cycle_id=0,
            actual_start_step=1,
            actual_bite_step=2,
            actual_removal_step=2,
            actual_start_cell_id=goal.selected_cell_id,
            actual_bite_cell_id=goal.selected_cell_id,
            actual_removal_cell_id=goal.selected_cell_id,
            payload_gain_kg=150.0,
            deposit_delta_kg=0.0,
            collision_count_delta=0,
        )
        auditor = PlannerDecisionAuditor(grid=grid)
        audit = auditor.audit(
            goal=goal,
            outcome=ok_outcome,
            current_bucket_pose=(
                goal.planned_entry_x_m,
                goal.planned_entry_y_m,
                goal.planned_entry_z_m,
            ),
            geometry_available=True,
        )
        self.assertTrue(audit.planner_ok)
        self.assertEqual(audit.reason_code, AUDIT_REASON_TO_ID["ok"])

        geometry_audit = auditor.audit(
            goal=goal,
            outcome=ok_outcome,
            current_bucket_pose=(
                goal.planned_entry_x_m,
                goal.planned_entry_y_m,
                goal.planned_entry_z_m,
            ),
            geometry_available=False,
        )
        self.assertFalse(geometry_audit.planner_ok)
        self.assertEqual(geometry_audit.reason, AUDIT_REASON_GEOMETRY_UNAVAILABLE)

        miss_outcome = PrimitiveCycleOutcome(
            cycle_id=0,
            actual_start_step=1,
            actual_bite_step=2,
            actual_removal_step=2,
            actual_start_cell_id=goal.selected_cell_id + 1,
            actual_bite_cell_id=goal.selected_cell_id + 1,
            actual_removal_cell_id=goal.selected_cell_id + 1,
            payload_gain_kg=150.0,
            deposit_delta_kg=0.0,
            collision_count_delta=0,
        )
        miss_audit = auditor.audit(
            goal=goal,
            outcome=miss_outcome,
            current_bucket_pose=(
                goal.planned_entry_x_m,
                goal.planned_entry_y_m,
                goal.planned_entry_z_m,
            ),
            geometry_available=True,
        )
        self.assertEqual(miss_audit.reason, AUDIT_REASON_TARGET_CELL_MISS)

    def test_builder_writes_tokens_and_primitive_slice_preserves_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_dir = tmp / "raw"
            output_dir = tmp / "enriched"
            source_dir.mkdir()
            _write_cell_entry_episode(source_dir / "episode_0.hdf5")

            summary = build_cell_entry_dataset(
                dataset_dir=source_dir,
                output_dir=output_dir,
            )
            self.assertEqual(summary["cycle_count"], 1)
            self.assertEqual(summary["planner_ok_rate"], 1.0)

            enriched = read_episode(output_dir / "episode_0.hdf5")
            v2_step = dict(enriched["v2"]["step"])
            v2_cycle = dict(enriched["v2"]["cycle"])
            self.assertEqual(
                v2_step["cell_entry_tokens"].shape, (6, CELL_ENTRY_TOKEN_DIM)
            )
            self.assertEqual(v2_step["selected_cell_id"].tolist(), [2] * 6)
            self.assertEqual(v2_cycle["actual_accepted_start_cell_id"].tolist(), [2])
            self.assertEqual(v2_cycle["cell_entry_planner_ok"].tolist(), [1])
            self.assertAlmostEqual(float(v2_cycle["deposit_delta_kg"][0]), 120.0)

            primitive_v2 = build_primitive_v2_payload(
                source_episode=enriched,
                crop=slice(1, 4),
            )
            self.assertEqual(
                primitive_v2["step"]["cell_entry_tokens"].shape,
                (3, CELL_ENTRY_TOKEN_DIM),
            )

            stats = get_norm_stats(
                output_dir,
                num_episodes=1,
                low_dim_keys=["qpos", "qvel", "cell_entry_tokens"],
            )
            self.assertEqual(stats["proprio_mean"].shape[0], 8 + CELL_ENTRY_TOKEN_DIM)

    def test_builder_keeps_legacy_env_state_compatible_but_unknown(self) -> None:
        episode = _legacy_episode()

        v2, summary = enrich_episode_cell_entry(episode=episode)

        self.assertEqual(summary["cycle_count"], 1)
        self.assertEqual(summary["planner_ok_count"], 0)
        self.assertEqual(
            int(v2["cycle"]["actual_accepted_start_cell_id"][0]),
            -1,
        )
        self.assertEqual(
            int(v2["cycle"]["cell_entry_audit_reason_code"][0]),
            AUDIT_REASON_TO_ID[AUDIT_REASON_GEOMETRY_UNAVAILABLE],
        )

    def test_actual_removal_prefers_removed_depth_delta_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "episode_0.hdf5"
            _write_cell_entry_episode(path, with_removed_depth=True)

            episode = read_episode(path)
            v2, _summary = enrich_episode_cell_entry(episode=episode)

            self.assertEqual(int(v2["cycle"]["actual_removal_step"][0]), 3)
            self.assertEqual(int(v2["cycle"]["actual_removal_cell_id"][0]), 5)

    def test_builder_vds_mode_virtualizes_source_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_dir = tmp / "raw"
            output_dir = tmp / "enriched_vds"
            source_dir.mkdir()
            _write_cell_entry_episode(source_dir / "episode_0.hdf5")

            summary = build_cell_entry_dataset(
                dataset_dir=source_dir,
                output_dir=output_dir,
                storage_mode="vds",
            )
            self.assertEqual(summary["storage_mode"], "vds")

            enriched = read_episode(output_dir / "episode_0.hdf5")
            self.assertEqual(enriched["qpos"].shape, (6, 4))
            self.assertEqual(
                enriched["v2"]["step"]["cell_entry_tokens"].shape,
                (6, CELL_ENTRY_TOKEN_DIM),
            )
            with h5py.File(output_dir / "episode_0.hdf5", "r") as f:
                self.assertTrue(f["observations/qpos"].is_virtual)
                self.assertTrue(f["v2/step/cycle_id"].is_virtual)
                self.assertFalse(f["v2/step/cell_entry_tokens"].is_virtual)
                self.assertEqual(f["metadata"].attrs["storage_mode"], "vds")
            self.assertTrue((output_dir / "lineage.json").exists())


def _write_cell_entry_episode(path: Path, *, with_removed_depth: bool = False) -> None:
    n_steps = 6
    env_dim = ENV_STATE_V2_2_DIM if with_removed_depth else 28
    env_state = np.zeros((n_steps, env_dim), dtype=np.float32)
    env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] = [0.0, 0.0, 180.0, 180.0, 90.0, 10.0]
    env_state[:, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = [
        0.0,
        0.0,
        0.0,
        40.0,
        90.0,
        120.0,
    ]
    env_state[:, ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
    env_state[:, ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = float(LONG_AXIS_Z)
    env_state[:, ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    env_state[:, ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = -0.625
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.0
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.0
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = -0.5
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_LONG_INDEX_IDX] = 1.0
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_SHORT_INDEX_IDX] = 0.0
    env_state[:, ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 2.0
    if with_removed_depth:
        env_state[:, ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + 6] = 1.0
        env_state[:, ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 5] = [
            0.0,
            0.0,
            0.002,
            0.03,
            0.05,
            0.05,
        ]

    v2_step = {
        "cycle_id": np.zeros(n_steps, dtype=np.int32),
        "qualified_dig_start_mask": np.asarray([0, 1, 0, 0, 0, 0], dtype=np.uint8),
    }
    write_episode(
        path,
        qpos=np.zeros((n_steps, 4), dtype=np.float32),
        qvel=np.zeros((n_steps, 4), dtype=np.float32),
        actions=np.zeros((n_steps, 4), dtype=np.float32),
        env_state=env_state,
        step_ids=np.arange(n_steps, dtype=np.int64),
        v2={"step": v2_step, "cycle": {}},
    )


def _legacy_episode() -> dict[str, object]:
    n_steps = 4
    env_state = np.zeros((n_steps, 16), dtype=np.float32)
    env_state[:, ENV_STATE_MASS_IN_BUCKET_IDX] = [0.0, 0.0, 150.0, 150.0]
    return {
        "qpos": np.zeros((n_steps, 4), dtype=np.float32),
        "qvel": np.zeros((n_steps, 4), dtype=np.float32),
        "actions": np.zeros((n_steps, 4), dtype=np.float32),
        "images": {},
        "rewards": None,
        "env_state": env_state,
        "metadata": {},
        "v2": {
            "step": {
                "cycle_id": np.zeros(n_steps, dtype=np.int32),
                "qualified_dig_start_mask": np.asarray([0, 1, 0, 0], dtype=np.uint8),
            },
            "cycle": {},
        },
    }


if __name__ == "__main__":
    unittest.main()
