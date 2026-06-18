from __future__ import annotations

from testbed.planner import dig_lifecycle
from testbed.planner.dig_lifecycle import (
    DigGateDecision,
    DigLifecycleConfig,
    DigLifecycleFacts,
    DigLifecycleGateService,
    DigTransitionRuntimeOutcome,
)


def test_dig_transition_runtime_projection_skips_later_gates_after_exit_guard() -> None:
    calls: list[str] = []

    class SpyService(DigLifecycleGateService):
        def exit_guard_ready(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> bool:
            calls.append("exit_guard")
            return True

        def bad_replan_ready(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> bool:
            raise AssertionError("bad_replan must not run after exit guard")

        def complete_boundary_low_payload(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> bool:
            raise AssertionError("complete_low must not run after exit guard")

        def dig_to_carry_ready(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> DigGateDecision:
            raise AssertionError("dig_to_carry must not run after exit guard")

    projection = dig_lifecycle.dig_transition_runtime_projection_from_facts(
        service=SpyService(),
        facts=_facts(),
        config=_config(),
    )

    assert calls == ["exit_guard"]
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="failed_dig",
        counter="exit_guard_replan",
        failed_dig_reason="exit_overshoot_low_payload",
        coverage_reject_reason="exit_overshoot_low_payload",
    )
    assert projection.exit_guard_replan_count_increment == 1
    assert projection.bad_replan_count_increment == 0
    assert projection.dig_to_carry_checked is False
    assert projection.dig_to_carry_reason == ""


def test_dig_transition_runtime_projection_records_checked_carry_reason() -> None:
    calls: list[str] = []

    class SpyService(DigLifecycleGateService):
        def exit_guard_ready(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> bool:
            calls.append("exit_guard")
            return False

        def bad_replan_ready(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> bool:
            calls.append("bad_replan")
            return False

        def complete_boundary_low_payload(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> bool:
            calls.append("complete_low")
            return False

        def dig_to_carry_ready(
            self,
            facts: DigLifecycleFacts,
            config: DigLifecycleConfig,
        ) -> DigGateDecision:
            calls.append("dig_to_carry")
            return DigGateDecision(True, "target_payload_loaded")

    projection = dig_lifecycle.dig_transition_runtime_projection_from_facts(
        service=SpyService(),
        facts=_facts(),
        config=_config(),
    )

    assert calls == [
        "exit_guard",
        "bad_replan",
        "complete_low",
        "dig_to_carry",
    ]
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="carry",
        switch_reason="dig_to_carry_target_payload_loaded",
    )
    assert projection.dig_to_carry_checked is True
    assert projection.dig_to_carry_reason == "target_payload_loaded"


def _facts() -> DigLifecycleFacts:
    return DigLifecycleFacts(
        mass_in_bucket_kg=0.0,
        min_distance_to_dig_area_m=0.0,
        carry_mass_in_bucket_kg=0.0,
        carry_min_distance_to_dig_area_m=0.0,
        semantic_boundary_profile_active=False,
        boundary_dig_complete=False,
        coverage_terminal_stop_requested=False,
        dig_step_count=0,
        dig_best_mass_kg=0.0,
        dig_mass_plateau_count=0,
        coverage_current_payload_gain_kg=0.0,
    )


def _config() -> DigLifecycleConfig:
    return DigLifecycleConfig(
        dig_to_carry_min_bucket_mass_kg=10.0,
        dig_to_carry_min_distance_to_dig_area_m=0.0,
        dig_to_carry_target_bucket_mass_kg=10.0,
        dig_to_carry_mass_plateau_enabled=True,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=5.0,
        dig_to_carry_mass_plateau_epsilon_kg=0.1,
        dig_to_carry_mass_plateau_hold_steps=2,
        dig_to_carry_mass_plateau_min_steps=2,
        dig_bad_replan_enabled=True,
        dig_bad_replan_max_steps=5,
        dig_bad_replan_min_bucket_mass_kg=1.0,
        dig_exit_guard_enabled=True,
        dig_exit_guard_min_steps=5,
        dig_exit_guard_overshoot_m=0.1,
        dig_exit_guard_min_bucket_mass_kg=1.0,
        dump_ready_min_bucket_mass_kg=1.0,
    )
