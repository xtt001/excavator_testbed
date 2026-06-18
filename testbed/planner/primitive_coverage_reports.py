"""Coverage reporting payload builders for primitive planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive_coverage import CoverageCorridorState


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
    "CoverageReportService",
    "CoverageReportState",
]
