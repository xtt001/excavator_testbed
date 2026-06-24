"""Primitive token runtime sequencing for policy observation providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState

if TYPE_CHECKING:
    from testbed.planner.primitive.coverage.state import CoverageRuntimeState


ReturnTargetPlanTuple = tuple[np.ndarray, dict[str, float | int], str, str, int]


class ReturnStartEnvelopeTokenBuilder(Protocol):
    """Build return start-envelope tokens with an optional coverage corridor."""

    def __call__(
        self,
        obs: dict[str, Any],
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        ...


@dataclass(frozen=True)
class PrimitiveTokenRuntimePorts:
    """Shell-owned token state and planner algorithm ports."""

    state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    current_skill_name: Callable[[], str]
    bootstrap_policy_available: Callable[[], bool]
    cycle_index: Callable[[], int]
    dig_cut_planner_enabled: Callable[[], bool]
    dig_cut_hold_token_until_skill_exit: Callable[[], bool]
    coverage_terminal_stop_requested: Callable[[], bool]
    return_target_planner_enabled: Callable[[], bool]
    return_target_hold_token_until_skill_exit: Callable[[], bool]

    build_dig_cut_tokens_for_obs: Callable[[dict[str, Any]], np.ndarray]
    build_dig_depth_profile_tokens_for_obs: Callable[[dict[str, Any]], np.ndarray]

    build_next_dig_cut_plan_for_return: Callable[[dict[str, Any]], ReturnTargetPlanTuple]
    build_return_start_envelope_tokens_for_obs: ReturnStartEnvelopeTokenBuilder
    plan_return_relocate_tokens: Callable[[np.ndarray], np.ndarray]

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
            return self.ports.state.dig_cut_tokens.copy()
        self.ensure_dig_cut_plan_for_cycle(obs)
        return self.ports.state.dig_cut_tokens.copy()

    def dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        if not self._dig_tokens_available_for_obs():
            return None
        if self._terminal_stop_cached_dig_tokens_active():
            return self.ports.state.dig_depth_profile_tokens.copy()
        self.ensure_dig_cut_plan_for_cycle(obs)
        return self.ports.state.dig_depth_profile_tokens.copy()

    def ensure_dig_cut_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        ports = self.ports
        if not ports.dig_cut_planner_enabled():
            return
        cycle_index = int(ports.cycle_index())
        if (
            ports.dig_cut_hold_token_until_skill_exit()
            and int(ports.state.dig_cut_planned_cycle_id) == cycle_index
        ):
            return
        ports.state.dig_cut_tokens = ports.build_dig_cut_tokens_for_obs(obs)
        ports.state.dig_depth_profile_tokens = (
            ports.build_dig_depth_profile_tokens_for_obs(obs)
        )
        ports.state.dig_cut_planned_cycle_id = cycle_index

    def return_target_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray | None:
        if not self._return_tokens_available_for_obs():
            return None
        self.ensure_return_target_plan_for_cycle(obs)
        return self.ports.state.return_target_tokens.copy()

    def return_relocate_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray | None:
        if not self._return_tokens_available_for_obs():
            return None
        self.ensure_return_target_plan_for_cycle(obs)
        token = self.ports.plan_return_relocate_tokens(
            self.ports.state.return_target_tokens
        )
        self.ports.state.return_relocate_tokens = token
        return token.copy()

    def return_start_envelope_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        if not self._return_tokens_available_for_obs():
            return None
        self.ensure_return_target_plan_for_cycle(obs)
        return self.ports.state.return_start_envelope_tokens.copy()

    def ensure_return_target_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        ports = self.ports
        if not ports.return_target_planner_enabled():
            return
        cycle_index = int(ports.cycle_index())
        if (
            ports.return_target_hold_token_until_skill_exit()
            and int(ports.state.return_target_planned_cycle_id) == cycle_index
        ):
            return
        try:
            token, raw_fields, source, fallback_reason, corridor_id = (
                ports.build_next_dig_cut_plan_for_return(obs)
            )
            target_token = np.asarray(token, dtype=np.float32).astype(np.float32)
            ports.state.return_target_tokens = target_token
            ports.state.return_start_envelope_tokens = (
                ports.build_return_start_envelope_tokens_for_obs(
                    obs,
                    dict(raw_fields),
                    corridor_id=int(corridor_id),
                )
            )
            ports.state.return_target_token_source = str(source)
            ports.state.return_target_fallback_reason = str(fallback_reason)
            ports.state.return_target_planned_cycle_id = cycle_index
            ports.state.pending_dig_cut_cycle_id = cycle_index + 1
            ports.state.pending_dig_cut_raw_fields = dict(raw_fields)
            ports.state.pending_dig_cut_tokens = (
                np.asarray(token, dtype=np.float32).astype(np.float32)
            )
            ports.state.pending_dig_cut_corridor_id = int(corridor_id)
            profile_token = (
                ports.coverage_state.coverage_active_state_exemplar_profile_token
            )
            ports.state.pending_dig_depth_profile_tokens = (
                None
                if profile_token is None
                else np.asarray(profile_token, dtype=np.float32).astype(
                    np.float32
                ).copy()
            )
            ports.state.pending_dig_state_exemplar_ids = list(
                ports.coverage_state.coverage_active_state_exemplar_ids
            )
            ports.state.pending_dig_state_exemplar_distance = float(
                ports.coverage_state.coverage_active_state_exemplar_distance
            )
        except Exception as exc:
            ports.state.return_target_tokens = np.zeros(
                RETURN_TARGET_TOKEN_DIM, dtype=np.float32
            )
            ports.state.return_start_envelope_tokens = np.zeros(
                RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32
            )
            ports.state.return_target_token_source = "fallback_zero"
            ports.state.return_start_envelope_token_source = "fallback_zero"
            ports.state.return_target_fallback_reason = str(exc)
            ports.state.return_target_planned_cycle_id = cycle_index
            self.invalidate_pending_dig_cut_plan()

    def clear_dig_cut_plan(self) -> None:
        ports = self.ports
        ports.state.dig_cut_planned_cycle_id = -1
        ports.state.dig_cut_tokens = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        ports.state.dig_depth_profile_tokens = np.zeros(
            DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32
        )
        ports.state.dig_cut_token_source = "none"
        ports.state.dig_cut_fallback_reason = ""
        ports.state.dig_cut_token_in_prior_p10_p90 = False
        ports.coverage_state.clear_active_state_exemplar()

    def invalidate_pending_dig_cut_plan(self) -> None:
        ports = self.ports
        ports.state.pending_dig_cut_cycle_id = -1
        ports.state.pending_dig_cut_corridor_id = -1
        ports.state.pending_dig_cut_raw_fields = None
        ports.state.pending_dig_cut_tokens = None
        ports.state.pending_dig_depth_profile_tokens = None
        ports.state.pending_dig_state_exemplar_ids = []
        ports.state.pending_dig_state_exemplar_distance = float("nan")

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
    "ReturnStartEnvelopeTokenBuilder",
]
