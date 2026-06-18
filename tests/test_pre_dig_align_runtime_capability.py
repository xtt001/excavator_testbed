from __future__ import annotations

from typing import Any

from testbed.planner.dig_start_alignment_outcome import (
    DigStartAlignmentOutcomeService,
    PreDigAlignOutcome,
    PreDigAlignReplanHandoffRequest,
    PreDigAlignReplanHandoffRuntime,
    PreDigAlignTimeoutHandoffResult,
    pre_dig_align_outcome_from_gate_providers,
    pre_dig_align_replan_handoff_request,
    pre_dig_align_replan_handoff_runtime_from_providers,
)


def test_pre_dig_align_outcome_uses_surface_guard_path_first() -> None:
    calls: list[str] = []

    def surface_guard_triggered(obs: dict[str, Any]) -> bool:
        calls.append(f"surface_trigger:{obs['step']}")
        return True

    def surface_guard_handoff(obs: dict[str, Any]) -> bool:
        calls.append(f"surface_handoff:{obs['step']}")
        return False

    def fail_ready(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("ready gate must not run after surface guard")

    def fail_timeout(*_args: Any, **_kwargs: Any) -> PreDigAlignTimeoutHandoffResult:
        raise AssertionError("timeout gate must not run after surface guard")

    outcome = pre_dig_align_outcome_from_gate_providers(
        service=DigStartAlignmentOutcomeService(),
        obs={"step": 4},
        step_count=0,
        max_steps=3,
        surface_guard_triggered=surface_guard_triggered,
        surface_guard_can_handoff=surface_guard_handoff,
        ready=fail_ready,
        timeout_can_handoff=fail_timeout,
    )

    assert calls == ["surface_trigger:4", "surface_handoff:4"]
    assert outcome == PreDigAlignOutcome(
        action="surface_guard_replan",
        switch_reason="pre_dig_align_to_dig_surface_guard_replan",
        reject_reason="pre_align_surface_penetration_entry_gap",
    )


def test_pre_dig_align_outcome_skips_timeout_when_ready() -> None:
    calls: list[str] = []

    def surface_guard_triggered(obs: dict[str, Any]) -> bool:
        calls.append(f"surface_trigger:{obs['step']}")
        return False

    def fail_surface_handoff(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("surface handoff must not run without surface guard")

    def ready(obs: dict[str, Any]) -> bool:
        calls.append(f"ready:{obs['step']}")
        return True

    def fail_timeout(*_args: Any, **_kwargs: Any) -> PreDigAlignTimeoutHandoffResult:
        raise AssertionError("timeout gate must not run when ready")

    outcome = pre_dig_align_outcome_from_gate_providers(
        service=DigStartAlignmentOutcomeService(),
        obs={"step": 5},
        step_count=4,
        max_steps=3,
        surface_guard_triggered=surface_guard_triggered,
        surface_guard_can_handoff=fail_surface_handoff,
        ready=ready,
        timeout_can_handoff=fail_timeout,
    )

    assert calls == ["surface_trigger:5", "ready:5"]
    assert outcome == PreDigAlignOutcome(
        action="ready",
        switch_reason="pre_dig_align_to_dig_ready",
    )


def test_pre_dig_align_outcome_uses_timeout_reason_when_timed_out() -> None:
    calls: list[str] = []

    def surface_guard_triggered(obs: dict[str, Any]) -> bool:
        calls.append(f"surface_trigger:{obs['step']}")
        return False

    def fail_surface_handoff(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("surface handoff must not run without surface guard")

    def ready(obs: dict[str, Any]) -> bool:
        calls.append(f"ready:{obs['step']}")
        return False

    def timeout_can_handoff(obs: dict[str, Any]) -> PreDigAlignTimeoutHandoffResult:
        calls.append(f"timeout:{obs['step']}")
        return PreDigAlignTimeoutHandoffResult(
            ready=True,
            reason="pre_dig_align_to_dig_timeout_intent_close",
        )

    outcome = pre_dig_align_outcome_from_gate_providers(
        service=DigStartAlignmentOutcomeService(),
        obs={"step": 6},
        step_count=3,
        max_steps=3,
        surface_guard_triggered=surface_guard_triggered,
        surface_guard_can_handoff=fail_surface_handoff,
        ready=ready,
        timeout_can_handoff=timeout_can_handoff,
    )

    assert calls == ["surface_trigger:6", "ready:6", "timeout:6"]
    assert outcome == PreDigAlignOutcome(
        action="timeout_handoff",
        switch_reason="pre_dig_align_to_dig_timeout_intent_close",
    )


def test_pre_dig_align_replan_handoff_request_filters_unsupported_modes() -> None:
    assert pre_dig_align_replan_handoff_request(
        planner_mode="none",
    ) == PreDigAlignReplanHandoffRequest(should_attempt=False)
    assert pre_dig_align_replan_handoff_request(
        planner_mode="operator_prior_coverage",
    ) == PreDigAlignReplanHandoffRequest(should_attempt=True)
    assert pre_dig_align_replan_handoff_request(
        planner_mode="operator_prior_sweep_belief",
    ) == PreDigAlignReplanHandoffRequest(should_attempt=True)


def test_pre_dig_align_replan_handoff_runtime_stops_after_build_failure() -> None:
    calls: list[str] = []

    def build_plan(obs: dict[str, Any]) -> object:
        calls.append(f"build:{obs['step']}")
        raise RuntimeError("no plan")

    def fail_entry(*_args: Any, **_kwargs: Any) -> float:
        raise AssertionError("entry-error must not run after build failure")

    def fail_timeout(*_args: Any, **_kwargs: Any) -> PreDigAlignTimeoutHandoffResult:
        raise AssertionError("timeout must not run after build failure")

    runtime = pre_dig_align_replan_handoff_runtime_from_providers(
        obs={"step": 8},
        build_dig_cut_plan=build_plan,
        entry_error=fail_entry,
        timeout_can_handoff=fail_timeout,
    )

    assert calls == ["build:8"]
    assert runtime == PreDigAlignReplanHandoffRuntime(action="build_failed")


def test_pre_dig_align_replan_handoff_runtime_preserves_gate_order() -> None:
    calls: list[str] = []
    plan_state = object()

    def build_plan(obs: dict[str, Any]) -> object:
        calls.append(f"build:{obs['step']}")
        return plan_state

    def entry_error(obs: dict[str, Any]) -> float:
        calls.append(f"entry:{obs['step']}")
        return 0.12

    def timeout_can_handoff(
        obs: dict[str, Any],
        *,
        entry_error_m: float,
    ) -> PreDigAlignTimeoutHandoffResult:
        calls.append(f"timeout:{obs['step']}:{entry_error_m}")
        return PreDigAlignTimeoutHandoffResult(
            ready=True,
            reason="pre_dig_align_to_dig_timeout_close_enough",
        )

    runtime = pre_dig_align_replan_handoff_runtime_from_providers(
        obs={"step": 9},
        build_dig_cut_plan=build_plan,
        entry_error=entry_error,
        timeout_can_handoff=timeout_can_handoff,
    )

    assert calls == ["build:9", "entry:9", "timeout:9:0.12"]
    assert runtime == PreDigAlignReplanHandoffRuntime(
        action="handoff",
        dig_cut_plan_state=plan_state,
        entry_error_m=0.12,
        timeout=PreDigAlignTimeoutHandoffResult(
            ready=True,
            reason="pre_dig_align_to_dig_timeout_close_enough",
        ),
    )
