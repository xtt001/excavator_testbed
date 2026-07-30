from __future__ import annotations

import json

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
    SafetyInterlockConfig,
)


def _obs(
    *,
    step_id: int,
    payload_kg: float = 0.0,
    wall_mask: float = 0.0,
    wall_force_n: float = 0.0,
    wall_sessions: int = 0,
    bottom_mask: float = 0.0,
    bottom_sessions: int = 0,
    plane_depth_m: float = 0.0,
    hard_bottom_depth_m: float = 0.60,
    qpos: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0),
    qvel: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0),
    bucket_tip: tuple[float, ...] = (0.0, 0.0, 0.0),
) -> dict[str, object]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[0] = payload_kg
    env[8] = plane_depth_m
    env[89] = hard_bottom_depth_m
    env[90] = 1600.0
    env[91:97] = 0.2
    env[97] = 1920.0
    env[98] = 1920.0
    env[99] = 1.0
    env[100] = 1.0
    env[101] = wall_mask
    env[102] = wall_force_n
    env[103] = wall_sessions
    env[104] = bottom_mask
    env[106] = bottom_sessions
    env[28:31] = bucket_tip
    warnings: list[str] = []
    if wall_mask >= 0.5:
        wall_name = "Dig_XMin_Board"
        warning = {
            "schema": "worktool_wall_contact_detail_v1",
            "step_id": step_id,
            "sim_time_s": step_id * 0.05,
            "delta_time_s": 0.05,
            "session_id": wall_sessions,
            "session_count": wall_sessions,
            "consecutive_contact_steps": 1,
            "session_duration_s": 0.05,
            "session_normal_impulse_n_s": max(0.0, wall_force_n * 0.05),
            "parts": ["bucket"],
            "walls": [wall_name],
            "pairs": [
                {
                    "component": "bucket",
                    "machine_shape_path": "Machine/bucket/shape",
                    "wall_name": wall_name,
                    "wall_shape_path": f"DigArea/{wall_name}/shape",
                    "callback_count": 1,
                    "contact_point_count": 1,
                    "max_normal_force_n": wall_force_n,
                    "max_tangential_force_n": 0.0,
                    "max_total_force_n": wall_force_n,
                    "contact_points_world_m": [[0.0, 0.0, 0.0]],
                    "representative_contact_point_component_local_m": [],
                    "tangential_displacement_m": 0.0,
                }
            ],
        }
        warnings.append(
            "worktool_wall_contact_detail_v1:"
            + json.dumps(warning, separators=(",", ":"))
        )
    return {
        "step_id": step_id,
        "env_state": env,
        "qpos": np.asarray(qpos, dtype=np.float32),
        "qvel": np.asarray(qvel, dtype=np.float32),
        "warnings": warnings,
    }


def test_first_wall_contact_neutralizes_then_releases_recovery_after_ack() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    proposed = np.full(4, 0.2, dtype=np.float32)

    contact = interlock.filter_action(
        _obs(step_id=10, wall_mask=1.0, wall_sessions=1),
        proposed,
        active_cell_id=3,
        active_corridor_id=12,
    )
    assert contact.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert contact.reason == "wall_contact_first_session"
    assert contact.awaiting_neutral_ack is True
    assert contact.terminal is False

    duplicate_step = interlock.filter_action(
        _obs(step_id=10, wall_mask=1.0, wall_sessions=1),
        proposed,
        active_cell_id=3,
        active_corridor_id=12,
    )
    assert duplicate_step.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert duplicate_step.awaiting_neutral_ack is True
    assert duplicate_step.replan is False

    acknowledged = interlock.filter_action(
        _obs(step_id=11, wall_mask=0.0, wall_sessions=1),
        proposed,
        active_cell_id=3,
        active_corridor_id=12,
    )
    assert acknowledged.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.replan is True
    assert acknowledged.blocked_corridor_id == 12


def test_second_or_high_force_wall_contact_is_terminal_only_after_neutral_ack() -> None:
    for sessions, force in ((2, 1.0), (1, 100_000.0)):
        interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
        decision = interlock.filter_action(
            _obs(
                step_id=20,
                wall_mask=1.0,
                wall_force_n=force,
                wall_sessions=sessions,
            ),
            np.ones(4, dtype=np.float32),
            active_cell_id=1,
            active_corridor_id=2,
        )
        assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
        assert decision.terminal is False
        assert decision.awaiting_neutral_ack is True

        acknowledged = interlock.filter_action(
            _obs(step_id=21, wall_sessions=sessions),
            np.ones(4, dtype=np.float32),
            active_cell_id=1,
            active_corridor_id=2,
        )
        assert acknowledged.action.tolist() == [0.0, 0.0, 0.0, 0.0]
        assert acknowledged.neutral_acknowledged is True
        assert acknowledged.terminal is True


def test_bottom_contact_marks_cell_exhausted_before_clearance_routing() -> None:
    for payload in (14.9, 15.0):
        interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
        initial = interlock.filter_action(
            _obs(
                step_id=30,
                payload_kg=payload,
                bottom_mask=1.0,
                bottom_sessions=1,
            ),
            np.ones(4, dtype=np.float32),
            active_cell_id=4,
            active_corridor_id=8,
        )
        assert initial.action.tolist() == [0.0, 0.0, 0.0, 0.0]

        acknowledged = interlock.filter_action(
            _obs(step_id=31, payload_kg=payload, bottom_sessions=1),
            np.ones(4, dtype=np.float32),
            active_cell_id=4,
            active_corridor_id=8,
        )
        assert acknowledged.depth_exhausted_cell_id == 4
        assert acknowledged.blocked_corridor_id == -1
        assert acknowledged.contact_kind == "hard_bottom"
        assert acknowledged.next_skill == ""
        assert acknowledged.neutral_acknowledged is True
        assert acknowledged.hard_bottom_recovery_active is True


def test_hard_bottom_recovery_requires_scripted_clearance_and_second_neutral_ack() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    proposed = np.asarray([0.7, 0.4, 0.3, 0.2], dtype=np.float32)
    contact = interlock.filter_action(
        _obs(
            step_id=30,
            payload_kg=20.0,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=0,
        active_corridor_id=0,
        skill_name="dig",
    )
    assert contact.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert contact.hard_bottom_contact is True
    assert contact.event_id > 0

    acknowledged = interlock.filter_action(
        _obs(
            step_id=31,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=0,
        active_corridor_id=0,
        skill_name="dig",
    )
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.next_skill == ""
    assert acknowledged.depth_exhausted_cell_id == 0
    assert acknowledged.hard_bottom_recovery_active is True

    interlock.mark_policy_restarted(acknowledged.event_id)
    assert interlock.debug_fields()["box_safety_policy_restarted"] is True

    first_clearance = interlock.pre_policy_decision(
        _obs(
            step_id=32,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.57,
        ),
    )
    assert first_clearance is not None
    assert first_clearance.reason == "hard_bottom_scripted_clearance"
    assert first_clearance.hard_bottom_clearance_active is True
    assert first_clearance.action.tolist() == pytest.approx(
        [0.0, -0.35, 0.35, 0.55]
    )

    second_clearance = interlock.pre_policy_decision(
        _obs(
            step_id=33,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.57,
        ),
    )
    assert second_clearance is not None
    assert second_clearance.hard_bottom_clearance_active is True

    clearance_neutral = interlock.pre_policy_decision(
        _obs(
            step_id=34,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.57,
        ),
    )
    assert clearance_neutral is not None
    assert clearance_neutral.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert clearance_neutral.hard_bottom_clearance_completed is True
    assert clearance_neutral.awaiting_neutral_ack is True

    clearance_ack = interlock.pre_policy_decision(
        _obs(
            step_id=35,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.57,
        ),
    )
    assert clearance_ack is not None
    assert clearance_ack.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert clearance_ack.hard_bottom_clearance_neutral_acknowledged is True
    assert clearance_ack.next_skill == "carry"
    assert clearance_ack.replan is True
    assert clearance_ack.hard_bottom_recovery_active is False


def test_hard_bottom_low_payload_routes_to_fresh_return_after_clearance() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(hard_bottom_clearance_hold_steps=1)
    )
    proposed = np.ones(4, dtype=np.float32)
    interlock.filter_action(
        _obs(
            step_id=10,
            payload_kg=14.9,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=2,
        active_corridor_id=4,
        skill_name="dig",
    )
    interlock.filter_action(
        _obs(
            step_id=11,
            payload_kg=14.9,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=2,
        active_corridor_id=4,
        skill_name="dig",
    )
    neutral = interlock.pre_policy_decision(
        _obs(
            step_id=12,
            payload_kg=14.9,
            bottom_sessions=1,
            plane_depth_m=0.57,
        )
    )
    assert neutral is not None and neutral.awaiting_neutral_ack is True
    acknowledged = interlock.pre_policy_decision(
        _obs(
            step_id=13,
            payload_kg=14.9,
            bottom_sessions=1,
            plane_depth_m=0.57,
        )
    )
    assert acknowledged is not None
    assert acknowledged.next_skill == "return"


def test_exhausted_cell_depth_guard_neutralizes_before_policy_and_replans() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(hard_bottom_clearance_hold_steps=1)
    )
    proposed = np.ones(4, dtype=np.float32)
    interlock.filter_action(
        _obs(
            step_id=10,
            payload_kg=20.0,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=3,
        active_corridor_id=4,
        skill_name="return",
    )
    initial_ack = interlock.filter_action(
        _obs(
            step_id=11,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=3,
        active_corridor_id=4,
        skill_name="return",
    )
    interlock.mark_policy_restarted(initial_ack.event_id)
    interlock.pre_policy_decision(
        _obs(
            step_id=12,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.57,
        ),
    )
    interlock.pre_policy_decision(
        _obs(
            step_id=13,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.57,
        ),
    )

    guarded = interlock.pre_policy_decision(
        _obs(
            step_id=14,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.59,
        ),
        active_cell_id=3,
        active_corridor_id=2,
        skill_name="return",
    )

    assert guarded is not None
    assert guarded.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert guarded.reason == "depth_exhausted_cell_guard"
    assert guarded.awaiting_neutral_ack is True
    assert guarded.depth_exhausted_guard is True

    acknowledged = interlock.pre_policy_decision(
        _obs(
            step_id=15,
            payload_kg=20.0,
            bottom_sessions=1,
            plane_depth_m=0.59,
        ),
        active_cell_id=3,
        active_corridor_id=2,
        skill_name="return",
    )
    assert acknowledged is not None
    assert acknowledged.reason == (
        "depth_exhausted_cell_guard_neutral_acknowledged"
    )
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.hard_bottom_recovery_active is True
    assert acknowledged.depth_exhausted_cell_id == 3
    assert acknowledged.blocked_corridor_id == -1
    assert acknowledged.contact_kind == "hard_bottom"


def test_non_dig_hard_bottom_depth_budget_guards_outside_known_cells() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    obs = _obs(
        step_id=20,
        payload_kg=0.0,
        plane_depth_m=0.59,
        hard_bottom_depth_m=0.60,
    )

    assert (
        interlock.pre_policy_decision(
            obs,
            active_cell_id=-1,
            active_corridor_id=5,
            skill_name="dig",
        )
        is None
    )

    guarded = interlock.pre_policy_decision(
        obs,
        active_cell_id=-1,
        active_corridor_id=5,
        skill_name="return",
    )
    assert guarded is not None
    assert guarded.reason == "hard_bottom_depth_budget_guard"
    assert guarded.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert guarded.awaiting_neutral_ack is True
    assert guarded.hard_bottom_depth_budget_guard is True


def test_hard_bottom_clearance_depth_increase_neutralizes_then_terminates() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    proposed = np.ones(4, dtype=np.float32)
    interlock.filter_action(
        _obs(
            step_id=20,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.50,
        ),
        proposed,
        active_cell_id=1,
        active_corridor_id=1,
        skill_name="dig",
    )
    interlock.filter_action(
        _obs(step_id=21, bottom_sessions=1, plane_depth_m=0.50),
        proposed,
        active_cell_id=1,
        active_corridor_id=1,
        skill_name="dig",
    )

    abort = interlock.pre_policy_decision(
        _obs(step_id=22, bottom_sessions=1, plane_depth_m=0.503)
    )
    assert abort is not None
    assert abort.reason == "hard_bottom_clearance_depth_increase"
    assert abort.awaiting_neutral_ack is True
    assert abort.terminal is False

    terminal = interlock.pre_policy_decision(
        _obs(step_id=23, bottom_sessions=1, plane_depth_m=0.503)
    )
    assert terminal is not None
    assert terminal.neutral_acknowledged is True
    assert terminal.terminal is True


def test_hard_bottom_clearance_depth_increase_is_cumulative_from_contact() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    proposed = np.ones(4, dtype=np.float32)
    interlock.filter_action(
        _obs(
            step_id=20,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.50,
        ),
        proposed,
        active_cell_id=1,
        active_corridor_id=1,
        skill_name="dig",
    )
    interlock.filter_action(
        _obs(step_id=21, bottom_sessions=1, plane_depth_m=0.50),
        proposed,
        active_cell_id=1,
        active_corridor_id=1,
        skill_name="dig",
    )

    first = interlock.pre_policy_decision(
        _obs(step_id=22, bottom_sessions=1, plane_depth_m=0.5015)
    )
    assert first is not None
    assert first.reason == "hard_bottom_scripted_clearance"

    abort = interlock.pre_policy_decision(
        _obs(step_id=23, bottom_sessions=1, plane_depth_m=0.5025)
    )
    assert abort is not None
    assert abort.reason == "hard_bottom_clearance_depth_increase"
    assert abort.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert abort.awaiting_neutral_ack is True


def test_hard_bottom_clearance_timeout_neutralizes_before_terminal() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        SafetyInterlockConfig(hard_bottom_clearance_max_steps=2)
    )
    proposed = np.ones(4, dtype=np.float32)
    interlock.filter_action(
        _obs(
            step_id=30,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        ),
        proposed,
        active_cell_id=1,
        active_corridor_id=1,
        skill_name="dig",
    )
    interlock.filter_action(
        _obs(step_id=31, bottom_sessions=1, plane_depth_m=0.60),
        proposed,
        active_cell_id=1,
        active_corridor_id=1,
        skill_name="dig",
    )

    timeout = interlock.pre_policy_decision(
        _obs(
            step_id=33,
            bottom_mask=1.0,
            bottom_sessions=1,
            plane_depth_m=0.60,
        )
    )
    assert timeout is not None
    assert timeout.reason == "hard_bottom_clearance_timeout"
    assert timeout.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert timeout.awaiting_neutral_ack is True


def test_stuck_detector_requires_50_nonzero_steps_and_both_motion_limits() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    action = np.asarray([0.025, 0.025, 0.025, 0.025], dtype=np.float32)

    for step_id in range(49):
        decision = interlock.filter_action(
            _obs(
                step_id=step_id,
                qpos=(0.001, 0.0, 0.0, 0.0),
                bucket_tip=(0.01, 0.0, 0.0),
            ),
            action,
            active_cell_id=0,
            active_corridor_id=0,
        )
        assert decision.terminal is False

    stuck = interlock.filter_action(
        _obs(
            step_id=49,
            qpos=(0.001, 0.0, 0.0, 0.0),
            bucket_tip=(0.01, 0.0, 0.0),
        ),
        action,
        active_cell_id=0,
        active_corridor_id=0,
    )
    assert stuck.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert stuck.reason == "stuck_50_steps"
    assert stuck.terminal is False
    assert stuck.awaiting_neutral_ack is True

    acknowledged = interlock.filter_action(
        _obs(step_id=50),
        action,
        active_cell_id=0,
        active_corridor_id=0,
    )
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True


def test_subthreshold_action_resets_stuck_window() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())
    moving = np.asarray([0.025, 0.025, 0.025, 0.025], dtype=np.float32)
    for step_id in range(49):
        interlock.filter_action(
            _obs(step_id=step_id),
            moving,
            active_cell_id=0,
            active_corridor_id=0,
        )
    interlock.filter_action(
        _obs(step_id=49),
        np.asarray([0.024, 0.024, 0.024, 0.024], dtype=np.float32),
        active_cell_id=0,
        active_corridor_id=0,
    )
    decision = interlock.filter_action(
        _obs(step_id=50),
        moving,
        active_cell_id=0,
        active_corridor_id=0,
    )
    assert decision.terminal is False
