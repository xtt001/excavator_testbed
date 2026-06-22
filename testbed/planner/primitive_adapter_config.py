"""Public adapter configuration normalization for primitive planner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.cell_entry import (
    CellEntryPlanner,
    CellGridSpec,
    PlannerDecisionAuditor,
)
from testbed.planner.primitive_coverage_exemplars import (
    CoverageStateExemplarPlanner,
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive_tokens import GoalTokenProvider


@dataclass(frozen=True)
class PrimitivePlannerAdapterConfigInputs:
    """Public primitive planner config parameters excluding policy handles."""

    bootstrap_end_mode: str = "disabled"
    bootstrap_end_min_bucket_mass_kg: float = 300.0
    bootstrap_end_min_distance_to_dig_area_m: float = 0.25
    dig_to_carry_min_bucket_mass_kg: float = 300.0
    dig_to_carry_min_distance_to_dig_area_m: float = 0.0
    dig_to_carry_target_bucket_mass_kg: float | None = None
    dig_to_carry_mass_plateau_enabled: bool = False
    dig_to_carry_mass_plateau_min_bucket_mass_kg: float = 20.0
    dig_to_carry_mass_plateau_epsilon_kg: float = 1.0
    dig_to_carry_mass_plateau_hold_steps: int = 25
    dig_to_carry_mass_plateau_min_steps: int = 80
    dig_bad_replan_enabled: bool = False
    dig_bad_replan_max_steps: int = 180
    dig_bad_replan_min_bucket_mass_kg: float = 15.0
    dig_exit_guard_enabled: bool = False
    dig_exit_guard_min_steps: int = 80
    dig_exit_guard_overshoot_m: float = 0.65
    dig_exit_guard_min_bucket_mass_kg: float = 20.0
    dig_failed_replan_next_skill: str = "dig"
    dump_ready_min_bucket_mass_kg: float = 150.0
    dump_ready_min_height_above_rim_m: float = 0.45
    dump_ready_require_over_footprint: bool = True
    dump_ready_require_clearance: bool = True
    dump_ready_max_horizontal_distance_m: float | None = 0.60
    dump_ready_position_mode: str = "footprint_or_dump_area_relative"
    dump_ready_max_dump_area_footprint_outside_distance_m: float | None = 0.05
    dump_ready_min_dump_area_relative_x_m: float | None = None
    dump_ready_max_dump_area_relative_x_m: float | None = None
    dump_ready_min_dump_area_relative_z_m: float | None = None
    dump_ready_max_dump_area_relative_z_m: float | None = None
    dump_ready_hold_steps: int = 3
    dump_ready_near_window_enabled: bool = False
    dump_ready_near_window_x_tolerance_m: float = 0.05
    dump_ready_near_window_z_tolerance_m: float = 0.05
    dump_ready_near_window_outside_tolerance_m: float = 0.0
    dump_ready_near_window_require_over_footprint: bool = True
    dump_done_max_bucket_mass_kg: float = 100.0
    dump_done_min_deposit_delta_kg: float = 10.0
    dump_done_hold_steps: int = 2
    dump_done_use_boundary_event: bool = True
    return_to_dig_shallow_guard_enabled: bool = False
    return_to_dig_max_bucket_mass_kg: float = 15.0
    return_to_dig_touch_tolerance_m: float = 0.05
    return_to_dig_min_depth_m: float = 0.02
    return_to_dig_max_depth_m: float = 0.12
    return_to_dig_max_entry_error_m: float | None = None
    return_to_dig_start_envelope_gate_enabled: bool = False
    return_to_dig_start_envelope_spatial_tolerance: float = 0.10
    return_to_dig_start_envelope_depth_tolerance_m: float = 0.08
    return_to_dig_start_envelope_local_depth_tolerance_m: float = 0.005
    return_to_dig_start_envelope_plane_depth_tolerance_m: float = 0.05
    return_to_dig_start_envelope_plane_depth_mode: str = "range"
    return_to_dig_start_envelope_qpos_tolerance: float = 0.04
    return_to_dig_start_envelope_require_contact: bool = True
    return_to_dig_start_envelope_direct_handoff_enabled: bool = False
    return_max_steps: int = 420
    action_dim: int = 4
    primitive_checkpoint_paths: dict[str, str] | None = None
    goal_sequence: list[str] | tuple[str, ...] | None = None
    goal_scenario_id: str = "s0_truck"
    goal_depth_norm: float = 1.0
    goal_dump_target_norm: float = 1.0
    cell_entry_enabled: bool = False
    cell_entry_grid: dict[str, Any] | None = None
    cell_entry_low_productivity_payload_gain_kg: float = 100.0
    dig_cut_planner: dict[str, Any] | None = None
    return_target_planner: dict[str, Any] | None = None
    scripted_bootstrap_target_qpos: list[float] | tuple[float, ...] | np.ndarray | None = None
    scripted_bootstrap_kp: float = 2.0
    scripted_bootstrap_kd: float = 0.25
    scripted_bootstrap_action_clip: float | list[float] | tuple[float, ...] = 0.35
    scripted_bootstrap_action_signs: list[float] | tuple[float, ...] | np.ndarray | None = None
    scripted_bootstrap_qpos_tolerance: float = 0.02
    scripted_bootstrap_qvel_abs_max: float = 0.08
    scripted_bootstrap_hold_steps: int = 5
    scripted_bootstrap_max_steps: int = 240
    pre_dig_align: dict[str, Any] | None = None


@dataclass
class PrimitivePlannerAdapterConfigState:
    """Normalized policy-field values for the public adapter shell."""

    field_updates: dict[str, Any]

    def as_policy_field_updates(self) -> dict[str, Any]:
        return dict(self.field_updates)


class PrimitivePlannerAdapterConfigNormalizer:
    """Build normalized legacy policy fields from public constructor config."""

    @staticmethod
    def normalize(
        inputs: PrimitivePlannerAdapterConfigInputs,
    ) -> PrimitivePlannerAdapterConfigState:
        values: dict[str, Any] = {}

        def set_value(name: str, value: Any) -> Any:
            values[name] = value
            return value

        action_dim = set_value("action_dim", int(inputs.action_dim))
        bootstrap_end_mode = set_value(
            "bootstrap_end_mode",
            str(inputs.bootstrap_end_mode),
        )
        set_value(
            "bootstrap_end_min_bucket_mass_kg",
            float(inputs.bootstrap_end_min_bucket_mass_kg),
        )
        set_value(
            "bootstrap_end_min_distance_to_dig_area_m",
            float(inputs.bootstrap_end_min_distance_to_dig_area_m),
        )
        dig_to_carry_min_bucket_mass_kg = set_value(
            "dig_to_carry_min_bucket_mass_kg",
            float(inputs.dig_to_carry_min_bucket_mass_kg),
        )
        set_value(
            "dig_to_carry_min_distance_to_dig_area_m",
            float(inputs.dig_to_carry_min_distance_to_dig_area_m),
        )
        set_value(
            "dig_to_carry_target_bucket_mass_kg",
            float(
                dig_to_carry_min_bucket_mass_kg
                if inputs.dig_to_carry_target_bucket_mass_kg is None
                else inputs.dig_to_carry_target_bucket_mass_kg
            ),
        )
        set_value(
            "dig_to_carry_mass_plateau_enabled",
            bool(inputs.dig_to_carry_mass_plateau_enabled),
        )
        set_value(
            "dig_to_carry_mass_plateau_min_bucket_mass_kg",
            float(inputs.dig_to_carry_mass_plateau_min_bucket_mass_kg),
        )
        set_value(
            "dig_to_carry_mass_plateau_epsilon_kg",
            float(inputs.dig_to_carry_mass_plateau_epsilon_kg),
        )
        set_value(
            "dig_to_carry_mass_plateau_hold_steps",
            max(1, int(inputs.dig_to_carry_mass_plateau_hold_steps)),
        )
        set_value(
            "dig_to_carry_mass_plateau_min_steps",
            max(1, int(inputs.dig_to_carry_mass_plateau_min_steps)),
        )
        set_value("dig_bad_replan_enabled", bool(inputs.dig_bad_replan_enabled))
        set_value(
            "dig_bad_replan_max_steps",
            max(1, int(inputs.dig_bad_replan_max_steps)),
        )
        set_value(
            "dig_bad_replan_min_bucket_mass_kg",
            float(inputs.dig_bad_replan_min_bucket_mass_kg),
        )
        set_value("dig_exit_guard_enabled", bool(inputs.dig_exit_guard_enabled))
        set_value(
            "dig_exit_guard_min_steps",
            max(1, int(inputs.dig_exit_guard_min_steps)),
        )
        set_value("dig_exit_guard_overshoot_m", float(inputs.dig_exit_guard_overshoot_m))
        set_value(
            "dig_exit_guard_min_bucket_mass_kg",
            float(inputs.dig_exit_guard_min_bucket_mass_kg),
        )
        set_value(
            "dig_failed_replan_next_skill",
            normalize_failed_dig_replan_skill(inputs.dig_failed_replan_next_skill),
        )

        set_value(
            "dump_ready_min_bucket_mass_kg",
            float(inputs.dump_ready_min_bucket_mass_kg),
        )
        set_value(
            "dump_ready_min_height_above_rim_m",
            float(inputs.dump_ready_min_height_above_rim_m),
        )
        set_value(
            "dump_ready_require_over_footprint",
            bool(inputs.dump_ready_require_over_footprint),
        )
        set_value(
            "dump_ready_require_clearance",
            bool(inputs.dump_ready_require_clearance),
        )
        set_value(
            "dump_ready_max_horizontal_distance_m",
            none_or_float(inputs.dump_ready_max_horizontal_distance_m),
        )
        set_value("dump_ready_position_mode", str(inputs.dump_ready_position_mode))
        set_value(
            "dump_ready_max_dump_area_footprint_outside_distance_m",
            none_or_float(inputs.dump_ready_max_dump_area_footprint_outside_distance_m),
        )
        set_value(
            "dump_ready_min_dump_area_relative_x_m",
            none_or_float(inputs.dump_ready_min_dump_area_relative_x_m),
        )
        set_value(
            "dump_ready_max_dump_area_relative_x_m",
            none_or_float(inputs.dump_ready_max_dump_area_relative_x_m),
        )
        set_value(
            "dump_ready_min_dump_area_relative_z_m",
            none_or_float(inputs.dump_ready_min_dump_area_relative_z_m),
        )
        set_value(
            "dump_ready_max_dump_area_relative_z_m",
            none_or_float(inputs.dump_ready_max_dump_area_relative_z_m),
        )
        set_value("dump_ready_hold_steps", max(1, int(inputs.dump_ready_hold_steps)))
        set_value(
            "dump_ready_near_window_enabled",
            bool(inputs.dump_ready_near_window_enabled),
        )
        set_value(
            "dump_ready_near_window_x_tolerance_m",
            float(inputs.dump_ready_near_window_x_tolerance_m),
        )
        set_value(
            "dump_ready_near_window_z_tolerance_m",
            float(inputs.dump_ready_near_window_z_tolerance_m),
        )
        set_value(
            "dump_ready_near_window_outside_tolerance_m",
            float(inputs.dump_ready_near_window_outside_tolerance_m),
        )
        set_value(
            "dump_ready_near_window_require_over_footprint",
            bool(inputs.dump_ready_near_window_require_over_footprint),
        )
        set_value(
            "dump_done_max_bucket_mass_kg",
            float(inputs.dump_done_max_bucket_mass_kg),
        )
        set_value(
            "dump_done_min_deposit_delta_kg",
            float(inputs.dump_done_min_deposit_delta_kg),
        )
        set_value("dump_done_hold_steps", max(1, int(inputs.dump_done_hold_steps)))
        set_value("dump_done_use_boundary_event", bool(inputs.dump_done_use_boundary_event))

        set_value(
            "return_to_dig_shallow_guard_enabled",
            bool(inputs.return_to_dig_shallow_guard_enabled),
        )
        set_value(
            "return_to_dig_max_bucket_mass_kg",
            float(inputs.return_to_dig_max_bucket_mass_kg),
        )
        set_value(
            "return_to_dig_touch_tolerance_m",
            float(inputs.return_to_dig_touch_tolerance_m),
        )
        set_value(
            "return_to_dig_min_depth_m",
            float(inputs.return_to_dig_min_depth_m),
        )
        set_value(
            "return_to_dig_max_depth_m",
            float(inputs.return_to_dig_max_depth_m),
        )
        set_value(
            "return_to_dig_max_entry_error_m",
            optional_float(inputs.return_to_dig_max_entry_error_m),
        )
        set_value(
            "return_to_dig_start_envelope_gate_enabled",
            bool(inputs.return_to_dig_start_envelope_gate_enabled),
        )
        set_value(
            "return_to_dig_start_envelope_spatial_tolerance",
            float(inputs.return_to_dig_start_envelope_spatial_tolerance),
        )
        set_value(
            "return_to_dig_start_envelope_depth_tolerance_m",
            float(inputs.return_to_dig_start_envelope_depth_tolerance_m),
        )
        set_value(
            "return_to_dig_start_envelope_local_depth_tolerance_m",
            float(inputs.return_to_dig_start_envelope_local_depth_tolerance_m),
        )
        set_value(
            "return_to_dig_start_envelope_plane_depth_tolerance_m",
            float(inputs.return_to_dig_start_envelope_plane_depth_tolerance_m),
        )
        set_value(
            "return_to_dig_start_envelope_plane_depth_mode",
            normalize_plane_depth_mode(
                inputs.return_to_dig_start_envelope_plane_depth_mode
            ),
        )
        set_value(
            "return_to_dig_start_envelope_qpos_tolerance",
            float(inputs.return_to_dig_start_envelope_qpos_tolerance),
        )
        set_value(
            "return_to_dig_start_envelope_require_contact",
            bool(inputs.return_to_dig_start_envelope_require_contact),
        )
        set_value(
            "return_to_dig_start_envelope_direct_handoff_enabled",
            bool(inputs.return_to_dig_start_envelope_direct_handoff_enabled),
        )
        set_value("return_max_steps", int(inputs.return_max_steps))
        set_value(
            "primitive_checkpoint_paths",
            {
                str(name): str(path)
                for name, path in dict(
                    inputs.primitive_checkpoint_paths or {}
                ).items()
            },
        )
        set_value("goal_sequence", normalize_goal_sequence(inputs.goal_sequence))
        set_value("goal_scenario_id", str(inputs.goal_scenario_id))
        set_value("goal_depth_norm", float(inputs.goal_depth_norm))
        set_value("goal_dump_target_norm", float(inputs.goal_dump_target_norm))

        cell_entry_grid = CellGridSpec(**dict(inputs.cell_entry_grid or {}))
        cell_entry_grid.validate()
        set_value("cell_entry_enabled", bool(inputs.cell_entry_enabled))
        set_value("cell_entry_grid", cell_entry_grid)
        set_value("cell_entry_planner", CellEntryPlanner(grid=cell_entry_grid))
        set_value(
            "cell_entry_auditor",
            PlannerDecisionAuditor(
                grid=cell_entry_grid,
                low_productivity_payload_gain_kg=(
                    inputs.cell_entry_low_productivity_payload_gain_kg
                ),
            ),
        )

        dig_cut_planner_cfg = set_value(
            "dig_cut_planner_cfg",
            dict(inputs.dig_cut_planner or {}),
        )
        dig_cut_planner_enabled = set_value(
            "dig_cut_planner_enabled",
            bool(dig_cut_planner_cfg.get("enabled", True)),
        )
        dig_cut_planner_mode = set_value(
            "dig_cut_planner_mode",
            str(dig_cut_planner_cfg.get("mode", "conservative_pose")),
        )
        set_value(
            "dig_cut_planner_fallback_mode",
            str(dig_cut_planner_cfg.get("fallback_mode", "conservative_pose")),
        )
        set_value(
            "dig_cut_hold_token_until_skill_exit",
            bool(
                dig_cut_planner_cfg.get(
                    "hold_token_until_skill_exit",
                    dig_cut_planner_mode
                    in {
                        "operator_prior",
                        "operator_prior_coverage",
                        "operator_prior_sweep_belief",
                    },
                )
            ),
        )
        dig_cut_prior_path = set_value(
            "dig_cut_prior_path",
            str(dig_cut_planner_cfg.get("prior_path", "")),
        )
        dig_cut_prior = set_value(
            "dig_cut_prior",
            load_dig_cut_prior(dig_cut_prior_path),
        )
        set_value("dig_cut_prior_id", str(dig_cut_prior.get("prior_id", "")))

        return_start_envelope_cfg = dict(
            dig_cut_planner_cfg.get("return_start_envelope", {}) or {}
        )
        set_value(
            "return_start_envelope_use_cell_prior",
            bool(return_start_envelope_cfg.get("use_cell_prior", False)),
        )
        set_value(
            "return_start_envelope_min_source_count",
            max(1, int(return_start_envelope_cfg.get("min_source_count", 1))),
        )
        set_value(
            "return_start_envelope_min_source_fraction",
            max(
                0.0,
                float(return_start_envelope_cfg.get("min_source_fraction", 0.0)),
            ),
        )
        qpos_from_relocate_cfg = dict(
            return_start_envelope_cfg.get("qpos_from_relocate", {}) or {}
        )
        set_value(
            "return_start_envelope_qpos_from_relocate_enabled",
            bool(qpos_from_relocate_cfg.get("enabled", False)),
        )
        raw_relocate_coefficients = qpos_from_relocate_cfg.get("coefficients")
        set_value(
            "return_start_envelope_qpos_from_relocate_coefficients",
            None
            if raw_relocate_coefficients is None
            else np.asarray(raw_relocate_coefficients, dtype=np.float32).reshape(4, 8),
        )
        set_value(
            "return_start_envelope_qpos_from_relocate_min",
            align_vector(
                qpos_from_relocate_cfg.get("qpos_min", [0.44, 0.50, 0.0, 0.0]),
                default=[0.44, 0.50, 0.0, 0.0],
                action_dim=action_dim,
            ),
        )
        set_value(
            "return_start_envelope_qpos_from_relocate_max",
            align_vector(
                qpos_from_relocate_cfg.get("qpos_max", [0.56, 0.80, 0.56, 0.48]),
                default=[0.56, 0.80, 0.56, 0.48],
                action_dim=action_dim,
            ),
        )
        set_value(
            "return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds",
            bool(qpos_from_relocate_cfg.get("use_prior_qpos_bounds", False)),
        )
        spatial_from_relocate_cfg = dict(
            return_start_envelope_cfg.get("spatial_from_relocate", {}) or {}
        )
        set_value(
            "return_start_envelope_spatial_from_relocate_enabled",
            bool(spatial_from_relocate_cfg.get("enabled", False)),
        )
        raw_spatial_coefficients = spatial_from_relocate_cfg.get("coefficients")
        set_value(
            "return_start_envelope_spatial_from_relocate_coefficients",
            None
            if raw_spatial_coefficients is None
            else np.asarray(raw_spatial_coefficients, dtype=np.float32).reshape(2, 8),
        )
        set_value(
            "return_start_envelope_spatial_from_relocate_min",
            np.asarray(
                spatial_from_relocate_cfg.get("spatial_min", [-1.0, -0.10]),
                dtype=np.float32,
            ).reshape(2),
        )
        set_value(
            "return_start_envelope_spatial_from_relocate_max",
            np.asarray(
                spatial_from_relocate_cfg.get("spatial_max", [1.0, 1.0]),
                dtype=np.float32,
            ).reshape(2),
        )
        set_value(
            "return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds",
            bool(spatial_from_relocate_cfg.get("use_prior_spatial_bounds", False)),
        )

        dig_depth_profile_cfg = dict(
            dig_cut_planner_cfg.get("dig_depth_profile", {}) or {}
        )
        dig_depth_profile_source = set_value(
            "dig_depth_profile_source",
            str(dig_depth_profile_cfg.get("source", "live_plan")).strip().lower(),
        )
        dig_depth_profile_required = set_value(
            "dig_depth_profile_required",
            bool(dig_depth_profile_cfg.get("required", False)),
        )
        dig_depth_profile_allow_live_fallback = set_value(
            "dig_depth_profile_allow_live_fallback",
            bool(
                dig_depth_profile_cfg.get(
                    "allow_live_fallback",
                    dig_depth_profile_source != "prior_profile",
                )
            ),
        )
        set_value(
            "dig_depth_profile_allow_global_fallback",
            bool(dig_depth_profile_cfg.get("allow_global_fallback", True)),
        )

        return_target_planner_cfg = set_value(
            "return_target_planner_cfg",
            dict(inputs.return_target_planner or {}),
        )
        set_value(
            "return_target_planner_enabled",
            bool(return_target_planner_cfg.get("enabled", False)),
        )
        set_value(
            "return_target_hold_token_until_skill_exit",
            bool(return_target_planner_cfg.get("hold_token_until_skill_exit", True)),
        )
        set_value(
            "return_target_token_source_prefix",
            str(return_target_planner_cfg.get("token_source_prefix", "return_target")),
        )

        coverage_cfg = dict(dig_cut_planner_cfg.get("coverage", {}) or {})
        coverage_candidate_layout = set_value(
            "coverage_candidate_layout",
            str(coverage_cfg.get("candidate_layout", "percentile_grid"))
            .strip()
            .lower(),
        )
        coverage_use_env_removed_depth = set_value(
            "coverage_use_env_removed_depth",
            bool(
                coverage_cfg.get(
                    "use_env_removed_depth",
                    dig_cut_planner_mode == "operator_prior_coverage",
                )
            ),
        )
        set_value("coverage_belief_gain_scale", float(coverage_cfg.get("belief_gain_scale", 0.55)))
        set_value(
            "coverage_belief_depleted_score",
            float(coverage_cfg.get("belief_depleted_score", 1.0)),
        )
        set_value(
            "coverage_low_productivity_payload_kg",
            float(coverage_cfg.get("low_productivity_payload_kg", 15.0)),
        )
        set_value(
            "coverage_low_productivity_deposit_kg",
            float(coverage_cfg.get("low_productivity_deposit_kg", 15.0)),
        )
        set_value(
            "coverage_deplete_after_low_streak",
            max(1, int(coverage_cfg.get("deplete_after_low_streak", 2))),
        )
        coverage_min_remaining_depth_m = set_value(
            "coverage_min_remaining_depth_m",
            float(coverage_cfg.get("min_remaining_depth_m", 0.05)),
        )
        set_value(
            "coverage_global_low_productivity_stop",
            max(1, int(coverage_cfg.get("global_low_productivity_stop", 3))),
        )
        set_value(
            "coverage_max_attempts_per_corridor",
            max(1, int(coverage_cfg.get("max_attempts_per_corridor", 3))),
        )
        set_value(
            "coverage_multi_pass_enabled",
            bool(coverage_cfg.get("multi_pass_enabled", False)),
        )
        set_value(
            "coverage_multi_pass_max_passes",
            max(1, int(coverage_cfg.get("multi_pass_max_passes", 1))),
        )
        set_value(
            "coverage_multi_pass_min_remaining_depth_m",
            float(
                coverage_cfg.get(
                    "multi_pass_min_remaining_depth_m",
                    coverage_min_remaining_depth_m,
                )
            ),
        )
        set_value("coverage_unattempted_bonus", float(coverage_cfg.get("unattempted_bonus", 2.0)))
        set_value("coverage_attempt_penalty", float(coverage_cfg.get("attempt_penalty", 0.65)))
        set_value(
            "coverage_recent_selection_penalty",
            float(coverage_cfg.get("recent_selection_penalty", 1.25)),
        )
        set_value(
            "coverage_recent_row_selection_penalty",
            float(coverage_cfg.get("recent_row_selection_penalty", 0.0)),
        )
        set_value(
            "coverage_rare_cell_source_fraction_threshold",
            float(coverage_cfg.get("rare_cell_source_fraction_threshold", 0.05)),
        )
        set_value(
            "coverage_rare_cell_max_attempts",
            max(1, int(coverage_cfg.get("rare_cell_max_attempts", 1))),
        )
        set_value(
            "coverage_cell_confidence_weight",
            float(coverage_cfg.get("cell_confidence_weight", 0.75)),
        )

        state_exemplar_cfg = dict(
            coverage_cfg.get("state_conditioned_exemplars", {}) or {}
        )
        coverage_state_exemplars_enabled = set_value(
            "coverage_state_exemplars_enabled",
            bool(state_exemplar_cfg.get("enabled", False)),
        )
        coverage_state_exemplar_path = set_value(
            "coverage_state_exemplar_path",
            str(
                state_exemplar_cfg.get(
                    "path",
                    dig_cut_prior.get("coverage_state_exemplars_path", ""),
                )
            ),
        )
        coverage_state_exemplar_k = set_value(
            "coverage_state_exemplar_k",
            max(1, int(state_exemplar_cfg.get("k", 5))),
        )
        coverage_state_exemplar_removed_depth_scale_m = set_value(
            "coverage_state_exemplar_removed_depth_scale_m",
            max(1.0e-6, float(state_exemplar_cfg.get("removed_depth_scale_m", 0.12))),
        )
        coverage_state_exemplar_target_cell_weight = set_value(
            "coverage_state_exemplar_target_cell_weight",
            max(0.0, float(state_exemplar_cfg.get("target_cell_weight", 2.0))),
        )
        coverage_state_exemplar_score_weight = set_value(
            "coverage_state_exemplar_score_weight",
            float(state_exemplar_cfg.get("score_weight", 0.75)),
        )
        coverage_state_exemplar_temperature = set_value(
            "coverage_state_exemplar_temperature",
            max(1.0e-6, float(state_exemplar_cfg.get("temperature", 0.35))),
        )
        coverage_state_exemplar_skip_rejected = set_value(
            "coverage_state_exemplar_skip_rejected",
            bool(state_exemplar_cfg.get("skip_rejected", True)),
        )
        set_value(
            "coverage_state_exemplars_by_cell",
            CoverageStateExemplarPlanner(
                CoverageStateExemplarPlannerConfig(
                    enabled=coverage_state_exemplars_enabled,
                    path=coverage_state_exemplar_path,
                    dig_cut_prior_path=dig_cut_prior_path,
                    k=coverage_state_exemplar_k,
                    removed_depth_scale_m=(
                        coverage_state_exemplar_removed_depth_scale_m
                    ),
                    target_cell_weight=coverage_state_exemplar_target_cell_weight,
                    temperature=coverage_state_exemplar_temperature,
                    skip_rejected=coverage_state_exemplar_skip_rejected,
                )
            ).load_exemplars(),
        )
        set_value(
            "coverage_first_dig_strategy",
            str(coverage_cfg.get("first_dig_strategy", "coverage_score"))
            .strip()
            .lower(),
        )
        raw_first_dig_corridor = coverage_cfg.get("first_dig_preferred_corridor_id")
        set_value(
            "coverage_first_dig_preferred_corridor_id",
            None
            if raw_first_dig_corridor is None
            or str(raw_first_dig_corridor).strip().lower() in {"", "none", "null"}
            else int(raw_first_dig_corridor),
        )
        set_value(
            "coverage_first_dig_preferred_bonus",
            float(coverage_cfg.get("first_dig_preferred_bonus", 10000.0)),
        )
        set_value(
            "coverage_first_dig_proximity_weight",
            float(coverage_cfg.get("first_dig_proximity_weight", 0.0)),
        )
        set_value(
            "coverage_first_dig_max_entry_distance_m",
            optional_float(coverage_cfg.get("first_dig_max_entry_distance_m")),
        )
        set_value(
            "coverage_first_dig_qpos_delta_weight",
            float(coverage_cfg.get("first_dig_qpos_delta_weight", 0.0)),
        )
        set_value(
            "coverage_first_dig_max_qpos_delta",
            optional_align_vector(
                coverage_cfg.get("first_dig_max_qpos_delta"),
                action_dim=action_dim,
            ),
        )
        set_value(
            "coverage_entry_x_percentiles",
            coverage_percentile_list(
                coverage_cfg.get("entry_x_percentiles", ["p10", "p50", "p90"]),
                default=("p10", "p50", "p90"),
            ),
        )
        set_value(
            "coverage_entry_z_percentiles",
            coverage_percentile_list(
                coverage_cfg.get("entry_z_percentiles", ["p10", "p50", "p90"]),
                default=("p10", "p50", "p90"),
            ),
        )
        set_value(
            "coverage_cut_direction_percentile",
            coverage_percentile_name(
                coverage_cfg.get("cut_direction_percentile", "p50"),
                default="p50",
            ),
        )
        set_value(
            "coverage_cut_length_percentile",
            coverage_percentile_name(
                coverage_cfg.get("cut_length_percentile", "p50"),
                default="p50",
            ),
        )
        set_value(
            "coverage_cut_depth_percentile",
            coverage_percentile_name(
                coverage_cfg.get("cut_depth_percentile", "p50"),
                default="p50",
            ),
        )
        set_value(
            "coverage_payload_percentile",
            coverage_percentile_name(
                coverage_cfg.get("payload_percentile", "p50"),
                default="p50",
            ),
        )

        pre_dig_align_cfg = set_value(
            "pre_dig_align_cfg",
            dict(inputs.pre_dig_align or {}),
        )
        set_value(
            "pre_dig_align_enabled",
            bool(pre_dig_align_cfg.get("enabled", False)),
        )
        set_value(
            "pre_dig_align_first_dig_only",
            bool(pre_dig_align_cfg.get("first_dig_only", False)),
        )
        set_value(
            "pre_dig_align_replan_after_failed_dig",
            bool(pre_dig_align_cfg.get("replan_after_failed_dig", False)),
        )
        set_value("pre_dig_align_kp", float(pre_dig_align_cfg.get("kp", 2.0)))
        set_value("pre_dig_align_kd", float(pre_dig_align_cfg.get("kd", 0.25)))
        set_value(
            "pre_dig_align_action_clip",
            pre_dig_align_cfg.get("action_clip", [0.55, 0.35, 0.35, 0.35]),
        )
        set_value(
            "pre_dig_align_action_signs",
            np.asarray(
                pre_dig_align_cfg.get("action_signs", [1.0, -1.0, 1.0, 1.0]),
                dtype=np.float32,
            ).reshape(action_dim),
        )
        set_value(
            "pre_dig_align_controlled_dims",
            (
                np.asarray(
                    pre_dig_align_cfg.get("controlled_dims", [1, 1, 1, 0]),
                    dtype=np.float32,
                ).reshape(action_dim)
                > 0.5
            ),
        )
        raw_entry_intent_dims = pre_dig_align_cfg.get("entry_intent_controlled_dims")
        pre_dig_align_entry_intent_controlled_dims = set_value(
            "pre_dig_align_entry_intent_controlled_dims",
            None
            if raw_entry_intent_dims is None
            else (
                np.asarray(raw_entry_intent_dims, dtype=np.float32).reshape(action_dim)
                > 0.5
            ),
        )
        set_value(
            "pre_dig_align_bucket_target_qpos",
            optional_float(pre_dig_align_cfg.get("bucket_target_qpos")),
        )
        set_value(
            "pre_dig_align_qpos_tolerance",
            align_vector(
                pre_dig_align_cfg.get("qpos_tolerance", [0.025, 0.04, 0.05, 0.06]),
                default=[0.025, 0.04, 0.05, 0.06],
                action_dim=action_dim,
            ),
        )
        set_value(
            "pre_dig_align_qvel_abs_max",
            float(pre_dig_align_cfg.get("qvel_abs_max", 0.12)),
        )
        set_value(
            "pre_dig_align_hold_steps",
            max(1, int(pre_dig_align_cfg.get("hold_steps", 3))),
        )
        set_value(
            "pre_dig_align_max_steps",
            max(1, int(pre_dig_align_cfg.get("max_steps", 140))),
        )
        set_value(
            "pre_dig_align_max_entry_error_m",
            optional_float(pre_dig_align_cfg.get("max_entry_error_m")),
        )
        set_value(
            "pre_dig_align_timeout_accept_entry_error_m",
            optional_float(pre_dig_align_cfg.get("timeout_accept_entry_error_m")),
        )
        set_value(
            "pre_dig_align_timeout_replan_entry_error_m",
            optional_float(pre_dig_align_cfg.get("timeout_replan_entry_error_m")),
        )
        set_value(
            "pre_dig_align_start_envelope_enabled",
            bool(pre_dig_align_cfg.get("start_envelope_enabled", False)),
        )
        set_value(
            "pre_dig_align_first_dig_entry_close_handoff",
            bool(pre_dig_align_cfg.get("first_dig_entry_close_handoff", False)),
        )
        set_value(
            "pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max",
            optional_float(
                pre_dig_align_cfg.get("first_dig_entry_close_handoff_qvel_abs_max")
            ),
        )
        set_value(
            "pre_dig_align_start_envelope_max_entry_error_m",
            float(pre_dig_align_cfg.get("start_envelope_max_entry_error_m", 0.65)),
        )
        set_value(
            "pre_dig_align_entry_intent_handoff_enabled",
            bool(
                pre_dig_align_cfg.get(
                    "entry_intent_handoff_enabled",
                    pre_dig_align_entry_intent_controlled_dims is not None,
                )
            ),
        )
        set_value(
            "pre_dig_align_surface_guard_enabled",
            bool(pre_dig_align_cfg.get("surface_guard_enabled", False)),
        )
        set_value(
            "pre_dig_align_surface_guard_max_penetration_m",
            float(pre_dig_align_cfg.get("surface_guard_max_penetration_m", 0.005)),
        )
        set_value(
            "pre_dig_align_surface_guard_handoff_entry_error_m",
            optional_float(pre_dig_align_cfg.get("surface_guard_handoff_entry_error_m")),
        )
        set_value(
            "pre_dig_align_surface_guard_use_contact_fallback",
            bool(pre_dig_align_cfg.get("surface_guard_use_contact_fallback", True)),
        )
        set_value(
            "pre_dig_align_start_qpos_min",
            align_vector(
                pre_dig_align_cfg.get("start_qpos_min", [0.45, 0.52, 0.0, 0.0]),
                default=[0.45, 0.52, 0.0, 0.0],
                action_dim=action_dim,
            ),
        )
        set_value(
            "pre_dig_align_start_qpos_max",
            align_vector(
                pre_dig_align_cfg.get("start_qpos_max", [0.57, 0.78, 0.40, 0.12]),
                default=[0.57, 0.78, 0.40, 0.12],
                action_dim=action_dim,
            ),
        )
        set_value(
            "pre_dig_align_start_pose_min",
            np.asarray(
                pre_dig_align_cfg.get("start_pose_min", [-0.60, -0.30, -1.50]),
                dtype=np.float32,
            ).reshape(3),
        )
        set_value(
            "pre_dig_align_start_pose_max",
            np.asarray(
                pre_dig_align_cfg.get("start_pose_max", [1.65, 0.25, 1.20]),
                dtype=np.float32,
            ).reshape(3),
        )
        set_value(
            "pre_dig_align_qpos_min",
            align_vector(
                pre_dig_align_cfg.get("qpos_min", [0.44, 0.50, 0.0, 0.0]),
                default=[0.44, 0.50, 0.0, 0.0],
                action_dim=action_dim,
            ),
        )
        set_value(
            "pre_dig_align_qpos_max",
            align_vector(
                pre_dig_align_cfg.get("qpos_max", [0.56, 0.79, 0.42, 0.36]),
                default=[0.56, 0.79, 0.42, 0.36],
                action_dim=action_dim,
            ),
        )
        set_value(
            "pre_dig_align_qpos_from_token_coefficients",
            np.asarray(
                pre_dig_align_cfg.get(
                    "qpos_from_token_coefficients",
                    [
                        [0.49761536, -0.00324577, -0.07974796],
                        [0.48509995, 0.34124863, -0.02063946],
                        [0.39998216, -0.50266185, 0.04142020],
                        [0.21223230, -0.14153491, -0.01244724],
                    ],
                ),
                dtype=np.float32,
            ).reshape(action_dim, 3),
        )

        validate_dig_cut_planner_config(
            dig_cut_planner_enabled=dig_cut_planner_enabled,
            dig_cut_planner_mode=dig_cut_planner_mode,
            dig_cut_prior_path=dig_cut_prior_path,
            coverage_candidate_layout=coverage_candidate_layout,
            dig_depth_profile_source=dig_depth_profile_source,
            dig_depth_profile_required=dig_depth_profile_required,
            dig_depth_profile_allow_live_fallback=dig_depth_profile_allow_live_fallback,
            dig_cut_prior=dig_cut_prior,
        )

        set_value(
            "scripted_bootstrap_target_qpos",
            None
            if inputs.scripted_bootstrap_target_qpos is None
            else np.asarray(
                inputs.scripted_bootstrap_target_qpos,
                dtype=np.float32,
            ).reshape(action_dim),
        )
        set_value("scripted_bootstrap_kp", float(inputs.scripted_bootstrap_kp))
        set_value("scripted_bootstrap_kd", float(inputs.scripted_bootstrap_kd))
        set_value(
            "scripted_bootstrap_action_clip",
            inputs.scripted_bootstrap_action_clip,
        )
        set_value(
            "scripted_bootstrap_action_signs",
            np.ones(action_dim, dtype=np.float32)
            if inputs.scripted_bootstrap_action_signs is None
            else np.asarray(
                inputs.scripted_bootstrap_action_signs,
                dtype=np.float32,
            ).reshape(action_dim),
        )
        set_value(
            "scripted_bootstrap_qpos_tolerance",
            float(inputs.scripted_bootstrap_qpos_tolerance),
        )
        set_value(
            "scripted_bootstrap_qvel_abs_max",
            float(inputs.scripted_bootstrap_qvel_abs_max),
        )
        set_value(
            "scripted_bootstrap_hold_steps",
            max(1, int(inputs.scripted_bootstrap_hold_steps)),
        )
        set_value(
            "scripted_bootstrap_max_steps",
            max(1, int(inputs.scripted_bootstrap_max_steps)),
        )

        # Keep the normalized text value live for parity with the old shell.
        values["bootstrap_end_mode"] = bootstrap_end_mode
        values["coverage_use_env_removed_depth"] = coverage_use_env_removed_depth
        values["coverage_state_exemplar_score_weight"] = (
            coverage_state_exemplar_score_weight
        )
        return PrimitivePlannerAdapterConfigState(values)


def normalize_plane_depth_mode(value: object) -> str:
    mode = str(value or "range").strip().lower().replace("-", "_")
    aliases = {
        "legacy": "range",
        "p05_p95": "range",
        "median_floor": "p50_floor",
        "target_floor": "p50_floor",
        "median_band": "target_band",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"range", "p50_floor", "target_band"}:
        raise ValueError(
            "return_to_dig_start_envelope_plane_depth_mode must be one of "
            "'range', 'p50_floor', or 'target_band'"
        )
    return mode


def normalize_failed_dig_replan_skill(value: object) -> str:
    skill = str(value or "dig").strip().lower().replace("-", "_")
    aliases = {
        "fail": "stop",
        "fail_fast": "stop",
        "terminal": "stop",
        "terminal_stop": "stop",
        "same": "dig",
        "same_dig": "dig",
        "new_dig": "dig",
    }
    skill = aliases.get(skill, skill)
    if skill not in {"dig", "stop"}:
        raise ValueError("dig_failed_replan_next_skill must be 'dig' or 'stop'.")
    return skill


def normalize_goal_sequence(
    goal_sequence: list[str] | tuple[str, ...] | None,
) -> tuple[int, ...]:
    return GoalTokenProvider.normalize_goal_sequence(goal_sequence)


def none_or_float(value: object) -> float | None:
    return None if value is None else float(value)


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"", "none", "null"}:
        return None
    return float(value)


def align_vector(
    value: object,
    *,
    default: list[float] | tuple[float, ...],
    action_dim: int,
) -> np.ndarray:
    arr = np.asarray(default if value is None else value, dtype=np.float32)
    return arr.reshape(int(action_dim))


def optional_align_vector(value: object, *, action_dim: int) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "none", "null"}:
            return None
        value = [part.strip() for part in text.split(",") if part.strip()]
    return np.asarray(value, dtype=np.float32).reshape(int(action_dim))


def coverage_percentile_list(
    value: object,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    allowed = {"p10", "p50", "p90"}
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    else:
        items = list(default)
    cleaned = tuple(item for item in items if item in allowed)
    return cleaned or tuple(default)


def coverage_percentile_name(value: object, *, default: str) -> str:
    allowed = {"p10", "p50", "p90"}
    text = str(value).strip().lower()
    return text if text in allowed else default


def load_dig_cut_prior(path: str) -> dict[str, Any]:
    if not path:
        return {}
    prior_path = Path(path).expanduser()
    if not prior_path.is_absolute():
        prior_path = Path.cwd() / prior_path
    with prior_path.open("r", encoding="utf-8") as handle:
        prior = json.load(handle)
    if int(len(prior.get("token_order", []))) != DIG_CUT_TOKEN_DIM:
        raise ValueError(f"dig cut prior {prior_path} has invalid token_order length.")
    return dict(prior)


def validate_dig_cut_planner_config(
    *,
    dig_cut_planner_enabled: bool,
    dig_cut_planner_mode: str,
    dig_cut_prior_path: str,
    coverage_candidate_layout: str,
    dig_depth_profile_source: str,
    dig_depth_profile_required: bool,
    dig_depth_profile_allow_live_fallback: bool,
    dig_cut_prior: dict[str, Any],
) -> None:
    if not dig_cut_planner_enabled:
        return
    supported_modes = {
        "conservative_pose",
        "operator_prior",
        "operator_prior_coverage",
        "operator_prior_sweep_belief",
    }
    if dig_cut_planner_mode not in supported_modes:
        raise ValueError(
            f"Unsupported dig_cut_planner mode {dig_cut_planner_mode!r}; "
            f"expected one of {sorted(supported_modes)}."
        )
    if (
        dig_cut_planner_mode
        in {"operator_prior", "operator_prior_coverage", "operator_prior_sweep_belief"}
        and not dig_cut_prior_path
    ):
        raise ValueError(f"{dig_cut_planner_mode} dig_cut_planner requires prior_path.")
    supported_layouts = {"percentile_grid", "cell_weighted_3x2"}
    if coverage_candidate_layout not in supported_layouts:
        raise ValueError(
            "Unsupported coverage.candidate_layout "
            f"{coverage_candidate_layout!r}; expected one of "
            f"{sorted(supported_layouts)}."
        )
    supported_profile_sources = {"live_plan", "prior_profile"}
    if dig_depth_profile_source not in supported_profile_sources:
        raise ValueError(
            "Unsupported dig_depth_profile.source "
            f"{dig_depth_profile_source!r}; expected one of "
            f"{sorted(supported_profile_sources)}."
        )
    if dig_depth_profile_source == "prior_profile":
        if not dig_cut_prior_path:
            raise ValueError(
                "dig_depth_profile.source='prior_profile' requires prior_path."
            )
        if "dig_depth_profile_cells" not in dig_cut_prior:
            raise ValueError(
                "dig_depth_profile.source='prior_profile' requires "
                "dig_depth_profile_cells in the dig cut prior."
            )
        if dig_depth_profile_required and dig_depth_profile_allow_live_fallback:
            raise ValueError(
                "dig_depth_profile.required=true must set "
                "allow_live_fallback=false so missing prior profiles fail fast."
            )


__all__ = [
    "PrimitivePlannerAdapterConfigInputs",
    "PrimitivePlannerAdapterConfigNormalizer",
    "PrimitivePlannerAdapterConfigState",
    "align_vector",
    "coverage_percentile_list",
    "coverage_percentile_name",
    "load_dig_cut_prior",
    "normalize_failed_dig_replan_skill",
    "normalize_goal_sequence",
    "normalize_plane_depth_mode",
    "optional_align_vector",
    "optional_float",
    "validate_dig_cut_planner_config",
]
