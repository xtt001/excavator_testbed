from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from testbed.planner.primitive.coverage.continuous_goal import (
    ContinuousCoverageGoalService,
    ContinuousCutGoal,
    ContinuousGoalContractError,
    ContinuousGoalSupportDiagnostic,
    LockedCutGoalExecutionPlan,
)
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    PlannedReferenceQposSweep,
)
from testbed.planner.primitive.token.cut_goal_return_envelope import (
    CanonicalHandoffReference,
    CutGoalReturnEnvelopeService,
)


def _goal(
    *,
    effect_intent: dict[str, object] | None = None,
    terrain_signature: dict[str, object] | None = None,
) -> ContinuousCutGoal:
    return ContinuousCutGoal.create(
        target_cell_id=7,
        entry_xz_m=(1.0, 2.0),
        exit_xz_m=(4.0, 6.0),
        planned_depth_m=0.12,
        payload_intent_kg=45.0,
        effect_intent=effect_intent
        or {"kind": "remove_soil", "target_mass_kg": 45.0},
        terrain_signature=terrain_signature
        or {"schema": "terrain_signature_v1", "samples": [0.1, 0.2]},
    )


def _sweep(goal: ContinuousCutGoal) -> PlannedReferenceQposSweep:
    return PlannedReferenceQposSweep.create(
        goal_id=goal.goal_id,
        handoff_qpos=(0.1, 0.2, 0.3, 0.4),
        handoff_qvel=(0.0, 0.0, 0.0, 0.0),
        qpos_path=[
            [0.1, 0.2, 0.3, 0.4],
            [0.2, 0.3, 0.4, 0.5],
        ],
        predictor_profile="test_continuous_reference",
        predictor_version="1",
        predictor_code_sha256="a" * 64,
    )


def _return_envelope(goal: ContinuousCutGoal):
    return CutGoalReturnEnvelopeService().derive(
        goal=goal,
        terrain_local_depth_m=0.02,
        terrain_plane_depth_m=0.03,
        handoff_reference=CanonicalHandoffReference(
            goal_id=goal.goal_id,
            qpos=(0.1, 0.2, 0.3, 0.4),
            qpos_half_width=(0.02, 0.02, 0.02, 0.02),
            qvel_abs_max=0.1,
            spatial_half_width_norm=0.2,
            expected_contact=False,
            predictor_profile="test_continuous_reference",
            predictor_version="1",
            predictor_code_sha256="a" * 64,
        ),
    )


def test_continuous_goal_derives_geometry_and_has_canonical_identity() -> None:
    first = _goal(
        effect_intent={"target_mass_kg": 45.0, "kind": "remove_soil"},
        terrain_signature={
            "samples": [0.1, 0.2],
            "schema": "terrain_signature_v1",
        },
    )
    second = _goal()

    assert first.direction_xz == pytest.approx((0.6, 0.8))
    assert first.cut_length_m == pytest.approx(5.0)
    assert first.goal_id == second.goal_id
    assert len(first.goal_id) == 64
    assert first.as_dict()["direction_xz"] == pytest.approx([0.6, 0.8])


def test_continuous_goal_rejects_written_or_drifting_derived_geometry() -> None:
    payload = _goal().as_dict()
    payload["direction_xz"] = [1.0, 0.0]

    with pytest.raises(ContinuousGoalContractError, match="direction_xz"):
        ContinuousCutGoal.from_mapping(payload)

    payload = _goal().as_dict()
    payload["cut_length_m"] = 99.0
    with pytest.raises(ContinuousGoalContractError, match="cut_length_m"):
        ContinuousCutGoal.from_mapping(payload)

    with pytest.raises(TypeError):
        ContinuousCutGoal.create(
            target_cell_id=7,
            entry_xz_m=(1.0, 2.0),
            exit_xz_m=(4.0, 6.0),
            direction_xz=(0.6, 0.8),  # type: ignore[call-arg]
            planned_depth_m=0.12,
            payload_intent_kg=45.0,
            effect_intent={"kind": "remove_soil"},
            terrain_signature={"schema": "terrain_signature_v1"},
        )


def test_continuous_goal_has_no_episode_runtime_binding() -> None:
    with pytest.raises(ContinuousGoalContractError, match="episode"):
        _goal(terrain_signature={"source_episode_id": 168})

    assert "episode" not in repr(_goal()).lower()


def test_continuous_goal_and_locked_plan_are_deeply_immutable() -> None:
    goal = _goal()
    with pytest.raises(FrozenInstanceError):
        goal.target_cell_id = 8  # type: ignore[misc]
    with pytest.raises(TypeError):
        goal.effect_intent["kind"] = "snap_to_expert"  # type: ignore[index]

    diagnostic = ContinuousGoalSupportDiagnostic(
        support_status="ood",
        whole_goal_distance=0.4,
        ood_reasons=("terrain_signature_outside_support",),
    )
    plan = ContinuousCoverageGoalService().lock_execution_plan(
        goal=goal,
        return_envelope=_return_envelope(goal),
        planned_qpos_sweep=_sweep(goal),
        support_ood=diagnostic,
    )

    assert isinstance(plan, LockedCutGoalExecutionPlan)
    assert plan.goal_id == goal.goal_id
    assert plan.planned_qpos_path_sha256 == plan.planned_qpos_sweep.path_sha256
    assert plan.dig_token.shape == (10,)
    assert plan.dig_token.dtype == np.float32
    assert plan.dig_token.flags.writeable is False
    assert plan.raw_fields["operator_cut_direction_x"] == pytest.approx(0.6)
    assert plan.raw_fields["operator_cut_length_m"] == pytest.approx(5.0)
    assert "episode_id" not in plan.raw_fields
    assert plan.support_ood.episode_snap_applied is False
    with pytest.raises(ValueError):
        plan.dig_token[0] = 0.0


def test_locked_plan_fails_closed_on_goal_identity_drift() -> None:
    goal = _goal()
    other_goal = ContinuousCutGoal.create(
        target_cell_id=8,
        entry_xz_m=(1.0, 2.0),
        exit_xz_m=(4.0, 6.0),
        planned_depth_m=0.12,
        payload_intent_kg=45.0,
        effect_intent={"kind": "remove_soil", "target_mass_kg": 45.0},
        terrain_signature={"schema": "terrain_signature_v1"},
    )

    with pytest.raises(ContinuousGoalContractError, match="goal identity"):
        ContinuousCoverageGoalService().lock_execution_plan(
            goal=goal,
            return_envelope=_return_envelope(other_goal),
            planned_qpos_sweep=_sweep(goal),
            support_ood=ContinuousGoalSupportDiagnostic(
            support_status="supported"
            ),
        )
