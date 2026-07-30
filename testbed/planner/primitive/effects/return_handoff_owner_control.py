"""Diagnostic activation control for return start-envelope owners."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from testbed.planner.primitive.effects.return_handoff import (
        ReturnStartEnvelopeGateConfig,
    )

_CONFIG_KEY = "return_start_envelope_owner_control"
_CONTACT_OWNER = "token"
_DEPTH_OWNER = "runtime_prior_p05_p95"


@dataclass(frozen=True)
class ReturnStartEnvelopeOwnerControlConfig:
    """Request-local diagnostic owner override with delayed activation."""

    enabled: bool = False
    diagnostic_only: bool = False
    min_completed_dump_count: int = 7
    contact_owner: str = _CONTACT_OWNER
    depth_owner: str = _DEPTH_OWNER

    @classmethod
    def from_box_emptying_mapping(
        cls,
        box_emptying: Mapping[str, Any] | None,
    ) -> ReturnStartEnvelopeOwnerControlConfig:
        root = dict(box_emptying or {})
        raw = root.get(_CONFIG_KEY, {})
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ValueError(f"{_CONFIG_KEY} must be a mapping")
        enabled = raw.get("enabled", False)
        diagnostic_only = raw.get("diagnostic_only", False)
        if not isinstance(enabled, bool):
            raise ValueError(f"{_CONFIG_KEY}.enabled must be boolean")
        if not isinstance(diagnostic_only, bool):
            raise ValueError(
                f"{_CONFIG_KEY}.diagnostic_only must be boolean"
            )
        min_completed = raw.get("min_completed_dump_count", 7)
        if isinstance(min_completed, bool) or not isinstance(
            min_completed,
            int,
        ):
            raise ValueError(
                f"{_CONFIG_KEY}.min_completed_dump_count must be integer"
            )
        contact_owner = str(
            raw.get("contact_owner", _CONTACT_OWNER)
        )
        depth_owner = str(raw.get("depth_owner", _DEPTH_OWNER))
        if enabled and not diagnostic_only:
            raise ValueError(
                f"enabled {_CONFIG_KEY} requires diagnostic_only=true"
            )
        if min_completed < 0:
            raise ValueError(
                f"{_CONFIG_KEY}.min_completed_dump_count must be nonnegative"
            )
        if contact_owner != _CONTACT_OWNER:
            raise ValueError(
                f"{_CONFIG_KEY}.contact_owner must be {_CONTACT_OWNER}"
            )
        if depth_owner != _DEPTH_OWNER:
            raise ValueError(
                f"{_CONFIG_KEY}.depth_owner must be {_DEPTH_OWNER}"
            )
        return cls(
            enabled=enabled,
            diagnostic_only=diagnostic_only,
            min_completed_dump_count=min_completed,
            contact_owner=contact_owner,
            depth_owner=depth_owner,
        )


@dataclass(frozen=True)
class ReturnStartEnvelopeOwnerControlDecision:
    """Effective gate config and append-only diagnostic evidence."""

    active: bool
    gate_config: ReturnStartEnvelopeGateConfig
    log_fields: dict[str, Any]


@dataclass(frozen=True)
class ReturnStartEnvelopeOwnerControlService:
    """Apply the owner override only after its completed-dump boundary."""

    config: ReturnStartEnvelopeOwnerControlConfig

    def resolve(
        self,
        *,
        base_gate: ReturnStartEnvelopeGateConfig,
        completed_dump_count: int,
    ) -> ReturnStartEnvelopeOwnerControlDecision:
        count = int(completed_dump_count)
        active = bool(
            self.config.enabled
            and count >= int(self.config.min_completed_dump_count)
        )
        gate = (
            replace(
                base_gate,
                require_contact=False,
                plane_depth_mode="range",
            )
            if active
            else base_gate
        )
        return ReturnStartEnvelopeOwnerControlDecision(
            active=active,
            gate_config=gate,
            log_fields={
                "enabled": bool(self.config.enabled),
                "diagnostic_only": bool(self.config.diagnostic_only),
                "active": active,
                "completed_dump_count": count,
                "min_completed_dump_count": int(
                    self.config.min_completed_dump_count
                ),
                "contact_owner": str(self.config.contact_owner),
                "depth_owner": str(self.config.depth_owner),
            },
        )


__all__ = [
    "ReturnStartEnvelopeOwnerControlConfig",
    "ReturnStartEnvelopeOwnerControlDecision",
    "ReturnStartEnvelopeOwnerControlService",
]
