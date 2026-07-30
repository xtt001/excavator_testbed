"""Diagnostic-only bounded stop contract for one cycle-one dig probe."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from testbed.planner.box_emptying.safety_interlock import (
    SafetyActionDecision,
)

BOUNDED_DIG_PROBE_TARGET_CYCLE_INDEX = 1
BOUNDED_DIG_PROBE_MAX_DIG_STEPS = 500
BOUNDED_DIG_PROBE_ENVELOPE_REASON = (
    "bounded_dig_probe_stop:carry_start_envelope_ready"
)
BOUNDED_DIG_PROBE_STEP_LIMIT_REASON = (
    "bounded_dig_probe_stop:dig_step_limit"
)
BOUNDED_DIG_PROBE_TERMINAL_REASON_PREFIX = "bounded_dig_probe_stop"


@dataclass(frozen=True)
class BoundedDigProbeStopConfig:
    """Locked diagnostic contract; it is inert unless explicitly enabled."""

    enabled: bool = False
    diagnostic_only: bool = True
    target_cycle_index: int = BOUNDED_DIG_PROBE_TARGET_CYCLE_INDEX
    max_dig_steps: int = BOUNDED_DIG_PROBE_MAX_DIG_STEPS

    @classmethod
    def from_box_emptying_mapping(
        cls,
        box_emptying: Mapping[str, Any] | None,
    ) -> BoundedDigProbeStopConfig:
        box_values = dict(box_emptying or {})
        raw_value = box_values.get("bounded_dig_probe_stop", {})
        if raw_value is None:
            raw_value = {}
        if not isinstance(raw_value, Mapping):
            raise ValueError(
                "box_emptying.bounded_dig_probe_stop must be a mapping"
            )
        raw = dict(raw_value)
        enabled = bool(raw.get("enabled", False))
        target_cycle_index = int(
            raw.get(
                "target_cycle_index",
                BOUNDED_DIG_PROBE_TARGET_CYCLE_INDEX,
            )
        )
        max_dig_steps = int(
            raw.get("max_dig_steps", BOUNDED_DIG_PROBE_MAX_DIG_STEPS)
        )
        if enabled:
            safety_enabled = bool(
                box_values.get(
                    "safety_enabled",
                    box_values.get("enabled", False),
                )
            )
            if not safety_enabled:
                raise ValueError(
                    "enabled bounded dig probe stop requires the safety "
                    "interlock"
                )
            if target_cycle_index != BOUNDED_DIG_PROBE_TARGET_CYCLE_INDEX:
                raise ValueError(
                    "bounded dig probe stop is locked to cycle_index=1"
                )
            if max_dig_steps != BOUNDED_DIG_PROBE_MAX_DIG_STEPS:
                raise ValueError(
                    "bounded dig probe stop is locked to max_dig_steps=500"
                )
            if raw.get("diagnostic_only", True) is not True:
                raise ValueError(
                    "bounded dig probe stop must remain diagnostic_only"
                )
        return cls(
            enabled=enabled,
            target_cycle_index=target_cycle_index,
            max_dig_steps=max_dig_steps,
        )


@dataclass
class BoundedDigProbeStopContract:
    """Latch the first bounded-probe stop and wait for a real neutral ack."""

    config: BoundedDigProbeStopConfig = field(
        default_factory=BoundedDigProbeStopConfig
    )
    _trigger_kind: str = field(default="", init=False)
    _trigger_reason: str = field(default="", init=False)
    _trigger_step: int = field(default=-1, init=False)
    _neutral_request_emitted: bool = field(default=False, init=False)
    _awaiting_neutral_ack: bool = field(default=False, init=False)
    _neutral_acknowledged: bool = field(default=False, init=False)
    _terminal_requested: bool = field(default=False, init=False)

    def reset(self) -> None:
        self._trigger_kind = ""
        self._trigger_reason = ""
        self._trigger_step = -1
        self._neutral_request_emitted = False
        self._awaiting_neutral_ack = False
        self._neutral_acknowledged = False
        self._terminal_requested = False

    def observe_dig_state(
        self,
        *,
        step_id: int,
        cycle_index: int,
        dig_step_count: int,
        envelope_ready: bool,
    ) -> str | None:
        """Return one external-neutral reason for an ordinary probe bound."""

        if not self._eligible(cycle_index) or self._trigger_kind:
            return None
        # On the return->dig switch tick the action is already dispatched by
        # the newly reset dig ACT, but the carry-envelope debug state has not
        # yet been evaluated for the new dig and may still reflect cycle 0.
        # The first trustworthy envelope observation is dig_step_count >= 1.
        if bool(envelope_ready) and int(dig_step_count) >= 1:
            reason = BOUNDED_DIG_PROBE_ENVELOPE_REASON
            self._latch(
                kind="envelope_ready",
                reason=reason,
                step_id=step_id,
            )
        elif int(dig_step_count) >= int(self.config.max_dig_steps):
            reason = BOUNDED_DIG_PROBE_STEP_LIMIT_REASON
            self._latch(
                kind="dig_step_limit",
                reason=reason,
                step_id=step_id,
            )
        else:
            return None
        self._neutral_request_emitted = True
        return reason

    def observe_safety_decision(
        self,
        decision: SafetyActionDecision,
        *,
        cycle_index: int,
        step_id: int = -1,
    ) -> None:
        """Observe, but never weaken or replace, the owning safety decision."""

        if not self.config.enabled:
            return
        if not self._trigger_kind:
            if not self._eligible(cycle_index):
                return
            kind = _safety_trigger_kind(decision.reason)
            if not kind or not decision.awaiting_neutral_ack:
                return
            self._latch(
                kind=kind,
                reason=str(decision.reason),
                step_id=step_id,
            )
        if decision.awaiting_neutral_ack:
            self._awaiting_neutral_ack = True
        if decision.neutral_acknowledged:
            self._awaiting_neutral_ack = False
            self._neutral_acknowledged = True
            self._terminal_requested = True

    def apply_after_safety_decision(
        self,
        decision: SafetyActionDecision,
        *,
        step_id: int,
        cycle_index: int,
        dig_step_count: int,
        envelope_ready: bool,
        request_terminal_neutral: Callable[[str], None],
        refilter_after_request: Callable[[], SafetyActionDecision],
    ) -> SafetyActionDecision:
        """Apply probe bounds only after the safety owner had first refusal."""

        self.observe_safety_decision(
            decision,
            cycle_index=cycle_index,
            step_id=step_id,
        )
        if not self.config.enabled or str(decision.reason):
            return decision
        reason = self.observe_dig_state(
            step_id=step_id,
            cycle_index=cycle_index,
            dig_step_count=dig_step_count,
            envelope_ready=envelope_ready,
        )
        if reason is None:
            return decision
        request_terminal_neutral(reason)
        neutral = refilter_after_request()
        self.observe_safety_decision(
            neutral,
            cycle_index=cycle_index,
            step_id=step_id,
        )
        return neutral

    def terminal_stop_requested(self) -> bool:
        return bool(
            self.config.enabled
            and self._trigger_kind
            and self._neutral_acknowledged
            and self._terminal_requested
        )

    def terminal_stop_reason(self) -> str:
        if not self.terminal_stop_requested():
            return ""
        return (
            f"{BOUNDED_DIG_PROBE_TERMINAL_REASON_PREFIX}:"
            f"{self._trigger_kind}"
        )

    def debug_fields(self) -> dict[str, Any]:
        return {
            "bounded_dig_probe_stop_enabled": bool(self.config.enabled),
            "bounded_dig_probe_stop_diagnostic_only": True,
            "bounded_dig_probe_stop_target_cycle_index": int(
                self.config.target_cycle_index
            ),
            "bounded_dig_probe_stop_max_dig_steps": int(
                self.config.max_dig_steps
            ),
            "bounded_dig_probe_stop_trigger_kind": str(self._trigger_kind),
            "bounded_dig_probe_stop_trigger_reason": str(
                self._trigger_reason
            ),
            "bounded_dig_probe_stop_trigger_step": int(self._trigger_step),
            "bounded_dig_probe_stop_neutral_request_emitted": bool(
                self._neutral_request_emitted
            ),
            "bounded_dig_probe_stop_awaiting_neutral_ack": bool(
                self._awaiting_neutral_ack
            ),
            "bounded_dig_probe_stop_neutral_acknowledged": bool(
                self._neutral_acknowledged
            ),
            "bounded_dig_probe_stop_terminal_requested": bool(
                self._terminal_requested
            ),
            "bounded_dig_probe_stop_terminal_reason": (
                self.terminal_stop_reason()
            ),
        }

    def _eligible(self, cycle_index: int) -> bool:
        return bool(
            self.config.enabled
            and int(cycle_index) == int(self.config.target_cycle_index)
        )

    def _latch(
        self,
        *,
        kind: str,
        reason: str,
        step_id: int,
    ) -> None:
        self._trigger_kind = str(kind)
        self._trigger_reason = str(reason)
        self._trigger_step = int(step_id)


def _safety_trigger_kind(reason: str) -> str:
    value = str(reason)
    if value.startswith("wall_contact"):
        return "wall"
    if value == "hard_bottom_contact":
        return "bottom"
    if value.startswith("stuck"):
        return "stuck"
    if value == "timeout" or value.endswith("_timeout"):
        return "timeout"
    return ""


def bounded_dig_probe_step_fields(
    policy_debug: Mapping[str, Any],
) -> dict[str, Any]:
    """Project the diagnostic handshake into one JSONL-safe step record."""

    return {
        "bounded_dig_probe_stop_enabled": bool(
            policy_debug.get("bounded_dig_probe_stop_enabled", False)
        ),
        "bounded_dig_probe_stop_diagnostic_only": bool(
            policy_debug.get(
                "bounded_dig_probe_stop_diagnostic_only",
                True,
            )
        ),
        "bounded_dig_probe_stop_target_cycle_index": int(
            policy_debug.get(
                "bounded_dig_probe_stop_target_cycle_index",
                BOUNDED_DIG_PROBE_TARGET_CYCLE_INDEX,
            )
        ),
        "bounded_dig_probe_stop_max_dig_steps": int(
            policy_debug.get(
                "bounded_dig_probe_stop_max_dig_steps",
                BOUNDED_DIG_PROBE_MAX_DIG_STEPS,
            )
        ),
        "bounded_dig_probe_stop_trigger_kind": str(
            policy_debug.get("bounded_dig_probe_stop_trigger_kind", "")
        ),
        "bounded_dig_probe_stop_trigger_reason": str(
            policy_debug.get("bounded_dig_probe_stop_trigger_reason", "")
        ),
        "bounded_dig_probe_stop_trigger_step": int(
            policy_debug.get("bounded_dig_probe_stop_trigger_step", -1)
        ),
        "bounded_dig_probe_stop_neutral_request_emitted": bool(
            policy_debug.get(
                "bounded_dig_probe_stop_neutral_request_emitted",
                False,
            )
        ),
        "bounded_dig_probe_stop_awaiting_neutral_ack": bool(
            policy_debug.get(
                "bounded_dig_probe_stop_awaiting_neutral_ack",
                False,
            )
        ),
        "bounded_dig_probe_stop_neutral_acknowledged": bool(
            policy_debug.get(
                "bounded_dig_probe_stop_neutral_acknowledged",
                False,
            )
        ),
        "bounded_dig_probe_stop_terminal_requested": bool(
            policy_debug.get(
                "bounded_dig_probe_stop_terminal_requested",
                False,
            )
        ),
        "bounded_dig_probe_stop_terminal_reason": str(
            policy_debug.get("bounded_dig_probe_stop_terminal_reason", "")
        ),
    }


__all__ = [
    "BOUNDED_DIG_PROBE_ENVELOPE_REASON",
    "BOUNDED_DIG_PROBE_MAX_DIG_STEPS",
    "BOUNDED_DIG_PROBE_STEP_LIMIT_REASON",
    "BOUNDED_DIG_PROBE_TARGET_CYCLE_INDEX",
    "BOUNDED_DIG_PROBE_TERMINAL_REASON_PREFIX",
    "BoundedDigProbeStopConfig",
    "BoundedDigProbeStopContract",
    "bounded_dig_probe_step_fields",
]
