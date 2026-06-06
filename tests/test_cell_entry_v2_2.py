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
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_2_DIM,
)
from testbed.planner import cell_entry as cell_entry_module
from testbed.planner import cell_entry_runtime as cell_entry_runtime_module
from testbed.planner.cell_entry import (
    AUDIT_REASON_GEOMETRY_UNAVAILABLE,
    AUDIT_REASON_TARGET_CELL_MISS,
    AUDIT_REASON_TO_ID,
    CELL_ENTRY_RUNTIME_FACT_FIELDS,
    CELL_ENTRY_RUNTIME_STATE_FIELDS,
    CELL_ENTRY_TOKEN_DIM,
    LONG_AXIS_Z,
    CellEntryPlanner,
    CellEntryRuntimeConfig,
    CellEntryRuntimeFacts,
    CellEntryRuntimeService,
    CellEntryRuntimeState,
    CellGridSpec,
    PlannerDecisionAudit,
    PlannerDecisionAuditor,
    PrimitiveCycleOutcome,
    build_cell_entry_planner_config,
    build_cell_entry_runtime_facts_from_mapping,
    build_cell_entry_runtime_facts_from_observation_view,
    build_cell_entry_runtime_state_from_mapping,
)
from testbed.planner.snapshots import build_planner_snapshot


class TestCellEntryV22(unittest.TestCase):
    def test_runtime_symbols_remain_compatible_facades(self) -> None:
        self.assertIs(
            cell_entry_module.CELL_ENTRY_RUNTIME_FACT_FIELDS,
            cell_entry_runtime_module.CELL_ENTRY_RUNTIME_FACT_FIELDS,
        )
        self.assertIs(
            cell_entry_module.CELL_ENTRY_RUNTIME_STATE_FIELDS,
            cell_entry_runtime_module.CELL_ENTRY_RUNTIME_STATE_FIELDS,
        )
        self.assertIs(
            cell_entry_module.CellEntryDebugSnapshot,
            cell_entry_runtime_module.CellEntryDebugSnapshot,
        )
        self.assertIs(
            cell_entry_module.CellEntryRuntimeCompletionResult,
            cell_entry_runtime_module.CellEntryRuntimeCompletionResult,
        )
        self.assertIs(
            cell_entry_module.CellEntryRuntimeConfig,
            cell_entry_runtime_module.CellEntryRuntimeConfig,
        )
        self.assertIs(
            cell_entry_module.CellEntryRuntimeFacts,
            cell_entry_runtime_module.CellEntryRuntimeFacts,
        )
        self.assertIs(
            cell_entry_module.CellEntryRuntimeService,
            cell_entry_runtime_module.CellEntryRuntimeService,
        )
        self.assertIs(
            cell_entry_module.CellEntryRuntimeState,
            cell_entry_runtime_module.CellEntryRuntimeState,
        )
        self.assertIs(
            cell_entry_module.CellEntryRuntimeTokenResult,
            cell_entry_runtime_module.CellEntryRuntimeTokenResult,
        )
        self.assertIs(
            cell_entry_module.build_cell_entry_runtime_facts_from_mapping,
            cell_entry_runtime_module.build_cell_entry_runtime_facts_from_mapping,
        )
        self.assertIs(
            cell_entry_module.build_cell_entry_runtime_facts_from_observation_view,
            cell_entry_runtime_module.build_cell_entry_runtime_facts_from_observation_view,
        )
        self.assertIs(
            cell_entry_module.build_cell_entry_runtime_state_from_mapping,
            cell_entry_runtime_module.build_cell_entry_runtime_state_from_mapping,
        )
        self.assertIs(
            cell_entry_module._runtime_outcome,
            cell_entry_runtime_module._runtime_outcome,
        )

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

    def test_build_cell_entry_planner_config_preserves_defaults_and_overrides(
        self,
    ) -> None:
        default_config = build_cell_entry_planner_config(
            cell_entry_enabled=False,
            cell_entry_grid=None,
            cell_entry_low_productivity_payload_gain_kg=100.0,
        )

        self.assertFalse(default_config.cell_entry_enabled)
        self.assertIsInstance(default_config.cell_entry_grid, CellGridSpec)
        self.assertEqual(default_config.cell_entry_grid.long_axis, LONG_AXIS_Z)
        self.assertAlmostEqual(
            default_config.cell_entry_low_productivity_payload_gain_kg,
            100.0,
        )

        override_config = build_cell_entry_planner_config(
            cell_entry_enabled=True,
            cell_entry_grid={
                "half_long_m": 2.0,
                "half_short_m": 1.0,
                "entry_margin_m": 0.1,
            },
            cell_entry_low_productivity_payload_gain_kg=45,
        )

        self.assertTrue(override_config.cell_entry_enabled)
        self.assertAlmostEqual(override_config.cell_entry_grid.half_long_m, 2.0)
        self.assertAlmostEqual(override_config.cell_entry_grid.half_short_m, 1.0)
        self.assertAlmostEqual(override_config.cell_entry_grid.entry_margin_m, 0.1)
        self.assertAlmostEqual(
            override_config.cell_entry_low_productivity_payload_gain_kg,
            45.0,
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

    def test_runtime_service_builds_tokens_and_updates_seen_cell(self) -> None:
        grid = CellGridSpec(long_axis=LONG_AXIS_Z)
        planner = CellEntryPlanner(grid=grid)
        auditor = PlannerDecisionAuditor(grid=grid)
        service = CellEntryRuntimeService()

        result = service.tokens_for_obs(
            planner=planner,
            auditor=auditor,
            facts=CellEntryRuntimeFacts(
                cycle_index=0,
                active_skill="dig",
                cell_id=2,
                bucket_pose=(-0.625, 0.0, 0.0),
                geometry_available=True,
                bucket_mass_kg=0.0,
            ),
            config=CellEntryRuntimeConfig(enabled=True),
            state=CellEntryRuntimeState(),
        )

        self.assertIsNotNone(result.tokens)
        self.assertEqual(result.tokens.shape, (CELL_ENTRY_TOKEN_DIM,))
        self.assertIsNotNone(result.state.goal)
        self.assertEqual(result.state.goal.selected_cell_id, 2)
        self.assertEqual(result.state.goal_cycle_id, 0)
        self.assertEqual(result.state.seen_cell_id, 2)
        self.assertIsNotNone(result.state.audit)
        self.assertTrue(result.state.audit.planner_ok)

    def test_runtime_service_initial_state_preserves_legacy_reset_defaults(self) -> None:
        state = CellEntryRuntimeService.initial_runtime_state()
        other_state = CellEntryRuntimeService.initial_runtime_state()

        self.assertIsInstance(state, CellEntryRuntimeState)
        self.assertIsNone(state.goal)
        self.assertEqual(state.goal_cycle_id, -1)
        self.assertIsNone(state.audit)
        self.assertIsNotNone(state.tokens)
        self.assertEqual(state.tokens.shape, (CELL_ENTRY_TOKEN_DIM,))
        self.assertEqual(state.tokens.dtype, np.float32)
        self.assertAlmostEqual(float(np.max(np.abs(state.tokens))), 0.0)
        self.assertFalse(state.token_injected)
        self.assertEqual(state.seen_cell_id, -1)
        self.assertEqual(state.trace_events, ())

        state.tokens[0] = 99.0
        self.assertAlmostEqual(float(other_state.tokens[0]), 0.0)

    def test_runtime_facts_mapping_preserves_planner_projection(self) -> None:
        values = {
            "cycle_index": np.int64(3),
            "active_skill": 123,
            "cell_id": "2",
            "bucket_pose": (0.1, 0.2, 0.3),
            "geometry_available": 1,
            "bucket_mass_kg": "12.5",
            "ignored": object(),
        }

        facts = build_cell_entry_runtime_facts_from_mapping(values)

        self.assertEqual(set(CELL_ENTRY_RUNTIME_FACT_FIELDS), set(values) - {"ignored"})
        self.assertEqual(facts.cycle_index, 3)
        self.assertEqual(facts.active_skill, "123")
        self.assertEqual(facts.cell_id, 2)
        self.assertEqual(facts.bucket_pose, (0.1, 0.2, 0.3))
        self.assertTrue(facts.geometry_available)
        self.assertAlmostEqual(facts.bucket_mass_kg, 12.5)

    def test_runtime_facts_from_observation_view_preserves_sources(self) -> None:
        env_state = np.zeros(ENV_STATE_V2_2_DIM, dtype=np.float32)
        env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 2.4
        env_state[ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX] = 1.0
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.25
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.40
        env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 7.5
        obs = {
            "env_state": env_state,
            "task_metrics": {"mass_in_bucket_kg": "12.5"},
        }
        snapshot = build_planner_snapshot(
            obs,
            active_skill="dig",
            cycle_index=3,
            prev_action=None,
            boundary_event=None,
            action_dim=4,
        )

        facts = CellEntryRuntimeService.facts_from_observation_view(
            view=snapshot.view,
            cycle_index=np.int64(3),
            active_skill=123,
        )

        self.assertEqual(
            facts,
            build_cell_entry_runtime_facts_from_observation_view(
                view=snapshot.view,
                cycle_index=np.int64(3),
                active_skill=123,
            ),
        )
        self.assertEqual(facts.cycle_index, 3)
        self.assertEqual(facts.active_skill, "123")
        self.assertEqual(facts.cell_id, 2)
        np.testing.assert_allclose(facts.bucket_pose, (0.25, 0.0, 0.40))
        self.assertTrue(facts.geometry_available)
        self.assertAlmostEqual(facts.bucket_mass_kg, 12.5)

    def test_runtime_facts_from_observation_view_preserves_missing_env_defaults(
        self,
    ) -> None:
        snapshot = build_planner_snapshot(
            {},
            active_skill="dig",
            cycle_index=0,
            prev_action=None,
            boundary_event=None,
            action_dim=4,
        )

        facts = CellEntryRuntimeService.facts_from_observation_view(
            view=snapshot.view,
            cycle_index=0,
            active_skill="dig",
        )

        self.assertEqual(facts.cell_id, -1)
        self.assertIsNone(facts.bucket_pose)
        self.assertFalse(facts.geometry_available)
        self.assertAlmostEqual(facts.bucket_mass_kg, 0.0)

    def test_runtime_state_mapping_preserves_service_input_defaults(self) -> None:
        planner = CellEntryPlanner(grid=CellGridSpec(long_axis=LONG_AXIS_Z))
        goal = planner.plan(cycle_id=3)
        audit = PlannerDecisionAudit(
            cycle_id=3,
            planner_ok=True,
            risk_flags=0,
            reason_code=AUDIT_REASON_TO_ID["ok"],
            reason="ok",
            inside_entry_envelope=True,
            distance_to_entry_envelope_m=0.0,
            entry_delta_x_m=0.0,
            entry_delta_y_m=0.0,
            entry_delta_z_m=0.0,
            target_cell_match=True,
        )
        tokens = np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float64)
        values = {
            "goal": goal,
            "goal_cycle_id": "3",
            "audit": audit,
            "tokens": tokens,
            "seen_cell_id": np.int64(2),
            "ignored": object(),
        }

        state = build_cell_entry_runtime_state_from_mapping(values)

        self.assertEqual(
            {key for key, _ in CELL_ENTRY_RUNTIME_STATE_FIELDS},
            set(values) - {"ignored"},
        )
        self.assertIs(state.goal, goal)
        self.assertEqual(state.goal_cycle_id, 3)
        self.assertIs(state.audit, audit)
        self.assertIs(state.tokens, tokens)
        self.assertFalse(state.token_injected)
        self.assertEqual(state.seen_cell_id, 2)
        self.assertEqual(state.trace_events, ())

    def test_runtime_service_completion_uses_seen_cell_for_trace(self) -> None:
        grid = CellGridSpec(long_axis=LONG_AXIS_Z)
        planner = CellEntryPlanner(grid=grid)
        auditor = PlannerDecisionAuditor(grid=grid)
        service = CellEntryRuntimeService()
        token_result = service.tokens_for_obs(
            planner=planner,
            auditor=auditor,
            facts=CellEntryRuntimeFacts(
                cycle_index=0,
                active_skill="dig",
                cell_id=2,
                bucket_pose=(-0.625, 0.0, 0.0),
                geometry_available=True,
                bucket_mass_kg=0.0,
            ),
            config=CellEntryRuntimeConfig(enabled=True),
            state=CellEntryRuntimeState(),
        )

        completion = service.complete_dig(
            planner=planner,
            facts=CellEntryRuntimeFacts(
                cycle_index=0,
                active_skill="dig",
                cell_id=-1,
                bucket_pose=None,
                geometry_available=False,
                bucket_mass_kg=150.0,
            ),
            config=CellEntryRuntimeConfig(enabled=True),
            state=token_result.state,
        )

        self.assertIsNotNone(completion.trace_event)
        self.assertEqual(completion.trace_event["cycle_id"], 0)
        self.assertEqual(completion.trace_event["selected_cell_id"], 2)
        self.assertEqual(completion.trace_event["actual_cell_id"], 2)
        self.assertAlmostEqual(float(completion.trace_event["payload_gain_kg"]), 150.0)
        self.assertEqual(completion.trace_event["audit_reason_code"], 0)
        self.assertEqual(completion.trace_event["audit_reason"], "ok")

    def test_runtime_service_debug_snapshot_uses_legacy_empty_fallbacks(self) -> None:
        service = CellEntryRuntimeService()

        snapshot = service.debug_snapshot(
            state=CellEntryRuntimeState(seen_cell_id=4)
        )

        self.assertEqual(snapshot.selected_cell_id, -1)
        self.assertEqual(snapshot.selected_long_index, -1)
        self.assertEqual(snapshot.selected_short_index, -1)
        self.assertTrue(np.isnan(snapshot.planned_entry_x_m))
        self.assertTrue(np.isnan(snapshot.planned_entry_y_m))
        self.assertTrue(np.isnan(snapshot.planned_entry_z_m))
        self.assertFalse(snapshot.planner_ok)
        self.assertEqual(snapshot.audit_reason_code, -1)
        self.assertEqual(snapshot.audit_reason, "")
        self.assertEqual(snapshot.audit_risk_flags, 0)
        self.assertFalse(snapshot.inside_entry_envelope)
        self.assertTrue(np.isnan(snapshot.distance_to_entry_envelope_m))
        self.assertEqual(snapshot.seen_cell_id, 4)

    def test_runtime_service_debug_snapshot_projects_goal_audit_and_seen_cell(self) -> None:
        grid = CellGridSpec(long_axis=LONG_AXIS_Z)
        planner = CellEntryPlanner(grid=grid)
        auditor = PlannerDecisionAuditor(grid=grid)
        goal = planner.plan(cycle_id=3)
        audit = auditor.audit(
            goal=goal,
            outcome=PrimitiveCycleOutcome(
                cycle_id=3,
                actual_start_step=1,
                actual_bite_step=2,
                actual_removal_step=2,
                actual_start_cell_id=goal.selected_cell_id,
                actual_bite_cell_id=goal.selected_cell_id,
                actual_removal_cell_id=goal.selected_cell_id,
                payload_gain_kg=150.0,
                deposit_delta_kg=0.0,
                collision_count_delta=0,
            ),
            current_bucket_pose=(
                goal.planned_entry_x_m,
                goal.planned_entry_y_m,
                goal.planned_entry_z_m,
            ),
            geometry_available=True,
        )

        snapshot = CellEntryRuntimeService.debug_snapshot(
            state=CellEntryRuntimeState(
                goal=goal,
                goal_cycle_id=3,
                audit=audit,
                seen_cell_id=5,
            )
        )

        self.assertEqual(snapshot.selected_cell_id, goal.selected_cell_id)
        self.assertEqual(snapshot.selected_long_index, goal.selected_long_index)
        self.assertEqual(snapshot.selected_short_index, goal.selected_short_index)
        self.assertAlmostEqual(snapshot.planned_entry_x_m, goal.planned_entry_x_m)
        self.assertAlmostEqual(snapshot.planned_entry_y_m, goal.planned_entry_y_m)
        self.assertAlmostEqual(snapshot.planned_entry_z_m, goal.planned_entry_z_m)
        self.assertTrue(snapshot.planner_ok)
        self.assertEqual(snapshot.audit_reason_code, AUDIT_REASON_TO_ID["ok"])
        self.assertEqual(snapshot.audit_reason, "ok")
        self.assertEqual(snapshot.audit_risk_flags, 0)
        self.assertTrue(snapshot.inside_entry_envelope)
        self.assertAlmostEqual(snapshot.distance_to_entry_envelope_m, 0.0)
        self.assertEqual(snapshot.seen_cell_id, 5)

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
