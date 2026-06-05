"""Coverage progress, rejection, trace, and debug helpers."""

from __future__ import annotations

from .models import *


class CoverageProgressMixin:
    def _complete_coverage_dig(self, obs: dict) -> CoverageActionResult:
        if self.dig_cut_planner_mode not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return CoverageActionResult()
        self._coverage_current_payload_gain_kg = max(
            float(self._coverage_current_payload_gain_kg),
            self._mass_in_bucket(obs),
        )
        return CoverageActionResult()

    def _complete_coverage_dump(
        self,
        obs: dict,
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
            0.0, self._deposited_mass(obs) - float(self._coverage_cycle_start_deposit_kg)
        )
        remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
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
            obs=obs,
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
            if not self._maybe_reopen_coverage_pass(obs, reason="complete_all_depleted"):
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
        obs: dict,
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
            self._mass_in_bucket(obs),
            0.0,
        )
        effective_deposit = max(
            0.0, self._deposited_mass(obs) - float(self._coverage_cycle_start_deposit_kg)
        )
        remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
        if str(reason) == "align_entry_gap_timeout":
            corridor.last_payload_gain_kg = float(payload_gain)
            corridor.last_effective_deposit_delta_kg = float(effective_deposit)
            corridor.last_remaining_depth_m = float(remaining_depth)
            corridor.last_reason = str(reason)
            self._coverage_last_payload_gain_kg = float(payload_gain)
            self._coverage_last_effective_deposit_delta_kg = float(effective_deposit)
            self._record_coverage_decision_event(
                "reject_corridor",
                obs=obs,
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
            obs=obs,
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
            if not self._maybe_reopen_coverage_pass(obs, reason="reject_all_depleted"):
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

    def _record_coverage_decision_event(
        self,
        event: str,
        *,
        obs: dict | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": str(event),
            "cycle_index": int(self._cycle_index),
            "skill_name": str(self._skill_name),
            "active_corridor_id": int(self._coverage_active_corridor_id),
            "last_selected_corridor_id": int(
                self._coverage_last_selected_corridor_id
            ),
            "last_selected_cell_id": int(
                self._coverage_corridor_cell_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            "last_selected_row_id": int(
                self._coverage_corridor_row_id_by_id(
                    self._coverage_last_selected_corridor_id
                )
            ),
            "depleted_count": int(self._coverage_depleted_count()),
            "pass_index": int(self._coverage_pass_index),
            "global_low_productivity_streak": int(
                self._coverage_global_low_productivity_streak
            ),
            "terminal_stop_requested": int(self._coverage_terminal_stop_requested),
            "terminal_stop_reason": str(self._coverage_terminal_stop_reason),
        }
        if corridor is not None:
            payload["corridor"] = self._coverage_corridor_to_debug(corridor)
        if obs is not None:
            env_state = self._env_state(obs)
            payload["bucket"] = {
                "mass_kg": float(self._mass_in_bucket(obs)),
                "deposited_mass_kg": float(self._deposited_mass(obs)),
                "dig_area_x_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
                ),
                "dig_area_y_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
                ),
                "dig_area_z_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
                ),
                "long_norm": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
                ),
                "short_norm": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
                ),
                "plane_depth_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
                ),
                "local_depth_m": self._env_state_value(
                    env_state,
                    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
                ),
            }
        payload.update(dict(extra or {}))
        self._coverage_decision_trace.append(payload)

    @staticmethod
    def _env_state_value(env_state: np.ndarray, index: int) -> float:
        if len(env_state) <= int(index):
            return float("nan")
        return float(env_state[int(index)])

    def _coverage_all_depleted(self) -> bool:
        return bool(
            self._coverage_corridors
            and all(corridor.depleted for corridor in self._coverage_corridors)
        )

    def _maybe_reopen_coverage_pass(self, obs: dict, *, reason: str) -> bool:
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
            remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
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
            obs=obs,
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

    def _coverage_active_corridor(self) -> CoverageCorridorState | None:
        return self._coverage_corridor_by_id(self._coverage_active_corridor_id)

    def _coverage_corridor_by_id(
        self,
        corridor_id: int,
    ) -> CoverageCorridorState | None:
        for corridor in self._coverage_corridors:
            if int(corridor.corridor_id) == int(corridor_id):
                return corridor
        return None

    def _coverage_active_corridor_score(self) -> float:
        corridor = self._coverage_active_corridor()
        return float("nan") if corridor is None else float(corridor.score)

    def _coverage_active_value(self, name: str) -> float:
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return float("nan")
        return float(getattr(corridor, name, float("nan")))

    def _coverage_active_cell_id(self) -> int:
        corridor = self._coverage_active_corridor()
        if corridor is None:
            return -1
        return int(self._coverage_cell_id(corridor))

    def _coverage_corridor_cell_id_by_id(self, corridor_id: int) -> int:
        corridor = self._coverage_corridor_by_id(corridor_id)
        if corridor is None:
            return -1
        return int(self._coverage_cell_id(corridor))

    def _coverage_corridor_row_id_by_id(self, corridor_id: int) -> int:
        corridor = self._coverage_corridor_by_id(corridor_id)
        if corridor is None:
            return -1
        return int(self._coverage_corridor_row_id(corridor))

    def _coverage_depleted_count(self) -> int:
        return int(sum(1 for corridor in self._coverage_corridors if corridor.depleted))

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
