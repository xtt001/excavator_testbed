from __future__ import annotations

from types import MethodType
from typing import Any

import numpy as np
import pytest

from testbed.planner.primitive_tick_finalization import (
    PrimitivePlannerDebugState,
    PrimitiveTickFinalizationInputs,
    PrimitiveTickFinalizationService,
)
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _inputs(
    *,
    skill_name: str = "dig",
    skill_ids: dict[str, int] | None = None,
    transition_skill_names: tuple[str, ...] = ("return", "pre_dig_align"),
    first_dig_policy_active: bool = False,
    approach_ready_hold_count: int = 0,
    dump_release_ready_hold_count: int = 0,
) -> PrimitiveTickFinalizationInputs:
    return PrimitiveTickFinalizationInputs(
        skill_name=skill_name,
        skill_ids=skill_ids or {"dig": 0, "carry": 1, "dump": 2, "return": 3},
        skill_switch_reason="dig_to_carry_loaded",
        primitive_checkpoint_paths={
            "dig": "/ckpt/dig.pt",
            "first_dig": "/ckpt/first_dig.pt",
            "return": "/ckpt/return.pt",
            "pre_dig_align": "/ckpt/pre_dig_align.pt",
            "approach_dump": "/ckpt/approach.pt",
            "dump_release": "/ckpt/dump_release.pt",
        },
        first_dig_policy_active=first_dig_policy_active,
        transition_skill_names=transition_skill_names,
        transition_timeout=True,
        transition_completed=False,
        completed_transition_count=7,
        transition_timeout_count=3,
        dump_ready_hold_count=11,
        dump_done_hold_count=13,
        primitive_cycle_index=5,
        approach_ready_hold_count=approach_ready_hold_count,
        dump_release_ready_hold_count=dump_release_ready_hold_count,
    )


def test_previous_action_is_copied_without_aliasing() -> None:
    action = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    service = PrimitiveTickFinalizationService()

    stored = service.copy_previous_action(action)
    action[0] = 99.0

    assert stored.dtype == np.float32
    assert stored.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert stored is not action


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("return_to_dig_start_envelope_ready", True),
        ("return_to_pre_dig_align_start_envelope_ready", False),
        ("dig_to_carry_loaded", False),
        ("return_to_dump_unexpected", False),
        ("", False),
    ],
)
def test_transition_completed_after_dispatch_uses_return_prefixes(
    reason: str,
    expected: bool,
) -> None:
    assert (
        PrimitiveTickFinalizationService().transition_completed_after_dispatch(reason)
        is expected
    )


def test_make_debug_state_assembles_4p_fields_and_first_dig_checkpoint() -> None:
    state = PrimitiveTickFinalizationService().make_debug_state(
        _inputs(first_dig_policy_active=True)
    )

    assert state == PrimitivePlannerDebugState(
        skill_name="dig",
        skill_id=0,
        skill_switch_reason="dig_to_carry_loaded",
        primitive_checkpoint_path="/ckpt/first_dig.pt",
        hybrid_mode=HYBRID_MODE_WORK,
        transition_timeout=True,
        transition_completed=False,
        completed_transition_count=7,
        transition_timeout_count=3,
        dump_ready_hold_count=11,
        dump_done_hold_count=13,
        primitive_cycle_index=5,
    )


def test_make_debug_state_marks_4p_return_and_pre_dig_as_transition() -> None:
    service = PrimitiveTickFinalizationService()

    return_state = service.make_debug_state(_inputs(skill_name="return"))
    pre_dig_state = service.make_debug_state(_inputs(skill_name="pre_dig_align"))
    carry_state = service.make_debug_state(_inputs(skill_name="carry"))

    assert return_state.hybrid_mode == HYBRID_MODE_TRANSITION
    assert pre_dig_state.hybrid_mode == HYBRID_MODE_TRANSITION
    assert carry_state.hybrid_mode == HYBRID_MODE_WORK


def test_make_debug_state_assembles_5p_fields_and_return_only_transition() -> None:
    service = PrimitiveTickFinalizationService()
    skill_ids = {
        "dig": 0,
        "carry": 1,
        "approach_dump": 2,
        "dump_release": 3,
        "return": 4,
    }

    approach_state = service.make_debug_state(
        _inputs(
            skill_name="approach_dump",
            skill_ids=skill_ids,
            transition_skill_names=("return",),
            approach_ready_hold_count=17,
            dump_release_ready_hold_count=19,
        )
    )
    return_state = service.make_debug_state(
        _inputs(
            skill_name="return",
            skill_ids=skill_ids,
            transition_skill_names=("return",),
            approach_ready_hold_count=17,
            dump_release_ready_hold_count=19,
        )
    )

    assert approach_state.skill_id == 2
    assert approach_state.primitive_checkpoint_path == "/ckpt/approach.pt"
    assert approach_state.hybrid_mode == HYBRID_MODE_WORK
    assert approach_state.dump_ready_hold_count == 11
    assert approach_state.dump_done_hold_count == 13
    assert approach_state.approach_ready_hold_count == 17
    assert approach_state.dump_release_ready_hold_count == 19
    assert return_state.skill_id == 4
    assert return_state.hybrid_mode == HYBRID_MODE_TRANSITION


def test_policy_tick_finalization_private_methods_delegate_to_service() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    action = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    copied_action = np.asarray([9.0, 8.0, 7.0, 6.0], dtype=np.float32)
    debug_state = PrimitivePlannerDebugState(
        skill_name="dig",
        skill_id=0,
        skill_switch_reason="dig_to_carry_loaded",
        primitive_checkpoint_path="/ckpt/dig.pt",
        hybrid_mode=HYBRID_MODE_WORK,
        transition_timeout=False,
        transition_completed=True,
        completed_transition_count=1,
        transition_timeout_count=2,
        dump_ready_hold_count=3,
        dump_done_hold_count=4,
        primitive_cycle_index=5,
    )
    inputs = object()
    events: list[str] = []

    class _FakeService:
        def copy_previous_action(self, got_action: np.ndarray) -> np.ndarray:
            assert got_action is action
            events.append("copy_previous_action")
            return copied_action

        def transition_completed_after_dispatch(self, reason: str) -> bool:
            assert reason == "return_to_dig_start_envelope_ready"
            events.append("transition_completed")
            return True

        def make_debug_state(self, got_inputs: Any) -> PrimitivePlannerDebugState:
            assert got_inputs is inputs
            events.append("make_debug_state")
            return debug_state

    planner._switch_reason = "return_to_dig_start_envelope_ready"
    planner._tick_finalization_service = MethodType(lambda self: _FakeService(), planner)
    planner._tick_finalization_inputs = MethodType(
        lambda self, *, transition_timeout, transition_completed: inputs,
        planner,
    )

    planner._record_tick_previous_action(action)
    completed = planner._transition_completed_after_tick_dispatch()
    made_state = planner._make_debug_state(
        transition_timeout=False,
        transition_completed=True,
    )
    planner._finalize_tick_debug_state(
        transition_timeout=False,
        transition_completed=True,
    )

    assert planner._prev_action is copied_action
    assert completed is True
    assert made_state is debug_state
    assert planner._debug_state is debug_state
    assert events == [
        "copy_previous_action",
        "transition_completed",
        "make_debug_state",
        "make_debug_state",
    ]
