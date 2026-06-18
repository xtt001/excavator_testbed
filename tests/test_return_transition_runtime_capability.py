from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.planner.primitive_action_tree import PrimitiveActionTreeRunner
from testbed.planner.return_to_dig_transition import (
    ReturnDirectHandoffAttemptOutcome,
    ReturnDirectHandoffRuntimeProjection,
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntime,
    ReturnToDigTransitionRuntimeProjection,
    ReturnToDigTransitionService,
    return_direct_handoff_runtime_from_gate_providers,
    return_transition_runtime_from_gate_providers,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_return_transition_runtime_skips_direct_and_shallow_after_next_dig_event() -> None:
    calls: list[str] = []

    def handoff_ready(obs: dict) -> bool:
        calls.append(f"handoff:{obs['step']}")
        return True

    def fail_direct(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("direct handoff must not run after next-dig event")

    def fail_shallow(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("shallow guard must not run after next-dig event")

    runtime = return_transition_runtime_from_gate_providers(
        service=ReturnToDigTransitionService(),
        obs={"step": 7},
        boundary_event=_BoundaryEvent(next_dig_entry_ready=True),
        previous_next_dig_event_seen=False,
        semantic_boundary_profile_active=False,
        handoff_ready=handoff_ready,
        direct_handoff_ready=fail_direct,
        shallow_guard_ready=fail_shallow,
    )

    assert calls == ["handoff:7"]
    assert runtime.outcome == ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    assert runtime.projection == ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert runtime.facts is not None
    assert runtime.facts.handoff_ready is True
    assert runtime.facts.direct_handoff_ready is False
    assert runtime.facts.shallow_guard_ready is False


def test_return_transition_runtime_skips_shallow_after_direct_handoff() -> None:
    calls: list[str] = []

    def handoff_ready(obs: dict) -> bool:
        calls.append(f"handoff:{obs['step']}")
        return True

    def direct_handoff_ready(
        obs: dict,
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        calls.append(f"direct:{obs['step']}:{handoff_ready}")
        return bool(handoff_ready)

    def fail_shallow(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("shallow guard must not run after direct handoff")

    runtime = return_transition_runtime_from_gate_providers(
        service=ReturnToDigTransitionService(),
        obs={"step": 8},
        boundary_event=None,
        previous_next_dig_event_seen=False,
        semantic_boundary_profile_active=False,
        handoff_ready=handoff_ready,
        direct_handoff_ready=direct_handoff_ready,
        shallow_guard_ready=fail_shallow,
    )

    assert calls == ["handoff:8", "direct:8:True"]
    assert runtime.outcome == ReturnToDigTransitionOutcome(
        action="direct_handoff",
        reason_suffix="start_envelope_ready",
        next_dig_event_seen=False,
    )
    assert runtime.projection == ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=False,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert runtime.facts is not None
    assert runtime.facts.handoff_ready is True
    assert runtime.facts.direct_handoff_ready is True
    assert runtime.facts.shallow_guard_ready is False


def test_action_tree_return_uses_transition_runtime_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    calls: list[str] = []

    def provider(
        *,
        obs: dict,
        boundary_event: Any | None,
        previous_next_dig_event_seen: bool,
    ) -> ReturnToDigTransitionRuntime:
        calls.append(
            "provider:"
            f"{obs['step']}:{getattr(boundary_event, 'next_dig_entry_ready', False)}:"
            f"{previous_next_dig_event_seen}"
        )
        return ReturnToDigTransitionRuntime(
            outcome=ReturnToDigTransitionOutcome(
                action="next_dig_event",
                reason_suffix="next_dig_entry_ready",
                next_dig_event_seen=True,
            ),
            projection=ReturnToDigTransitionRuntimeProjection(
                next_dig_event_seen=True,
                should_transition=True,
                completed_transition_increment=1,
                cycle_index_increment=1,
            ),
        )

    monkeypatch.setattr(policy, "_return_transition_runtime", provider)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_handoff_ready",
        lambda _obs: (_ for _ in ()).throw(
            AssertionError("action tree must use return runtime provider")
        ),
    )
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("action tree must use return runtime provider")
        ),
    )
    monkeypatch.setattr(
        policy,
        "_return_to_dig_shallow_guard_ready",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("action tree must use return runtime provider")
        ),
    )

    trace = PrimitiveActionTreeRunner().tick_transition(
        policy,
        {"step": 9},
        _BoundaryEvent(next_dig_entry_ready=True),
    )

    assert calls == ["provider:9:True:False"]
    assert trace.active_skill_before == "return"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason == "return_to_dig_next_dig_entry_ready"
    assert trace.node_path[-2:] == ("next_dig_event", "completion")


def test_return_direct_handoff_runtime_skips_prepare_and_gates_before_return() -> None:
    calls: list[str] = []

    def fail_prepare(_obs: dict) -> None:
        raise AssertionError("prepare must not run when direct handoff is skipped")

    def fail_handoff(_obs: dict) -> bool:
        raise AssertionError("handoff gate must not run when direct handoff is skipped")

    def fail_direct(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("direct gate must not run when direct handoff is skipped")

    runtime = return_direct_handoff_runtime_from_gate_providers(
        service=ReturnToDigTransitionService(),
        obs={"step": 11},
        active_skill_name="dump",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
        prepare_return_target_plan=fail_prepare,
        handoff_ready=fail_handoff,
        direct_handoff_ready=fail_direct,
    )

    assert calls == []
    assert runtime.outcome == ReturnDirectHandoffAttemptOutcome(action="skip")
    assert runtime.projection == ReturnDirectHandoffRuntimeProjection(
        should_transition=False,
    )
    assert runtime.facts.active_skill_name == "dump"
    assert runtime.facts.handoff_evaluated is False


def test_return_direct_handoff_runtime_preserves_prepare_and_gate_order() -> None:
    calls: list[str] = []

    def prepare_return_target_plan(obs: dict) -> None:
        calls.append(f"prepare:{obs['step']}")

    def handoff_ready(obs: dict) -> bool:
        calls.append(f"handoff:{obs['step']}")
        return True

    def direct_handoff_ready(
        obs: dict,
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        calls.append(f"direct:{obs['step']}:{handoff_ready}")
        return bool(handoff_ready)

    runtime = return_direct_handoff_runtime_from_gate_providers(
        service=ReturnToDigTransitionService(),
        obs={"step": 12},
        active_skill_name="return",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
        prepare_return_target_plan=prepare_return_target_plan,
        handoff_ready=handoff_ready,
        direct_handoff_ready=direct_handoff_ready,
    )

    assert calls == ["prepare:12", "handoff:12", "direct:12:True"]
    assert runtime.outcome == ReturnDirectHandoffAttemptOutcome(
        action="direct_handoff",
        reason_suffix="start_envelope_ready",
    )
    assert runtime.projection == ReturnDirectHandoffRuntimeProjection(
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert runtime.facts.handoff_evaluated is True
    assert runtime.facts.handoff_ready is True
    assert runtime.facts.direct_handoff_ready is True


def test_return_direct_handoff_runtime_waits_when_direct_gate_is_not_ready() -> None:
    calls: list[str] = []

    def prepare_return_target_plan(obs: dict) -> None:
        calls.append(f"prepare:{obs['step']}")

    def handoff_ready(obs: dict) -> bool:
        calls.append(f"handoff:{obs['step']}")
        return True

    def direct_handoff_ready(
        obs: dict,
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        calls.append(f"direct:{obs['step']}:{handoff_ready}")
        return False

    runtime = return_direct_handoff_runtime_from_gate_providers(
        service=ReturnToDigTransitionService(),
        obs={"step": 13},
        active_skill_name="return",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
        prepare_return_target_plan=prepare_return_target_plan,
        handoff_ready=handoff_ready,
        direct_handoff_ready=direct_handoff_ready,
    )

    assert calls == ["prepare:13", "handoff:13", "direct:13:True"]
    assert runtime.outcome == ReturnDirectHandoffAttemptOutcome(action="wait")
    assert runtime.projection == ReturnDirectHandoffRuntimeProjection(
        should_transition=False,
    )
    assert runtime.facts.handoff_evaluated is True
    assert runtime.facts.handoff_ready is True
    assert runtime.facts.direct_handoff_ready is False


class _BoundaryEvent:
    def __init__(
        self,
        *,
        next_dig_entry_ready: bool = False,
        qualified_dig_start: bool = False,
    ) -> None:
        self.next_dig_entry_ready = bool(next_dig_entry_ready)
        self.qualified_dig_start = bool(qualified_dig_start)


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, _obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    config = type("_Config", (), {"boundary_profile": "legacy"})()

    def reset(self) -> None:
        pass

    def update(self, **_kwargs: Any) -> _BoundaryEvent:
        return _BoundaryEvent()


def _make_policy() -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0),
        carry_policy=_ConstantPolicy(1),
        dump_policy=_ConstantPolicy(2),
        return_policy=_ConstantPolicy(3),
        boundary_detector=_FakeBoundaryDetector(),
        dig_to_carry_min_bucket_mass_kg=999.0,
    )
