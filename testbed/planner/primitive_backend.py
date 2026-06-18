"""Decision backend protocol and legacy FSM adapter for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from testbed.planner.primitive_decision import PrimitiveDecisionResult
from testbed.planner.primitive_execution import PrimitiveTickPreparation


class PrimitiveDecisionBackend(Protocol):
    """Backend interface for choosing the next primitive skill for a tick."""

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult: ...


@dataclass(frozen=True)
class LegacyFSMBackendAdapter:
    """Adapter around the existing already-mutating legacy FSM callback."""

    maybe_switch_skill: Callable[..., None]
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        skill_before = str(preparation.skill_name_before_decision)
        self.maybe_switch_skill(obs=obs, boundary_event=boundary_event)
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=skill_before,
            skill_after=str(self.current_skill_name()),
            switch_reason=str(self.current_switch_reason()),
        )


@dataclass(frozen=True)
class LegacyFSMBootstrapConfig:
    bootstrap_skill_name: str
    pre_dig_align_skill_name: str


@dataclass(frozen=True)
class LegacyFSMBootstrapBranch:
    """Bootstrap branch of the legacy FSM with explicit callbacks."""

    config: LegacyFSMBootstrapConfig
    current_skill_name: Callable[[], str]
    should_end_bootstrap: Callable[..., bool]
    bootstrap_end_mode: Callable[[], str]
    should_pre_dig_align_before_dig: Callable[[], bool]
    set_skill: Callable[[str, str], None]

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        if str(self.current_skill_name()) != str(self.config.bootstrap_skill_name):
            return False
        if self.should_end_bootstrap(obs=obs, boundary_event=boundary_event):
            if self.bootstrap_end_mode() in {
                "first_qualified_dig_start",
                "scripted_qpos",
            }:
                next_skill = (
                    str(self.config.pre_dig_align_skill_name)
                    if self.should_pre_dig_align_before_dig()
                    else "dig"
                )
            else:
                next_skill = "carry"
            self.set_skill(next_skill, f"bootstrap_to_{next_skill}")
        return True


__all__ = [
    "LegacyFSMBackendAdapter",
    "LegacyFSMBootstrapBranch",
    "LegacyFSMBootstrapConfig",
    "PrimitiveDecisionBackend",
]
