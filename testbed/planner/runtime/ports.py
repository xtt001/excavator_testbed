"""Typed backend dependency ports for planner runtime ticks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class BootstrapEndPredicate(Protocol):
    def __call__(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        """Return whether the bootstrap skill should end for this tick."""


class ObservationPredicate(Protocol):
    def __call__(self, obs: dict[str, Any]) -> bool:
        """Return a boolean gate decision for one observation."""


class BoundaryObservationPredicate(Protocol):
    def __call__(self, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        """Return a boolean gate decision using observation and boundary event."""


class DigToCarryDecision(Protocol):
    ready: bool
    reason: str


class DigToCarryDecisionProvider(Protocol):
    def __call__(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigToCarryDecision:
        """Return a dig-to-carry decision with explicit ready/reason fields."""


class DigTransitionRuntimeProjection(Protocol):
    outcome: Any
    bad_replan_count_increment: int
    exit_guard_replan_count_increment: int
    dig_to_carry_checked: bool
    dig_to_carry_reason: str


class DigTransitionRuntimeProvider(Protocol):
    def __call__(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigTransitionRuntimeProjection:
        """Return the dig transition runtime projection for one tick."""


class CarryTransitionRuntime(Protocol):
    dump_ready_hold_count: int
    outcome: Any


class CarryTransitionRuntimeProvider(Protocol):
    def __call__(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        current_dump_ready_hold_count: int,
    ) -> CarryTransitionRuntime:
        """Return the carry transition runtime state for one tick."""


class DumpTransitionRuntime(Protocol):
    dump_done_hold_count: int
    outcome: Any


class DumpTransitionRuntimeProvider(Protocol):
    def __call__(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        current_dump_done_hold_count: int,
    ) -> DumpTransitionRuntime:
        """Return the dump transition runtime state for one tick."""


class ReturnTransitionRuntime(Protocol):
    outcome: Any
    projection: Any


class ReturnTransitionRuntimeProvider(Protocol):
    def __call__(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        previous_next_dig_event_seen: bool,
    ) -> ReturnTransitionRuntime:
        """Return the return-to-dig transition runtime state for one tick."""


class BoolProvider(Protocol):
    def __call__(self) -> bool:
        """Return a boolean runtime/config value."""


class IntProvider(Protocol):
    def __call__(self) -> int:
        """Return an integer runtime/config value."""


class RuntimeConfigProvider(Protocol):
    def __call__(self) -> Any:
        """Return a runtime config object for a backend-owned decision."""


class ObservationOutcomeBuilder(Protocol):
    def __call__(self, obs: dict[str, Any]) -> Any:
        """Return a domain outcome for one observation."""


@dataclass(frozen=True, slots=True)
class PlannerSkillNames:
    """Active-skill names shared by planner backend branch boundaries."""

    bootstrap: str
    pre_dig_align: str
    dig: str
    carry: str
    dump: str
    return_skill: str

    def __post_init__(self) -> None:
        for field_name in (
            "bootstrap",
            "pre_dig_align",
            "dig",
            "carry",
            "dump",
            "return_skill",
        ):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))


LegacyFsmSkillNames = PlannerSkillNames


@dataclass(frozen=True, slots=True)
class LegacyFsmBootstrapPorts:
    """Bootstrap transition dependencies used by the legacy FSM backend."""

    service: Any
    should_end: BootstrapEndPredicate
    should_pre_dig_align_before_dig: BoolProvider
    config: RuntimeConfigProvider


@dataclass(frozen=True, slots=True)
class LegacyFsmPreDigAlignmentPorts:
    """Pre-dig alignment outcome dependency for the legacy FSM backend."""

    compute_outcome: ObservationOutcomeBuilder


@dataclass(frozen=True, slots=True)
class PlannerDigTransitionPorts:
    """Dig transition dependencies shared by planner backends."""

    transition_runtime: DigTransitionRuntimeProvider | None = None
    lifecycle_gate: Any | None = None
    exit_guard_ready: ObservationPredicate | None = None
    bad_replan_ready: ObservationPredicate | None = None
    complete_boundary_low_payload: BoundaryObservationPredicate | None = None
    dig_to_carry_decision: DigToCarryDecisionProvider | None = None


LegacyFsmDigTransitionPorts = PlannerDigTransitionPorts


@dataclass(frozen=True, slots=True)
class PlannerDumpLifecyclePorts:
    """Carry/dump lifecycle dependencies shared by planner backends."""

    carry_transition_runtime: CarryTransitionRuntimeProvider
    dump_transition_runtime: DumpTransitionRuntimeProvider


LegacyFsmDumpLifecyclePorts = PlannerDumpLifecyclePorts


@dataclass(frozen=True, slots=True)
class PlannerReturnTransitionPorts:
    """Return-to-dig transition dependency shared by planner backends."""

    return_transition_runtime: ReturnTransitionRuntimeProvider


LegacyFsmReturnTransitionPorts = PlannerReturnTransitionPorts


@dataclass(frozen=True, slots=True)
class LegacyFsmBackendPorts:
    """Typed dependency bundle for the legacy FSM backend."""

    skill_names: LegacyFsmSkillNames
    bootstrap_transition: LegacyFsmBootstrapPorts | None = None
    pre_dig_alignment: LegacyFsmPreDigAlignmentPorts | None = None
    dig_transition: LegacyFsmDigTransitionPorts | None = None
    dump_lifecycle: LegacyFsmDumpLifecyclePorts | None = None
    return_transition: LegacyFsmReturnTransitionPorts | None = None


@dataclass(frozen=True, slots=True)
class PlannerBackendPorts:
    """Typed backend dependency ports carried by one planner tick context."""

    legacy_fsm: LegacyFsmBackendPorts | None = None
    skill_names: PlannerSkillNames | None = None
    dig_transition: PlannerDigTransitionPorts | None = None
    dump_lifecycle: PlannerDumpLifecyclePorts | None = None
    return_transition: PlannerReturnTransitionPorts | None = None


__all__ = [
    "BoolProvider",
    "BootstrapEndPredicate",
    "BoundaryObservationPredicate",
    "CarryTransitionRuntime",
    "CarryTransitionRuntimeProvider",
    "DigToCarryDecision",
    "DigToCarryDecisionProvider",
    "DigTransitionRuntimeProjection",
    "DigTransitionRuntimeProvider",
    "DumpTransitionRuntime",
    "DumpTransitionRuntimeProvider",
    "IntProvider",
    "LegacyFsmBackendPorts",
    "LegacyFsmBootstrapPorts",
    "LegacyFsmDigTransitionPorts",
    "LegacyFsmDumpLifecyclePorts",
    "LegacyFsmPreDigAlignmentPorts",
    "LegacyFsmReturnTransitionPorts",
    "LegacyFsmSkillNames",
    "ObservationOutcomeBuilder",
    "ObservationPredicate",
    "PlannerBackendPorts",
    "PlannerDigTransitionPorts",
    "PlannerDumpLifecyclePorts",
    "PlannerReturnTransitionPorts",
    "PlannerSkillNames",
    "ReturnTransitionRuntime",
    "ReturnTransitionRuntimeProvider",
    "RuntimeConfigProvider",
]
