from __future__ import annotations

import numpy as np

from testbed.planner.primitive.effects.continuous_goal_handoff import (
    ContinuousGoalHandoffGuardService,
    ContinuousGoalHandoffGuardState,
)


def _token() -> np.ndarray:
    token = np.zeros(18, dtype=np.float32)
    token[0:2] = [0.25, 0.50]
    token[2:6] = [0.08, 0.20, 0.04, 0.12]
    token[6] = 1.0
    token[7:11] = [0.5, 0.4, 0.6, 0.2]
    token[11:15] = 0.03
    token[15] = 0.10
    token[16:18] = 1.0
    return token


def test_continuous_handoff_requires_three_consecutive_ready_frames() -> None:
    goal_id = "a" * 64
    state = ContinuousGoalHandoffGuardState()
    service = ContinuousGoalHandoffGuardService(hold_steps=3)

    results = [
        service.evaluate(
            state,
            expected_goal_id=goal_id,
            envelope_goal_id=goal_id,
            return_step=step,
            token=_token(),
            prior_independent_depth_m=0.08,
            prior_independent_plane_depth_m=0.06,
            base_ready=True,
            base_checks={
                "spatial": {"ok": True},
                "local_depth_m": {"ok": True},
                "plane_depth_m": {"ok": True},
                "dig_contact": {"ok": True},
                "qpos_0": {"ok": True},
                "qvel_abs_max": {"ok": True},
            },
        )
        for step in (12, 13, 14)
    ]

    assert [result.ready for result in results] == [False, False, True]
    assert results[-1].hold_count == 3
    assert results[-1].first_ready_step == 14
    assert results[-1].violations == {}


def test_continuous_handoff_fails_closed_and_resets_hold_on_violation() -> None:
    goal_id = "b" * 64
    state = ContinuousGoalHandoffGuardState()
    service = ContinuousGoalHandoffGuardService(hold_steps=3)
    valid = service.evaluate(
        state,
        expected_goal_id=goal_id,
        envelope_goal_id=goal_id,
        return_step=20,
        token=_token(),
        prior_independent_depth_m=0.08,
        prior_independent_plane_depth_m=0.06,
        base_ready=True,
        base_checks={"qpos_0": {"ok": True}},
    )
    assert valid.hold_count == 1

    bad_token = _token()
    bad_token[0] = np.nan
    blocked = service.evaluate(
        state,
        expected_goal_id=goal_id,
        envelope_goal_id="c" * 64,
        return_step=21,
        token=bad_token,
        prior_independent_depth_m=float("nan"),
        prior_independent_plane_depth_m=float("nan"),
        base_ready=False,
        base_checks={
            "qpos_0": {"ok": False},
            "local_depth_missing": True,
        },
    )

    assert blocked.ready is False
    assert blocked.hold_count == 0
    assert blocked.first_ready_step is None
    assert set(blocked.violations) >= {
        "goal_identity_drift",
        "return_envelope_token_invalid",
        "prior_independent_depth_missing",
        "qpos_0",
        "local_depth_missing",
    }
