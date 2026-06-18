from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.planner.return_to_dig_transition import (
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntime,
    ReturnToDigTransitionRuntimeProjection,
    ReturnToDigTransitionService,
)
from testbed.planner.runtime import (
    LegacyFsmBackendPorts,
    LegacyFsmReturnTransitionPorts,
    LegacyFsmSkillNames,
    PlannerBackendPorts,
    PlannerBlackboard,
    PlannerRuntimeEffect,
    PlannerTickContext,
)
from testbed.planner.runtime.legacy_fsm import (
    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
    LEGACY_FSM_TRANSITION_EFFECT,
    LegacyStateMachineBackend,
    apply_legacy_fsm_runtime_effects,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _skill_names() -> LegacyFsmSkillNames:
    return LegacyFsmSkillNames(
        bootstrap="bootstrap",
        pre_dig_align="pre_dig_align",
        dig="dig",
        carry="carry",
        dump="dump",
        return_skill="return",
    )


def _ports(
    return_transition: LegacyFsmReturnTransitionPorts,
) -> PlannerBackendPorts:
    return PlannerBackendPorts(
        legacy_fsm=LegacyFsmBackendPorts(
            skill_names=_skill_names(),
            return_transition=return_transition,
        )
    )


def test_legacy_fsm_backend_return_returns_apply_runtime_effect() -> None:
    calls: list[str] = []

    def handoff_ready(obs: dict) -> bool:
        calls.append(f"handoff:{obs['step']}")
        return True

    def fail_direct(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("direct handoff must not run after next-dig event")

    def fail_shallow(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("shallow guard must not run after next-dig event")

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 24},
            boundary_event=_FakeBoundaryEvent(next_dig_entry_ready=True),
            blackboard=PlannerBlackboard(
                current_skill="return",
                return_next_dig_event_seen=False,
            ),
            ports=_ports(
                LegacyFsmReturnTransitionPorts(
                    return_transition_runtime=_return_transition_runtime_provider(
                        handoff_ready=handoff_ready,
                        direct_handoff_ready=fail_direct,
                        shallow_guard_ready=fail_shallow,
                    ),
                ),
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "return")
    assert result.status == "running"
    assert result.reason == "next_dig_entry_ready"
    assert calls == ["handoff:24"]
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.effect_type == APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT
    assert effect.payload["outcome"] == ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    assert effect.payload["projection"] == ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert dict(result.diagnostics) == {
        "active_skill": "return",
        "action": "next_dig_event",
        "reason_suffix": "next_dig_entry_ready",
        "next_dig_event_seen": True,
    }


def test_legacy_fsm_backend_return_direct_handoff_preserves_gate_order() -> None:
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
        return True

    def fail_shallow(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("shallow guard must not run after direct handoff")

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 25},
            boundary_event=None,
            blackboard=PlannerBlackboard(
                current_skill="return",
                return_next_dig_event_seen=False,
            ),
            ports=_ports(
                LegacyFsmReturnTransitionPorts(
                    return_transition_runtime=_return_transition_runtime_provider(
                        handoff_ready=handoff_ready,
                        direct_handoff_ready=direct_handoff_ready,
                        shallow_guard_ready=fail_shallow,
                    ),
                ),
            ),
        )
    )

    assert result.reason == "start_envelope_ready"
    assert calls == ["handoff:25", "direct:25:True"]
    assert result.effects[0].payload["outcome"] == ReturnToDigTransitionOutcome(
        action="direct_handoff",
        reason_suffix="start_envelope_ready",
        next_dig_event_seen=False,
    )


def test_apply_legacy_fsm_runtime_effects_applies_return_runtime_in_order() -> None:
    outcome = ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    projection = ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    calls: list[tuple[str, object]] = []

    apply_legacy_fsm_runtime_effects(
        (
            PlannerRuntimeEffect(
                LEGACY_FSM_TRANSITION_EFFECT,
                {"obs": {"step": 1}, "boundary_event": None},
            ),
            PlannerRuntimeEffect(
                APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
                {"outcome": outcome, "projection": projection},
            ),
        ),
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            ("legacy", int(obs["step"]))
        ),
        apply_return_to_dig_transition_runtime=lambda outcome, projection: calls.append(
            ("return", (outcome, projection))
        ),
    )

    assert calls == [
        ("legacy", 1),
        ("return", (outcome, projection)),
    ]


def test_apply_legacy_fsm_runtime_effects_requires_return_callback() -> None:
    outcome = ReturnToDigTransitionOutcome(
        action="wait",
        reason_suffix="",
        next_dig_event_seen=False,
    )
    projection = ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=False,
        should_transition=False,
    )

    with pytest.raises(ValueError, match="return-to-dig transition"):
        apply_legacy_fsm_runtime_effects(
            (
                PlannerRuntimeEffect(
                    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
                    {"outcome": outcome, "projection": projection},
                ),
            ),
            run_legacy_fsm_transition=lambda *, obs, boundary_event: None,
        )


def test_policy_maybe_switch_skill_applies_return_backend_runtime_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    boundary_event = _FakeBoundaryEvent(next_dig_entry_ready=True)
    applied: list[
        tuple[ReturnToDigTransitionOutcome, ReturnToDigTransitionRuntimeProjection]
    ] = []

    def fail_fallback(*, obs: dict, boundary_event: Any | None) -> None:
        raise AssertionError("return should be handled by backend runtime effect")

    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda obs: True)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("direct handoff must not run after next-dig event")
        ),
    )
    monkeypatch.setattr(
        policy,
        "_return_to_dig_shallow_guard_ready",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("shallow guard must not run after next-dig event")
        ),
    )
    monkeypatch.setattr(
        policy,
        "_apply_return_to_dig_transition_runtime",
        lambda outcome, projection: applied.append((outcome, projection)) or True,
    )
    monkeypatch.setattr(policy, "_run_legacy_fsm_transition", fail_fallback)

    policy._maybe_switch_skill(obs={"step": 26}, boundary_event=boundary_event)

    assert applied == [
        (
            ReturnToDigTransitionOutcome(
                action="next_dig_event",
                reason_suffix="next_dig_entry_ready",
                next_dig_event_seen=True,
            ),
            ReturnToDigTransitionRuntimeProjection(
                next_dig_event_seen=True,
                should_transition=True,
                completed_transition_increment=1,
                cycle_index_increment=1,
            ),
        )
    ]


def _make_policy(**overrides: Any) -> PrimitivePlannerACTPolicy:
    kwargs: dict[str, Any] = {
        "dig_policy": _ConstantPolicy(0.0),
        "carry_policy": _ConstantPolicy(1.0),
        "dump_policy": _ConstantPolicy(2.0),
        "return_policy": _ConstantPolicy(3.0),
        "boundary_detector": _FakeBoundaryDetector(
            boundary_profile="v2_4_5_spatial_mass"
        ),
        "dig_to_carry_min_bucket_mass_kg": 999.0,
        "dump_ready_hold_steps": 3,
        "dump_done_hold_steps": 30,
    }
    kwargs.update(overrides)
    return PrimitivePlannerACTPolicy(**kwargs)


def _return_transition_runtime_provider(
    *,
    handoff_ready,
    direct_handoff_ready,
    shallow_guard_ready,
    semantic_boundary_profile_active: bool = False,
):
    service = ReturnToDigTransitionService()

    def provider(
        *,
        obs: dict,
        boundary_event: Any | None,
        previous_next_dig_event_seen: bool,
    ) -> ReturnToDigTransitionRuntime:
        handoff = handoff_ready(obs)
        request = service.transition_request(
            handoff_ready=handoff,
            boundary_event=boundary_event,
            previous_next_dig_event_seen=previous_next_dig_event_seen,
            semantic_boundary_profile_active=semantic_boundary_profile_active,
        )
        direct = False
        shallow = False
        if request.should_check_direct_handoff:
            direct = direct_handoff_ready(obs, handoff_ready=handoff)
        if request.should_check_shallow_guard(direct):
            shallow = shallow_guard_ready(
                obs=obs,
                boundary_event=boundary_event,
            )
        outcome = service.classify(
            request.facts_with_gate_results(
                direct_handoff_ready=direct,
                shallow_guard_ready=shallow,
            ),
            request.config,
        )
        projection = service.transition_runtime_projection(outcome)
        return ReturnToDigTransitionRuntime(
            outcome=outcome,
            projection=projection,
        )

    return provider


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, _obs: dict[str, Any]) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryEvent:
    def __init__(
        self,
        *,
        next_dig_entry_ready: bool = False,
    ) -> None:
        self.next_dig_entry_ready = bool(next_dig_entry_ready)
        self.qualified_dig_start = False


class _FakeBoundaryDetector:
    def __init__(self, *, boundary_profile: str) -> None:
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": str(boundary_profile)},
        )()

    def reset(self) -> None:
        pass

    def update(self, **_kwargs: Any) -> _FakeBoundaryEvent:
        return _FakeBoundaryEvent()
