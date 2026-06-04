"""Base properties and public wrappers for coverage planning."""

from __future__ import annotations

from .models import *


class CoverageServiceBase:
    def __init__(
        self,
        *,
        config: CoverageServiceConfig,
        state: CoverageServiceState | None = None,
        first_dig_alignment_target_fn: FirstDigAlignmentTargetFn | None = None,
    ) -> None:
        self.config = config
        if self.config.state_exemplars_by_cell is None:
            self.config.state_exemplars_by_cell = load_coverage_state_exemplars(
                enabled=self.config.state_exemplars_enabled,
                raw_path=self.config.state_exemplar_path,
                prior_path=self.config.dig_cut_prior_path,
        )
        self.state = state or CoverageServiceState()
        self.first_dig_alignment_target_fn = first_dig_alignment_target_fn
        self._active_facts: CoverageObservationFacts | None = None

    @property
    def decision_trace(self) -> list[dict[str, Any]]:
        return self.state.decision_trace or []

    def ensure_corridors(self) -> None:
        self._ensure_coverage_corridors()

    def select_next_corridor(
        self,
        facts: CoverageObservationFacts,
    ) -> CoverageCorridorState:
        return self._select_next_coverage_corridor(facts)

    def raw_fields(
        self,
        corridor: CoverageCorridorState,
        *,
        facts: CoverageObservationFacts | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        return self._coverage_raw_fields(
            corridor,
            obs=facts,
            update_state=update_state,
        )

    def complete_dig(self, facts: CoverageObservationFacts) -> None:
        self._complete_coverage_dig(facts)

    def complete_dump(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> None:
        self._complete_coverage_dump(facts, reason=reason)

    def reject_active_corridor(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> None:
        self._reject_active_coverage_corridor(facts, reason=reason)

    def corridor_debug(
        self,
        corridor: CoverageCorridorState,
    ) -> dict[str, float | int | str]:
        return self._coverage_corridor_to_debug(corridor)

    @property
    def dig_cut_planner_mode(self) -> str:
        return self.config.dig_cut_planner_mode

    @property
    def dig_cut_prior(self) -> dict[str, Any]:
        return self.config.dig_cut_prior

    @property
    def dig_cut_prior_path(self) -> str:
        return self.config.dig_cut_prior_path

    @property
    def action_dim(self) -> int:
        return int(self.config.action_dim)

    @property
    def coverage_candidate_layout(self) -> str:
        return self.config.candidate_layout

    @property
    def coverage_use_env_removed_depth(self) -> bool:
        return bool(self.config.use_env_removed_depth)

    @property
    def coverage_belief_gain_scale(self) -> float:
        return float(self.config.belief_gain_scale)

    @property
    def coverage_belief_depleted_score(self) -> float:
        return float(self.config.belief_depleted_score)

    @property
    def coverage_low_productivity_payload_kg(self) -> float:
        return float(self.config.low_productivity_payload_kg)

    @property
    def coverage_low_productivity_deposit_kg(self) -> float:
        return float(self.config.low_productivity_deposit_kg)

    @property
    def coverage_deplete_after_low_streak(self) -> int:
        return int(self.config.deplete_after_low_streak)

    @property
    def coverage_min_remaining_depth_m(self) -> float:
        return float(self.config.min_remaining_depth_m)

    @property
    def coverage_global_low_productivity_stop(self) -> int:
        return int(self.config.global_low_productivity_stop)

    @property
    def coverage_max_attempts_per_corridor(self) -> int:
        return int(self.config.max_attempts_per_corridor)

    @property
    def coverage_multi_pass_enabled(self) -> bool:
        return bool(self.config.multi_pass_enabled)

    @property
    def coverage_multi_pass_max_passes(self) -> int:
        return int(self.config.multi_pass_max_passes)

    @property
    def coverage_multi_pass_min_remaining_depth_m(self) -> float:
        return float(self.config.multi_pass_min_remaining_depth_m)

    @property
    def coverage_unattempted_bonus(self) -> float:
        return float(self.config.unattempted_bonus)

    @property
    def coverage_attempt_penalty(self) -> float:
        return float(self.config.attempt_penalty)

    @property
    def coverage_recent_selection_penalty(self) -> float:
        return float(self.config.recent_selection_penalty)

    @property
    def coverage_recent_row_selection_penalty(self) -> float:
        return float(self.config.recent_row_selection_penalty)

    @property
    def coverage_rare_cell_source_fraction_threshold(self) -> float:
        return float(self.config.rare_cell_source_fraction_threshold)

    @property
    def coverage_rare_cell_max_attempts(self) -> int:
        return int(self.config.rare_cell_max_attempts)

    @property
    def coverage_cell_confidence_weight(self) -> float:
        return float(self.config.cell_confidence_weight)

    @property
    def coverage_state_exemplars_enabled(self) -> bool:
        return bool(self.config.state_exemplars_enabled)

    @property
    def coverage_state_exemplar_path(self) -> str:
        return str(self.config.state_exemplar_path)

    @property
    def coverage_state_exemplar_k(self) -> int:
        return int(self.config.state_exemplar_k)

    @property
    def coverage_state_exemplar_removed_depth_scale_m(self) -> float:
        return float(self.config.state_exemplar_removed_depth_scale_m)

    @property
    def coverage_state_exemplar_target_cell_weight(self) -> float:
        return float(self.config.state_exemplar_target_cell_weight)

    @property
    def coverage_state_exemplar_score_weight(self) -> float:
        return float(self.config.state_exemplar_score_weight)

    @property
    def coverage_state_exemplar_temperature(self) -> float:
        return float(self.config.state_exemplar_temperature)

    @property
    def coverage_state_exemplar_skip_rejected(self) -> bool:
        return bool(self.config.state_exemplar_skip_rejected)

    @property
    def coverage_state_exemplars_by_cell(self) -> dict[int, list[dict[str, Any]]]:
        return dict(self.config.state_exemplars_by_cell or {})

    @property
    def coverage_first_dig_strategy(self) -> str:
        return str(self.config.first_dig_strategy)

    @property
    def coverage_first_dig_preferred_corridor_id(self) -> int | None:
        return self.config.first_dig_preferred_corridor_id

    @property
    def coverage_first_dig_preferred_bonus(self) -> float:
        return float(self.config.first_dig_preferred_bonus)

    @property
    def coverage_first_dig_proximity_weight(self) -> float:
        return float(self.config.first_dig_proximity_weight)

    @property
    def coverage_first_dig_max_entry_distance_m(self) -> float | None:
        return self.config.first_dig_max_entry_distance_m

    @property
    def coverage_first_dig_qpos_delta_weight(self) -> float:
        return float(self.config.first_dig_qpos_delta_weight)

    @property
    def coverage_first_dig_max_qpos_delta(self) -> np.ndarray | None:
        return self.config.first_dig_max_qpos_delta

    @property
    def pre_dig_align_enabled(self) -> bool:
        return bool(self.config.first_dig_alignment_enabled)

    @property
    def pre_dig_align_controlled_dims(self) -> np.ndarray:
        if self.config.first_dig_controlled_dims is None:
            return np.ones(self.action_dim, dtype=bool)
        return self.config.first_dig_controlled_dims

    @property
    def coverage_entry_x_percentiles(self) -> tuple[str, ...]:
        return tuple(self.config.entry_x_percentiles)

    @property
    def coverage_entry_z_percentiles(self) -> tuple[str, ...]:
        return tuple(self.config.entry_z_percentiles)

    @property
    def coverage_cut_direction_percentile(self) -> str:
        return str(self.config.cut_direction_percentile)

    @property
    def coverage_cut_length_percentile(self) -> str:
        return str(self.config.cut_length_percentile)

    @property
    def coverage_cut_depth_percentile(self) -> str:
        return str(self.config.cut_depth_percentile)

    @property
    def coverage_payload_percentile(self) -> str:
        return str(self.config.payload_percentile)

    @property
    def _coverage_corridors(self) -> list[CoverageCorridorState]:
        if self.state.corridors is None:
            self.state.corridors = []
        return self.state.corridors

    @_coverage_corridors.setter
    def _coverage_corridors(self, value: list[CoverageCorridorState]) -> None:
        self.state.corridors = list(value)

    @property
    def _coverage_active_corridor_id(self) -> int:
        return int(self.state.active_corridor_id)

    @_coverage_active_corridor_id.setter
    def _coverage_active_corridor_id(self, value: int) -> None:
        self.state.active_corridor_id = int(value)

    @property
    def _coverage_last_selected_corridor_id(self) -> int:
        return int(self.state.last_selected_corridor_id)

    @_coverage_last_selected_corridor_id.setter
    def _coverage_last_selected_corridor_id(self, value: int) -> None:
        self.state.last_selected_corridor_id = int(value)

    @property
    def _coverage_current_payload_gain_kg(self) -> float:
        return float(self.state.current_payload_gain_kg)

    @_coverage_current_payload_gain_kg.setter
    def _coverage_current_payload_gain_kg(self, value: float) -> None:
        self.state.current_payload_gain_kg = float(value)

    @property
    def _coverage_cycle_start_deposit_kg(self) -> float:
        return float(self.state.cycle_start_deposit_kg)

    @_coverage_cycle_start_deposit_kg.setter
    def _coverage_cycle_start_deposit_kg(self, value: float) -> None:
        self.state.cycle_start_deposit_kg = float(value)

    @property
    def _coverage_last_payload_gain_kg(self) -> float:
        return float(self.state.last_payload_gain_kg)

    @_coverage_last_payload_gain_kg.setter
    def _coverage_last_payload_gain_kg(self, value: float) -> None:
        self.state.last_payload_gain_kg = float(value)

    @property
    def _coverage_last_effective_deposit_delta_kg(self) -> float:
        return float(self.state.last_effective_deposit_delta_kg)

    @_coverage_last_effective_deposit_delta_kg.setter
    def _coverage_last_effective_deposit_delta_kg(self, value: float) -> None:
        self.state.last_effective_deposit_delta_kg = float(value)

    @property
    def _coverage_global_low_productivity_streak(self) -> int:
        return int(self.state.global_low_productivity_streak)

    @_coverage_global_low_productivity_streak.setter
    def _coverage_global_low_productivity_streak(self, value: int) -> None:
        self.state.global_low_productivity_streak = int(value)

    @property
    def _coverage_completed_dump_count(self) -> int:
        return int(self.state.completed_dump_count)

    @_coverage_completed_dump_count.setter
    def _coverage_completed_dump_count(self, value: int) -> None:
        self.state.completed_dump_count = int(value)

    @property
    def _coverage_pass_index(self) -> int:
        return int(self.state.pass_index)

    @_coverage_pass_index.setter
    def _coverage_pass_index(self, value: int) -> None:
        self.state.pass_index = int(value)

    @property
    def _coverage_terminal_stop_requested(self) -> bool:
        return bool(self.state.terminal_stop_requested)

    @_coverage_terminal_stop_requested.setter
    def _coverage_terminal_stop_requested(self, value: bool) -> None:
        self.state.terminal_stop_requested = bool(value)

    @property
    def _coverage_terminal_stop_reason(self) -> str:
        return str(self.state.terminal_stop_reason)

    @_coverage_terminal_stop_reason.setter
    def _coverage_terminal_stop_reason(self, value: str) -> None:
        self.state.terminal_stop_reason = str(value)

    @property
    def _coverage_candidate_scores(self) -> list[dict[str, float | int | str]]:
        if self.state.candidate_scores is None:
            self.state.candidate_scores = []
        return self.state.candidate_scores

    @_coverage_candidate_scores.setter
    def _coverage_candidate_scores(
        self,
        value: list[dict[str, float | int | str]],
    ) -> None:
        self.state.candidate_scores = list(value)

    @property
    def _coverage_decision_trace(self) -> list[dict[str, Any]]:
        if self.state.decision_trace is None:
            self.state.decision_trace = []
        return self.state.decision_trace

    @_coverage_decision_trace.setter
    def _coverage_decision_trace(self, value: list[dict[str, Any]]) -> None:
        self.state.decision_trace = list(value)

    @property
    def _coverage_active_state_exemplar_ids(self) -> list[str]:
        if self.state.active_state_exemplar_ids is None:
            self.state.active_state_exemplar_ids = []
        return self.state.active_state_exemplar_ids

    @_coverage_active_state_exemplar_ids.setter
    def _coverage_active_state_exemplar_ids(self, value: list[str]) -> None:
        self.state.active_state_exemplar_ids = list(value)

    @property
    def _coverage_rejected_state_exemplar_ids(self) -> set[str]:
        if self.state.rejected_state_exemplar_ids is None:
            self.state.rejected_state_exemplar_ids = set()
        return self.state.rejected_state_exemplar_ids

    @_coverage_rejected_state_exemplar_ids.setter
    def _coverage_rejected_state_exemplar_ids(self, value: set[str]) -> None:
        self.state.rejected_state_exemplar_ids = set(value)

    @property
    def _coverage_active_state_exemplar_distance(self) -> float:
        return float(self.state.active_state_exemplar_distance)

    @_coverage_active_state_exemplar_distance.setter
    def _coverage_active_state_exemplar_distance(self, value: float) -> None:
        self.state.active_state_exemplar_distance = float(value)

    @property
    def _coverage_active_state_exemplar_profile_token(self) -> np.ndarray | None:
        return self.state.active_state_exemplar_profile_token

    @_coverage_active_state_exemplar_profile_token.setter
    def _coverage_active_state_exemplar_profile_token(
        self,
        value: np.ndarray | None,
    ) -> None:
        self.state.active_state_exemplar_profile_token = value

    @staticmethod
    def coverage_percentile_list(
        value: object,
        *,
        default: tuple[str, ...],
    ) -> tuple[str, ...]:
        allowed = {"p10", "p50", "p90"}
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value]
        else:
            items = list(default)
        cleaned = tuple(item for item in items if item in allowed)
        return cleaned or tuple(default)

    @staticmethod
    def coverage_percentile_name(value: object, *, default: str) -> str:
        allowed = {"p10", "p50", "p90"}
        text = str(value).strip().lower()
        return text if text in allowed else default

    @staticmethod
    def prior_percentile(
        fields: dict[str, Any],
        field_name: str,
        percentile: str,
    ) -> float:
        try:
            return float(fields[field_name][percentile])
        except KeyError as exc:
            raise KeyError(f"Missing prior field {field_name}.{percentile}") from exc

    def _prior_percentile(
        self,
        fields: dict[str, Any],
        field_name: str,
        percentile: str,
    ) -> float:
        return self.prior_percentile(fields, field_name, percentile)

    def _clamp_to_prior(
        self,
        fields: dict[str, Any],
        field_name: str,
        value: float,
    ) -> float:
        lo = self._prior_percentile(fields, field_name, "p10")
        hi = self._prior_percentile(fields, field_name, "p90")
        return float(np.clip(float(value), lo, hi))

    def raw_fields_in_prior_range(
        self,
        raw_fields: dict[str, float | int],
    ) -> bool:
        if not self.dig_cut_prior:
            return False
        fields = dict(self.dig_cut_prior.get("fields", {}))
        mapping = {
            "operator_entry_x_m": "entry_x_m",
            "operator_entry_z_m": "entry_z_m",
            "operator_exit_x_m": "exit_x_m",
            "operator_exit_z_m": "exit_z_m",
            "operator_cut_direction_x": "cut_direction_x",
            "operator_cut_direction_z": "cut_direction_z",
            "operator_cut_length_m": "cut_length_m",
            "operator_cut_depth_peak_m": "cut_depth_peak_m",
            "operator_cut_payload_gain_kg": "payload_gain_kg",
        }
        for raw_name, prior_name in mapping.items():
            value = float(raw_fields.get(raw_name, np.nan))
            lo = self._prior_percentile(fields, prior_name, "p10")
            hi = self._prior_percentile(fields, prior_name, "p90")
            if not np.isfinite(value) or value < lo - 1.0e-6 or value > hi + 1.0e-6:
                return False
        return True

    def _coerce_facts(
        self,
        value: CoverageObservationFacts | dict,
    ) -> CoverageObservationFacts:
        if isinstance(value, CoverageObservationFacts):
            self._active_facts = value
            return value
        raise TypeError(
            "CoverageService methods require CoverageObservationFacts; "
            f"got {type(value).__name__}."
        )

    @property
    def _cycle_index(self) -> int:
        if self._active_facts is None:
            return 0
        return int(self._active_facts.cycle_index)

    @property
    def _skill_name(self) -> str:
        if self._active_facts is None:
            return ""
        return str(self._active_facts.skill_name)

    @property
    def _dig_best_mass_kg(self) -> float:
        if self._active_facts is None:
            return 0.0
        return float(self._active_facts.dig_best_mass_kg)

    def _env_state(self, facts: CoverageObservationFacts | dict) -> np.ndarray:
        return np.asarray(self._coerce_facts(facts).env_state, dtype=np.float32)

    def _mass_in_bucket(self, facts: CoverageObservationFacts | dict) -> float:
        return float(self._coerce_facts(facts).mass_in_bucket_kg)

    def _deposited_mass(self, facts: CoverageObservationFacts | dict) -> float:
        return float(self._coerce_facts(facts).deposited_mass_kg)

    def _bucket_tip_dig_area_pose(
        self,
        facts: CoverageObservationFacts | dict,
    ) -> tuple[float, float, float] | None:
        return self._coerce_facts(facts).bucket_tip_dig_area_pose

    def _pre_dig_align_target_from_token(
        self,
        *,
        token: np.ndarray,
        obs: CoverageObservationFacts | dict,
        update_state: bool,
    ) -> np.ndarray:
        facts = self._coerce_facts(obs)
        if self.first_dig_alignment_target_fn is None:
            return np.asarray(facts.qpos, dtype=np.float32).reshape(self.action_dim)
        return np.asarray(
            self.first_dig_alignment_target_fn(np.asarray(token, dtype=np.float32), facts),
            dtype=np.float32,
        ).reshape(self.action_dim)
