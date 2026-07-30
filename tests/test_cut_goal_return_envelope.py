from __future__ import annotations

import inspect

import numpy as np
import pytest

from testbed.planner.primitive.coverage.continuous_goal import ContinuousCutGoal
from testbed.planner.primitive.token.cut_goal_return_envelope import (
    CUT_GOAL_RETURN_ENVELOPE_SCHEMA,
    CanonicalHandoffReference,
    CutGoalReturnEnvelopeContractError,
    CutGoalReturnEnvelopeService,
)


def _goal() -> ContinuousCutGoal:
    return ContinuousCutGoal.create(
        target_cell_id=2,
        entry_xz_m=(1.2, 2.4),
        exit_xz_m=(2.2, 2.4),
        planned_depth_m=0.12,
        payload_intent_kg=45.0,
        effect_intent={"kind": "remove_soil", "target_mass_kg": 45.0},
        terrain_signature={"schema": "terrain_signature_v1"},
    )


def _reference(goal: ContinuousCutGoal) -> CanonicalHandoffReference:
    return CanonicalHandoffReference(
        goal_id=goal.goal_id,
        qpos=(0.1, 0.2, 0.3, 0.4),
        qpos_half_width=(0.02, 0.03, 0.04, 0.05),
        qvel_abs_max=0.1,
        spatial_half_width_norm=0.2,
        expected_contact=False,
        predictor_profile="continuous_goal_reference_v1",
        predictor_version="1",
        predictor_code_sha256="a" * 64,
    )


def test_return_envelope_is_complete_goal_locked_and_prior_independent() -> None:
    goal = _goal()
    result = CutGoalReturnEnvelopeService().derive(
        goal=goal,
        terrain_local_depth_m=0.03,
        terrain_plane_depth_m=0.01,
        handoff_reference=_reference(goal),
    )

    assert result.schema == CUT_GOAL_RETURN_ENVELOPE_SCHEMA
    assert result.goal_id == goal.goal_id
    assert result.derivation == "continuous_cut_goal"
    assert result.token.shape == (18,)
    assert result.token.dtype == np.float32
    assert result.token.flags.writeable is False
    np.testing.assert_allclose(result.token[0:2], [0.6, 1.0])
    np.testing.assert_allclose(result.token[2], 0.03)
    np.testing.assert_allclose(result.token[3], 0.2)
    np.testing.assert_allclose(result.token[4:6], [0.01, 0.03])
    np.testing.assert_allclose(result.token[7:11], [0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(result.token[11:15], [0.02, 0.03, 0.04, 0.05])
    np.testing.assert_allclose(result.token[15], 0.1)
    assert result.token[16] == 1.0
    assert result.token[17] == 1.0
    assert result.terrain_local_depth_m == pytest.approx(0.03)
    assert result.terrain_plane_depth_m == pytest.approx(0.01)
    assert result.source_uses_prior is False
    assert result.source_uses_live_current_fallback is False
    assert result.source_uses_relocate_conditioning is False


def test_return_envelope_rejects_missing_nonfinite_depth_or_qpos() -> None:
    goal = _goal()
    with pytest.raises(
        CutGoalReturnEnvelopeContractError,
        match="terrain_local_depth_m",
    ):
        CutGoalReturnEnvelopeService().derive(
            goal=goal,
            terrain_local_depth_m=float("nan"),
            terrain_plane_depth_m=0.01,
            handoff_reference=_reference(goal),
        )

    bad_reference = CanonicalHandoffReference(
        goal_id=goal.goal_id,
        qpos=(0.1, float("nan"), 0.3, 0.4),
        qpos_half_width=(0.02, 0.03, 0.04, 0.05),
        qvel_abs_max=0.1,
        spatial_half_width_norm=0.2,
        expected_contact=False,
        predictor_profile="continuous_goal_reference_v1",
        predictor_version="1",
        predictor_code_sha256="a" * 64,
    )
    with pytest.raises(CutGoalReturnEnvelopeContractError, match="qpos"):
        CutGoalReturnEnvelopeService().derive(
            goal=goal,
            terrain_local_depth_m=0.03,
            terrain_plane_depth_m=0.01,
            handoff_reference=bad_reference,
        )


def test_return_envelope_rejects_goal_identity_drift() -> None:
    goal = _goal()
    reference = CanonicalHandoffReference(
        goal_id="b" * 64,
        qpos=(0.1, 0.2, 0.3, 0.4),
        qpos_half_width=(0.02, 0.03, 0.04, 0.05),
        qvel_abs_max=0.1,
        spatial_half_width_norm=0.2,
        expected_contact=False,
        predictor_profile="continuous_goal_reference_v1",
        predictor_version="1",
        predictor_code_sha256="a" * 64,
    )
    with pytest.raises(
        CutGoalReturnEnvelopeContractError,
        match="goal identity",
    ):
        CutGoalReturnEnvelopeService().derive(
            goal=goal,
            terrain_local_depth_m=0.03,
            terrain_plane_depth_m=0.01,
            handoff_reference=reference,
        )


def test_return_envelope_api_has_no_legacy_fallback_inputs() -> None:
    parameters = inspect.signature(CutGoalReturnEnvelopeService.derive).parameters
    forbidden = {
        "cell_id",
        "global_prior",
        "live_current",
        "relocate_token",
        "expert_return_token",
        "episode_id",
    }

    assert forbidden.isdisjoint(parameters)
