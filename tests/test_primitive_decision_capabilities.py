from __future__ import annotations

from typing import Any

from testbed.planner.primitive_capabilities import DigTransitionStatus
from testbed.planner.primitive_decision_capabilities import (
    BootstrapDecisionStatus,
    PrimitiveDecisionCapabilities,
    PrimitiveDecisionCapabilitiesPorts,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import (
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveReturnTransitionFacts,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation


class _RecordingTransitionStatusProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], object | None]] = []
        self.dig_status = _dig_status()
        self.carry_status = object()
        self.dump_status = object()
        self.return_status = object()

    def refresh_return_transition_state(
        self,
        obs: dict[str, Any],
    ) -> None:
        self.calls.append(("refresh_return", obs, None))

    def dig_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> object:
        self.calls.append(("dig", obs, boundary_event))
        return self.dig_status

    def sync_dig_transition_reason(self, status: object) -> None:
        self.calls.append(("sync_dig", status, None))

    def carry_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> object:
        self.calls.append(("carry", obs, boundary_event))
        return self.carry_status

    def dump_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> object:
        self.calls.append(("dump", obs, boundary_event))
        return self.dump_status

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> object:
        self.calls.append(("return", obs, boundary_event))
        return self.return_status


def _context(
    *,
    obs: dict[str, Any] | None = None,
    boundary_event: object | None = None,
    skill: str = "dig",
) -> PrimitiveDecisionContext:
    return PrimitiveDecisionContext.from_tick(
        obs=obs if obs is not None else {"qpos": [1.0]},
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision=skill,
            dig_progress_updated=skill == "dig",
        ),
    )


def _dig_status(**overrides: Any) -> DigTransitionStatus:
    values: dict[str, Any] = {
        "dig_step_count": 0,
        "mass_in_bucket_kg": 0.0,
        "min_distance_to_dig_area_m": 0.0,
        "transition_mass_in_bucket_kg": 0.0,
        "transition_min_distance_to_dig_area_m": 0.0,
        "distance_ready": False,
        "semantic_boundary_profile_active": False,
        "coverage_terminal_stop_requested": False,
        "dig_complete_boundary": False,
        "dig_complete_boundary_low_payload": False,
        "dig_bad_replan_ready": False,
        "dig_exit_guard_ready": False,
        "dig_mass_plateau_ready": False,
        "dig_to_carry_ready": False,
        "dig_to_carry_reason": "",
    }
    values.update(overrides)
    return DigTransitionStatus(**values)


def _capabilities(
    *,
    current_skill_name: str = "dig",
    current_switch_reason: str = "",
    should_end_bootstrap: bool = False,
    bootstrap_end_mode: str = "first_qualified_dig_start",
    should_pre_dig_align_before_dig: bool = False,
    transition_status_provider: _RecordingTransitionStatusProvider | None = None,
    residual_calls: list[dict[str, Any]] | None = None,
) -> tuple[PrimitiveDecisionCapabilities, _RecordingTransitionStatusProvider]:
    provider = transition_status_provider or _RecordingTransitionStatusProvider()
    residual_events = residual_calls if residual_calls is not None else []

    def residual_handler(obs: dict[str, Any]) -> bool:
        residual_events.append(obs)
        return True

    return (
        PrimitiveDecisionCapabilities.from_ports(
            PrimitiveDecisionCapabilitiesPorts(
                current_skill_name=lambda: current_skill_name,
                current_switch_reason=lambda: current_switch_reason,
                should_end_bootstrap=(
                    lambda *, obs, boundary_event: should_end_bootstrap
                ),
                bootstrap_end_mode=lambda: bootstrap_end_mode,
                should_pre_dig_align_before_dig=(
                    lambda: should_pre_dig_align_before_dig
                ),
                transition_status_provider=provider,
                maybe_handle_residual_pre_dig_align=residual_handler,
            )
        ),
        provider,
    )


def test_decision_capabilities_route_status_providers_through_context() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event)
    capabilities, provider = _capabilities()

    assert capabilities.dig_transition_status(context) is provider.dig_status
    assert capabilities.carry_transition_status(context) is provider.carry_status
    assert capabilities.dump_transition_status(context) is provider.dump_status
    assert capabilities.return_transition_status(context) is provider.return_status
    assert provider.calls == [
        ("dig", obs, boundary_event),
        ("carry", obs, boundary_event),
        ("dump", obs, boundary_event),
        ("return", obs, boundary_event),
    ]


def test_decision_capabilities_refresh_return_transition_state_is_explicit() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="return")
    capabilities, provider = _capabilities(current_skill_name="return")

    capabilities.refresh_return_transition_state(context)

    assert provider.calls == [("refresh_return", obs, None)]


def test_decision_capabilities_return_status_read_does_not_refresh() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="return")
    capabilities, provider = _capabilities(current_skill_name="return")

    assert capabilities.return_transition_status(context) is provider.return_status

    assert provider.calls == [("return", obs, boundary_event)]


def test_decision_capabilities_dig_transition_facts_reuses_existing_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="dig")
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []

    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: port_calls.append("current_skill") or "dig",
            current_switch_reason=lambda: port_calls.append("current_reason") or "",
            should_end_bootstrap=lambda *, obs, boundary_event: False,
            bootstrap_end_mode=lambda: "first_qualified_dig_start",
            should_pre_dig_align_before_dig=lambda: False,
            transition_status_provider=provider,
            maybe_handle_residual_pre_dig_align=(
                lambda obs: port_calls.append("residual") or False
            ),
        )
    )
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="dig",
        current_switch_reason="",
    )

    dig_facts = capabilities.dig_transition_facts(context, facts=common)

    assert isinstance(dig_facts, PrimitiveDigTransitionFacts)
    assert dig_facts.common is common
    assert dig_facts.status is provider.dig_status
    assert dig_facts.obs is obs
    assert dig_facts.boundary_event is boundary_event
    assert provider.calls == [("dig", obs, boundary_event)]
    assert port_calls == []


def test_decision_capabilities_dig_transition_facts_do_not_sync_reason() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="dig")
    capabilities, provider = _capabilities(current_skill_name="dig")

    dig_facts = capabilities.dig_transition_facts(context)

    assert isinstance(dig_facts, PrimitiveDigTransitionFacts)
    assert dig_facts.status is provider.dig_status
    assert provider.calls == [("dig", obs, boundary_event)]


def test_decision_capabilities_sync_dig_transition_reason_uses_status_from_facts() -> None:
    context = _context(skill="dig")
    capabilities, provider = _capabilities(current_skill_name="dig")
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="dig",
        current_switch_reason="",
    )
    dig_facts = PrimitiveDigTransitionFacts(
        common=common,
        status=provider.dig_status,
    )

    capabilities.sync_dig_transition_reason(dig_facts)

    assert provider.calls == [("sync_dig", provider.dig_status, None)]


def test_decision_capabilities_return_transition_facts_reuses_existing_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="return")
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []

    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: port_calls.append("current_skill") or "return",
            current_switch_reason=lambda: port_calls.append("current_reason") or "",
            should_end_bootstrap=lambda *, obs, boundary_event: False,
            bootstrap_end_mode=lambda: "first_qualified_dig_start",
            should_pre_dig_align_before_dig=lambda: False,
            transition_status_provider=provider,
            maybe_handle_residual_pre_dig_align=(
                lambda obs: port_calls.append("residual") or False
            ),
        )
    )
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="return",
        current_switch_reason="dump_to_return_mass_low",
    )

    return_facts = capabilities.return_transition_facts(context, facts=common)

    assert isinstance(return_facts, PrimitiveReturnTransitionFacts)
    assert return_facts.common is common
    assert return_facts.status is provider.return_status
    assert return_facts.obs is obs
    assert return_facts.boundary_event is boundary_event
    assert provider.calls == [("return", obs, boundary_event)]
    assert port_calls == []


def test_decision_capabilities_return_transition_facts_are_read_only() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="return")
    capabilities, provider = _capabilities(current_skill_name="return")

    return_facts = capabilities.return_transition_facts(context)

    assert isinstance(return_facts, PrimitiveReturnTransitionFacts)
    assert return_facts.status is provider.return_status
    assert provider.calls == [("return", obs, boundary_event)]


def test_decision_capabilities_build_common_facts_without_status_or_residual_calls() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    residual_calls: list[dict[str, Any]] = []
    capabilities, provider = _capabilities(
        current_skill_name="return",
        current_switch_reason="dump_to_return_mass_low",
        residual_calls=residual_calls,
    )
    context = _context(obs=obs, boundary_event=boundary_event, skill="return")

    facts = capabilities.decision_facts(context)

    assert isinstance(facts, PrimitiveDecisionFacts)
    assert facts.context is context
    assert facts.obs is obs
    assert facts.boundary_event is boundary_event
    assert facts.preparation is context.preparation
    assert facts.current_skill_name == "return"
    assert facts.current_switch_reason == "dump_to_return_mass_low"
    assert provider.calls == []
    assert residual_calls == []


def test_bootstrap_status_computes_target_skill_from_mode_and_pre_dig_gate() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    capabilities, _ = _capabilities(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="first_qualified_dig_start",
        should_pre_dig_align_before_dig=True,
    )

    status = capabilities.bootstrap_status(
        _context(obs=obs, boundary_event=boundary_event, skill="bootstrap"),
        bootstrap_skill_name="bootstrap",
        pre_dig_align_skill_name="pre_dig_align",
    )

    assert status == BootstrapDecisionStatus(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="first_qualified_dig_start",
        should_pre_dig_align_before_dig=True,
        next_skill_after_bootstrap="pre_dig_align",
    )

    carry_capabilities, _ = _capabilities(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="loaded_and_clear",
        should_pre_dig_align_before_dig=True,
    )
    assert (
        carry_capabilities.bootstrap_status(
            _context(obs=obs, boundary_event=boundary_event, skill="bootstrap"),
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ).next_skill_after_bootstrap
        == "carry"
    )


def test_residual_pre_dig_align_handler_is_explicit_compatibility_port() -> None:
    obs = {"qpos": [1.0]}
    calls: list[dict[str, Any]] = []
    capabilities, _ = _capabilities(residual_calls=calls)

    assert capabilities.handle_residual_pre_dig_align(_context(obs=obs)) is True
    assert calls == [obs]
