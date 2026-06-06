from __future__ import annotations

import json

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import DIG_CUT_TOKEN_DIM
from testbed.planner.dig_coverage import CoverageService
from testbed.planner.primitive_config import (
    align_vector,
    build_conditioning_config,
    build_dig_lifecycle_config,
    build_pre_dig_alignment_config,
    build_return_to_dig_config,
    load_dig_cut_prior,
    normalize_failed_dig_replan_skill,
    normalize_goal_sequence,
    normalize_plane_depth_mode,
    optional_align_vector,
    optional_float,
    validate_dig_cut_planner_config,
)


def test_normalize_plane_depth_mode_aliases_and_errors() -> None:
    assert normalize_plane_depth_mode(None) == "range"
    assert normalize_plane_depth_mode("legacy") == "range"
    assert normalize_plane_depth_mode("p05-p95") == "range"
    assert normalize_plane_depth_mode("median_floor") == "p50_floor"
    assert normalize_plane_depth_mode("target-floor") == "p50_floor"
    assert normalize_plane_depth_mode("median_band") == "target_band"

    with pytest.raises(
        ValueError,
        match="return_to_dig_start_envelope_plane_depth_mode must be one of",
    ):
        normalize_plane_depth_mode("unknown")


def test_normalize_failed_dig_replan_skill_aliases_and_errors() -> None:
    assert normalize_failed_dig_replan_skill(None) == "dig"
    assert normalize_failed_dig_replan_skill("same-dig") == "dig"
    assert normalize_failed_dig_replan_skill("new_dig") == "dig"
    assert normalize_failed_dig_replan_skill("fail_fast") == "stop"
    assert normalize_failed_dig_replan_skill("terminal-stop") == "stop"

    with pytest.raises(
        ValueError,
        match="dig_failed_replan_next_skill must be 'dig' or 'stop'",
    ):
        normalize_failed_dig_replan_skill("carry")


def test_optional_and_align_vector_helpers_match_planner_facade_semantics() -> None:
    np.testing.assert_allclose(
        align_vector(None, default=[1.0, 2.0, 3.0, 4.0], action_dim=4),
        np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        align_vector([0.0, 0.1, 0.2, 0.3], default=[1.0, 2.0, 3.0, 4.0], action_dim=4),
        np.asarray([0.0, 0.1, 0.2, 0.3], dtype=np.float32),
    )
    assert optional_align_vector(None, action_dim=4) is None
    assert optional_align_vector("none", action_dim=4) is None
    np.testing.assert_allclose(
        optional_align_vector("0, 1, 2, 3", action_dim=4),
        np.asarray([0.0, 1.0, 2.0, 3.0], dtype=np.float32),
    )
    assert optional_float(None) is None
    assert optional_float("null") is None
    assert optional_float("1.25") == pytest.approx(1.25)


def test_build_dig_lifecycle_config_preserves_legacy_defaults() -> None:
    config = build_dig_lifecycle_config(
        dig_to_carry_min_bucket_mass_kg=300.0,
        dig_to_carry_min_distance_to_dig_area_m=0.0,
        dig_to_carry_target_bucket_mass_kg=None,
        dig_to_carry_mass_plateau_enabled=False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=20.0,
        dig_to_carry_mass_plateau_epsilon_kg=1.0,
        dig_to_carry_mass_plateau_hold_steps=25,
        dig_to_carry_mass_plateau_min_steps=80,
        dig_bad_replan_enabled=False,
        dig_bad_replan_max_steps=180,
        dig_bad_replan_min_bucket_mass_kg=15.0,
        dig_exit_guard_enabled=False,
        dig_exit_guard_min_steps=80,
        dig_exit_guard_overshoot_m=0.65,
        dig_exit_guard_min_bucket_mass_kg=20.0,
        dig_failed_replan_next_skill="dig",
    )

    assert config.dig_to_carry_min_bucket_mass_kg == pytest.approx(300.0)
    assert config.dig_to_carry_min_distance_to_dig_area_m == pytest.approx(0.0)
    assert config.dig_to_carry_target_bucket_mass_kg == pytest.approx(300.0)
    assert config.dig_to_carry_mass_plateau_enabled is False
    assert config.dig_to_carry_mass_plateau_min_bucket_mass_kg == pytest.approx(20.0)
    assert config.dig_to_carry_mass_plateau_epsilon_kg == pytest.approx(1.0)
    assert config.dig_to_carry_mass_plateau_hold_steps == 25
    assert config.dig_to_carry_mass_plateau_min_steps == 80
    assert config.dig_bad_replan_enabled is False
    assert config.dig_bad_replan_max_steps == 180
    assert config.dig_bad_replan_min_bucket_mass_kg == pytest.approx(15.0)
    assert config.dig_exit_guard_enabled is False
    assert config.dig_exit_guard_min_steps == 80
    assert config.dig_exit_guard_overshoot_m == pytest.approx(0.65)
    assert config.dig_exit_guard_min_bucket_mass_kg == pytest.approx(20.0)
    assert config.dig_failed_replan_next_skill == "dig"


def test_build_dig_lifecycle_config_preserves_overrides_and_aliases() -> None:
    config = build_dig_lifecycle_config(
        dig_to_carry_min_bucket_mass_kg=15,
        dig_to_carry_min_distance_to_dig_area_m=0.25,
        dig_to_carry_target_bucket_mass_kg=45,
        dig_to_carry_mass_plateau_enabled=True,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=25,
        dig_to_carry_mass_plateau_epsilon_kg=0.5,
        dig_to_carry_mass_plateau_hold_steps=0,
        dig_to_carry_mass_plateau_min_steps=0,
        dig_bad_replan_enabled=True,
        dig_bad_replan_max_steps=0,
        dig_bad_replan_min_bucket_mass_kg=5,
        dig_exit_guard_enabled=True,
        dig_exit_guard_min_steps=0,
        dig_exit_guard_overshoot_m=0.2,
        dig_exit_guard_min_bucket_mass_kg=7,
        dig_failed_replan_next_skill="terminal-stop",
    )

    assert config.dig_to_carry_min_bucket_mass_kg == pytest.approx(15.0)
    assert config.dig_to_carry_min_distance_to_dig_area_m == pytest.approx(0.25)
    assert config.dig_to_carry_target_bucket_mass_kg == pytest.approx(45.0)
    assert config.dig_to_carry_mass_plateau_enabled is True
    assert config.dig_to_carry_mass_plateau_min_bucket_mass_kg == pytest.approx(25.0)
    assert config.dig_to_carry_mass_plateau_epsilon_kg == pytest.approx(0.5)
    assert config.dig_to_carry_mass_plateau_hold_steps == 1
    assert config.dig_to_carry_mass_plateau_min_steps == 1
    assert config.dig_bad_replan_enabled is True
    assert config.dig_bad_replan_max_steps == 1
    assert config.dig_bad_replan_min_bucket_mass_kg == pytest.approx(5.0)
    assert config.dig_exit_guard_enabled is True
    assert config.dig_exit_guard_min_steps == 1
    assert config.dig_exit_guard_overshoot_m == pytest.approx(0.2)
    assert config.dig_exit_guard_min_bucket_mass_kg == pytest.approx(7.0)
    assert config.dig_failed_replan_next_skill == "stop"


def test_build_return_to_dig_config_preserves_legacy_defaults() -> None:
    config = build_return_to_dig_config(
        return_to_dig_shallow_guard_enabled=False,
        return_to_dig_max_bucket_mass_kg=15.0,
        return_to_dig_touch_tolerance_m=0.05,
        return_to_dig_min_depth_m=0.02,
        return_to_dig_max_depth_m=0.12,
        return_to_dig_max_entry_error_m=None,
        return_to_dig_start_envelope_gate_enabled=False,
        return_to_dig_start_envelope_spatial_tolerance=0.10,
        return_to_dig_start_envelope_depth_tolerance_m=0.08,
        return_to_dig_start_envelope_local_depth_tolerance_m=0.005,
        return_to_dig_start_envelope_plane_depth_tolerance_m=0.05,
        return_to_dig_start_envelope_plane_depth_mode="range",
        return_to_dig_start_envelope_qpos_tolerance=0.04,
        return_to_dig_start_envelope_require_contact=True,
        return_to_dig_start_envelope_direct_handoff_enabled=False,
        return_max_steps=420,
    )

    assert config.return_to_dig_shallow_guard_enabled is False
    assert config.return_to_dig_max_bucket_mass_kg == pytest.approx(15.0)
    assert config.return_to_dig_touch_tolerance_m == pytest.approx(0.05)
    assert config.return_to_dig_min_depth_m == pytest.approx(0.02)
    assert config.return_to_dig_max_depth_m == pytest.approx(0.12)
    assert config.return_to_dig_max_entry_error_m is None
    assert config.return_to_dig_start_envelope_gate_enabled is False
    assert config.return_to_dig_start_envelope_spatial_tolerance == pytest.approx(0.10)
    assert config.return_to_dig_start_envelope_depth_tolerance_m == pytest.approx(0.08)
    assert config.return_to_dig_start_envelope_local_depth_tolerance_m == pytest.approx(
        0.005
    )
    assert config.return_to_dig_start_envelope_plane_depth_tolerance_m == pytest.approx(
        0.05
    )
    assert config.return_to_dig_start_envelope_plane_depth_mode == "range"
    assert config.return_to_dig_start_envelope_qpos_tolerance == pytest.approx(0.04)
    assert config.return_to_dig_start_envelope_require_contact is True
    assert config.return_to_dig_start_envelope_direct_handoff_enabled is False
    assert config.return_max_steps == 420


def test_build_return_to_dig_config_preserves_overrides_and_aliases() -> None:
    config = build_return_to_dig_config(
        return_to_dig_shallow_guard_enabled=True,
        return_to_dig_max_bucket_mass_kg=2,
        return_to_dig_touch_tolerance_m=0.15,
        return_to_dig_min_depth_m=0.03,
        return_to_dig_max_depth_m=0.18,
        return_to_dig_max_entry_error_m="0.55",
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_start_envelope_spatial_tolerance=0.20,
        return_to_dig_start_envelope_depth_tolerance_m=0.07,
        return_to_dig_start_envelope_local_depth_tolerance_m=0.006,
        return_to_dig_start_envelope_plane_depth_tolerance_m=0.025,
        return_to_dig_start_envelope_plane_depth_mode="median-floor",
        return_to_dig_start_envelope_qpos_tolerance=0.08,
        return_to_dig_start_envelope_require_contact=False,
        return_to_dig_start_envelope_direct_handoff_enabled=True,
        return_max_steps=12,
    )

    assert config.return_to_dig_shallow_guard_enabled is True
    assert config.return_to_dig_max_bucket_mass_kg == pytest.approx(2.0)
    assert config.return_to_dig_max_entry_error_m == pytest.approx(0.55)
    assert config.return_to_dig_start_envelope_gate_enabled is True
    assert config.return_to_dig_start_envelope_plane_depth_mode == "p50_floor"
    assert config.return_to_dig_start_envelope_require_contact is False
    assert config.return_to_dig_start_envelope_direct_handoff_enabled is True
    assert config.return_max_steps == 12


def test_build_pre_dig_alignment_config_preserves_legacy_defaults() -> None:
    config = build_pre_dig_alignment_config(pre_dig_align=None, action_dim=4)

    assert config.pre_dig_align_cfg == {}
    assert config.pre_dig_align_enabled is False
    assert config.pre_dig_align_first_dig_only is False
    assert config.pre_dig_align_replan_after_failed_dig is False
    assert config.pre_dig_align_kp == pytest.approx(2.0)
    assert config.pre_dig_align_kd == pytest.approx(0.25)
    assert config.pre_dig_align_action_clip == [0.55, 0.35, 0.35, 0.35]
    np.testing.assert_array_equal(
        config.pre_dig_align_action_signs,
        np.asarray([1.0, -1.0, 1.0, 1.0], dtype=np.float32),
    )
    assert config.pre_dig_align_action_signs.dtype == np.float32
    np.testing.assert_array_equal(
        config.pre_dig_align_controlled_dims,
        np.asarray([True, True, True, False], dtype=bool),
    )
    assert config.pre_dig_align_controlled_dims.dtype == bool
    assert config.pre_dig_align_bucket_target_qpos is None
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_tolerance,
        np.asarray([0.025, 0.04, 0.05, 0.06], dtype=np.float32),
    )
    assert config.pre_dig_align_qpos_tolerance.dtype == np.float32
    assert config.pre_dig_align_qvel_abs_max == pytest.approx(0.12)
    assert config.pre_dig_align_hold_steps == 3
    assert config.pre_dig_align_max_steps == 140
    assert config.pre_dig_align_max_entry_error_m is None
    assert config.pre_dig_align_timeout_accept_entry_error_m is None
    assert config.pre_dig_align_timeout_replan_entry_error_m is None
    assert config.pre_dig_align_start_envelope_enabled is False
    assert config.pre_dig_align_first_dig_entry_close_handoff is False
    assert config.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max is None
    assert config.pre_dig_align_start_envelope_max_entry_error_m == pytest.approx(0.65)
    assert config.pre_dig_align_entry_intent_controlled_dims is None
    assert config.pre_dig_align_entry_intent_handoff_enabled is False
    assert config.pre_dig_align_surface_guard_enabled is False
    assert config.pre_dig_align_surface_guard_max_penetration_m == pytest.approx(0.005)
    assert config.pre_dig_align_surface_guard_handoff_entry_error_m is None
    assert config.pre_dig_align_surface_guard_use_contact_fallback is True
    np.testing.assert_array_equal(
        config.pre_dig_align_start_qpos_min,
        np.asarray([0.45, 0.52, 0.0, 0.0], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_start_qpos_max,
        np.asarray([0.57, 0.78, 0.40, 0.12], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_start_pose_min,
        np.asarray([-0.60, -0.30, -1.50], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_start_pose_max,
        np.asarray([1.65, 0.25, 1.20], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_min,
        np.asarray([0.44, 0.50, 0.0, 0.0], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_max,
        np.asarray([0.56, 0.79, 0.42, 0.36], dtype=np.float32),
    )
    assert config.pre_dig_align_qpos_from_token_coefficients.shape == (4, 3)
    assert config.pre_dig_align_qpos_from_token_coefficients.dtype == np.float32


def test_build_pre_dig_alignment_config_preserves_overrides() -> None:
    coefficients = np.arange(12, dtype=np.float32).reshape(4, 3)
    action_clip = np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32)

    config = build_pre_dig_alignment_config(
        pre_dig_align={
            "enabled": True,
            "first_dig_only": True,
            "replan_after_failed_dig": True,
            "kp": 3.0,
            "kd": 0.4,
            "action_clip": action_clip,
            "action_signs": [-1.0, 1.0, -1.0, 1.0],
            "controlled_dims": [1, 0, 1, 0],
            "bucket_target_qpos": "0.25",
            "qpos_tolerance": [0.1, 0.2, 0.3, 0.4],
            "qvel_abs_max": 0.2,
            "hold_steps": 0,
            "max_steps": 0,
            "max_entry_error_m": "0.45",
            "timeout_accept_entry_error_m": "0.55",
            "timeout_replan_entry_error_m": "0.65",
            "start_envelope_enabled": True,
            "first_dig_entry_close_handoff": True,
            "first_dig_entry_close_handoff_qvel_abs_max": "0.075",
            "start_envelope_max_entry_error_m": 0.7,
            "entry_intent_controlled_dims": [1, 0, 0, 0],
            "surface_guard_enabled": True,
            "surface_guard_max_penetration_m": 0.01,
            "surface_guard_handoff_entry_error_m": "0.8",
            "surface_guard_use_contact_fallback": False,
            "start_qpos_min": [0.1, 0.2, 0.3, 0.4],
            "start_qpos_max": [0.5, 0.6, 0.7, 0.8],
            "start_pose_min": [-0.1, -0.2, -0.3],
            "start_pose_max": [0.1, 0.2, 0.3],
            "qpos_min": [-0.4, -0.3, -0.2, -0.1],
            "qpos_max": [0.4, 0.3, 0.2, 0.1],
            "qpos_from_token_coefficients": coefficients,
        },
        action_dim=4,
    )

    assert config.pre_dig_align_enabled is True
    assert config.pre_dig_align_first_dig_only is True
    assert config.pre_dig_align_replan_after_failed_dig is True
    assert config.pre_dig_align_kp == pytest.approx(3.0)
    assert config.pre_dig_align_kd == pytest.approx(0.4)
    assert config.pre_dig_align_action_clip is action_clip
    np.testing.assert_array_equal(
        config.pre_dig_align_action_signs,
        np.asarray([-1.0, 1.0, -1.0, 1.0], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_controlled_dims,
        np.asarray([True, False, True, False], dtype=bool),
    )
    assert config.pre_dig_align_bucket_target_qpos == pytest.approx(0.25)
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_tolerance,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert config.pre_dig_align_qvel_abs_max == pytest.approx(0.2)
    assert config.pre_dig_align_hold_steps == 1
    assert config.pre_dig_align_max_steps == 1
    assert config.pre_dig_align_max_entry_error_m == pytest.approx(0.45)
    assert config.pre_dig_align_timeout_accept_entry_error_m == pytest.approx(0.55)
    assert config.pre_dig_align_timeout_replan_entry_error_m == pytest.approx(0.65)
    assert config.pre_dig_align_start_envelope_enabled is True
    assert config.pre_dig_align_first_dig_entry_close_handoff is True
    assert (
        config.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
        == pytest.approx(0.075)
    )
    assert config.pre_dig_align_start_envelope_max_entry_error_m == pytest.approx(0.7)
    np.testing.assert_array_equal(
        config.pre_dig_align_entry_intent_controlled_dims,
        np.asarray([True, False, False, False], dtype=bool),
    )
    assert config.pre_dig_align_entry_intent_handoff_enabled is True
    assert config.pre_dig_align_surface_guard_enabled is True
    assert config.pre_dig_align_surface_guard_max_penetration_m == pytest.approx(0.01)
    assert config.pre_dig_align_surface_guard_handoff_entry_error_m == pytest.approx(
        0.8
    )
    assert config.pre_dig_align_surface_guard_use_contact_fallback is False
    np.testing.assert_array_equal(
        config.pre_dig_align_start_qpos_min,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_start_qpos_max,
        np.asarray([0.5, 0.6, 0.7, 0.8], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_start_pose_min,
        np.asarray([-0.1, -0.2, -0.3], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_start_pose_max,
        np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_min,
        np.asarray([-0.4, -0.3, -0.2, -0.1], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_max,
        np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        config.pre_dig_align_qpos_from_token_coefficients,
        coefficients,
    )


def test_build_pre_dig_alignment_config_preserves_explicit_intent_handoff() -> None:
    config = build_pre_dig_alignment_config(
        pre_dig_align={
            "entry_intent_controlled_dims": [1, 0, 0, 0],
            "entry_intent_handoff_enabled": False,
        },
        action_dim=4,
    )

    np.testing.assert_array_equal(
        config.pre_dig_align_entry_intent_controlled_dims,
        np.asarray([True, False, False, False], dtype=bool),
    )
    assert config.pre_dig_align_entry_intent_handoff_enabled is False


def test_build_conditioning_config_preserves_default_values() -> None:
    config = build_conditioning_config(
        dig_cut_planner=None,
        return_target_planner=None,
        action_dim=4,
        coverage_percentile_list_fn=CoverageService.coverage_percentile_list,
        coverage_percentile_name_fn=CoverageService.coverage_percentile_name,
    )

    assert config.dig_cut_planner_cfg == {}
    assert config.dig_cut_planner_enabled is True
    assert config.dig_cut_planner_mode == "conservative_pose"
    assert config.dig_cut_planner_fallback_mode == "conservative_pose"
    assert config.dig_cut_hold_token_until_skill_exit is False
    assert config.dig_cut_prior_path == ""
    assert config.dig_cut_prior == {}
    assert config.dig_cut_prior_id == ""
    assert config.return_start_envelope_use_cell_prior is False
    assert config.return_start_envelope_min_source_count == 1
    assert config.return_start_envelope_min_source_fraction == 0.0
    assert config.return_start_envelope_qpos_from_relocate_coefficients is None
    np.testing.assert_allclose(
        config.return_start_envelope_qpos_from_relocate_min,
        np.asarray([0.44, 0.50, 0.0, 0.0], dtype=np.float32),
    )
    assert config.return_start_envelope_spatial_from_relocate_coefficients is None
    np.testing.assert_allclose(
        config.return_start_envelope_spatial_from_relocate_min,
        np.asarray([-1.0, -0.10], dtype=np.float32),
    )
    assert config.dig_depth_profile_source == "live_plan"
    assert config.dig_depth_profile_required is False
    assert config.dig_depth_profile_allow_live_fallback is True
    assert config.dig_depth_profile_allow_global_fallback is True
    assert config.return_target_planner_cfg == {}
    assert config.return_target_planner_enabled is False
    assert config.return_target_hold_token_until_skill_exit is True
    assert config.return_target_token_source_prefix == "return_target"
    assert config.coverage_candidate_layout == "percentile_grid"
    assert config.coverage_use_env_removed_depth is False
    assert config.coverage_multi_pass_max_passes == 1
    assert config.coverage_multi_pass_min_remaining_depth_m == pytest.approx(0.05)
    assert config.coverage_state_exemplars_enabled is False
    assert config.coverage_state_exemplar_path == ""
    assert config.coverage_first_dig_strategy == "coverage_score"
    assert config.coverage_first_dig_preferred_corridor_id is None
    assert config.coverage_first_dig_max_entry_distance_m is None
    assert config.coverage_first_dig_max_qpos_delta is None
    assert config.coverage_entry_x_percentiles == ("p10", "p50", "p90")
    assert config.coverage_entry_z_percentiles == ("p10", "p50", "p90")
    assert config.coverage_cut_direction_percentile == "p50"
    assert config.coverage_payload_percentile == "p50"


def test_build_conditioning_config_preserves_nested_overrides(tmp_path) -> None:
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(
        json.dumps(
            {
                "prior_id": "unit_prior",
                "token_order": list(range(DIG_CUT_TOKEN_DIM)),
                "coverage_state_exemplars_path": "from_prior.json",
                "dig_depth_profile_cells": [],
            }
        ),
        encoding="utf-8",
    )
    qpos_coefficients = np.arange(32, dtype=np.float32).reshape(4, 8)
    spatial_coefficients = np.arange(16, dtype=np.float32).reshape(2, 8)

    config = build_conditioning_config(
        dig_cut_planner={
            "enabled": True,
            "mode": "operator_prior_coverage",
            "fallback_mode": "conservative_pose",
            "prior_path": str(prior_path),
            "return_start_envelope": {
                "use_cell_prior": True,
                "min_source_count": 0,
                "min_source_fraction": -1.0,
                "qpos_from_relocate": {
                    "enabled": True,
                    "coefficients": qpos_coefficients,
                    "qpos_min": [0.1, 0.2, 0.3, 0.4],
                    "qpos_max": [0.5, 0.6, 0.7, 0.8],
                    "use_prior_qpos_bounds": True,
                },
                "spatial_from_relocate": {
                    "enabled": True,
                    "coefficients": spatial_coefficients,
                    "spatial_min": [-0.5, -0.25],
                    "spatial_max": [0.5, 0.75],
                    "use_prior_spatial_bounds": True,
                },
            },
            "dig_depth_profile": {
                "source": "Prior_Profile",
                "required": True,
                "allow_live_fallback": False,
                "allow_global_fallback": False,
            },
            "coverage": {
                "candidate_layout": "cell_weighted_3x2",
                "multi_pass_enabled": True,
                "multi_pass_max_passes": 0,
                "multi_pass_min_remaining_depth_m": 0.12,
                "state_conditioned_exemplars": {
                    "enabled": True,
                    "path": "explicit.json",
                    "k": 0,
                    "removed_depth_scale_m": 0.0,
                    "target_cell_weight": -1.0,
                    "score_weight": 0.5,
                    "temperature": 0.0,
                    "skip_rejected": False,
                },
                "first_dig_strategy": "Nearest_Entry",
                "first_dig_preferred_corridor_id": "7",
                "first_dig_max_entry_distance_m": "0.75",
                "first_dig_max_qpos_delta": "0.1,0.2,0.3,0.4",
                "entry_x_percentiles": "p05,p50,p90",
                "entry_z_percentiles": ["p10", "bad", "p50"],
                "cut_direction_percentile": "bad",
                "payload_percentile": "p90",
            },
        },
        return_target_planner={
            "enabled": True,
            "hold_token_until_skill_exit": False,
            "token_source_prefix": "unit_return",
        },
        action_dim=4,
        coverage_percentile_list_fn=CoverageService.coverage_percentile_list,
        coverage_percentile_name_fn=CoverageService.coverage_percentile_name,
    )

    assert config.dig_cut_planner_mode == "operator_prior_coverage"
    assert config.dig_cut_hold_token_until_skill_exit is True
    assert config.dig_cut_prior_path == str(prior_path)
    assert config.dig_cut_prior_id == "unit_prior"
    assert config.return_start_envelope_use_cell_prior is True
    assert config.return_start_envelope_min_source_count == 1
    assert config.return_start_envelope_min_source_fraction == 0.0
    np.testing.assert_allclose(
        config.return_start_envelope_qpos_from_relocate_coefficients,
        qpos_coefficients,
    )
    np.testing.assert_allclose(
        config.return_start_envelope_qpos_from_relocate_min,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert config.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds
    np.testing.assert_allclose(
        config.return_start_envelope_spatial_from_relocate_coefficients,
        spatial_coefficients,
    )
    assert config.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds
    assert config.dig_depth_profile_source == "prior_profile"
    assert config.dig_depth_profile_required is True
    assert config.dig_depth_profile_allow_live_fallback is False
    assert config.dig_depth_profile_allow_global_fallback is False
    assert config.return_target_planner_enabled is True
    assert config.return_target_hold_token_until_skill_exit is False
    assert config.return_target_token_source_prefix == "unit_return"
    assert config.coverage_candidate_layout == "cell_weighted_3x2"
    assert config.coverage_use_env_removed_depth is True
    assert config.coverage_multi_pass_enabled is True
    assert config.coverage_multi_pass_max_passes == 1
    assert config.coverage_multi_pass_min_remaining_depth_m == pytest.approx(0.12)
    assert config.coverage_state_exemplars_enabled is True
    assert config.coverage_state_exemplar_path == "explicit.json"
    assert config.coverage_state_exemplar_k == 1
    assert config.coverage_state_exemplar_removed_depth_scale_m == pytest.approx(
        1.0e-6
    )
    assert config.coverage_state_exemplar_target_cell_weight == pytest.approx(0.0)
    assert config.coverage_state_exemplar_score_weight == pytest.approx(0.5)
    assert config.coverage_state_exemplar_temperature == pytest.approx(1.0e-6)
    assert config.coverage_state_exemplar_skip_rejected is False
    assert config.coverage_first_dig_strategy == "nearest_entry"
    assert config.coverage_first_dig_preferred_corridor_id == 7
    assert config.coverage_first_dig_max_entry_distance_m == pytest.approx(0.75)
    np.testing.assert_allclose(
        config.coverage_first_dig_max_qpos_delta,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert config.coverage_entry_x_percentiles == ("p50", "p90")
    assert config.coverage_entry_z_percentiles == ("p10", "p50")
    assert config.coverage_cut_direction_percentile == "p50"
    assert config.coverage_payload_percentile == "p90"


def test_load_dig_cut_prior_validates_token_order(tmp_path) -> None:
    valid_path = tmp_path / "prior.json"
    valid_path.write_text(
        json.dumps({"prior_id": "unit", "token_order": list(range(DIG_CUT_TOKEN_DIM))}),
        encoding="utf-8",
    )

    assert load_dig_cut_prior("") == {}
    assert load_dig_cut_prior(str(valid_path))["prior_id"] == "unit"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"token_order": [0]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid token_order length"):
        load_dig_cut_prior(str(invalid_path))


def test_validate_dig_cut_planner_config_preserves_error_cases() -> None:
    _validate()
    _validate(dig_cut_planner_enabled=False, dig_cut_planner_mode="unsupported")

    with pytest.raises(ValueError, match="Unsupported dig_cut_planner mode"):
        _validate(dig_cut_planner_mode="unsupported")
    with pytest.raises(ValueError, match="operator_prior dig_cut_planner requires prior_path"):
        _validate(dig_cut_planner_mode="operator_prior", dig_cut_prior_path="")
    with pytest.raises(ValueError, match="Unsupported coverage.candidate_layout"):
        _validate(coverage_candidate_layout="unknown")
    with pytest.raises(ValueError, match="Unsupported dig_depth_profile.source"):
        _validate(dig_depth_profile_source="unknown")
    with pytest.raises(
        ValueError,
        match="dig_depth_profile.source='prior_profile' requires prior_path",
    ):
        _validate(dig_depth_profile_source="prior_profile", dig_cut_prior_path="")
    with pytest.raises(
        ValueError,
        match="requires dig_depth_profile_cells in the dig cut prior",
    ):
        _validate(dig_depth_profile_source="prior_profile", dig_cut_prior={})
    with pytest.raises(
        ValueError,
        match="dig_depth_profile.required=true must set allow_live_fallback=false",
    ):
        _validate(
            dig_depth_profile_source="prior_profile",
            dig_cut_prior={"dig_depth_profile_cells": []},
            dig_depth_profile_required=True,
            dig_depth_profile_allow_live_fallback=True,
        )


def test_normalize_goal_sequence_accepts_names_and_ids() -> None:
    assert normalize_goal_sequence(None) == ()
    assert normalize_goal_sequence(["left", "mid", "right"]) == (0, 1, 2)
    assert normalize_goal_sequence([0, 2]) == (0, 2)

    with pytest.raises(ValueError, match="Unknown primitive goal sector"):
        normalize_goal_sequence(["front"])
    with pytest.raises(ValueError, match="Primitive goal sector id must be 0, 1, or 2"):
        normalize_goal_sequence([3])


def _validate(**overrides: object) -> None:
    defaults = {
        "dig_cut_planner_enabled": True,
        "dig_cut_planner_mode": "conservative_pose",
        "dig_cut_prior_path": "prior.json",
        "coverage_candidate_layout": "percentile_grid",
        "dig_depth_profile_source": "live_plan",
        "dig_cut_prior": {"dig_depth_profile_cells": []},
        "dig_depth_profile_required": False,
        "dig_depth_profile_allow_live_fallback": False,
    }
    defaults.update(overrides)
    validate_dig_cut_planner_config(**defaults)
