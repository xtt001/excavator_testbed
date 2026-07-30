"""Static coverage configuration owned by the coverage lane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.effects import (
    CoverageRuntimeConfig,
    CoverageUpdateConfig,
)
from testbed.planner.primitive.coverage.exemplars import (
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive.coverage.facts import CoveragePlanningFactConfig
from testbed.planner.primitive.coverage.reports import CoverageReportConfig
from testbed.planner.primitive.coverage.selection import CoverageSelectionConfig
from testbed.planner.primitive.coverage.start_reachability import (
    CoverageTupleStartReachabilityConfig,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallSafetyConfig,
)
from testbed.planner.primitive.coverage.worktool_sweep import (
    CoverageWorktoolSweepConfig,
)


@dataclass(frozen=True)
class CoverageFirstPlanPoseStabilityConfig:
    """Readiness gate for discontinuous worktool-corner observations."""

    enabled: bool = False
    hold_steps: int = 3
    max_step_delta_m: float = 0.05
    max_wait_steps: int = 30

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> CoverageFirstPlanPoseStabilityConfig:
        mapping = dict(values or {})
        config = cls(
            enabled=bool(mapping.get("enabled", False)),
            hold_steps=int(mapping.get("hold_steps", 3)),
            max_step_delta_m=float(
                mapping.get("max_step_delta_m", 0.05)
            ),
            max_wait_steps=int(mapping.get("max_wait_steps", 30)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if int(self.hold_steps) <= 0:
            raise ValueError(
                "coverage.actual_tuple_execution_library."
                "first_plan_pose_stability.hold_steps must be positive."
            )
        if (
            not np.isfinite(float(self.max_step_delta_m))
            or float(self.max_step_delta_m) <= 0.0
        ):
            raise ValueError(
                "coverage.actual_tuple_execution_library."
                "first_plan_pose_stability.max_step_delta_m "
                "must be finite and positive."
            )
        if int(self.max_wait_steps) < int(self.hold_steps):
            raise ValueError(
                "coverage.actual_tuple_execution_library."
                "first_plan_pose_stability.max_wait_steps "
                "must be at least hold_steps."
            )


@dataclass(frozen=True)
class CoverageExecutionLibraryConfig:
    """Fail-closed runtime contract for exact expert coverage tuples."""

    enabled: bool = False
    runtime_role: str = "diagnostic_legacy"
    path: str = ""
    artifact_sha256: str = ""
    mode: str = "exact_k1"
    missing_contract: str = "fail_closed"
    hard_bottom_margin_m: float = 0.02
    first_plan_pose_stability: CoverageFirstPlanPoseStabilityConfig = field(
        default_factory=CoverageFirstPlanPoseStabilityConfig
    )
    worktool_sweep_3d: CoverageWorktoolSweepConfig = field(
        default_factory=CoverageWorktoolSweepConfig
    )
    start_reachability: CoverageTupleStartReachabilityConfig = field(
        default_factory=CoverageTupleStartReachabilityConfig
    )

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> CoverageExecutionLibraryConfig:
        mapping = dict(values or {})
        config = cls(
            enabled=bool(mapping.get("enabled", False)),
            runtime_role=str(
                mapping.get("runtime_role", "diagnostic_legacy")
            ).strip(),
            path=str(mapping.get("path", "")).strip(),
            artifact_sha256=str(
                mapping.get("artifact_sha256", "")
            ).strip().lower(),
            mode=str(mapping.get("mode", "exact_k1")).strip(),
            missing_contract=str(
                mapping.get("missing_contract", "fail_closed")
            ).strip(),
            hard_bottom_margin_m=float(
                mapping.get("hard_bottom_margin_m", 0.02)
            ),
            first_plan_pose_stability=(
                CoverageFirstPlanPoseStabilityConfig.from_mapping(
                    mapping.get("first_plan_pose_stability")
                )
            ),
            worktool_sweep_3d=CoverageWorktoolSweepConfig.from_mapping(
                mapping.get("worktool_sweep_3d")
            ),
            start_reachability=(
                CoverageTupleStartReachabilityConfig.from_mapping(
                    mapping.get("start_reachability")
                )
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.runtime_role != "diagnostic_legacy":
            raise ValueError(
                "coverage.actual_tuple_execution_library.runtime_role "
                "must be 'diagnostic_legacy'."
            )
        if self.mode != "exact_k1":
            raise ValueError(
                "coverage.actual_tuple_execution_library.mode must be 'exact_k1'."
            )
        if self.missing_contract != "fail_closed":
            raise ValueError(
                "coverage.actual_tuple_execution_library.missing_contract "
                "must be 'fail_closed'."
            )
        if (
            not np.isfinite(float(self.hard_bottom_margin_m))
            or float(self.hard_bottom_margin_m) < 0.0
        ):
            raise ValueError(
                "coverage.actual_tuple_execution_library."
                "hard_bottom_margin_m must be finite and non-negative."
            )
        if not self.enabled:
            if (
                self.worktool_sweep_3d.enabled
                or self.start_reachability.enabled
            ):
                raise ValueError(
                    "coverage.actual_tuple_execution_library "
                    "companion gates require the execution library"
                )
            return
        if not self.path:
            raise ValueError(
                "coverage.actual_tuple_execution_library.enabled=true "
                "requires path."
            )
        if not self.artifact_sha256:
            raise ValueError(
                "coverage.actual_tuple_execution_library.enabled=true "
                "requires artifact_sha256."
            )
        if len(self.artifact_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.artifact_sha256
        ):
            raise ValueError(
                "coverage.actual_tuple_execution_library.artifact_sha256 "
                "must be a lowercase SHA256 hex digest."
            )
        if (
            self.worktool_sweep_3d.enabled
            and self.worktool_sweep_3d.execution_library_sha256
            != self.artifact_sha256
        ):
            raise ValueError(
                "coverage.actual_tuple_execution_library.worktool_sweep_3d."
                "execution_library_sha256 must match artifact_sha256."
            )
        if (
            self.start_reachability.enabled
            and self.start_reachability.execution_library_sha256
            != self.artifact_sha256
        ):
            raise ValueError(
                "coverage.actual_tuple_execution_library.start_reachability."
                "execution_library_sha256 must match artifact_sha256."
            )

    def validate_for_planner_mode(self, planner_mode: str) -> None:
        """Keep the diagnostic exact-tuple library outside continuous runtime."""

        if (
            self.enabled
            and str(planner_mode) == "continuous_goal_conditioned"
        ):
            raise ValueError(
                "continuous_goal_conditioned cannot enable the diagnostic "
                "exact-tuple execution library"
            )


@dataclass(frozen=True)
class PrimitiveCoverageStaticConfig:
    """Static coverage config snapshot used by coverage runtimes."""

    dig_cut_prior: dict[str, object]
    dig_cut_prior_path: str
    dig_cut_planner_mode: str
    action_dim: int

    candidate_layout: str
    entry_x_percentiles: tuple[str, ...]
    entry_z_percentiles: tuple[str, ...]
    cut_direction_percentile: str
    cut_length_percentile: str
    cut_depth_percentile: str
    payload_percentile: str

    use_env_removed_depth: bool
    max_attempts_per_corridor: int
    recent_selection_penalty: float
    unattempted_bonus: float
    attempt_penalty: float
    cell_confidence_weight: float
    rare_cell_source_fraction_threshold: float
    rare_cell_max_attempts: int
    recent_row_selection_penalty: float

    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_preferred_bonus: float
    first_dig_proximity_weight: float
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    first_dig_max_qpos_delta: np.ndarray | None
    pre_dig_align_controlled_dims: np.ndarray

    state_exemplars_enabled: bool
    state_exemplar_path: str
    state_exemplar_k: int
    state_exemplar_removed_depth_scale_m: float
    state_exemplar_target_cell_weight: float
    state_exemplar_temperature: float
    state_exemplar_skip_rejected: bool
    state_exemplar_score_weight: float
    state_exemplars_by_cell: dict[int, list[dict[str, object]]]

    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float

    low_productivity_payload_kg: float
    low_productivity_deposit_kg: float
    deplete_after_low_streak: int
    min_remaining_depth_m: float
    belief_depleted_score: float
    belief_gain_scale: float
    global_low_productivity_stop: int
    wall_safety: CoverageWallSafetyConfig = field(
        default_factory=CoverageWallSafetyConfig
    )
    execution_library: CoverageExecutionLibraryConfig = field(
        default_factory=CoverageExecutionLibraryConfig
    )

    @property
    def prior_fields(self) -> dict[str, object]:
        fields = self.dig_cut_prior.get("fields", {})
        if not isinstance(fields, dict):
            return {}
        return dict(fields)

    def report_config(self) -> CoverageReportConfig:
        return CoverageReportConfig(
            state_exemplar_enabled=bool(self.state_exemplars_enabled),
            multi_pass_enabled=bool(self.multi_pass_enabled),
            multi_pass_max_passes=int(self.multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.multi_pass_min_remaining_depth_m
            ),
            use_env_removed_depth=bool(self.use_env_removed_depth),
            candidate_layout=str(self.candidate_layout),
            first_dig_strategy=str(self.first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.first_dig_preferred_corridor_id is None
                else int(self.first_dig_preferred_corridor_id)
            ),
            first_dig_max_entry_distance_m=self.first_dig_max_entry_distance_m,
            first_dig_qpos_delta_weight=float(self.first_dig_qpos_delta_weight),
            first_dig_max_qpos_delta=self.first_dig_max_qpos_delta,
        )

    def selection_config(
        self,
        state: CoverageRuntimeState,
        *,
        cycle_index: int,
    ) -> CoverageSelectionConfig:
        max_qpos_delta = self.first_dig_max_qpos_delta
        last_selected_outcome_id = int(
            state.coverage_last_selected_effect_outcome_cell_id
        )
        return CoverageSelectionConfig(
            candidate_layout=str(self.candidate_layout),
            prior_fields=self.prior_fields,
            cut_depth_percentile=str(self.cut_depth_percentile),
            use_env_removed_depth=bool(self.use_env_removed_depth),
            max_attempts_per_corridor=int(self.max_attempts_per_corridor),
            recent_selection_penalty=float(self.recent_selection_penalty),
            unattempted_bonus=float(self.unattempted_bonus),
            attempt_penalty=float(self.attempt_penalty),
            cell_confidence_weight=float(self.cell_confidence_weight),
            rare_cell_source_fraction_threshold=float(
                self.rare_cell_source_fraction_threshold
            ),
            rare_cell_max_attempts=int(self.rare_cell_max_attempts),
            recent_row_selection_penalty=float(self.recent_row_selection_penalty),
            last_selected_corridor_id=(
                last_selected_outcome_id
                if last_selected_outcome_id >= 0
                else int(state.coverage_last_selected_corridor_id)
            ),
            cycle_index=int(cycle_index),
            completed_dump_count=int(state.coverage_completed_dump_count),
            first_dig_strategy=str(self.first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.first_dig_preferred_corridor_id is None
                else int(self.first_dig_preferred_corridor_id)
            ),
            first_dig_preferred_bonus=float(self.first_dig_preferred_bonus),
            first_dig_proximity_weight=float(self.first_dig_proximity_weight),
            first_dig_max_entry_distance_m=(
                None
                if self.first_dig_max_entry_distance_m is None
                else float(self.first_dig_max_entry_distance_m)
            ),
            first_dig_qpos_delta_weight=float(self.first_dig_qpos_delta_weight),
            first_dig_max_qpos_delta=(
                None
                if max_qpos_delta is None
                else np.asarray(max_qpos_delta, dtype=np.float32).copy()
            ),
            pre_dig_align_controlled_dims=np.asarray(
                self.pre_dig_align_controlled_dims,
                dtype=bool,
            ).copy(),
            state_exemplars_enabled=bool(self.state_exemplars_enabled),
            state_exemplar_score_weight=float(self.state_exemplar_score_weight),
            wall_safety=self.wall_safety,
        )

    def planning_fact_config(self) -> CoveragePlanningFactConfig:
        return CoveragePlanningFactConfig(
            prior_fields=self.prior_fields,
            cut_direction_percentile=str(self.cut_direction_percentile),
            cut_length_percentile=str(self.cut_length_percentile),
            cut_depth_percentile=str(self.cut_depth_percentile),
            payload_percentile=str(self.payload_percentile),
            wall_safety=self.wall_safety,
        )

    def state_exemplar_planner_config(self) -> CoverageStateExemplarPlannerConfig:
        return CoverageStateExemplarPlannerConfig(
            enabled=bool(self.state_exemplars_enabled),
            path=str(self.state_exemplar_path),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            k=int(self.state_exemplar_k),
            removed_depth_scale_m=float(self.state_exemplar_removed_depth_scale_m),
            target_cell_weight=float(self.state_exemplar_target_cell_weight),
            temperature=float(self.state_exemplar_temperature),
            skip_rejected=bool(self.state_exemplar_skip_rejected),
        )

    def update_config(self) -> CoverageUpdateConfig:
        return CoverageUpdateConfig(
            prior_fields=self.prior_fields,
            use_env_removed_depth=bool(self.use_env_removed_depth),
            low_productivity_payload_kg=float(self.low_productivity_payload_kg),
            low_productivity_deposit_kg=float(self.low_productivity_deposit_kg),
            deplete_after_low_streak=int(self.deplete_after_low_streak),
            min_remaining_depth_m=float(self.min_remaining_depth_m),
            belief_depleted_score=float(self.belief_depleted_score),
            belief_gain_scale=float(self.belief_gain_scale),
        )

    def runtime_config(self) -> CoverageRuntimeConfig:
        return CoverageRuntimeConfig(
            multi_pass_enabled=bool(self.multi_pass_enabled),
            use_env_removed_depth=bool(self.use_env_removed_depth),
            multi_pass_max_passes=int(self.multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.multi_pass_min_remaining_depth_m
            ),
        )


__all__ = [
    "CoverageExecutionLibraryConfig",
    "PrimitiveCoverageStaticConfig",
]
