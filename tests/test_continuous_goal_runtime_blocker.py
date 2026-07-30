from __future__ import annotations

from types import SimpleNamespace

import pytest

from testbed.planner.primitive.coverage.selection_runtime import (
    PrimitiveCoverageSelectionRuntime,
    PrimitiveCoverageSelectionRuntimePorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallSafetyConfig,
    CoverageWallSafetyPrePolicyGuard,
    CoverageWallSafetyPrePolicyGuardPorts,
    NoWallSafeCorridorError,
)


def test_missing_continuous_qpos_predictor_blocks_before_legacy_goal_building() -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("legacy coverage/exemplar path must not run")

    runtime = PrimitiveCoverageSelectionRuntime(
        PrimitiveCoverageSelectionRuntimePorts(
            state=CoverageRuntimeState(),
            static_config=SimpleNamespace(
                dig_cut_planner_mode="continuous_goal_conditioned",
                execution_library=SimpleNamespace(enabled=False),
            ),
            cycle_index=lambda: 0,
            observation_facts=forbidden,
            maybe_reopen_pass=lambda _obs, _reason: False,
            request_terminal_stop=lambda _reason: None,
            record_decision_event=lambda name, **fields: events.append(
                (name, fields)
            ),
        )
    )

    with pytest.raises(
        NoWallSafeCorridorError,
        match="continuous_goal_3d_predictor_missing",
    ):
        runtime.select_next_coverage_plan({}, update_state=True)

    assert events[-1][0] == "continuous_goal_3d_predictor_missing"
    assert runtime.ports.state.coverage_active_execution_contract is None


def test_missing_predictor_returns_terminal_zero_before_act_inference() -> None:
    act_calls: list[str] = []
    terminal_reasons: list[str] = []

    def ensure_plan(_obs: dict[str, object]) -> None:
        raise NoWallSafeCorridorError(
            reason="continuous_goal_3d_predictor_missing"
        )

    guard = CoverageWallSafetyPrePolicyGuard(
        CoverageWallSafetyPrePolicyGuardPorts(
            config=CoverageWallSafetyConfig(enabled=True),
            current_skill_name=lambda: "dig",
            ensure_dig_plan=ensure_plan,
            ensure_return_plan=ensure_plan,
            terminal_neutral_action=lambda _obs, reason: (
                terminal_reasons.append(reason)
                or [0.0, 0.0, 0.0, 0.0]
            ),
        )
    )
    action = guard.apply({})
    if action is None:
        act_calls.append("ACT")

    assert action == [0.0, 0.0, 0.0, 0.0]
    assert act_calls == []
    assert terminal_reasons == ["continuous_goal_3d_predictor_missing"]


def test_continuous_mode_never_falls_through_to_legacy_coverage_synthesis() -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("legacy coverage/exemplar path must not run")

    runtime = PrimitiveCoverageSelectionRuntime(
        PrimitiveCoverageSelectionRuntimePorts(
            state=CoverageRuntimeState(),
            static_config=SimpleNamespace(
                dig_cut_planner_mode="continuous_goal_conditioned",
                execution_library=SimpleNamespace(enabled=False),
            ),
            cycle_index=lambda: 0,
            observation_facts=forbidden,
            maybe_reopen_pass=lambda _obs, _reason: False,
            request_terminal_stop=lambda _reason: None,
            record_decision_event=lambda *_args, **_kwargs: None,
            continuous_goal_qpos_sweep_predictor=SimpleNamespace(),
        )
    )

    with pytest.raises(
        NoWallSafeCorridorError,
        match="continuous_goal_contract_invalid",
    ):
        runtime.select_next_coverage_plan({}, update_state=True)
