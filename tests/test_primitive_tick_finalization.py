from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.primitive.execution.cycle_state import (
    PrimitiveCycleReportStatus,
    PrimitiveCycleRuntimeState,
)
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.tick_finalization import (
    PrimitivePlannerDebugState,
    PrimitiveTickFinalizationInputs,
    PrimitiveTickFinalizationRuntime,
    PrimitiveTickFinalizationRuntimePorts,
    PrimitiveTickFinalizationService,
)
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_OLD_TICK_FINALIZATION_POLICY_WRAPPERS = (
    "_record_tick_previous_action",
    "_transition_completed_after_tick_dispatch",
    "_finalize_tick_debug_state",
    "_make_debug_state",
    "_tick_finalization_inputs",
    "_account_return_timeout_for_tick",
    "_tick_finalization_service",
)


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


def _cycle_report_status() -> PrimitiveCycleReportStatus:
    return PrimitiveCycleReportStatus(
        completed_transition_count=1,
        transition_timeout_count=2,
        dump_ready_hold_count=3,
        dump_done_hold_count=4,
        primitive_cycle_index=5,
        dig_step_count=6,
        dig_best_mass_kg=7.5,
        dig_mass_plateau_count=8,
        dig_to_carry_reason="loaded",
        dig_bad_replan_count=9,
        dig_exit_guard_replan_count=10,
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


def test_policy_no_longer_exposes_tick_finalization_private_wrappers() -> None:
    for wrapper_name in _OLD_TICK_FINALIZATION_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__


def test_tick_finalization_runtime_builds_and_writes_debug_state() -> None:
    execution_state = PrimitiveExecutionRuntimeState(
        skill_name="dig",
        switch_reason="dig_to_carry_loaded",
    )
    ports = PrimitiveTickFinalizationRuntimePorts(
        execution_state=execution_state,
        cycle_state=PrimitiveCycleRuntimeState(),
        return_state=PrimitiveReturnRuntimeState(),
        cycle_report_status=_cycle_report_status,
        first_dig_policy_active=lambda: True,
        skill_ids={"dig": 0, "return": 3},
        primitive_checkpoint_paths={
            "dig": "/ckpt/dig.pt",
            "first_dig": "/ckpt/first_dig.pt",
            "return": "/ckpt/return.pt",
        },
        transition_skill_names=("return",),
        return_max_steps=3,
    )
    runtime = PrimitiveTickFinalizationRuntime.from_ports(ports)

    inputs = runtime.finalization_inputs(
        transition_timeout=False,
        transition_completed=True,
    )
    made_state = runtime.make_debug_state(
        transition_timeout=False,
        transition_completed=True,
    )
    runtime.finalize_debug_state(
        transition_timeout=False,
        transition_completed=True,
    )

    assert inputs.skill_name == "dig"
    assert inputs.skill_switch_reason == "dig_to_carry_loaded"
    assert inputs.first_dig_policy_active is True
    assert inputs.completed_transition_count == 1
    assert inputs.transition_timeout_count == 2
    assert made_state == PrimitivePlannerDebugState(
        skill_name="dig",
        skill_id=0,
        skill_switch_reason="dig_to_carry_loaded",
        primitive_checkpoint_path="/ckpt/first_dig.pt",
        hybrid_mode=HYBRID_MODE_WORK,
        transition_timeout=False,
        transition_completed=True,
        completed_transition_count=1,
        transition_timeout_count=2,
        dump_ready_hold_count=3,
        dump_done_hold_count=4,
        primitive_cycle_index=5,
    )
    assert execution_state.debug_state == made_state


def test_tick_finalization_runtime_accounts_return_timeout_only_for_return() -> None:
    execution_state = PrimitiveExecutionRuntimeState(skill_name="dig")
    cycle_state = PrimitiveCycleRuntimeState()
    return_state = PrimitiveReturnRuntimeState(return_step_count=2)
    runtime = PrimitiveTickFinalizationRuntime.from_ports(
        PrimitiveTickFinalizationRuntimePorts(
            execution_state=execution_state,
            cycle_state=cycle_state,
            return_state=return_state,
            cycle_report_status=_cycle_report_status,
            first_dig_policy_active=lambda: False,
            skill_ids={"dig": 0, "return": 3},
            primitive_checkpoint_paths={"dig": "/ckpt/dig.pt"},
            transition_skill_names=("return",),
            return_max_steps=3,
        )
    )

    assert runtime.account_return_timeout() is False
    assert return_state.return_step_count == 2
    assert cycle_state.transition_timeout_count == 0

    execution_state.set_skill_name("return")

    assert runtime.account_return_timeout() is True
    assert return_state.return_step_count == 3
    assert cycle_state.transition_timeout_count == 1
