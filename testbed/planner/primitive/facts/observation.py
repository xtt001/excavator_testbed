"""Policy observation assembly for primitive planner token injection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrimitivePolicyObservationAssemblerPorts:
    """Token provider ports used to assemble low-level policy observations."""

    goal_tokens: Callable[[], Any | None]
    dig_cut_tokens: Callable[[dict[str, Any]], Any | None]
    dig_depth_profile_tokens: Callable[[dict[str, Any]], Any | None]
    return_target_tokens: Callable[[dict[str, Any]], Any | None]
    return_relocate_tokens: Callable[[dict[str, Any]], Any | None]
    return_start_envelope_tokens: Callable[[dict[str, Any]], Any | None]


@dataclass(frozen=True)
class PrimitiveTokenInjectionState:
    """Legacy injected-flag state produced by policy observation assembly."""

    cell_entry_token_injected: bool = False
    dig_cut_token_injected: bool = False
    dig_depth_profile_token_injected: bool = False
    return_target_token_injected: bool = False
    return_relocate_token_injected: bool = False
    return_start_envelope_token_injected: bool = False


@dataclass
class PrimitiveObservationInjectionRuntimeState:
    """Own mutable per-observation token injected compatibility flags."""

    cell_entry_token_injected: bool = False
    dig_cut_token_injected: bool = False
    dig_depth_profile_token_injected: bool = False
    return_target_token_injected: bool = False
    return_relocate_token_injected: bool = False
    return_start_envelope_token_injected: bool = False

    @classmethod
    def fresh(cls) -> PrimitiveObservationInjectionRuntimeState:
        """Return reset-default injected flags for a new observation lifecycle."""

        return cls()

    def clear(self) -> None:
        self.cell_entry_token_injected = False
        self.dig_cut_token_injected = False
        self.dig_depth_profile_token_injected = False
        self.return_target_token_injected = False
        self.return_relocate_token_injected = False
        self.return_start_envelope_token_injected = False

    def apply_token_injection_state(
        self,
        state: PrimitiveTokenInjectionState,
    ) -> None:
        self.cell_entry_token_injected = bool(state.cell_entry_token_injected)
        self.dig_cut_token_injected = bool(state.dig_cut_token_injected)
        self.dig_depth_profile_token_injected = bool(
            state.dig_depth_profile_token_injected
        )
        self.return_target_token_injected = bool(
            state.return_target_token_injected
        )
        self.return_relocate_token_injected = bool(
            state.return_relocate_token_injected
        )
        self.return_start_envelope_token_injected = bool(
            state.return_start_envelope_token_injected
        )

    def to_token_injection_state(self) -> PrimitiveTokenInjectionState:
        return PrimitiveTokenInjectionState(
            cell_entry_token_injected=bool(self.cell_entry_token_injected),
            dig_cut_token_injected=bool(self.dig_cut_token_injected),
            dig_depth_profile_token_injected=bool(
                self.dig_depth_profile_token_injected
            ),
            return_target_token_injected=bool(self.return_target_token_injected),
            return_relocate_token_injected=bool(self.return_relocate_token_injected),
            return_start_envelope_token_injected=bool(
                self.return_start_envelope_token_injected
            ),
        )


@dataclass(frozen=True)
class PrimitivePolicyObservationAssemblyResult:
    """Assembled policy observation plus legacy injected-flag state."""

    policy_obs: dict[str, Any]
    token_injection_state: PrimitiveTokenInjectionState


@dataclass(frozen=True)
class PrimitivePolicyObservationAssembler:
    """Assemble policy observations with ordered primitive token injection."""

    ports: PrimitivePolicyObservationAssemblerPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitivePolicyObservationAssemblerPorts,
    ) -> PrimitivePolicyObservationAssembler:
        return cls(ports=ports)

    def assemble(
        self,
        obs: dict[str, Any],
    ) -> PrimitivePolicyObservationAssemblyResult:
        ports = self.ports
        goal_tokens = ports.goal_tokens()
        dig_cut_tokens = ports.dig_cut_tokens(obs)
        dig_depth_profile_tokens = ports.dig_depth_profile_tokens(obs)
        return_target_tokens = ports.return_target_tokens(obs)
        return_relocate_tokens = ports.return_relocate_tokens(obs)
        return_start_envelope_tokens = ports.return_start_envelope_tokens(obs)

        if (
            goal_tokens is None
            and dig_cut_tokens is None
            and dig_depth_profile_tokens is None
            and return_target_tokens is None
            and return_relocate_tokens is None
            and return_start_envelope_tokens is None
        ):
            return PrimitivePolicyObservationAssemblyResult(
                policy_obs=obs,
                token_injection_state=PrimitiveTokenInjectionState(),
            )

        policy_obs = dict(obs)
        state = PrimitiveTokenInjectionState(
            cell_entry_token_injected=False,
            dig_cut_token_injected=dig_cut_tokens is not None,
            dig_depth_profile_token_injected=dig_depth_profile_tokens is not None,
            return_target_token_injected=return_target_tokens is not None,
            return_relocate_token_injected=return_relocate_tokens is not None,
            return_start_envelope_token_injected=(
                return_start_envelope_tokens is not None
            ),
        )
        if goal_tokens is not None:
            policy_obs["goal_tokens"] = goal_tokens
        if dig_cut_tokens is not None:
            policy_obs["dig_cut_tokens"] = dig_cut_tokens
        if dig_depth_profile_tokens is not None:
            policy_obs["dig_depth_profile_tokens_v1"] = dig_depth_profile_tokens
        if return_target_tokens is not None:
            policy_obs["return_target_tokens"] = return_target_tokens
        if return_relocate_tokens is not None:
            policy_obs["return_relocate_tokens_v1"] = return_relocate_tokens
        if return_start_envelope_tokens is not None:
            policy_obs["return_start_envelope_tokens_v1"] = (
                return_start_envelope_tokens
            )
        return PrimitivePolicyObservationAssemblyResult(
            policy_obs=policy_obs,
            token_injection_state=state,
        )


__all__ = [
    "PrimitiveObservationInjectionRuntimeState",
    "PrimitivePolicyObservationAssembler",
    "PrimitivePolicyObservationAssemblerPorts",
    "PrimitivePolicyObservationAssemblyResult",
    "PrimitiveTokenInjectionState",
]
