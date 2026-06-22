"""Primitive token runtime sequencing for policy observation providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)


ReturnTargetPlanTuple = tuple[np.ndarray, dict[str, float | int], str, str, int]


@dataclass(frozen=True)
class PrimitiveTokenRuntimePorts:
    """Shell-owned token state and planner algorithm ports."""

    current_skill_name: Callable[[], str]
    bootstrap_policy_available: Callable[[], bool]
    cycle_index: Callable[[], int]
    dig_cut_planner_enabled: Callable[[], bool]
    dig_cut_hold_token_until_skill_exit: Callable[[], bool]
    coverage_terminal_stop_requested: Callable[[], bool]
    return_target_planner_enabled: Callable[[], bool]
    return_target_hold_token_until_skill_exit: Callable[[], bool]

    get_dig_cut_planned_cycle_id: Callable[[], int]
    set_dig_cut_planned_cycle_id: Callable[[int], None]
    get_dig_cut_tokens: Callable[[], np.ndarray]
    set_dig_cut_tokens: Callable[[np.ndarray], None]
    get_dig_depth_profile_tokens: Callable[[], np.ndarray]
    set_dig_depth_profile_tokens: Callable[[np.ndarray], None]
    set_dig_cut_token_source: Callable[[str], None]
    set_dig_cut_fallback_reason: Callable[[str], None]
    set_dig_cut_token_in_prior_p10_p90: Callable[[bool], None]
    build_dig_cut_tokens_for_obs: Callable[[dict[str, Any]], np.ndarray]
    build_dig_depth_profile_tokens_for_obs: Callable[[dict[str, Any]], np.ndarray]

    get_return_target_planned_cycle_id: Callable[[], int]
    set_return_target_planned_cycle_id: Callable[[int], None]
    get_return_target_tokens: Callable[[], np.ndarray]
    set_return_target_tokens: Callable[[np.ndarray], None]
    get_return_relocate_tokens: Callable[[], np.ndarray]
    set_return_relocate_tokens: Callable[[np.ndarray], None]
    get_return_start_envelope_tokens: Callable[[], np.ndarray]
    set_return_start_envelope_tokens: Callable[[np.ndarray], None]
    set_return_target_token_source: Callable[[str], None]
    set_return_start_envelope_token_source: Callable[[str], None]
    set_return_target_fallback_reason: Callable[[str], None]
    build_next_dig_cut_plan_for_return: Callable[[dict[str, Any]], ReturnTargetPlanTuple]
    build_return_start_envelope_tokens_for_obs: Callable[
        [dict[str, Any], dict[str, float | int]],
        np.ndarray,
    ]
    plan_return_relocate_tokens: Callable[[np.ndarray], np.ndarray]

    set_pending_dig_cut_cycle_id: Callable[[int], None]
    set_pending_dig_cut_corridor_id: Callable[[int], None]
    set_pending_dig_cut_raw_fields: Callable[[dict[str, float | int] | None], None]
    set_pending_dig_cut_tokens: Callable[[np.ndarray | None], None]
    set_pending_dig_depth_profile_tokens: Callable[[np.ndarray | None], None]
    set_pending_dig_state_exemplar_ids: Callable[[list[str]], None]
    set_pending_dig_state_exemplar_distance: Callable[[float], None]
    get_coverage_active_state_exemplar_ids: Callable[[], list[str]]
    get_coverage_active_state_exemplar_distance: Callable[[], float]
    get_coverage_active_state_exemplar_profile_token: Callable[[], np.ndarray | None]
    clear_active_state_exemplar: Callable[[], None]

    dig_skill_name: str = "dig"
    return_skill_name: str = "return"
    bootstrap_skill_name: str = "bootstrap"


@dataclass(frozen=True)
class PrimitiveTokenRuntimeCoordinator:
    """Own runtime sequencing for primitive dig and return token state."""

    ports: PrimitiveTokenRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveTokenRuntimePorts,
    ) -> "PrimitiveTokenRuntimeCoordinator":
        return cls(ports=ports)

    def dig_cut_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray | None:
        if not self._dig_tokens_available_for_obs():
            return None
        if self._terminal_stop_cached_dig_tokens_active():
            return self.ports.get_dig_cut_tokens().copy()
        self.ensure_dig_cut_plan_for_cycle(obs)
        return self.ports.get_dig_cut_tokens().copy()

    def dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        if not self._dig_tokens_available_for_obs():
            return None
        if self._terminal_stop_cached_dig_tokens_active():
            return self.ports.get_dig_depth_profile_tokens().copy()
        self.ensure_dig_cut_plan_for_cycle(obs)
        return self.ports.get_dig_depth_profile_tokens().copy()

    def ensure_dig_cut_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        ports = self.ports
        if not ports.dig_cut_planner_enabled():
            return
        cycle_index = int(ports.cycle_index())
        if (
            ports.dig_cut_hold_token_until_skill_exit()
            and int(ports.get_dig_cut_planned_cycle_id()) == cycle_index
        ):
            return
        ports.set_dig_cut_tokens(ports.build_dig_cut_tokens_for_obs(obs))
        ports.set_dig_depth_profile_tokens(
            ports.build_dig_depth_profile_tokens_for_obs(obs)
        )
        ports.set_dig_cut_planned_cycle_id(cycle_index)

    def return_target_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray | None:
        if not self._return_tokens_available_for_obs():
            return None
        self.ensure_return_target_plan_for_cycle(obs)
        return self.ports.get_return_target_tokens().copy()

    def return_relocate_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray | None:
        if not self._return_tokens_available_for_obs():
            return None
        self.ensure_return_target_plan_for_cycle(obs)
        token = self.ports.plan_return_relocate_tokens(
            self.ports.get_return_target_tokens()
        )
        self.ports.set_return_relocate_tokens(token)
        return token.copy()

    def return_start_envelope_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        if not self._return_tokens_available_for_obs():
            return None
        self.ensure_return_target_plan_for_cycle(obs)
        return self.ports.get_return_start_envelope_tokens().copy()

    def ensure_return_target_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        ports = self.ports
        if not ports.return_target_planner_enabled():
            return
        cycle_index = int(ports.cycle_index())
        if (
            ports.return_target_hold_token_until_skill_exit()
            and int(ports.get_return_target_planned_cycle_id()) == cycle_index
        ):
            return
        try:
            token, raw_fields, source, fallback_reason, corridor_id = (
                ports.build_next_dig_cut_plan_for_return(obs)
            )
            target_token = np.asarray(token, dtype=np.float32).astype(np.float32)
            ports.set_return_target_tokens(target_token)
            ports.set_return_start_envelope_tokens(
                ports.build_return_start_envelope_tokens_for_obs(
                    obs,
                    dict(raw_fields),
                    corridor_id=int(corridor_id),
                )
            )
            ports.set_return_target_token_source(str(source))
            ports.set_return_target_fallback_reason(str(fallback_reason))
            ports.set_return_target_planned_cycle_id(cycle_index)
            ports.set_pending_dig_cut_cycle_id(cycle_index + 1)
            ports.set_pending_dig_cut_raw_fields(dict(raw_fields))
            ports.set_pending_dig_cut_tokens(
                np.asarray(token, dtype=np.float32).astype(np.float32)
            )
            ports.set_pending_dig_cut_corridor_id(int(corridor_id))
            profile_token = ports.get_coverage_active_state_exemplar_profile_token()
            ports.set_pending_dig_depth_profile_tokens(
                None
                if profile_token is None
                else np.asarray(profile_token, dtype=np.float32).astype(
                    np.float32
                ).copy()
            )
            ports.set_pending_dig_state_exemplar_ids(
                list(ports.get_coverage_active_state_exemplar_ids())
            )
            ports.set_pending_dig_state_exemplar_distance(
                float(ports.get_coverage_active_state_exemplar_distance())
            )
        except Exception as exc:
            ports.set_return_target_tokens(
                np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
            )
            ports.set_return_start_envelope_tokens(
                np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
            )
            ports.set_return_target_token_source("fallback_zero")
            ports.set_return_start_envelope_token_source("fallback_zero")
            ports.set_return_target_fallback_reason(str(exc))
            ports.set_return_target_planned_cycle_id(cycle_index)
            self.invalidate_pending_dig_cut_plan()

    def clear_dig_cut_plan(self) -> None:
        ports = self.ports
        ports.set_dig_cut_planned_cycle_id(-1)
        ports.set_dig_cut_tokens(np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32))
        ports.set_dig_depth_profile_tokens(
            np.zeros(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
        )
        ports.set_dig_cut_token_source("none")
        ports.set_dig_cut_fallback_reason("")
        ports.set_dig_cut_token_in_prior_p10_p90(False)
        ports.clear_active_state_exemplar()

    def invalidate_pending_dig_cut_plan(self) -> None:
        ports = self.ports
        ports.set_pending_dig_cut_cycle_id(-1)
        ports.set_pending_dig_cut_corridor_id(-1)
        ports.set_pending_dig_cut_raw_fields(None)
        ports.set_pending_dig_cut_tokens(None)
        ports.set_pending_dig_depth_profile_tokens(None)
        ports.set_pending_dig_state_exemplar_ids([])
        ports.set_pending_dig_state_exemplar_distance(float("nan"))

    def _dig_tokens_available_for_obs(self) -> bool:
        ports = self.ports
        if not ports.dig_cut_planner_enabled():
            return False
        skill_name = str(ports.current_skill_name())
        if ports.coverage_terminal_stop_requested():
            return skill_name == str(ports.dig_skill_name)
        if skill_name == str(ports.dig_skill_name):
            return True
        return bool(
            skill_name == str(ports.bootstrap_skill_name)
            and ports.bootstrap_policy_available()
        )

    def _return_tokens_available_for_obs(self) -> bool:
        ports = self.ports
        return bool(
            str(ports.current_skill_name()) == str(ports.return_skill_name)
            and ports.return_target_planner_enabled()
        )

    def _terminal_stop_cached_dig_tokens_active(self) -> bool:
        ports = self.ports
        return bool(
            ports.coverage_terminal_stop_requested()
            and str(ports.current_skill_name()) == str(ports.dig_skill_name)
        )


__all__ = [
    "PrimitiveTokenRuntimeCoordinator",
    "PrimitiveTokenRuntimePorts",
]
