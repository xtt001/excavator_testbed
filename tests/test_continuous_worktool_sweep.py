from __future__ import annotations

import hashlib

import numpy as np
import pytest

from testbed.planner.primitive.coverage.continuous_goal import ContinuousCutGoal
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    CONTINUOUS_ACT_TRACKING_MARGIN_M,
    CONTINUOUS_GOAL_3D_PREDICTOR_MISSING,
    CONTINUOUS_HARD_CLEARANCE_M,
    CONTINUOUS_POSE_INTERPOLATION_BOUND_M,
    CONTINUOUS_QPOS_ORDER,
    ContinuousGoalQposSweepContractError,
    ContinuousGoalQposSweepPrediction,
    ContinuousWorktoolSweepMargins,
    PlannedReferenceQposSweep,
    predict_continuous_goal_qpos_sweep,
)


def _goal() -> ContinuousCutGoal:
    return ContinuousCutGoal.create(
        target_cell_id=2,
        entry_xz_m=(0.2, 0.4),
        exit_xz_m=(0.5, 0.8),
        planned_depth_m=0.12,
        payload_intent_kg=45.0,
        effect_intent={"kind": "remove_soil", "target_mass_kg": 45.0},
        terrain_signature={"schema": "terrain_signature_v1"},
    )


def _kwargs(goal: ContinuousCutGoal) -> dict[str, object]:
    return {
        "goal_id": goal.goal_id,
        "handoff_qpos": [0.1, 0.2, 0.3, 0.4],
        "handoff_qvel": [0.0, 0.01, 0.02, 0.03],
        "qpos_path": [
            [0.1, 0.2, 0.3, 0.4],
            [0.4, 0.3, 0.2, 0.1],
        ],
        "predictor_profile": "continuous_goal_reference_v1",
        "predictor_version": "1",
        "predictor_code_sha256": "a" * 64,
    }


def test_planned_qpos_sweep_hash_is_float32_little_endian_row_major() -> None:
    goal = _goal()
    sweep = PlannedReferenceQposSweep.create(**_kwargs(goal))
    expected = hashlib.sha256(
        np.asarray(
            _kwargs(goal)["qpos_path"],
            dtype="<f4",
            order="C",
        ).tobytes(order="C")
    ).hexdigest()

    assert sweep.qpos_order == CONTINUOUS_QPOS_ORDER
    assert sweep.path_sha256 == expected
    assert sweep.qpos_path.flags.writeable is False
    assert sweep.handoff_qpos == pytest.approx((0.1, 0.2, 0.3, 0.4))
    assert sweep.as_dict()["goal_sha256"] == goal.goal_id


def test_planned_qpos_sweep_requires_actual_handoff_as_path_start() -> None:
    kwargs = _kwargs(_goal())
    kwargs["qpos_path"] = [
        [0.100002, 0.2, 0.3, 0.4],
        [0.4, 0.3, 0.2, 0.1],
    ]
    with pytest.raises(
        ContinuousGoalQposSweepContractError,
        match="path\\[0\\].*1e-06",
    ):
        PlannedReferenceQposSweep.create(**kwargs)


def test_missing_predictor_returns_only_the_fixed_blocker() -> None:
    result = predict_continuous_goal_qpos_sweep(
        predictor=None,
        live_handoff_state={
            "qpos": [0.1, 0.2, 0.3, 0.4],
            "qvel": [0.0, 0.0, 0.0, 0.0],
        },
        goal=_goal(),
    )

    assert isinstance(result, ContinuousGoalQposSweepPrediction)
    assert result.status == "blocked"
    assert result.blocker == CONTINUOUS_GOAL_3D_PREDICTOR_MISSING
    assert result.sweep is None
    assert result.act_inference_allowed is False


def test_predictor_receives_live_handoff_and_whole_goal_without_snap() -> None:
    goal = _goal()

    class Predictor:
        def __init__(self) -> None:
            self.received: tuple[object, object] | None = None

        def predict(self, live_handoff_state, whole_goal):
            self.received = (live_handoff_state, whole_goal)
            return PlannedReferenceQposSweep.create(**_kwargs(whole_goal))

    predictor = Predictor()
    live = {
        "qpos": [0.1, 0.2, 0.3, 0.4],
        "qvel": [0.0, 0.01, 0.02, 0.03],
    }
    result = predict_continuous_goal_qpos_sweep(
        predictor=predictor,
        live_handoff_state=live,
        goal=goal,
    )

    assert predictor.received == (live, goal)
    assert result.status == "passed"
    assert result.blocker == ""
    assert result.sweep is not None
    assert result.sweep.goal_id == goal.goal_id
    assert result.act_inference_allowed is True


def test_continuous_margins_are_python_owned_and_locked() -> None:
    margins = ContinuousWorktoolSweepMargins()
    assert margins.act_tracking_margin_m == CONTINUOUS_ACT_TRACKING_MARGIN_M == 0.05
    assert (
        margins.pose_interpolation_bound_m
        == CONTINUOUS_POSE_INTERPOLATION_BOUND_M
        == 0.01
    )
    assert margins.hard_clearance_m == CONTINUOUS_HARD_CLEARANCE_M == 0.24

    with pytest.raises(
        ContinuousGoalQposSweepContractError,
        match="locked",
    ):
        ContinuousWorktoolSweepMargins(hard_clearance_m=0.30)


def test_predictor_goal_identity_drift_fails_closed() -> None:
    goal = _goal()

    class Predictor:
        def predict(self, live_handoff_state, whole_goal):
            kwargs = _kwargs(whole_goal)
            kwargs["goal_id"] = "b" * 64
            return PlannedReferenceQposSweep.create(**kwargs)

    with pytest.raises(
        ContinuousGoalQposSweepContractError,
        match="goal identity",
    ):
        predict_continuous_goal_qpos_sweep(
            predictor=Predictor(),
            live_handoff_state={
                "qpos": [0.1, 0.2, 0.3, 0.4],
                "qvel": [0.0, 0.0, 0.0, 0.0],
            },
            goal=goal,
        )
