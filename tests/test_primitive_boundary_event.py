from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import numpy as np

from testbed.planner.primitive.execution.boundary_event import (
    PrimitiveBoundaryEventRuntimePorts,
    PrimitiveBoundaryEventRuntimeService,
)
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_OLD_BOUNDARY_EVENT_POLICY_WRAPPERS = ("_tick_boundary_event",)


class _FakeBoundaryDetector:
    def __init__(self, event: object | None = None) -> None:
        self.event = event
        self.calls: list[dict[str, object]] = []

    def update(self, **kwargs):
        self.calls.append(kwargs)
        return self.event


def _facts_provider(action_dim: int = 4):
    return lambda obs: PrimitiveObservationFacts.from_obs(obs, action_dim=action_dim)


def test_boundary_event_ports_expose_state_owner_detector_and_typed_fact_source() -> None:
    port_fields = {field.name for field in fields(PrimitiveBoundaryEventRuntimePorts)}

    assert {
        "execution_state",
        "boundary_detector",
        "observation_facts",
    }.issubset(port_fields)
    assert "prev_action" not in port_fields
    assert "env_state" not in port_fields
    assert "qpos" not in port_fields


def test_boundary_event_service_skips_detector_without_prev_action() -> None:
    detector = _FakeBoundaryDetector(event=object())
    service = PrimitiveBoundaryEventRuntimeService.from_ports(
        PrimitiveBoundaryEventRuntimePorts(
            execution_state=PrimitiveExecutionRuntimeState.fresh(),
            boundary_detector=detector,
            observation_facts=_facts_provider(),
        )
    )

    assert service.update({}) is None
    assert detector.calls == []


def test_boundary_event_service_projects_observation_facts_to_detector() -> None:
    event = object()
    detector = _FakeBoundaryDetector(event=event)
    execution_state = PrimitiveExecutionRuntimeState.fresh()
    action = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    execution_state.set_prev_action(action)
    service = PrimitiveBoundaryEventRuntimeService.from_ports(
        PrimitiveBoundaryEventRuntimePorts(
            execution_state=execution_state,
            boundary_detector=detector,
            observation_facts=_facts_provider(action_dim=4),
        )
    )
    task_metrics = {"mass_in_bucket_kg": 2.5}
    obs = {
        "reward_phase": "dig",
        "task_step_successes": {"dig": True},
        "task_metrics": task_metrics,
    }

    result = service.update(obs)

    assert result is event
    assert len(detector.calls) == 1
    call = detector.calls[0]
    assert call["action"] is action
    assert np.array_equal(call["env_state"], np.zeros(13, dtype=np.float32))
    assert np.array_equal(call["qpos"], np.zeros(4, dtype=np.float32))
    assert call["reward_phase"] == "dig"
    assert call["task_step_successes"] == {"dig": True}
    assert dict(call["task_metrics"]) == task_metrics


def test_policy_no_longer_exposes_boundary_event_private_wrapper() -> None:
    for wrapper_name in _OLD_BOUNDARY_EVENT_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__


def test_policy_boundary_event_runtime_uses_execution_owner_and_detector() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    detector = _FakeBoundaryDetector(event=SimpleNamespace(kind="boundary"))
    policy.boundary_detector = detector
    execution_state = policy._primitive_execution_runtime_state()
    action = np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32)
    execution_state.set_prev_action(action)

    ports = policy._primitive_boundary_event_runtime_ports()
    result = policy._primitive_boundary_event_runtime_service().update(
        {"task_metrics": {"mass_in_bucket_kg": 3.0}}
    )

    assert ports.execution_state is execution_state
    assert ports.boundary_detector is detector
    assert result.kind == "boundary"
    assert detector.calls[0]["action"] is action
