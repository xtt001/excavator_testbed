from __future__ import annotations

from types import MethodType

import numpy as np
import pytest

from testbed.planner.box_emptying.safety_interlock import SafetyActionDecision
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.return_approach_control import (
    RETURN_APPROACH_AXIS_LIMIT_LINEAGE_DRIFT_REASON,
    RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON,
    ReturnApproachAxisLimitConfig,
    ReturnApproachAxisLimitService,
    build_return_approach_axis_limit_log_fields,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _config(**overrides: object) -> ReturnApproachAxisLimitConfig:
    values: dict[str, object] = {
        "enabled": True,
        "diagnostic_only": True,
        "action_dim": 4,
        "axis_index": 1,
        "min_completed_dump_count": 7,
        "required_cell_id": None,
        "lineage_warmup_ticks": 0,
        "activation_margin": 0.020,
        "target_margin": 0.016,
        "activation_velocity_min": 0.0,
        "kp": 4.0,
        "kd": 2.0,
        "action_sign": -1.0,
        "action_clip": 0.35,
    }
    values.update(overrides)
    return ReturnApproachAxisLimitConfig(**values)


def _checks(*, upper: float = 0.6481370115280152) -> dict[str, object]:
    return {
        "qpos_1": {
            "value": 0.6395,
            "min": 0.39158900737762453,
            "max": upper,
            "ok": True,
            "error": 0.0,
        }
    }


def _decision(
    service: ReturnApproachAxisLimitService,
    *,
    qpos_1: float = 0.6395,
    qvel_1: float = 0.208,
    proposed_axis_1: float = -0.548,
    skill_name: str = "return",
    completed_dump_count: int = 7,
    goal_cell_id: int = 0,
    checks: dict[str, object] | None = None,
):
    return service.shape_action(
        {
            "step_id": 3551,
            "qpos": [0.55, qpos_1, 0.34, 0.21],
            "qvel": [0.0, qvel_1, 0.0, 0.0],
        },
        np.asarray([0.1, proposed_axis_1, -0.36, 0.06], dtype=np.float32),
        skill_name=skill_name,
        completed_dump_count=completed_dump_count,
        goal_cell_id=goal_cell_id,
        envelope_checks=_checks() if checks is None else checks,
    )


def test_enabled_axis_limit_is_explicitly_diagnostic_only() -> None:
    with pytest.raises(ValueError, match="diagnostic_only=true"):
        ReturnApproachAxisLimitConfig(enabled=True, diagnostic_only=False)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"axis_index": 4}, "axis_index"),
        ({"activation_margin": 0.004, "target_margin": 0.005}, "target_margin"),
        ({"action_sign": 0.0}, "action_sign"),
        ({"min_completed_dump_count": -1}, "min_completed_dump_count"),
    ],
)
def test_axis_limit_config_rejects_invalid_control_contract(
    overrides: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _config(**overrides)


def test_axis_limit_is_passthrough_outside_the_locked_diagnostic_context() -> None:
    service = ReturnApproachAxisLimitService(_config(required_cell_id=0))

    before_dump_seven = _decision(service, completed_dump_count=6)
    wrong_skill = _decision(service, skill_name="dig")
    wrong_cell = _decision(service, goal_cell_id=1)

    expected = [0.1, -0.548, -0.36, 0.06]
    assert before_dump_seven.action.tolist() == pytest.approx(expected)
    assert wrong_skill.action.tolist() == pytest.approx(expected)
    assert wrong_cell.action.tolist() == pytest.approx(expected)
    assert before_dump_seven.active is False
    assert wrong_skill.active is False
    assert wrong_cell.active is False
    assert service.debug_fields()["return_approach_axis_limit_intervention_count"] == 0


def test_axis_limit_brakes_only_boom_and_does_not_relax_handoff_bound() -> None:
    service = ReturnApproachAxisLimitService(_config())

    decision = _decision(service)

    assert decision.active is True
    assert decision.terminal_reason == ""
    assert decision.axis_upper_bound == pytest.approx(0.6481370115280152)
    assert decision.target_qpos == pytest.approx(0.6321370115280152)
    assert decision.action.tolist() == pytest.approx([0.1, 0.35, -0.36, 0.06])
    fields = service.debug_fields()
    assert fields["return_approach_axis_limit_latched"] is True
    assert fields["return_approach_axis_limit_first_intervention_step_id"] == 3551
    assert fields["return_approach_axis_limit_intervention_count"] == 1
    assert fields["return_approach_axis_limit_axis_upper_bound"] == pytest.approx(
        0.6481370115280152
    )
    assert fields["return_approach_axis_limit_target_qpos"] < fields[
        "return_approach_axis_limit_axis_upper_bound"
    ]


def test_axis_limit_can_lock_the_current_supported_cell_without_cell0_snap() -> None:
    service = ReturnApproachAxisLimitService(_config(required_cell_id=None))

    decision = _decision(
        service,
        goal_cell_id=4,
        qpos_1=0.615,
        qvel_1=0.2,
        checks=_checks(upper=0.6276280069351197),
    )

    assert decision.active is True
    assert decision.axis_upper_bound == pytest.approx(0.6276280069351197)
    assert decision.target_qpos == pytest.approx(0.6116280069351197)
    fields = service.debug_fields()
    assert fields["return_approach_axis_limit_required_cell_id"] == -1
    assert fields["return_approach_axis_limit_locked_cell_id"] == 4


def test_axis_limit_stays_latched_until_return_exits() -> None:
    service = ReturnApproachAxisLimitService(_config())
    first = _decision(service)
    latched = _decision(service, qpos_1=0.62, qvel_1=-0.01)
    exited = _decision(service, skill_name="dig")
    reentered_below_activation = _decision(
        service,
        qpos_1=0.62,
        qvel_1=0.2,
    )

    assert first.active is True
    assert latched.active is True
    assert exited.active is False
    assert reentered_below_activation.active is False


def test_axis_limit_warmup_ignores_the_previous_skill_envelope_snapshot() -> None:
    service = ReturnApproachAxisLimitService(
        _config(lineage_warmup_ticks=1)
    )

    stale = _decision(
        service,
        qpos_1=0.2395,
        qvel_1=0.02,
        checks=_checks(upper=0.6223429822921753),
    )
    current = _decision(
        service,
        qpos_1=0.6395,
        qvel_1=0.208,
        checks=_checks(),
    )

    assert stale.active is False
    assert stale.terminal_reason == ""
    assert current.active is True
    assert current.axis_upper_bound == pytest.approx(0.6481370115280152)


def test_axis_limit_fails_closed_on_missing_or_nonfinite_lineage() -> None:
    service = ReturnApproachAxisLimitService(_config())

    missing = _decision(service, checks={})
    nonfinite = _decision(
        service,
        checks={
            "qpos_1": {
                "min": 0.39,
                "max": float("nan"),
            }
        },
    )

    assert missing.terminal_reason == RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON
    assert nonfinite.terminal_reason == RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON
    assert missing.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert nonfinite.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_axis_limit_fails_closed_if_locked_upper_bound_drifts() -> None:
    service = ReturnApproachAxisLimitService(_config())
    first = _decision(service)
    drift = _decision(service, checks=_checks(upper=0.6581370115280152))

    assert first.active is True
    assert drift.active is False
    assert drift.terminal_reason == RETURN_APPROACH_AXIS_LIMIT_LINEAGE_DRIFT_REASON
    assert drift.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_axis_limit_reset_clears_latch_and_diagnostic_counters() -> None:
    service = ReturnApproachAxisLimitService(_config())
    assert _decision(service).active is True

    service.reset()

    fields = service.debug_fields()
    assert fields["return_approach_axis_limit_latched"] is False
    assert fields["return_approach_axis_limit_intervention_count"] == 0
    assert fields["return_approach_axis_limit_first_intervention_step_id"] == -1


def test_planner_wires_axis_limit_before_the_existing_safety_interlock() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 4
    planner._skill_name = "return"
    planner.return_approach_axis_limit_enabled = True
    planner.box_emptying_cfg = {
        "return_approach_axis_limit": {
            "enabled": True,
            "diagnostic_only": True,
            "axis_index": 1,
            "required_cell_id": None,
            "min_completed_dump_count": 7,
            "lineage_warmup_ticks": 0,
            "activation_margin": 0.020,
            "target_margin": 0.016,
            "kp": 4.0,
            "kd": 2.0,
            "action_sign": -1.0,
            "action_clip": 0.35,
        }
    }
    coverage_state = CoverageRuntimeState()
    coverage_state.coverage_completed_dump_count = 7
    coverage_state.set_coverage_corridors(
        [
            CoverageCorridorState(
                corridor_id=9,
                cell_id=0,
                entry_x_m=0.1,
                entry_z_m=0.2,
                exit_x_m=0.3,
                exit_z_m=0.4,
            )
        ]
    )
    coverage_state.set_active_corridor_id(9)
    requested: list[dict[str, object]] = []
    filtered_actions: list[np.ndarray] = []

    class _CycleState:
        cycle_index = 6
        dig_step_count = 0
        transition_timeout_count = 0

    class _ReturnState:
        return_to_dig_start_envelope_checks = _checks()

    class _Interlock:
        def request_neutral_event(self, **kwargs: object) -> None:
            requested.append(dict(kwargs))

        def filter_action(
            self,
            obs: dict[str, object],
            proposed_action: np.ndarray,
            **kwargs: object,
        ) -> SafetyActionDecision:
            del obs, kwargs
            filtered_actions.append(proposed_action.copy())
            return SafetyActionDecision(action=proposed_action.copy())

    interlock = _Interlock()
    planner._box_safety_interlock = MethodType(
        lambda self: interlock,
        planner,
    )
    planner._box_emptying_runtime_monitor = MethodType(
        lambda self: None,
        planner,
    )
    planner._primitive_cycle_runtime_state = MethodType(
        lambda self: _CycleState(),
        planner,
    )
    planner._primitive_return_runtime_state = MethodType(
        lambda self: _ReturnState(),
        planner,
    )
    planner._coverage_runtime_state = MethodType(
        lambda self: coverage_state,
        planner,
    )
    planner._box_safety_active_cell_id = MethodType(
        lambda self, obs, active_corridor_id: 4,
        planner,
    )
    planner._apply_box_safety_decision = MethodType(
        lambda self, decision: None,
        planner,
    )

    action = planner._box_safety_filter_action(
        {
            "step_id": 3551,
            "qpos": [0.55, 0.6395, 0.34, 0.21],
            "qvel": [0.0, 0.208, 0.0, 0.0],
            "env_state": np.zeros(107, dtype=np.float32),
        },
        np.asarray([0.1, -0.548, -0.36, 0.06], dtype=np.float32),
    )

    assert requested == []
    assert action.tolist() == pytest.approx([0.1, 0.35, -0.36, 0.06])
    assert filtered_actions[-1].tolist() == pytest.approx(
        [0.1, 0.35, -0.36, 0.06]
    )
    assert (
        planner._return_approach_axis_limit()
        .debug_fields()["return_approach_axis_limit_intervention_count"]
        == 1
    )
    assert (
        planner._return_approach_axis_limit()
        .debug_fields()["return_approach_axis_limit_locked_cell_id"]
        == 0
    )


def test_axis_limit_recorder_fields_preserve_intervention_evidence() -> None:
    service = ReturnApproachAxisLimitService(_config())
    assert _decision(service).active is True

    fields = build_return_approach_axis_limit_log_fields(
        service.debug_fields()
    )

    assert fields["return_approach_axis_limit_enabled"] is True
    assert fields["return_approach_axis_limit_required_cell_id"] == -1
    assert fields["return_approach_axis_limit_locked_cell_id"] == 0
    assert fields["return_approach_axis_limit_intervention_count"] == 1
    assert fields[
        "return_approach_axis_limit_first_intervention_step_id"
    ] == 3551
    assert fields["return_approach_axis_limit_shaped_axis_action"] == pytest.approx(
        0.35
    )


def test_planner_terminalizes_missing_axis_lineage_before_action_progresses() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 4
    planner._skill_name = "return"
    planner.return_approach_axis_limit_enabled = True
    planner.box_emptying_cfg = {
        "return_approach_axis_limit": {
            "enabled": True,
            "diagnostic_only": True,
            "required_cell_id": 0,
            "lineage_warmup_ticks": 0,
        }
    }
    coverage_state = CoverageRuntimeState()
    coverage_state.coverage_completed_dump_count = 7
    requested: list[dict[str, object]] = []

    class _CycleState:
        cycle_index = 6
        dig_step_count = 0
        transition_timeout_count = 0

    class _ReturnState:
        return_to_dig_start_envelope_checks: dict[str, object] = {}

    class _Interlock:
        pending_reason = ""

        def request_neutral_event(self, **kwargs: object) -> None:
            requested.append(dict(kwargs))
            self.pending_reason = str(kwargs["reason"])

        def filter_action(
            self,
            obs: dict[str, object],
            proposed_action: np.ndarray,
            **kwargs: object,
        ) -> SafetyActionDecision:
            del obs, kwargs
            return SafetyActionDecision(
                action=np.zeros_like(proposed_action),
                reason=self.pending_reason,
                awaiting_neutral_ack=True,
            )

    interlock = _Interlock()
    planner._box_safety_interlock = MethodType(
        lambda self: interlock,
        planner,
    )
    planner._box_emptying_runtime_monitor = MethodType(
        lambda self: None,
        planner,
    )
    planner._primitive_cycle_runtime_state = MethodType(
        lambda self: _CycleState(),
        planner,
    )
    planner._primitive_return_runtime_state = MethodType(
        lambda self: _ReturnState(),
        planner,
    )
    planner._coverage_runtime_state = MethodType(
        lambda self: coverage_state,
        planner,
    )
    planner._box_safety_active_cell_id = MethodType(
        lambda self, obs, active_corridor_id: 0,
        planner,
    )
    planner._apply_box_safety_decision = MethodType(
        lambda self, decision: None,
        planner,
    )

    action = planner._box_safety_filter_action(
        {
            "step_id": 3551,
            "qpos": [0.55, 0.6395, 0.34, 0.21],
            "qvel": [0.0, 0.208, 0.0, 0.0],
            "env_state": np.zeros(107, dtype=np.float32),
        },
        np.asarray([0.1, -0.548, -0.36, 0.06], dtype=np.float32),
    )

    assert action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert requested == [
        {
            "step_id": 3551,
            "reason": RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON,
            "terminal": True,
        }
    ]
