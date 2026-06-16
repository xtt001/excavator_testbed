"""Configuration helpers for primitive planner facades."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import numpy as np

from testbed.contracts.primitive_tokens import DIG_CUT_TOKEN_DIM
from testbed.planner.dig_lifecycle import (
    DIG_LIFECYCLE_CONFIG_KEYS,
    DigLifecyclePlannerConfig,
    build_dig_lifecycle_config,
    build_dig_lifecycle_config_from_mapping,
    normalize_failed_dig_replan_skill,
)
from testbed.planner.goal_sequence import (
    GOAL_SECTOR_NAME_TO_ID,
    normalize_goal_sequence as normalize_goal_sequence_values,
)
from testbed.planner.return_handoff import (
    RETURN_TO_DIG_CONFIG_KEYS,
    ReturnToDigPlannerConfig,
    build_return_to_dig_config,
    build_return_to_dig_config_from_mapping,
)
from testbed.planner.return_start_envelope import normalize_plane_depth_mode

PRIMITIVE_GOAL_SECTOR_IDS = GOAL_SECTOR_NAME_TO_ID


@dataclass(frozen=True)
class PrimitiveConditioningConfig:
    dig_cut_planner_cfg: dict[str, Any]
    dig_cut_planner_enabled: bool
    dig_cut_planner_mode: str
    dig_cut_planner_fallback_mode: str
    dig_cut_hold_token_until_skill_exit: bool
    dig_cut_prior_path: str
    dig_cut_prior: dict[str, Any]
    dig_cut_prior_id: str
    return_start_envelope_use_cell_prior: bool
    return_start_envelope_min_source_count: int
    return_start_envelope_min_source_fraction: float
    return_start_envelope_qpos_from_relocate_enabled: bool
    return_start_envelope_qpos_from_relocate_coefficients: np.ndarray | None
    return_start_envelope_qpos_from_relocate_min: np.ndarray
    return_start_envelope_qpos_from_relocate_max: np.ndarray
    return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds: bool
    return_start_envelope_spatial_from_relocate_enabled: bool
    return_start_envelope_spatial_from_relocate_coefficients: np.ndarray | None
    return_start_envelope_spatial_from_relocate_min: np.ndarray
    return_start_envelope_spatial_from_relocate_max: np.ndarray
    return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds: bool
    dig_depth_profile_source: str
    dig_depth_profile_required: bool
    dig_depth_profile_allow_live_fallback: bool
    dig_depth_profile_allow_global_fallback: bool
    return_target_planner_cfg: dict[str, Any]
    return_target_planner_enabled: bool
    return_target_hold_token_until_skill_exit: bool
    return_target_token_source_prefix: str
    coverage_candidate_layout: str
    coverage_use_env_removed_depth: bool
    coverage_belief_gain_scale: float
    coverage_belief_depleted_score: float
    coverage_low_productivity_payload_kg: float
    coverage_low_productivity_deposit_kg: float
    coverage_deplete_after_low_streak: int
    coverage_min_remaining_depth_m: float
    coverage_global_low_productivity_stop: int
    coverage_max_attempts_per_corridor: int
    coverage_multi_pass_enabled: bool
    coverage_multi_pass_max_passes: int
    coverage_multi_pass_min_remaining_depth_m: float
    coverage_unattempted_bonus: float
    coverage_attempt_penalty: float
    coverage_recent_selection_penalty: float
    coverage_recent_row_selection_penalty: float
    coverage_rare_cell_source_fraction_threshold: float
    coverage_rare_cell_max_attempts: int
    coverage_cell_confidence_weight: float
    coverage_state_exemplars_enabled: bool
    coverage_state_exemplar_path: str
    coverage_state_exemplar_k: int
    coverage_state_exemplar_removed_depth_scale_m: float
    coverage_state_exemplar_target_cell_weight: float
    coverage_state_exemplar_score_weight: float
    coverage_state_exemplar_temperature: float
    coverage_state_exemplar_skip_rejected: bool
    coverage_first_dig_strategy: str
    coverage_first_dig_preferred_corridor_id: int | None
    coverage_first_dig_preferred_bonus: float
    coverage_first_dig_proximity_weight: float
    coverage_first_dig_max_entry_distance_m: float | None
    coverage_first_dig_qpos_delta_weight: float
    coverage_first_dig_max_qpos_delta: np.ndarray | None
    coverage_entry_x_percentiles: tuple[str, ...]
    coverage_entry_z_percentiles: tuple[str, ...]
    coverage_cut_direction_percentile: str
    coverage_cut_length_percentile: str
    coverage_cut_depth_percentile: str
    coverage_payload_percentile: str

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


@dataclass(frozen=True)
class PreDigAlignmentPlannerConfig:
    pre_dig_align_cfg: dict[str, Any]
    pre_dig_align_enabled: bool
    pre_dig_align_first_dig_only: bool
    pre_dig_align_replan_after_failed_dig: bool
    pre_dig_align_kp: float
    pre_dig_align_kd: float
    pre_dig_align_action_clip: Any
    pre_dig_align_action_signs: np.ndarray
    pre_dig_align_controlled_dims: np.ndarray
    pre_dig_align_bucket_target_qpos: float | None
    pre_dig_align_qpos_tolerance: np.ndarray
    pre_dig_align_qvel_abs_max: float
    pre_dig_align_hold_steps: int
    pre_dig_align_max_steps: int
    pre_dig_align_max_entry_error_m: float | None
    pre_dig_align_timeout_accept_entry_error_m: float | None
    pre_dig_align_timeout_replan_entry_error_m: float | None
    pre_dig_align_start_envelope_enabled: bool
    pre_dig_align_first_dig_entry_close_handoff: bool
    pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max: float | None
    pre_dig_align_start_envelope_max_entry_error_m: float
    pre_dig_align_entry_intent_controlled_dims: np.ndarray | None
    pre_dig_align_entry_intent_handoff_enabled: bool
    pre_dig_align_surface_guard_enabled: bool
    pre_dig_align_surface_guard_max_penetration_m: float
    pre_dig_align_surface_guard_handoff_entry_error_m: float | None
    pre_dig_align_surface_guard_use_contact_fallback: bool
    pre_dig_align_start_qpos_min: np.ndarray
    pre_dig_align_start_qpos_max: np.ndarray
    pre_dig_align_start_pose_min: np.ndarray
    pre_dig_align_start_pose_max: np.ndarray
    pre_dig_align_qpos_min: np.ndarray
    pre_dig_align_qpos_max: np.ndarray
    pre_dig_align_qpos_from_token_coefficients: np.ndarray

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


CoveragePercentileListFn = Callable[..., tuple[str, ...]]
CoveragePercentileNameFn = Callable[..., str]


class PlannerConfigItems(Protocol):
    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        ...


def apply_planner_config_items(target: Any, config: PlannerConfigItems) -> None:
    for name, value in config.planner_items():
        setattr(target, name, value)


def build_pre_dig_alignment_config(
    *,
    pre_dig_align: dict[str, Any] | None,
    action_dim: int,
) -> PreDigAlignmentPlannerConfig:
    pre_dig_align_cfg = dict(pre_dig_align or {})
    entry_intent_controlled_dims = _pre_dig_align_entry_intent_dims(
        pre_dig_align_cfg.get("entry_intent_controlled_dims"),
        action_dim=action_dim,
    )
    return PreDigAlignmentPlannerConfig(
        pre_dig_align_cfg=pre_dig_align_cfg,
        pre_dig_align_enabled=bool(pre_dig_align_cfg.get("enabled", False)),
        pre_dig_align_first_dig_only=bool(
            pre_dig_align_cfg.get("first_dig_only", False)
        ),
        pre_dig_align_replan_after_failed_dig=bool(
            pre_dig_align_cfg.get("replan_after_failed_dig", False)
        ),
        pre_dig_align_kp=float(pre_dig_align_cfg.get("kp", 2.0)),
        pre_dig_align_kd=float(pre_dig_align_cfg.get("kd", 0.25)),
        pre_dig_align_action_clip=pre_dig_align_cfg.get(
            "action_clip",
            [0.55, 0.35, 0.35, 0.35],
        ),
        pre_dig_align_action_signs=np.asarray(
            pre_dig_align_cfg.get("action_signs", [1.0, -1.0, 1.0, 1.0]),
            dtype=np.float32,
        ).reshape(int(action_dim)),
        pre_dig_align_controlled_dims=(
            np.asarray(
                pre_dig_align_cfg.get("controlled_dims", [1, 1, 1, 0]),
                dtype=np.float32,
            ).reshape(int(action_dim))
            > 0.5
        ),
        pre_dig_align_bucket_target_qpos=optional_float(
            pre_dig_align_cfg.get("bucket_target_qpos")
        ),
        pre_dig_align_qpos_tolerance=align_vector(
            pre_dig_align_cfg.get(
                "qpos_tolerance",
                [0.025, 0.04, 0.05, 0.06],
            ),
            default=[0.025, 0.04, 0.05, 0.06],
            action_dim=action_dim,
        ),
        pre_dig_align_qvel_abs_max=float(
            pre_dig_align_cfg.get("qvel_abs_max", 0.12)
        ),
        pre_dig_align_hold_steps=max(
            1, int(pre_dig_align_cfg.get("hold_steps", 3))
        ),
        pre_dig_align_max_steps=max(1, int(pre_dig_align_cfg.get("max_steps", 140))),
        pre_dig_align_max_entry_error_m=optional_float(
            pre_dig_align_cfg.get("max_entry_error_m")
        ),
        pre_dig_align_timeout_accept_entry_error_m=optional_float(
            pre_dig_align_cfg.get("timeout_accept_entry_error_m")
        ),
        pre_dig_align_timeout_replan_entry_error_m=optional_float(
            pre_dig_align_cfg.get("timeout_replan_entry_error_m")
        ),
        pre_dig_align_start_envelope_enabled=bool(
            pre_dig_align_cfg.get("start_envelope_enabled", False)
        ),
        pre_dig_align_first_dig_entry_close_handoff=bool(
            pre_dig_align_cfg.get("first_dig_entry_close_handoff", False)
        ),
        pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max=optional_float(
            pre_dig_align_cfg.get("first_dig_entry_close_handoff_qvel_abs_max")
        ),
        pre_dig_align_start_envelope_max_entry_error_m=float(
            pre_dig_align_cfg.get("start_envelope_max_entry_error_m", 0.65)
        ),
        pre_dig_align_entry_intent_controlled_dims=entry_intent_controlled_dims,
        pre_dig_align_entry_intent_handoff_enabled=bool(
            pre_dig_align_cfg.get(
                "entry_intent_handoff_enabled",
                entry_intent_controlled_dims is not None,
            )
        ),
        pre_dig_align_surface_guard_enabled=bool(
            pre_dig_align_cfg.get("surface_guard_enabled", False)
        ),
        pre_dig_align_surface_guard_max_penetration_m=float(
            pre_dig_align_cfg.get("surface_guard_max_penetration_m", 0.005)
        ),
        pre_dig_align_surface_guard_handoff_entry_error_m=optional_float(
            pre_dig_align_cfg.get("surface_guard_handoff_entry_error_m")
        ),
        pre_dig_align_surface_guard_use_contact_fallback=bool(
            pre_dig_align_cfg.get("surface_guard_use_contact_fallback", True)
        ),
        pre_dig_align_start_qpos_min=align_vector(
            pre_dig_align_cfg.get(
                "start_qpos_min",
                [0.45, 0.52, 0.0, 0.0],
            ),
            default=[0.45, 0.52, 0.0, 0.0],
            action_dim=action_dim,
        ),
        pre_dig_align_start_qpos_max=align_vector(
            pre_dig_align_cfg.get(
                "start_qpos_max",
                [0.57, 0.78, 0.40, 0.12],
            ),
            default=[0.57, 0.78, 0.40, 0.12],
            action_dim=action_dim,
        ),
        pre_dig_align_start_pose_min=np.asarray(
            pre_dig_align_cfg.get("start_pose_min", [-0.60, -0.30, -1.50]),
            dtype=np.float32,
        ).reshape(3),
        pre_dig_align_start_pose_max=np.asarray(
            pre_dig_align_cfg.get("start_pose_max", [1.65, 0.25, 1.20]),
            dtype=np.float32,
        ).reshape(3),
        pre_dig_align_qpos_min=align_vector(
            pre_dig_align_cfg.get(
                "qpos_min",
                [0.44, 0.50, 0.0, 0.0],
            ),
            default=[0.44, 0.50, 0.0, 0.0],
            action_dim=action_dim,
        ),
        pre_dig_align_qpos_max=align_vector(
            pre_dig_align_cfg.get(
                "qpos_max",
                [0.56, 0.79, 0.42, 0.36],
            ),
            default=[0.56, 0.79, 0.42, 0.36],
            action_dim=action_dim,
        ),
        pre_dig_align_qpos_from_token_coefficients=np.asarray(
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
        ).reshape(int(action_dim), 3),
    )


def build_conditioning_config(
    *,
    dig_cut_planner: dict[str, Any] | None,
    return_target_planner: dict[str, Any] | None,
    action_dim: int,
    coverage_percentile_list_fn: CoveragePercentileListFn,
    coverage_percentile_name_fn: CoveragePercentileNameFn,
) -> PrimitiveConditioningConfig:
    dig_cut_planner_cfg = dict(dig_cut_planner or {})
    dig_cut_planner_enabled = bool(dig_cut_planner_cfg.get("enabled", True))
    dig_cut_planner_mode = str(
        dig_cut_planner_cfg.get("mode", "conservative_pose")
    )
    dig_cut_planner_fallback_mode = str(
        dig_cut_planner_cfg.get("fallback_mode", "conservative_pose")
    )
    dig_cut_hold_token_until_skill_exit = bool(
        dig_cut_planner_cfg.get(
            "hold_token_until_skill_exit",
            dig_cut_planner_mode
            in {
                "operator_prior",
                "operator_prior_coverage",
                "operator_prior_sweep_belief",
            },
        )
    )
    dig_cut_prior_path = str(dig_cut_planner_cfg.get("prior_path", ""))
    dig_cut_prior = load_dig_cut_prior(dig_cut_prior_path)
    dig_cut_prior_id = str(dig_cut_prior.get("prior_id", ""))

    return_start_envelope_cfg = dict(
        dig_cut_planner_cfg.get("return_start_envelope", {}) or {}
    )
    qpos_from_relocate_cfg = dict(
        return_start_envelope_cfg.get("qpos_from_relocate", {}) or {}
    )
    raw_relocate_coefficients = qpos_from_relocate_cfg.get("coefficients")
    spatial_from_relocate_cfg = dict(
        return_start_envelope_cfg.get("spatial_from_relocate", {}) or {}
    )
    raw_spatial_coefficients = spatial_from_relocate_cfg.get("coefficients")

    dig_depth_profile_cfg = dict(
        dig_cut_planner_cfg.get("dig_depth_profile", {}) or {}
    )
    dig_depth_profile_source = str(
        dig_depth_profile_cfg.get("source", "live_plan")
    ).strip().lower()
    dig_depth_profile_required = bool(
        dig_depth_profile_cfg.get("required", False)
    )

    return_target_planner_cfg = dict(return_target_planner or {})
    coverage_cfg = dict(dig_cut_planner_cfg.get("coverage", {}) or {})
    coverage_candidate_layout = str(
        coverage_cfg.get("candidate_layout", "percentile_grid")
    ).strip().lower()
    coverage_use_env_removed_depth = bool(
        coverage_cfg.get(
            "use_env_removed_depth",
            dig_cut_planner_mode == "operator_prior_coverage",
        )
    )
    coverage_min_remaining_depth_m = float(
        coverage_cfg.get("min_remaining_depth_m", 0.05)
    )
    state_exemplar_cfg = dict(
        coverage_cfg.get("state_conditioned_exemplars", {}) or {}
    )
    coverage_state_exemplars_enabled = bool(
        state_exemplar_cfg.get("enabled", False)
    )
    coverage_state_exemplar_path = str(
        state_exemplar_cfg.get(
            "path",
            dig_cut_prior.get("coverage_state_exemplars_path", ""),
        )
    )
    raw_first_dig_corridor = coverage_cfg.get("first_dig_preferred_corridor_id")

    return PrimitiveConditioningConfig(
        dig_cut_planner_cfg=dig_cut_planner_cfg,
        dig_cut_planner_enabled=dig_cut_planner_enabled,
        dig_cut_planner_mode=dig_cut_planner_mode,
        dig_cut_planner_fallback_mode=dig_cut_planner_fallback_mode,
        dig_cut_hold_token_until_skill_exit=dig_cut_hold_token_until_skill_exit,
        dig_cut_prior_path=dig_cut_prior_path,
        dig_cut_prior=dig_cut_prior,
        dig_cut_prior_id=dig_cut_prior_id,
        return_start_envelope_use_cell_prior=bool(
            return_start_envelope_cfg.get("use_cell_prior", False)
        ),
        return_start_envelope_min_source_count=max(
            1, int(return_start_envelope_cfg.get("min_source_count", 1))
        ),
        return_start_envelope_min_source_fraction=max(
            0.0,
            float(return_start_envelope_cfg.get("min_source_fraction", 0.0)),
        ),
        return_start_envelope_qpos_from_relocate_enabled=bool(
            qpos_from_relocate_cfg.get("enabled", False)
        ),
        return_start_envelope_qpos_from_relocate_coefficients=(
            None
            if raw_relocate_coefficients is None
            else np.asarray(raw_relocate_coefficients, dtype=np.float32).reshape(
                4,
                8,
            )
        ),
        return_start_envelope_qpos_from_relocate_min=align_vector(
            qpos_from_relocate_cfg.get("qpos_min", [0.44, 0.50, 0.0, 0.0]),
            default=[0.44, 0.50, 0.0, 0.0],
            action_dim=action_dim,
        ),
        return_start_envelope_qpos_from_relocate_max=align_vector(
            qpos_from_relocate_cfg.get("qpos_max", [0.56, 0.80, 0.56, 0.48]),
            default=[0.56, 0.80, 0.56, 0.48],
            action_dim=action_dim,
        ),
        return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds=bool(
            qpos_from_relocate_cfg.get("use_prior_qpos_bounds", False)
        ),
        return_start_envelope_spatial_from_relocate_enabled=bool(
            spatial_from_relocate_cfg.get("enabled", False)
        ),
        return_start_envelope_spatial_from_relocate_coefficients=(
            None
            if raw_spatial_coefficients is None
            else np.asarray(raw_spatial_coefficients, dtype=np.float32).reshape(
                2,
                8,
            )
        ),
        return_start_envelope_spatial_from_relocate_min=np.asarray(
            spatial_from_relocate_cfg.get("spatial_min", [-1.0, -0.10]),
            dtype=np.float32,
        ).reshape(2),
        return_start_envelope_spatial_from_relocate_max=np.asarray(
            spatial_from_relocate_cfg.get("spatial_max", [1.0, 1.0]),
            dtype=np.float32,
        ).reshape(2),
        return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds=bool(
            spatial_from_relocate_cfg.get("use_prior_spatial_bounds", False)
        ),
        dig_depth_profile_source=dig_depth_profile_source,
        dig_depth_profile_required=dig_depth_profile_required,
        dig_depth_profile_allow_live_fallback=bool(
            dig_depth_profile_cfg.get(
                "allow_live_fallback",
                dig_depth_profile_source != "prior_profile",
            )
        ),
        dig_depth_profile_allow_global_fallback=bool(
            dig_depth_profile_cfg.get("allow_global_fallback", True)
        ),
        return_target_planner_cfg=return_target_planner_cfg,
        return_target_planner_enabled=bool(
            return_target_planner_cfg.get("enabled", False)
        ),
        return_target_hold_token_until_skill_exit=bool(
            return_target_planner_cfg.get("hold_token_until_skill_exit", True)
        ),
        return_target_token_source_prefix=str(
            return_target_planner_cfg.get("token_source_prefix", "return_target")
        ),
        coverage_candidate_layout=coverage_candidate_layout,
        coverage_use_env_removed_depth=coverage_use_env_removed_depth,
        coverage_belief_gain_scale=float(
            coverage_cfg.get("belief_gain_scale", 0.55)
        ),
        coverage_belief_depleted_score=float(
            coverage_cfg.get("belief_depleted_score", 1.0)
        ),
        coverage_low_productivity_payload_kg=float(
            coverage_cfg.get("low_productivity_payload_kg", 15.0)
        ),
        coverage_low_productivity_deposit_kg=float(
            coverage_cfg.get("low_productivity_deposit_kg", 15.0)
        ),
        coverage_deplete_after_low_streak=max(
            1, int(coverage_cfg.get("deplete_after_low_streak", 2))
        ),
        coverage_min_remaining_depth_m=coverage_min_remaining_depth_m,
        coverage_global_low_productivity_stop=max(
            1, int(coverage_cfg.get("global_low_productivity_stop", 3))
        ),
        coverage_max_attempts_per_corridor=max(
            1, int(coverage_cfg.get("max_attempts_per_corridor", 3))
        ),
        coverage_multi_pass_enabled=bool(
            coverage_cfg.get("multi_pass_enabled", False)
        ),
        coverage_multi_pass_max_passes=max(
            1, int(coverage_cfg.get("multi_pass_max_passes", 1))
        ),
        coverage_multi_pass_min_remaining_depth_m=float(
            coverage_cfg.get(
                "multi_pass_min_remaining_depth_m",
                coverage_min_remaining_depth_m,
            )
        ),
        coverage_unattempted_bonus=float(
            coverage_cfg.get("unattempted_bonus", 2.0)
        ),
        coverage_attempt_penalty=float(coverage_cfg.get("attempt_penalty", 0.65)),
        coverage_recent_selection_penalty=float(
            coverage_cfg.get("recent_selection_penalty", 1.25)
        ),
        coverage_recent_row_selection_penalty=float(
            coverage_cfg.get("recent_row_selection_penalty", 0.0)
        ),
        coverage_rare_cell_source_fraction_threshold=float(
            coverage_cfg.get("rare_cell_source_fraction_threshold", 0.05)
        ),
        coverage_rare_cell_max_attempts=max(
            1, int(coverage_cfg.get("rare_cell_max_attempts", 1))
        ),
        coverage_cell_confidence_weight=float(
            coverage_cfg.get("cell_confidence_weight", 0.75)
        ),
        coverage_state_exemplars_enabled=coverage_state_exemplars_enabled,
        coverage_state_exemplar_path=coverage_state_exemplar_path,
        coverage_state_exemplar_k=max(1, int(state_exemplar_cfg.get("k", 5))),
        coverage_state_exemplar_removed_depth_scale_m=max(
            1.0e-6,
            float(state_exemplar_cfg.get("removed_depth_scale_m", 0.12)),
        ),
        coverage_state_exemplar_target_cell_weight=max(
            0.0,
            float(state_exemplar_cfg.get("target_cell_weight", 2.0)),
        ),
        coverage_state_exemplar_score_weight=float(
            state_exemplar_cfg.get("score_weight", 0.75)
        ),
        coverage_state_exemplar_temperature=max(
            1.0e-6,
            float(state_exemplar_cfg.get("temperature", 0.35)),
        ),
        coverage_state_exemplar_skip_rejected=bool(
            state_exemplar_cfg.get("skip_rejected", True)
        ),
        coverage_first_dig_strategy=str(
            coverage_cfg.get("first_dig_strategy", "coverage_score")
        ).strip().lower(),
        coverage_first_dig_preferred_corridor_id=(
            None
            if raw_first_dig_corridor is None
            or str(raw_first_dig_corridor).strip().lower() in {"", "none", "null"}
            else int(raw_first_dig_corridor)
        ),
        coverage_first_dig_preferred_bonus=float(
            coverage_cfg.get("first_dig_preferred_bonus", 10000.0)
        ),
        coverage_first_dig_proximity_weight=float(
            coverage_cfg.get("first_dig_proximity_weight", 0.0)
        ),
        coverage_first_dig_max_entry_distance_m=optional_float(
            coverage_cfg.get("first_dig_max_entry_distance_m")
        ),
        coverage_first_dig_qpos_delta_weight=float(
            coverage_cfg.get("first_dig_qpos_delta_weight", 0.0)
        ),
        coverage_first_dig_max_qpos_delta=optional_align_vector(
            coverage_cfg.get("first_dig_max_qpos_delta"),
            action_dim=action_dim,
        ),
        coverage_entry_x_percentiles=coverage_percentile_list_fn(
            coverage_cfg.get("entry_x_percentiles", ["p10", "p50", "p90"]),
            default=("p10", "p50", "p90"),
        ),
        coverage_entry_z_percentiles=coverage_percentile_list_fn(
            coverage_cfg.get("entry_z_percentiles", ["p10", "p50", "p90"]),
            default=("p10", "p50", "p90"),
        ),
        coverage_cut_direction_percentile=coverage_percentile_name_fn(
            coverage_cfg.get("cut_direction_percentile", "p50"),
            default="p50",
        ),
        coverage_cut_length_percentile=coverage_percentile_name_fn(
            coverage_cfg.get("cut_length_percentile", "p50"),
            default="p50",
        ),
        coverage_cut_depth_percentile=coverage_percentile_name_fn(
            coverage_cfg.get("cut_depth_percentile", "p50"),
            default="p50",
        ),
        coverage_payload_percentile=coverage_percentile_name_fn(
            coverage_cfg.get("payload_percentile", "p50"),
            default="p50",
        ),
    )


def _pre_dig_align_entry_intent_dims(
    value: object,
    *,
    action_dim: int,
) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32).reshape(int(action_dim)) > 0.5


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


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"", "none", "null"}:
        return None
    return float(value)


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
    dig_cut_prior: dict[str, Any],
    dig_depth_profile_required: bool,
    dig_depth_profile_allow_live_fallback: bool,
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
            raise ValueError("dig_depth_profile.source='prior_profile' requires prior_path.")
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


def normalize_goal_sequence(
    goal_sequence: list[object] | tuple[object, ...] | None,
) -> tuple[int, ...]:
    return normalize_goal_sequence_values(goal_sequence)
