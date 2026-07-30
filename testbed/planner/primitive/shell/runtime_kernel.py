"""Public runtime composition root for the primitive planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.report.debug_report import PrimitiveDebugReportBuilder
from testbed.planner.primitive.report.planner_trace import PrimitivePlannerTraceBuilder
from testbed.planner.primitive.report.rollout_summary import (
    PrimitiveRolloutSummaryBuilder,
)


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
    ) -> PrimitivePlannerRuntimeKernel:
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


@dataclass(frozen=True)
class PrimitivePlannerPublicRuntimePorts:
    """Focused services and runtimes needed for public policy calls."""

    reset_lifecycle_service: Callable[[], Any]
    apply_reset_lifecycle_state: Callable[[Any], None]
    tick_finalization_runtime: Callable[[], Any]
    set_debug_state: Callable[[Any], None]
    execution_runtime: Callable[[], Any]
    report_runtime: Callable[[], Any]


@dataclass(frozen=True)
class PrimitivePlannerPublicRuntime:
    """Own public runtime-kernel composition for the primitive planner."""

    ports: PrimitivePlannerPublicRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitivePlannerPublicRuntimePorts,
    ) -> PrimitivePlannerPublicRuntime:
        return cls(ports=ports)

    def runtime_kernel_ports(self) -> PrimitivePlannerRuntimeKernelPorts:
        ports = self.ports
        return PrimitivePlannerRuntimeKernelPorts(
            reset_lifecycle_service=ports.reset_lifecycle_service,
            apply_reset_lifecycle_state=ports.apply_reset_lifecycle_state,
            make_debug_state=(
                lambda **kwargs: (
                    ports.tick_finalization_runtime().make_debug_state(**kwargs)
                )
            ),
            set_debug_state=ports.set_debug_state,
            execution_driver=(
                lambda: ports.execution_runtime().execution_driver()
            ),
            debug_report_builder=PrimitiveDebugReportBuilder,
            debug_report_inputs=lambda: ports.report_runtime().debug_report_inputs(),
            rollout_summary_builder=PrimitiveRolloutSummaryBuilder,
            rollout_summary_inputs=(
                lambda: ports.report_runtime().rollout_summary_inputs()
            ),
            planner_trace_builder=PrimitivePlannerTraceBuilder,
            planner_trace_inputs=lambda: ports.report_runtime().planner_trace_inputs(),
        )

    def runtime_kernel(self) -> PrimitivePlannerRuntimeKernel:
        return PrimitivePlannerRuntimeKernel.from_ports(self.runtime_kernel_ports())

    def reset(self) -> None:
        self.runtime_kernel().reset()

    def predict(self, obs: dict[str, Any]) -> Any:
        return self.runtime_kernel().predict(obs)

    def debug_state(self) -> dict[str, Any]:
        return self.runtime_kernel().debug_state()

    def rollout_summary(self) -> dict[str, Any]:
        return self.runtime_kernel().rollout_summary()

    def planner_trace(self) -> dict[str, object]:
        return self.runtime_kernel().planner_trace()


__all__ = [
    "PrimitivePlannerRuntimeKernel",
    "PrimitivePlannerRuntimeKernelPorts",
    "PrimitivePlannerPublicRuntime",
    "PrimitivePlannerPublicRuntimePorts",
]
