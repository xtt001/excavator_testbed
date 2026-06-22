"""Mutable primitive return runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrimitiveReturnRuntimeState:
    """Own mutable return handoff/cache runtime state."""

    return_step_count: int = 0
    return_to_dig_entry_error_m: float = field(default_factory=lambda: float("nan"))
    return_to_dig_entry_close_state: bool = True
    return_next_dig_event_seen: bool = False
    return_to_dig_start_envelope_ready_state: bool = True
    return_to_dig_start_envelope_error: float = field(
        default_factory=lambda: float("nan")
    )
    return_to_dig_start_envelope_checks: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fresh(cls) -> "PrimitiveReturnRuntimeState":
        """Return a fresh return runtime state matching reset defaults."""

        return cls()

    def mark_next_dig_event_seen(self) -> None:
        self.return_next_dig_event_seen = True

    def clear_next_dig_event_seen(self) -> None:
        self.return_next_dig_event_seen = False

    def apply_start_envelope_gate_result(
        self,
        *,
        ready: bool,
        error: float,
        checks: dict[str, Any],
    ) -> None:
        self.return_to_dig_start_envelope_ready_state = bool(ready)
        self.return_to_dig_start_envelope_error = float(error)
        self.return_to_dig_start_envelope_checks = dict(checks)

    def set_entry_close_result(
        self,
        *,
        error_m: float,
        close: bool,
    ) -> None:
        self.return_to_dig_entry_error_m = float(error_m)
        self.return_to_dig_entry_close_state = bool(close)


__all__ = ["PrimitiveReturnRuntimeState"]
