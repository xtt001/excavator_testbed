"""Coverage scoring, rare-cell, and first-dig gate helpers."""

from __future__ import annotations

from testbed.data.operator_first_v2_2 import _build_dig_cut_token

from .models import *


class CoverageScoringMixin:
    def _coverage_first_dig_active(self) -> bool:
        return bool(
            int(self._cycle_index) == 0
            and int(self._coverage_completed_dump_count) <= 0
            and self.coverage_first_dig_strategy
            not in {"", "none", "coverage_score"}
        )

    def _coverage_first_dig_gate_available(
        self,
        facts: CoverageObservationFacts,
    ) -> bool:
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
            distance = self._coverage_entry_distance_m(corridor, facts)
            qpos_delta = self._coverage_first_dig_qpos_delta(corridor, facts)
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
        facts: CoverageObservationFacts | None = None,
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
        if facts is not None and self.coverage_state_exemplars_enabled:
            distance = self._coverage_state_exemplar_distance(corridor, facts)
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
        facts: CoverageObservationFacts,
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
            distance = self._coverage_entry_distance_m(corridor, facts)
            if not np.isfinite(distance):
                return 0.0
            qpos_penalty = self._coverage_first_dig_qpos_delta_penalty(
                self._coverage_first_dig_qpos_delta(corridor, facts)
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
        facts: CoverageObservationFacts,
    ) -> float:
        pose = self._bucket_tip_dig_area_pose(facts)
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

    def _pre_dig_align_target_from_token(
        self,
        *,
        token: np.ndarray,
        facts: CoverageObservationFacts,
        update_state: bool,
    ) -> np.ndarray:
        coerced_facts = self._coerce_facts(facts)
        if self.first_dig_alignment_target_fn is None:
            return np.asarray(coerced_facts.qpos, dtype=np.float32).reshape(
                self.action_dim
            )
        return np.asarray(
            self.first_dig_alignment_target_fn(
                np.asarray(token, dtype=np.float32),
                coerced_facts,
            ),
            dtype=np.float32,
        ).reshape(self.action_dim)

    def _coverage_first_dig_qpos_delta(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageObservationFacts,
    ) -> np.ndarray:
        if not self._coverage_first_dig_active() or not self.pre_dig_align_enabled:
            return np.zeros(self.action_dim, dtype=np.float32)
        raw_fields = self._coverage_raw_fields(corridor, facts=facts)
        token = _build_dig_cut_token(raw_fields)
        target = self._pre_dig_align_target_from_token(
            token=token,
            facts=facts,
            update_state=False,
        )
        qpos = np.asarray(
            self._coerce_facts(facts).qpos,
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
