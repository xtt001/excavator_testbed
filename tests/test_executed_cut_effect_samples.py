from __future__ import annotations

import numpy as np
import pytest

from testbed.eval.executed_cut_effect_samples import (
    LabelLeakageError,
    StableTerrainWindowConfig,
    build_effect_execution_context,
    build_executed_cut_silver_sample,
    build_executed_cut_silver_samples,
    vectorize_effect_input,
)


def _env_state(n_steps: int = 80) -> np.ndarray:
    env = np.zeros((n_steps, 89), dtype=np.float64)
    env[:, 33:39] = 0.20
    env[:, 39:45] = 0.10
    env[:, 51:57] = 1.0
    env[:, 64:67] = [1.0, 0.0, 2.0]
    env[:, 67:70] = [1.0, 0.0, 0.0]
    env[:, 70:73] = [0.0, 0.0, 1.0]
    env[:, 73:77] = [0.5, 0.4, 0.2, 0.0]
    env[:, 77:83] = 0.0
    env[:, 83:89] = 1.0
    return env


def _executed_cut() -> dict[str, float | bool | str]:
    return {
        "entry_x_m": 0.1,
        "entry_z_m": 0.2,
        "exit_x_m": 0.6,
        "exit_z_m": 0.2,
        "direction_x": 1.0,
        "direction_z": 0.0,
        "length_m": 0.5,
        "actual_surface_penetration_peak_m": 0.12,
        "depth_source": "env_state_surface_penetration",
        "valid": True,
    }


def _qpos(n_steps: int = 80) -> np.ndarray:
    return np.tile(np.asarray([0.1, 0.2, 0.3, 0.4]), (n_steps, 1))


def _qvel(n_steps: int = 80) -> np.ndarray:
    return np.tile(np.asarray([0.01, 0.02, 0.03, 0.04]), (n_steps, 1))


def _previous_outcome(*, valid: bool = False) -> dict[str, object]:
    return {
        "signed_depth_delta_m": [0.0] * 6,
        "payload_gain_kg": 0.0,
        "valid": valid,
    }


def test_stability_defaults_are_the_reviewed_silver_contract() -> None:
    config = StableTerrainWindowConfig()

    assert config.window_steps == 10
    assert config.min_surface_valid_fraction == pytest.approx(8.0 / 9.0)
    assert config.max_removed_depth_range_m == pytest.approx(0.002)
    assert config.post_search_steps == 150


def test_build_sample_uses_stable_pre_and_first_stable_post_window() -> None:
    env = _env_state()
    env[36:46, 39:45] = np.linspace(0.10, 0.13, 10)[:, None]
    env[46:, 39:45] = [0.12, 0.11, 0.10, 0.13, 0.10, 0.10]

    result = build_executed_cut_silver_sample(
        env_state=env,
        qpos=_qpos(),
        qvel=_qvel(),
        episode_id="episode_03",
        cycle_id=7,
        cycle_start_step=0,
        cycle_end_step_exclusive=75,
        operator_entry_step=20,
        operator_exit_step=35,
        executed_cut=_executed_cut(),
        payload_gain_kg=42.0,
        effective_deposit_delta_kg=39.0,
        previous_outcome=_previous_outcome(),
    )

    assert result["status"] == "present"
    record = result["record"]
    assert record["schema"] == "executed_cut_silver_sample_v1"
    assert record["evidence_tier"] == "replay_derived_silver"
    assert record["pre_window"] == {"start_step": 10, "end_step_exclusive": 20}
    assert record["post_window"] == {
        "start_step": 46,
        "end_step_exclusive": 56,
        "dump_start_step": 75,
        "status": "stable_window_ends_before_dump",
    }
    assert record["execution_context"] == {
        "cycle_index": 7,
        "entry_qpos": [0.1, 0.2, 0.3, 0.4],
        "entry_qvel": [0.01, 0.02, 0.03, 0.04],
        "entry_bucket_tip_xyz_m": [0.0, 0.0, 0.0],
        "previous_outcome": _previous_outcome(),
    }
    assert record["outcome"]["signed_depth_delta_m"] == pytest.approx(
        [0.02, 0.01, 0.0, 0.03, 0.0, 0.0]
    )
    assert (
        record["outcome"]["terrain_delta_semantics"]
        == "stable_post_median_minus_stable_pre_median_net"
    )
    assert record["outcome"]["removed_volume_m3"] == pytest.approx(0.012)
    assert record["outcome"]["payload_gain_kg"] == pytest.approx(42.0)
    assert record["capability_labels"]["effective_move"] is None
    assert (
        record["capability_label_status"]["effective_move"]
        == "threshold_not_configured"
    )


def test_build_sample_rejects_unstable_or_low_coverage_windows() -> None:
    env = _env_state(55)
    env[10:20, 83] = 0.5

    result = build_executed_cut_silver_sample(
        env_state=env,
        qpos=_qpos(55),
        qvel=_qvel(55),
        episode_id="episode_03",
        cycle_id=0,
        cycle_start_step=0,
        cycle_end_step_exclusive=55,
        operator_entry_step=20,
        operator_exit_step=30,
        executed_cut=_executed_cut(),
        payload_gain_kg=10.0,
        effective_deposit_delta_kg=8.0,
        previous_outcome=_previous_outcome(),
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "pre_window_not_stable"


def test_post_window_must_finish_before_dump_start() -> None:
    env = _env_state(70)
    env[36:43, 39:45] = np.linspace(0.10, 0.14, 7)[:, None]
    env[43:, 39:45] = 0.12

    result = build_executed_cut_silver_sample(
        env_state=env,
        qpos=_qpos(70),
        qvel=_qvel(70),
        episode_id="episode_03",
        cycle_id=0,
        cycle_start_step=0,
        cycle_end_step_exclusive=65,
        operator_entry_step=20,
        operator_exit_step=35,
        dump_start_step=50,
        executed_cut=_executed_cut(),
        payload_gain_kg=10.0,
        effective_deposit_delta_kg=8.0,
        previous_outcome=_previous_outcome(),
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "post_window_not_stable_before_dump_within_search"


def test_pre_window_may_precede_cycle_start_when_operator_entry_is_the_boundary() -> (
    None
):
    env = _env_state(70)
    env[36:, 39:45] = 0.11

    result = build_executed_cut_silver_sample(
        env_state=env,
        qpos=_qpos(70),
        qvel=_qvel(70),
        episode_id="episode_03",
        cycle_id=1,
        cycle_start_step=20,
        cycle_end_step_exclusive=65,
        operator_entry_step=20,
        operator_exit_step=35,
        executed_cut=_executed_cut(),
        payload_gain_kg=10.0,
        effective_deposit_delta_kg=8.0,
        previous_outcome=_previous_outcome(),
    )

    assert result["status"] == "present"
    assert result["record"]["pre_window"] == {
        "start_step": 10,
        "end_step_exclusive": 20,
    }


def test_batch_builder_checks_eligibility_before_short_operator_arrays() -> None:
    env = _env_state(80)
    env[36:, 39:45] = 0.11
    result = build_executed_cut_silver_samples(
        env_state=env,
        qpos=_qpos(),
        qvel=_qvel(),
        episode_id="episode_03",
        cycle_fields={
            "cycle_id": np.asarray([0, 1]),
            "start_step": np.asarray([0, 60]),
            "end_step": np.asarray([60, 80]),
            "cleaning_effect_calibration_eligible": np.asarray([1, 0]),
            # The trailing ineligible partial cycle intentionally has no operator row.
            "operator_entry_step": np.asarray([20]),
            "operator_exit_step": np.asarray([35]),
            "operator_entry_x_m": np.asarray([0.1]),
            "operator_entry_z_m": np.asarray([0.2]),
            "operator_exit_x_m": np.asarray([0.6]),
            "operator_exit_z_m": np.asarray([0.2]),
            "operator_cut_direction_x": np.asarray([1.0]),
            "operator_cut_direction_z": np.asarray([0.0]),
            "operator_cut_length_m": np.asarray([0.5]),
            "operator_cut_depth_peak_m": np.asarray([0.12]),
            "operator_cut_depth_source": np.asarray(
                ["env_state_surface_penetration"], dtype=object
            ),
            "operator_cut_payload_gain_kg": np.asarray([42.0]),
            "cycle_effective_deposit_delta_kg": np.asarray([39.0]),
            "operator_cut_valid": np.asarray([1]),
        },
    )

    assert result["status"] == "present"
    assert result["eligible_cycle_count"] == 1
    assert result["record_count"] == 1
    assert result["skipped_ineligible_cycle_count"] == 1
    assert result["rejections"] == []


def test_feature_contract_separates_executed_cut_from_planned_cut_leakage() -> None:
    base = {
        "effect_input_schema": "terrain_effect_input_v1",
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
            "cycle_index": 7,
            "entry_qpos": [0.1, 0.2, 0.3, 0.4],
            "entry_qvel": [0.01, 0.02, 0.03, 0.04],
            "entry_bucket_tip_xyz_m": [0.0, 0.0, 0.0],
            "previous_outcome": _previous_outcome(valid=True),
        },
        "dig_outcome_targets": [99.0] * 8,
        "post_terrain": {"removed_depth_m": [9.0] * 6},
    }
    executed = dict(base, executed_cut=_executed_cut())
    values, names = vectorize_effect_input(executed, input_contract="executed_cut")

    assert len(values) == len(names)
    assert "executed_cut.actual_surface_penetration_peak_m" in names
    assert "execution_context.entry_qpos[0]" in names
    assert "execution_context.previous_outcome.signed_depth_delta_m[0]" in names
    assert not any("dig_outcome" in name or "post_terrain" in name for name in names)

    planned = dict(
        base,
        planned_cut={
            "entry_x_m": 0.1,
            "entry_z_m": 0.2,
            "exit_x_m": 0.6,
            "exit_z_m": 0.2,
            "direction_x": 1.0,
            "direction_z": 0.0,
            "length_m": 0.5,
            "planned_penetration_m": 0.08,
            "planned_payload_target_kg": 35.0,
            "actual_surface_penetration_peak_m": 0.12,
            "valid": True,
        },
    )
    with pytest.raises(LabelLeakageError, match="actual_surface_penetration_peak_m"):
        vectorize_effect_input(planned, input_contract="planned_cut")


def test_effect_input_requires_fixed_execution_context() -> None:
    record = {
        "effect_input_schema": "terrain_effect_input_v1",
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
        "executed_cut": _executed_cut(),
    }

    with pytest.raises(ValueError, match="execution_context"):
        vectorize_effect_input(record, input_contract="executed_cut")


def test_public_execution_context_builder_is_shared_by_planned_recorders() -> None:
    context = build_effect_execution_context(
        cycle_index=2,
        entry_qpos=[0.1, 0.2, 0.3, 0.4],
        entry_qvel=[0.01, 0.02, 0.03, 0.04],
        entry_bucket_tip_xyz_m=[1.0, 0.0, 2.0],
        previous_outcome=_previous_outcome(valid=True),
    )

    assert context["cycle_index"] == 2
    assert context["previous_outcome"]["valid"] is True
    with pytest.raises(ValueError, match="entry_qpos"):
        build_effect_execution_context(
            cycle_index=2,
            entry_qpos=[0.1, 0.2, 0.3],
            entry_qvel=[0.01, 0.02, 0.03, 0.04],
            entry_bucket_tip_xyz_m=[1.0, 0.0, 2.0],
            previous_outcome=_previous_outcome(),
        )
