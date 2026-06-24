from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignPorts,
    PrimitivePreDigAlignRuntimeConfig,
    PrimitivePreDigAlignRuntimeService,
    PrimitivePreDigAlignRuntimeState,
)


@dataclass(frozen=True)
class _Corridor:
    entry_x_m: float
    entry_z_m: float


@dataclass
class _PortFacts:
    token: np.ndarray
    corridor: _Corridor | None = _Corridor(0.0, 0.0)
    bucket_tip_pose: tuple[float, float, float] | None = (0.0, 0.0, 0.0)
    bucket_dig_area_pose: tuple[float, float, float] | None = (0.0, 0.0, 0.0)
    surface_depth_m: float = float("nan")
    contact_mask: bool = False
    cycle_index: int = 0
    ensure_calls: int = 0

    def ensure_dig_cut_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        del obs
        self.ensure_calls += 1


def _config(**overrides: Any) -> PrimitivePreDigAlignRuntimeConfig:
    values: dict[str, Any] = {
        "action_dim": 4,
        "enabled": True,
        "first_dig_only": False,
        "replan_after_failed_dig": False,
        "kp": 2.0,
        "kd": 0.25,
        "action_clip": np.ones(4, dtype=np.float32),
        "action_signs": np.ones(4, dtype=np.float32),
        "controlled_dims": np.ones(4, dtype=bool),
        "entry_intent_controlled_dims": None,
        "bucket_target_qpos": None,
        "qpos_tolerance": np.full(4, 0.05, dtype=np.float32),
        "qvel_abs_max": 0.1,
        "hold_steps": 2,
        "max_steps": 3,
        "max_entry_error_m": 0.25,
        "timeout_accept_entry_error_m": None,
        "timeout_replan_entry_error_m": None,
        "start_envelope_enabled": False,
        "first_dig_entry_close_handoff": False,
        "first_dig_entry_close_handoff_qvel_abs_max": None,
        "start_envelope_max_entry_error_m": 0.65,
        "entry_intent_handoff_enabled": False,
        "surface_guard_enabled": False,
        "surface_guard_max_penetration_m": 0.005,
        "surface_guard_handoff_entry_error_m": None,
        "surface_guard_use_contact_fallback": True,
        "start_qpos_min": np.full(4, -1.0, dtype=np.float32),
        "start_qpos_max": np.full(4, 1.0, dtype=np.float32),
        "start_pose_min": np.full(3, -1.0, dtype=np.float32),
        "start_pose_max": np.full(3, 1.0, dtype=np.float32),
        "qpos_min": np.full(4, -1.0, dtype=np.float32),
        "qpos_max": np.full(4, 1.0, dtype=np.float32),
        "qpos_from_token_coefficients": np.zeros((4, 3), dtype=np.float32),
    }
    values.update(overrides)
    return PrimitivePreDigAlignRuntimeConfig(**values)


def _service(
    config: PrimitivePreDigAlignRuntimeConfig | None = None,
    facts: _PortFacts | None = None,
) -> tuple[PrimitivePreDigAlignRuntimeService, PrimitivePreDigAlignRuntimeState, _PortFacts]:
    port_facts = facts or _PortFacts(token=np.zeros(10, dtype=np.float32))
    state = PrimitivePreDigAlignRuntimeState.fresh(action_dim=4)
    ports = PrimitivePreDigAlignPorts(
        ensure_dig_cut_plan_for_cycle=port_facts.ensure_dig_cut_plan_for_cycle,
        dig_cut_tokens=lambda: port_facts.token,
        active_coverage_corridor=lambda: port_facts.corridor,
        bucket_tip_dig_area_pose=lambda obs: port_facts.bucket_tip_pose,
        bucket_dig_area_pose=lambda obs: port_facts.bucket_dig_area_pose,
        bucket_depth_below_local_surface=lambda obs: port_facts.surface_depth_m,
        bucket_dig_area_contact_mask=lambda obs: port_facts.contact_mask,
        cycle_index=lambda: port_facts.cycle_index,
    )
    return (
        PrimitivePreDigAlignRuntimeService(
            config=config or _config(),
            state=state,
            ports=ports,
        ),
        state,
        port_facts,
    )


def test_target_from_token_clips_bucket_override_and_uncontrolled_dims() -> None:
    service, state, _ = _service(
        _config(
            controlled_dims=np.asarray([True, False, True, True]),
            qpos_min=np.asarray([-0.5, -0.5, -0.3, -0.2], dtype=np.float32),
            qpos_max=np.asarray([0.6, 0.7, 0.4, 0.2], dtype=np.float32),
            bucket_target_qpos=0.25,
            qpos_from_token_coefficients=np.asarray(
                [
                    [0.5, 1.0, 0.0],
                    [0.0, 0.0, 0.0],
                    [0.1, 0.0, 2.0],
                    [0.0, 0.0, 0.0],
                ],
                dtype=np.float32,
            ),
        )
    )
    obs = {"qpos": np.asarray([0.1, -0.77, 0.2, 0.0], dtype=np.float32)}

    target = service.target_from_token(
        token=np.asarray([1.0, -1.0], dtype=np.float32),
        obs=obs,
        update_state=True,
    )

    assert target.dtype == np.float32
    np.testing.assert_allclose(target, [0.6, -0.77, -0.3, 0.2])
    np.testing.assert_allclose(state.target_qpos, target)


def test_target_uses_current_dig_cut_token_and_ensure_port() -> None:
    facts = _PortFacts(token=np.asarray([0.2, 0.4], dtype=np.float32))
    service, _, port_facts = _service(
        _config(
            qpos_from_token_coefficients=np.asarray(
                [
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                ],
                dtype=np.float32,
            ),
        ),
        facts=facts,
    )

    target = service.target({"qpos": np.zeros(4, dtype=np.float32)})

    assert port_facts.ensure_calls == 1
    np.testing.assert_allclose(target, [0.2, 0.4, 0.0, 0.0])


def test_pd_servo_action_applies_sign_clip_and_uncontrolled_zeroing() -> None:
    service, _, _ = _service(
        _config(
            kp=2.0,
            kd=0.5,
            action_clip=np.asarray([0.5, 0.5, 0.25, 1.0], dtype=np.float32),
            action_signs=np.asarray([1.0, -1.0, -1.0, 1.0], dtype=np.float32),
            controlled_dims=np.asarray([True, False, True, True]),
        )
    )

    action = service.pd_servo_action(
        qpos=np.asarray([0.0, 0.0, 1.0, -1.0], dtype=np.float32),
        qvel=np.asarray([0.2, 0.0, -0.5, 1.0], dtype=np.float32),
        target_qpos=np.asarray([1.0, 1.0, 0.0, 1.0], dtype=np.float32),
    )

    assert action.dtype == np.float32
    np.testing.assert_allclose(action, [0.5, 0.0, 0.25, 1.0])


def test_surface_guard_action_returns_zero_and_updates_state() -> None:
    service, state, facts = _service(
        _config(
            surface_guard_enabled=True,
            surface_guard_max_penetration_m=0.01,
        ),
        facts=_PortFacts(
            token=np.asarray([0.2, 0.4], dtype=np.float32),
            surface_depth_m=0.02,
        ),
    )

    action = service.action({"qpos": np.zeros(4), "qvel": np.zeros(4)})

    np.testing.assert_allclose(action, np.zeros(4, dtype=np.float32))
    assert state.step_count == 1
    assert state.surface_guard_triggered is True
    assert state.surface_depth_m == pytest.approx(0.02)
    assert facts.ensure_calls == 0


def test_ready_increments_hold_with_start_envelope_and_resets_on_gate_failure() -> None:
    service, state, facts = _service(
        _config(
            max_entry_error_m=0.1,
            start_envelope_enabled=True,
            start_envelope_max_entry_error_m=0.5,
            start_qpos_min=np.full(4, -0.1, dtype=np.float32),
            start_qpos_max=np.full(4, 0.1, dtype=np.float32),
            start_pose_min=np.full(3, -0.2, dtype=np.float32),
            start_pose_max=np.full(3, 0.2, dtype=np.float32),
        ),
        facts=_PortFacts(
            token=np.zeros(10, dtype=np.float32),
            bucket_tip_pose=(0.3, 0.0, 0.0),
            bucket_dig_area_pose=(0.0, 0.0, 0.0),
        ),
    )
    obs = {"qpos": np.zeros(4, dtype=np.float32), "qvel": np.zeros(4, dtype=np.float32)}

    assert service.ready(obs) is False
    assert state.hold_count == 1
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is False
    assert service.ready(obs) is True
    assert state.hold_count == 2

    facts.bucket_tip_pose = (0.8, 0.0, 0.0)
    assert service.ready(obs) is False
    assert state.hold_count == 0
    assert state.start_envelope_ready is False

    facts.bucket_tip_pose = (0.0, 0.0, 0.0)
    fast_obs = {
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.asarray([0.2, 0.0, 0.0, 0.0], dtype=np.float32),
    }
    assert service.ready(fast_obs) is False
    assert state.hold_count == 0


def test_mark_completed_increments_completed_count() -> None:
    service, state, _ = _service()

    service.mark_completed()
    service.mark_completed()

    assert state.completed_count == 2


def test_mark_surface_guard_increments_counter_and_reset_hold_clears_hold_count() -> None:
    service, state, _ = _service()
    state.hold_count = 3

    service.mark_surface_guard()
    service.reset_hold()

    assert state.surface_guard_count == 1
    assert state.hold_count == 0


def test_timeout_state_helpers_preserve_step_threshold_and_counter_owner() -> None:
    service, state, _ = _service(_config(max_steps=3))

    state.step_count = 2
    assert service.timed_out() is False

    state.step_count = 3
    assert service.timed_out() is True

    service.mark_timeout()
    assert state.timeout_count == 1


@pytest.mark.parametrize(
    ("overrides", "bucket_tip_pose", "expected_reason"),
    [
        (
            {"max_entry_error_m": None, "timeout_accept_entry_error_m": None},
            (99.0, 0.0, 0.0),
            "pre_dig_align_to_dig_timeout_no_entry_gate",
        ),
        (
            {
                "controlled_dims": np.asarray([True, True, False, False]),
                "entry_intent_controlled_dims": np.asarray(
                    [True, False, False, False]
                ),
                "entry_intent_handoff_enabled": True,
                "max_entry_error_m": 0.1,
                "timeout_accept_entry_error_m": 0.2,
            },
            (99.0, 0.0, 0.0),
            "pre_dig_align_to_dig_timeout_intent_aligned",
        ),
        (
            {"max_entry_error_m": 0.1, "timeout_accept_entry_error_m": 0.5},
            (0.3, 0.0, 0.0),
            "pre_dig_align_to_dig_timeout_close_enough",
        ),
    ],
)
def test_timeout_can_handoff_preserves_legacy_reason_strings(
    overrides: dict[str, Any],
    bucket_tip_pose: tuple[float, float, float],
    expected_reason: str,
) -> None:
    service, state, _ = _service(
        _config(**overrides),
        facts=_PortFacts(
            token=np.zeros(10, dtype=np.float32),
            bucket_tip_pose=bucket_tip_pose,
        ),
    )

    assert service.timeout_can_handoff({"qpos": np.zeros(4)}) is True
    assert state.timeout_handoff_reason == expected_reason


def test_should_pre_dig_align_predicates_respect_enabled_cycle_and_replan_flags() -> None:
    service, _, facts = _service(_config(first_dig_only=True))

    assert service.should_pre_dig_align_before_dig() is True
    facts.cycle_index = 1
    assert service.should_pre_dig_align_before_dig() is False

    disabled, _, _ = _service(_config(enabled=False, replan_after_failed_dig=True))
    assert disabled.should_pre_dig_align_before_dig() is False
    assert disabled.should_pre_dig_align_after_failed_dig() is False

    replan, _, _ = _service(_config(replan_after_failed_dig=True))
    assert replan.should_pre_dig_align_after_failed_dig() is True
