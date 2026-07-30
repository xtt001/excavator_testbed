from __future__ import annotations

import json

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_cycle_quality_report import (
    build_terrain_cycle_quality_report,
    write_terrain_cycle_quality_report,
)


def _env_state(removed_depth: list[float]) -> list[float]:
    values = [0.0] * 64
    values[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    values[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    values[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX : ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        + 6
    ] = removed_depth
    values[
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
        + 6
    ] = [1.0] * 6
    return values


def _report(records: list[dict[str, object]]) -> dict[str, object]:
    return build_terrain_cycle_quality_report(
        records,
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
        branch_name="heuristic_residual_pipeline",
    )


def test_cycle_quality_report_records_residual_payload_deposit_and_handoff() -> None:
    report = _report(
        [
            {
                "primitive_cycle_index": 0,
                "skill_name": "dig",
                "env_state": _env_state([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
                "dig_best_mass_kg": 12.0,
            },
            {
                "primitive_cycle_index": 0,
                "skill_name": "dump",
                "env_state": _env_state([0.10, 0.0, 0.20, 0.0, 0.0, 0.0]),
                "coverage_last_payload_gain_kg": 12.0,
                "coverage_last_effective_deposit_delta_kg": 9.0,
                "dump_start_mask": 1,
                "dump_end_mask": 1,
            },
            {
                "primitive_cycle_index": 0,
                "skill_name": "return",
                "env_state": _env_state([0.10, 0.0, 0.20, 0.0, 0.0, 0.0]),
                "return_to_dig_entry_close": True,
                "return_to_dig_start_envelope_ready": False,
                "return_to_dig_start_envelope_checks": {
                    "local_depth_m": {"ok": False},
                    "dig_contact": {"ok": True},
                },
                "return_to_dig_start_envelope_error": 0.04,
            },
            {
                "primitive_cycle_index": 1,
                "skill_name": "dig",
                "env_state": _env_state([0.10, 0.0, 0.20, 0.0, 0.0, 0.0]),
                "skill_switch_reason": "return_to_dig_start_envelope_ready",
                "return_to_dig_entry_error_m": 0.21,
                "return_to_dig_start_envelope_error": 0.0,
                "return_to_dig_start_envelope_checks": {},
                "dig_best_mass_kg": 8.0,
            },
            {
                "primitive_cycle_index": 1,
                "skill_name": "dump",
                "env_state": _env_state([0.30, 0.0, 0.25, 0.0, 0.0, 0.0]),
                "coverage_last_payload_gain_kg": 8.0,
                "coverage_last_effective_deposit_delta_kg": 4.0,
                "dump_start_mask": 1,
                "dump_end_mask": 1,
            },
        ]
    )

    assert report["status"] == "present"
    assert report["source"] == "rollout_jsonl_per_cycle_terrain_quality_report"
    assert report["schema"] == "terrain_cycle_quality_report_v1"
    assert report["branch_name"] == "heuristic_residual_pipeline"
    assert report["summary"] == {
        "status": "present",
        "cycle_count": 2,
        "completed_cycle_count": 2,
        "target_positive_residual_depth_sum_start_m": 0.25,
        "target_positive_residual_depth_sum_end_m": 0.0,
        "target_positive_residual_depth_sum_delta_m": -0.25,
        "target_overdig_depth_sum_start_m": 0.0,
        "target_overdig_depth_sum_end_m": 0.05,
        "target_overdig_depth_sum_delta_m": 0.05,
        "outside_target_removed_depth_sum_start_m": 0.0,
        "outside_target_removed_depth_sum_end_m": 0.25,
        "outside_target_removed_depth_sum_delta_m": 0.25,
        "payload_peak_kg_mean": 10.0,
        "effective_deposit_delta_kg_mean": 6.5,
        "deposited_fraction_mean": 0.625,
        "deposited_fraction_min": 0.5,
        "completed_transition_count": 1,
        "transition_timeout_count": 0,
    }

    first_cycle = report["cycles"][0]
    assert first_cycle["cycle_index"] == 0
    assert first_cycle["row_start_index"] == 0
    assert first_cycle["row_end_index"] == 2
    assert first_cycle["skill_counts"] == {"dig": 1, "dump": 1, "return": 1}
    assert first_cycle["residual_summary"] == {
        "status": "present",
        "start_row_index": 0,
        "end_row_index": 2,
        "removed_depth_grid_start_m": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "removed_depth_grid_end_m": [0.1, 0.0, 0.2, 0.0, 0.0, 0.0],
        "target_depth_grid_m": [0.25, 0.0, 0.0, 0.0, 0.0, 0.0],
        "target_region_mask": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "valid_mask": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        "target_positive_residual_depth_sum_start_m": 0.25,
        "target_positive_residual_depth_sum_end_m": 0.15,
        "target_positive_residual_depth_sum_delta_m": -0.1,
        "target_overdig_depth_sum_start_m": 0.0,
        "target_overdig_depth_sum_end_m": 0.0,
        "target_overdig_depth_sum_delta_m": 0.0,
        "outside_target_removed_depth_sum_start_m": 0.0,
        "outside_target_removed_depth_sum_end_m": 0.2,
        "outside_target_removed_depth_sum_delta_m": 0.2,
        "target_removed_completion_ratio_start": 0.0,
        "target_removed_completion_ratio_end": 0.4,
        "target_removed_completion_ratio_delta": 0.4,
    }
    assert first_cycle["payload_summary"] == {
        "payload_peak_kg": 12.0,
        "effective_deposit_delta_kg": 9.0,
        "deposited_fraction": 0.75,
    }
    assert first_cycle["handoff_summary"] == {
        "return_row_count": 1,
        "entry_close_return_row_count": 1,
        "envelope_ready_return_row_count": 0,
        "completed_transition_count": 1,
        "completed_transition_row_indices": [3],
        "transition_timeout_count": 0,
        "transition_timeout_row_indices": [],
        "max_return_start_envelope_error": 0.04,
        "failed_envelope_check_names": ["local_depth_m"],
    }


def test_cycle_quality_report_marks_missing_when_no_valid_cycles() -> None:
    report = _report(
        [
            {
                "primitive_cycle_index": -1,
                "skill_name": "bootstrap",
                "env_state": _env_state([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            }
        ]
    )

    assert report["status"] == "missing_cycles"
    assert report["cycles"] == []
    assert report["summary"]["status"] == "missing_cycles"


def test_cycle_quality_report_resolves_official_target_and_pass_fail() -> None:
    records = [
        {
            "primitive_cycle_index": 0,
            "skill_name": "dig",
            "env_state": _env_state([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            "dig_best_mass_kg": 12.0,
        },
        {
            "primitive_cycle_index": 0,
            "skill_name": "dump",
            "env_state": _env_state([0.10, 0.0, 0.20, 0.0, 0.0, 0.0]),
            "coverage_last_payload_gain_kg": 12.0,
            "coverage_last_effective_deposit_delta_kg": 9.0,
            "dump_start_mask": 1,
            "dump_end_mask": 1,
        },
        {
            "primitive_cycle_index": 1,
            "skill_name": "dump",
            "env_state": _env_state([0.10, 0.0, 0.20, 0.0, 0.05, 0.0]),
            "coverage_last_payload_gain_kg": 8.0,
            "coverage_last_effective_deposit_delta_kg": 4.0,
            "dump_start_mask": 1,
            "dump_end_mask": 1,
        },
    ]

    report = build_terrain_cycle_quality_report(
        records,
        official_target_id="t1_large_shallow_rectangular_pit_default",
        branch_name="heuristic_residual_pipeline",
        rollout_summary={
            "target_cycle_gate_success": 1,
            "target_cycle_completed_dump_count": 2,
            "cycle1_depth_abs_error_m": 0.20,
            "cycle2_depth_abs_error_m": 0.24,
        },
        baseline_quality_summary={
            "target_cycle_gate_success": 1,
            "target_cycle_completed_dump_count": 2,
            "transition_timeout_count": 0,
            "latest_target_positive_residual_depth_sum_m": 0.60,
            "latest_target_overdig_depth_sum_m": 0.0,
            "latest_outside_target_removed_depth_sum_m": 0.0,
            "deposited_fraction_mean": 0.90,
            "depth_abs_error_m_mean": 0.05,
        },
    )

    assert report["target_spec"]["target_id"] == "t1_large_shallow_rectangular_pit_default"
    assert report["target_spec"]["official_semantics"] == "official_phase6_v0_default"
    assert report["official_quality_summary"] == {
        "target_cycle_gate_success": 1,
        "target_cycle_completed_dump_count": 2,
        "transition_timeout_count": 0,
        "latest_target_positive_residual_depth_sum_m": 0.7,
        "latest_target_overdig_depth_sum_m": 0.0,
        "latest_outside_target_removed_depth_sum_m": 0.05,
        "deposited_fraction_mean": 0.625,
        "depth_abs_error_m_mean": 0.22,
    }
    assert report["official_pass_fail"]["status"] == "present"
    assert report["official_pass_fail"]["pass"] is False
    assert report["official_pass_fail"]["failed_checks"] == [
        "target_positive_residual_worse_than_baseline",
        "outside_target_removed_worse_than_baseline",
        "deposited_fraction_below_baseline",
        "depth_abs_error_above_baseline",
    ]


def test_write_cycle_quality_report_reads_rollout_artifacts_without_overwrite(
    tmp_path,
) -> None:
    rollout_jsonl = tmp_path / "rollout_000.jsonl"
    rollout_summary = tmp_path / "rollout_000_summary.json"
    output_path = tmp_path / "cycle_quality_report.json"
    rows = [
        {
            "primitive_cycle_index": 0,
            "skill_name": "dig",
            "env_state": _env_state([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            "dig_best_mass_kg": 12.0,
        },
        {
            "primitive_cycle_index": 0,
            "skill_name": "dump",
            "env_state": _env_state([0.10, 0.0, 0.20, 0.0, 0.0, 0.0]),
            "coverage_last_effective_deposit_delta_kg": 9.0,
            "dump_end_mask": 1,
        },
    ]
    rollout_jsonl.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    rollout_summary.write_text(
        json.dumps(
            {
                "cycle1_bucket_mass_out_kg": 20.0,
                "cycle1_target_deposit_final_delta_kg": 10.0,
                "cycle1_deposited_fraction": 0.5,
                "cycle1_depth_target_m": 0.02,
                "cycle1_depth_peak_m": 0.22,
                "cycle1_depth_error_m": 0.20,
                "cycle1_depth_abs_error_m": 0.03,
                "cycle1_entry_planned_x_m": 0.1,
                "cycle1_entry_planned_z_m": -0.2,
                "cycle1_entry_actual_x_m": 0.12,
                "cycle1_entry_actual_z_m": -0.21,
                "cycle1_exit_planned_x_m": 0.5,
                "cycle1_exit_planned_z_m": -0.2,
                "cycle1_exit_actual_x_m": 0.46,
                "cycle1_exit_actual_z_m": -0.24,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = write_terrain_cycle_quality_report(
        rollout_jsonl_path=rollout_jsonl,
        rollout_summary_path=rollout_summary,
        output_path=output_path,
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
        branch_name="current_planner_baseline",
    )

    assert result["status"] == "present"
    assert result["output_path"] == str(output_path)
    assert result["cycles"][0]["payload_summary"] == {
        "payload_peak_kg": 20.0,
        "effective_deposit_delta_kg": 10.0,
        "deposited_fraction": 0.5,
    }
    assert result["cycles"][0]["execution_quality_summary"]["depth_abs_error_m"] == 0.03
    assert result["cycles"][0]["execution_quality_summary"] == {
        "success": None,
        "entry_error_m": None,
        "entry_planned_x_m": 0.1,
        "entry_planned_z_m": -0.2,
        "entry_actual_x_m": 0.12,
        "entry_actual_z_m": -0.21,
        "exit_error_m": None,
        "exit_abs_overshoot_m": None,
        "exit_signed_error_m": None,
        "exit_planned_x_m": 0.5,
        "exit_planned_z_m": -0.2,
        "exit_actual_x_m": 0.46,
        "exit_actual_z_m": -0.24,
        "depth_target_m": 0.02,
        "depth_peak_m": 0.22,
        "depth_error_m": 0.2,
        "depth_abs_error_m": 0.03,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == result

    second = write_terrain_cycle_quality_report(
        rollout_jsonl_path=rollout_jsonl,
        rollout_summary_path=rollout_summary,
        output_path=output_path,
        grid_shape=[3, 2],
        row_start=0,
        row_end=1,
        col_start=0,
        col_end=1,
        target_depth_m=0.25,
        branch_name="current_planner_baseline",
    )
    assert second["status"] == "output_path_already_exists"
    assert second["validation_errors"] == [
        "output_path must not already exist before writing"
    ]
