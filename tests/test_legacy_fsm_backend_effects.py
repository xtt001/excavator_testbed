from __future__ import annotations

from typing import Any

import pytest

from testbed.planner.bootstrap import BootstrapTransitionDecision
from testbed.planner.dig_lifecycle import (
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.dig_start_alignment_outcome import PreDigAlignOutcome
from testbed.planner.dump_lifecycle import (
    CarryTransitionRuntimeState,
    DumpLifecycleOutcome,
    DumpTransitionRuntimeState,
)
from testbed.planner.runtime import PlannerRuntimeEffect
from testbed.planner.runtime.legacy_fsm import (
    APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT,
    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
    APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT,
    LEGACY_FSM_TRANSITION_EFFECT,
    apply_legacy_fsm_runtime_effects,
)


def test_apply_legacy_fsm_runtime_effects_preserves_effect_order() -> None:
    first_event = object()
    second_event = object()
    calls: list[tuple[dict[str, Any], object]] = []
    effects = (
        PlannerRuntimeEffect(
            LEGACY_FSM_TRANSITION_EFFECT,
            {"obs": {"step": 1}, "boundary_event": first_event},
        ),
        PlannerRuntimeEffect(
            LEGACY_FSM_TRANSITION_EFFECT,
            {"obs": {"step": 2}, "boundary_event": second_event},
        ),
    )

    apply_legacy_fsm_runtime_effects(
        effects,
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            (dict(obs), boundary_event)
        ),
    )

    assert calls == [({"step": 1}, first_event), ({"step": 2}, second_event)]


def test_apply_legacy_fsm_runtime_effects_applies_bootstrap_decision_in_order() -> None:
    boundary_event = object()
    decision = BootstrapTransitionDecision(
        next_skill="dig",
        switch_reason="bootstrap_to_dig",
    )
    calls: list[tuple[str, object]] = []

    apply_legacy_fsm_runtime_effects(
        (
            PlannerRuntimeEffect(
                LEGACY_FSM_TRANSITION_EFFECT,
                {"obs": {"step": 1}, "boundary_event": boundary_event},
            ),
            PlannerRuntimeEffect(
                APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT,
                {"decision": decision},
            ),
        ),
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            ("legacy", int(obs["step"]))
        ),
        apply_bootstrap_transition_decision=lambda decision: calls.append(
            ("bootstrap", decision)
        ),
    )

    assert calls == [("legacy", 1), ("bootstrap", decision)]


def test_apply_legacy_fsm_runtime_effects_applies_pre_dig_align_outcome_in_order() -> None:
    boundary_event = object()
    outcome = PreDigAlignOutcome(
        action="timeout_replan",
        switch_reason="pre_dig_align_retry_entry_gap",
        reject_reason="align_entry_gap_timeout",
    )
    calls: list[tuple[str, object]] = []

    apply_legacy_fsm_runtime_effects(
        (
            PlannerRuntimeEffect(
                LEGACY_FSM_TRANSITION_EFFECT,
                {"obs": {"step": 1}, "boundary_event": boundary_event},
            ),
            PlannerRuntimeEffect(
                APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT,
                {"outcome": outcome, "obs": {"step": 2}},
            ),
        ),
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            ("legacy", int(obs["step"]))
        ),
        apply_pre_dig_align_outcome=lambda outcome, obs: calls.append(
            ("pre_dig_align", (outcome, dict(obs)))
        ),
    )

    assert calls == [
        ("legacy", 1),
        ("pre_dig_align", (outcome, {"step": 2})),
    ]


def test_apply_legacy_fsm_runtime_effects_applies_dig_projection_in_order() -> None:
    projection = DigTransitionRuntimeProjection(
        outcome=DigTransitionRuntimeOutcome(
            action="failed_dig",
            counter="bad_replan",
            failed_dig_reason="bad_dig_low_payload",
            coverage_reject_reason="bad_dig_low_payload",
        ),
        bad_replan_count_increment=1,
    )
    calls: list[tuple[str, object]] = []

    apply_legacy_fsm_runtime_effects(
        (
            PlannerRuntimeEffect(
                LEGACY_FSM_TRANSITION_EFFECT,
                {"obs": {"step": 1}, "boundary_event": None},
            ),
            PlannerRuntimeEffect(
                APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
                {"projection": projection, "obs": {"step": 2}},
            ),
        ),
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            ("legacy", int(obs["step"]))
        ),
        apply_dig_transition_runtime_projection=lambda projection, obs: calls.append(
            ("dig", (projection, dict(obs)))
        ),
    )

    assert calls == [
        ("legacy", 1),
        ("dig", (projection, {"step": 2})),
    ]


def test_apply_legacy_fsm_runtime_effects_applies_carry_runtime_in_order() -> None:
    runtime = CarryTransitionRuntimeState(
        dump_ready_hold_count=3,
        outcome=DumpLifecycleOutcome(
            action="dump",
            switch_reason="carry_to_dump_target_ready",
        ),
    )
    calls: list[tuple[str, object]] = []

    apply_legacy_fsm_runtime_effects(
        (
            PlannerRuntimeEffect(
                LEGACY_FSM_TRANSITION_EFFECT,
                {"obs": {"step": 1}, "boundary_event": None},
            ),
            PlannerRuntimeEffect(
                APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
                {"runtime": runtime, "obs": {"step": 2}},
            ),
        ),
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            ("legacy", int(obs["step"]))
        ),
        apply_carry_transition_runtime=lambda runtime, obs: calls.append(
            ("carry", (runtime, dict(obs)))
        ),
    )

    assert calls == [
        ("legacy", 1),
        ("carry", (runtime, {"step": 2})),
    ]


def test_apply_legacy_fsm_runtime_effects_applies_dump_runtime_in_order() -> None:
    runtime = DumpTransitionRuntimeState(
        dump_done_hold_count=3,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="dump_to_return_mass_low",
            coverage_reason="dump_mass_low",
        ),
    )
    calls: list[tuple[str, object]] = []

    apply_legacy_fsm_runtime_effects(
        (
            PlannerRuntimeEffect(
                LEGACY_FSM_TRANSITION_EFFECT,
                {"obs": {"step": 1}, "boundary_event": None},
            ),
            PlannerRuntimeEffect(
                APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
                {"runtime": runtime, "obs": {"step": 2}},
            ),
        ),
        run_legacy_fsm_transition=lambda *, obs, boundary_event: calls.append(
            ("legacy", int(obs["step"]))
        ),
        apply_dump_transition_runtime=lambda runtime, obs: calls.append(
            ("dump", (runtime, dict(obs)))
        ),
    )

    assert calls == [
        ("legacy", 1),
        ("dump", (runtime, {"step": 2})),
    ]


def test_apply_legacy_fsm_runtime_effects_requires_bootstrap_callback() -> None:
    decision = BootstrapTransitionDecision(
        next_skill="dig",
        switch_reason="bootstrap_to_dig",
    )

    with pytest.raises(ValueError, match="bootstrap"):
        apply_legacy_fsm_runtime_effects(
            (
                PlannerRuntimeEffect(
                    APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT,
                    {"decision": decision},
                ),
            ),
            run_legacy_fsm_transition=lambda *, obs, boundary_event: None,
        )


def test_apply_legacy_fsm_runtime_effects_requires_pre_dig_align_callback() -> None:
    outcome = PreDigAlignOutcome(action="none")

    with pytest.raises(ValueError, match="pre-dig-align"):
        apply_legacy_fsm_runtime_effects(
            (
                PlannerRuntimeEffect(
                    APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT,
                    {"outcome": outcome, "obs": {"step": 2}},
                ),
            ),
            run_legacy_fsm_transition=lambda *, obs, boundary_event: None,
        )


def test_apply_legacy_fsm_runtime_effects_requires_dig_callback() -> None:
    projection = DigTransitionRuntimeProjection(
        outcome=DigTransitionRuntimeOutcome(action="none")
    )

    with pytest.raises(ValueError, match="dig transition"):
        apply_legacy_fsm_runtime_effects(
            (
                PlannerRuntimeEffect(
                    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
                    {"projection": projection, "obs": {"step": 2}},
                ),
            ),
            run_legacy_fsm_transition=lambda *, obs, boundary_event: None,
        )


def test_apply_legacy_fsm_runtime_effects_requires_carry_callback() -> None:
    runtime = CarryTransitionRuntimeState(
        dump_ready_hold_count=1,
        outcome=DumpLifecycleOutcome(action="none"),
    )

    with pytest.raises(ValueError, match="carry transition"):
        apply_legacy_fsm_runtime_effects(
            (
                PlannerRuntimeEffect(
                    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
                    {"runtime": runtime, "obs": {"step": 2}},
                ),
            ),
            run_legacy_fsm_transition=lambda *, obs, boundary_event: None,
        )


def test_apply_legacy_fsm_runtime_effects_requires_dump_callback() -> None:
    runtime = DumpTransitionRuntimeState(
        dump_done_hold_count=1,
        outcome=DumpLifecycleOutcome(action="none"),
    )

    with pytest.raises(ValueError, match="dump transition"):
        apply_legacy_fsm_runtime_effects(
            (
                PlannerRuntimeEffect(
                    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
                    {"runtime": runtime, "obs": {"step": 2}},
                ),
            ),
            run_legacy_fsm_transition=lambda *, obs, boundary_event: None,
        )
