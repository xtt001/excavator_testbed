"""Coverage debug, trace, and rollout snapshot helpers."""

from __future__ import annotations

from .models import *


class CoverageSnapshotMixin:
    def coverage_debug_snapshot(self) -> CoverageDebugSnapshot:
        active_value_keys = (
            "entry_x_m",
            "entry_z_m",
            "exit_x_m",
            "exit_z_m",
            "entry_x_p05_m",
            "entry_x_p50_m",
            "entry_x_p95_m",
            "entry_z_p05_m",
            "entry_z_p50_m",
            "entry_z_p95_m",
            "entry_radial_p75_m",
            "entry_radial_p95_m",
            "exit_x_p05_m",
            "exit_x_p50_m",
            "exit_x_p95_m",
            "exit_z_p05_m",
            "exit_z_p50_m",
            "exit_z_p95_m",
            "exit_radial_p75_m",
            "exit_radial_p95_m",
            "cut_depth_peak_p05_m",
            "cut_depth_peak_p50_m",
            "cut_depth_peak_p95_m",
        )
        return CoverageDebugSnapshot(
            active_corridor_id=int(self._coverage_active_corridor_id),
            last_selected_corridor_id=int(self._coverage_last_selected_corridor_id),
            last_selected_cell_id=int(
                self._coverage_corridor_cell_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            last_selected_row_id=int(
                self._coverage_corridor_row_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            active_values={
                key: float(self._coverage_active_value(key))
                for key in active_value_keys
            },
            active_cell_id=int(self._coverage_active_cell_id()),
            active_corridor_score=float(self._coverage_active_corridor_score()),
            state_exemplar_enabled=bool(self.coverage_state_exemplars_enabled),
            active_state_exemplar_ids=tuple(self._coverage_active_state_exemplar_ids),
            active_state_exemplar_distance=float(
                self._coverage_active_state_exemplar_distance
            ),
            depleted_count=int(self._coverage_depleted_count()),
            pass_index=int(self._coverage_pass_index),
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
            last_payload_gain_kg=float(self._coverage_last_payload_gain_kg),
            last_effective_deposit_delta_kg=float(
                self._coverage_last_effective_deposit_delta_kg
            ),
            global_low_productivity_streak=int(
                self._coverage_global_low_productivity_streak
            ),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            candidate_layout=str(self.coverage_candidate_layout),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            first_dig_max_entry_distance_m=(
                None
                if self.coverage_first_dig_max_entry_distance_m is None
                else float(self.coverage_first_dig_max_entry_distance_m)
            ),
            first_dig_qpos_delta_weight=float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            first_dig_max_qpos_delta=(
                None
                if self.coverage_first_dig_max_qpos_delta is None
                else self.coverage_first_dig_max_qpos_delta.copy()
            ),
            terminal_stop_requested=bool(self._coverage_terminal_stop_requested),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
            corridors=tuple(
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ),
            candidate_scores=tuple(self._coverage_candidate_scores),
        )

    def coverage_trace_snapshot(self) -> CoverageTraceSnapshot:
        return CoverageTraceSnapshot(
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            candidate_layout=str(self.coverage_candidate_layout),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            pass_index=int(self._coverage_pass_index),
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            corridors=tuple(
                self._coverage_corridor_to_debug(corridor)
                for corridor in self._coverage_corridors
            ),
            decision_trace=tuple(self._coverage_decision_trace),
            terminal_stop_requested=bool(self._coverage_terminal_stop_requested),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )

    def coverage_rollout_summary_snapshot(self) -> CoverageRolloutSummarySnapshot:
        return CoverageRolloutSummarySnapshot(
            selected_corridor_id=int(self._coverage_active_corridor_id),
            depleted_count=int(self._coverage_depleted_count()),
            completed_dump_count=int(self._coverage_completed_dump_count),
            pass_index=int(self._coverage_pass_index),
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            candidate_layout=str(self.coverage_candidate_layout),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            first_dig_max_entry_distance_m=(
                None
                if self.coverage_first_dig_max_entry_distance_m is None
                else float(self.coverage_first_dig_max_entry_distance_m)
            ),
            first_dig_qpos_delta_weight=float(
                self.coverage_first_dig_qpos_delta_weight
            ),
            terminal_stop_requested=bool(self._coverage_terminal_stop_requested),
            terminal_stop_reason=str(self._coverage_terminal_stop_reason),
        )

    def _coverage_corridor_to_debug(
        self,
        corridor: CoverageCorridorState,
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
            "attempt_limit": int(self._coverage_corridor_attempt_limit(corridor)),
            "cell_confidence": float(self._coverage_cell_confidence(corridor)),
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
