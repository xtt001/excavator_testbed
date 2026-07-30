from __future__ import annotations

from dataclasses import fields
from types import MethodType
from typing import Any

import numpy as np
import pytest

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.action_dispatch import (
    PrimitiveActionDispatchPorts,
    PrimitiveActionDispatchService,
)
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.state import (
    PrimitiveExecutionRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy

_OLD_EXECUTION_ACTION_POLICY_WRAPPERS = (
    "_dispatch_tick_action",
    "_active_policy",
    "_all_policies",
    "_first_dig_policy_active",
)


class _FakePolicy:
    def __init__(self, name: str, events: list[str] | None = None) -> None:
        self.name = name
        self.events = events if events is not None else []
        self.predicted_obs: dict[str, Any] | None = None

    def predict(self, obs: dict[str, Any]) -> list[float]:
        self.events.append(f"predict:{self.name}")
        self.predicted_obs = obs
        return [1.0, 2.0, 3.0, 4.0]

    def reset(self) -> None:
        self.events.append(f"reset:{self.name}")


def _ports(
    events: list[str],
    *,
    skill_name: str = "dig",
    action_dim: int = 4,
    dig_policy: _FakePolicy | None = None,
    carry_policy: _FakePolicy | None = None,
    dump_policy: _FakePolicy | None = None,
    return_policy: _FakePolicy | None = None,
    first_dig_policy: _FakePolicy | None = None,
    bootstrap_policy: _FakePolicy | None = None,
    cycle_index: int = 1,
    completed_dump_count: int = 1,
    scripted_bootstrap_enabled: bool = False,
    pre_dig_align_action: Any | None = None,
    action_interlock: Any | None = None,
    pre_policy_action: Any | None = None,
) -> PrimitiveActionDispatchPorts:
    execution_state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name=skill_name,
    )
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    cycle_state.cycle_index = int(cycle_index)
    coverage_state = CoverageRuntimeState()
    coverage_state.coverage_completed_dump_count = int(completed_dump_count)
    dig_policy = dig_policy or _FakePolicy("dig", events)
    carry_policy = carry_policy or _FakePolicy("carry", events)
    dump_policy = dump_policy or _FakePolicy("dump", events)
    return_policy = return_policy or _FakePolicy("return", events)

    def policy_observation(obs: dict[str, Any]) -> dict[str, Any]:
        events.append("policy_obs")
        return {"assembled": obs}

    def scripted_action(obs: dict[str, Any]) -> np.ndarray:
        events.append("scripted_action")
        return np.asarray([9.0, 8.0, 7.0, 6.0], dtype=np.float32)

    def default_pre_dig_align_action(obs: dict[str, Any]) -> np.ndarray:
        events.append("pre_dig_align_action")
        return np.asarray([4.0, 3.0, 2.0, 1.0], dtype=np.float32)

    return PrimitiveActionDispatchPorts(
        execution_state=execution_state,
        cycle_state=cycle_state,
        coverage_state=coverage_state,
        action_dim=action_dim,
        skill_policies={
            "dig": dig_policy,
            "carry": carry_policy,
            "dump": dump_policy,
            "return": return_policy,
        },
        base_policy_order=("dig", "carry", "dump", "return"),
        optional_policy_order=("first_dig", "bootstrap"),
        first_dig_policy=first_dig_policy,
        bootstrap_policy=bootstrap_policy,
        policy_observation=policy_observation,
        scripted_bootstrap_enabled=lambda: scripted_bootstrap_enabled,
        scripted_bootstrap_action=scripted_action,
        pre_dig_align_action=pre_dig_align_action or default_pre_dig_align_action,
        action_interlock=action_interlock,
        pre_policy_action=pre_policy_action,
    )


def test_action_dispatch_ports_use_focused_state_owners() -> None:
    port_fields = {field.name for field in fields(PrimitiveActionDispatchPorts)}

    assert {"execution_state", "cycle_state", "coverage_state"} <= port_fields
    assert not {
        "current_skill_name",
        "cycle_index",
        "coverage_completed_dump_count",
    } & port_fields


def test_dispatch_short_circuits_to_scripted_bootstrap_action() -> None:
    events: list[str] = []
    low_level = _FakePolicy("bootstrap", events)
    service = PrimitiveActionDispatchService.from_ports(
        _ports(
            events,
            skill_name="bootstrap",
            bootstrap_policy=low_level,
            scripted_bootstrap_enabled=True,
        )
    )

    action = service.dispatch_action({"qpos": [1.0]})

    assert action.tolist() == [9.0, 8.0, 7.0, 6.0]
    assert action.dtype == np.float32
    assert events == ["scripted_action"]
    assert low_level.predicted_obs is None


def test_pre_dig_align_short_circuits_to_runtime_action_without_policy_lookup() -> None:
    events: list[str] = []
    low_level = _FakePolicy("dig", events)
    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, skill_name="pre_dig_align", dig_policy=low_level)
    )

    action = service.dispatch_action({"qpos": [1.0]})

    assert action.dtype == np.float32
    assert action.shape == (4,)
    assert action.tolist() == [4.0, 3.0, 2.0, 1.0]
    assert events == ["pre_dig_align_action"]
    assert low_level.predicted_obs is None


def test_dispatch_normal_policy_uses_policy_observation_and_shapes_action() -> None:
    events: list[str] = []
    dig_policy = _FakePolicy("dig", events)
    obs = {"qpos": [1.0]}
    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, skill_name="dig", dig_policy=dig_policy)
    )

    action = service.dispatch_action(obs)

    assert action.dtype == np.float32
    assert action.shape == (4,)
    assert action.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert dig_policy.predicted_obs == {"assembled": obs}
    assert events == ["policy_obs", "predict:dig"]


def test_dispatch_applies_optional_safety_interlock_after_policy_prediction() -> None:
    events: list[str] = []

    def interlock(obs: dict[str, Any], action: np.ndarray) -> np.ndarray:
        events.append("interlock")
        assert obs == {"qpos": [1.0]}
        assert action.tolist() == [1.0, 2.0, 3.0, 4.0]
        return np.zeros(4, dtype=np.float32)

    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, skill_name="dig", action_interlock=interlock)
    )

    action = service.dispatch_action({"qpos": [1.0]})

    assert action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert events == ["policy_obs", "predict:dig", "interlock"]


def test_dispatch_pre_policy_action_skips_policy_and_post_interlock() -> None:
    events: list[str] = []
    dig_policy = _FakePolicy("dig", events)

    def pre_policy_action(obs: dict[str, Any]) -> np.ndarray:
        events.append("pre_policy_action")
        assert obs == {"qpos": [1.0]}
        return np.asarray([0.0, 0.1, -0.2, 0.3], dtype=np.float32)

    def interlock(obs: dict[str, Any], action: np.ndarray) -> np.ndarray:
        events.append("interlock")
        return action

    service = PrimitiveActionDispatchService.from_ports(
        _ports(
            events,
            skill_name="dig",
            dig_policy=dig_policy,
            pre_policy_action=pre_policy_action,
            action_interlock=interlock,
        )
    )

    action = service.dispatch_action({"qpos": [1.0]})

    assert action.tolist() == pytest.approx([0.0, 0.1, -0.2, 0.3])
    assert events == ["pre_policy_action"]
    assert dig_policy.predicted_obs is None


def test_dispatch_pre_policy_none_falls_through_to_policy() -> None:
    events: list[str] = []

    def pre_policy_action(obs: dict[str, Any]) -> None:
        events.append("pre_policy_check")
        return None

    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, pre_policy_action=pre_policy_action)
    )

    action = service.dispatch_action({"qpos": [1.0]})

    assert action.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert events == ["pre_policy_check", "policy_obs", "predict:dig"]


def test_first_dig_policy_active_selects_first_dig_policy() -> None:
    events: list[str] = []
    first_dig_policy = _FakePolicy("first_dig", events)
    service = PrimitiveActionDispatchService.from_ports(
        _ports(
            events,
            skill_name="dig",
            first_dig_policy=first_dig_policy,
            cycle_index=0,
            completed_dump_count=0,
        )
    )

    assert service.first_dig_policy_active() is True
    assert service.active_policy() is first_dig_policy


@pytest.mark.parametrize(
    ("cycle_index", "completed_dump_count"),
    [(1, 0), (0, 1)],
)
def test_first_dig_policy_inactive_falls_back_to_dig_policy(
    cycle_index: int,
    completed_dump_count: int,
) -> None:
    events: list[str] = []
    dig_policy = _FakePolicy("dig", events)
    first_dig_policy = _FakePolicy("first_dig", events)
    service = PrimitiveActionDispatchService.from_ports(
        _ports(
            events,
            skill_name="dig",
            dig_policy=dig_policy,
            first_dig_policy=first_dig_policy,
            cycle_index=cycle_index,
            completed_dump_count=completed_dump_count,
        )
    )

    assert service.first_dig_policy_active() is False
    assert service.active_policy() is dig_policy


def test_all_policies_preserves_legacy_4p_order_with_optional_policies() -> None:
    events: list[str] = []
    dig_policy = _FakePolicy("dig", events)
    carry_policy = _FakePolicy("carry", events)
    dump_policy = _FakePolicy("dump", events)
    return_policy = _FakePolicy("return", events)
    first_dig_policy = _FakePolicy("first_dig", events)
    bootstrap_policy = _FakePolicy("bootstrap", events)
    service = PrimitiveActionDispatchService.from_ports(
        _ports(
            events,
            dig_policy=dig_policy,
            carry_policy=carry_policy,
            dump_policy=dump_policy,
            return_policy=return_policy,
            first_dig_policy=first_dig_policy,
            bootstrap_policy=bootstrap_policy,
        )
    )

    assert service.all_policies() == [
        dig_policy,
        carry_policy,
        dump_policy,
        return_policy,
        first_dig_policy,
        bootstrap_policy,
    ]


def test_bootstrap_active_without_bootstrap_policy_raises_exact_error() -> None:
    service = PrimitiveActionDispatchService.from_ports(
        _ports([], skill_name="bootstrap", bootstrap_policy=None)
    )

    with pytest.raises(
        RuntimeError,
        match="bootstrap skill is active but bootstrap_policy is None.",
    ):
        service.active_policy()


def test_unknown_skill_raises_exact_error() -> None:
    service = PrimitiveActionDispatchService.from_ports(
        _ports([], skill_name="unknown")
    )

    with pytest.raises(RuntimeError, match="Unknown primitive skill 'unknown'."):
        service.active_policy()


def test_policy_no_longer_exposes_action_dispatch_private_wrappers() -> None:
    for wrapper_name in _OLD_EXECUTION_ACTION_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__


def test_policy_action_dispatch_service_uses_focused_contract() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"qpos": [1.0]}
    action = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    policy = _FakePolicy("dig")
    policies = [policy]

    class _FakeService:
        def dispatch_action(self, got_obs: dict[str, Any]) -> np.ndarray:
            assert got_obs is obs
            return action

        def active_policy(self) -> _FakePolicy:
            return policy

        def all_policies(self) -> list[_FakePolicy]:
            return policies

        def first_dig_policy_active(self) -> bool:
            return True

    planner._action_dispatch_service = MethodType(
        lambda self: _FakeService(),
        planner,
    )

    service = planner._action_dispatch_service()

    assert service.dispatch_action(obs) is action
    assert service.active_policy() is policy
    assert service.all_policies() is policies
    assert service.first_dig_policy_active() is True


def test_policy_action_dispatch_ports_share_focused_state_owners() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 4
    planner.dig_policy = _FakePolicy("dig")
    planner.carry_policy = _FakePolicy("carry")
    planner.dump_policy = _FakePolicy("dump")
    planner.return_policy = _FakePolicy("return")
    planner.first_dig_policy = _FakePolicy("first_dig")
    planner.bootstrap_policy = _FakePolicy("bootstrap")
    planner._skill_name = "dig"
    planner._primitive_cycle_runtime_state().cycle_index = 0
    planner._coverage_runtime_state().coverage_completed_dump_count = 0

    ports = planner._action_dispatch_ports()
    port_fields = {field.name for field in fields(PrimitiveActionDispatchPorts)}

    assert ports.execution_state is planner._primitive_execution_runtime_state()
    assert ports.cycle_state is planner._primitive_cycle_runtime_state()
    assert ports.coverage_state is planner._coverage_runtime_state()
    assert ports.execution_state.skill_name == "dig"
    assert ports.cycle_state.cycle_index == 0
    assert ports.coverage_state.coverage_completed_dump_count == 0
    assert "current_skill_name" not in port_fields
    assert "cycle_index" not in port_fields
    assert "coverage_completed_dump_count" not in port_fields


def test_policy_action_dispatch_ports_supply_pre_dig_align_runtime_action() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 4
    planner.dig_policy = _FakePolicy("dig")
    planner.carry_policy = _FakePolicy("carry")
    planner.dump_policy = _FakePolicy("dump")
    planner.return_policy = _FakePolicy("return")
    planner.first_dig_policy = None
    planner.bootstrap_policy = None
    planner._skill_name = "pre_dig_align"
    obs = {"qpos": [1.0]}
    action = np.asarray([-0.1, -0.2, -0.3, -0.4], dtype=np.float32)
    calls: list[dict[str, Any]] = []

    class _FakePreDigAlignRuntimeService:
        def action(self, got_obs: dict[str, Any]) -> np.ndarray:
            calls.append(got_obs)
            return action

    planner._primitive_pre_dig_align_runtime_service = MethodType(
        lambda self: _FakePreDigAlignRuntimeService(),
        planner,
    )

    ports = planner._action_dispatch_ports()
    dispatched = PrimitiveActionDispatchService.from_ports(ports).dispatch_action(obs)

    np.testing.assert_allclose(dispatched, action)
    assert calls == [obs]
