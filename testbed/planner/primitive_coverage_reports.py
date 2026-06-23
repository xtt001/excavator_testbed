"""Coverage reporting payload builders for primitive planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage import (
    CoverageCorridorState,
    CoverageSelectionService,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState


@dataclass(frozen=True)
class CoverageDebugReportInputs:
    active_corridor_id: int
    last_selected_corridor_id: int
    last_selected_cell_id: int
    last_selected_row_id: int
    active_corridor: dict[str, Any] | None
    active_cell_id: int
    active_score: float
    state_exemplar_enabled: bool
    state_exemplar_ids: list[str]
    state_exemplar_distance: float
    depleted_count: int
    pass_index: int
    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float
    last_payload_gain_kg: float
    last_effective_deposit_delta_kg: float
    global_low_productivity_streak: int
    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    first_dig_max_qpos_delta: Any | None
    terminal_stop_requested: bool
    terminal_stop_reason: str
    corridors: list[dict[str, Any]]
    candidate_scores: list[dict[str, Any]]


@dataclass(frozen=True)
class CoverageReportConfig:
    state_exemplar_enabled: bool
    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float
    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    first_dig_max_qpos_delta: Any | None


@dataclass(frozen=True)
class CoverageTraceReportStatus:
    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    pass_index: int
    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float
    first_dig_preferred_corridor_id: int | None
    corridors: list[Any]
    decision_trace: list[Any]
    terminal_stop_requested: bool
    terminal_stop_reason: str


@dataclass(frozen=True)
class CoverageSummaryReportStatus:
    selected_corridor_id: int
    depleted_count: int
    completed_dump_count: int
    pass_index: int
    multi_pass_enabled: bool
    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    terminal_stop_requested: bool
    terminal_stop_reason: str


@dataclass(frozen=True)
class CoverageReportState:
    cycle_index: int
    skill_name: str
    active_corridor_id: int
    last_selected_corridor_id: int
    last_selected_cell_id: int
    last_selected_row_id: int
    depleted_count: int
    pass_index: int
    global_low_productivity_streak: int
    terminal_stop_requested: bool
    terminal_stop_reason: str


@dataclass(frozen=True)
class CoverageBucketSnapshot:
    mass_kg: float
    deposited_mass_kg: float
    dig_area_x_m: float
    dig_area_y_m: float
    dig_area_z_m: float
    long_norm: float
    short_norm: float
    plane_depth_m: float
    local_depth_m: float


class CoverageReportService:
    """Build coverage debug and trace payloads from explicit state snapshots."""

    def debug_fields_from_state(
        self,
        state: CoverageRuntimeState,
        *,
        config: CoverageReportConfig,
        selection_service: CoverageSelectionService,
    ) -> dict[str, Any]:
        active_corridor = state.active_corridor()
        last_selected_corridor = state.corridor_by_id(
            state.coverage_last_selected_corridor_id
        )
        return self.debug_fields(
            CoverageDebugReportInputs(
                active_corridor_id=int(state.coverage_active_corridor_id),
                last_selected_corridor_id=int(
                    state.coverage_last_selected_corridor_id
                ),
                last_selected_cell_id=(
                    -1
                    if last_selected_corridor is None
                    else int(selection_service.cell_id(last_selected_corridor))
                ),
                last_selected_row_id=(
                    -1
                    if last_selected_corridor is None
                    else int(selection_service.corridor_row_id(last_selected_corridor))
                ),
                active_corridor=(
                    None
                    if active_corridor is None
                    else self.corridor_to_debug(
                        active_corridor,
                        attempt_limit=selection_service.corridor_attempt_limit(
                            active_corridor
                        ),
                        cell_confidence=selection_service.cell_confidence(
                            active_corridor
                        ),
                    )
                ),
                active_cell_id=(
                    -1
                    if active_corridor is None
                    else int(selection_service.cell_id(active_corridor))
                ),
                active_score=(
                    float("nan")
                    if active_corridor is None
                    else float(active_corridor.score)
                ),
                state_exemplar_enabled=bool(config.state_exemplar_enabled),
                state_exemplar_ids=list(state.coverage_active_state_exemplar_ids),
                state_exemplar_distance=float(
                    state.coverage_active_state_exemplar_distance
                ),
                depleted_count=int(state.depleted_count()),
                pass_index=int(state.coverage_pass_index),
                multi_pass_enabled=bool(config.multi_pass_enabled),
                multi_pass_max_passes=int(config.multi_pass_max_passes),
                multi_pass_min_remaining_depth_m=float(
                    config.multi_pass_min_remaining_depth_m
                ),
                last_payload_gain_kg=float(state.coverage_last_payload_gain_kg),
                last_effective_deposit_delta_kg=float(
                    state.coverage_last_effective_deposit_delta_kg
                ),
                global_low_productivity_streak=int(
                    state.coverage_global_low_productivity_streak
                ),
                use_env_removed_depth=bool(config.use_env_removed_depth),
                candidate_layout=str(config.candidate_layout),
                first_dig_strategy=str(config.first_dig_strategy),
                first_dig_preferred_corridor_id=(
                    config.first_dig_preferred_corridor_id
                ),
                first_dig_max_entry_distance_m=(
                    config.first_dig_max_entry_distance_m
                ),
                first_dig_qpos_delta_weight=float(
                    config.first_dig_qpos_delta_weight
                ),
                first_dig_max_qpos_delta=config.first_dig_max_qpos_delta,
                terminal_stop_requested=bool(
                    state.coverage_terminal_stop_requested
                ),
                terminal_stop_reason=str(state.coverage_terminal_stop_reason),
                corridors=[
                    self.corridor_to_debug(
                        corridor,
                        attempt_limit=selection_service.corridor_attempt_limit(
                            corridor
                        ),
                        cell_confidence=selection_service.cell_confidence(corridor),
                    )
                    for corridor in state.coverage_corridors
                ],
                candidate_scores=list(state.coverage_candidate_scores),
            )
        )

    def summary_status_from_state(
        self,
        state: CoverageRuntimeState,
        *,
        config: CoverageReportConfig,
    ) -> CoverageSummaryReportStatus:
        return self.summary_status(
            selected_corridor_id=int(state.coverage_active_corridor_id),
            depleted_count=int(state.depleted_count()),
            completed_dump_count=int(state.coverage_completed_dump_count),
            pass_index=int(state.coverage_pass_index),
            multi_pass_enabled=bool(config.multi_pass_enabled),
            use_env_removed_depth=bool(config.use_env_removed_depth),
            candidate_layout=str(config.candidate_layout),
            first_dig_strategy=str(config.first_dig_strategy),
            first_dig_preferred_corridor_id=(
                config.first_dig_preferred_corridor_id
            ),
            first_dig_max_entry_distance_m=config.first_dig_max_entry_distance_m,
            first_dig_qpos_delta_weight=float(config.first_dig_qpos_delta_weight),
            terminal_stop_requested=bool(state.coverage_terminal_stop_requested),
            terminal_stop_reason=str(state.coverage_terminal_stop_reason),
        )

    def trace_status_from_state(
        self,
        state: CoverageRuntimeState,
        *,
        config: CoverageReportConfig,
        selection_service: CoverageSelectionService,
    ) -> CoverageTraceReportStatus:
        return self.trace_status(
            use_env_removed_depth=bool(config.use_env_removed_depth),
            candidate_layout=str(config.candidate_layout),
            first_dig_strategy=str(config.first_dig_strategy),
            pass_index=int(state.coverage_pass_index),
            multi_pass_enabled=bool(config.multi_pass_enabled),
            multi_pass_max_passes=int(config.multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                config.multi_pass_min_remaining_depth_m
            ),
            first_dig_preferred_corridor_id=(
                config.first_dig_preferred_corridor_id
            ),
            corridors=[
                self.corridor_to_debug(
                    corridor,
                    attempt_limit=selection_service.corridor_attempt_limit(corridor),
                    cell_confidence=selection_service.cell_confidence(corridor),
                )
                for corridor in state.coverage_corridors
            ],
            decision_trace=state.coverage_decision_trace,
            terminal_stop_requested=bool(state.coverage_terminal_stop_requested),
            terminal_stop_reason=str(state.coverage_terminal_stop_reason),
        )

    @staticmethod
    def trace_status(
        *,
        use_env_removed_depth: bool,
        candidate_layout: str,
        first_dig_strategy: str,
        pass_index: int,
        multi_pass_enabled: bool,
        multi_pass_max_passes: int,
        multi_pass_min_remaining_depth_m: float,
        first_dig_preferred_corridor_id: int | None,
        corridors: list[Any],
        decision_trace: list[Any],
        terminal_stop_requested: bool,
        terminal_stop_reason: str,
    ) -> CoverageTraceReportStatus:
        return CoverageTraceReportStatus(
            use_env_removed_depth=bool(use_env_removed_depth),
            candidate_layout=str(candidate_layout),
            first_dig_strategy=str(first_dig_strategy),
            pass_index=int(pass_index),
            multi_pass_enabled=bool(multi_pass_enabled),
            multi_pass_max_passes=int(multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                multi_pass_min_remaining_depth_m
            ),
            first_dig_preferred_corridor_id=(
                None
                if first_dig_preferred_corridor_id is None
                else int(first_dig_preferred_corridor_id)
            ),
            corridors=list(corridors),
            decision_trace=list(decision_trace),
            terminal_stop_requested=bool(terminal_stop_requested),
            terminal_stop_reason=str(terminal_stop_reason),
        )

    @staticmethod
    def summary_status(
        *,
        selected_corridor_id: int,
        depleted_count: int,
        completed_dump_count: int,
        pass_index: int,
        multi_pass_enabled: bool,
        use_env_removed_depth: bool,
        candidate_layout: str,
        first_dig_strategy: str,
        first_dig_preferred_corridor_id: int | None,
        first_dig_max_entry_distance_m: float | None,
        first_dig_qpos_delta_weight: float,
        terminal_stop_requested: bool,
        terminal_stop_reason: str,
    ) -> CoverageSummaryReportStatus:
        return CoverageSummaryReportStatus(
            selected_corridor_id=int(selected_corridor_id),
            depleted_count=int(depleted_count),
            completed_dump_count=int(completed_dump_count),
            pass_index=int(pass_index),
            multi_pass_enabled=bool(multi_pass_enabled),
            use_env_removed_depth=bool(use_env_removed_depth),
            candidate_layout=str(candidate_layout),
            first_dig_strategy=str(first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if first_dig_preferred_corridor_id is None
                else int(first_dig_preferred_corridor_id)
            ),
            first_dig_max_entry_distance_m=(
                None
                if first_dig_max_entry_distance_m is None
                else float(first_dig_max_entry_distance_m)
            ),
            first_dig_qpos_delta_weight=float(first_dig_qpos_delta_weight),
            terminal_stop_requested=bool(terminal_stop_requested),
            terminal_stop_reason=str(terminal_stop_reason),
        )

    @staticmethod
    def debug_fields(inputs: CoverageDebugReportInputs) -> dict[str, Any]:
        active = inputs.active_corridor

        def active_float(name: str) -> float:
            if active is None:
                return float("nan")
            return float(active.get(name, float("nan")))

        return {
            "coverage_corridor_id": int(inputs.active_corridor_id),
            "coverage_selected_corridor_id": int(inputs.active_corridor_id),
            "coverage_last_selected_corridor_id": int(
                inputs.last_selected_corridor_id
            ),
            "coverage_last_selected_cell_id": int(inputs.last_selected_cell_id),
            "coverage_last_selected_row_id": int(inputs.last_selected_row_id),
            "coverage_entry_x_m": active_float("entry_x_m"),
            "coverage_entry_z_m": active_float("entry_z_m"),
            "coverage_exit_x_m": active_float("exit_x_m"),
            "coverage_exit_z_m": active_float("exit_z_m"),
            "coverage_entry_x_p05_m": active_float("entry_x_p05_m"),
            "coverage_entry_x_p50_m": active_float("entry_x_p50_m"),
            "coverage_entry_x_p95_m": active_float("entry_x_p95_m"),
            "coverage_entry_z_p05_m": active_float("entry_z_p05_m"),
            "coverage_entry_z_p50_m": active_float("entry_z_p50_m"),
            "coverage_entry_z_p95_m": active_float("entry_z_p95_m"),
            "coverage_entry_radial_p75_m": active_float("entry_radial_p75_m"),
            "coverage_entry_radial_p95_m": active_float("entry_radial_p95_m"),
            "coverage_exit_x_p05_m": active_float("exit_x_p05_m"),
            "coverage_exit_x_p50_m": active_float("exit_x_p50_m"),
            "coverage_exit_x_p95_m": active_float("exit_x_p95_m"),
            "coverage_exit_z_p05_m": active_float("exit_z_p05_m"),
            "coverage_exit_z_p50_m": active_float("exit_z_p50_m"),
            "coverage_exit_z_p95_m": active_float("exit_z_p95_m"),
            "coverage_exit_radial_p75_m": active_float("exit_radial_p75_m"),
            "coverage_exit_radial_p95_m": active_float("exit_radial_p95_m"),
            "coverage_cut_depth_peak_p05_m": active_float(
                "cut_depth_peak_p05_m"
            ),
            "coverage_cut_depth_peak_p50_m": active_float(
                "cut_depth_peak_p50_m"
            ),
            "coverage_cut_depth_peak_p95_m": active_float(
                "cut_depth_peak_p95_m"
            ),
            "coverage_cell_id": int(inputs.active_cell_id),
            "coverage_corridor_score": float(inputs.active_score),
            "coverage_state_exemplar_enabled": bool(
                inputs.state_exemplar_enabled
            ),
            "coverage_state_exemplar_ids": list(inputs.state_exemplar_ids),
            "coverage_state_exemplar_distance": float(
                inputs.state_exemplar_distance
            ),
            "coverage_depleted_count": int(inputs.depleted_count),
            "coverage_pass_index": int(inputs.pass_index),
            "coverage_multi_pass_enabled": bool(inputs.multi_pass_enabled),
            "coverage_multi_pass_max_passes": int(inputs.multi_pass_max_passes),
            "coverage_multi_pass_min_remaining_depth_m": float(
                inputs.multi_pass_min_remaining_depth_m
            ),
            "coverage_last_payload_gain_kg": float(inputs.last_payload_gain_kg),
            "coverage_last_effective_deposit_delta_kg": float(
                inputs.last_effective_deposit_delta_kg
            ),
            "coverage_global_low_productivity_streak": int(
                inputs.global_low_productivity_streak
            ),
            "coverage_use_env_removed_depth": bool(inputs.use_env_removed_depth),
            "coverage_candidate_layout": str(inputs.candidate_layout),
            "coverage_first_dig_strategy": str(inputs.first_dig_strategy),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if inputs.first_dig_preferred_corridor_id is None
                else inputs.first_dig_preferred_corridor_id
            ),
            "coverage_first_dig_max_entry_distance_m": float(
                np.nan
                if inputs.first_dig_max_entry_distance_m is None
                else inputs.first_dig_max_entry_distance_m
            ),
            "coverage_first_dig_qpos_delta_weight": float(
                inputs.first_dig_qpos_delta_weight
            ),
            "coverage_first_dig_max_qpos_delta": (
                None
                if inputs.first_dig_max_qpos_delta is None
                else np.asarray(
                    inputs.first_dig_max_qpos_delta,
                    dtype=float,
                ).tolist()
            ),
            "coverage_terminal_stop_requested": bool(
                inputs.terminal_stop_requested
            ),
            "coverage_terminal_stop_reason": str(inputs.terminal_stop_reason),
            "coverage_corridors": list(inputs.corridors),
            "planner_terminal_stop_requested": bool(
                inputs.terminal_stop_requested
            ),
            "planner_terminal_stop_reason": str(inputs.terminal_stop_reason),
            "coverage_candidate_scores": list(inputs.candidate_scores),
        }

    @staticmethod
    def corridor_to_debug(
        corridor: CoverageCorridorState,
        *,
        attempt_limit: int,
        cell_confidence: float,
    ) -> dict[str, float | int | str]:
        return {
            "corridor_id": int(corridor.corridor_id),
            "entry_x_m": float(corridor.entry_x_m),
            "entry_z_m": float(corridor.entry_z_m),
            "exit_x_m": float(corridor.exit_x_m),
            "exit_z_m": float(corridor.exit_z_m),
            "entry_x_p05_m": float(corridor.entry_x_p05_m),
            "entry_x_p50_m": float(corridor.entry_x_p50_m),
            "entry_x_p95_m": float(corridor.entry_x_p95_m),
            "entry_z_p05_m": float(corridor.entry_z_p05_m),
            "entry_z_p50_m": float(corridor.entry_z_p50_m),
            "entry_z_p95_m": float(corridor.entry_z_p95_m),
            "entry_radial_p75_m": float(corridor.entry_radial_p75_m),
            "entry_radial_p95_m": float(corridor.entry_radial_p95_m),
            "exit_x_p05_m": float(corridor.exit_x_p05_m),
            "exit_x_p50_m": float(corridor.exit_x_p50_m),
            "exit_x_p95_m": float(corridor.exit_x_p95_m),
            "exit_z_p05_m": float(corridor.exit_z_p05_m),
            "exit_z_p50_m": float(corridor.exit_z_p50_m),
            "exit_z_p95_m": float(corridor.exit_z_p95_m),
            "exit_radial_p75_m": float(corridor.exit_radial_p75_m),
            "exit_radial_p95_m": float(corridor.exit_radial_p95_m),
            "cut_depth_peak_p05_m": float(corridor.cut_depth_peak_p05_m),
            "cut_depth_peak_p50_m": float(corridor.cut_depth_peak_p50_m),
            "cut_depth_peak_p95_m": float(corridor.cut_depth_peak_p95_m),
            "cell_id": int(max(0, min(5, corridor.cell_id))),
            "source_count": int(corridor.source_count),
            "source_fraction": float(corridor.source_fraction),
            "attempt_limit": int(attempt_limit),
            "cell_confidence": float(cell_confidence),
            "score": float(corridor.score),
            "attempts": int(corridor.attempts),
            "low_productivity_streak": int(corridor.low_productivity_streak),
            "depleted": int(corridor.depleted),
            "belief_coverage": float(corridor.belief_coverage),
            "last_payload_gain_kg": float(corridor.last_payload_gain_kg),
            "last_effective_deposit_delta_kg": float(
                corridor.last_effective_deposit_delta_kg
            ),
            "last_remaining_depth_m": float(corridor.last_remaining_depth_m),
            "last_reason": str(corridor.last_reason),
            "state_exemplar_id": str(corridor.state_exemplar_id),
            "state_exemplar_distance": float(corridor.state_exemplar_distance),
        }

    @staticmethod
    def decision_event(
        event: str,
        *,
        state: CoverageReportState,
        corridor: dict[str, float | int | str] | None = None,
        bucket: CoverageBucketSnapshot | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": str(event),
            "cycle_index": int(state.cycle_index),
            "skill_name": str(state.skill_name),
            "active_corridor_id": int(state.active_corridor_id),
            "last_selected_corridor_id": int(state.last_selected_corridor_id),
            "last_selected_cell_id": int(state.last_selected_cell_id),
            "last_selected_row_id": int(state.last_selected_row_id),
            "depleted_count": int(state.depleted_count),
            "pass_index": int(state.pass_index),
            "global_low_productivity_streak": int(
                state.global_low_productivity_streak
            ),
            "terminal_stop_requested": int(state.terminal_stop_requested),
            "terminal_stop_reason": str(state.terminal_stop_reason),
        }
        if corridor is not None:
            payload["corridor"] = dict(corridor)
        if bucket is not None:
            payload["bucket"] = {
                "mass_kg": float(bucket.mass_kg),
                "deposited_mass_kg": float(bucket.deposited_mass_kg),
                "dig_area_x_m": float(bucket.dig_area_x_m),
                "dig_area_y_m": float(bucket.dig_area_y_m),
                "dig_area_z_m": float(bucket.dig_area_z_m),
                "long_norm": float(bucket.long_norm),
                "short_norm": float(bucket.short_norm),
                "plane_depth_m": float(bucket.plane_depth_m),
                "local_depth_m": float(bucket.local_depth_m),
            }
        payload.update(dict(extra or {}))
        return payload


__all__ = [
    "CoverageBucketSnapshot",
    "CoverageDebugReportInputs",
    "CoverageReportConfig",
    "CoverageReportService",
    "CoverageReportState",
    "CoverageSummaryReportStatus",
    "CoverageTraceReportStatus",
]
