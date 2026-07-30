from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from testbed.eval.terrain_effect_ensemble import (
    DEFAULT_GROUPED_FOLD_COUNT,
    TerrainEffectEnsembleConfig,
    load_planned_cut_effect_ensemble,
    load_terrain_effect_ensemble,
    train_terrain_effect_ensemble,
)


def _record(index: int, *, planned: bool) -> dict:
    cut_key = "planned_cut" if planned else "executed_cut"
    depth_key = (
        "planned_penetration_m" if planned else "actual_surface_penetration_peak_m"
    )
    moved = bool(index % 2)
    record = {
        "schema": "planned_cut_cycle_v1"
        if planned
        else "executed_cut_silver_sample_v1",
        "effect_input_schema": "terrain_effect_input_v1",
        "episode_id": f"episode_{index // 2}",
        "reset_group_id": f"reset_{index // 2}",
        "cycle_id": index,
        "pre_terrain": {
            "surface_depth_m": [0.2 + index * 0.001] * 6,
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
        cut_key: {
            "entry_x_m": 0.1 + index * 0.01,
            "entry_z_m": 0.2,
            "exit_x_m": 0.5,
            "exit_z_m": 0.2,
            "direction_x": 1.0,
            "direction_z": 0.0,
            "length_m": 0.4,
            depth_key: 0.05 + index * 0.01,
            "valid": True,
        },
        "outcome": {
            "signed_depth_delta_m": [0.01 * int(moved)] * 6,
            "payload_gain_kg": 10.0 * int(moved),
        },
        "capability_labels": {
            "effective_move": moved,
            "low_payload": not moved,
        },
    }
    if planned:
        record["planned_cut"]["planned_payload_target_kg"] = 35.0
        record["execution"] = {
            # It is a recorded response, but must never become a planned input feature.
            "actual_surface_penetration_peak_m": 0.3 + index,
        }
    return record


def test_default_config_is_five_seed_two_by_sixty_four_ensemble() -> None:
    config = TerrainEffectEnsembleConfig()

    assert config.schema == "terrain_effect_ensemble_config_v1"
    assert config.hidden_dims == (64, 64)
    assert config.seeds == (0, 1, 2, 3, 4)
    assert config.regression_loss == "huber"
    assert config.grouped_cv_folds == 6
    assert DEFAULT_GROUPED_FOLD_COUNT == 6


def test_tiny_planned_cut_training_writes_a_leakage_safe_ensemble_artifact(
    tmp_path: Path,
) -> None:
    records = [_record(index, planned=True) for index in range(6)]
    config = TerrainEffectEnsembleConfig(
        hidden_dims=(64, 64),
        seeds=(3, 5),
        epochs=2,
        batch_size=3,
        device="cpu",
    )

    artifact = train_terrain_effect_ensemble(
        train_records=records[:4],
        eval_records=records[4:],
        output_dir=tmp_path / "effect_model",
        input_contract="planned_cut",
        config=config,
    )

    assert artifact["schema"] == "terrain_effect_ensemble_artifact_v1"
    assert artifact["status"] == "present"
    assert artifact["input_contract"] == "planned_cut"
    assert artifact["model_stage"] == "direct_planned_cut_to_outcome_ablation"
    assert artifact["two_stage_calibration_status"] == "not_implemented"
    assert artifact["model"]["hidden_dims"] == [64, 64]
    assert artifact["training_objective"]["regression_loss"] == "huber"
    assert artifact["member_count"] == 2
    assert len(artifact["members"]) == 2
    assert all(Path(row["checkpoint_path"]).is_file() for row in artifact["members"])
    assert (tmp_path / "effect_model" / "artifact.json").is_file()
    assert not any("actual" in name for name in artifact["feature_names"])
    assert "planned_cut.planned_payload_target_kg" in artifact["feature_names"]
    assert artifact["capability_metrics"] == {}
    assert artifact["capability_training_status"] == "rule_only_due_to_class_imbalance"
    assert artifact["excluded_capability_labels"]["effective_move"] == (
        "insufficient_20_each_or_3_reset_groups_per_class"
    )

    predictor = load_terrain_effect_ensemble(
        tmp_path / "effect_model" / "artifact.json"
    )
    prediction = predictor.predict(records[4])
    assert prediction["schema"] == "terrain_effect_ensemble_prediction_v1"
    assert len(prediction["signed_depth_delta_m"]) == 6
    assert len(prediction["uncertainty"]["signed_depth_delta_std_m"]) == 6
    assert prediction["uncertainty"]["member_count"] == 2
    assert prediction["derived_volume"]["cell_area_m2"] == 0.2
    assert "removed_volume_m3_std" in prediction["uncertainty"]
    assert "payload_gain_kg_std" in prediction["uncertainty"]
    with pytest.raises(ValueError, match="not released"):
        load_planned_cut_effect_ensemble(tmp_path / "effect_model" / "artifact.json")


def test_executed_and_planned_contracts_produce_distinct_feature_schemas(
    tmp_path: Path,
) -> None:
    executed_records = [_record(index, planned=False) for index in range(4)]
    config = TerrainEffectEnsembleConfig(seeds=(0,), epochs=1, batch_size=2)

    artifact = train_terrain_effect_ensemble(
        train_records=executed_records[:2],
        eval_records=deepcopy(executed_records[2:]),
        output_dir=tmp_path / "executed",
        input_contract="executed_cut",
        config=config,
    )

    assert "executed_cut.actual_surface_penetration_peak_m" in artifact["feature_names"]
    assert artifact["training_evidence"] == "replay_derived_silver"
    assert artifact["model_stage"] == "stage1_executed_cut_to_outcome"


def test_missing_explicit_effective_move_threshold_does_not_invent_a_classifier(
    tmp_path: Path,
) -> None:
    records = [_record(index, planned=False) for index in range(4)]
    for record in records:
        record["capability_labels"] = {"effective_move": None}
    config = TerrainEffectEnsembleConfig(seeds=(0,), epochs=1, batch_size=2)

    artifact = train_terrain_effect_ensemble(
        train_records=records[:2],
        eval_records=records[2:],
        output_dir=tmp_path / "regression_only",
        input_contract="executed_cut",
        config=config,
    )

    assert artifact["capability_target_names"] == []
    assert artifact["capability_training_status"] == "rule_only_due_to_class_imbalance"


def test_single_class_capability_labels_are_excluded_from_classifier(
    tmp_path: Path,
) -> None:
    records = [_record(index, planned=False) for index in range(4)]
    for record in records:
        record["capability_labels"] = {"effective_move": True}
    config = TerrainEffectEnsembleConfig(seeds=(0,), epochs=1, batch_size=2)

    artifact = train_terrain_effect_ensemble(
        train_records=records[:2],
        eval_records=records[2:],
        output_dir=tmp_path / "single_class",
        input_contract="executed_cut",
        config=config,
    )

    assert artifact["capability_target_names"] == []
    assert artifact["capability_training_status"] == "rule_only_due_to_class_imbalance"
    assert artifact["excluded_capability_labels"] == {
        "effective_move": "single_class_in_training_split"
    }
