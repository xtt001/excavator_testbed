"""Public adapter configuration normalization for primitive planner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.box_emptying.bottom_contact_detail import (
    validate_unity_contact_diagnostic_scope,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2,
    WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS,
    WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION,
    validate_wall_contact_session_end_clear_ticks,
    validate_wall_first_touch_mode,
    validate_wall_high_force_threshold,
)
from testbed.planner.cell_entry import (
    CellEntryPlanner,
    CellGridSpec,
    PlannerDecisionAuditor,
)
from testbed.planner.primitive.coverage.config import (
    CoverageExecutionLibraryConfig,
)
from testbed.planner.primitive.coverage.exemplars import (
    CoverageStateExemplarPlanner,
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallSafetyConfig,
)
from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
    PrimitiveFSMCapabilityProviderConfig,
)
from testbed.planner.primitive.effects.return_handoff import (
    ReturnHandoffReadinessConfig,
    ReturnStartEnvelopeGateConfig,
)
from testbed.planner.primitive.token.dig_planning import (
    DIG_CUT_PLANNER_MODES_REQUIRING_PRIOR,
    SUPPORTED_DIG_CUT_PLANNER_MODES,
)
from testbed.planner.primitive.token.tokens import GoalTokenProvider


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
    box_emptying: dict[str, Any] | None = None
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
    fsm_capability_provider_config: PrimitiveFSMCapabilityProviderConfig | None = None
    return_handoff_readiness_config: ReturnHandoffReadinessConfig | None = None

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
        if bool(inputs.cell_entry_enabled):
            raise ValueError(
                "cell_entry primitive planner runtime has been removed; "
                "set cell_entry.enabled=false or remove the block."
            )
        set_value("cell_entry_enabled", False)
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
        dig_cut_planner_fallback_mode = set_value(
            "dig_cut_planner_fallback_mode",
            str(dig_cut_planner_cfg.get("fallback_mode", "conservative_pose")),
        )
        residual_cut_intent_source_path = dig_cut_planner_cfg.get(
            "residual_cut_intent_source_path",
            "",
        )
        if residual_cut_intent_source_path is None:
            residual_cut_intent_source_path = ""
        if not isinstance(residual_cut_intent_source_path, (str, Path)):
            raise ValueError("residual_cut_intent_source_path must be a path string.")
        set_value(
            "residual_cut_intent_source_path",
            str(residual_cut_intent_source_path),
        )
        dig_cut_hold_token_until_skill_exit = set_value(
            "dig_cut_hold_token_until_skill_exit",
            bool(
                dig_cut_planner_cfg.get(
                    "hold_token_until_skill_exit",
                    dig_cut_planner_mode
                    in {
                        "operator_prior",
                        "operator_prior_coverage",
                        "operator_prior_sweep_belief",
                        "continuous_goal_conditioned",
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

        box_emptying_cfg = set_value(
            "box_emptying_cfg",
            dict(inputs.box_emptying or {}),
        )
        box_safety_cfg = dict(box_emptying_cfg.get("safety", {}) or {})
        diagnostic_ab_enabled = box_safety_cfg.get(
            "wall_contact_diagnostic_ab_enabled",
            False,
        )
        if not isinstance(diagnostic_ab_enabled, bool):
            raise ValueError(
                "box_emptying.safety."
                "wall_contact_diagnostic_ab_enabled must be a boolean."
            )
        diagnostic_observe_only_enabled = box_safety_cfg.get(
            "wall_contact_diagnostic_observe_only_enabled",
            False,
        )
        if not isinstance(diagnostic_observe_only_enabled, bool):
            raise ValueError(
                "box_emptying.safety."
                "wall_contact_diagnostic_observe_only_enabled "
                "must be a boolean."
            )
        if diagnostic_ab_enabled and diagnostic_observe_only_enabled:
            raise ValueError(
                "wall contact diagnostic markers are mutually exclusive"
            )
        unity_contact_diagnostic_enabled = box_safety_cfg.get(
            "unity_contact_diagnostic_observe_only_enabled",
            False,
        )
        wall_first_touch_mode = validate_wall_first_touch_mode(
            str(box_safety_cfg.get("wall_first_touch_mode", "interrupt"))
        )
        if (
            wall_first_touch_mode
            == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION
            and not diagnostic_ab_enabled
        ):
            raise ValueError(
                "record_bucket_first_session requires "
                "wall_contact_diagnostic_ab_enabled=true"
            )
        if (
            wall_first_touch_mode
            == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
            and not diagnostic_observe_only_enabled
        ):
            raise ValueError(
                "record_bucket_all_contacts requires "
                "wall_contact_diagnostic_observe_only_enabled=true"
            )
        if (
            diagnostic_observe_only_enabled
            and wall_first_touch_mode
            != WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
        ):
            raise ValueError(
                "observe-only diagnostic marker requires "
                "record_bucket_all_contacts mode"
            )
        validate_unity_contact_diagnostic_scope(
            enabled=unity_contact_diagnostic_enabled,
            backend=box_safety_cfg.get(
                "unity_contact_diagnostic_backend",
                "",
            ),
            wall_observe_only_enabled=diagnostic_observe_only_enabled,
            wall_first_touch_mode=wall_first_touch_mode,
            high_force_n=box_safety_cfg.get(
                "wall_high_force_n",
                100_000.0,
            ),
        )
        wall_contact_session_end_clear_ticks = (
            validate_wall_contact_session_end_clear_ticks(
                box_safety_cfg.get(
                    "wall_contact_session_end_clear_ticks",
                    1,
                )
            )
        )
        if (
            wall_contact_session_end_clear_ticks
            == WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2
            and not (
                wall_first_touch_mode
                == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION
                and diagnostic_ab_enabled
            )
        ):
            raise ValueError(
                "two-clear-tick session semantics requires diagnostic "
                "record_bucket_first_session mode"
            )
        validate_wall_high_force_threshold(
            float(box_safety_cfg.get("wall_high_force_n", 100_000.0))
        )
        box_emptying_planner_enabled = set_value(
            "box_emptying_planner_enabled",
            bool(box_emptying_cfg.get("enabled", False)),
        )
        box_emptying_safety_enabled = set_value(
            "box_emptying_safety_enabled",
            bool(
                box_emptying_cfg.get(
                    "safety_enabled",
                    box_emptying_cfg.get("enabled", False),
                )
            ),
        )
        artifact_manifest_path = box_emptying_cfg.get(
            "effect_artifact_manifest_path",
            "",
        )
        if artifact_manifest_path is None:
            artifact_manifest_path = ""
        if not isinstance(artifact_manifest_path, (str, Path)):
            raise ValueError(
                "box_emptying.effect_artifact_manifest_path must be a path string."
            )
        set_value(
            "box_emptying_artifact_manifest_path",
            str(artifact_manifest_path),
        )
        carry_start_envelope_cfg = dict(
            box_emptying_cfg.get("carry_start_envelope", {}) or {}
        )
        functional_cycle_gate_cfg = dict(
            box_emptying_cfg.get("functional_cycle_gate", {}) or {}
        )
        for gate_name, gate_config in (
            ("carry_start_envelope", carry_start_envelope_cfg),
            ("functional_cycle_gate", functional_cycle_gate_cfg),
        ):
            if bool(gate_config.get("enabled", False)) and not (
                box_emptying_safety_enabled
            ):
                raise ValueError(
                    f"box_emptying.{gate_name}.enabled=true requires "
                    "the safety interlock."
                )
        if (
            bool(functional_cycle_gate_cfg.get("enabled", False))
            and int(functional_cycle_gate_cfg.get("target_cycles", 10)) != 10
        ):
            raise ValueError(
                "act_functional_10cycle_validation_v1 requires "
                "functional_cycle_gate.target_cycles=10."
            )
        if box_emptying_planner_enabled:
            if dig_cut_planner_mode != "residual_cut_intent":
                raise ValueError(
                    "box_emptying.enabled=true requires "
                    "dig_cut_planner.mode='residual_cut_intent'."
                )
            if dig_cut_planner_fallback_mode != "error":
                raise ValueError(
                    "box_emptying.enabled=true requires "
                    "dig_cut_planner.fallback_mode='error'."
                )
            if not str(artifact_manifest_path).strip():
                raise ValueError(
                    "box_emptying.enabled=true requires "
                    "effect_artifact_manifest_path."
                )
            if not box_emptying_safety_enabled:
                raise ValueError(
                    "box_emptying.enabled=true requires the safety interlock."
                )

        return_start_envelope_cfg = dict(
            dig_cut_planner_cfg.get("return_start_envelope", {}) or {}
        )
        return_start_envelope_use_cell_prior = set_value(
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
        return_start_envelope_qpos_from_relocate_enabled = set_value(
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
        return_start_envelope_spatial_from_relocate_enabled = set_value(
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
        return_target_planner_enabled = set_value(
            "return_target_planner_enabled",
            bool(return_target_planner_cfg.get("enabled", False)),
        )
        return_target_hold_token_until_skill_exit = set_value(
            "return_target_hold_token_until_skill_exit",
            bool(return_target_planner_cfg.get("hold_token_until_skill_exit", True)),
        )
        if dig_cut_planner_mode == "continuous_goal_conditioned" and (
            not dig_cut_hold_token_until_skill_exit
            or not return_target_hold_token_until_skill_exit
        ):
            raise ValueError(
                "continuous_goal_conditioned requires dig and return "
                "hold_token_until_skill_exit=true"
            )
        if dig_cut_planner_mode == "continuous_goal_conditioned" and any(
            (
                return_start_envelope_use_cell_prior,
                return_start_envelope_qpos_from_relocate_enabled,
                return_start_envelope_spatial_from_relocate_enabled,
            )
        ):
            raise ValueError(
                "continuous_goal_conditioned forbids legacy return "
                "cell-prior and relocate-derived sources"
            )
        set_value(
            "return_target_token_source_prefix",
            str(return_target_planner_cfg.get("token_source_prefix", "return_target")),
        )

        coverage_cfg = dict(dig_cut_planner_cfg.get("coverage", {}) or {})
        coverage_wall_safety_config = set_value(
            "coverage_wall_safety_config",
            CoverageWallSafetyConfig.from_mapping(
                coverage_cfg.get("wall_safety", {})
            ),
        )
        if dig_cut_planner_mode == "continuous_goal_conditioned":
            if not coverage_wall_safety_config.enabled:
                raise ValueError(
                    "continuous_goal_conditioned requires "
                    "coverage.wall_safety.enabled=true"
                )
            if not return_target_planner_enabled:
                raise ValueError(
                    "continuous_goal_conditioned requires "
                    "return_target_planner.enabled=true"
                )
            if not values["return_to_dig_start_envelope_gate_enabled"]:
                raise ValueError(
                    "continuous_goal_conditioned requires "
                    "return_to_dig_start_envelope_gate_enabled=true"
                )
        if coverage_wall_safety_config.enabled:
            if not box_emptying_safety_enabled:
                raise ValueError(
                    "coverage.wall_safety.enabled=true requires the safety "
                    "interlock."
                )
            if dig_cut_planner_fallback_mode == "conservative_pose":
                raise ValueError(
                    "coverage.wall_safety.enabled=true forbids planner fallback."
                )
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
        coverage_execution_library_config = set_value(
            "coverage_execution_library_config",
            CoverageExecutionLibraryConfig.from_mapping(
                coverage_cfg.get("actual_tuple_execution_library")
            ),
        )
        coverage_execution_library_config.validate_for_planner_mode(
            dig_cut_planner_mode
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
            dig_cut_planner_fallback_mode=dig_cut_planner_fallback_mode,
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
        fsm_capability_provider_config = PrimitiveFSMCapabilityProviderConfig(
            action_dim=values["action_dim"],
            dig_to_carry_min_distance_to_dig_area_m=(
                values["dig_to_carry_min_distance_to_dig_area_m"]
            ),
            dig_to_carry_min_bucket_mass_kg=(
                values["dig_to_carry_min_bucket_mass_kg"]
            ),
            dig_to_carry_target_bucket_mass_kg=(
                values["dig_to_carry_target_bucket_mass_kg"]
            ),
            dig_to_carry_mass_plateau_enabled=(
                values["dig_to_carry_mass_plateau_enabled"]
            ),
            dig_to_carry_mass_plateau_min_bucket_mass_kg=(
                values["dig_to_carry_mass_plateau_min_bucket_mass_kg"]
            ),
            dig_to_carry_mass_plateau_hold_steps=(
                values["dig_to_carry_mass_plateau_hold_steps"]
            ),
            dig_to_carry_mass_plateau_min_steps=(
                values["dig_to_carry_mass_plateau_min_steps"]
            ),
            dump_ready_min_bucket_mass_kg=(
                values["dump_ready_min_bucket_mass_kg"]
            ),
            dig_bad_replan_enabled=values["dig_bad_replan_enabled"],
            dig_bad_replan_max_steps=values["dig_bad_replan_max_steps"],
            dig_bad_replan_min_bucket_mass_kg=(
                values["dig_bad_replan_min_bucket_mass_kg"]
            ),
            dig_exit_guard_enabled=values["dig_exit_guard_enabled"],
            dig_exit_guard_min_steps=values["dig_exit_guard_min_steps"],
            dig_exit_guard_min_bucket_mass_kg=(
                values["dig_exit_guard_min_bucket_mass_kg"]
            ),
            dig_exit_guard_overshoot_m=values["dig_exit_guard_overshoot_m"],
            dump_ready_hold_steps=values["dump_ready_hold_steps"],
            dump_ready_min_height_above_rim_m=(
                values["dump_ready_min_height_above_rim_m"]
            ),
            dump_ready_require_over_footprint=(
                values["dump_ready_require_over_footprint"]
            ),
            dump_ready_require_clearance=values["dump_ready_require_clearance"],
            dump_ready_max_horizontal_distance_m=(
                values["dump_ready_max_horizontal_distance_m"]
            ),
            dump_ready_position_mode=values["dump_ready_position_mode"],
            dump_ready_max_dump_area_footprint_outside_distance_m=(
                values["dump_ready_max_dump_area_footprint_outside_distance_m"]
            ),
            dump_ready_min_dump_area_relative_x_m=(
                values["dump_ready_min_dump_area_relative_x_m"]
            ),
            dump_ready_max_dump_area_relative_x_m=(
                values["dump_ready_max_dump_area_relative_x_m"]
            ),
            dump_ready_min_dump_area_relative_z_m=(
                values["dump_ready_min_dump_area_relative_z_m"]
            ),
            dump_ready_max_dump_area_relative_z_m=(
                values["dump_ready_max_dump_area_relative_z_m"]
            ),
            dump_ready_near_window_enabled=(
                values["dump_ready_near_window_enabled"]
            ),
            dump_ready_near_window_x_tolerance_m=(
                values["dump_ready_near_window_x_tolerance_m"]
            ),
            dump_ready_near_window_z_tolerance_m=(
                values["dump_ready_near_window_z_tolerance_m"]
            ),
            dump_ready_near_window_outside_tolerance_m=(
                values["dump_ready_near_window_outside_tolerance_m"]
            ),
            dump_ready_near_window_require_over_footprint=(
                values["dump_ready_near_window_require_over_footprint"]
            ),
            dump_done_max_bucket_mass_kg=values["dump_done_max_bucket_mass_kg"],
            dump_done_min_deposit_delta_kg=(
                values["dump_done_min_deposit_delta_kg"]
            ),
            dump_done_use_boundary_event=values["dump_done_use_boundary_event"],
            dump_done_hold_steps=values["dump_done_hold_steps"],
            return_to_dig_start_envelope_direct_handoff_enabled=(
                values["return_to_dig_start_envelope_direct_handoff_enabled"]
            ),
            return_to_dig_start_envelope_gate_enabled=(
                values["return_to_dig_start_envelope_gate_enabled"]
            ),
            return_to_dig_shallow_guard_enabled=(
                values["return_to_dig_shallow_guard_enabled"]
            ),
            return_to_dig_max_bucket_mass_kg=(
                values["return_to_dig_max_bucket_mass_kg"]
            ),
            return_to_dig_touch_tolerance_m=(
                values["return_to_dig_touch_tolerance_m"]
            ),
            return_to_dig_min_depth_m=values["return_to_dig_min_depth_m"],
            return_to_dig_max_depth_m=values["return_to_dig_max_depth_m"],
            return_to_dig_max_entry_error_m=(
                values["return_to_dig_max_entry_error_m"]
            ),
        )
        return_handoff_readiness_config = ReturnHandoffReadinessConfig(
            return_target_planner_enabled=values["return_target_planner_enabled"],
            max_entry_error_m=values["return_to_dig_max_entry_error_m"],
            max_bucket_mass_kg=values["return_to_dig_max_bucket_mass_kg"],
            start_envelope_direct_handoff_enabled=(
                values["return_to_dig_start_envelope_direct_handoff_enabled"]
            ),
            start_envelope_gate=ReturnStartEnvelopeGateConfig(
                enabled=values["return_to_dig_start_envelope_gate_enabled"],
                action_dim=values["action_dim"],
                spatial_tolerance=(
                    values["return_to_dig_start_envelope_spatial_tolerance"]
                ),
                depth_tolerance_m=(
                    values["return_to_dig_start_envelope_depth_tolerance_m"]
                ),
                local_depth_tolerance_m=(
                    values[
                        "return_to_dig_start_envelope_local_depth_tolerance_m"
                    ]
                ),
                plane_depth_tolerance_m=(
                    values[
                        "return_to_dig_start_envelope_plane_depth_tolerance_m"
                    ]
                ),
                plane_depth_mode=(
                    values["return_to_dig_start_envelope_plane_depth_mode"]
                ),
                qpos_tolerance=(
                    values["return_to_dig_start_envelope_qpos_tolerance"]
                ),
                require_contact=(
                    values["return_to_dig_start_envelope_require_contact"]
                ),
            ),
        )
        return PrimitivePlannerAdapterConfigState(
            values,
            fsm_capability_provider_config=fsm_capability_provider_config,
            return_handoff_readiness_config=return_handoff_readiness_config,
        )


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
    dig_cut_planner_fallback_mode: str | None = None,
    dig_cut_prior_path: str,
    coverage_candidate_layout: str,
    dig_depth_profile_source: str,
    dig_depth_profile_required: bool,
    dig_depth_profile_allow_live_fallback: bool,
    dig_cut_prior: dict[str, Any],
) -> None:
    if not dig_cut_planner_enabled:
        return
    if dig_cut_planner_mode not in SUPPORTED_DIG_CUT_PLANNER_MODES:
        raise ValueError(
            f"Unsupported dig_cut_planner mode {dig_cut_planner_mode!r}; "
            f"expected one of {sorted(SUPPORTED_DIG_CUT_PLANNER_MODES)}."
        )
    if (
        dig_cut_planner_mode == "continuous_goal_conditioned"
        and dig_cut_planner_fallback_mode != "raise"
    ):
        raise ValueError(
            "continuous_goal_conditioned requires "
            "dig_cut_planner.fallback_mode='raise'."
        )
    if (
        dig_cut_planner_mode in DIG_CUT_PLANNER_MODES_REQUIRING_PRIOR
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
