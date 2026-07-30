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
    ) -> np.ndarray: ...


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

    build_next_dig_cut_plan_for_return: Callable[
        [dict[str, Any]], ReturnTargetPlanTuple
    ]
    build_return_start_envelope_tokens_for_obs: ReturnStartEnvelopeTokenBuilder
    plan_return_relocate_tokens: Callable[[np.ndarray], np.ndarray]
    allow_return_plan_fallback: Callable[[], bool] = lambda: True

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
    ) -> PrimitiveTokenRuntimeCoordinator:
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
        if self.ports.state.pending_dig_locked_execution_plan is not None:
            return None
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
            exact_transition = ports.coverage_state.active_exact_return_transition()
            continuous_plan = (
                ports.coverage_state.coverage_active_continuous_execution_plan
            )
            if continuous_plan is not None:
                if (
                    dict(getattr(continuous_plan, "raw_fields", {}) or {})
                    != dict(raw_fields)
                    or not np.array_equal(
                        np.asarray(
                            getattr(continuous_plan, "dig_token", []),
                            dtype=np.float32,
                        ),
                        target_token,
                    )
                ):
                    raise ValueError(
                        "continuous_goal_contract_invalid:"
                        "return plan content drift"
                    )
                continuous_envelope = getattr(
                    continuous_plan,
                    "return_envelope",
                    None,
                )
                start_envelope_token = np.asarray(
                    getattr(continuous_envelope, "token", []),
                    dtype=np.float32,
                ).reshape(-1)
                if (
                    str(getattr(continuous_envelope, "goal_id", ""))
                    != str(getattr(continuous_plan, "goal_id", ""))
                    or start_envelope_token.shape
                    != (RETURN_START_ENVELOPE_TOKEN_DIM,)
                    or not np.all(np.isfinite(start_envelope_token))
                ):
                    raise ValueError(
                        "return_envelope_contract_invalid:"
                        "continuous goal identity or token"
                    )
                start_envelope_source = "continuous_cut_goal"
                exact_valid_mask = None
                exact_required = False
            elif exact_transition is None:
                start_envelope_token = ports.build_return_start_envelope_tokens_for_obs(
                    obs,
                    dict(raw_fields),
                    corridor_id=int(corridor_id),
                )
                start_envelope_source = str(
                    ports.state.return_start_envelope_token_source
                )
                exact_valid_mask = None
                exact_required = False
            else:
                start_envelope_token = np.asarray(
                    exact_transition.exact_return_start_envelope_tokens,
                    dtype=np.float32,
                ).reshape(-1)
                exact_valid_mask = np.asarray(
                    exact_transition.exact_return_start_envelope_valid_mask,
                    dtype=np.uint8,
                ).reshape(-1)
                if (
                    start_envelope_token.shape != (RETURN_START_ENVELOPE_TOKEN_DIM,)
                    or not np.all(np.isfinite(start_envelope_token))
                    or exact_valid_mask.shape != (RETURN_START_ENVELOPE_TOKEN_DIM,)
                    or not bool(np.all(exact_valid_mask > 0))
                    or not bool(exact_transition.eligible)
                    or str(exact_transition.exemplar_id)
                    != str(ports.coverage_state.coverage_active_execution_exemplar_id)
                    or str(exact_transition.raw_fields_sha256)
                    != str(
                        ports.coverage_state.coverage_active_execution_raw_fields_sha256
                    )
                ):
                    raise ValueError("exact_return_transition_contract_invalid")
                start_envelope_source = (
                    "strict_train_gold_return:"
                    f"{exact_transition.paired_return_exemplar_id}"
                )
                exact_required = True

            if exact_required or continuous_plan is not None:
                use_prior_spatial_bounds = False
                use_prior_qpos_bounds = False
            else:
                use_prior_spatial_bounds = bool(
                    ports.state.return_start_envelope_use_prior_spatial_bounds
                )
                use_prior_qpos_bounds = bool(
                    ports.state.return_start_envelope_use_prior_qpos_bounds
                )
            profile_token = (
                None
                if continuous_plan is not None
                else ports.coverage_state.coverage_active_state_exemplar_profile_token
            )
            pending_depth_profile_tokens = (
                None
                if profile_token is None
                else np.asarray(profile_token, dtype=np.float32)
                .astype(np.float32)
                .copy()
            )
            ports.state.commit_return_plan(
                return_target_tokens=target_token,
                return_start_envelope_tokens=np.asarray(
                    start_envelope_token,
                    dtype=np.float32,
                ),
                return_start_envelope_token_source=start_envelope_source,
                return_start_envelope_use_prior_spatial_bounds=(
                    use_prior_spatial_bounds
                ),
                return_start_envelope_use_prior_qpos_bounds=(use_prior_qpos_bounds),
                return_target_token_source=str(source),
                return_target_fallback_reason=str(fallback_reason),
                return_target_planned_cycle_id=cycle_index,
                pending_dig_cut_cycle_id=cycle_index + 1,
                pending_dig_cut_raw_fields=dict(raw_fields),
                pending_dig_cut_tokens=np.asarray(
                    token,
                    dtype=np.float32,
                ),
                pending_dig_cut_corridor_id=int(corridor_id),
                pending_dig_execution_exemplar_id=str(
                    ports.coverage_state.coverage_active_execution_exemplar_id
                    if exact_required
                    else ""
                ),
                pending_dig_execution_raw_fields_sha256=str(
                    ports.coverage_state.coverage_active_execution_raw_fields_sha256
                    if exact_required
                    else ""
                ),
                pending_dig_paired_return_primitive_episode_id=int(
                    exact_transition.paired_return_primitive_episode_id
                    if exact_required
                    else -1
                ),
                pending_dig_paired_return_exemplar_id=str(
                    exact_transition.paired_return_exemplar_id if exact_required else ""
                ),
                pending_dig_return_transition_artifact_sha256=str(
                    exact_transition.artifact_sha256 if exact_required else ""
                ),
                pending_dig_exact_start_contract_required=bool(exact_required),
                pending_dig_exact_return_envelope_valid_mask=(exact_valid_mask),
                pending_dig_depth_profile_tokens=(pending_depth_profile_tokens),
                pending_dig_state_exemplar_ids=(
                    []
                    if continuous_plan is not None
                    else list(
                        ports.coverage_state.coverage_active_state_exemplar_ids
                    )
                ),
                pending_dig_state_exemplar_distance=float(
                    float("nan")
                    if continuous_plan is not None
                    else ports.coverage_state.coverage_active_state_exemplar_distance
                ),
                pending_dig_locked_execution_plan=continuous_plan,
            )
        except Exception as exc:
            if not bool(ports.allow_return_plan_fallback()):
                self.invalidate_return_plan()
                raise
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
        ports.state.pending_dig_execution_exemplar_id = ""
        ports.state.pending_dig_execution_raw_fields_sha256 = ""
        ports.state.pending_dig_paired_return_primitive_episode_id = -1
        ports.state.pending_dig_paired_return_exemplar_id = ""
        ports.state.pending_dig_return_transition_artifact_sha256 = ""
        ports.state.pending_dig_exact_start_contract_required = False
        ports.state.pending_dig_exact_return_envelope_valid_mask = None
        ports.state.pending_dig_locked_execution_plan = None

    def invalidate_return_plan(self) -> None:
        """Clear every held return token and the pending next-dig plan."""

        ports = self.ports
        ports.state.return_target_planned_cycle_id = -1
        ports.state.return_target_tokens = np.zeros(
            RETURN_TARGET_TOKEN_DIM,
            dtype=np.float32,
        )
        ports.state.return_relocate_tokens = np.zeros(
            RETURN_TARGET_TOKEN_DIM,
            dtype=np.float32,
        )
        ports.state.return_start_envelope_tokens = np.zeros(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float32,
        )
        ports.state.return_target_token_source = "none"
        ports.state.return_start_envelope_token_source = "none"
        ports.state.return_start_envelope_use_prior_spatial_bounds = True
        ports.state.return_start_envelope_use_prior_qpos_bounds = True
        ports.state.return_target_fallback_reason = ""
        self.invalidate_pending_dig_cut_plan()

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
