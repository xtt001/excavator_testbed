from __future__ import annotations

import json

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.rollout_logs import (
    build_box_safety_contact_diagnostic_log_fields,
)
from testbed.planner.box_emptying.bottom_contact_detail import (
    BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
    WORKTOOL_CONTACT_MONITOR_STATUS_MISSING,
    WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX,
)
from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
    SafetyInterlockConfig,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WORKTOOL_WALL_CONTACT_DETAIL_PREFIX,
)
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)


def _unity_diagnostic_config(
    **overrides: object,
) -> SafetyInterlockConfig:
    values: dict[str, object] = {
        "wall_contact_diagnostic_observe_only_enabled": True,
        "wall_first_touch_mode": "record_bucket_all_contacts",
        "unity_contact_diagnostic_observe_only_enabled": True,
        "unity_contact_diagnostic_backend": "agx_unity",
    }
    values.update(overrides)
    return SafetyInterlockConfig(**values)


def _wall_warning(
    *,
    step_id: int,
    component: str = "bucket",
    force_n: float = 10_000.0,
    consecutive_steps: int = 1,
) -> str:
    wall_name = "Dig_XMin_Board"
    payload = {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.05,
        "delta_time_s": 0.05,
        "session_id": 1,
        "session_count": 1,
        "consecutive_contact_steps": consecutive_steps,
        "session_duration_s": consecutive_steps * 0.05,
        "session_normal_impulse_n_s": (
            force_n * consecutive_steps * 0.05
        ),
        "parts": [component],
        "walls": [wall_name],
        "pairs": [
            {
                "component": component,
                "machine_shape_path": f"Machine/{component}/shape",
                "wall_name": wall_name,
                "wall_shape_path": f"DigArea/{wall_name}/shape",
                "callback_count": 1,
                "contact_point_count": 1,
                "max_normal_force_n": force_n,
                "max_tangential_force_n": 0.0,
                "max_total_force_n": force_n,
                "contact_points_world_m": [[0.0, 0.0, 0.0]],
                "representative_contact_point_component_local_m": [
                    0.0,
                    0.0,
                    0.0,
                ],
                "tangential_displacement_m": 0.0,
            }
        ],
    }
    return WORKTOOL_WALL_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )


def _floor_warning(
    *,
    step_id: int,
    session_id: int = 1,
    consecutive_steps: int = 1,
    component: str = "bucket",
    normal_force_n: float = 10_000.0,
    tangential_force_n: float = 0.0,
    total_force_n: float | None = None,
) -> str:
    total = normal_force_n if total_force_n is None else total_force_n
    payload = {
        "schema": "worktool_factory_floor_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.05,
        "delta_time_s": 0.05,
        "session_id": session_id,
        "session_count": session_id,
        "consecutive_contact_steps": consecutive_steps,
        "session_duration_s": consecutive_steps * 0.05,
        "step_max_normal_force_n": normal_force_n,
        "step_max_tangential_force_n": tangential_force_n,
        "step_max_total_force_n": total,
        "parts": [component],
        "pairs": [
            {
                "component": component,
                "machine_shape_path": f"Machine/{component}/shape",
                "floor_shape_path": "FactoryFloor/shape",
                "callback_count": 1,
                "contact_point_count": 1,
                "max_normal_force_n": normal_force_n,
                "max_tangential_force_n": tangential_force_n,
                "max_total_force_n": total,
                "contact_points_world_m": [[0.0, 0.0, 0.0]],
                "representative_contact_point_component_local_m": [
                    0.0,
                    0.0,
                    0.0,
                ],
            }
        ],
    }
    return WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )


def _obs(
    *,
    step_id: int,
    bottom_mask: float = 0.0,
    bottom_force_n: float = 0.0,
    bottom_sessions: float = 0.0,
    wall_mask: float = 0.0,
    wall_force_n: float = 0.0,
    wall_sessions: float = 0.0,
    plane_depth_m: float = 0.0,
    hard_bottom_depth_m: float = 0.60,
    warnings: list[str] | None = None,
    include_floor_sidecar: bool | None = None,
    floor_consecutive_steps: int = 1,
) -> dict[str, object]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX : ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3] = (
        0.1,
        0.2,
        0.3,
    )
    env[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX] = hard_bottom_depth_m
    env[90] = 1600.0
    env[91:97] = 0.2
    env[97:99] = 1920.0
    env[99:101] = 1.0
    env[8] = plane_depth_m
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] = wall_mask
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX] = wall_force_n
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX] = wall_sessions
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX] = bottom_mask
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX] = (
        bottom_force_n
    )
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX] = (
        bottom_sessions
    )
    warning_values = list(warnings or [])
    auto_sidecar = bool(
        bottom_mask == 1.0
        and np.isfinite(bottom_force_n)
        and bottom_force_n >= 0.0
        and np.isfinite(bottom_sessions)
        and bottom_sessions >= 1.0
        and float(bottom_sessions).is_integer()
    )
    if include_floor_sidecar is True or (
        include_floor_sidecar is None and auto_sidecar
    ):
        warning_values.append(
            _floor_warning(
                step_id=step_id,
                session_id=int(bottom_sessions),
                consecutive_steps=floor_consecutive_steps,
                normal_force_n=float(bottom_force_n),
            )
        )
    return {
        "step_id": step_id,
        "sim_time_ns": step_id * 50_000_000,
        "env_state": env,
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "warnings": warning_values,
    }


def _pre(
    interlock: BoxEmptyingSafetyInterlock,
    obs: dict[str, object],
    *,
    skill_name: str = "dig",
):
    return interlock.pre_policy_decision(
        obs,
        active_cell_id=3,
        active_corridor_id=12,
        skill_name=skill_name,
    )


def test_unity_diagnostic_marker_requires_agx_backend_and_wall_superset() -> None:
    with pytest.raises(ValueError, match="unity_contact_diagnostic_backend"):
        SafetyInterlockConfig(
            wall_contact_diagnostic_observe_only_enabled=True,
            wall_first_touch_mode="record_bucket_all_contacts",
            unity_contact_diagnostic_observe_only_enabled=True,
        )
    with pytest.raises(ValueError, match="record_bucket_all_contacts"):
        SafetyInterlockConfig(
            unity_contact_diagnostic_observe_only_enabled=True,
            unity_contact_diagnostic_backend="agx_unity",
        )
    with pytest.raises(ValueError, match="must be empty when.*disabled"):
        SafetyInterlockConfig(
            unity_contact_diagnostic_backend="agx_unity",
        )
    with pytest.raises(ValueError, match="exactly 100000"):
        _unity_diagnostic_config(wall_high_force_n=99_999.0)


def test_adapter_rejects_unscoped_or_nonboolean_unity_diagnostic_marker() -> None:
    for safety, match in (
        (
            {
                "unity_contact_diagnostic_observe_only_enabled": "true",
            },
            "unity_contact_diagnostic_observe_only_enabled",
        ),
        (
            {
                "wall_contact_diagnostic_observe_only_enabled": True,
                "wall_first_touch_mode": "record_bucket_all_contacts",
                "unity_contact_diagnostic_observe_only_enabled": True,
                "unity_contact_diagnostic_backend": "mujoco",
            },
            "unity_contact_diagnostic_backend",
        ),
    ):
        with pytest.raises(ValueError, match=match):
            PrimitivePlannerAdapterConfigNormalizer.normalize(
                PrimitivePlannerAdapterConfigInputs(
                    box_emptying={
                        "safety_enabled": True,
                        "safety": safety,
                    }
                )
            )


def test_adapter_accepts_explicit_agx_unity_contact_diagnostic() -> None:
    safety = {
        "wall_contact_diagnostic_observe_only_enabled": True,
        "wall_first_touch_mode": "record_bucket_all_contacts",
        "unity_contact_diagnostic_observe_only_enabled": True,
        "unity_contact_diagnostic_backend": "agx_unity",
    }
    updates = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            box_emptying={
                "safety_enabled": True,
                "safety": safety,
            }
        )
    ).as_policy_field_updates()

    assert updates["box_emptying_cfg"]["safety"] == safety


def test_low_force_bottom_contacts_are_record_only_across_sessions() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    proposed = np.asarray([0.2, -0.3, 0.4, -0.5], dtype=np.float32)
    frames = (
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_force_n=20_000.0,
            bottom_sessions=1,
        ),
        _obs(
            step_id=11,
            bottom_mask=1.0,
            bottom_force_n=30_000.0,
            bottom_sessions=1,
            floor_consecutive_steps=2,
        ),
        _obs(step_id=12, bottom_sessions=1),
        _obs(
            step_id=13,
            bottom_mask=1.0,
            bottom_force_n=40_000.0,
            bottom_sessions=2,
        ),
    )

    for frame in frames:
        assert _pre(interlock, frame) is None
        decision = interlock.filter_action(
            frame,
            proposed,
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        )
        assert decision.action.tolist() == pytest.approx(proposed.tolist())
        assert decision.reason == ""
        assert decision.terminal is False
        assert decision.awaiting_neutral_ack is False
        assert decision.neutral_acknowledged is False
        assert decision.replan is False
        assert decision.blocked_corridor_id == -1
        assert decision.depth_exhausted_cell_id == -1
        if float(np.asarray(frame["env_state"])[104]) >= 0.5:
            assert (
                decision.factory_floor_contact_diagnostic_allowed is True
            )
            assert decision.unity_contact_diagnostic_allowed is True

    debug = interlock.debug_fields()
    assert debug[
        "box_safety_unity_contact_diagnostic_observe_only_enabled"
    ] is True
    assert debug["box_safety_unity_contact_diagnostic_backend"] == "agx_unity"
    assert debug["box_safety_depth_exhausted_cell_ids"] == []


def test_unity_diagnostic_disables_depth_budget_guard_and_takeover() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    proposed = np.full(4, 0.25, dtype=np.float32)
    contact = _obs(
        step_id=10,
        bottom_mask=1.0,
        bottom_force_n=25_000.0,
        bottom_sessions=1,
        plane_depth_m=0.60,
    )

    assert _pre(interlock, contact, skill_name="return") is None
    decision = interlock.filter_action(
        contact,
        proposed,
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="return",
    )
    assert decision.action.tolist() == pytest.approx(proposed.tolist())
    assert decision.hard_bottom_contact is False
    assert decision.hard_bottom_recovery_active is False
    assert decision.hard_bottom_depth_budget_guard is False

    clear_near_bottom = _obs(
        step_id=11,
        bottom_sessions=1,
        plane_depth_m=0.59,
    )
    assert _pre(
        interlock,
        clear_near_bottom,
        skill_name="return",
    ) is None


@pytest.mark.parametrize(
    ("force_n", "reason"),
    [
        (100_000.0, "factory_floor_contact_high_force"),
        (float("nan"), "factory_floor_contact_detail_invalid"),
        (-1.0, "factory_floor_contact_detail_invalid"),
    ],
)
def test_bottom_high_force_or_invalid_force_stops_before_policy(
    force_n: float,
    reason: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    decision = _pre(
        interlock,
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_force_n=force_n,
            bottom_sessions=1,
        ),
    )

    assert decision is not None
    assert decision.reason == reason
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert decision.awaiting_neutral_ack is True
    assert decision.event_id > 0
    acknowledged = _pre(
        interlock,
        _obs(step_id=11, bottom_sessions=1),
    )
    assert acknowledged is not None
    assert acknowledged.reason == reason
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
    assert acknowledged.event_id == decision.event_id


@pytest.mark.parametrize(
    ("warnings", "reason"),
    [
        ((), "factory_floor_contact_high_force"),
        (
            ("bucket_factory_floor_contact_lineage_incomplete_v1",),
            "factory_floor_contact_lineage_incomplete",
        ),
    ],
)
def test_persistent_bottom_hard_stop_reaches_neutral_ack_without_rearming(
    warnings: tuple[str, ...],
    reason: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    force_n = 100_000.0 if not warnings else 0.0
    first = _obs(
        step_id=10,
        bottom_mask=1.0,
        bottom_force_n=force_n,
        bottom_sessions=1,
        warnings=list(warnings),
    )
    second = _obs(
        step_id=11,
        bottom_mask=1.0,
        bottom_force_n=force_n,
        bottom_sessions=1,
        warnings=list(warnings),
        floor_consecutive_steps=2,
    )

    initial = _pre(interlock, first)
    acknowledged = _pre(interlock, second)

    assert initial is not None
    assert initial.reason == reason
    assert initial.awaiting_neutral_ack is True
    assert acknowledged is not None
    assert acknowledged.reason == reason
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True


def test_same_bottom_session_low_to_high_force_stops_before_policy() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    assert _pre(
        interlock,
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_force_n=20_000.0,
            bottom_sessions=1,
        ),
    ) is None

    decision = _pre(
        interlock,
        _obs(
            step_id=11,
            bottom_mask=1.0,
            bottom_force_n=100_000.0,
            bottom_sessions=1,
            floor_consecutive_steps=2,
        ),
    )

    assert decision is not None
    assert decision.reason == "factory_floor_contact_high_force"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert decision.awaiting_neutral_ack is True


def test_simultaneous_floor_and_wall_unsafe_keeps_first_terminal_event() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    initial = _pre(
        interlock,
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_force_n=100_000.0,
            bottom_sessions=1,
            wall_mask=1.0,
            wall_force_n=100_000.0,
            wall_sessions=1,
            warnings=[
                _wall_warning(
                    step_id=10,
                    force_n=100_000.0,
                )
            ],
        ),
    )
    acknowledged = _pre(
        interlock,
        _obs(
            step_id=11,
            bottom_mask=1.0,
            bottom_force_n=100_000.0,
            bottom_sessions=1,
            floor_consecutive_steps=2,
            wall_mask=1.0,
            wall_force_n=100_000.0,
            wall_sessions=1,
            warnings=[
                _wall_warning(
                    step_id=11,
                    force_n=100_000.0,
                    consecutive_steps=2,
                )
            ],
        ),
    )

    assert initial is not None
    assert initial.reason == "factory_floor_contact_high_force"
    assert initial.awaiting_neutral_ack is True
    assert acknowledged is not None
    assert acknowledged.reason == initial.reason
    assert acknowledged.event_id == initial.event_id
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True


@pytest.mark.parametrize(
    "warning",
    [
        "bucket_factory_floor_contact_lineage_incomplete_v1",
        (
            BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX
            + '{"step_id":10}'
        ),
    ],
)
def test_bottom_incomplete_force_lineage_is_terminal(
    warning: str,
) -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())

    decision = _pre(
        interlock,
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_sessions=1,
            warnings=[warning],
        ),
    )

    assert decision is not None
    assert decision.reason == "factory_floor_contact_lineage_incomplete"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize(
    "frames",
    [
        (
            _obs(step_id=10),
            _obs(
                step_id=11,
                bottom_mask=0.25,
                bottom_sessions=0,
            ),
        ),
        (
            _obs(step_id=10),
            _obs(
                step_id=11,
                bottom_mask=float("nan"),
                bottom_sessions=0,
            ),
        ),
        (
            _obs(step_id=10),
            _obs(
                step_id=11,
                bottom_mask=1.0,
                bottom_force_n=10_000.0,
                bottom_sessions=2,
            ),
        ),
        (
            _obs(step_id=10),
            _obs(
                step_id=11,
                bottom_mask=1.0,
                bottom_force_n=10_000.0,
                bottom_sessions=float("nan"),
            ),
        ),
        (
            _obs(
                step_id=10,
                bottom_mask=1.0,
                bottom_force_n=10_000.0,
                bottom_sessions=1,
            ),
            _obs(step_id=11, bottom_sessions=0),
        ),
    ],
)
def test_bottom_mask_and_session_lineage_anomalies_stop(
    frames: tuple[dict[str, object], ...],
) -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    for frame in frames[:-1]:
        assert _pre(interlock, frame) is None

    decision = _pre(interlock, frames[-1])

    assert decision is not None
    assert decision.reason == "factory_floor_contact_detail_invalid"


def test_low_bottom_does_not_hide_forbidden_wall_component() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    obs = _obs(
        step_id=10,
        bottom_mask=1.0,
        bottom_force_n=20_000.0,
        bottom_sessions=1,
        wall_mask=1.0,
        wall_force_n=30_000.0,
        wall_sessions=1,
        warnings=[
            _wall_warning(
                step_id=10,
                component="boom",
                force_n=30_000.0,
            )
        ],
    )

    decision = _pre(interlock, obs)

    assert decision is not None
    assert decision.reason == "wall_contact_forbidden_component"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_low_bucket_wall_sets_combined_unity_diagnostic_allowed_marker() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    obs = _obs(
        step_id=10,
        wall_mask=1.0,
        wall_force_n=30_000.0,
        wall_sessions=1,
        warnings=[_wall_warning(step_id=10, force_n=30_000.0)],
    )

    decision = interlock.filter_action(
        obs,
        np.full(4, 0.25, dtype=np.float32),
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )

    assert decision.wall_contact_diagnostic_allowed is True
    assert decision.factory_floor_contact_diagnostic_allowed is False
    assert decision.unity_contact_diagnostic_allowed is True
    assert decision.action.tolist() == [0.25, 0.25, 0.25, 0.25]


def test_outside_footprint_floor_contact_sets_only_floor_marker() -> None:
    interlock = BoxEmptyingSafetyInterlock(_unity_diagnostic_config())
    obs = _obs(
        step_id=10,
        warnings=[_floor_warning(step_id=10, normal_force_n=25_000.0)],
    )

    decision = interlock.filter_action(
        obs,
        np.full(4, 0.25, dtype=np.float32),
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )

    assert decision.factory_floor_contact_diagnostic_allowed is True
    assert decision.wall_contact_diagnostic_allowed is False
    assert decision.unity_contact_diagnostic_allowed is True
    assert decision.action.tolist() == [0.25, 0.25, 0.25, 0.25]


@pytest.mark.parametrize(
    ("warning", "reason"),
    [
        (
            _floor_warning(step_id=10, component="stick"),
            "factory_floor_contact_forbidden_component",
        ),
        (
            _floor_warning(
                step_id=10,
                normal_force_n=10_000.0,
                tangential_force_n=100_000.0,
                total_force_n=100_000.0,
            ),
            "factory_floor_contact_high_force",
        ),
        (
            WORKTOOL_CONTACT_MONITOR_STATUS_MISSING,
            "factory_floor_contact_lineage_incomplete",
        ),
    ],
)
def test_all_part_floor_unsafe_contact_stops_before_policy(
    warning: str,
    reason: str,
) -> None:
    decision = _pre(
        BoxEmptyingSafetyInterlock(_unity_diagnostic_config()),
        _obs(step_id=10, warnings=[warning]),
    )

    assert decision is not None
    assert decision.reason == reason
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert decision.awaiting_neutral_ack is True


def test_allowed_bottom_still_reaches_stuck_and_timeout_stops() -> None:
    interlock = BoxEmptyingSafetyInterlock(
        _unity_diagnostic_config(stuck_window_steps=2)
    )
    proposed = np.full(4, 0.25, dtype=np.float32)
    frames = (
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_force_n=10_000.0,
            bottom_sessions=1,
        ),
        _obs(
            step_id=11,
            bottom_mask=1.0,
            bottom_force_n=10_000.0,
            bottom_sessions=1,
            floor_consecutive_steps=2,
        ),
    )
    for frame in frames:
        decision = interlock.filter_action(
            frame,
            proposed,
            active_cell_id=3,
            active_corridor_id=12,
            skill_name="dig",
        )
    assert decision.reason == "stuck_50_steps"
    assert decision.action.tolist() == [0.0, 0.0, 0.0, 0.0]

    timeout_interlock = BoxEmptyingSafetyInterlock(
        _unity_diagnostic_config()
    )
    timeout = timeout_interlock.request_terminal_neutral_action(
        _obs(step_id=20),
        reason="timeout",
        active_cell_id=3,
        active_corridor_id=12,
        skill_name="dig",
    )
    assert timeout.reason == "timeout"
    assert timeout.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert timeout.awaiting_neutral_ack is True


def test_production_default_retains_hard_bottom_takeover() -> None:
    interlock = BoxEmptyingSafetyInterlock(SafetyInterlockConfig())

    decision = _pre(
        interlock,
        _obs(
            step_id=10,
            bottom_mask=1.0,
            bottom_force_n=10_000.0,
            bottom_sessions=1,
        ),
    )

    assert decision is not None
    assert decision.reason == "hard_bottom_contact"
    assert decision.hard_bottom_contact is True


def test_rollout_log_preserves_unity_contact_diagnostic_lineage() -> None:
    fields = build_box_safety_contact_diagnostic_log_fields(
        {
            "box_safety_wall_contact_diagnostic_allowed": True,
            "box_safety_factory_floor_contact_diagnostic_allowed": True,
            "box_safety_unity_contact_diagnostic_allowed": True,
            (
                "box_safety_unity_contact_diagnostic_"
                "observe_only_enabled"
            ): True,
            "box_safety_unity_contact_diagnostic_backend": "agx_unity",
            "box_safety_contact_kind": "wall",
            "box_safety_wall_contact_session_count": 3,
        }
    )

    assert fields == {
        "box_safety_wall_contact_diagnostic_allowed": True,
        "box_safety_factory_floor_contact_diagnostic_allowed": True,
        "box_safety_unity_contact_diagnostic_allowed": True,
        "box_safety_unity_contact_diagnostic_observe_only_enabled": True,
        "box_safety_unity_contact_diagnostic_backend": "agx_unity",
        "box_safety_contact_kind": "wall",
        "box_safety_wall_contact_session_count": 3,
    }
