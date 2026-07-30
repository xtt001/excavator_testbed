from __future__ import annotations

import json

import numpy as np
import pytest

from testbed.eval.terrain_gold_cycle_samples import (
    GoldCycleSampleReplayRecorder,
    build_gold_cycle_sample_records,
    write_gold_cycle_sample_jsonl,
)
from testbed.eval.terrain_residual_contract import list_replay_snapshot_target_specs


def _cycle_quality_report() -> dict[str, object]:
    return {
        "schema": "terrain_cycle_quality_report_v1",
        "source": "rollout_jsonl_per_cycle_terrain_quality_report",
        "status": "present",
        "branch_name": "heuristic_residual_pipeline",
        "target_spec": {
            "target_id": "t1_large_shallow_rectangular_pit_default",
            "official_semantics": "official_phase6_v0_default",
        },
        "cycles": [
            {
                "cycle_index": 0,
                "residual_summary": {
                    "status": "present",
                    "removed_depth_grid_start_m": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "removed_depth_grid_end_m": [0.1, 0.0, 0.2, 0.0, 0.0, 0.0],
                    "target_depth_grid_m": [0.25, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "target_region_mask": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "valid_mask": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                    "cell_area_m2": 0.5,
                    "target_positive_residual_depth_sum_start_m": 1.0,
                    "target_positive_residual_depth_sum_end_m": 0.9,
                    "target_positive_residual_depth_sum_delta_m": -0.1,
                    "target_removed_completion_ratio_start": 0.0,
                    "target_removed_completion_ratio_end": 0.1,
                    "target_removed_completion_ratio_delta": 0.1,
                    "target_overdig_depth_sum_end_m": 0.0,
                    "outside_target_removed_depth_sum_end_m": 0.0,
                },
                "payload_summary": {
                    "payload_peak_kg": 29.0,
                    "effective_deposit_delta_kg": 20.0,
                    "deposited_fraction": 0.69,
                },
                "execution_quality_summary": {
                    "success": 0,
                    "depth_target_m": 0.02,
                    "depth_peak_m": 0.24,
                    "depth_error_m": 0.22,
                    "depth_abs_error_m": 0.22,
                    "entry_planned_x_m": 0.0,
                    "entry_planned_z_m": 0.0,
                    "entry_actual_x_m": 0.12,
                    "entry_actual_z_m": -0.09,
                    "entry_error_m": 0.15,
                    "exit_planned_x_m": 0.5,
                    "exit_planned_z_m": 0.0,
                    "exit_actual_x_m": 0.42,
                    "exit_actual_z_m": -0.08,
                    "exit_error_m": 0.11313708499,
                    "exit_abs_overshoot_m": 0.08,
                },
                "handoff_summary": {
                    "completed_transition_count": 1,
                    "transition_timeout_count": 0,
                },
            }
        ],
    }


def test_build_gold_cycle_samples_records_one_sample_per_cycle() -> None:
    result = build_gold_cycle_sample_records(
        _cycle_quality_report(),
        episode_id="episode_a",
        rollout_id="rollout_000",
        low_payload_mass_threshold_kg=30.0,
    )

    assert result["status"] == "present"
    assert result["schema"] == "terrain_gold_cycle_samples_v1"
    assert result["source"] == "official_gold_cycle_sample_builder"
    assert result["record_count"] == 1
    assert result["required_payload_label"] == "payload_mass_kg"
    assert result["volume_label_status"] == "derived_grid_integral"
    assert result["records"] == [
        {
            "schema": "terrain_gold_cycle_sample_v1",
            "source": "official_gold_cycle_sample_builder",
            "episode_id": "episode_a",
            "rollout_id": "rollout_000",
            "cycle_index": 0,
            "branch_name": "heuristic_residual_pipeline",
            "target_id": "t1_large_shallow_rectangular_pit_default",
            "removed_depth_grid_start_m": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "removed_depth_grid_end_m": [0.1, 0.0, 0.2, 0.0, 0.0, 0.0],
            "target_depth_grid_m": [0.25, 0.0, 0.0, 0.0, 0.0, 0.0],
            "target_region_mask": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "valid_mask": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            "target_positive_residual_depth_sum_start_m": 1.0,
            "target_positive_residual_depth_sum_end_m": 0.9,
            "target_positive_residual_depth_sum_delta_m": -0.1,
            "target_removed_completion_ratio_start": 0.0,
            "target_removed_completion_ratio_end": 0.1,
            "target_removed_completion_ratio_delta": 0.1,
            "target_overdig_depth_sum_m": 0.0,
            "outside_target_removed_depth_sum_m": 0.0,
            "payload_mass_kg": 29.0,
            "effective_deposit_mass_kg": 20.0,
            "deposited_fraction": 0.69,
            "depth_target_m": 0.02,
            "depth_peak_m": 0.24,
            "depth_error_m": 0.22,
            "depth_abs_error_m": 0.22,
            "entry_planned_x_m": 0.0,
            "entry_planned_z_m": 0.0,
            "entry_actual_x_m": 0.12,
            "entry_actual_z_m": -0.09,
            "entry_error_m": 0.15,
            "exit_planned_x_m": 0.5,
            "exit_planned_z_m": 0.0,
            "exit_actual_x_m": 0.42,
            "exit_actual_z_m": -0.08,
            "exit_error_m": 0.11313708499,
            "exit_abs_overshoot_m": 0.08,
            "completed_transition_count": 1,
            "transition_timeout_count": 0,
            "success": False,
            "overdig_event": False,
            "low_payload_event": True,
            "signed_depth_delta_m": [0.1, 0.0, 0.2, 0.0, 0.0, 0.0],
            "removed_volume_by_cell_m3": [0.05, 0.0, 0.1, 0.0, 0.0, 0.0],
            "refill_volume_by_cell_m3": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "removed_volume_m3": 0.15,
            "refill_volume_m3": 0.0,
            "volume_label_status": "derived_grid_integral",
            "direct_volume_status": "unavailable_no_sensor",
        }
    ]


def test_gold_cycle_samples_require_split_key_and_no_overwrite(tmp_path) -> None:
    missing_split = build_gold_cycle_sample_records(
        _cycle_quality_report(),
        low_payload_mass_threshold_kg=30.0,
    )

    assert missing_split["status"] == "missing_split_key"
    assert missing_split["records"] == []

    output_path = tmp_path / "gold_cycle_samples.jsonl"
    first = write_gold_cycle_sample_jsonl(
        _cycle_quality_report(),
        output_path=output_path,
        episode_id="episode_a",
        low_payload_mass_threshold_kg=30.0,
    )
    second = write_gold_cycle_sample_jsonl(
        _cycle_quality_report(),
        output_path=output_path,
        episode_id="episode_a",
        low_payload_mass_threshold_kg=30.0,
    )

    assert first["status"] == "present"
    assert output_path.read_text(encoding="utf-8").splitlines() == [
        json.dumps(first["records"][0], sort_keys=True)
    ]
    assert second["status"] == "output_path_already_exists"


def test_replay_recorder_builds_cycle_sample_on_dump_end() -> None:
    from testbed.data.schema import (
        ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
        ENV_STATE_DIG_AREA_CELL_AREA_IDX,
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX,
        ENV_STATE_MASS_IN_BUCKET_IDX,
        ENV_STATE_V2_3_DIM,
    )

    def env_state(
        removed_depth: list[float],
        *,
        bucket_mass_kg: float,
        dumped_mass_kg: float,
    ) -> np.ndarray:
        values = [0.0] * ENV_STATE_V2_3_DIM
        values[ENV_STATE_MASS_IN_BUCKET_IDX] = bucket_mass_kg
        values[ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX] = dumped_mass_kg
        values[
            ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX : ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
            + 6
        ] = removed_depth
        values[
            ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
            + 6
        ] = [1.0] * 6
        values[ENV_STATE_DIG_AREA_CELL_AREA_IDX] = 0.5
        values[
            ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX :
            ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX + 6
        ] = [1.0] * 6
        return np.array(values, dtype=np.float32)

    recorder = GoldCycleSampleReplayRecorder(
        target_id="t1_large_shallow_rectangular_pit_default",
        episode_id="episode_a",
        rollout_id="rollout_000",
        low_payload_mass_threshold_kg=20.0,
    )

    recorder.observe(env_state([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], bucket_mass_kg=0.0, dumped_mass_kg=0.0))
    recorder.observe(env_state([0.1, 0.0, 0.2, 0.0, 0.0, 0.0], bucket_mass_kg=24.0, dumped_mass_kg=0.0))
    recorder.observe(
        env_state([0.1, 0.0, 0.2, 0.0, 0.0, 0.0], bucket_mass_kg=2.0, dumped_mass_kg=18.0),
        dump_end=True,
    )

    result = recorder.build_result()

    assert result["status"] == "present"
    assert result["record_count"] == 1
    record = result["records"][0]
    assert record["cycle_index"] == 0
    assert record["cycle_start_observation_index"] == 0
    assert record["cycle_end_observation_index"] == 2
    assert record["target_positive_residual_depth_sum_start_m"] == 1.0
    np.testing.assert_allclose(
        record["target_positive_residual_depth_sum_end_m"],
        0.7,
    )
    assert record["payload_mass_kg"] == 24.0
    assert record["effective_deposit_mass_kg"] == 18.0
    assert record["low_payload_event"] is False
    assert record["removed_depth_grid_start_m"] == [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    ]
    np.testing.assert_allclose(
        record["removed_depth_grid_end_m"],
        [0.1, 0.0, 0.2, 0.0, 0.0, 0.0],
    )
    assert record["volume_label_status"] == "derived_grid_integral"
    assert record["direct_volume_status"] == "unavailable_no_sensor"
    assert record["removed_volume_m3"] == pytest.approx(0.15)
    assert record["refill_volume_m3"] == pytest.approx(0.0)
    assert record["evidence_kind"] == "replay_derived_open_loop"
    assert record["planner_trace_status"] == "missing_not_generated_by_replay"
    assert record["actual_response_status"] == "missing_not_generated_by_replay"
    for forbidden_field in (
        "depth_target_m",
        "depth_peak_m",
        "depth_error_m",
        "depth_abs_error_m",
        "entry_planned_x_m",
        "entry_planned_z_m",
        "entry_actual_x_m",
        "entry_actual_z_m",
        "entry_error_m",
        "exit_planned_x_m",
        "exit_planned_z_m",
        "exit_actual_x_m",
        "exit_actual_z_m",
        "exit_error_m",
        "exit_abs_overshoot_m",
        "completed_transition_count",
        "transition_timeout_count",
        "success",
    ):
        assert forbidden_field not in record


def test_replay_snapshot_targets_separate_recording_diagnostic_from_official() -> None:
    specs = list_replay_snapshot_target_specs()

    assert [spec["target_id"] for spec in specs] == [
        "recording_depth_0p08_full_grid_diagnostic",
        "t1_large_shallow_rectangular_pit_default",
        "t2_long_shallow_trench_default",
    ]
    assert specs[0]["target_depth_m"] == pytest.approx(0.08)
    assert specs[0]["evidence_role"] == "recording_diagnostic"
    assert [spec["target_depth_m"] for spec in specs[1:]] == [0.25, 0.25]
    assert all(spec["evidence_role"] == "official_residual" for spec in specs[1:])
