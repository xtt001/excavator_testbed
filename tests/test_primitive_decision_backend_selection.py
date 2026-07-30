from __future__ import annotations

import pytest

from testbed.planner.primitive.decision.backends.behavior_tree import (
    BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE,
    BEHAVIOR_TREE_DECISION_BACKEND_NAME,
)
from testbed.planner.primitive.decision.backends.legacy_fsm import (
    LegacyFSMDecisionBackendFactory,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.decision.contracts import (
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)
from testbed.planner.primitive.decision.runtime import (
    LEGACY_FSM_DECISION_BACKEND_NAME,
    PRODUCTION_DECISION_BACKEND_NAMES,
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimeConfig,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation


class _RecordingBackend:
    def __init__(
        self,
        *,
        result: PrimitiveDecisionResult | None,
        calls: list[tuple[str, str]],
        role: str,
    ) -> None:
        self._result = result
        self._calls = calls
        self._role = role

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        self._calls.append((self._role, str(context.skill_name_before_decision)))
        return self._result


class _RecordingBackendFactory:
    def __init__(
        self,
        *,
        requested: PrimitiveDecisionResult,
        compatibility: PrimitiveDecisionResult | None,
        calls: list[tuple[str, str]],
    ) -> None:
        self._requested = requested
        self._compatibility = compatibility
        self._calls = calls

    def requested_decision_backend(self) -> _RecordingBackend:
        return _RecordingBackend(
            result=self._requested,
            calls=self._calls,
            role="requested",
        )

    def compatibility_decision_backend(self) -> _RecordingBackend:
        return _RecordingBackend(
            result=self._compatibility,
            calls=self._calls,
            role="compatibility",
        )


def _result(source: str, *, skill: str = "dig") -> PrimitiveDecisionResult:
    return PrimitiveDecisionResult.from_requested_effects(
        decision_source=source,
        status="no_change",
        skill_before=skill,
        skill_after=skill,
        switch_reason="",
        effects=(),
    )


def _context(skill: str = "dig") -> PrimitiveDecisionContext:
    return PrimitiveDecisionContext.from_tick(
        obs={"qpos": [1.0]},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision=skill,
            dig_progress_updated=skill == "dig",
        ),
    )


def test_default_runtime_config_selects_legacy_fsm() -> None:
    assert PrimitiveDecisionRuntimeConfig().backend_name == (
        LEGACY_FSM_DECISION_BACKEND_NAME
    )


def test_production_backend_names_are_legacy_only() -> None:
    assert PRODUCTION_DECISION_BACKEND_NAMES == (LEGACY_FSM_DECISION_BACKEND_NAME,)
    assert BEHAVIOR_TREE_DECISION_BACKEND_NAME not in PRODUCTION_DECISION_BACKEND_NAMES


def test_behavior_tree_shadow_selection_requires_explicit_registered_factory() -> None:
    calls: list[tuple[str, str]] = []
    requested = _result(
        BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE,
        skill="return",
    )
    factory = _RecordingBackendFactory(
        requested=requested,
        compatibility=None,
        calls=calls,
    )
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={BEHAVIOR_TREE_DECISION_BACKEND_NAME: lambda: factory}
        ),
        config=PrimitiveDecisionRuntimeConfig(
            backend_name=f" {BEHAVIOR_TREE_DECISION_BACKEND_NAME.upper()} "
        ),
    )

    result = runtime.decide_context(_context("return"))

    assert result is requested
    assert calls == [("requested", "return")]


def test_missing_behavior_tree_shadow_factory_fails_without_legacy_fallback() -> None:
    legacy_factory_built = False

    def unexpected_legacy_factory() -> LegacyFSMDecisionBackendFactory:
        nonlocal legacy_factory_built
        legacy_factory_built = True
        raise AssertionError("missing shadow factory must not build legacy backend")

    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={
                LEGACY_FSM_DECISION_BACKEND_NAME: unexpected_legacy_factory
            }
        ),
        config=PrimitiveDecisionRuntimeConfig(
            backend_name=f" {BEHAVIOR_TREE_DECISION_BACKEND_NAME.upper()} "
        ),
    )

    with pytest.raises(PrimitiveDecisionContractError) as exc_info:
        runtime.decide_context(_context("dig"))

    message = str(exc_info.value)
    assert BEHAVIOR_TREE_DECISION_BACKEND_NAME in message
    assert LEGACY_FSM_DECISION_BACKEND_NAME in message
    assert legacy_factory_built is False


def test_unsupported_backend_error_lists_requested_and_registered_names() -> None:
    calls: list[tuple[str, str]] = []
    factory = _RecordingBackendFactory(
        requested=_result("external_requested"),
        compatibility=None,
        calls=calls,
    )
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={
                "external_shadow": lambda: factory,
                LEGACY_FSM_DECISION_BACKEND_NAME: lambda: factory,
            }
        ),
        config=PrimitiveDecisionRuntimeConfig(backend_name="missing_shadow"),
    )

    with pytest.raises(PrimitiveDecisionContractError) as exc_info:
        runtime.decide_context(_context("dig"))

    message = str(exc_info.value)
    assert "missing_shadow" in message
    assert "external_shadow" in message
    assert LEGACY_FSM_DECISION_BACKEND_NAME in message
    assert calls == []


def test_backend_names_are_normalized_for_registered_factories() -> None:
    calls: list[tuple[str, str]] = []
    requested = _result("external_requested", skill="carry")
    factory = _RecordingBackendFactory(
        requested=requested,
        compatibility=None,
        calls=calls,
    )
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={" External_Shadow ": lambda: factory}
        ),
        config=PrimitiveDecisionRuntimeConfig(backend_name=" EXTERNAL_SHADOW "),
    )

    assert runtime.backend_factory_for(" external_shadow ") is factory
    assert runtime.decide_context(_context("carry")) is requested
    assert calls == [("requested", "carry")]
