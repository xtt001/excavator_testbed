"""Policy observation assembly for primitive ACT dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from testbed.contracts.low_dim import CELL_ENTRY_TOKEN_KEY, GOAL_TOKEN_KEY
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_KEY,
)


@dataclass(frozen=True)
class PolicyObservationRequestConfig:
    dig_skill_name: str = "dig"
    return_skill_name: str = "return"
    bootstrap_skill_name: str = "bootstrap"


@dataclass(frozen=True)
class PolicyObservationRequestFacts:
    active_skill: str
    cell_entry_enabled: bool = False
    dig_cut_planner_enabled: bool = False
    coverage_terminal_stop_requested: bool = False
    bootstrap_policy_present: bool = False
    return_target_planner_enabled: bool = False


POLICY_OBSERVATION_REQUEST_FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("active_skill", "_skill_name"),
    ("cell_entry_enabled", "cell_entry_enabled"),
    ("dig_cut_planner_enabled", "dig_cut_planner_enabled"),
    ("coverage_terminal_stop_requested", "_coverage_terminal_stop_requested"),
    ("bootstrap_policy", "bootstrap_policy"),
    ("return_target_planner_enabled", "return_target_planner_enabled"),
)


def build_policy_observation_request_facts_from_mapping(
    values: Mapping[str, object],
) -> PolicyObservationRequestFacts:
    return PolicyObservationRequestFacts(
        active_skill=str(values["active_skill"]),
        cell_entry_enabled=bool(values["cell_entry_enabled"]),
        dig_cut_planner_enabled=bool(values["dig_cut_planner_enabled"]),
        coverage_terminal_stop_requested=bool(
            values["coverage_terminal_stop_requested"]
        ),
        bootstrap_policy_present=values["bootstrap_policy"] is not None,
        return_target_planner_enabled=bool(
            values["return_target_planner_enabled"]
        ),
    )


@dataclass(frozen=True)
class PolicyObservationTokenRequest:
    goal_tokens: bool = True
    cell_entry_tokens: bool = False
    dig_cut_tokens: bool = False
    dig_depth_profile_tokens: bool = False
    return_target_tokens: bool = False
    return_relocate_tokens: bool = False
    return_start_envelope_tokens: bool = False


@dataclass(frozen=True)
class DigConditioningObservationTokenGateFacts:
    token_requested: bool
    active_skill: str
    coverage_terminal_stop_requested: bool = False


DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("active_skill", "_skill_name"),
    ("coverage_terminal_stop_requested", "_coverage_terminal_stop_requested"),
)


def build_dig_conditioning_token_gate_facts_from_mapping(
    values: Mapping[str, object],
    *,
    token_requested: object,
) -> DigConditioningObservationTokenGateFacts:
    return DigConditioningObservationTokenGateFacts(
        token_requested=bool(token_requested),
        active_skill=str(values["active_skill"]),
        coverage_terminal_stop_requested=bool(
            values["coverage_terminal_stop_requested"]
        ),
    )


@dataclass(frozen=True)
class DigConditioningObservationTokenGateDecision:
    return_token: bool
    should_build_plan: bool


@dataclass(frozen=True)
class PolicyObservationTokens:
    goal_tokens: Any | None = None
    cell_entry_tokens: Any | None = None
    dig_cut_tokens: Any | None = None
    dig_depth_profile_tokens: Any | None = None
    return_target_tokens: Any | None = None
    return_relocate_tokens: Any | None = None
    return_start_envelope_tokens: Any | None = None

    def all_missing(self) -> bool:
        return bool(
            self.goal_tokens is None
            and self.cell_entry_tokens is None
            and self.dig_cut_tokens is None
            and self.dig_depth_profile_tokens is None
            and self.return_target_tokens is None
            and self.return_relocate_tokens is None
            and self.return_start_envelope_tokens is None
        )


@dataclass(frozen=True)
class PolicyObservationAssembly:
    obs: dict[str, Any]
    cell_entry_token_injected: bool = False
    dig_cut_token_injected: bool = False
    dig_depth_profile_token_injected: bool = False
    return_target_token_injected: bool = False
    return_relocate_token_injected: bool = False
    return_start_envelope_token_injected: bool = False


class PolicyObservationAssembler:
    """Gates token requests and merges already-built tokens into policy obs."""

    def token_request(
        self,
        facts: PolicyObservationRequestFacts,
        config: PolicyObservationRequestConfig | None = None,
    ) -> PolicyObservationTokenRequest:
        config = config or PolicyObservationRequestConfig()
        active_skill = str(facts.active_skill)
        dig_active = active_skill == str(config.dig_skill_name)
        return_active = active_skill == str(config.return_skill_name)
        bootstrap_active = active_skill == str(config.bootstrap_skill_name)

        cell_entry_tokens = bool(facts.cell_entry_enabled and dig_active)
        if not bool(facts.dig_cut_planner_enabled):
            dig_cut_tokens = False
        elif bool(facts.coverage_terminal_stop_requested):
            dig_cut_tokens = bool(dig_active)
        else:
            dig_cut_tokens = bool(
                dig_active
                or (bootstrap_active and bool(facts.bootstrap_policy_present))
            )
        return_tokens = bool(
            return_active and bool(facts.return_target_planner_enabled)
        )
        return PolicyObservationTokenRequest(
            goal_tokens=True,
            cell_entry_tokens=cell_entry_tokens,
            dig_cut_tokens=dig_cut_tokens,
            dig_depth_profile_tokens=dig_cut_tokens,
            return_target_tokens=return_tokens,
            return_relocate_tokens=return_tokens,
            return_start_envelope_tokens=return_tokens,
        )

    def token_request_from_mapping(
        self,
        values: Mapping[str, object],
        config: PolicyObservationRequestConfig | None = None,
    ) -> PolicyObservationTokenRequest:
        return self.token_request(
            build_policy_observation_request_facts_from_mapping(values),
            config,
        )

    def dig_conditioning_token_gate(
        self,
        facts: DigConditioningObservationTokenGateFacts,
        config: PolicyObservationRequestConfig | None = None,
    ) -> DigConditioningObservationTokenGateDecision:
        config = config or PolicyObservationRequestConfig()
        if not bool(facts.token_requested):
            return DigConditioningObservationTokenGateDecision(
                return_token=False,
                should_build_plan=False,
            )
        if bool(facts.coverage_terminal_stop_requested):
            return DigConditioningObservationTokenGateDecision(
                return_token=str(facts.active_skill) == str(config.dig_skill_name),
                should_build_plan=False,
            )
        return DigConditioningObservationTokenGateDecision(
            return_token=True,
            should_build_plan=True,
        )

    def dig_conditioning_token_gate_from_mapping(
        self,
        values: Mapping[str, object],
        *,
        token_requested: object,
        config: PolicyObservationRequestConfig | None = None,
    ) -> DigConditioningObservationTokenGateDecision:
        return self.dig_conditioning_token_gate(
            build_dig_conditioning_token_gate_facts_from_mapping(
                values,
                token_requested=token_requested,
            ),
            config,
        )

    def assemble(
        self,
        obs: dict[str, Any],
        tokens: PolicyObservationTokens,
    ) -> PolicyObservationAssembly:
        if tokens.all_missing():
            return PolicyObservationAssembly(obs=obs)

        policy_obs = dict(obs)
        if tokens.goal_tokens is not None:
            policy_obs[GOAL_TOKEN_KEY] = tokens.goal_tokens
        if tokens.cell_entry_tokens is not None:
            policy_obs[CELL_ENTRY_TOKEN_KEY] = tokens.cell_entry_tokens
        if tokens.dig_cut_tokens is not None:
            policy_obs[DIG_CUT_TOKEN_KEY] = tokens.dig_cut_tokens
        if tokens.dig_depth_profile_tokens is not None:
            policy_obs[DIG_DEPTH_PROFILE_TOKEN_KEY] = tokens.dig_depth_profile_tokens
        if tokens.return_target_tokens is not None:
            policy_obs[RETURN_TARGET_TOKEN_KEY] = tokens.return_target_tokens
        if tokens.return_relocate_tokens is not None:
            policy_obs[RETURN_RELOCATE_TOKEN_KEY] = tokens.return_relocate_tokens
        if tokens.return_start_envelope_tokens is not None:
            policy_obs[RETURN_START_ENVELOPE_TOKEN_KEY] = (
                tokens.return_start_envelope_tokens
            )

        return PolicyObservationAssembly(
            obs=policy_obs,
            cell_entry_token_injected=tokens.cell_entry_tokens is not None,
            dig_cut_token_injected=tokens.dig_cut_tokens is not None,
            dig_depth_profile_token_injected=(
                tokens.dig_depth_profile_tokens is not None
            ),
            return_target_token_injected=tokens.return_target_tokens is not None,
            return_relocate_token_injected=tokens.return_relocate_tokens is not None,
            return_start_envelope_token_injected=(
                tokens.return_start_envelope_tokens is not None
            ),
        )
