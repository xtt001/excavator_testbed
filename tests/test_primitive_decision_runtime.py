from __future__ import annotations

from types import MethodType
from typing import Any

import pytest

from testbed.planner.primitive_backend import LegacyFSMBranchSet
from testbed.planner.primitive_decision import (
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)
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
    ) -> None:
        self.name = name
        self.result = result
        self.calls = calls

    def decide_tick(self, *, obs, boundary_event, preparation):
        self.calls.append(self.name)
        return self.result


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
            legacy_fsm_branch_set=lambda: branch_set,
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


@pytest.mark.parametrize("backend_name", ["behavior_tree", "vlm", "unknown"])
def test_unsupported_backend_fails_fast_without_building_legacy_fsm(
    backend_name: str,
) -> None:
    def unexpected_branch_set() -> LegacyFSMBranchSet:
        raise AssertionError("unsupported backend must not build legacy branches")

    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            legacy_fsm_branch_set=unexpected_branch_set,
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
