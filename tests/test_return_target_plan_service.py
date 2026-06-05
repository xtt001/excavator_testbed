from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.return_target_plan import (
    ReturnTargetExemplarSnapshot,
    ReturnTargetPlanBuild,
    ReturnTargetPlanService,
)


def test_should_hold_plan_matches_cycle_when_hold_enabled() -> None:
    service = ReturnTargetPlanService()

    assert service.should_hold_plan(
        hold_until_skill_exit=True,
        planned_cycle_id=3,
        cycle_index=3,
    )
    assert not service.should_hold_plan(
        hold_until_skill_exit=False,
        planned_cycle_id=3,
        cycle_index=3,
    )
    assert not service.should_hold_plan(
        hold_until_skill_exit=True,
        planned_cycle_id=2,
        cycle_index=3,
    )


def test_success_state_sets_return_target_and_pending_dig_plan() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    depth_profile = np.arange(12, dtype=np.float32)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    state = ReturnTargetPlanService.success_state(
        cycle_index=4,
        plan=ReturnTargetPlanBuild(
            token=token,
            raw_fields=raw_fields,
            return_start_envelope_tokens=envelope,
            source="return_target_operator_prior",
            fallback_reason="",
            corridor_id=7,
        ),
        exemplar=ReturnTargetExemplarSnapshot(
            depth_profile_token=depth_profile,
            state_exemplar_ids=["cell7_deep"],
            state_exemplar_distance=0.25,
        ),
    )

    np.testing.assert_allclose(state.return_target_tokens, token)
    np.testing.assert_allclose(state.return_start_envelope_tokens, envelope)
    assert state.return_target_token_source == "return_target_operator_prior"
    assert state.return_target_fallback_reason == ""
    assert state.return_target_planned_cycle_id == 4
    assert state.pending_dig_cut_cycle_id == 5
    assert state.pending_dig_cut_corridor_id == 7
    assert state.pending_dig_cut_raw_fields == raw_fields
    assert state.pending_dig_cut_raw_fields is not raw_fields
    np.testing.assert_allclose(state.pending_dig_cut_tokens, token)
    assert state.pending_dig_cut_tokens is not state.return_target_tokens
    np.testing.assert_allclose(state.pending_dig_depth_profile_tokens, depth_profile)
    assert state.pending_dig_state_exemplar_ids == ("cell7_deep",)
    assert state.pending_dig_state_exemplar_distance == pytest.approx(0.25)
    assert state.return_start_envelope_token_source is None


def test_failure_state_zeros_tokens_and_invalidates_pending_plan() -> None:
    state = ReturnTargetPlanService.failure_state(
        cycle_index=6,
        reason=RuntimeError("missing plan"),
    )

    assert state.return_target_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert state.return_start_envelope_tokens.shape == (
        RETURN_START_ENVELOPE_TOKEN_DIM,
    )
    assert float(np.max(np.abs(state.return_target_tokens))) == pytest.approx(0.0)
    assert float(np.max(np.abs(state.return_start_envelope_tokens))) == pytest.approx(
        0.0
    )
    assert state.return_target_token_source == "fallback_zero"
    assert state.return_start_envelope_token_source == "fallback_zero"
    assert state.return_target_fallback_reason == "missing plan"
    assert state.return_target_planned_cycle_id == 6
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_cut_tokens is None
    assert state.pending_dig_cut_corridor_id == -1
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == ()
    assert np.isnan(state.pending_dig_state_exemplar_distance)
