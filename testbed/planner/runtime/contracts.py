"""Small runtime contracts shared by planner backends and adapters."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from testbed.planner.runtime.blackboard import PlannerBlackboard

if TYPE_CHECKING:
    from testbed.planner.dig_coverage import CoverageServiceState


@dataclass(frozen=True, slots=True)
class PlannerTickContext:
    """Read-only inputs for one backend tick.

    Coverage state is intentionally referenced, not copied into a generic
    blackboard, while the initial migration keeps coverage ownership in
    ``CoverageServiceState``.
    """

    obs: Mapping[str, Any] = field(default_factory=dict)
    boundary_event: Any | None = None
    coverage_state: CoverageServiceState | None = None
    blackboard: PlannerBlackboard = field(default_factory=PlannerBlackboard)
    services: Mapping[str, Any] = field(default_factory=dict)
    policies: Mapping[str, Any] = field(default_factory=dict)
    config: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "obs", _immutable_mapping(self.obs))
        if not isinstance(self.blackboard, PlannerBlackboard):
            raise TypeError("PlannerTickContext.blackboard must be PlannerBlackboard.")
        object.__setattr__(self, "services", _immutable_mapping(self.services))
        object.__setattr__(self, "policies", _immutable_mapping(self.policies))
        object.__setattr__(self, "config", _immutable_mapping(self.config))
        object.__setattr__(self, "metadata", _immutable_mapping(self.metadata))

    __hash__ = None


@dataclass(frozen=True, slots=True)
class PlannerRuntimeEffect:
    """A requested runtime side effect returned by a planner backend."""

    effect_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_type", str(self.effect_type))
        object.__setattr__(self, "payload", _immutable_mapping(self.payload))

    def __hash__(self) -> int:
        return hash((self.effect_type, _hashable_mapping_items(self.payload)))


@dataclass(frozen=True, slots=True)
class PlannerTickResult:
    """Backend tick decision and ordered runtime effects."""

    node_path: tuple[str, ...] = ()
    status: str = "running"
    reason: str = ""
    effects: tuple[PlannerRuntimeEffect, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "node_path",
            tuple(str(item) for item in self.node_path),
        )
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "effects", tuple(self.effects))
        object.__setattr__(
            self,
            "diagnostics",
            _immutable_mapping(self.diagnostics),
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.node_path,
                self.status,
                self.reason,
                self.effects,
                _hashable_mapping_items(self.diagnostics),
            )
        )


@runtime_checkable
class PlannerBackend(Protocol):
    """Backend protocol for one backend-neutral planner tick."""

    name: str

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        """Return one tick result without mutating the public planner adapter."""


def _immutable_mapping(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


def _hashable_mapping_items(mapping: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(
        sorted(
            (str(key), _hashable_value(value))
            for key, value in mapping.items()
        )
    )


def _hashable_value(value: Any) -> Hashable:
    if isinstance(value, Mapping):
        return _hashable_mapping_items(value)
    if isinstance(value, list | tuple):
        return tuple(_hashable_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_hashable_value(item) for item in value)
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value
