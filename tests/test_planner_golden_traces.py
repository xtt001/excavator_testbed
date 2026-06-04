from __future__ import annotations

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_DIM,
    RETURN_TARGET_TOKEN_KEY,
    token_contract_string,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_spatial_mass_boundary_events_drive_planner_golden_trace() -> None:
    dig_policy = _ConstantPolicy(0)
    carry_policy = _ConstantPolicy(1)
    dump_policy = _ConstantPolicy(2)
    return_policy = _ConstantPolicy(3)
    policy = PrimitivePlannerACTPolicy(
        dig_policy=dig_policy,
        carry_policy=carry_policy,
        dump_policy=dump_policy,
        return_policy=return_policy,
        boundary_detector=_FakeBoundaryDetector(
            [
                _FakeBoundaryEvent(dig_complete=True),
                _FakeBoundaryEvent(dump_committed_start=True),
                _FakeBoundaryEvent(dump_complete=True),
                _FakeBoundaryEvent(next_dig_entry_ready=True),
            ],
            boundary_profile="v2_4_5_spatial_mass",
        ),
        dig_to_carry_min_bucket_mass_kg=999.0,
        dump_ready_hold_steps=3,
        dump_done_hold_steps=30,
    )
    trace = [
        (_obs(mass=0.0, dig_distance=0.0), 0.0, "dig", None),
        (
            _obs(mass=1000.0, dig_distance=0.0),
            1.0,
            "carry",
            "dig_to_carry_dig_complete_boundary",
        ),
        (
            _obs(mass=0.0, dig_distance=0.0, dump_ready=False),
            2.0,
            "dump",
            "carry_to_dump_dump_committed_boundary",
        ),
        (
            _obs(mass=500.0, dig_distance=0.0, deposited=0.0),
            3.0,
            "return",
            "dump_to_return_dump_complete_boundary",
        ),
        (
            _obs(mass=0.0, dig_distance=0.0),
            0.0,
            "dig",
            "return_to_dig_next_dig_entry_ready",
        ),
    ]

    observed = []
    for obs, expected_action, expected_skill, expected_reason in trace:
        action = policy.predict(obs)
        state = policy.debug_state()
        observed.append(
            {
                "action0": float(action[0]),
                "skill": state["skill_name"],
                "reason": state["skill_switch_reason"],
            }
        )
        assert float(action[0]) == expected_action
        assert state["skill_name"] == expected_skill
        if expected_reason is not None:
            assert state["skill_switch_reason"] == expected_reason

    assert observed == [
        {"action0": 0.0, "skill": "dig", "reason": ""},
        {
            "action0": 1.0,
            "skill": "carry",
            "reason": "dig_to_carry_dig_complete_boundary",
        },
        {
            "action0": 2.0,
            "skill": "dump",
            "reason": "carry_to_dump_dump_committed_boundary",
        },
        {
            "action0": 3.0,
            "skill": "return",
            "reason": "dump_to_return_dump_complete_boundary",
        },
        {
            "action0": 0.0,
            "skill": "dig",
            "reason": "return_to_dig_next_dig_entry_ready",
        },
    ]
    summary = policy.rollout_summary()
    assert summary["completed_transition_count"] == 1
    state = policy.debug_state()
    assert state["dig_cut_token_dim"] == DIG_CUT_TOKEN_DIM
    assert state["dig_depth_profile_token_dim"] == DIG_DEPTH_PROFILE_TOKEN_DIM
    assert state["return_target_token_dim"] == RETURN_TARGET_TOKEN_DIM
    assert state["return_start_envelope_token_dim"] == RETURN_START_ENVELOPE_TOKEN_DIM
    assert state["return_target_token_source"] == "none"
    assert state["return_start_envelope_token_source"] == "none"
    planner_trace = policy.planner_trace()
    assert planner_trace["dig_cut_token_contract"] == token_contract_string(
        DIG_CUT_TOKEN_KEY
    )
    assert planner_trace["return_target_token_contract"] == token_contract_string(
        RETURN_TARGET_TOKEN_KEY,
        prefix="next",
    )
    assert planner_trace["return_start_envelope_token_contract_version"] == (
        RETURN_START_ENVELOPE_TOKEN_KEY
    )
    assert planner_trace["return_start_envelope_token_contract"] == (
        token_contract_string(RETURN_START_ENVELOPE_TOKEN_KEY)
    )
    assert dig_policy.reset_count == 2
    assert carry_policy.reset_count == 2
    assert dump_policy.reset_count == 2
    assert return_policy.reset_count == 2


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, _obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryEvent:
    def __init__(
        self,
        *,
        qualified_dig_start: bool = False,
        dig_complete: bool = False,
        dump_committed_start: bool = False,
        dump_complete: bool = False,
        next_dig_entry_ready: bool = False,
        dump_end: bool = False,
        metrics: dict | None = None,
    ) -> None:
        self.qualified_dig_start = bool(qualified_dig_start)
        self.dig_complete = bool(dig_complete)
        self.dump_committed_start = bool(dump_committed_start)
        self.dump_complete = bool(dump_complete)
        self.next_dig_entry_ready = bool(next_dig_entry_ready)
        self.dump_end = bool(dump_end)
        self.metrics = dict(metrics or {})


class _FakeBoundaryDetector:
    def __init__(
        self,
        events: list[_FakeBoundaryEvent],
        *,
        boundary_profile: str,
    ) -> None:
        self.events = list(events)
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": str(boundary_profile)},
        )()

    def reset(self) -> None:
        pass

    def update(self, **_kwargs) -> _FakeBoundaryEvent:
        if self.events:
            return self.events.pop(0)
        return _FakeBoundaryEvent()


def _obs(
    *,
    mass: float,
    dig_distance: float,
    bucket_depth: float = 0.0,
    dump_ready: bool = False,
    deposited: float = 0.0,
) -> dict:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(mass)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited)
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = float(dig_distance)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(bucket_depth)
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.15 if dump_ready else 2.0
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = (
        0.50 if dump_ready else -0.20
    )
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 1.0 if dump_ready else 0.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0 if dump_ready else 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = (
        0.0 if dump_ready else 2.0
    )
    return {
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": float(mass),
            "deposited_mass_in_target_box_kg": float(deposited),
            "min_distance_to_dig_area_m": float(dig_distance),
            "bucket_depth_below_dig_area_plane_m": float(bucket_depth),
            "target_geometry_available": 1.0,
            "target_horizontal_distance_m": float(
                env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
            ),
            "bucket_height_above_target_rim_m": float(
                env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
            ),
            "bucket_over_target_footprint_mask": float(
                env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX]
            ),
            "dump_clearance_ok_mask": float(
                env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX]
            ),
            "bucket_dump_area_relative_x_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
            ),
            "bucket_dump_area_relative_z_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
            ),
            "bucket_dump_area_footprint_outside_distance_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
            ),
        },
    }
