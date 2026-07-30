from __future__ import annotations

from copy import deepcopy
from random import Random

from testbed.eval.planned_cut_calibration import (
    assign_episode_grouped_folds,
    build_planned_cut_calibration_dataset,
    build_planned_cut_cycle_record,
    validate_planned_cut_cycle,
)


def _negative_cycle(episode_id: str = "episode_a", cycle_id: int = 0) -> dict:
    return {
        "schema": "planned_cut_cycle_v1",
        "effect_input_schema": "terrain_effect_input_v1",
        "episode_id": episode_id,
        "reset_group_id": f"reset_{episode_id}",
        "cycle_id": cycle_id,
        "provenance": {
            "source": "controlled_frozen_act_rollout",
            "act_checkpoint_sha256": "abc123",
        },
        "pre_terrain": {
            "surface_depth_m": [0.2] * 6,
            "removed_depth_m": [0.1] * 6,
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
            "cycle_index": cycle_id,
            "entry_qpos": [0.1, 0.2, 0.3, 0.4],
            "entry_qvel": [0.01, 0.02, 0.03, 0.04],
            "entry_bucket_tip_xyz_m": [0.0, 0.0, 0.0],
            "previous_outcome": {
                "signed_depth_delta_m": [0.0] * 6,
                "payload_gain_kg": 0.0,
                "valid": False,
            },
        },
        "planned_cut": {
            "entry_x_m": 0.1,
            "entry_z_m": 0.2,
            "exit_x_m": 0.5,
            "exit_z_m": 0.2,
            "direction_x": 1.0,
            "direction_z": 0.0,
            "length_m": 0.4,
            "planned_penetration_m": 0.08,
            "planned_payload_target_kg": 35.0,
            "valid": True,
        },
        "execution": {
            "actual_surface_penetration_peak_m": 0.01,
            "completed_dig": False,
            "completed_full_cycle": False,
        },
        "outcome": {
            "status": "stable_post_terrain_present",
            "signed_depth_delta_m": [0.0] * 6,
            "payload_gain_kg": 0.0,
            "removed_volume_m3": 0.0,
        },
        "capability_labels": {
            "effective_move": False,
            "low_payload": True,
            "stuck_no_motion": True,
            "timeout": False,
            "wall_contact": False,
            "bottom_contact": True,
            "recovery_required": True,
            "completed_dig": False,
            "completed_full_cycle": False,
        },
    }


def test_negative_planned_cut_cycle_is_valid_and_preserved_for_capability() -> None:
    record = _negative_cycle()

    validated = validate_planned_cut_cycle(record)
    dataset = build_planned_cut_calibration_dataset([record])

    assert validated["status"] == "valid"
    assert validated["record"]["execution"]["actual_surface_penetration_peak_m"] == 0.01
    assert dataset["status"] == "present"
    assert dataset["input_contract"] == "planned_cut"
    assert dataset["capability_record_count"] == 1
    assert dataset["capability_records"][0]["capability_labels"]["stuck_no_motion"]
    assert dataset["negative_label_counts"]["stuck_no_motion"] == 1


def test_planned_record_builder_uses_the_same_fixed_effect_input_contract() -> None:
    source = _negative_cycle("episode_builder", 3)

    built = build_planned_cut_cycle_record(
        episode_id=source["episode_id"],
        reset_group_id=source["reset_group_id"],
        cycle_id=source["cycle_id"],
        provenance=source["provenance"],
        pre_terrain=source["pre_terrain"],
        execution_context=source["execution_context"],
        planned_cut=source["planned_cut"],
        execution=source["execution"],
        outcome=source["outcome"],
        capability_labels=source["capability_labels"],
    )

    assert built["status"] == "valid"
    assert built["record"]["effect_input_schema"] == "terrain_effect_input_v1"

    mismatched = deepcopy(source)
    mismatched["execution_context"]["cycle_index"] = 99
    invalid = validate_planned_cut_cycle(mismatched)
    assert invalid["status"] == "invalid"
    assert any(
        "cycle_index must equal cycle_id" in error
        for error in invalid["validation_errors"]
    )


def test_actual_depth_is_forbidden_in_planned_input_but_allowed_as_execution_result() -> (
    None
):
    bad = _negative_cycle()
    bad["planned_cut"]["actual_peak_depth_m"] = 0.2

    result = validate_planned_cut_cycle(bad)

    assert result["status"] == "invalid"
    assert any(
        "planned_cut.actual_peak_depth_m" in item
        for item in result["validation_errors"]
    )


def test_episode_grouped_fold_assignment_is_deterministic_and_order_independent() -> (
    None
):
    records = [
        _negative_cycle("episode_a", 0),
        _negative_cycle("episode_b", 0),
        _negative_cycle("episode_a", 1),
        _negative_cycle("episode_c", 0),
        _negative_cycle("episode_d", 0),
    ]
    shuffled = deepcopy(records)
    Random(42).shuffle(shuffled)

    first = assign_episode_grouped_folds(records, fold_count=3, salt="effect-v1")
    second = assign_episode_grouped_folds(shuffled, fold_count=3, salt="effect-v1")

    assert first == second
    assert set(first) == {"episode_a", "episode_b", "episode_c", "episode_d"}
    assert 0 <= first["episode_a"] < 3
