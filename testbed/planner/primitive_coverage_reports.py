"""Coverage reporting payload builders for primitive planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage import CoverageCorridorState


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
    "CoverageReportService",
    "CoverageReportState",
]
