from __future__ import annotations

import json

from testbed.eval.terrain_residual_execution_diagnostic import (
    build_official_v0_failure_packet,
    build_terrain_residual_execution_diagnostic,
    write_official_v0_failure_packet,
    write_terrain_residual_execution_diagnostic,
)


def _runtime_source() -> dict[str, object]:
    return {
        "schema": "residual_cut_intent_runtime_source_v1",
        "source": "explicit_residual_cut_intent_runtime_source",
        "status": "present",
        "plans": [
            {
                "cycle_index": 0,
                "cut_intent_candidate_id": "cut_candidate_000001",
                "plan": {
                    "status": "present",
                    "candidate_id": "cut_candidate_000001",
                    "dig_cut_token_contract": {"depth_scale_m": 0.8},
                    "dig_cut_tokens": [
                        0.0,
                        0.0,
                        0.25,
                        0.0,
                        1.0,
                        0.0,
                        0.25,
                        0.025,
                        0.2,
                        1.0,
                    ],
                    "raw_fields": {
                        "operator_entry_x_m": 0.0,
                        "operator_entry_z_m": 0.0,
                        "operator_exit_x_m": 0.5,
                        "operator_exit_z_m": 0.0,
                        "operator_cut_length_m": 0.5,
                        "operator_cut_depth_peak_m": 0.02,
                        "operator_cut_payload_gain_kg": 12.5,
                        "operator_effective_deposit_delta_kg": 12.5,
                    },
                },
            }
        ],
    }


def _rollout_summary() -> dict[str, object]:
    return {
        "target_cycle_gate_success": 1,
        "target_cycle_completed_dump_count": 2,
        "transition_timeout_count": 0,
        "cycle1_depth_target_m": 0.02,
        "cycle1_depth_peak_m": 0.26,
        "cycle1_depth_abs_error_m": 0.24,
        "cycle1_entry_actual_x_m": 0.12,
        "cycle1_entry_actual_z_m": -0.09,
        "cycle1_exit_actual_x_m": 0.42,
        "cycle1_exit_actual_z_m": -0.08,
        "cycle1_bucket_mass_out_kg": 29.0,
        "cycle1_target_deposit_final_delta_kg": 20.0,
        "cycle1_deposited_fraction": 0.69,
        "cycle1_success": 0,
        "dig_depth_abs_error_mean_m": 0.24,
        "cycle_deposited_fraction_mean": 0.69,
    }


def _rollout_records() -> list[dict[str, object]]:
    return [
        {
            "primitive_cycle_index": 0,
            "skill_name": "dump",
            "dump_end_mask": 1,
            "return_target_token_source": "conditioned_return_explicit_residual_cut_intent_dig_cut_token",
            "return_start_envelope_token_source": "qc6_return_start_envelope_cell_1+relocate_spatial_linear+relocate_qpos_linear",
            "return_to_dig_entry_error_m": 0.21,
            "return_to_dig_start_envelope_ready": True,
            "return_to_dig_start_envelope_error": 0.0,
            "return_to_dig_start_envelope_checks": {
                "local_depth_m": {"ok": True},
                "dig_contact": {"ok": True},
            },
        }
    ]


def test_execution_diagnostic_aligns_intent_execution_and_dump_exit() -> None:
    result = build_terrain_residual_execution_diagnostic(
        runtime_source=_runtime_source(),
        rollout_summary=_rollout_summary(),
        rollout_records=_rollout_records(),
        target_id="t1_large_shallow_rectangular_pit_default",
        branch_name="heuristic_residual_pipeline",
    )

    assert result["schema"] == "terrain_residual_execution_diagnostic_v1"
    assert result["source"] == "residual_cut_intent_execution_quality_diagnostic"
    assert result["status"] == "present"
    assert result["root_cause_hypothesis"] == {
        "status": "present",
        "primary_category": "act_depth_execution_quality_or_dump_exit_state",
        "planner_behavior_change_status": "not_made",
        "evidence_summary": "gate reached with zero transition timeouts, but depth peak exceeds intent on completed cycles",
    }
    assert result["non_goal_statuses"] == {
        "planner_behavior_change_status": "not_made",
        "checked_in_default_config_change": "not_made",
        "production_readiness_status": "not_claimed",
        "calibrated_branch_status": "blocked_pending_gold_replay_samples",
    }
    assert result["summary"] == {
        "cycle_count": 1,
        "depth_overshoot_cycle_count": 1,
        "mean_depth_peak_minus_intent_m": 0.24,
        "mean_deposited_fraction": 0.69,
        "target_cycle_gate_success": 1,
        "target_cycle_completed_dump_count": 2,
        "transition_timeout_count": 0,
    }
    assert result["cycles"] == [
        {
            "cycle_index": 0,
            "candidate_id": "cut_candidate_000001",
            "intent_summary": {
                "entry_x_m": 0.0,
                "entry_z_m": 0.0,
                "exit_x_m": 0.5,
                "exit_z_m": 0.0,
                "cut_length_m": 0.5,
                "cut_depth_peak_m": 0.02,
                "token_cut_depth_peak_m": 0.02,
                "cut_payload_gain_kg": 12.5,
                "effective_deposit_delta_kg": 12.5,
            },
            "execution_summary": {
                "depth_target_m": 0.02,
                "depth_peak_m": 0.26,
                "depth_abs_error_m": 0.24,
                "depth_peak_minus_intent_m": 0.24,
                "depth_peak_to_intent_ratio": 13.0,
                "entry_actual_x_m": 0.12,
                "entry_actual_z_m": -0.09,
                "entry_actual_error_vs_intent_m": 0.15,
                "exit_actual_x_m": 0.42,
                "exit_actual_z_m": -0.08,
                "exit_actual_error_vs_intent_m": 0.11313708499,
                "payload_mass_kg": 29.0,
                "effective_deposit_mass_kg": 20.0,
                "deposited_fraction": 0.69,
                "success": 0,
            },
            "dump_exit_summary": {
                "dump_end_row_index": 0,
                "return_target_token_source": "conditioned_return_explicit_residual_cut_intent_dig_cut_token",
                "return_start_envelope_token_source": "qc6_return_start_envelope_cell_1+relocate_spatial_linear+relocate_qpos_linear",
                "return_to_dig_entry_error_m": 0.21,
                "return_to_dig_start_envelope_ready": True,
                "return_to_dig_start_envelope_error": 0.0,
                "failed_envelope_check_names": [],
            },
            "diagnosis_flags": {
                "depth_peak_exceeds_intent": True,
                "return_handoff_reachable": True,
            },
        }
    ]


def test_execution_diagnostic_writer_reads_inputs_and_rejects_overwrite(tmp_path) -> None:
    runtime_source_path = tmp_path / "residual_cut_intent_runtime_source.json"
    rollout_summary_path = tmp_path / "rollout_000_summary.json"
    rollout_jsonl_path = tmp_path / "rollout_000.jsonl"
    output_path = tmp_path / "diagnostic.json"
    runtime_source_path.write_text(json.dumps(_runtime_source()), encoding="utf-8")
    rollout_summary_path.write_text(json.dumps(_rollout_summary()), encoding="utf-8")
    rollout_jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _rollout_records()),
        encoding="utf-8",
    )

    result = write_terrain_residual_execution_diagnostic(
        runtime_source_path=runtime_source_path,
        rollout_summary_path=rollout_summary_path,
        rollout_jsonl_path=rollout_jsonl_path,
        output_path=output_path,
        target_id="t1_large_shallow_rectangular_pit_default",
        branch_name="heuristic_residual_pipeline",
    )
    second = write_terrain_residual_execution_diagnostic(
        runtime_source_path=runtime_source_path,
        rollout_summary_path=rollout_summary_path,
        rollout_jsonl_path=rollout_jsonl_path,
        output_path=output_path,
        target_id="t1_large_shallow_rectangular_pit_default",
        branch_name="heuristic_residual_pipeline",
    )

    assert result["status"] == "present"
    assert result["input_paths"] == {
        "runtime_source_path": str(runtime_source_path),
        "rollout_summary_path": str(rollout_summary_path),
        "rollout_jsonl_path": str(rollout_jsonl_path),
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == result
    assert second["status"] == "output_path_already_exists"


def test_execution_diagnostic_skips_source_plans_without_execution_evidence() -> None:
    runtime_source = _runtime_source()
    runtime_source["plans"].append(
        {
            "cycle_index": 1,
            "cut_intent_candidate_id": "cut_candidate_000001",
            "plan": _runtime_source()["plans"][0]["plan"],
        }
    )

    result = build_terrain_residual_execution_diagnostic(
        runtime_source=runtime_source,
        rollout_summary=_rollout_summary(),
        rollout_records=_rollout_records(),
        target_id="t1_large_shallow_rectangular_pit_default",
        branch_name="heuristic_residual_pipeline",
    )

    assert result["summary"]["cycle_count"] == 1
    assert [cycle["cycle_index"] for cycle in result["cycles"]] == [0]


def _official_v0_comparison() -> dict[str, object]:
    return {
        "schema": "official_v0_comparison_v1",
        "status": "present",
        "targets": {
            "t1_large_shallow_rectangular_pit_default": {
                "target_id": "t1_large_shallow_rectangular_pit_default",
                "branches": {
                    "A": {
                        "official_pass_fail": {
                            "status": "present",
                            "pass": True,
                            "failed_checks": [],
                        },
                        "cycle_quality_report_path": "runs/t1/a_cycle_quality.json",
                    },
                    "B": {
                        "official_pass_fail": {
                            "status": "present",
                            "pass": False,
                            "failed_checks": [
                                "deposited_fraction_below_baseline",
                                "depth_abs_error_above_baseline",
                            ],
                        },
                        "cycle_quality_report_path": "runs/t1/b_cycle_quality.json",
                        "runtime_source_path": "runs/t1/b_runtime_source.json",
                    },
                },
            },
            "t2_offset_rectangular_pit_default": {
                "target_id": "t2_offset_rectangular_pit_default",
                "branches": {
                    "A": {
                        "official_pass_fail": {
                            "status": "present",
                            "pass": True,
                            "failed_checks": [],
                        },
                        "cycle_quality_report_path": "runs/t2/a_cycle_quality.json",
                    },
                    "B": {
                        "official_pass_fail": {
                            "status": "present",
                            "pass": False,
                            "failed_checks": ["depth_abs_error_above_baseline"],
                        },
                        "cycle_quality_report_path": "runs/t2/b_cycle_quality.json",
                        "runtime_source_path": "runs/t2/b_runtime_source.json",
                    },
                },
            },
        },
    }


def _depth_execution_diagnostic_index() -> dict[str, object]:
    return {
        "status": "present",
        "targets": {
            "t1_large_shallow_rectangular_pit_default": {
                "status": "present",
                "summary": {
                    "cycle_count": 1,
                    "depth_overshoot_cycle_count": 1,
                    "mean_depth_peak_minus_intent_m": 0.24,
                    "mean_deposited_fraction": 0.69,
                    "target_cycle_gate_success": 1,
                    "transition_timeout_count": 0,
                },
                "root_cause_hypothesis": {
                    "status": "present",
                    "primary_category": "act_depth_execution_quality_or_dump_exit_state",
                },
            },
            "t2_offset_rectangular_pit_default": {
                "status": "present",
                "summary": {
                    "cycle_count": 1,
                    "depth_overshoot_cycle_count": 1,
                    "mean_depth_peak_minus_intent_m": 0.19,
                    "mean_deposited_fraction": 0.62,
                    "target_cycle_gate_success": 1,
                    "transition_timeout_count": 0,
                },
                "root_cause_hypothesis": {
                    "status": "present",
                    "primary_category": "act_depth_execution_quality_or_dump_exit_state",
                },
            },
        },
    }


def test_official_v0_failure_packet_summarizes_t1_t2_b_failures() -> None:
    result = build_official_v0_failure_packet(
        official_v0_comparison=_official_v0_comparison(),
        depth_execution_diagnostic_index=_depth_execution_diagnostic_index(),
    )

    assert result["schema"] == "terrain_residual_official_v0_failure_packet_v1"
    assert result["source"] == "request_local_official_v0_failure_packet_builder"
    assert result["status"] == "present"
    assert result["target_count"] == 2
    assert result["conclusion"] == {
        "status": "b_not_promoted",
        "primary_blocker": "act_depth_execution_quality_or_dump_exit_state",
        "official_v0_b_pass_status": "failed",
    }
    assert result["non_goal_statuses"] == {
        "planner_behavior_change_status": "not_made",
        "checked_in_default_config_change": "not_made",
        "production_readiness_status": "not_claimed",
        "calibrated_branch_status": "blocked_pending_gold_replay_samples",
    }
    assert result["targets"] == [
        {
            "target_id": "t1_large_shallow_rectangular_pit_default",
            "official_b_pass": False,
            "official_b_failed_checks": [
                "deposited_fraction_below_baseline",
                "depth_abs_error_above_baseline",
            ],
            "depth_execution_status": "present",
            "depth_overshoot_cycle_count": 1,
            "mean_depth_peak_minus_intent_m": 0.24,
            "mean_deposited_fraction": 0.69,
            "target_cycle_gate_success": 1,
            "transition_timeout_count": 0,
            "root_cause_primary_category": "act_depth_execution_quality_or_dump_exit_state",
            "artifact_refs": {
                "a_cycle_quality_report_path": "runs/t1/a_cycle_quality.json",
                "b_cycle_quality_report_path": "runs/t1/b_cycle_quality.json",
                "b_runtime_source_path": "runs/t1/b_runtime_source.json",
            },
        },
        {
            "target_id": "t2_offset_rectangular_pit_default",
            "official_b_pass": False,
            "official_b_failed_checks": ["depth_abs_error_above_baseline"],
            "depth_execution_status": "present",
            "depth_overshoot_cycle_count": 1,
            "mean_depth_peak_minus_intent_m": 0.19,
            "mean_deposited_fraction": 0.62,
            "target_cycle_gate_success": 1,
            "transition_timeout_count": 0,
            "root_cause_primary_category": "act_depth_execution_quality_or_dump_exit_state",
            "artifact_refs": {
                "a_cycle_quality_report_path": "runs/t2/a_cycle_quality.json",
                "b_cycle_quality_report_path": "runs/t2/b_cycle_quality.json",
                "b_runtime_source_path": "runs/t2/b_runtime_source.json",
            },
        },
    ]


def test_official_v0_failure_packet_writer_reads_inputs_and_rejects_overwrite(
    tmp_path,
) -> None:
    comparison_path = tmp_path / "official_v0_comparison.json"
    diagnostic_index_path = tmp_path / "depth_execution_diagnostics.json"
    output_path = tmp_path / "official_v0_failure_packet.json"
    comparison_path.write_text(json.dumps(_official_v0_comparison()), encoding="utf-8")
    diagnostic_index_path.write_text(
        json.dumps(_depth_execution_diagnostic_index()),
        encoding="utf-8",
    )

    result = write_official_v0_failure_packet(
        official_v0_comparison_path=comparison_path,
        depth_execution_diagnostic_index_path=diagnostic_index_path,
        output_path=output_path,
    )
    second = write_official_v0_failure_packet(
        official_v0_comparison_path=comparison_path,
        depth_execution_diagnostic_index_path=diagnostic_index_path,
        output_path=output_path,
    )

    assert result["status"] == "present"
    assert result["input_paths"] == {
        "official_v0_comparison_path": str(comparison_path),
        "depth_execution_diagnostic_index_path": str(diagnostic_index_path),
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == result
    assert second["status"] == "output_path_already_exists"
