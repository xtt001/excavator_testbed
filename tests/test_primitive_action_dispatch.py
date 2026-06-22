from __future__ import annotations

from types import MethodType
from typing import Any

import numpy as np
import pytest

from testbed.planner.primitive_action_dispatch import (
    PrimitiveActionDispatchPorts,
    PrimitiveActionDispatchService,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


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
) -> PrimitiveActionDispatchPorts:
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

    def pre_dig_action(obs: dict[str, Any]) -> np.ndarray:
        events.append("pre_dig_action")
        return np.asarray([6.0, 7.0, 8.0, 9.0], dtype=np.float32)

    return PrimitiveActionDispatchPorts(
        current_skill_name=lambda: skill_name,
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
        cycle_index=lambda: cycle_index,
        coverage_completed_dump_count=lambda: completed_dump_count,
        policy_observation=policy_observation,
        scripted_bootstrap_enabled=lambda: scripted_bootstrap_enabled,
        scripted_bootstrap_action=scripted_action,
        pre_dig_align_action=pre_dig_action,
    )


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


def test_dispatch_short_circuits_to_pre_dig_align_action() -> None:
    events: list[str] = []
    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, skill_name="pre_dig_align")
    )

    action = service.dispatch_action({"qpos": [1.0]})

    assert action.tolist() == [6.0, 7.0, 8.0, 9.0]
    assert action.dtype == np.float32
    assert events == ["pre_dig_action"]


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


def test_policy_action_dispatch_private_methods_delegate_to_service() -> None:
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

    assert planner._dispatch_tick_action(obs) is action
    assert planner._active_policy() is policy
    assert planner._all_policies() is policies
    assert planner._first_dig_policy_active() is True
