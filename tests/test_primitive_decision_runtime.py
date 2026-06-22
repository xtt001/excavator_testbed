from __future__ import annotations

from dataclasses import fields
from types import MethodType
from typing import Any

import pytest

from testbed.planner.primitive_backend import (
    LegacyFSMBranchSet,
    LegacyFSMDecisionBackendFactory,
)
from testbed.planner.primitive_backend_input import PrimitiveBackendDecisionInput
from testbed.planner.primitive_decision import (
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import PrimitiveDecisionFacts
from testbed.planner.primitive_decision_runtime import (
    LEGACY_FSM_DECISION_BACKEND_NAME,
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimeConfig,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


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


def _branch_dependencies() -> dict[str, object]:
    return {
        "facts_source": _RuntimeFactsSource(),
        "compatibility_actions": _RuntimeCompatibilityActions(),
    }


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
        residual_branch=_RecordingBranch("residual", compatibility_result, calls),
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
        residual_branch=_RecordingBranch("residual", None, calls, contexts),
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
    expected = _result("residual", skill="pre_dig_align")
    runtime = _runtime(_branch_set(calls, compatibility_result=expected))

    result = runtime.decide_legacy_compatibility_tick(
        obs={},
        boundary_event=None,
        preparation=_preparation("pre_dig_align"),
    )

    assert result is expected
    assert calls == ["bootstrap", "residual"]

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
    assert miss_calls == ["bootstrap", "residual", "dig", "carry", "dump", "return"]


def test_runtime_ports_use_backend_factory_registry_instead_of_legacy_branch_set() -> None:
    field_names = {field.name for field in fields(PrimitiveDecisionRuntimePorts)}

    assert "backend_factories" in field_names
    assert "legacy_fsm_branch_set" not in field_names


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


def test_policy_execution_driver_ports_use_generic_decision_runtime_path() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)

    ports = planner._execution_driver_ports()

    assert ports.decide_tick.__self__ is planner
    assert ports.decide_tick.__name__ == "_decide_tick"


def test_policy_decision_runtime_ports_expose_backend_factory_registry() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    sentinel = object()
    planner._legacy_fsm_backend_factory = MethodType(lambda self: sentinel, planner)

    ports = planner._decision_runtime_ports()

    assert LEGACY_FSM_DECISION_BACKEND_NAME in ports.backend_factories
    assert ports.backend_factories[LEGACY_FSM_DECISION_BACKEND_NAME]() is sentinel
    assert not hasattr(ports, "legacy_fsm_branch_set")


def test_policy_decision_wrappers_delegate_to_same_runtime() -> None:
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

        def legacy_fsm_requested_decision_backend(self) -> str:
            calls.append("requested_backend")
            return "requested_backend"

        def legacy_fsm_compatibility_decision_backend(self) -> str:
            calls.append("compat_backend")
            return "compat_backend"

        def legacy_fsm_branch_set(self) -> str:
            calls.append("branch_set")
            return "branch_set"

    planner._decision_runtime = MethodType(lambda self: _FakeRuntime(), planner)

    assert (
        planner._decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )
        is requested
    )
    assert (
        planner._decide_tick_with_legacy_fsm(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )
        is requested
    )
    assert (
        planner._legacy_fsm_requested_decision_backend()
        == "requested_backend"
    )
    assert (
        planner._legacy_fsm_compatibility_decision_backend()
        == "compat_backend"
    )
    assert planner._legacy_fsm_branch_set() == "branch_set"

    planner._skill_name = "dig"
    planner._apply_requested_tick_effects = MethodType(
        lambda self, got_obs, effects: calls.append(("apply", got_obs, effects)),
        planner,
    )
    planner._maybe_switch_skill(obs=obs, boundary_event=boundary_event)

    assert calls == [
        ("requested", obs, boundary_event, preparation),
        ("requested", obs, boundary_event, preparation),
        "requested_backend",
        "compat_backend",
        "branch_set",
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
