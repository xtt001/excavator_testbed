"""Coverage corridor selection and first-dig gating helpers."""

from __future__ import annotations

from testbed.data.operator_first_v2_2 import _build_dig_cut_token

from .models import *


class CoverageSelectionMixin:
    def _select_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        if self._coverage_all_depleted():
            self._maybe_reopen_coverage_pass(obs, reason="select_all_depleted")
        best: CoverageCorridorState | None = None
        best_score = -float("inf")
        self._coverage_candidate_scores = []
        first_dig_gate_available = self._coverage_first_dig_gate_available(obs)
        for corridor in self._coverage_corridors:
            remaining_depth = self._coverage_remaining_depth_for_corridor(obs, corridor)
            first_dig_bonus = self._coverage_first_dig_bonus(corridor, obs)
            first_dig_distance = self._coverage_entry_distance_m(corridor, obs)
            first_dig_entry_reachable = self._coverage_first_dig_entry_reachable(
                first_dig_distance
            )
            first_dig_qpos_delta = self._coverage_first_dig_qpos_delta(corridor, obs)
            first_dig_qpos_reachable = self._coverage_first_dig_qpos_reachable(
                first_dig_qpos_delta
            )
            first_dig_qpos_penalty = self._coverage_first_dig_qpos_delta_penalty(
                first_dig_qpos_delta
            )
            first_dig_reachable = bool(
                first_dig_entry_reachable and first_dig_qpos_reachable
            )
            first_dig_gated_out = bool(first_dig_gate_available and not first_dig_reachable)
            rare_first_dig_gated_out = self._coverage_rare_first_dig_gated_out(
                corridor
            )
            state_exemplar_distance = self._coverage_state_exemplar_distance(
                corridor,
                obs,
            )
            score = (
                self._coverage_score(corridor, remaining_depth, obs=obs)
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
                    "attempt_limit": int(self._coverage_corridor_attempt_limit(corridor)),
                    "depleted": int(corridor.depleted),
                    "source_count": int(corridor.source_count),
                    "source_fraction": float(corridor.source_fraction),
                    "cell_confidence": float(self._coverage_cell_confidence(corridor)),
                    "state_exemplar_distance": float(state_exemplar_distance),
                    "state_exemplar_id": str(
                        self._coverage_state_exemplar_id(corridor, obs)
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
                        else self.coverage_first_dig_max_qpos_delta.astype(float).tolist()
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
            obs=obs,
            corridor=best,
            extra={
                "selected_score": float(best_score),
                "candidate_scores": list(self._coverage_candidate_scores),
                "first_dig_gate_available": int(first_dig_gate_available),
            },
        )
        if self._coverage_all_depleted():
            if not self._maybe_reopen_coverage_pass(obs, reason="select_all_depleted"):
                self._request_coverage_terminal_stop("dig_area_depleted")
        return best

    def _coverage_first_dig_active(self) -> bool:
        return bool(
            int(self._cycle_index) == 0
            and int(self._coverage_completed_dump_count) <= 0
            and self.coverage_first_dig_strategy
            not in {"", "none", "coverage_score"}
        )

    def _coverage_first_dig_gate_available(self, obs: dict) -> bool:
        if not self._coverage_first_dig_active():
            return False
        if (
            self.coverage_first_dig_max_entry_distance_m is None
            and self.coverage_first_dig_max_qpos_delta is None
        ):
            return False
        for corridor in self._coverage_corridors:
            if corridor.depleted:
                continue
            if corridor.attempts >= self._coverage_corridor_attempt_limit(corridor):
                continue
            if self._coverage_rare_first_dig_gated_out(corridor):
                continue
            distance = self._coverage_entry_distance_m(corridor, obs)
            qpos_delta = self._coverage_first_dig_qpos_delta(corridor, obs)
            if (
                self._coverage_first_dig_entry_reachable(distance)
                and self._coverage_first_dig_qpos_reachable(qpos_delta)
            ):
                return True
        return False

    def _coverage_first_dig_entry_reachable(self, distance: float) -> bool:
        if not self._coverage_first_dig_active():
            return True
        if self.coverage_first_dig_max_entry_distance_m is None:
            return True
        return bool(
            np.isfinite(distance)
            and float(distance) <= float(self.coverage_first_dig_max_entry_distance_m)
        )

    def _coverage_score(
        self,
        corridor: CoverageCorridorState,
        remaining_depth_m: float,
        *,
        obs: dict | None = None,
    ) -> float:
        if corridor.depleted:
            return -1.0e9 - float(corridor.attempts)
        if corridor.attempts >= self._coverage_corridor_attempt_limit(corridor):
            return -1.0e8 - float(corridor.attempts)
        fields = dict(self.dig_cut_prior.get("fields", {}))
        target_depth = (
            float(corridor.cut_depth_peak_m)
            if np.isfinite(corridor.cut_depth_peak_m)
            else self._prior_percentile(
                fields,
                "cut_depth_peak_m",
                self.coverage_cut_depth_percentile,
            )
        )
        if self.coverage_use_env_removed_depth:
            remaining_ratio = (
                1.0
                if not np.isfinite(remaining_depth_m) or target_depth <= 1.0e-6
                else float(np.clip(remaining_depth_m / target_depth, 0.0, 1.5))
            )
        else:
            remaining_ratio = float(
                np.clip(1.0 - float(corridor.belief_coverage), 0.0, 1.5)
            )
        deposit_p50 = max(
            self._prior_percentile(fields, "effective_deposit_delta_kg", "p50"),
            1.0,
        )
        productivity = (
            1.0
            if corridor.attempts <= 0
            else float(
                np.clip(
                    corridor.last_effective_deposit_delta_kg / deposit_p50,
                    0.0,
                    1.5,
                )
            )
        )
        repeat_penalty = (
            self.coverage_recent_selection_penalty
            if int(corridor.corridor_id) == int(self._coverage_last_selected_corridor_id)
            else 0.0
        )
        row_penalty = self._coverage_recent_row_penalty(corridor)
        unattempted_bonus = (
            self.coverage_unattempted_bonus if corridor.attempts <= 0 else 0.0
        )
        attempt_penalty = self.coverage_attempt_penalty * float(corridor.attempts)
        cell_confidence = self._coverage_cell_confidence(corridor)
        state_exemplar_penalty = 0.0
        if obs is not None and self.coverage_state_exemplars_enabled:
            distance = self._coverage_state_exemplar_distance(corridor, obs)
            if np.isfinite(distance):
                state_exemplar_penalty = (
                    self.coverage_state_exemplar_score_weight * float(distance)
                )
        return (
            2.0 * remaining_ratio
            + productivity
            + self.coverage_cell_confidence_weight * cell_confidence
            + unattempted_bonus
            - repeat_penalty
            - row_penalty
            - attempt_penalty
            - state_exemplar_penalty
            - 0.5 * float(corridor.low_productivity_streak)
        )

    def _coverage_cell_confidence(self, corridor: CoverageCorridorState) -> float:
        if self.coverage_candidate_layout != "cell_weighted_3x2":
            return 0.0
        fraction = float(corridor.source_fraction)
        if not np.isfinite(fraction) or fraction <= 0.0:
            return 0.0
        uniform_fraction = 1.0 / 6.0
        return float(np.clip(fraction / uniform_fraction, 0.0, 1.5))

    def _coverage_corridor_is_rare(self, corridor: CoverageCorridorState) -> bool:
        if self.coverage_candidate_layout != "cell_weighted_3x2":
            return False
        fraction = float(corridor.source_fraction)
        return bool(
            np.isfinite(fraction)
            and fraction > 0.0
            and fraction < self.coverage_rare_cell_source_fraction_threshold
        )

    def _coverage_corridor_attempt_limit(self, corridor: CoverageCorridorState) -> int:
        limit = int(self.coverage_max_attempts_per_corridor)
        if self._coverage_corridor_is_rare(corridor):
            limit = min(limit, int(self.coverage_rare_cell_max_attempts))
        return max(1, int(limit))

    def _coverage_rare_first_dig_gated_out(
        self,
        corridor: CoverageCorridorState,
    ) -> bool:
        if not self._coverage_first_dig_active():
            return False
        if not self._coverage_corridor_is_rare(corridor):
            return False
        for candidate in self._coverage_corridors:
            if candidate is corridor:
                continue
            if self._coverage_corridor_is_rare(candidate):
                continue
            if candidate.depleted:
                continue
            if candidate.attempts >= self._coverage_corridor_attempt_limit(candidate):
                continue
            return True
        return False

    def _coverage_recent_row_penalty(self, corridor: CoverageCorridorState) -> float:
        if self.coverage_recent_row_selection_penalty <= 0.0:
            return 0.0
        previous = self._coverage_recent_row_reference_corridor()
        if previous is None:
            return 0.0
        if int(previous.corridor_id) == int(corridor.corridor_id):
            return 0.0
        same_row = bool(
            self._coverage_corridor_row_id(previous)
            == self._coverage_corridor_row_id(corridor)
        )
        return float(self.coverage_recent_row_selection_penalty if same_row else 0.0)

    def _coverage_recent_row_reference_corridor(
        self,
    ) -> CoverageCorridorState | None:
        previous = self._coverage_corridor_by_id(self._coverage_last_selected_corridor_id)
        if previous is not None:
            return previous
        return self._coverage_active_corridor()

    def _coverage_first_dig_bonus(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        if self.coverage_first_dig_strategy in {"", "none", "coverage_score"}:
            return 0.0
        if int(self._cycle_index) != 0 or int(self._coverage_completed_dump_count) > 0:
            return 0.0
        if corridor.depleted or corridor.attempts > 0:
            return 0.0
        if self.coverage_first_dig_strategy in {
            "nearest_entry",
            "bootstrap_nearest_entry",
        }:
            distance = self._coverage_entry_distance_m(corridor, obs)
            if not np.isfinite(distance):
                return 0.0
            qpos_penalty = self._coverage_first_dig_qpos_delta_penalty(
                self._coverage_first_dig_qpos_delta(corridor, obs)
            )
            return (
                -float(self.coverage_first_dig_proximity_weight) * float(distance)
                - float(self.coverage_first_dig_qpos_delta_weight) * qpos_penalty
            )
        if self.coverage_first_dig_strategy not in {
            "preferred_corridor",
            "bootstrap_friendly",
        }:
            return 0.0
        preferred_id = self.coverage_first_dig_preferred_corridor_id
        if preferred_id is None:
            return 0.0
        if int(corridor.corridor_id) != int(preferred_id):
            return 0.0
        return float(self.coverage_first_dig_preferred_bonus)

    def _coverage_entry_distance_m(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        pose = self._bucket_tip_dig_area_pose(obs)
        if pose is None:
            return float("nan")
        bucket_x, _, bucket_z = pose
        if not all(np.isfinite(value) for value in (bucket_x, bucket_z)):
            return float("nan")
        return float(
            np.hypot(
                float(bucket_x) - float(corridor.entry_x_m),
                float(bucket_z) - float(corridor.entry_z_m),
            )
        )

    def _coverage_first_dig_qpos_delta(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> np.ndarray:
        if not self._coverage_first_dig_active() or not self.pre_dig_align_enabled:
            return np.zeros(self.action_dim, dtype=np.float32)
        raw_fields = self._coverage_raw_fields(corridor, obs=obs)
        token = _build_dig_cut_token(raw_fields)
        target = self._pre_dig_align_target_from_token(
            token=token,
            obs=obs,
            update_state=False,
        )
        qpos = np.asarray(
            self._coerce_facts(obs).qpos,
            dtype=np.float32,
        ).reshape(self.action_dim)
        delta = np.abs(target - qpos).astype(np.float32)
        delta[~self.pre_dig_align_controlled_dims] = 0.0
        return delta

    def _coverage_first_dig_qpos_reachable(self, delta: np.ndarray) -> bool:
        if not self._coverage_first_dig_active():
            return True
        if self.coverage_first_dig_max_qpos_delta is None:
            return True
        controlled = self.pre_dig_align_controlled_dims
        if not np.any(controlled):
            return True
        delta = np.asarray(delta, dtype=np.float32).reshape(self.action_dim)
        return bool(
            np.all(
                delta[controlled]
                <= self.coverage_first_dig_max_qpos_delta[controlled] + 1.0e-6
            )
        )

    def _coverage_first_dig_qpos_delta_penalty(self, delta: np.ndarray) -> float:
        if not self._coverage_first_dig_active():
            return 0.0
        controlled = self.pre_dig_align_controlled_dims
        if not np.any(controlled):
            return 0.0
        delta = np.asarray(delta, dtype=np.float32).reshape(self.action_dim)
        delta = delta[controlled]
        if self.coverage_first_dig_max_qpos_delta is not None:
            scale = np.maximum(
                self.coverage_first_dig_max_qpos_delta[controlled],
                1.0e-6,
            )
            delta = delta / scale
        return float(np.linalg.norm(delta))
