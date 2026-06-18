from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

import pytest

from testbed.planner.dig_lifecycle import (
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.dump_lifecycle import (
    CarryTransitionRuntimeState,
    DumpLifecycleOutcome,
    DumpTransitionRuntimeState,
)
from testbed.planner.return_to_dig_transition import (
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntimeProjection,
)
from testbed.planner.runtime import (
    PlannerBackendPorts,
    PlannerBackend,
    PlannerBlackboard,
    PlannerDigTransitionPorts,
    PlannerDumpLifecyclePorts,
    PlannerReturnTransitionPorts,
    PlannerSkillNames,
    PlannerTickContext,
)
from testbed.planner.runtime import behavior_tree
from testbed.planner.runtime import transition_nodes
from testbed.planner.runtime.behavior_tree import (
    BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME,
    BehaviorTreeBackend,
)
from testbed.planner.runtime.effects import (
    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
)


def test_behavior_tree_backend_is_experimental_backend_contract() -> None:
    backend = BehaviorTreeBackend()

    assert backend.name == BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME
    assert isinstance(backend, PlannerBackend)
    with pytest.raises(NotImplementedError, match="experimental.*not wired"):
        backend.tick(
            PlannerTickContext(
                obs={"step": 1},
                blackboard=PlannerBlackboard(current_skill="dig"),
            )
        )


def test_behavior_tree_runtime_contract_does_not_import_shadow_runner_or_shell() -> None:
    source = inspect.getsource(behavior_tree) + inspect.getsource(transition_nodes)

    assert "legacy_fsm" not in source
    assert "primitive_action_tree" not in source
    assert "primitive_planner" not in source


def test_behavior_tree_return_node_uses_runtime_ports_without_shell() -> None:
    calls: list[str] = []
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

    @dataclass(frozen=True)
    class ReturnRuntime:
        outcome: ReturnToDigTransitionOutcome
        projection: ReturnToDigTransitionRuntimeProjection

    def return_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        previous_next_dig_event_seen: bool,
    ) -> ReturnRuntime:
        calls.append(
            "return:"
            f"{obs['step']}:"
            f"{boundary_event is not None}:"
            f"{previous_next_dig_event_seen}"
        )
        return ReturnRuntime(outcome=outcome, projection=projection)

    result = BehaviorTreeBackend().tick(
        PlannerTickContext(
            obs={"step": 11},
            boundary_event=object(),
            blackboard=PlannerBlackboard(
                current_skill="return",
                return_next_dig_event_seen=True,
            ),
            ports=PlannerBackendPorts(
                skill_names=PlannerSkillNames(
                    bootstrap="bootstrap",
                    pre_dig_align="pre_dig_align",
                    dig="dig",
                    carry="carry",
                    dump="dump",
                    return_skill="return",
                ),
                return_transition=PlannerReturnTransitionPorts(
                    return_transition_runtime=return_transition_runtime,
                ),
            ),
        )
    )

    assert calls == ["return:11:True:True"]
    assert result.node_path == ("behavior_tree", "transition", "return")
    assert result.status == "running"
    assert result.reason == "next_dig_entry_ready"
    assert result.effects[0].effect_type == (
        APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT
    )
    assert result.effects[0].payload == {
        "outcome": outcome,
        "projection": projection,
    }
    assert dict(result.diagnostics) == {
        "active_skill": "return",
        "action": "next_dig_event",
        "reason_suffix": "next_dig_entry_ready",
        "next_dig_event_seen": True,
    }


def test_behavior_tree_dig_node_uses_runtime_ports_without_shell() -> None:
    calls: list[str] = []

    def transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> DigTransitionRuntimeProjection:
        calls.append(f"dig_runtime:{obs['step']}:{boundary_event is not None}")
        return DigTransitionRuntimeProjection(
            outcome=DigTransitionRuntimeOutcome(
                action="carry",
                switch_reason="dig_to_carry_target_payload_loaded",
            ),
            dig_to_carry_checked=True,
            dig_to_carry_reason="target_payload_loaded",
        )

    result = BehaviorTreeBackend().tick(
        PlannerTickContext(
            obs={"step": 15},
            boundary_event=object(),
            blackboard=PlannerBlackboard(current_skill="dig"),
            ports=PlannerBackendPorts(
                skill_names=PlannerSkillNames(
                    bootstrap="bootstrap",
                    pre_dig_align="pre_dig_align",
                    dig="dig",
                    carry="carry",
                    dump="dump",
                    return_skill="return",
                ),
                dig_transition=PlannerDigTransitionPorts(
                    transition_runtime=transition_runtime,
                ),
            ),
        )
    )

    assert calls == ["dig_runtime:15:True"]
    assert result.node_path == ("behavior_tree", "transition", "dig")
    assert result.status == "running"
    assert result.reason == "dig_to_carry_target_payload_loaded"
    assert result.effects[0].effect_type == (
        APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT
    )
    assert dict(result.effects[0].payload["obs"]) == {"step": 15}
    projection = result.effects[0].payload["projection"]
    assert isinstance(projection, DigTransitionRuntimeProjection)
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="carry",
        switch_reason="dig_to_carry_target_payload_loaded",
    )
    assert projection.dig_to_carry_checked is True
    assert projection.dig_to_carry_reason == "target_payload_loaded"
    assert dict(result.diagnostics) == {
        "active_skill": "dig",
        "action": "carry",
        "switch_reason": "dig_to_carry_target_payload_loaded",
    }


def test_behavior_tree_carry_node_uses_runtime_ports_without_shell() -> None:
    calls: list[str] = []

    def carry_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_ready_hold_count: int,
    ) -> CarryTransitionRuntimeState:
        calls.append(
            "carry:"
            f"{obs['step']}:"
            f"{boundary_event is not None}:"
            f"{current_dump_ready_hold_count}"
        )
        return CarryTransitionRuntimeState(
            dump_ready_hold_count=current_dump_ready_hold_count + 1,
            outcome=DumpLifecycleOutcome(
                action="dump",
                switch_reason="carry_to_dump_target_ready",
            ),
        )

    result = BehaviorTreeBackend().tick(
        PlannerTickContext(
            obs={"step": 21},
            boundary_event=object(),
            blackboard=PlannerBlackboard(
                current_skill="carry",
                dump_ready_hold_count=4,
            ),
            ports=PlannerBackendPorts(
                skill_names=PlannerSkillNames(
                    bootstrap="bootstrap",
                    pre_dig_align="pre_dig_align",
                    dig="dig",
                    carry="carry",
                    dump="dump",
                    return_skill="return",
                ),
                dump_lifecycle=PlannerDumpLifecyclePorts(
                    carry_transition_runtime=carry_transition_runtime,
                    dump_transition_runtime=_unused_dump_transition_runtime,
                ),
            ),
        )
    )

    assert calls == ["carry:21:True:4"]
    assert result.node_path == ("behavior_tree", "transition", "carry")
    assert result.status == "running"
    assert result.reason == "carry_to_dump_target_ready"
    assert result.effects[0].effect_type == APPLY_CARRY_TRANSITION_RUNTIME_EFFECT
    assert result.effects[0].payload == {
        "runtime": CarryTransitionRuntimeState(
            dump_ready_hold_count=5,
            outcome=DumpLifecycleOutcome(
                action="dump",
                switch_reason="carry_to_dump_target_ready",
            ),
        ),
        "obs": {"step": 21},
    }
    assert dict(result.diagnostics) == {
        "active_skill": "carry",
        "action": "dump",
        "switch_reason": "carry_to_dump_target_ready",
    }


def test_behavior_tree_dump_node_uses_runtime_ports_without_shell() -> None:
    calls: list[str] = []

    def dump_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_done_hold_count: int,
    ) -> DumpTransitionRuntimeState:
        calls.append(
            "dump:"
            f"{obs['step']}:"
            f"{boundary_event is not None}:"
            f"{current_dump_done_hold_count}"
        )
        return DumpTransitionRuntimeState(
            dump_done_hold_count=current_dump_done_hold_count + 1,
            outcome=DumpLifecycleOutcome(
                action="return",
                switch_reason="dump_to_return_mass_low",
                coverage_reason="dump_mass_low",
            ),
        )

    result = BehaviorTreeBackend().tick(
        PlannerTickContext(
            obs={"step": 27},
            boundary_event=object(),
            blackboard=PlannerBlackboard(
                current_skill="dump",
                dump_done_hold_count=6,
            ),
            ports=PlannerBackendPorts(
                skill_names=PlannerSkillNames(
                    bootstrap="bootstrap",
                    pre_dig_align="pre_dig_align",
                    dig="dig",
                    carry="carry",
                    dump="dump",
                    return_skill="return",
                ),
                dump_lifecycle=PlannerDumpLifecyclePorts(
                    carry_transition_runtime=_unused_carry_transition_runtime,
                    dump_transition_runtime=dump_transition_runtime,
                ),
            ),
        )
    )

    assert calls == ["dump:27:True:6"]
    assert result.node_path == ("behavior_tree", "transition", "dump")
    assert result.status == "running"
    assert result.reason == "dump_to_return_mass_low"
    assert result.effects[0].effect_type == APPLY_DUMP_TRANSITION_RUNTIME_EFFECT
    assert result.effects[0].payload == {
        "runtime": DumpTransitionRuntimeState(
            dump_done_hold_count=7,
            outcome=DumpLifecycleOutcome(
                action="return",
                switch_reason="dump_to_return_mass_low",
                coverage_reason="dump_mass_low",
            ),
        ),
        "obs": {"step": 27},
    }
    assert dict(result.diagnostics) == {
        "active_skill": "dump",
        "action": "return",
        "switch_reason": "dump_to_return_mass_low",
    }


def _unused_carry_transition_runtime(**_kwargs: object) -> CarryTransitionRuntimeState:
    raise AssertionError("carry transition runtime should not be called")


def _unused_dump_transition_runtime(**_kwargs: object) -> DumpTransitionRuntimeState:
    raise AssertionError("dump transition runtime should not be called")
