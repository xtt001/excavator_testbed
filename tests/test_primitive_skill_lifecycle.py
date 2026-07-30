from __future__ import annotations

from dataclasses import fields
from types import MethodType

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.skill_lifecycle import (
    PrimitiveSkillLifecyclePorts,
    PrimitiveSkillLifecycleService,
)
from testbed.planner.primitive.execution.state import (
    PrimitiveExecutionRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _ports(
    *,
    skill_name: str = "dig",
    switch_reason: str = "old",
    events: list[str] | None = None,
) -> tuple[PrimitiveSkillLifecyclePorts, dict[str, object], list[str]]:
    events = events if events is not None else []
    execution_state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name=skill_name,
        switch_reason=switch_reason,
    )
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()

    return (
        PrimitiveSkillLifecyclePorts(
            execution_state=execution_state,
            cycle_state=cycle_state,
            return_state=return_state,
            coverage_state=coverage_state,
            reset_active_policy=lambda: events.append(
                f"reset:{execution_state.skill_name}"
            ),
            clear_dig_cut_plan=lambda: events.append("clear_dig_cut_plan"),
        ),
        {
            "execution": execution_state,
            "cycle": cycle_state,
            "return": return_state,
            "coverage": coverage_state,
        },
        events,
    )


def test_same_skill_noop_preserves_reason_and_side_effects() -> None:
    ports, owners, events = _ports(skill_name="dig", switch_reason="old_reason")

    PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
        "dig",
        "new_reason",
    )

    execution_state = owners["execution"]
    assert execution_state.skill_name == "dig"
    assert execution_state.switch_reason == "old_reason"
    assert events == []


def test_same_skill_restart_resets_policy_updates_reason_and_resets_skill_state() -> None:
    ports, owners, events = _ports(skill_name="return", switch_reason="old_reason")
    owners["return"].return_step_count = 17
    owners["return"].return_next_dig_event_seen = True

    PrimitiveSkillLifecycleService.from_ports(ports).restart_skill(
        "hard_bottom_neutral_acknowledged",
    )

    execution_state = owners["execution"]
    assert execution_state.skill_name == "return"
    assert execution_state.switch_reason == "hard_bottom_neutral_acknowledged"
    assert owners["return"].return_step_count == 0
    assert owners["return"].return_next_dig_event_seen is False
    assert events == ["reset:return", "clear_dig_cut_plan"]


def test_switch_to_dig_resets_active_policy_and_dig_lifecycle_without_clear() -> None:
    ports, owners, events = _ports(skill_name="return", switch_reason="old")
    cycle_state = owners["cycle"]
    return_state = owners["return"]
    coverage_state = owners["coverage"]
    cycle_state.dump_ready_hold_count = 5
    cycle_state.dump_done_hold_count = 6
    cycle_state.dig_step_count = 7
    cycle_state.dig_best_mass_kg = 8.5
    cycle_state.dig_mass_plateau_count = 9
    cycle_state.dig_to_carry_reason = "old"
    return_state.return_next_dig_event_seen = True
    coverage_state.coverage_current_payload_gain_kg = 2.5

    PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
        "dig",
        "return_to_dig_next_dig_entry_ready",
    )

    execution_state = owners["execution"]
    assert events == ["reset:dig"]
    assert execution_state.skill_name == "dig"
    assert execution_state.switch_reason == "return_to_dig_next_dig_entry_ready"
    assert return_state.return_next_dig_event_seen is False
    assert cycle_state.dump_ready_hold_count == 0
    assert cycle_state.dump_done_hold_count == 0
    assert coverage_state.coverage_current_payload_gain_kg == 0.0
    assert cycle_state.dig_step_count == 0
    assert cycle_state.dig_best_mass_kg == 0.0
    assert cycle_state.dig_mass_plateau_count == 0
    assert cycle_state.dig_to_carry_reason == ""


def test_switch_to_carry_dump_and_return_reset_expected_counters_and_clear_plan() -> None:
    for target in ("carry", "dump", "return"):
        ports, owners, events = _ports(skill_name="dig", switch_reason="old")
        owners["cycle"].dump_ready_hold_count = 4
        owners["cycle"].dump_done_hold_count = 5
        owners["return"].return_step_count = 6
        owners["return"].return_next_dig_event_seen = True

        PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
            target,
            f"to_{target}",
        )

        assert events == [f"reset:{target}", "clear_dig_cut_plan"]
        if target == "carry":
            assert owners["cycle"].dump_ready_hold_count == 0
        elif target == "dump":
            assert owners["cycle"].dump_done_hold_count == 0
        else:
            assert owners["return"].return_step_count == 0
            assert owners["return"].return_next_dig_event_seen is False


def test_policy_set_skill_delegates_to_skill_lifecycle_service() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    calls: list[tuple[str, str]] = []

    class _FakeLifecycle:
        def set_skill(self, skill_name: str, reason: str) -> None:
            calls.append((skill_name, reason))

    planner._primitive_skill_lifecycle = MethodType(
        lambda self: _FakeLifecycle(),
        planner,
    )

    planner._set_skill("carry", "dig_to_carry_loaded")

    assert calls == [("carry", "dig_to_carry_loaded")]


def test_policy_restart_skill_delegates_to_skill_lifecycle_service() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    calls: list[str] = []

    class _FakeLifecycle:
        def restart_skill(self, reason: str) -> None:
            calls.append(reason)

    planner._primitive_skill_lifecycle = MethodType(
        lambda self: _FakeLifecycle(),
        planner,
    )

    planner._restart_skill("hard_bottom_neutral_acknowledged")

    assert calls == ["hard_bottom_neutral_acknowledged"]


def test_skill_lifecycle_boundary_uses_typed_ports_without_planner_self() -> None:
    port_fields = {field.name for field in fields(PrimitiveSkillLifecyclePorts)}
    service_fields = {field.name for field in fields(PrimitiveSkillLifecycleService)}

    assert "planner" not in port_fields
    assert "self" not in port_fields
    assert {
        "execution_state",
        "cycle_state",
        "return_state",
        "coverage_state",
    } <= port_fields
    assert not {
        "current_skill_name",
        "set_skill_name",
        "set_switch_reason",
        "set_dump_ready_hold_count",
        "set_dump_done_hold_count",
        "set_return_step_count",
        "set_return_next_dig_event_seen",
        "set_coverage_current_payload_gain_kg",
        "set_dig_step_count",
        "set_dig_best_mass_kg",
        "set_dig_mass_plateau_count",
        "set_dig_to_carry_reason",
    } & port_fields
    assert service_fields == {"ports"}
