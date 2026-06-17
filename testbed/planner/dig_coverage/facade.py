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
        values = {
            config_key: getattr(self, attr_name)
            for config_key, attr_name in COVERAGE_SERVICE_CONFIG_FIELDS
            if config_key != "state_exemplars_by_cell"
        }
        values["state_exemplars_by_cell"] = getattr(
            self,
            "coverage_state_exemplars_by_cell",
            None,
        )
        return build_coverage_service_config_from_mapping(values)

    def _create_coverage_service(self) -> CoverageService:
        return CoverageService(
            config=self._coverage_service_config(),
            state=CoverageService.initial_runtime_state(),
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

    def _coverage_observation_fact_values(self) -> dict[str, Any]:
        return {
            fact_key: getattr(self, attr_name, default)
            for fact_key, attr_name, default in COVERAGE_OBSERVATION_FACT_FIELDS
        }

    def _coverage_observation_facts(self, obs: dict) -> CoverageObservationFacts:
        build_kwargs = {}
        if "qpos" in obs:
            build_kwargs["qpos"] = obs["qpos"]
        return build_coverage_observation_facts_from_mapping(
            self._coverage_observation_fact_values(),
            action_dim=self.action_dim,
            env_state=self._env_state(obs),
            bucket_tip_dig_area_pose=self._bucket_tip_dig_area_pose(obs),
            mass_in_bucket_kg=self._mass_in_bucket(obs),
            deposited_mass_kg=self._deposited_mass(obs),
            **build_kwargs,
        )

    def _coverage_context_facts(self) -> CoverageObservationFacts:
        return build_coverage_context_facts_from_mapping(
            self._coverage_observation_fact_values(),
            action_dim=self.action_dim,
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

    def _clear_coverage_active_state_exemplar(self) -> None:
        self._apply_coverage_active_state_exemplar_state(
            self._coverage_service().cleared_active_state_exemplar_state()
        )

    def _apply_coverage_active_state_exemplar_state(
        self,
        state: CoverageActiveStateExemplarState,
    ) -> None:
        self._coverage_active_state_exemplar_ids = list(state.ids)
        self._coverage_active_state_exemplar_distance = float(state.distance)
        self._coverage_active_state_exemplar_profile_token = (
            None
            if state.profile_token is None
            else np.asarray(state.profile_token, dtype=np.float32).copy()
        )

    def _select_next_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        result = self._coverage_service().select_next_corridor_result(
            self._coverage_observation_facts(obs)
        )
        self._apply_coverage_action_result(result.action)
        return result.corridor

    def _ensure_coverage_corridors(self) -> None:
        self._coverage_service().ensure_corridors()

    def _select_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        result = self._coverage_service()._select_coverage_corridor_result(
            self._coverage_observation_facts(obs)
        )
        self._apply_coverage_action_result(result.action)
        return result.corridor

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
            facts=None if obs is None else self._coverage_observation_facts(obs),
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

    def _activate_coverage_dig_cut(
        self,
        obs: dict,
        *,
        reset_cycle_metrics: bool,
    ) -> CoverageDigCutActivationResult:
        result = self._coverage_service().activate_dig_cut_corridor(
            self._coverage_observation_facts(obs),
            reset_cycle_metrics=reset_cycle_metrics,
        )
        self._apply_coverage_action_result(result.action)
        return result

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

    def _coverage_debug_snapshot(self) -> CoverageDebugSnapshot:
        return self._coverage_service().coverage_debug_snapshot()

    def _coverage_trace_snapshot(self) -> CoverageTraceSnapshot:
        return self._coverage_service().coverage_trace_snapshot()

    def _coverage_rollout_summary_snapshot(self) -> CoverageRolloutSummarySnapshot:
        return self._coverage_service().coverage_rollout_summary_snapshot()

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
        result = self._coverage_service().complete_dig(
            self._coverage_observation_facts(obs)
        )
        self._apply_coverage_action_result(result)

    def _complete_coverage_dump(self, obs: dict, *, reason: str) -> None:
        result = self._coverage_service().complete_dump(
            self._coverage_observation_facts(obs),
            reason=reason,
        )
        self._apply_coverage_action_result(result)

    def _reject_active_coverage_corridor(self, obs: dict, *, reason: str) -> None:
        result = self._coverage_service().reject_active_corridor(
            self._coverage_observation_facts(obs),
            reason=reason,
        )
        self._apply_coverage_action_result(result)

    def _apply_coverage_action_result(self, result: CoverageActionResult) -> None:
        reason = str(getattr(result, "terminal_stop_reason", "") or "")
        if not reason:
            return
        self._request_coverage_terminal_stop(
            reason,
            replace=bool(getattr(result, "terminal_stop_replace", False)),
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
            facts=None if obs is None else self._coverage_observation_facts(obs),
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
