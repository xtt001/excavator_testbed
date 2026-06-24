from __future__ import annotations

from typing import Any

from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def make_policy_shell_for_private_weld_tests(**overrides: Any) -> PrimitivePlannerACTPolicy:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    seed_policy_token_factory_config(policy)
    seed_policy_coverage_static_config(policy)
    for name, value in overrides.items():
        setattr(policy, name, value)
    return policy


def seed_policy_coverage_static_config(
    policy: PrimitivePlannerACTPolicy,
) -> PrimitivePlannerACTPolicy:
    policy.action_dim = 4
    policy.dig_cut_prior_path = ""
    policy.dig_cut_planner_mode = "operator_prior"
    policy.coverage_candidate_layout = "corridor_grid"
    policy.coverage_entry_x_percentiles = ("p10", "p50", "p90")
    policy.coverage_entry_z_percentiles = ("p10", "p50", "p90")
    policy.coverage_cut_direction_percentile = "p50"
    policy.coverage_cut_length_percentile = "p50"
    policy.coverage_cut_depth_percentile = "p50"
    policy.coverage_payload_percentile = "p50"
    policy.coverage_use_env_removed_depth = False
    policy.coverage_max_attempts_per_corridor = 1
    policy.coverage_recent_selection_penalty = 0.0
    policy.coverage_unattempted_bonus = 0.0
    policy.coverage_attempt_penalty = 0.0
    policy.coverage_cell_confidence_weight = 0.0
    policy.coverage_rare_cell_source_fraction_threshold = 0.0
    policy.coverage_rare_cell_max_attempts = 1
    policy.coverage_recent_row_selection_penalty = 0.0
    policy.coverage_first_dig_strategy = "best_score"
    policy.coverage_first_dig_preferred_corridor_id = None
    policy.coverage_first_dig_preferred_bonus = 0.0
    policy.coverage_first_dig_proximity_weight = 0.0
    policy.coverage_first_dig_max_entry_distance_m = None
    policy.coverage_first_dig_qpos_delta_weight = 1.0
    policy.coverage_first_dig_max_qpos_delta = None
    policy.pre_dig_align_controlled_dims = [False, False, False, False]
    policy.coverage_state_exemplars_enabled = False
    policy.coverage_state_exemplar_path = ""
    policy.coverage_state_exemplar_k = 1
    policy.coverage_state_exemplar_removed_depth_scale_m = 1.0
    policy.coverage_state_exemplar_target_cell_weight = 1.0
    policy.coverage_state_exemplar_temperature = 1.0
    policy.coverage_state_exemplar_skip_rejected = True
    policy.coverage_state_exemplar_score_weight = 0.0
    policy.coverage_state_exemplars_by_cell = {}
    policy.coverage_multi_pass_enabled = False
    policy.coverage_multi_pass_max_passes = 1
    policy.coverage_multi_pass_min_remaining_depth_m = 0.0
    policy.coverage_low_productivity_payload_kg = 0.0
    policy.coverage_low_productivity_deposit_kg = 0.0
    policy.coverage_deplete_after_low_streak = 1
    policy.coverage_min_remaining_depth_m = 0.0
    policy.coverage_belief_depleted_score = 0.0
    policy.coverage_belief_gain_scale = 1.0
    policy.coverage_global_low_productivity_stop = 0
    return policy


def seed_policy_token_factory_config(
    policy: PrimitivePlannerACTPolicy,
) -> PrimitivePlannerACTPolicy:
    policy.goal_sequence = ()
    policy.goal_scenario_id = ""
    policy.goal_depth_norm = 0.0
    policy.goal_dump_target_norm = 0.0
    policy.dig_cut_prior = {}
    policy.dig_depth_profile_source = "none"
    policy.dig_depth_profile_required = False
    policy.dig_depth_profile_allow_live_fallback = True
    policy.dig_depth_profile_allow_global_fallback = True
    policy.return_target_token_source_prefix = "return_target"
    policy.return_start_envelope_use_cell_prior = False
    policy.return_start_envelope_min_source_count = 1
    policy.return_start_envelope_min_source_fraction = 0.0
    policy.return_start_envelope_qpos_from_relocate_enabled = False
    policy.return_start_envelope_qpos_from_relocate_coefficients = None
    policy.return_start_envelope_qpos_from_relocate_min = None
    policy.return_start_envelope_qpos_from_relocate_max = None
    policy.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds = True
    policy.return_start_envelope_spatial_from_relocate_enabled = False
    policy.return_start_envelope_spatial_from_relocate_coefficients = None
    policy.return_start_envelope_spatial_from_relocate_min = None
    policy.return_start_envelope_spatial_from_relocate_max = None
    policy.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds = True
    return policy
