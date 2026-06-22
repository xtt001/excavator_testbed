from __future__ import annotations

from dataclasses import fields
from types import MethodType

from testbed.planner.primitive_skill_lifecycle import (
    PrimitiveSkillLifecyclePorts,
    PrimitiveSkillLifecycleService,
)
from testbed.policies.hybrid.primitive_planner import (
    PRE_DIG_ALIGN_SKILL_NAME,
    PrimitivePlannerACTPolicy,
)


def _ports(
    *,
    state: dict[str, object] | None = None,
    events: list[str] | None = None,
) -> tuple[PrimitiveSkillLifecyclePorts, dict[str, object], list[str]]:
    state = state if state is not None else {"skill": "dig", "reason": "old"}
    events = events if events is not None else []

    def set_value(name: str, value: object) -> None:
        events.append(f"{name}:{value}")
        state[name] = value

    return (
        PrimitiveSkillLifecyclePorts(
            current_skill_name=lambda: str(state["skill"]),
            set_skill_name=lambda value: set_value("skill", value),
            set_switch_reason=lambda value: set_value("reason", value),
            reset_active_policy=lambda: events.append(f"reset:{state['skill']}"),
            clear_dig_cut_plan=lambda: events.append("clear_dig_cut_plan"),
            set_dump_ready_hold_count=lambda value: set_value(
                "dump_ready_hold_count",
                value,
            ),
            set_dump_done_hold_count=lambda value: set_value(
                "dump_done_hold_count",
                value,
            ),
            set_return_step_count=lambda value: set_value("return_step_count", value),
            set_return_next_dig_event_seen=lambda value: set_value(
                "return_next_dig_event_seen",
                value,
            ),
            set_pre_dig_align_step_count=lambda value: set_value(
                "pre_dig_align_step_count",
                value,
            ),
            set_pre_dig_align_hold_count=lambda value: set_value(
                "pre_dig_align_hold_count",
                value,
            ),
            set_pre_dig_align_entry_close_handoff_ready=lambda value: set_value(
                "pre_dig_align_entry_close_handoff_ready",
                value,
            ),
            set_pre_dig_align_entry_intent_handoff_ready=lambda value: set_value(
                "pre_dig_align_entry_intent_handoff_ready",
                value,
            ),
            set_pre_dig_align_timeout_handoff_reason=lambda value: set_value(
                "pre_dig_align_timeout_handoff_reason",
                value,
            ),
            set_pre_dig_align_surface_guard_triggered=lambda value: set_value(
                "pre_dig_align_surface_guard_triggered",
                value,
            ),
            set_coverage_current_payload_gain_kg=lambda value: set_value(
                "coverage_current_payload_gain_kg",
                value,
            ),
            set_dig_step_count=lambda value: set_value("dig_step_count", value),
            set_dig_best_mass_kg=lambda value: set_value("dig_best_mass_kg", value),
            set_dig_mass_plateau_count=lambda value: set_value(
                "dig_mass_plateau_count",
                value,
            ),
            set_dig_to_carry_reason=lambda value: set_value(
                "dig_to_carry_reason",
                value,
            ),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        ),
        state,
        events,
    )


def test_same_skill_noop_preserves_reason_and_side_effects() -> None:
    ports, state, events = _ports(state={"skill": "dig", "reason": "old_reason"})

    PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
        "dig",
        "new_reason",
    )

    assert state == {"skill": "dig", "reason": "old_reason"}
    assert events == []


def test_switch_to_dig_resets_active_policy_and_dig_lifecycle_without_clear() -> None:
    ports, state, events = _ports(state={"skill": "return", "reason": "old"})

    PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
        "dig",
        "return_to_dig_next_dig_entry_ready",
    )

    assert events == [
        "skill:dig",
        "reason:return_to_dig_next_dig_entry_ready",
        "reset:dig",
        "return_next_dig_event_seen:False",
        "dump_ready_hold_count:0",
        "dump_done_hold_count:0",
        "coverage_current_payload_gain_kg:0.0",
        "dig_step_count:0",
        "dig_best_mass_kg:0.0",
        "dig_mass_plateau_count:0",
        "dig_to_carry_reason:",
    ]
    assert state["skill"] == "dig"
    assert state["reason"] == "return_to_dig_next_dig_entry_ready"


def test_switch_to_carry_dump_and_return_reset_expected_counters_and_clear_plan() -> None:
    for target, expected_tail in (
        ("carry", ["dump_ready_hold_count:0", "clear_dig_cut_plan"]),
        ("dump", ["dump_done_hold_count:0", "clear_dig_cut_plan"]),
        (
            "return",
            [
                "return_step_count:0",
                "return_next_dig_event_seen:False",
                "clear_dig_cut_plan",
            ],
        ),
    ):
        ports, _, events = _ports(state={"skill": "dig", "reason": "old"})

        PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
            target,
            f"to_{target}",
        )

        assert events[:3] == [f"skill:{target}", f"reason:to_{target}", f"reset:{target}"]
        assert events[3:] == expected_tail


def test_switch_to_pre_dig_align_skips_active_policy_reset_and_clearing() -> None:
    ports, _, events = _ports(state={"skill": "dig", "reason": "old"})

    PrimitiveSkillLifecycleService.from_ports(ports).set_skill(
        PRE_DIG_ALIGN_SKILL_NAME,
        "dig_to_pre_dig_align_bad_dig_low_payload",
    )

    assert events == [
        f"skill:{PRE_DIG_ALIGN_SKILL_NAME}",
        "reason:dig_to_pre_dig_align_bad_dig_low_payload",
        "pre_dig_align_step_count:0",
        "pre_dig_align_hold_count:0",
        "pre_dig_align_entry_close_handoff_ready:False",
        "pre_dig_align_entry_intent_handoff_ready:False",
        "pre_dig_align_timeout_handoff_reason:",
        "pre_dig_align_surface_guard_triggered:False",
    ]


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


def test_skill_lifecycle_boundary_uses_typed_ports_without_planner_self() -> None:
    port_fields = {field.name for field in fields(PrimitiveSkillLifecyclePorts)}
    service_fields = {field.name for field in fields(PrimitiveSkillLifecycleService)}

    assert "planner" not in port_fields
    assert "self" not in port_fields
    assert service_fields == {"ports"}
