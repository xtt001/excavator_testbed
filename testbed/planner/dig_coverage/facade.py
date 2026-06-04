from __future__ import annotations

from .models import *
from .service import CoverageService


class DigCoverageMixin:
    """Compatibility facade that routes planner coverage calls into CoverageService."""

    @staticmethod
    def _coverage_percentile_list(
        value: object,
        *,
        default: tuple[str, ...],
    ) -> tuple[str, ...]:
        return CoverageService.coverage_percentile_list(value, default=default)

    @staticmethod
    def _coverage_percentile_name(value: object, *, default: str) -> str:
        return CoverageService.coverage_percentile_name(value, default=default)

    @staticmethod
    def _prior_percentile(
        fields: dict[str, Any],
        field_name: str,
        percentile: str,
    ) -> float:
        return CoverageService.prior_percentile(fields, field_name, percentile)

    def _coverage_service_config(self) -> CoverageServiceConfig:
        return CoverageServiceConfig(
            dig_cut_planner_mode=str(self.dig_cut_planner_mode),
            dig_cut_prior=dict(self.dig_cut_prior),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            action_dim=int(self.action_dim),
            candidate_layout=str(self.coverage_candidate_layout),
            use_env_removed_depth=bool(self.coverage_use_env_removed_depth),
            belief_gain_scale=float(self.coverage_belief_gain_scale),
            belief_depleted_score=float(self.coverage_belief_depleted_score),
            low_productivity_payload_kg=float(
                self.coverage_low_productivity_payload_kg
            ),
            low_productivity_deposit_kg=float(
                self.coverage_low_productivity_deposit_kg
            ),
            deplete_after_low_streak=int(self.coverage_deplete_after_low_streak),
            min_remaining_depth_m=float(self.coverage_min_remaining_depth_m),
            global_low_productivity_stop=int(
                self.coverage_global_low_productivity_stop
            ),
            max_attempts_per_corridor=int(self.coverage_max_attempts_per_corridor),
            multi_pass_enabled=bool(self.coverage_multi_pass_enabled),
            multi_pass_max_passes=int(self.coverage_multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.coverage_multi_pass_min_remaining_depth_m
            ),
            unattempted_bonus=float(self.coverage_unattempted_bonus),
            attempt_penalty=float(self.coverage_attempt_penalty),
            recent_selection_penalty=float(self.coverage_recent_selection_penalty),
            recent_row_selection_penalty=float(
                self.coverage_recent_row_selection_penalty
            ),
            rare_cell_source_fraction_threshold=float(
                self.coverage_rare_cell_source_fraction_threshold
            ),
            rare_cell_max_attempts=int(self.coverage_rare_cell_max_attempts),
            cell_confidence_weight=float(self.coverage_cell_confidence_weight),
            state_exemplars_enabled=bool(self.coverage_state_exemplars_enabled),
            state_exemplar_path=str(self.coverage_state_exemplar_path),
            state_exemplar_k=int(self.coverage_state_exemplar_k),
            state_exemplar_removed_depth_scale_m=float(
                self.coverage_state_exemplar_removed_depth_scale_m
            ),
            state_exemplar_target_cell_weight=float(
                self.coverage_state_exemplar_target_cell_weight
            ),
            state_exemplar_score_weight=float(self.coverage_state_exemplar_score_weight),
            state_exemplar_temperature=float(self.coverage_state_exemplar_temperature),
            state_exemplar_skip_rejected=bool(
                self.coverage_state_exemplar_skip_rejected
            ),
            state_exemplars_by_cell=dict(
                getattr(self, "coverage_state_exemplars_by_cell", {}) or {}
            ),
            first_dig_strategy=str(self.coverage_first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.coverage_first_dig_preferred_corridor_id is None
                else int(self.coverage_first_dig_preferred_corridor_id)
            ),
            first_dig_preferred_bonus=float(
                self.coverage_first_dig_preferred_bonus
            ),
            first_dig_proximity_weight=float(self.coverage_first_dig_proximity_weight),
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
                else np.asarray(
                    self.coverage_first_dig_max_qpos_delta,
                    dtype=np.float32,
                ).reshape(int(self.action_dim))
            ),
            first_dig_alignment_enabled=bool(self.pre_dig_align_enabled),
            first_dig_controlled_dims=np.asarray(
                self.pre_dig_align_controlled_dims,
                dtype=bool,
            ).reshape(int(self.action_dim)),
            entry_x_percentiles=tuple(self.coverage_entry_x_percentiles),
            entry_z_percentiles=tuple(self.coverage_entry_z_percentiles),
            cut_direction_percentile=str(self.coverage_cut_direction_percentile),
            cut_length_percentile=str(self.coverage_cut_length_percentile),
            cut_depth_percentile=str(self.coverage_cut_depth_percentile),
            payload_percentile=str(self.coverage_payload_percentile),
        )

    def _create_coverage_service(self) -> CoverageService:
        return CoverageService(
            config=self._coverage_service_config(),
            state=CoverageServiceState(),
            first_dig_alignment_target_fn=self._coverage_first_dig_alignment_target,
        )

    def _reset_coverage_service(self) -> None:
        self.coverage_service = self._create_coverage_service()

    def _coverage_first_dig_alignment_target(
        self,
        token: np.ndarray,
        facts: CoverageObservationFacts,
    ) -> np.ndarray:
        obs = {
            "qpos": np.asarray(facts.qpos, dtype=np.float32).reshape(self.action_dim),
            "env_state": np.asarray(facts.env_state, dtype=np.float32),
        }
        return self._pre_dig_align_target_from_token(
            token=token,
            obs=obs,
            update_state=False,
        )

    def _coverage_observation_facts(self, obs: dict) -> CoverageObservationFacts:
        return CoverageObservationFacts(
            env_state=self._env_state(obs),
            qpos=np.asarray(
                obs.get("qpos", np.zeros(self.action_dim, dtype=np.float32)),
                dtype=np.float32,
            ).reshape(self.action_dim),
            bucket_tip_dig_area_pose=self._bucket_tip_dig_area_pose(obs),
            mass_in_bucket_kg=self._mass_in_bucket(obs),
            deposited_mass_kg=self._deposited_mass(obs),
            cycle_index=int(getattr(self, "_cycle_index", 0)),
            skill_name=str(getattr(self, "_skill_name", "")),
            dig_best_mass_kg=float(getattr(self, "_dig_best_mass_kg", 0.0)),
        )

    def _coverage_context_facts(self) -> CoverageObservationFacts:
        return CoverageObservationFacts(
            env_state=np.zeros(0, dtype=np.float32),
            qpos=np.zeros(self.action_dim, dtype=np.float32),
            bucket_tip_dig_area_pose=None,
            mass_in_bucket_kg=0.0,
            deposited_mass_kg=0.0,
            cycle_index=int(getattr(self, "_cycle_index", 0)),
            skill_name=str(getattr(self, "_skill_name", "")),
            dig_best_mass_kg=float(getattr(self, "_dig_best_mass_kg", 0.0)),
        )

    def _coverage_service(self) -> CoverageService:
        service = getattr(self, "coverage_service", None)
        if service is None:
            service = self._create_coverage_service()
            self.coverage_service = service
        return service

    @property
    def _coverage_corridors(self) -> list[CoverageCorridorState]:
        return self._coverage_service()._coverage_corridors

    @_coverage_corridors.setter
    def _coverage_corridors(self, value: list[CoverageCorridorState]) -> None:
        self._coverage_service()._coverage_corridors = value

    @property
    def _coverage_active_corridor_id(self) -> int:
        return self._coverage_service()._coverage_active_corridor_id

    @_coverage_active_corridor_id.setter
    def _coverage_active_corridor_id(self, value: int) -> None:
        self._coverage_service()._coverage_active_corridor_id = value

    @property
    def _coverage_last_selected_corridor_id(self) -> int:
        return self._coverage_service()._coverage_last_selected_corridor_id

    @_coverage_last_selected_corridor_id.setter
    def _coverage_last_selected_corridor_id(self, value: int) -> None:
        self._coverage_service()._coverage_last_selected_corridor_id = value

    @property
    def _coverage_current_payload_gain_kg(self) -> float:
        return self._coverage_service()._coverage_current_payload_gain_kg

    @_coverage_current_payload_gain_kg.setter
    def _coverage_current_payload_gain_kg(self, value: float) -> None:
        self._coverage_service()._coverage_current_payload_gain_kg = value

    @property
    def _coverage_cycle_start_deposit_kg(self) -> float:
        return self._coverage_service()._coverage_cycle_start_deposit_kg

    @_coverage_cycle_start_deposit_kg.setter
    def _coverage_cycle_start_deposit_kg(self, value: float) -> None:
        self._coverage_service()._coverage_cycle_start_deposit_kg = value

    @property
    def _coverage_last_payload_gain_kg(self) -> float:
        return self._coverage_service()._coverage_last_payload_gain_kg

    @_coverage_last_payload_gain_kg.setter
    def _coverage_last_payload_gain_kg(self, value: float) -> None:
        self._coverage_service()._coverage_last_payload_gain_kg = value

    @property
    def _coverage_last_effective_deposit_delta_kg(self) -> float:
        return self._coverage_service()._coverage_last_effective_deposit_delta_kg

    @_coverage_last_effective_deposit_delta_kg.setter
    def _coverage_last_effective_deposit_delta_kg(self, value: float) -> None:
        self._coverage_service()._coverage_last_effective_deposit_delta_kg = value

    @property
    def _coverage_global_low_productivity_streak(self) -> int:
        return self._coverage_service()._coverage_global_low_productivity_streak

    @_coverage_global_low_productivity_streak.setter
    def _coverage_global_low_productivity_streak(self, value: int) -> None:
        self._coverage_service()._coverage_global_low_productivity_streak = value

    @property
    def _coverage_completed_dump_count(self) -> int:
        return self._coverage_service()._coverage_completed_dump_count

    @_coverage_completed_dump_count.setter
    def _coverage_completed_dump_count(self, value: int) -> None:
        self._coverage_service()._coverage_completed_dump_count = value

    @property
    def _coverage_pass_index(self) -> int:
        return self._coverage_service()._coverage_pass_index

    @_coverage_pass_index.setter
    def _coverage_pass_index(self, value: int) -> None:
        self._coverage_service()._coverage_pass_index = value

    @property
    def _coverage_terminal_stop_requested(self) -> bool:
        return self._coverage_service()._coverage_terminal_stop_requested

    @_coverage_terminal_stop_requested.setter
    def _coverage_terminal_stop_requested(self, value: bool) -> None:
        self._coverage_service()._coverage_terminal_stop_requested = value

    @property
    def _coverage_terminal_stop_reason(self) -> str:
        return self._coverage_service()._coverage_terminal_stop_reason

    @_coverage_terminal_stop_reason.setter
    def _coverage_terminal_stop_reason(self, value: str) -> None:
        self._coverage_service()._coverage_terminal_stop_reason = value

    @property
    def _coverage_candidate_scores(self) -> list[dict[str, float | int | str]]:
        return self._coverage_service()._coverage_candidate_scores

    @_coverage_candidate_scores.setter
    def _coverage_candidate_scores(
        self,
        value: list[dict[str, float | int | str]],
    ) -> None:
        self._coverage_service()._coverage_candidate_scores = value

    @property
    def _coverage_decision_trace(self) -> list[dict[str, Any]]:
        return self._coverage_service()._coverage_decision_trace

    @_coverage_decision_trace.setter
    def _coverage_decision_trace(self, value: list[dict[str, Any]]) -> None:
        self._coverage_service()._coverage_decision_trace = value

    @property
    def _coverage_active_state_exemplar_ids(self) -> list[str]:
        return self._coverage_service()._coverage_active_state_exemplar_ids

    @_coverage_active_state_exemplar_ids.setter
    def _coverage_active_state_exemplar_ids(self, value: list[str]) -> None:
        self._coverage_service()._coverage_active_state_exemplar_ids = value

    @property
    def _coverage_rejected_state_exemplar_ids(self) -> set[str]:
        return self._coverage_service()._coverage_rejected_state_exemplar_ids

    @_coverage_rejected_state_exemplar_ids.setter
    def _coverage_rejected_state_exemplar_ids(self, value: set[str]) -> None:
        self._coverage_service()._coverage_rejected_state_exemplar_ids = value

    @property
    def _coverage_active_state_exemplar_distance(self) -> float:
        return self._coverage_service()._coverage_active_state_exemplar_distance

    @_coverage_active_state_exemplar_distance.setter
    def _coverage_active_state_exemplar_distance(self, value: float) -> None:
        self._coverage_service()._coverage_active_state_exemplar_distance = value

    @property
    def _coverage_active_state_exemplar_profile_token(self) -> np.ndarray | None:
        return self._coverage_service()._coverage_active_state_exemplar_profile_token

    @_coverage_active_state_exemplar_profile_token.setter
    def _coverage_active_state_exemplar_profile_token(
        self,
        value: np.ndarray | None,
    ) -> None:
        self._coverage_service()._coverage_active_state_exemplar_profile_token = value

    def _select_next_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        return self._coverage_service().select_next_corridor(
            self._coverage_observation_facts(obs)
        )

    def _ensure_coverage_corridors(self) -> None:
        self._coverage_service().ensure_corridors()

    def _select_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        return self._coverage_service()._select_coverage_corridor(
            self._coverage_observation_facts(obs)
        )

    def _coverage_first_dig_gate_available(self, obs: dict) -> bool:
        return self._coverage_service()._coverage_first_dig_gate_available(
            self._coverage_observation_facts(obs)
        )

    def _coverage_entry_distance_m(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        return self._coverage_service()._coverage_entry_distance_m(
            corridor,
            self._coverage_observation_facts(obs),
        )

    def _coverage_first_dig_qpos_delta(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> np.ndarray:
        return self._coverage_service()._coverage_first_dig_qpos_delta(
            corridor,
            self._coverage_observation_facts(obs),
        )

    def _coverage_score(
        self,
        corridor: CoverageCorridorState,
        remaining_depth_m: float,
        *,
        obs: dict | None = None,
    ) -> float:
        return self._coverage_service()._coverage_score(
            corridor,
            remaining_depth_m,
            obs=None if obs is None else self._coverage_observation_facts(obs),
        )

    def _coverage_first_dig_bonus(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        return self._coverage_service()._coverage_first_dig_bonus(
            corridor,
            self._coverage_observation_facts(obs),
        )

    def _coverage_raw_fields(
        self,
        corridor: CoverageCorridorState,
        *,
        obs: dict | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        return self._coverage_service().raw_fields(
            corridor,
            facts=None if obs is None else self._coverage_observation_facts(obs),
            update_state=update_state,
        )

    def _coverage_state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
        *,
        update_state: bool,
    ) -> dict[str, object] | None:
        return self._coverage_service()._coverage_state_conditioned_plan(
            corridor,
            self._coverage_observation_facts(obs),
            update_state=update_state,
        )

    def _coverage_state_exemplar_distance(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        return self._coverage_service()._coverage_state_exemplar_distance(
            corridor,
            self._coverage_observation_facts(obs),
        )

    def _coverage_state_exemplar_id(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> str:
        return self._coverage_service()._coverage_state_exemplar_id(
            corridor,
            self._coverage_observation_facts(obs),
        )

    def _coverage_removed_depth_grid(self, obs: dict) -> np.ndarray | None:
        return self._coverage_service()._coverage_removed_depth_grid(
            self._coverage_observation_facts(obs)
        )

    def _coverage_remaining_depth_for_corridor(
        self,
        obs: dict,
        corridor: CoverageCorridorState,
    ) -> float:
        return self._coverage_service()._coverage_remaining_depth_for_corridor(
            self._coverage_observation_facts(obs),
            corridor,
        )

    def _complete_coverage_dig(self, obs: dict) -> None:
        self._coverage_service().complete_dig(self._coverage_observation_facts(obs))

    def _complete_coverage_dump(self, obs: dict, *, reason: str) -> None:
        self._coverage_service().complete_dump(
            self._coverage_observation_facts(obs),
            reason=reason,
        )

    def _reject_active_coverage_corridor(self, obs: dict, *, reason: str) -> None:
        self._coverage_service().reject_active_corridor(
            self._coverage_observation_facts(obs),
            reason=reason,
        )

    def _record_coverage_decision_event(
        self,
        event: str,
        *,
        obs: dict | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._coverage_service()._record_coverage_decision_event(
            event,
            obs=None if obs is None else self._coverage_observation_facts(obs),
            corridor=corridor,
            extra=extra,
        )

    def _maybe_reopen_coverage_pass(self, obs: dict, *, reason: str) -> bool:
        return self._coverage_service()._maybe_reopen_coverage_pass(
            self._coverage_observation_facts(obs),
            reason=reason,
        )

    def _request_coverage_terminal_stop(
        self,
        reason: str,
        *,
        replace: bool = False,
    ) -> None:
        service = self._coverage_service()
        service._active_facts = self._coverage_context_facts()
        service._request_coverage_terminal_stop(reason, replace=replace)

    def _load_coverage_state_exemplars(self) -> dict[int, list[dict[str, Any]]]:
        return load_coverage_state_exemplars(
            enabled=bool(self.coverage_state_exemplars_enabled),
            raw_path=str(self.coverage_state_exemplar_path),
            prior_path=str(self.dig_cut_prior_path),
        )

    def _clamp_to_prior(
        self,
        fields: dict[str, Any],
        field_name: str,
        value: float,
    ) -> float:
        return self._coverage_service()._clamp_to_prior(fields, field_name, value)

    def _raw_fields_in_prior_range(self, raw_fields: dict[str, float | int]) -> bool:
        return self._coverage_service().raw_fields_in_prior_range(raw_fields)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_coverage") or name in {
            "_ensure_coverage_corridors",
            "_request_coverage_terminal_stop",
        }:
            service = self.__dict__.get("coverage_service")
            if service is not None and hasattr(service, name):
                return getattr(service, name)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")
