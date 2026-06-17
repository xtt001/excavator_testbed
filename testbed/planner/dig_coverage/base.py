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

    @staticmethod
    def initial_runtime_state() -> CoverageServiceState:
        return CoverageServiceState()

    @staticmethod
    def cleared_active_state_exemplar_state() -> CoverageActiveStateExemplarState:
        return CoverageActiveStateExemplarState(
            ids=(),
            distance=float("nan"),
            profile_token=None,
        )

    @property
    def decision_trace(self) -> list[dict[str, Any]]:
        return self.state.decision_trace or []

    def ensure_corridors(self) -> None:
        self._ensure_coverage_corridors()

    def select_next_corridor(
        self,
        facts: CoverageObservationFacts,
    ) -> CoverageCorridorState:
        return self.select_next_corridor_result(facts).corridor

    def select_next_corridor_result(
        self,
        facts: CoverageObservationFacts,
    ) -> CoverageSelectionResult:
        return self._select_next_coverage_corridor_result(facts)

    def raw_fields(
        self,
        corridor: CoverageCorridorState,
        *,
        facts: CoverageObservationFacts | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        return self._coverage_raw_fields(
            corridor,
            facts=facts,
            update_state=update_state,
        )

    def activate_dig_cut_corridor(
        self,
        facts: CoverageObservationFacts,
        *,
        reset_cycle_metrics: bool,
    ) -> CoverageDigCutActivationResult:
        selection = self.select_next_corridor_result(facts)
        if reset_cycle_metrics:
            self._coverage_current_payload_gain_kg = 0.0
            self._coverage_cycle_start_deposit_kg = self._deposited_mass(facts)
        raw_fields = self.raw_fields(
            selection.corridor,
            facts=facts,
            update_state=True,
        )
        return CoverageDigCutActivationResult(
            corridor=selection.corridor,
            raw_fields=raw_fields,
            action=selection.action,
        )

    def complete_dig(self, facts: CoverageObservationFacts) -> CoverageActionResult:
        return self._complete_coverage_dig(facts)

    def complete_dump(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> CoverageActionResult:
        return self._complete_coverage_dump(facts, reason=reason)

    def reject_active_corridor(
        self,
        facts: CoverageObservationFacts,
        *,
        reason: str,
    ) -> CoverageActionResult:
        return self._reject_active_coverage_corridor(facts, reason=reason)

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

    def _record_coverage_decision_event(
        self,
        event: str,
        *,
        facts: CoverageObservationFacts | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": str(event),
            "cycle_index": int(self._cycle_index),
            "skill_name": str(self._skill_name),
            "active_corridor_id": int(self._coverage_active_corridor_id),
            "last_selected_corridor_id": int(self._coverage_last_selected_corridor_id),
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
        if facts is not None:
            env_state = self._env_state(facts)
            payload["bucket"] = {
                "mass_kg": float(self._mass_in_bucket(facts)),
                "deposited_mass_kg": float(self._deposited_mass(facts)),
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

    def _coverage_all_depleted(self) -> bool:
        return bool(
            self._coverage_corridors
            and all(corridor.depleted for corridor in self._coverage_corridors)
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

    @staticmethod
    def _coverage_cell_id(corridor: CoverageCorridorState) -> int:
        if corridor.cell_id >= 0:
            return max(0, min(5, int(corridor.cell_id)))
        corridor_id = max(0, min(5, int(corridor.corridor_id)))
        z_index = corridor_id // 2
        x_index = corridor_id % 2
        return int(z_index * 2 + x_index)

    def _coverage_corridor_row_id(self, corridor: CoverageCorridorState) -> int:
        return int(self._coverage_cell_id(corridor) // 2)

    def _coverage_remaining_depth_for_corridor(
        self,
        facts: CoverageObservationFacts,
        corridor: CoverageCorridorState,
    ) -> float:
        env_state = self._env_state(facts)
        cell_id = self._coverage_cell_id(corridor)
        target_idx = ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + cell_id
        removed_idx = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + cell_id
        valid_idx = ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + cell_id
        if len(env_state) <= max(target_idx, removed_idx, valid_idx):
            return float("nan")
        if float(env_state[valid_idx]) <= 0.5:
            return float("nan")
        target_depth = float(env_state[target_idx])
        removed_depth = float(env_state[removed_idx])
        if not np.isfinite(target_depth) or not np.isfinite(removed_depth):
            return float("nan")
        return float(max(0.0, target_depth - removed_depth))

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

    @staticmethod
    def _coverage_cell_id_from_percentile_indices(
        *,
        x_index: int,
        x_count: int,
        z_index: int,
        z_count: int,
    ) -> int:
        long_index = int(round(np.interp(z_index, [0, max(1, z_count - 1)], [0, 2])))
        short_index = int(round(np.interp(x_index, [0, max(1, x_count - 1)], [0, 1])))
        return int(np.clip(long_index, 0, 2) * 2 + int(np.clip(short_index, 0, 1)))

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

    def _coerce_facts(
        self,
        value: CoverageObservationFacts,
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

    def _env_state(self, facts: CoverageObservationFacts) -> np.ndarray:
        return np.asarray(self._coerce_facts(facts).env_state, dtype=np.float32)

    def _mass_in_bucket(self, facts: CoverageObservationFacts) -> float:
        return float(self._coerce_facts(facts).mass_in_bucket_kg)

    def _deposited_mass(self, facts: CoverageObservationFacts) -> float:
        return float(self._coerce_facts(facts).deposited_mass_kg)

    def _bucket_tip_dig_area_pose(
        self,
        facts: CoverageObservationFacts,
    ) -> tuple[float, float, float] | None:
        return self._coerce_facts(facts).bucket_tip_dig_area_pose
