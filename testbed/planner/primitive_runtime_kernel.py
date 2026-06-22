"""Public runtime composition root for the primitive planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrimitivePlannerRuntimeKernelPorts:
    """Typed public-runtime ports supplied by the primitive policy adapter."""

    reset_lifecycle_service: Callable[[], Any]
    apply_reset_lifecycle_state: Callable[[Any], None]
    make_debug_state: Callable[..., Any]
    set_debug_state: Callable[[Any], None]
    execution_driver: Callable[[], Any]
    debug_report_builder: Callable[[], Any]
    debug_report_inputs: Callable[[], Any]
    rollout_summary_builder: Callable[[], Any]
    rollout_summary_inputs: Callable[[], Any]
    planner_trace_builder: Callable[[], Any]
    planner_trace_inputs: Callable[[], Any]


@dataclass(frozen=True)
class PrimitivePlannerRuntimeKernel:
    """Own the public primitive planner runtime route and service composition."""

    ports: PrimitivePlannerRuntimeKernelPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitivePlannerRuntimeKernelPorts,
    ) -> "PrimitivePlannerRuntimeKernel":
        return cls(ports=ports)

    def reset(self) -> None:
        reset_state = self.ports.reset_lifecycle_service().reset()
        self.ports.apply_reset_lifecycle_state(reset_state)
        self.ports.set_debug_state(
            self.ports.make_debug_state(
                transition_timeout=reset_state.debug_transition_timeout,
                transition_completed=reset_state.debug_transition_completed,
            )
        )

    def predict(self, obs: dict[str, Any]) -> Any:
        return self.ports.execution_driver().predict(obs)

    def debug_state(self) -> dict[str, Any]:
        return self.ports.debug_report_builder().build(
            self.ports.debug_report_inputs()
        )

    def rollout_summary(self) -> dict[str, Any]:
        return self.ports.rollout_summary_builder().build(
            self.ports.rollout_summary_inputs()
        )

    def planner_trace(self) -> dict[str, object]:
        return self.ports.planner_trace_builder().build(
            self.ports.planner_trace_inputs()
        )


__all__ = [
    "PrimitivePlannerRuntimeKernel",
    "PrimitivePlannerRuntimeKernelPorts",
]
