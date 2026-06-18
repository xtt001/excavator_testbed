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


class KeywordBoundaryObservationPredicate(Protocol):
    def __call__(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        """Return a boolean gate decision using keyword-only tick inputs."""


class DirectHandoffPredicate(Protocol):
    def __call__(
        self,
        obs: dict[str, Any],
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        """Return whether return-to-dig direct handoff is ready."""


class BoolProvider(Protocol):
    def __call__(self) -> bool:
        """Return a boolean runtime/config value."""


class IntProvider(Protocol):
    def __call__(self) -> int:
        """Return an integer runtime/config value."""


class StringProvider(Protocol):
    def __call__(self) -> str:
        """Return a string runtime value."""


class RuntimeConfigProvider(Protocol):
    def __call__(self) -> Any:
        """Return a runtime config object for a backend-owned decision."""


class ObservationOutcomeBuilder(Protocol):
    def __call__(self, obs: dict[str, Any]) -> Any:
        """Return a domain outcome for one observation."""


class CarryTransitionRuntimeRequestBuilder(Protocol):
    def __call__(
        self,
        *,
        release_safety_done: bool,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool,
        current_dump_ready_hold_count: int,
    ) -> Any:
        """Build a carry-to-dump transition runtime request."""


class DumpTransitionRuntimeRequestBuilder(Protocol):
    def __call__(
        self,
        *,
        dump_done_use_boundary_event: bool,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool,
        current_dump_done_hold_count: int,
    ) -> Any:
        """Build a dump-to-return transition runtime request."""


@dataclass(frozen=True, slots=True)
class LegacyFsmSkillNames:
    """Active-skill names used by the legacy FSM backend branch boundary."""

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
class LegacyFsmDigTransitionPorts:
    """Dig transition gate dependencies used by the legacy FSM backend."""

    lifecycle_gate: Any
    exit_guard_ready: ObservationPredicate
    bad_replan_ready: ObservationPredicate
    complete_boundary_low_payload: BoundaryObservationPredicate
    dig_to_carry_ready: KeywordBoundaryObservationPredicate
    dig_to_carry_reason: StringProvider


@dataclass(frozen=True, slots=True)
class LegacyFsmBoundaryProfilePorts:
    """Boundary profile dependency shared by dump and return transitions."""

    semantic_boundary_profile_active: BoolProvider


@dataclass(frozen=True, slots=True)
class LegacyFsmDumpLifecyclePorts:
    """Carry/dump lifecycle dependencies used by the legacy FSM backend."""

    lifecycle_gate: Any
    build_carry_transition_runtime_request: CarryTransitionRuntimeRequestBuilder
    build_dump_transition_runtime_request: DumpTransitionRuntimeRequestBuilder
    carry_release_safety_done: ObservationPredicate
    dump_ready_hold_steps: IntProvider
    dump_done_hold_steps: IntProvider
    dump_done_use_boundary_event: BoolProvider
    dump_ready: ObservationPredicate
    dump_done: ObservationPredicate


@dataclass(frozen=True, slots=True)
class LegacyFsmReturnTransitionPorts:
    """Return-to-dig transition dependencies used by the legacy FSM backend."""

    service: Any
    handoff_ready: ObservationPredicate
    direct_handoff_ready: DirectHandoffPredicate
    shallow_guard_ready: KeywordBoundaryObservationPredicate


@dataclass(frozen=True, slots=True)
class LegacyFsmBackendPorts:
    """Typed dependency bundle for the legacy FSM backend."""

    skill_names: LegacyFsmSkillNames
    bootstrap_transition: LegacyFsmBootstrapPorts | None = None
    pre_dig_alignment: LegacyFsmPreDigAlignmentPorts | None = None
    dig_transition: LegacyFsmDigTransitionPorts | None = None
    dump_lifecycle: LegacyFsmDumpLifecyclePorts | None = None
    return_transition: LegacyFsmReturnTransitionPorts | None = None
    boundary_profile: LegacyFsmBoundaryProfilePorts | None = None


@dataclass(frozen=True, slots=True)
class PlannerBackendPorts:
    """Typed backend dependency ports carried by one planner tick context."""

    legacy_fsm: LegacyFsmBackendPorts | None = None


__all__ = [
    "BoolProvider",
    "BootstrapEndPredicate",
    "BoundaryObservationPredicate",
    "CarryTransitionRuntimeRequestBuilder",
    "DirectHandoffPredicate",
    "DumpTransitionRuntimeRequestBuilder",
    "IntProvider",
    "KeywordBoundaryObservationPredicate",
    "LegacyFsmBackendPorts",
    "LegacyFsmBootstrapPorts",
    "LegacyFsmBoundaryProfilePorts",
    "LegacyFsmDigTransitionPorts",
    "LegacyFsmDumpLifecyclePorts",
    "LegacyFsmPreDigAlignmentPorts",
    "LegacyFsmReturnTransitionPorts",
    "LegacyFsmSkillNames",
    "ObservationOutcomeBuilder",
    "ObservationPredicate",
    "PlannerBackendPorts",
    "RuntimeConfigProvider",
    "StringProvider",
]
