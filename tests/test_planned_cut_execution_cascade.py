from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from testbed.eval.planned_cut_execution_cascade import (
    PlannedExecutionEnsembleConfig,
    build_planned_cut_effect_cascade,
    load_planned_cut_effect_cascade,
    load_planned_execution_ensemble,
    train_planned_execution_ensemble,
)
from testbed.eval.terrain_effect_ensemble import (
    TerrainEffectEnsembleConfig,
    train_terrain_effect_ensemble,
)


def _base(index: int) -> dict:
    return {
        "schema": "planned_cut_cycle_v1",
        "effect_input_schema": "terrain_effect_input_v1",
        "episode_id": f"episode_{index // 2}",
        "reset_group_id": f"reset_{index // 2}",
        "cycle_id": index,
        "pre_terrain": {
            "surface_depth_m": [0.2] * 6,
            "removed_depth_m": [0.01 * index] * 6,
            "valid_mask": [1.0] * 6,
            "surface_valid_fraction": [1.0] * 6,
            "baseline_depth_m": [0.0] * 6,
            "grid_origin_world_m": [1.0, 0.0, 2.0],
            "long_axis_unit_world": [1.0, 0.0, 0.0],
            "short_axis_unit_world": [0.0, 0.0, 1.0],
            "cell_long_size_m": 0.5,
            "cell_short_size_m": 0.4,
            "cell_area_m2": 0.2,
            "reference_plane_local_y_m": 0.0,
        },
        "execution_context": {
            "cycle_index": index,
            "entry_qpos": [0.1, 0.2, 0.3, 0.4],
            "entry_qvel": [0.01, 0.02, 0.03, 0.04],
            "entry_bucket_tip_xyz_m": [0.0, 0.0, 0.0],
            "previous_outcome": {
                "signed_depth_delta_m": [0.001 * index] * 6,
                "payload_gain_kg": float(index),
                "valid": index > 0,
            },
        },
        "planned_cut": {
            "entry_x_m": 0.1 + 0.01 * index,
            "entry_z_m": 0.2,
            "exit_x_m": 0.85,
            "exit_z_m": 0.2,
            "direction_x": 1.0,
            "direction_z": 0.0,
            "length_m": 0.75,
            "planned_penetration_m": 0.10 + 0.01 * index,
            "planned_payload_target_kg": 60.0,
            "valid": True,
        },
        "execution": {
            "actual_entry_x_m": 0.11 + 0.01 * index,
            "actual_entry_z_m": 0.19,
            "actual_exit_x_m": 0.78,
            "actual_exit_z_m": 0.21,
            "actual_direction_x": 0.999,
            "actual_direction_z": 0.02,
            "actual_length_m": 0.67,
            "actual_surface_penetration_peak_m": 0.08 + 0.01 * index,
            "completed_dig": True,
            "completed_full_cycle": True,
        },
        "outcome": {
            "signed_depth_delta_m": [0.005 + 0.001 * index] * 6,
            "payload_gain_kg": 20.0 + index,
        },
        "capability_labels": {"effective_move": True},
    }


def _executed(record: dict) -> dict:
    output = deepcopy(record)
    execution = output["execution"]
    output["schema"] = "executed_cut_silver_sample_v1"
    output["input_contract"] = "executed_cut"
    output["executed_cut"] = {
        "entry_x_m": execution["actual_entry_x_m"],
        "entry_z_m": execution["actual_entry_z_m"],
        "exit_x_m": execution["actual_exit_x_m"],
        "exit_z_m": execution["actual_exit_z_m"],
        "direction_x": execution["actual_direction_x"],
        "direction_z": execution["actual_direction_z"],
        "length_m": execution["actual_length_m"],
        "actual_surface_penetration_peak_m": execution[
            "actual_surface_penetration_peak_m"
        ],
        "valid": True,
    }
    output.pop("planned_cut")
    output.pop("execution")
    return output


def test_planned_to_executed_ensemble_and_released_cascade_are_loadable(
    tmp_path: Path,
) -> None:
    planned = [_base(index) for index in range(8)]
    calibration = train_planned_execution_ensemble(
        train_records=planned[:6],
        eval_records=planned[6:],
        output_dir=tmp_path / "calibration",
        config=PlannedExecutionEnsembleConfig(
            seeds=(0, 1), epochs=1, batch_size=3
        ),
    )
    assert calibration["model_stage"] == "planned_cut_to_executed_cut_distribution"
    calibrator = load_planned_execution_ensemble(
        tmp_path / "calibration/artifact.json"
    )
    executed_prediction = calibrator.predict(planned[6])
    assert len(executed_prediction["member_executed_cuts"]) == 2
    assert "actual_surface_penetration_peak_m" in executed_prediction[
        "executed_cut_mean"
    ]

    executed = [_executed(record) for record in planned]
    train_terrain_effect_ensemble(
        train_records=executed[:6],
        eval_records=executed[6:],
        output_dir=tmp_path / "silver",
        input_contract="executed_cut",
        config=TerrainEffectEnsembleConfig(
            seeds=(0, 1), epochs=1, batch_size=3
        ),
    )
    acceptance = {
        "schema": "planned_cut_calibration_acceptance_v1",
        "status": "pass",
        "two_stage_calibration_gate": {"status": "pass"},
        "direct_planned_residual_gate": {"status": "not_release"},
    }
    cascade = build_planned_cut_effect_cascade(
        planned_execution_artifact_path=tmp_path / "calibration/artifact.json",
        silver_effect_artifact_path=tmp_path / "silver/artifact.json",
        acceptance=acceptance,
        output_dir=tmp_path / "cascade",
    )
    assert cascade["release_status"] == "released"
    assert cascade["model_stage"] == "plan_to_executed_to_silver"

    predictor = load_planned_cut_effect_cascade(
        tmp_path / "cascade/artifact.json"
    )
    prediction = predictor.predict(planned[7])
    assert predictor.input_contract == "planned_cut"
    assert len(prediction["signed_depth_delta_m"]) == 6
    assert prediction["uncertainty"]["status"] == (
        "calibration_and_silver_ensemble_total_variance"
    )
    assert prediction["derived_volume"]["removed_volume_m3"] >= 0.0
