from __future__ import annotations

from dataclasses import fields
from types import CodeType
from types import MethodType
from typing import Any

import pytest

from testbed.planner.primitive.decision.backends.legacy_fsm import (
    LegacyFSMBranchSet,
    LegacyFSMDecisionBackendFactory,
    LegacyFSMDecisionBackendFactoryPorts,
)
from testbed.planner.primitive.facts.backend import PrimitiveBackendFactsSource
from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
    PrimitiveFSMCapabilityProviderConfig,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.decision.input import PrimitiveBackendDecisionInput
from testbed.planner.primitive.decision.contracts import (
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.facts.decision import PrimitiveDecisionFacts
from testbed.planner.primitive.decision.runtime import (
    LEGACY_FSM_DECISION_BACKEND_NAME,
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimeConfig,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_OLD_LEGACY_FSM_BACKEND_ACCESS_POLICY_WRAPPERS = (
    "_legacy_fsm_" + "requested_decision_backend",
    "_legacy_fsm_" + "compatibility_decision_backend",
    "_legacy_fsm_" + "branch_set",
)

_OLD_DECISION_BRIDGE_POLICY_WRAPPERS = (
    "_decide_tick_with_legacy_fsm",
    "_maybe_switch_skill",
)

_OLD_LEGACY_FSM_RUNTIME_ACCESSORS = (
    "legacy_fsm_" + "branch_set",
    "legacy_fsm_" + "backend_factory",
    "legacy_fsm_" + "requested_decision_backend",
    "legacy_fsm_" + "compatibility_decision_backend",
)

_OLD_DECISION_RUNTIME_COMPOSITION_NAMES = (
    "PrimitiveDecisionRuntime" + "Composition",
    "PrimitiveDecisionRuntime" + "CompositionPorts",
)


class _RecordingBranch:
    def __init__(
        self,
        name: str,
        result: PrimitiveDecisionResult | None,
        calls: list[str],
        contexts: list[PrimitiveDecisionContext] | None = None,
    ) -> None:
        self.name = name
        self.result = result
        self.calls = calls
        self.contexts = contexts if contexts is not None else []

    def decide_input(self, decision_input: PrimitiveBackendDecisionInput):
        self.contexts.append(decision_input.context)
        self.calls.append(self.name)
        return self.result

    def decide_tick(self, *, obs, boundary_event, preparation):
        raise AssertionError("runtime backend must pass backend decision input")


class _BackendFacts:
    def __init__(self, common: PrimitiveDecisionFacts) -> None:
        self.common = common


class _RuntimeFactsSource:
    def decision_facts(self, context: PrimitiveDecisionContext) -> PrimitiveDecisionFacts:
        return PrimitiveDecisionFacts.from_context(
            context,
            current_skill_name=str(context.skill_name_before_decision),
            current_switch_reason="",
        )

    def backend_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> _BackendFacts:
        if facts is None:
            facts = self.decision_facts(context)
        return _BackendFacts(facts)


class _RuntimeCompatibilityActions:
    def sync_dig_transition_reason(self, dig_facts: object) -> None:
        raise AssertionError("recording branches must not sync dig reason")

    def refresh_return_transition_state(self, context: PrimitiveDecisionContext) -> None:
        raise AssertionError("recording branches must not refresh return")

    def handle_residual_pre_dig_align(self, context: PrimitiveDecisionContext) -> bool:
        raise AssertionError("recording branches must not handle residual")


class _FakeDecisionBackend:
    def __init__(
        self,
        result: PrimitiveDecisionResult | None,
        calls: list[tuple[str, PrimitiveDecisionContext]],
        name: str,
    ) -> None:
        self._result = result
        self._calls = calls
        self._name = name

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        self._calls.append((self._name, context))
        return self._result

    def decide_tick(self, *, obs, boundary_event, preparation):
        raise AssertionError("runtime must build and pass decision contexts")


class _FakeDecisionBackendFactory:
    def __init__(
        self,
        *,
        requested: PrimitiveDecisionResult,
        compatibility: PrimitiveDecisionResult | None,
        calls: list[tuple[str, PrimitiveDecisionContext]],
    ) -> None:
        self._requested = requested
        self._compatibility = compatibility
        self._calls = calls

    def requested_decision_backend(self) -> _FakeDecisionBackend:
        return _FakeDecisionBackend(self._requested, self._calls, "requested")

    def compatibility_decision_backend(self) -> _FakeDecisionBackend:
        return _FakeDecisionBackend(self._compatibility, self._calls, "compatibility")


def _branch_dependencies() -> dict[str, object]:
    return {
        "facts_source": _RuntimeFactsSource(),
        "compatibility_actions": _RuntimeCompatibilityActions(),
    }


class _ReturnHandoffReadinessService:
    def handoff_ready(self, obs: dict[str, Any]) -> bool:
        return True


def _capability_provider_config() -> PrimitiveFSMCapabilityProviderConfig:
    return PrimitiveFSMCapabilityProviderConfig(
        action_dim=4,
        dig_to_carry_min_distance_to_dig_area_m=0.0,
        dig_to_carry_min_bucket_mass_kg=0.0,
        dig_to_carry_target_bucket_mass_kg=0.0,
        dig_to_carry_mass_plateau_enabled=False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=0.0,
        dig_to_carry_mass_plateau_hold_steps=1,
        dig_to_carry_mass_plateau_min_steps=1,
        dump_ready_min_bucket_mass_kg=0.0,
        dig_bad_replan_enabled=False,
        dig_bad_replan_max_steps=1,
        dig_bad_replan_min_bucket_mass_kg=0.0,
        dig_exit_guard_enabled=False,
        dig_exit_guard_min_steps=1,
        dig_exit_guard_min_bucket_mass_kg=0.0,
        dig_exit_guard_overshoot_m=0.0,
        dump_ready_hold_steps=1,
        dump_ready_min_height_above_rim_m=0.0,
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=False,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="footprint",
        dump_ready_max_dump_area_footprint_outside_distance_m=None,
        dump_ready_min_dump_area_relative_x_m=None,
        dump_ready_max_dump_area_relative_x_m=None,
        dump_ready_min_dump_area_relative_z_m=None,
        dump_ready_max_dump_area_relative_z_m=None,
        dump_ready_near_window_enabled=False,
        dump_ready_near_window_x_tolerance_m=0.0,
        dump_ready_near_window_z_tolerance_m=0.0,
        dump_ready_near_window_outside_tolerance_m=0.0,
        dump_ready_near_window_require_over_footprint=False,
        dump_done_max_bucket_mass_kg=0.0,
        dump_done_min_deposit_delta_kg=0.0,
        dump_done_use_boundary_event=False,
        dump_done_hold_steps=1,
        return_to_dig_start_envelope_direct_handoff_enabled=False,
        return_to_dig_start_envelope_gate_enabled=False,
        return_to_dig_shallow_guard_enabled=False,
        return_to_dig_max_bucket_mass_kg=0.0,
        return_to_dig_touch_tolerance_m=0.0,
        return_to_dig_min_depth_m=0.0,
        return_to_dig_max_depth_m=0.0,
        return_to_dig_max_entry_error_m=None,
    )


def _legacy_factory_ports(**overrides: Any) -> LegacyFSMDecisionBackendFactoryPorts:
    values: dict[str, Any] = {
        "capability_provider_config": _capability_provider_config(),
        "semantic_boundary_profile_active": lambda: False,
        "cycle_state": PrimitiveCycleRuntimeState.fresh(),
        "coverage_state": CoverageRuntimeState(),
        "return_state": PrimitiveReturnRuntimeState.fresh(),
        "return_handoff_readiness_service": _ReturnHandoffReadinessService(),
        "current_skill_name": lambda: "dig",
        "current_switch_reason": lambda: "",
        "should_end_bootstrap": lambda *, obs, boundary_event: False,
        "bootstrap_end_mode": lambda: "first_qualified_dig_start",
        "bootstrap_skill_name": "bootstrap",
        "dig_skill_name": "dig",
        "carry_skill_name": "carry",
        "dump_skill_name": "dump",
        "return_skill_name": "return",
    }
    values.update(overrides)
    return LegacyFSMDecisionBackendFactoryPorts(**values)


def _result(source: str, *, skill: str = "dig") -> PrimitiveDecisionResult:
    return PrimitiveDecisionResult.from_requested_effects(
        decision_source=source,
        status="no_change",
        skill_before=skill,
        skill_after=skill,
        switch_reason="",
        effects=(),
    )


def _branch_set(
    calls: list[str],
    *,
    requested_result: PrimitiveDecisionResult | None = None,
    compatibility_result: PrimitiveDecisionResult | None = None,
    requested_branch: str = "return",
) -> LegacyFSMBranchSet:
    requested_results = {
        "dig": requested_result if requested_branch == "dig" else None,
        "carry": requested_result if requested_branch == "carry" else None,
        "dump": requested_result if requested_branch == "dump" else None,
        "return": requested_result if requested_branch == "return" else None,
    }
    return LegacyFSMBranchSet(
        **_branch_dependencies(),
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch(
            "dig",
            requested_results["dig"] or compatibility_result,
            calls,
        ),
        carry_branch=_RecordingBranch("carry", requested_results["carry"], calls),
        dump_branch=_RecordingBranch("dump", requested_results["dump"], calls),
        return_branch=_RecordingBranch("return", requested_results["return"], calls),
    )


def _runtime(
    branch_set: LegacyFSMBranchSet,
    *,
    backend_name: str = LEGACY_FSM_DECISION_BACKEND_NAME,
) -> PrimitiveDecisionRuntime:
    return PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={
                LEGACY_FSM_DECISION_BACKEND_NAME: (
                    lambda: LegacyFSMDecisionBackendFactory.from_branch_set(
                        branch_set
                    )
                ),
            },
        ),
        config=PrimitiveDecisionRuntimeConfig(backend_name=backend_name),
    )


def _preparation(skill: str = "dig") -> PrimitiveTickPreparation:
    return PrimitiveTickPreparation(
        boundary_event=None,
        skill_name_before_decision=skill,
        dig_progress_updated=skill == "dig",
    )


def _all_code_names(code: CodeType) -> set[str]:
    names = set(code.co_names)
    for const in code.co_consts:
        if isinstance(const, CodeType):
            names.update(_all_code_names(const))
    return names


def _apply_legacy_compatibility_decision(
    planner: PrimitivePlannerACTPolicy,
    *,
    obs: dict[str, Any],
    boundary_event: Any | None,
) -> PrimitiveDecisionResult | None:
    skill_before = str(planner._skill_name)
    result = planner._decision_runtime().decide_legacy_compatibility_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision=skill_before,
            dig_progress_updated=skill_before == "dig",
        ),
    )
    if result is not None and not result.side_effects_applied:
        planner._primitive_requested_effect_runtime().apply(obs, result.effects)
    return result


def test_default_legacy_fsm_runtime_delegates_to_requested_backend() -> None:
    calls: list[str] = []
    expected = _result("return_branch", skill="return")
    runtime = _runtime(_branch_set(calls, requested_result=expected))

    result = runtime.decide_tick(
        obs={},
        boundary_event=None,
        preparation=_preparation("return"),
    )

    assert result is expected
    assert calls == ["bootstrap", "dig", "carry", "dump", "return"]


def test_runtime_decide_tick_builds_one_context_for_requested_backend() -> None:
    calls: list[str] = []
    contexts: list[PrimitiveDecisionContext] = []
    expected = _result("return_branch", skill="return")
    branch_set = LegacyFSMBranchSet(
        **_branch_dependencies(),
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls, contexts),
        dig_branch=_RecordingBranch("dig", None, calls, contexts),
        carry_branch=_RecordingBranch("carry", None, calls, contexts),
        dump_branch=_RecordingBranch("dump", None, calls, contexts),
        return_branch=_RecordingBranch("return", expected, calls, contexts),
    )
    runtime = _runtime(branch_set)
    obs = {"qpos": [1.0]}
    boundary_event = object()
    preparation = PrimitiveTickPreparation(
        boundary_event=boundary_event,
        skill_name_before_decision="return",
        dig_progress_updated=False,
    )

    result = runtime.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=preparation,
    )

    assert result is expected
    assert calls == ["bootstrap", "dig", "carry", "dump", "return"]
    assert len(contexts) == 5
    assert len({id(context) for context in contexts}) == 1
    assert contexts[0].obs is obs
    assert contexts[0].boundary_event is boundary_event
    assert contexts[0].preparation is preparation


def test_runtime_compatibility_path_preserves_legacy_order_and_miss() -> None:
    calls: list[str] = []
    expected = _result("dig", skill="dig")
    runtime = _runtime(_branch_set(calls, compatibility_result=expected))

    result = runtime.decide_legacy_compatibility_tick(
        obs={},
        boundary_event=None,
        preparation=_preparation("dig"),
    )

    assert result is expected
    assert calls == ["bootstrap", "dig"]

    miss_calls: list[str] = []
    miss_runtime = _runtime(_branch_set(miss_calls))
    assert (
        miss_runtime.decide_legacy_compatibility_tick(
            obs={},
            boundary_event=None,
            preparation=_preparation("legacy_skill"),
        )
        is None
    )
    assert miss_calls == ["bootstrap", "dig", "carry", "dump", "return"]


def test_runtime_ports_use_backend_factory_registry_instead_of_legacy_branch_set() -> None:
    field_names = {field.name for field in fields(PrimitiveDecisionRuntimePorts)}

    assert "backend_factories" in field_names
    assert "legacy_fsm_branch_set" not in field_names


def test_runtime_exposes_generic_backend_factory_and_backend_accessors() -> None:
    calls: list[str] = []
    branch_set = _branch_set(calls)
    runtime = _runtime(branch_set)

    factory = runtime.backend_factory_for(LEGACY_FSM_DECISION_BACKEND_NAME)

    assert isinstance(factory, LegacyFSMDecisionBackendFactory)
    assert factory.branch_set() is branch_set
    assert (
        runtime.requested_backend_for(LEGACY_FSM_DECISION_BACKEND_NAME).branch_set
        is branch_set
    )
    assert (
        runtime.compatibility_backend_for(LEGACY_FSM_DECISION_BACKEND_NAME).branch_set
        is branch_set
    )


def test_registered_non_legacy_backend_is_selected_through_generic_registry() -> None:
    calls: list[tuple[str, PrimitiveDecisionContext]] = []
    requested = _result("fake_requested", skill="carry")
    compatibility = _result("fake_compatibility", skill="carry")
    factory = _FakeDecisionBackendFactory(
        requested=requested,
        compatibility=compatibility,
        calls=calls,
    )
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={"fake_external": lambda: factory},
        ),
        config=PrimitiveDecisionRuntimeConfig(backend_name=" fake_external "),
    )
    context = PrimitiveDecisionContext.from_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=_preparation("carry"),
    )

    assert runtime.backend_factory_for("FAKE_EXTERNAL") is factory
    assert runtime.decide_context(context) is requested
    assert runtime.decide_legacy_compatibility_context(context) is compatibility
    assert calls == [
        ("requested", context),
        ("compatibility", context),
    ]


def test_runtime_no_longer_exposes_legacy_fsm_specific_accessors() -> None:
    for accessor_name in _OLD_LEGACY_FSM_RUNTIME_ACCESSORS:
        assert accessor_name not in PrimitiveDecisionRuntime.__dict__


@pytest.mark.parametrize("backend_name", ["behavior_tree", "vlm", "unknown"])
def test_unsupported_backend_fails_fast_without_building_legacy_fsm(
    backend_name: str,
) -> None:
    def unexpected_backend_factory() -> LegacyFSMDecisionBackendFactory:
        raise AssertionError("unsupported backend must not build legacy factory")

    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={
                LEGACY_FSM_DECISION_BACKEND_NAME: unexpected_backend_factory,
            },
        ),
        config=PrimitiveDecisionRuntimeConfig(backend_name=backend_name),
    )

    with pytest.raises(PrimitiveDecisionContractError) as exc_info:
        runtime.decide_tick(
            obs={},
            boundary_event=None,
            preparation=_preparation("dig"),
        )

    message = str(exc_info.value)
    assert f"unsupported primitive decision backend {backend_name!r}" in message
    assert LEGACY_FSM_DECISION_BACKEND_NAME in message


def test_policy_execution_runtime_ports_use_generic_decision_runtime_path() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    decision_runtime = object()
    requested_effect_runtime = object()

    planner._primitive_execution_runtime_state = MethodType(
        lambda self: object(),
        planner,
    )
    planner._primitive_boundary_event_runtime_service = MethodType(
        lambda self: object(),
        planner,
    )
    planner._primitive_dig_progress_runtime_service = MethodType(
        lambda self: object(),
        planner,
    )
    planner._decision_runtime = MethodType(lambda self: decision_runtime, planner)
    planner._primitive_requested_effect_runtime = MethodType(
        lambda self: requested_effect_runtime,
        planner,
    )
    planner._primitive_tick_finalization_runtime = MethodType(
        lambda self: object(),
        planner,
    )
    planner._action_dispatch_service = MethodType(lambda self: object(), planner)

    ports = planner._primitive_execution_runtime_ports()

    assert ports.decision_runtime is decision_runtime
    assert ports.requested_effect_applier is requested_effect_runtime


def test_decision_runtime_ports_expose_backend_factory_registry() -> None:
    sentinel = object()

    ports = PrimitiveDecisionRuntimePorts(
        backend_factories={
            LEGACY_FSM_DECISION_BACKEND_NAME: lambda: sentinel,
        }
    )

    assert LEGACY_FSM_DECISION_BACKEND_NAME in ports.backend_factories
    assert ports.backend_factories[LEGACY_FSM_DECISION_BACKEND_NAME]() is sentinel
    assert not hasattr(ports, "legacy_fsm_branch_set")


def test_legacy_fsm_backend_factory_runtime_ports_build_legacy_registry() -> None:
    factory = LegacyFSMDecisionBackendFactory.from_runtime_ports(
        _legacy_factory_ports()
    )
    assert isinstance(factory, LegacyFSMDecisionBackendFactory)
    branch_set = factory.branch_set()

    assert isinstance(branch_set.facts_source, PrimitiveBackendFactsSource)
    assert branch_set.bootstrap_branch.config.bootstrap_skill_name == "bootstrap"
    assert branch_set.dig_branch.config.dig_skill_name == "dig"
    assert branch_set.carry_branch.config.carry_skill_name == "carry"
    assert branch_set.dump_branch.config.dump_skill_name == "dump"
    assert branch_set.return_branch.config.return_skill_name == "return"


def test_policy_decision_runtime_weld_delegates_composition_boundary() -> None:
    names = _all_code_names(PrimitivePlannerACTPolicy._decision_runtime.__code__)

    for old_name in _OLD_DECISION_RUNTIME_COMPOSITION_NAMES:
        assert old_name not in names
    assert "LegacyFSMDecisionBackendFactory" in names
    assert "LegacyFSMDecisionBackendFactoryPorts" in names
    assert "PrimitiveDecisionRuntimePorts" in names
    assert "PrimitiveFSMCapabilityProviderPorts" not in names
    assert "PrimitiveDecisionCapabilities" not in names
    assert "LegacyFSMBranchPorts" not in names


def test_policy_requested_bridge_and_legacy_compatibility_use_decision_runtime() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"qpos": [1.0]}
    boundary_event = object()
    preparation = _preparation("dig")
    requested = _result("requested")
    compat = _result("compat")
    calls: list[Any] = []

    class _FakeRuntime:
        def decide_tick(self, *, obs, boundary_event, preparation):
            calls.append(("requested", obs, boundary_event, preparation))
            return requested

        def decide_legacy_compatibility_tick(
            self,
            *,
            obs,
            boundary_event,
            preparation,
        ):
            calls.append(("compat", obs, boundary_event, preparation))
            return compat

    planner._decision_runtime = MethodType(lambda self: _FakeRuntime(), planner)

    assert (
        planner._decision_runtime().decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )
        is requested
    )
    planner._skill_name = "dig"

    class _FakeApplier:
        def apply(self, got_obs, effects):
            calls.append(("apply", got_obs, effects))

    planner._primitive_requested_effect_runtime = MethodType(
        lambda self: _FakeApplier(),
        planner,
    )
    assert (
        _apply_legacy_compatibility_decision(
            planner,
            obs=obs,
            boundary_event=boundary_event,
        )
        is compat
    )

    assert calls == [
        ("requested", obs, boundary_event, preparation),
        (
            "compat",
            obs,
            boundary_event,
            PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision="dig",
                dig_progress_updated=True,
            ),
        ),
        ("apply", obs, ()),
    ]


def test_policy_no_longer_exposes_legacy_fsm_backend_access_wrappers() -> None:
    for wrapper_name in _OLD_LEGACY_FSM_BACKEND_ACCESS_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__


def test_policy_no_longer_exposes_legacy_decision_bridge_wrappers() -> None:
    for wrapper_name in _OLD_DECISION_BRIDGE_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__
