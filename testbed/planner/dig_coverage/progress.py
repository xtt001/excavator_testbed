"""Coverage progress, rejection, and terminal-stop helpers."""

from __future__ import annotations

from .models import *


class CoverageProgressMixin:
    def _complete_coverage_dig(
        self,
        facts: CoverageObservationFacts,
    ) -> CoverageActionResult:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return CoverageActionResult()
        self._coverage_current_payload_gain_kg = max(
            float(self._coverage_current_payload_gain_kg),
            self._mass_in_bucket(facts),
        )
        return CoverageActionResult()

    def _complete_coverage_dump(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> CoverageActionResult:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return CoverageActionResult()
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return CoverageActionResult()
        payload_gain = max(float(self._coverage_current_payload_gain_kg), 0.0)
        effective_deposit = max(
            0.0,
            self._deposited_mass(facts) - float(self._coverage_cycle_start_deposit_kg),
        )
        remaining_depth = self._coverage_remaining_depth_for_corridor(facts, corridor)
        low_productivity = (
            payload_gain < self.coverage_low_productivity_payload_kg
            or effective_deposit < self.coverage_low_productivity_deposit_kg
        )
        corridor.attempts += 1
        corridor.last_payload_gain_kg = float(payload_gain)
        corridor.last_effective_deposit_delta_kg = float(effective_deposit)
        corridor.last_remaining_depth_m = float(remaining_depth)
        corridor.last_reason = str(reason)
        self._update_corridor_belief(
            corridor,
            payload_gain_kg=payload_gain,
            effective_deposit_delta_kg=effective_deposit,
        )
        self._coverage_last_payload_gain_kg = float(payload_gain)
        self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
        self._coverage_completed_dump_count += 1

        if low_productivity:
            corridor.low_productivity_streak += 1
            self._coverage_global_low_productivity_streak += 1
        else:
            corridor.low_productivity_streak = 0
            self._coverage_global_low_productivity_streak = 0

        if (
            corridor.low_productivity_streak
            >= self.coverage_deplete_after_low_streak
        ):
            corridor.depleted = True
            corridor.last_reason = "low_productivity_consecutive"
        remaining_depth_available = bool(
            self.coverage_use_env_removed_depth
            and np.isfinite(remaining_depth)
            and float(remaining_depth) >= self.coverage_min_remaining_depth_m
        )
        if (
            corridor.attempts >= self._coverage_corridor_attempt_limit(corridor)
            and not remaining_depth_available
        ):
            corridor.depleted = True
            corridor.last_reason = "attempt_limit_reached"
        if (
            np.isfinite(remaining_depth)
            and remaining_depth < self.coverage_min_remaining_depth_m
        ):
            corridor.depleted = True
            corridor.last_reason = "remaining_depth_below_threshold"
        if (
            not self.coverage_use_env_removed_depth
            and corridor.belief_coverage >= self.coverage_belief_depleted_score
        ):
            corridor.depleted = True
            corridor.last_reason = "belief_coverage_complete"

        self._record_coverage_decision_event(
            "complete_dump",
            facts=facts,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "final_reason": str(corridor.last_reason),
                "payload_gain_kg": float(payload_gain),
                "effective_deposit_delta_kg": float(effective_deposit),
                "remaining_depth_m": float(remaining_depth),
                "low_productivity": int(low_productivity),
                "completed_dump_count": int(self._coverage_completed_dump_count),
            },
        )
        terminal_stop_reason = ""
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(
                facts,
                reason="complete_all_depleted",
            ):
                terminal_stop_reason = "dig_area_depleted"
        elif (
            self._coverage_global_low_productivity_streak
            >= self.coverage_global_low_productivity_stop
        ):
            terminal_stop_reason = "low_productivity_consecutive"
        if (
            low_productivity
            and payload_gain < self.coverage_low_productivity_payload_kg
            and effective_deposit >= self.coverage_low_productivity_deposit_kg
            and not terminal_stop_reason
        ):
            terminal_stop_reason = "physics_artifact_suspected"
        return CoverageActionResult(terminal_stop_reason=terminal_stop_reason)

    def _reject_active_coverage_corridor(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> CoverageActionResult:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return CoverageActionResult()
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return CoverageActionResult()
        self._coverage_rejected_state_exemplar_ids.update(
            exemplar_id
            for exemplar_id in self._coverage_active_state_exemplar_ids
            if exemplar_id
        )
        payload_gain = max(
            float(self._coverage_current_payload_gain_kg),
            float(self._dig_best_mass_kg),
            self._mass_in_bucket(facts),
            0.0,
        )
        effective_deposit = max(
            0.0,
            self._deposited_mass(facts) - float(self._coverage_cycle_start_deposit_kg),
        )
        remaining_depth = self._coverage_remaining_depth_for_corridor(facts, corridor)
        if str(reason) == "align_entry_gap_timeout":
            corridor.last_payload_gain_kg = float(payload_gain)
            corridor.last_effective_deposit_delta_kg = float(effective_deposit)
            corridor.last_remaining_depth_m = float(remaining_depth)
            corridor.last_reason = str(reason)
            self._coverage_last_payload_gain_kg = float(payload_gain)
            self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
            self._record_coverage_decision_event(
                "reject_corridor",
                facts=facts,
                corridor=corridor,
                extra={
                    "reason": str(reason),
                    "payload_gain_kg": float(payload_gain),
                    "effective_deposit_delta_kg": float(effective_deposit),
                    "remaining_depth_m": float(remaining_depth),
                    "counted_attempt": 0,
                },
            )
            return CoverageActionResult()
        corridor.attempts += 1
        corridor.low_productivity_streak += 1
        corridor.last_payload_gain_kg = float(payload_gain)
        corridor.last_effective_deposit_delta_kg = float(effective_deposit)
        corridor.last_remaining_depth_m = float(remaining_depth)
        corridor.last_reason = str(reason)
        self._update_corridor_belief(
            corridor,
            payload_gain_kg=payload_gain,
            effective_deposit_delta_kg=effective_deposit,
        )
        self._coverage_last_payload_gain_kg = float(payload_gain)
        self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
        if str(reason) != "align_entry_gap_timeout":
            self._coverage_global_low_productivity_streak += 1
        if (
            corridor.low_productivity_streak
            >= self.coverage_deplete_after_low_streak
            or corridor.attempts >= self._coverage_corridor_attempt_limit(corridor)
        ):
            corridor.depleted = True
        self._record_coverage_decision_event(
            "reject_corridor",
            facts=facts,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "payload_gain_kg": float(payload_gain),
                "effective_deposit_delta_kg": float(effective_deposit),
                "remaining_depth_m": float(remaining_depth),
                "counted_attempt": 1,
            },
        )
        terminal_stop_reason = ""
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(
                facts,
                reason="reject_all_depleted",
            ):
                terminal_stop_reason = "dig_area_depleted"
        elif (
            self._coverage_global_low_productivity_streak
            >= self.coverage_global_low_productivity_stop
        ):
            terminal_stop_reason = "low_productivity_consecutive"
        return CoverageActionResult(terminal_stop_reason=terminal_stop_reason)

    def _update_corridor_belief(
        self,
        corridor: CoverageCorridorState,
        *,
        payload_gain_kg: float,
        effective_deposit_delta_kg: float,
    ) -> None:
        if self.coverage_use_env_removed_depth:
            return
        fields = dict(self.dig_cut_prior.get("fields", {}))
        payload_p50 = max(self._prior_percentile(fields, "payload_gain_kg", "p50"), 1.0)
        deposit_p50 = max(
            self._prior_percentile(fields, "effective_deposit_delta_kg", "p50"),
            1.0,
        )
        payload_score = float(np.clip(float(payload_gain_kg) / payload_p50, 0.0, 1.5))
        deposit_score = float(
            np.clip(float(effective_deposit_delta_kg) / deposit_p50, 0.0, 1.5)
        )
        gain = self.coverage_belief_gain_scale * max(payload_score, deposit_score)
        if gain <= 0.0:
            return
        corridor.belief_coverage = float(
            np.clip(float(corridor.belief_coverage) + gain, 0.0, 1.5)
        )

    def _maybe_reopen_coverage_pass(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> bool:
        if not self.coverage_multi_pass_enabled:
            return False
        if self._coverage_terminal_stop_requested:
            return False
        if not self.coverage_use_env_removed_depth:
            return False
        if not self._coverage_all_depleted():
            return False
        if (
            int(self._coverage_pass_index) + 1
            >= int(self.coverage_multi_pass_max_passes)
        ):
            return False

        threshold = float(self.coverage_multi_pass_min_remaining_depth_m)
        reopened: list[dict[str, float | int | str]] = []
        for corridor in self._coverage_corridors:
            remaining_depth = self._coverage_remaining_depth_for_corridor(
                facts,
                corridor,
            )
            if not (
                np.isfinite(remaining_depth)
                and float(remaining_depth) >= threshold
            ):
                corridor.last_remaining_depth_m = float(remaining_depth)
                continue
            reopened.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(self._coverage_cell_id(corridor)),
                    "previous_attempts": int(corridor.attempts),
                    "previous_low_productivity_streak": int(
                        corridor.low_productivity_streak
                    ),
                    "previous_reason": str(corridor.last_reason),
                    "remaining_depth_m": float(remaining_depth),
                }
            )
            corridor.depleted = False
            corridor.attempts = 0
            corridor.low_productivity_streak = 0
            corridor.last_remaining_depth_m = float(remaining_depth)
            corridor.last_reason = f"multi_pass_reopened:{reason}"

        if not reopened:
            return False

        self._coverage_pass_index += 1
        self._coverage_active_corridor_id = -1
        self._coverage_global_low_productivity_streak = 0
        self._coverage_rejected_state_exemplar_ids.clear()
        self._record_coverage_decision_event(
            "reopen_coverage_pass",
            facts=facts,
            extra={
                "reason": str(reason),
                "pass_index": int(self._coverage_pass_index),
                "max_passes": int(self.coverage_multi_pass_max_passes),
                "min_remaining_depth_m": float(threshold),
                "reopened_corridors": reopened,
            },
        )
        return True

    def _request_coverage_terminal_stop(
        self,
        reason: str,
        *,
        replace: bool = False,
    ) -> None:
        if self._coverage_terminal_stop_requested and not replace:
            return
        self._coverage_terminal_stop_requested = True
        self._coverage_terminal_stop_reason = str(reason)
        self._record_coverage_decision_event(
            "terminal_stop",
            corridor=self._coverage_active_corridor(),
            extra={"reason": str(reason)},
        )
