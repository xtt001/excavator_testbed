from __future__ import annotations

from typing import Any

from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
)
from testbed.planner.primitive_backend_facts import PrimitiveBackendFactsAccess
from testbed.planner.primitive_backend_facts import PrimitiveBootstrapDecisionFacts
from testbed.planner.primitive_decision_capabilities import (
    BootstrapDecisionStatus,
    PrimitiveDecisionCapabilities,
    PrimitiveDecisionCapabilitiesPorts,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import (
    PrimitiveCarryTransitionFacts,
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveDumpTransitionFacts,
    PrimitiveReturnTransitionFacts,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation


class _RecordingTransitionStatusProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], object | None]] = []
        self.dig_status = _dig_status()
        self.carry_status = _carry_status()
        self.dump_status = _dump_status()
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


def _carry_status(**overrides: Any) -> CarryTransitionStatus:
    values: dict[str, Any] = {
        "mass_in_bucket_kg": 0.0,
        "deposited_mass_in_target_box_kg": 0.0,
        "deposit_delta_since_cycle_start_kg": 0.0,
        "semantic_boundary_profile_active": False,
        "dump_committed_event": False,
        "release_onset_event": False,
        "dump_complete_event": False,
        "legacy_dump_start_event": False,
        "carry_release_safety_done": False,
        "dump_ready": False,
        "next_dump_ready_hold_count": 0,
        "ready_to_dump": False,
        "carry_to_dump_reason": "",
        "carry_to_return_reason": "",
    }
    values.update(overrides)
    return CarryTransitionStatus(**values)


def _dump_status(**overrides: Any) -> DumpTransitionStatus:
    values: dict[str, Any] = {
        "mass_in_bucket_kg": 0.0,
        "deposited_mass_in_target_box_kg": 0.0,
        "deposit_delta_since_dump_start_kg": 0.0,
        "semantic_boundary_profile_active": False,
        "dump_complete_event": False,
        "legacy_dump_end_event": False,
        "boundary_dump_done": False,
        "dump_done_mass_low": False,
        "next_dump_done_hold_count": 0,
        "ready_to_return": False,
        "coverage_completion_reason": "",
        "dump_to_return_reason": "",
    }
    values.update(overrides)
    return DumpTransitionStatus(**values)


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


def test_decision_capabilities_backend_facts_constructs_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="carry")
    capabilities, provider = _capabilities(
        current_skill_name="carry",
        current_switch_reason="dig_to_carry_loaded",
    )

    backend_facts = capabilities.backend_facts(context)

    assert isinstance(backend_facts, PrimitiveBackendFactsAccess)
    assert backend_facts.context is context
    assert backend_facts.common.context is context
    assert backend_facts.common.current_skill_name == "carry"
    assert backend_facts.common.current_switch_reason == "dig_to_carry_loaded"
    assert provider.calls == []

    assert backend_facts.carry_transition().status is provider.carry_status
    assert provider.calls == [("carry", obs, boundary_event)]


def test_decision_capabilities_backend_facts_reuses_existing_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="dump")
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []
    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: port_calls.append("current_skill") or "dump",
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
        current_skill_name="dump",
        current_switch_reason="carry_to_dump_target_ready",
    )

    backend_facts = capabilities.backend_facts(context, facts=common)

    assert isinstance(backend_facts, PrimitiveBackendFactsAccess)
    assert backend_facts.common is common
    assert backend_facts.dump_transition().status is provider.dump_status
    assert provider.calls == [("dump", obs, boundary_event)]
    assert port_calls == []


def test_decision_capabilities_backend_facts_bootstrap_reuses_existing_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="bootstrap")
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []
    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=(
                lambda: port_calls.append("current_skill") or "bootstrap"
            ),
            current_switch_reason=lambda: port_calls.append("current_reason") or "",
            should_end_bootstrap=(
                lambda *, obs, boundary_event: port_calls.append("should_end")
                or True
            ),
            bootstrap_end_mode=(
                lambda: port_calls.append("bootstrap_end_mode")
                or "first_qualified_dig_start"
            ),
            should_pre_dig_align_before_dig=(
                lambda: port_calls.append("pre_dig_gate") or True
            ),
            transition_status_provider=provider,
            maybe_handle_residual_pre_dig_align=(
                lambda obs: port_calls.append("residual") or False
            ),
        )
    )
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="bootstrap",
        current_switch_reason="",
    )

    bootstrap_facts = capabilities.backend_facts(
        context,
        facts=common,
    ).bootstrap_decision(pre_dig_align_skill_name="pre_dig_align")

    assert isinstance(bootstrap_facts, PrimitiveBootstrapDecisionFacts)
    assert bootstrap_facts.common is common
    assert bootstrap_facts.status == BootstrapDecisionStatus(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="first_qualified_dig_start",
        should_pre_dig_align_before_dig=True,
        next_skill_after_bootstrap="pre_dig_align",
    )
    assert provider.calls == []
    assert port_calls == ["bootstrap_end_mode", "pre_dig_gate", "should_end"]


def test_decision_capabilities_backend_facts_keeps_compat_mutations_out_of_access() -> None:
    context = _context(skill="return")
    capabilities, _ = _capabilities(current_skill_name="return")

    backend_facts = capabilities.backend_facts(context)
    public_names = {name for name in dir(backend_facts) if not name.startswith("_")}

    assert {
        "sync_dig_transition_reason",
        "refresh_return_transition_state",
        "handle_residual_pre_dig_align",
    }.isdisjoint(public_names)
    assert hasattr(capabilities, "sync_dig_transition_reason")
    assert hasattr(capabilities, "refresh_return_transition_state")
    assert hasattr(capabilities, "handle_residual_pre_dig_align")


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


def test_decision_capabilities_carry_transition_facts_reuses_existing_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="carry")
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []

    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: port_calls.append("current_skill") or "carry",
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
        current_skill_name="carry",
        current_switch_reason="dig_to_carry_loaded",
    )

    carry_facts = capabilities.carry_transition_facts(context, facts=common)

    assert isinstance(carry_facts, PrimitiveCarryTransitionFacts)
    assert carry_facts.common is common
    assert carry_facts.status is provider.carry_status
    assert carry_facts.obs is obs
    assert carry_facts.boundary_event is boundary_event
    assert provider.calls == [("carry", obs, boundary_event)]
    assert port_calls == []


def test_decision_capabilities_dump_transition_facts_reuses_existing_common_facts() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    context = _context(obs=obs, boundary_event=boundary_event, skill="dump")
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []

    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: port_calls.append("current_skill") or "dump",
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
        current_skill_name="dump",
        current_switch_reason="carry_to_dump_target_ready",
    )

    dump_facts = capabilities.dump_transition_facts(context, facts=common)

    assert isinstance(dump_facts, PrimitiveDumpTransitionFacts)
    assert dump_facts.common is common
    assert dump_facts.status is provider.dump_status
    assert dump_facts.obs is obs
    assert dump_facts.boundary_event is boundary_event
    assert provider.calls == [("dump", obs, boundary_event)]
    assert port_calls == []


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


def test_bootstrap_status_compatibility_uses_backend_facts_access() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    provider = _RecordingTransitionStatusProvider()
    port_calls: list[str] = []
    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=(
                lambda: port_calls.append("current_skill") or "bootstrap"
            ),
            current_switch_reason=lambda: port_calls.append("current_reason") or "",
            should_end_bootstrap=(
                lambda *, obs, boundary_event: port_calls.append("should_end")
                or True
            ),
            bootstrap_end_mode=(
                lambda: port_calls.append("bootstrap_end_mode") or "scripted_qpos"
            ),
            should_pre_dig_align_before_dig=(
                lambda: port_calls.append("pre_dig_gate") or False
            ),
            transition_status_provider=provider,
            maybe_handle_residual_pre_dig_align=(
                lambda obs: port_calls.append("residual") or False
            ),
        )
    )

    status = capabilities.bootstrap_status(
        _context(obs=obs, boundary_event=boundary_event, skill="bootstrap"),
        bootstrap_skill_name="bootstrap",
        pre_dig_align_skill_name="pre_dig_align",
    )

    assert status == BootstrapDecisionStatus(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="scripted_qpos",
        should_pre_dig_align_before_dig=False,
        next_skill_after_bootstrap="dig",
    )
    assert provider.calls == []
    assert port_calls == [
        "current_skill",
        "current_reason",
        "bootstrap_end_mode",
        "pre_dig_gate",
        "should_end",
    ]


def test_residual_pre_dig_align_handler_is_explicit_compatibility_port() -> None:
    obs = {"qpos": [1.0]}
    calls: list[dict[str, Any]] = []
    capabilities, _ = _capabilities(residual_calls=calls)

    assert capabilities.handle_residual_pre_dig_align(_context(obs=obs)) is True
    assert calls == [obs]
