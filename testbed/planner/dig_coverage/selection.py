"""Coverage corridor selection helpers."""

from __future__ import annotations

from .models import *


class CoverageSelectionMixin:
    def _select_coverage_corridor(
        self,
        facts: CoverageObservationFacts,
    ) -> CoverageCorridorState:
        return self._select_coverage_corridor_result(facts).corridor

    def _select_coverage_corridor_result(
        self,
        facts: CoverageObservationFacts,
    ) -> CoverageSelectionResult:
        if self._coverage_all_depleted():
            self._maybe_reopen_coverage_pass(facts, reason="select_all_depleted")
        best: CoverageCorridorState | None = None
        best_score = -float("inf")
        self._coverage_candidate_scores = []
        first_dig_gate_available = self._coverage_first_dig_gate_available(facts)
        for corridor in self._coverage_corridors:
            remaining_depth = self._coverage_remaining_depth_for_corridor(
                facts,
                corridor,
            )
            first_dig_bonus = self._coverage_first_dig_bonus(corridor, facts)
            first_dig_distance = self._coverage_entry_distance_m(corridor, facts)
            first_dig_entry_reachable = self._coverage_first_dig_entry_reachable(
                first_dig_distance
            )
            first_dig_qpos_delta = self._coverage_first_dig_qpos_delta(corridor, facts)
            first_dig_qpos_reachable = self._coverage_first_dig_qpos_reachable(
                first_dig_qpos_delta
            )
            first_dig_qpos_penalty = self._coverage_first_dig_qpos_delta_penalty(
                first_dig_qpos_delta
            )
            first_dig_reachable = bool(
                first_dig_entry_reachable and first_dig_qpos_reachable
            )
            first_dig_gated_out = bool(
                first_dig_gate_available and not first_dig_reachable
            )
            rare_first_dig_gated_out = self._coverage_rare_first_dig_gated_out(
                corridor
            )
            state_exemplar_distance = self._coverage_state_exemplar_distance(
                corridor,
                facts,
            )
            score = (
                self._coverage_score(corridor, remaining_depth, facts=facts)
                + first_dig_bonus
            )
            if first_dig_gated_out or rare_first_dig_gated_out:
                score = -1.0e12 + float(score)
            corridor.score = float(score)
            corridor.last_remaining_depth_m = float(remaining_depth)
            recent_row_reference = self._coverage_recent_row_reference_corridor()
            recent_row_reference_id = (
                -1
                if recent_row_reference is None
                else int(recent_row_reference.corridor_id)
            )
            recent_row_reference_cell_id = (
                -1
                if recent_row_reference is None
                else int(self._coverage_cell_id(recent_row_reference))
            )
            recent_row_reference_row_id = (
                -1
                if recent_row_reference is None
                else int(self._coverage_corridor_row_id(recent_row_reference))
            )
            row_id = int(self._coverage_corridor_row_id(corridor))
            same_recent_row = bool(
                recent_row_reference is not None
                and int(recent_row_reference.corridor_id)
                != int(corridor.corridor_id)
                and row_id == recent_row_reference_row_id
            )
            self._coverage_candidate_scores.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(self._coverage_cell_id(corridor)),
                    "row_id": int(row_id),
                    "score": float(score),
                    "attempts": int(corridor.attempts),
                    "attempt_limit": int(
                        self._coverage_corridor_attempt_limit(corridor)
                    ),
                    "depleted": int(corridor.depleted),
                    "source_count": int(corridor.source_count),
                    "source_fraction": float(corridor.source_fraction),
                    "cell_confidence": float(self._coverage_cell_confidence(corridor)),
                    "state_exemplar_distance": float(state_exemplar_distance),
                    "state_exemplar_id": str(
                        self._coverage_state_exemplar_id(corridor, facts)
                    ),
                    "belief_coverage": float(corridor.belief_coverage),
                    "remaining_depth_m": float(remaining_depth),
                    "first_dig_bonus": float(first_dig_bonus),
                    "recent_row_penalty": float(
                        self._coverage_recent_row_penalty(corridor)
                    ),
                    "recent_row_reference_corridor_id": int(
                        recent_row_reference_id
                    ),
                    "recent_row_reference_cell_id": int(
                        recent_row_reference_cell_id
                    ),
                    "recent_row_reference_row_id": int(
                        recent_row_reference_row_id
                    ),
                    "same_recent_row": int(same_recent_row),
                    "first_dig_entry_distance_m": float(first_dig_distance),
                    "first_dig_entry_reachable": int(first_dig_entry_reachable),
                    "first_dig_qpos_delta_norm": float(first_dig_qpos_penalty),
                    "first_dig_qpos_reachable": int(first_dig_qpos_reachable),
                    "first_dig_qpos_delta": first_dig_qpos_delta.astype(float).tolist(),
                    "first_dig_max_qpos_delta": (
                        []
                        if self.coverage_first_dig_max_qpos_delta is None
                        else self.coverage_first_dig_max_qpos_delta.astype(
                            float
                        ).tolist()
                    ),
                    "first_dig_reachable": int(first_dig_reachable),
                    "first_dig_gate_applied": int(first_dig_gate_available),
                    "first_dig_gated_out": int(first_dig_gated_out),
                    "rare_first_dig_gated_out": int(rare_first_dig_gated_out),
                    "first_dig_max_entry_distance_m": float(
                        np.nan
                        if self.coverage_first_dig_max_entry_distance_m is None
                        else self.coverage_first_dig_max_entry_distance_m
                    ),
                    "low_productivity_streak": int(corridor.low_productivity_streak),
                }
            )
            if first_dig_gated_out or rare_first_dig_gated_out:
                continue
            if score > best_score:
                best = corridor
                best_score = float(score)

        if best is None:
            raise ValueError("operator_prior_coverage has no selectable corridors.")
        self._record_coverage_decision_event(
            "select_corridor",
            facts=facts,
            corridor=best,
            extra={
                "selected_score": float(best_score),
                "candidate_scores": list(self._coverage_candidate_scores),
                "first_dig_gate_available": int(first_dig_gate_available),
            },
        )
        terminal_stop_reason = ""
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(
                facts,
                reason="select_all_depleted",
            ):
                terminal_stop_reason = "dig_area_depleted"
        return CoverageSelectionResult(
            corridor=best,
            action=CoverageActionResult(terminal_stop_reason=terminal_stop_reason),
        )
