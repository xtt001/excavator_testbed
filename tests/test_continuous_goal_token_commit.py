from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.primitive.coverage.continuous_goal import (
    ContinuousCoverageGoalService,
    ContinuousCutGoal,
    ContinuousGoalSupportDiagnostic,
)
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    PlannedReferenceQposSweep,
)
from testbed.planner.primitive.token.cut_goal_return_envelope import (
    CanonicalHandoffReference,
    CutGoalReturnEnvelopeService,
)
from testbed.planner.primitive.token.dig_planning import (
    validate_locked_continuous_pending_plan,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState


def _plan():
    goal = ContinuousCutGoal.create(
        target_cell_id=2,
        entry_xz_m=(0.2, 0.4),
        exit_xz_m=(0.5, 0.8),
        planned_depth_m=0.12,
        payload_intent_kg=45.0,
        effect_intent={"kind": "remove_soil"},
        terrain_signature={"schema": "terrain_signature_v1"},
    )
    qpos = (0.5, 0.4, 0.6, 0.2)
    sweep = PlannedReferenceQposSweep.create(
        goal_id=goal.goal_id,
        handoff_qpos=qpos,
        handoff_qvel=(0.0, 0.0, 0.0, 0.0),
        qpos_path=[qpos, (0.51, 0.41, 0.61, 0.21)],
        predictor_profile="test",
        predictor_version="1",
        predictor_code_sha256="c" * 64,
    )
    envelope = CutGoalReturnEnvelopeService().derive(
        goal=goal,
        terrain_local_depth_m=0.08,
        terrain_plane_depth_m=0.10,
        handoff_reference=CanonicalHandoffReference(
            goal_id=goal.goal_id,
            qpos=qpos,
            qpos_half_width=(0.03, 0.03, 0.03, 0.03),
            qvel_abs_max=0.10,
            spatial_half_width_norm=0.05,
            expected_contact=True,
            predictor_profile="test",
            predictor_version="1",
            predictor_code_sha256="c" * 64,
        ),
    )
    return ContinuousCoverageGoalService().lock_execution_plan(
        goal=goal,
        return_envelope=envelope,
        planned_qpos_sweep=sweep,
        support_ood=ContinuousGoalSupportDiagnostic(
            support_status="supported",
            whole_goal_distance=0.2,
        ),
    )


def _commit(state: PrimitiveTokenRuntimeState, plan, *, raw_fields=None) -> None:
    state.commit_return_plan(
        return_target_tokens=plan.dig_token,
        return_start_envelope_tokens=plan.return_envelope.token,
        return_start_envelope_token_source="continuous_cut_goal",
        return_start_envelope_use_prior_spatial_bounds=False,
        return_start_envelope_use_prior_qpos_bounds=False,
        return_target_token_source="continuous_goal_conditioned",
        return_target_fallback_reason="",
        return_target_planned_cycle_id=3,
        pending_dig_cut_cycle_id=4,
        pending_dig_cut_raw_fields=(
            dict(plan.raw_fields) if raw_fields is None else raw_fields
        ),
        pending_dig_cut_tokens=plan.dig_token,
        pending_dig_cut_corridor_id=2,
        pending_dig_execution_exemplar_id="",
        pending_dig_execution_raw_fields_sha256="",
        pending_dig_paired_return_primitive_episode_id=-1,
        pending_dig_paired_return_exemplar_id="",
        pending_dig_return_transition_artifact_sha256="",
        pending_dig_exact_start_contract_required=False,
        pending_dig_exact_return_envelope_valid_mask=None,
        pending_dig_depth_profile_tokens=None,
        pending_dig_state_exemplar_ids=[],
        pending_dig_state_exemplar_distance=float("nan"),
        pending_dig_locked_execution_plan=plan,
    )


def test_return_commit_atomically_locks_complete_continuous_execution_plan() -> None:
    state = PrimitiveTokenRuntimeState()
    plan = _plan()
    _commit(state, plan)

    assert state.pending_dig_locked_execution_plan is plan
    assert state.pending_dig_locked_execution_plan.goal_id == plan.goal_id
    np.testing.assert_allclose(
        state.return_start_envelope_tokens,
        plan.return_envelope.token,
    )
    assert state.pending_dig_execution_exemplar_id == ""
    assert state.pending_dig_paired_return_exemplar_id == ""


def test_continuous_plan_commit_rejects_goal_content_drift_atomically() -> None:
    state = PrimitiveTokenRuntimeState()
    plan = _plan()
    old_target = state.return_target_tokens.copy()

    with pytest.raises(ValueError, match="continuous locked plan"):
        _commit(
            state,
            plan,
            raw_fields={
                **dict(plan.raw_fields),
                "operator_entry_x_m": 99.0,
            },
        )

    assert state.pending_dig_locked_execution_plan is None
    np.testing.assert_array_equal(state.return_target_tokens, old_target)


def test_dig_consumption_rejects_post_commit_goal_drift() -> None:
    state = PrimitiveTokenRuntimeState()
    plan = _plan()
    _commit(state, plan)
    state.pending_dig_cut_raw_fields = {
        **dict(state.pending_dig_cut_raw_fields or {}),
        "operator_exit_z_m": -10.0,
    }

    with pytest.raises(ValueError, match="continuous_goal_contract_invalid"):
        validate_locked_continuous_pending_plan(state)
