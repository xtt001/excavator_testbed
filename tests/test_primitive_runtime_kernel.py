from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import numpy as np

import testbed.planner.primitive.shell.runtime_kernel as primitive_runtime_kernel
from testbed.planner.primitive.report.debug_report import PrimitiveDebugReportBuilder
from testbed.planner.primitive.report.planner_trace import PrimitivePlannerTraceBuilder
from testbed.planner.primitive.shell.runtime_kernel import (
    PrimitivePlannerRuntimeKernel,
    PrimitivePlannerRuntimeKernelPorts,
)
from testbed.planner.primitive.report.rollout_summary import PrimitiveRolloutSummaryBuilder
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


class _FakeResetService:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def reset(self) -> SimpleNamespace:
        self._events.append(("reset_service", None))
        return SimpleNamespace(
            debug_transition_timeout=True,
            debug_transition_completed=False,
        )


class _FakeExecutionDriver:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def predict(self, obs: dict) -> np.ndarray:
        self._events.append(("execution_predict", obs))
        return np.asarray([1.0, 2.0], dtype=np.float32)


class _FakeReportBuilder:
    def __init__(self, events: list[tuple[str, object]], name: str) -> None:
        self._events = events
        self._name = name

    def build(self, inputs: object) -> dict[str, object]:
        self._events.append((f"{self._name}_build", inputs))
        return {"report": self._name, "inputs": inputs}


_OLD_PUBLIC_RUNTIME_POLICY_WRAPPERS = (
    "_runtime_kernel",
    "_runtime_kernel_ports",
    "_debug_report_builder",
    "_rollout_summary_builder",
    "_planner_trace_builder",
)


def test_policy_no_longer_exposes_public_runtime_composition_wrappers() -> None:
    for wrapper_name in _OLD_PUBLIC_RUNTIME_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__


def test_public_runtime_composes_kernel_from_focused_services_and_runtimes() -> None:
    events: list[tuple[str, object]] = []

    class _FakeTickFinalizationRuntime:
        def make_debug_state(self, **kwargs: object) -> dict[str, object]:
            events.append(("make_debug", kwargs))
            return {"debug": kwargs}

    class _FakeExecutionRuntime:
        def execution_driver(self) -> _FakeExecutionDriver:
            events.append(("execution_runtime_driver", None))
            return _FakeExecutionDriver(events)

    class _FakeReportRuntime:
        def debug_report_inputs(self) -> str:
            events.append(("debug_inputs", None))
            return "debug-inputs"

        def rollout_summary_inputs(self) -> str:
            events.append(("summary_inputs", None))
            return "summary-inputs"

        def planner_trace_inputs(self) -> str:
            events.append(("trace_inputs", None))
            return "trace-inputs"

    public_runtime = primitive_runtime_kernel.PrimitivePlannerPublicRuntime.from_ports(
        primitive_runtime_kernel.PrimitivePlannerPublicRuntimePorts(
            reset_lifecycle_service=lambda: _FakeResetService(events),
            apply_reset_lifecycle_state=lambda state: events.append(
                ("apply", state)
            ),
            tick_finalization_runtime=lambda: _FakeTickFinalizationRuntime(),
            set_debug_state=lambda state: events.append(("set_debug", state)),
            execution_runtime=lambda: _FakeExecutionRuntime(),
            report_runtime=lambda: _FakeReportRuntime(),
        )
    )
    kernel = public_runtime.runtime_kernel()

    kernel.reset()
    assert kernel.predict({"obs": "value"}).tolist() == [1.0, 2.0]
    runtime_ports = public_runtime.runtime_kernel_ports()
    assert isinstance(runtime_ports.debug_report_builder(), PrimitiveDebugReportBuilder)
    assert runtime_ports.debug_report_inputs() == "debug-inputs"
    assert isinstance(
        runtime_ports.rollout_summary_builder(),
        PrimitiveRolloutSummaryBuilder,
    )
    assert runtime_ports.rollout_summary_inputs() == "summary-inputs"
    assert isinstance(
        runtime_ports.planner_trace_builder(),
        PrimitivePlannerTraceBuilder,
    )
    assert runtime_ports.planner_trace_inputs() == "trace-inputs"
    assert [name for name, _ in events] == [
        "reset_service",
        "apply",
        "make_debug",
        "set_debug",
        "execution_runtime_driver",
        "execution_predict",
        "debug_inputs",
        "summary_inputs",
        "trace_inputs",
    ]


def test_runtime_kernel_reset_owns_reset_sequence() -> None:
    events: list[tuple[str, object]] = []

    ports = PrimitivePlannerRuntimeKernelPorts(
        reset_lifecycle_service=lambda: _FakeResetService(events),
        apply_reset_lifecycle_state=lambda state: events.append(("apply", state)),
        make_debug_state=lambda **kwargs: events.append(("make_debug", kwargs))
        or {"debug": kwargs},
        set_debug_state=lambda state: events.append(("set_debug", state)),
        execution_driver=lambda: _FakeExecutionDriver(events),
        debug_report_builder=lambda: _FakeReportBuilder(events, "debug"),
        debug_report_inputs=lambda: "debug-inputs",
        rollout_summary_builder=lambda: _FakeReportBuilder(events, "summary"),
        rollout_summary_inputs=lambda: "summary-inputs",
        planner_trace_builder=lambda: _FakeReportBuilder(events, "trace"),
        planner_trace_inputs=lambda: "trace-inputs",
    )

    PrimitivePlannerRuntimeKernel.from_ports(ports).reset()

    assert [name for name, _ in events] == [
        "reset_service",
        "apply",
        "make_debug",
        "set_debug",
    ]
    assert events[2][1] == {
        "transition_timeout": True,
        "transition_completed": False,
    }
    assert events[3][1] == {
        "debug": {
            "transition_timeout": True,
            "transition_completed": False,
        }
    }


def test_runtime_kernel_predict_delegates_to_execution_driver() -> None:
    events: list[tuple[str, object]] = []
    obs = {"x": object()}
    ports = _runtime_ports(events)

    action = PrimitivePlannerRuntimeKernel.from_ports(ports).predict(obs)

    assert action.dtype == np.float32
    assert action.tolist() == [1.0, 2.0]
    assert events == [("execution_predict", obs)]


def test_runtime_kernel_report_routes_compose_builders_and_inputs() -> None:
    events: list[tuple[str, object]] = []
    kernel = PrimitivePlannerRuntimeKernel.from_ports(_runtime_ports(events))

    assert kernel.debug_state() == {"report": "debug", "inputs": "debug-inputs"}
    assert kernel.rollout_summary() == {
        "report": "summary",
        "inputs": "summary-inputs",
    }
    assert kernel.planner_trace() == {"report": "trace", "inputs": "trace-inputs"}
    assert events == [
        ("debug_build", "debug-inputs"),
        ("summary_build", "summary-inputs"),
        ("trace_build", "trace-inputs"),
    ]


def test_runtime_kernel_ports_do_not_receive_planner_self() -> None:
    field_names = {field.name for field in fields(PrimitivePlannerRuntimeKernelPorts)}

    assert "planner" not in field_names
    assert "self" not in field_names


def test_policy_public_methods_delegate_to_public_runtime(monkeypatch) -> None:
    events: list[tuple[str, object]] = []
    action = np.asarray([3.0, 4.0], dtype=np.float32)

    class _FakeKernel:
        def reset(self) -> None:
            events.append(("reset", None))

        def predict(self, obs: dict) -> np.ndarray:
            events.append(("predict", obs))
            return action

        def debug_state(self) -> dict[str, object]:
            events.append(("debug_state", None))
            return {"debug": True}

        def rollout_summary(self) -> dict[str, object]:
            events.append(("rollout_summary", None))
            return {"summary": True}

        def planner_trace(self) -> dict[str, object]:
            events.append(("planner_trace", None))
            return {"trace": True}

    fake_kernel = _FakeKernel()
    monkeypatch.setattr(
        PrimitivePlannerACTPolicy,
        "_primitive_runtime_kernel_runtime",
        lambda self: fake_kernel,
        raising=False,
    )

    policy = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"obs": object()}

    policy.reset()
    assert policy.predict(obs) is action
    assert policy.debug_state() == {"debug": True}
    assert policy.rollout_summary() == {"summary": True}
    assert policy.planner_trace() == {"trace": True}
    assert events == [
        ("reset", None),
        ("predict", obs),
        ("debug_state", None),
        ("rollout_summary", None),
        ("planner_trace", None),
    ]


def _runtime_ports(
    events: list[tuple[str, object]],
) -> PrimitivePlannerRuntimeKernelPorts:
    return PrimitivePlannerRuntimeKernelPorts(
        reset_lifecycle_service=lambda: _FakeResetService(events),
        apply_reset_lifecycle_state=lambda state: events.append(("apply", state)),
        make_debug_state=lambda **kwargs: {"debug": kwargs},
        set_debug_state=lambda state: events.append(("set_debug", state)),
        execution_driver=lambda: _FakeExecutionDriver(events),
        debug_report_builder=lambda: _FakeReportBuilder(events, "debug"),
        debug_report_inputs=lambda: "debug-inputs",
        rollout_summary_builder=lambda: _FakeReportBuilder(events, "summary"),
        rollout_summary_inputs=lambda: "summary-inputs",
        planner_trace_builder=lambda: _FakeReportBuilder(events, "trace"),
        planner_trace_inputs=lambda: "trace-inputs",
    )
