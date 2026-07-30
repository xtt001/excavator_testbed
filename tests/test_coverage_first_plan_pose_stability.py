from __future__ import annotations

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.primitive.coverage.config import (
    CoverageExecutionLibraryConfig,
    CoverageFirstPlanPoseStabilityConfig,
)
from testbed.planner.primitive.coverage.plan_readiness import (
    CoverageFirstPlanPoseStabilityService,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _pose_obs(
    policy: PrimitivePlannerACTPolicy,
    *,
    x_m: float,
    z_m: float,
) -> dict[str, np.ndarray]:
    env_state = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = x_m
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = -0.073
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = z_m
    return {
        "qpos": policy.scripted_bootstrap_target_qpos.copy(),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
    }


def test_pose_stability_service_rejects_single_frame_worktool_corner_flip() -> None:
    state = CoverageRuntimeState()
    service = CoverageFirstPlanPoseStabilityService(
        config=CoverageFirstPlanPoseStabilityConfig(
            enabled=True,
            hold_steps=3,
            max_step_delta_m=0.05,
            max_wait_steps=30,
        ),
        state=state,
    )

    assert service.observe((0.082, -0.073, -0.320)).ready is False
    assert service.observe((0.083, -0.073, -0.320)).ready is False
    spike = service.observe((0.084, -0.073, 0.120))
    assert spike.ready is False
    assert spike.spike_count == 1
    assert spike.hold_count == 1
    assert service.observe((0.084, -0.073, -0.320)).ready is False
    assert service.observe((0.084, -0.073, -0.320)).ready is False
    ready = service.observe((0.084, -0.073, -0.320))

    assert ready.ready is True
    assert ready.timed_out is False
    assert ready.hold_count == 3
    assert ready.wait_count == 6


def test_pose_stability_service_times_out_instead_of_waiting_forever() -> None:
    state = CoverageRuntimeState()
    service = CoverageFirstPlanPoseStabilityService(
        config=CoverageFirstPlanPoseStabilityConfig(
            enabled=True,
            hold_steps=3,
            max_step_delta_m=0.05,
            max_wait_steps=3,
        ),
        state=state,
    )

    assert service.observe((0.0, 0.0, -0.32)).timed_out is False
    assert service.observe((0.0, 0.0, 0.12)).timed_out is False
    result = service.observe((0.0, 0.0, -0.32))

    assert result.ready is False
    assert result.timed_out is True


def test_exact_tuple_bootstrap_waits_for_three_stable_pose_frames() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    policy.bootstrap_end_mode = "scripted_qpos"
    policy.scripted_bootstrap_target_qpos = np.asarray(
        [0.5, 0.39, 0.64, 0.186],
        dtype=np.float32,
    )
    policy.scripted_bootstrap_kp = 2.0
    policy.scripted_bootstrap_kd = 0.25
    policy.scripted_bootstrap_action_clip = 0.35
    policy.scripted_bootstrap_action_signs = None
    policy.scripted_bootstrap_qpos_tolerance = 0.02
    policy.scripted_bootstrap_qvel_abs_max = 0.08
    policy.scripted_bootstrap_hold_steps = 1
    policy.scripted_bootstrap_max_steps = 240
    policy.coverage_execution_library_config = (
        CoverageExecutionLibraryConfig.from_mapping(
            {
                "enabled": True,
                "path": "/tmp/library.json",
                "artifact_sha256": "a" * 64,
                "first_plan_pose_stability": {
                    "enabled": True,
                    "hold_steps": 3,
                    "max_step_delta_m": 0.05,
                    "max_wait_steps": 30,
                },
            }
        )
    )

    for x_m, z_m in (
        (0.082, -0.320),
        (0.083, -0.320),
        (0.084, 0.120),
        (0.084, -0.320),
        (0.084, -0.320),
    ):
        assert (
            policy._should_end_bootstrap(
                obs=_pose_obs(policy, x_m=x_m, z_m=z_m),
                boundary_event=None,
            )
            is False
        )
    assert (
        policy._should_end_bootstrap(
            obs=_pose_obs(policy, x_m=0.084, z_m=-0.320),
            boundary_event=None,
        )
        is True
    )

    state = policy._coverage_runtime_state()
    assert state.coverage_first_plan_pose_stability_ready is True
    assert state.coverage_first_plan_pose_stability_spike_count == 2
    assert state.coverage_first_plan_pose_stability_hold_count == 3
