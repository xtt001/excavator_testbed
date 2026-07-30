"""Independent ten-cycle functional regression terminal gate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from testbed.planner.box_emptying.safety_interlock import SafetyActionDecision
from testbed.planner.primitive.facts.capabilities import ReturnTransitionStatus


FUNCTIONAL_TERMINAL_REASON = "functional_10cycle_terminal_return_ready"


@dataclass(frozen=True)
class FunctionalCycleGateConfig:
    """Config kept separate from the formal ACT freeze contract."""

    enabled: bool = False
    target_cycles: int = 10
    max_bucket_mass_kg: float = 15.0

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> "FunctionalCycleGateConfig":
        raw = dict(values or {})
        return cls(
            enabled=bool(raw.get("enabled", False)),
            target_cycles=int(raw.get("target_cycles", 10)),
            max_bucket_mass_kg=float(
                raw.get("max_bucket_mass_kg", 15.0)
            ),
        )


class FunctionalCycleGate:
    """Hold the final return and stop only after a neutral step ack."""

    def __init__(self, config: FunctionalCycleGateConfig) -> None:
        if int(config.target_cycles) < 1:
            raise ValueError("functional target_cycles must be >= 1")
        if float(config.max_bucket_mass_kg) < 0.0:
            raise ValueError(
                "functional max_bucket_mass_kg must be non-negative"
            )
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._terminal_return_ready = False
        self._terminal_awaiting_neutral_ack = False
        self._terminal_neutral_acknowledged = False

    def apply(
        self,
        status: ReturnTransitionStatus,
        *,
        cycle_index: int,
    ) -> ReturnTransitionStatus:
        """Suppress dig N+1 and latch a terminal request at the safe envelope."""

        if not self.config.enabled:
            return status
        final_cycle_index = int(self.config.target_cycles) - 1
        if int(cycle_index) != final_cycle_index:
            return status
        safe_return_ready = bool(
            status.handoff_ready
            and float(status.mass_in_bucket_kg)
            <= float(self.config.max_bucket_mass_kg)
        )
        if safe_return_ready:
            self._terminal_return_ready = True
        return replace(
            status,
            completed_transition=False,
            next_skill="",
            switch_reason="",
        )

    def terminal_neutral_requested(self) -> bool:
        return bool(
            self.config.enabled
            and self._terminal_return_ready
            and not self._terminal_neutral_acknowledged
        )

    def observe_safety_decision(
        self,
        decision: SafetyActionDecision,
    ) -> None:
        if str(decision.reason) != FUNCTIONAL_TERMINAL_REASON:
            return
        if decision.awaiting_neutral_ack:
            self._terminal_awaiting_neutral_ack = True
        if decision.neutral_acknowledged:
            self._terminal_awaiting_neutral_ack = False
            self._terminal_neutral_acknowledged = True

    def debug_fields(self) -> dict[str, Any]:
        return {
            "functional_cycle_gate_enabled": bool(self.config.enabled),
            "functional_cycle_gate_target_cycles": int(
                self.config.target_cycles
            ),
            "functional_terminal_return_ready": bool(
                self._terminal_return_ready
            ),
            "functional_terminal_awaiting_neutral_ack": bool(
                self._terminal_awaiting_neutral_ack
            ),
            "functional_terminal_neutral_acknowledged": bool(
                self._terminal_neutral_acknowledged
            ),
        }


__all__ = [
    "FUNCTIONAL_TERMINAL_REASON",
    "FunctionalCycleGate",
    "FunctionalCycleGateConfig",
]
