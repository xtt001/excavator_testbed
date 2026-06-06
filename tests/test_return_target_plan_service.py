from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    CUT_DEPTH_SEMANTIC_IDX,
    CUT_PAYLOAD_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.return_target_plan import (
    PENDING_RETURN_TARGET_ACTIVATION_FACT_FIELDS,
    RETURN_TARGET_CONDITIONING_STATUS_FIELDS,
    PendingDigCutPlanState,
    PendingReturnTargetActivationFacts,
    ReturnRelocateObservationTokenResult,
    ReturnStartEnvelopeObservationTokenResult,
    ReturnTargetConditioningRuntimeState,
    ReturnTargetConditioningStatusState,
    ReturnTargetDigCutBuildContext,
    ReturnTargetDigCutBuildFacts,
    ReturnTargetDigCutBuildResult,
    ReturnTargetDigCutBuildResultConfig,
    ReturnTargetExemplarSnapshot,
    ReturnTargetObservationTokenResult,
    ReturnTargetPlanAttempt,
    ReturnTargetPlanBuild,
    ReturnTargetPlanBuildAttemptFacts,
    ReturnTargetPlanBuildFacts,
    ReturnTargetPlanCycleConfig,
    ReturnTargetPlanCycleFacts,
    ReturnTargetPlanRuntimeUpdate,
    ReturnTargetPlanService,
    ReturnTargetPlanState,
    build_pending_return_target_activation_facts,
    build_pending_return_target_activation_facts_from_mapping,
    build_return_target_conditioning_status_state_from_mapping,
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


@pytest.mark.parametrize(
    (
        "enabled",
        "hold_until_skill_exit",
        "planned_cycle_id",
        "cycle_index",
        "expected_action",
        "expected_should_build",
    ),
    [
        (False, True, 3, 3, "disabled", False),
        (True, True, 3, 3, "hold_existing", False),
        (True, False, 3, 3, "build", True),
        (True, True, 2, 3, "build", True),
    ],
)
def test_cycle_decision_preserves_disabled_hold_build_order(
    enabled: bool,
    hold_until_skill_exit: bool,
    planned_cycle_id: int,
    cycle_index: int,
    expected_action: str,
    expected_should_build: bool,
) -> None:
    decision = ReturnTargetPlanService().cycle_decision(
        config=ReturnTargetPlanCycleConfig(
            enabled=enabled,
            hold_until_skill_exit=hold_until_skill_exit,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=planned_cycle_id,
            cycle_index=cycle_index,
        ),
    )

    assert decision.action == expected_action
    assert decision.should_build is expected_should_build


def test_plan_request_projects_cycle_decision_exemplar_and_attempts() -> None:
    service = ReturnTargetPlanService()
    depth_profile = np.arange(12, dtype=np.float64)
    request = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=4,
        ),
        depth_profile_token=depth_profile,
        state_exemplar_ids=["cell7_deep"],
        state_exemplar_distance=0.25,
    )

    assert request.decision.action == "build"
    assert request.should_build is True
    assert request.cycle_index == 4
    assert request.exemplar.depth_profile_token is depth_profile
    assert request.exemplar.state_exemplar_ids == ["cell7_deep"]
    assert request.exemplar.state_exemplar_distance == pytest.approx(0.25)

    plan = ReturnTargetPlanBuild(
        token=np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
        raw_fields={"operator_entry_x_m": 0.5},
        return_start_envelope_tokens=np.zeros(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float32,
        ),
        source="return_target_operator_prior",
        fallback_reason="",
        corridor_id=7,
    )
    success = request.success_attempt(plan)
    assert success.cycle_index == 4
    assert success.plan is plan
    assert success.failure_reason is None

    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    envelope = np.ones(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    success_from_facts = request.success_attempt_from_facts(
        ReturnTargetPlanBuildFacts(
            token=depth_profile,
            raw_fields=raw_fields,
            return_start_envelope_tokens=envelope,
            source="return_target_operator_prior",
            fallback_reason="",
            corridor_id=7,
        )
    )
    assert success_from_facts.cycle_index == 4
    assert success_from_facts.failure_reason is None
    assert success_from_facts.plan is not None
    assert success_from_facts.plan.token is depth_profile
    assert success_from_facts.plan.raw_fields is raw_fields
    assert success_from_facts.plan.return_start_envelope_tokens is envelope
    assert success_from_facts.plan.source == "return_target_operator_prior"
    assert success_from_facts.plan.fallback_reason == ""
    assert success_from_facts.plan.corridor_id == 7

    failure_reason = RuntimeError("missing plan")
    failure = request.failure_attempt(failure_reason)
    assert failure.cycle_index == 4
    assert failure.plan is None
    assert failure.failure_reason is failure_reason

    held = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=True,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=4,
            cycle_index=4,
        ),
    )
    assert held.decision.action == "hold_existing"
    assert held.should_build is False


def test_plan_request_from_runtime_matches_explicit_cycle_request() -> None:
    service = ReturnTargetPlanService()
    depth_profile = np.arange(12, dtype=np.float64)
    exemplar_ids = ["cell7_deep"]

    actual = service.plan_request_from_runtime(
        enabled=np.int64(1),
        hold_until_skill_exit=np.int64(0),
        planned_cycle_id=np.int64(-1),
        cycle_index=np.int64(4),
        depth_profile_token=depth_profile,
        state_exemplar_ids=exemplar_ids,
        state_exemplar_distance=np.float64(0.25),
    )
    expected = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=4,
        ),
        depth_profile_token=depth_profile,
        state_exemplar_ids=exemplar_ids,
        state_exemplar_distance=0.25,
    )

    assert actual.decision == expected.decision
    assert actual.cycle_index == expected.cycle_index
    assert actual.exemplar.depth_profile_token is depth_profile
    assert actual.exemplar.state_exemplar_ids is exemplar_ids
    assert actual.exemplar.state_exemplar_distance == pytest.approx(
        expected.exemplar.state_exemplar_distance
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


def test_state_from_success_attempt_matches_success_state() -> None:
    service = ReturnTargetPlanService()
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    depth_profile = np.arange(12, dtype=np.float32)
    plan = ReturnTargetPlanBuild(
        token=token,
        raw_fields={"operator_entry_x_m": 0.5, "operator_cut_valid": 1},
        return_start_envelope_tokens=envelope,
        source="return_target_operator_prior",
        fallback_reason="",
        corridor_id=7,
    )
    exemplar = ReturnTargetExemplarSnapshot(
        depth_profile_token=depth_profile,
        state_exemplar_ids=["cell7_deep"],
        state_exemplar_distance=0.25,
    )

    state = service.state_from_attempt(
        ReturnTargetPlanAttempt.success(cycle_index=4, plan=plan),
        exemplar=exemplar,
    )

    np.testing.assert_allclose(state.return_target_tokens, token)
    np.testing.assert_allclose(state.return_start_envelope_tokens, envelope)
    assert state.return_target_token_source == "return_target_operator_prior"
    assert state.pending_dig_cut_cycle_id == 5
    assert state.pending_dig_cut_corridor_id == 7
    np.testing.assert_allclose(state.pending_dig_depth_profile_tokens, depth_profile)
    assert state.pending_dig_state_exemplar_ids == ("cell7_deep",)


def test_state_from_build_attempt_success_matches_request_attempt_path() -> None:
    service = ReturnTargetPlanService()
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    depth_profile = np.arange(12, dtype=np.float64)
    request = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=4,
        ),
        depth_profile_token=depth_profile,
        state_exemplar_ids=["cell7_deep"],
        state_exemplar_distance=0.25,
    )
    build_facts = ReturnTargetPlanBuildFacts(
        token=token,
        raw_fields=raw_fields,
        return_start_envelope_tokens=envelope,
        source="return_target_operator_prior",
        fallback_reason="",
        corridor_id=7,
    )

    state = service.state_from_build_attempt(
        ReturnTargetPlanBuildAttemptFacts(
            request=request,
            build_facts=build_facts,
        )
    )

    np.testing.assert_allclose(state.return_target_tokens, token)
    assert state.return_target_tokens.dtype == np.float32
    np.testing.assert_allclose(state.return_start_envelope_tokens, envelope)
    assert state.return_start_envelope_tokens.dtype == np.float32
    assert state.return_target_token_source == "return_target_operator_prior"
    assert state.return_target_fallback_reason == ""
    assert state.return_target_planned_cycle_id == 4
    assert state.pending_dig_cut_cycle_id == 5
    assert state.pending_dig_cut_corridor_id == 7
    assert state.pending_dig_cut_raw_fields == raw_fields
    np.testing.assert_allclose(state.pending_dig_depth_profile_tokens, depth_profile)
    assert state.pending_dig_state_exemplar_ids == ("cell7_deep",)
    assert state.pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_state_from_build_attempt_failure_preserves_fallback_zero_state() -> None:
    service = ReturnTargetPlanService()
    request = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=6,
        ),
        depth_profile_token=np.arange(12, dtype=np.float32),
        state_exemplar_ids=["cell7_deep"],
        state_exemplar_distance=0.25,
    )

    state = service.state_from_build_attempt(
        ReturnTargetPlanBuildAttemptFacts(
            request=request,
            failure_reason=RuntimeError("bad envelope"),
        )
    )

    assert state.return_target_token_source == "fallback_zero"
    assert state.return_start_envelope_token_source == "fallback_zero"
    assert state.return_target_fallback_reason == "bad envelope"
    assert state.return_target_planned_cycle_id == 6
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_cut_tokens is None
    assert state.pending_dig_cut_corridor_id == -1
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == ()
    assert np.isnan(state.pending_dig_state_exemplar_distance)


def test_plan_build_facts_from_parts_preserves_payload_identity_and_projection() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    facts = ReturnTargetPlanService.plan_build_facts_from_parts(
        token=token,
        raw_fields=raw_fields,
        return_start_envelope_tokens=envelope,
        source=123,
        fallback_reason=456,
        corridor_id=np.int64(7),
    )

    assert isinstance(facts, ReturnTargetPlanBuildFacts)
    assert facts.token is token
    assert facts.raw_fields is raw_fields
    assert facts.return_start_envelope_tokens is envelope
    assert facts.source == "123"
    assert facts.fallback_reason == "456"
    assert facts.corridor_id == 7


def test_state_from_build_facts_callback_success_matches_build_attempt_path() -> None:
    service = ReturnTargetPlanService()
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    calls: list[str] = []
    request = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=4,
        ),
        state_exemplar_ids=["cell7_deep"],
        state_exemplar_distance=0.25,
    )

    def build_facts() -> ReturnTargetPlanBuildFacts:
        calls.append("build")
        return ReturnTargetPlanBuildFacts(
            token=token,
            raw_fields=raw_fields,
            return_start_envelope_tokens=envelope,
            source="return_target_operator_prior",
            fallback_reason="",
            corridor_id=7,
        )

    state = service.state_from_build_facts_callback(
        request=request,
        build_facts=build_facts,
    )

    assert calls == ["build"]
    np.testing.assert_allclose(state.return_target_tokens, token)
    assert state.return_target_token_source == "return_target_operator_prior"
    assert state.return_target_planned_cycle_id == 4
    assert state.pending_dig_cut_cycle_id == 5
    assert state.pending_dig_cut_corridor_id == 7
    assert state.pending_dig_cut_raw_fields == raw_fields
    assert state.pending_dig_state_exemplar_ids == ("cell7_deep",)
    assert state.pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_state_from_build_facts_callback_failure_preserves_fallback_zero_state() -> None:
    service = ReturnTargetPlanService()
    request = service.plan_request(
        config=ReturnTargetPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=ReturnTargetPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=6,
        ),
        state_exemplar_ids=["unused"],
        state_exemplar_distance=0.25,
    )

    def build_facts() -> ReturnTargetPlanBuildFacts:
        raise RuntimeError("bad envelope")

    state = service.state_from_build_facts_callback(
        request=request,
        build_facts=build_facts,
    )

    assert state.return_target_token_source == "fallback_zero"
    assert state.return_start_envelope_token_source == "fallback_zero"
    assert state.return_target_fallback_reason == "bad envelope"
    assert state.return_target_planned_cycle_id == 6
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_cut_tokens is None
    assert state.pending_dig_cut_corridor_id == -1
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == ()
    assert np.isnan(state.pending_dig_state_exemplar_distance)


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


def test_pending_plan_state_from_return_target_state_preserves_projection() -> None:
    service = ReturnTargetPlanService()
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    depth_profile = np.arange(12, dtype=np.float32)
    state = ReturnTargetPlanState(
        return_target_tokens=token,
        return_start_envelope_tokens=envelope,
        return_target_token_source="return_target_operator_prior",
        return_target_fallback_reason="",
        return_target_planned_cycle_id=4,
        pending_dig_cut_cycle_id=np.int64(5),
        pending_dig_cut_raw_fields={"operator_entry_x_m": 0.5},
        pending_dig_cut_tokens=token,
        pending_dig_cut_corridor_id=np.int64(7),
        pending_dig_depth_profile_tokens=depth_profile,
        pending_dig_state_exemplar_ids=["cell7_deep"],
        pending_dig_state_exemplar_distance=np.float64(0.25),
    )

    pending = service.pending_plan_state_from_return_target_state(state)

    assert pending.cycle_id == 5
    assert pending.corridor_id == 7
    assert pending.raw_fields is state.pending_dig_cut_raw_fields
    assert pending.tokens is token
    assert pending.depth_profile_tokens is depth_profile
    assert pending.state_exemplar_ids == ("cell7_deep",)
    assert pending.state_exemplar_distance == pytest.approx(0.25)


def test_runtime_update_from_plan_state_projects_runtime_fields_and_pending_plan() -> None:
    service = ReturnTargetPlanService()
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    envelope_tokens = np.arange(
        RETURN_START_ENVELOPE_TOKEN_DIM,
        dtype=np.float64,
    )
    pending_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0
    state = ReturnTargetPlanState(
        return_target_tokens=target_tokens,
        return_start_envelope_tokens=envelope_tokens,
        return_target_token_source=123,
        return_target_fallback_reason=456,
        return_target_planned_cycle_id=np.int64(4),
        pending_dig_cut_cycle_id=np.int64(5),
        pending_dig_cut_raw_fields={"operator_entry_x_m": 0.5},
        pending_dig_cut_tokens=pending_tokens,
        pending_dig_cut_corridor_id=np.int64(7),
        pending_dig_depth_profile_tokens=None,
        pending_dig_state_exemplar_ids=["cell7_deep"],
        pending_dig_state_exemplar_distance=np.float64(0.25),
        return_start_envelope_token_source=None,
    )

    update = service.runtime_update_from_plan_state(state)

    assert isinstance(update, ReturnTargetPlanRuntimeUpdate)
    assert update.return_target_tokens.dtype == np.float32
    assert update.return_start_envelope_tokens.dtype == np.float32
    np.testing.assert_allclose(update.return_target_tokens, target_tokens)
    np.testing.assert_allclose(update.return_start_envelope_tokens, envelope_tokens)
    assert update.return_target_token_source == "123"
    assert update.return_start_envelope_token_source is None
    assert update.return_target_fallback_reason == "456"
    assert update.return_target_planned_cycle_id == 4
    assert isinstance(update.pending_plan, PendingDigCutPlanState)
    assert update.pending_plan.cycle_id == 5
    assert update.pending_plan.corridor_id == 7
    assert update.pending_plan.raw_fields == {"operator_entry_x_m": 0.5}
    assert update.pending_plan.tokens is pending_tokens
    assert update.pending_plan.depth_profile_tokens is None
    assert update.pending_plan.state_exemplar_ids == ("cell7_deep",)
    assert update.pending_plan.state_exemplar_distance == pytest.approx(0.25)


def test_pending_plan_state_from_conditioning_state_preserves_projection() -> None:
    service = ReturnTargetPlanService()
    target = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    relocate = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    pending_token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 20.0
    profile = np.arange(12, dtype=np.float32)
    state = ReturnTargetConditioningRuntimeState(
        target_tokens=target,
        target_token_injected=False,
        target_token_source="return_target_operator_prior",
        target_fallback_reason="",
        relocate_tokens=relocate,
        relocate_token_injected=False,
        start_envelope_tokens=envelope,
        start_envelope_token_injected=False,
        start_envelope_token_source="qc6_return_start_envelope_cell_7",
        start_envelope_use_prior_spatial_bounds=True,
        start_envelope_use_prior_qpos_bounds=True,
        planned_cycle_id=4,
        pending_dig_cut_cycle_id=np.int64(5),
        pending_dig_cut_corridor_id=np.int64(7),
        pending_dig_cut_raw_fields={"operator_entry_x_m": 0.5},
        pending_dig_cut_tokens=pending_token,
        pending_dig_depth_profile_tokens=profile,
        pending_dig_state_exemplar_ids=["cell7_deep"],
        pending_dig_state_exemplar_distance=np.float64(0.25),
    )

    pending = service.pending_plan_state_from_conditioning_state(state)

    assert pending.cycle_id == 5
    assert pending.corridor_id == 7
    assert pending.raw_fields is state.pending_dig_cut_raw_fields
    assert pending.tokens is pending_token
    assert pending.depth_profile_tokens is profile
    assert pending.state_exemplar_ids == ("cell7_deep",)
    assert pending.state_exemplar_distance == pytest.approx(0.25)


def test_state_from_failure_attempt_matches_failure_state() -> None:
    state = ReturnTargetPlanService().state_from_attempt(
        ReturnTargetPlanAttempt.failure(
            cycle_index=6,
            reason=RuntimeError("missing plan"),
        ),
        exemplar=ReturnTargetExemplarSnapshot(
            depth_profile_token=np.ones(12, dtype=np.float32),
            state_exemplar_ids=["unused"],
            state_exemplar_distance=0.25,
        ),
    )

    assert state.return_target_token_source == "fallback_zero"
    assert state.return_start_envelope_token_source == "fallback_zero"
    assert state.return_target_fallback_reason == "missing plan"
    assert state.return_target_planned_cycle_id == 6
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == ()


def test_pending_activation_sets_dig_cut_and_coverage_restore_values() -> None:
    token = np.linspace(0.0, 1.0, RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    profile = np.arange(12, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    activation = ReturnTargetPlanService.pending_activation(
        PendingReturnTargetActivationFacts(
            pending_dig_cut_tokens=token,
            pending_dig_cut_raw_fields=raw_fields,
            pending_dig_cut_corridor_id=7,
            pending_dig_depth_profile_tokens=profile,
            pending_dig_state_exemplar_ids=["cell7_deep"],
            pending_dig_state_exemplar_distance=0.25,
            raw_fields_in_prior_range=True,
            cycle_start_deposit_kg=12.5,
        )
    )

    np.testing.assert_allclose(activation.dig_cut_tokens, token)
    assert activation.dig_cut_tokens.dtype == np.float32
    assert activation.dig_cut_tokens is not token
    assert activation.dig_cut_token_source == "pending_return_target"
    assert activation.dig_cut_fallback_reason == ""
    assert activation.dig_cut_token_in_prior_p10_p90
    assert activation.coverage_active_corridor_id == 7
    assert activation.coverage_last_selected_corridor_id == 7
    assert activation.coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert activation.coverage_cycle_start_deposit_kg == pytest.approx(12.5)
    assert activation.active_state_exemplar_ids == ("cell7_deep",)
    assert activation.active_state_exemplar_distance == pytest.approx(0.25)
    np.testing.assert_allclose(activation.active_state_exemplar_profile_token, profile)
    assert activation.active_state_exemplar_profile_token.dtype == np.float32


def test_build_pending_activation_facts_preserves_facade_inputs() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    profile = np.arange(12, dtype=np.float64)
    exemplar_ids = ["cell7_deep"]

    facts = build_pending_return_target_activation_facts(
        pending_dig_cut_tokens=token,
        pending_dig_cut_raw_fields=raw_fields,
        pending_dig_cut_corridor_id=np.int64(7),
        pending_dig_depth_profile_tokens=profile,
        pending_dig_state_exemplar_ids=exemplar_ids,
        pending_dig_state_exemplar_distance=np.float64(0.25),
        raw_fields_in_prior_range=1,
        cycle_start_deposit_kg=np.float64(12.5),
    )

    assert facts.pending_dig_cut_tokens is token
    assert facts.pending_dig_cut_raw_fields is raw_fields
    assert facts.pending_dig_cut_corridor_id == 7
    assert facts.pending_dig_depth_profile_tokens is profile
    assert facts.pending_dig_state_exemplar_ids is exemplar_ids
    assert facts.pending_dig_state_exemplar_distance == pytest.approx(0.25)
    assert facts.raw_fields_in_prior_range is True
    assert facts.cycle_start_deposit_kg == pytest.approx(12.5)


def test_pending_activation_facts_mapping_preserves_runtime_field_projection() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    profile = np.arange(12, dtype=np.float64)
    exemplar_ids = ["cell7_deep"]
    runtime_values = {
        "_pending_dig_cut_tokens": token,
        "_pending_dig_cut_raw_fields": raw_fields,
        "_pending_dig_cut_corridor_id": np.int64(7),
        "_pending_dig_depth_profile_tokens": profile,
        "_pending_dig_state_exemplar_ids": exemplar_ids,
        "_pending_dig_state_exemplar_distance": np.float64(0.25),
    }
    values = {
        field_name: runtime_values[attr_name]
        for field_name, attr_name in PENDING_RETURN_TARGET_ACTIVATION_FACT_FIELDS
    }

    facts = build_pending_return_target_activation_facts_from_mapping(
        values,
        raw_fields_in_prior_range=1,
        cycle_start_deposit_kg=np.float64(12.5),
    )

    assert facts.pending_dig_cut_tokens is token
    assert facts.pending_dig_cut_raw_fields is raw_fields
    assert facts.pending_dig_cut_corridor_id == 7
    assert facts.pending_dig_depth_profile_tokens is profile
    assert facts.pending_dig_state_exemplar_ids is exemplar_ids
    assert facts.pending_dig_state_exemplar_distance == pytest.approx(0.25)
    assert facts.raw_fields_in_prior_range is True
    assert facts.cycle_start_deposit_kg == pytest.approx(12.5)


def test_pending_activation_without_raw_fields_never_marks_prior_range() -> None:
    activation = ReturnTargetPlanService.pending_activation(
        PendingReturnTargetActivationFacts(
            pending_dig_cut_tokens=np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
            pending_dig_cut_raw_fields=None,
            raw_fields_in_prior_range=True,
        )
    )

    assert not activation.dig_cut_token_in_prior_p10_p90


def test_invalidated_pending_dig_cut_plan_preserves_legacy_defaults() -> None:
    state = ReturnTargetPlanService.invalidated_pending_dig_cut_plan()

    assert state.cycle_id == -1
    assert state.corridor_id == -1
    assert state.raw_fields is None
    assert state.tokens is None
    assert state.depth_profile_tokens is None
    assert state.state_exemplar_ids == ()
    assert np.isnan(state.state_exemplar_distance)


def test_initial_conditioning_state_preserves_legacy_reset_defaults() -> None:
    state = ReturnTargetPlanService.initial_conditioning_state()
    other_state = ReturnTargetPlanService.initial_conditioning_state()

    assert isinstance(state, ReturnTargetConditioningRuntimeState)
    np.testing.assert_array_equal(
        state.target_tokens,
        np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    assert state.target_tokens.dtype == np.float32
    assert state.target_token_injected is False
    assert state.target_token_source == "none"
    assert state.target_fallback_reason == ""
    np.testing.assert_array_equal(
        state.relocate_tokens,
        np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    assert state.relocate_tokens.dtype == np.float32
    assert state.relocate_token_injected is False
    np.testing.assert_array_equal(
        state.start_envelope_tokens,
        np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
    )
    assert state.start_envelope_tokens.dtype == np.float32
    assert state.start_envelope_token_injected is False
    assert state.start_envelope_token_source == "none"
    assert state.start_envelope_use_prior_spatial_bounds is True
    assert state.start_envelope_use_prior_qpos_bounds is True
    assert state.planned_cycle_id == -1
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_corridor_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_cut_tokens is None
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == ()
    assert np.isnan(state.pending_dig_state_exemplar_distance)

    state.target_tokens[0] = 99.0
    assert other_state.target_tokens[0] == np.float32(0.0)


def test_conditioning_status_snapshot_projects_return_runtime_state() -> None:
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    relocate_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 10.0
    envelope_tokens = (
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64) + 20.0
    )

    snapshot = ReturnTargetPlanService.conditioning_status_snapshot(
        ReturnTargetConditioningStatusState(
            target_token_injected=True,
            target_token_source="return_target_operator_prior",
            target_tokens=target_tokens,
            target_fallback_reason="",
            relocate_token_injected=True,
            relocate_tokens=relocate_tokens,
            start_envelope_token_injected=False,
            start_envelope_token_source="qc6_return_start_envelope_cell_2",
            start_envelope_tokens=envelope_tokens,
        )
    )
    target_tokens[0] = 99.0
    relocate_tokens[0] = 99.0
    envelope_tokens[0] = 99.0

    assert snapshot.target_token_injected is True
    assert snapshot.target_token_source == "return_target_operator_prior"
    assert snapshot.target_fallback_reason == ""
    assert snapshot.relocate_token_injected is True
    assert snapshot.start_envelope_token_injected is False
    assert (
        snapshot.start_envelope_token_source
        == "qc6_return_start_envelope_cell_2"
    )
    assert snapshot.target_tokens.dtype == np.float32
    assert snapshot.relocate_tokens.dtype == np.float32
    assert snapshot.start_envelope_tokens.dtype == np.float32
    np.testing.assert_allclose(
        snapshot.target_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    np.testing.assert_allclose(
        snapshot.relocate_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0,
    )
    np.testing.assert_allclose(
        snapshot.start_envelope_tokens,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32) + 20.0,
    )


def test_conditioning_status_state_mapping_preserves_legacy_projection() -> None:
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    relocate_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 10.0
    envelope_tokens = (
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64) + 20.0
    )
    values = {
        "target_token_injected": 1,
        "target_token_source": 123,
        "target_tokens": target_tokens,
        "target_fallback_reason": 456,
        "relocate_token_injected": 0,
        "relocate_tokens": relocate_tokens,
        "start_envelope_token_injected": 1,
        "start_envelope_token_source": 789,
        "start_envelope_tokens": envelope_tokens,
        "ignored": object(),
    }

    state = build_return_target_conditioning_status_state_from_mapping(values)

    assert {key for key, _ in RETURN_TARGET_CONDITIONING_STATUS_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state.target_token_injected is True
    assert state.target_token_source == "123"
    assert state.target_tokens is target_tokens
    assert state.target_fallback_reason == "456"
    assert state.relocate_token_injected is False
    assert state.relocate_tokens is relocate_tokens
    assert state.start_envelope_token_injected is True
    assert state.start_envelope_token_source == "789"
    assert state.start_envelope_tokens is envelope_tokens


def test_conditioning_status_snapshot_from_mapping_matches_explicit_snapshot() -> None:
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    relocate_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 10.0
    envelope_tokens = (
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64) + 20.0
    )
    values = {
        "target_token_injected": 1,
        "target_token_source": 123,
        "target_tokens": target_tokens,
        "target_fallback_reason": 456,
        "relocate_token_injected": 0,
        "relocate_tokens": relocate_tokens,
        "start_envelope_token_injected": 1,
        "start_envelope_token_source": 789,
        "start_envelope_tokens": envelope_tokens,
    }

    actual = ReturnTargetPlanService.conditioning_status_snapshot_from_mapping(values)
    expected = ReturnTargetPlanService.conditioning_status_snapshot(
        build_return_target_conditioning_status_state_from_mapping(values)
    )

    assert actual.target_token_injected == expected.target_token_injected
    assert actual.target_token_source == expected.target_token_source
    np.testing.assert_array_equal(actual.target_tokens, expected.target_tokens)
    assert actual.target_fallback_reason == expected.target_fallback_reason
    assert actual.relocate_token_injected == expected.relocate_token_injected
    np.testing.assert_array_equal(actual.relocate_tokens, expected.relocate_tokens)
    assert (
        actual.start_envelope_token_injected
        == expected.start_envelope_token_injected
    )
    assert actual.start_envelope_token_source == expected.start_envelope_token_source
    np.testing.assert_array_equal(
        actual.start_envelope_tokens,
        expected.start_envelope_tokens,
    )
    assert actual.target_tokens is not target_tokens
    assert actual.relocate_tokens is not relocate_tokens
    assert actual.start_envelope_tokens is not envelope_tokens


def test_return_target_token_result_copies_without_casting_dtype() -> None:
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)

    result = ReturnTargetPlanService.return_target_token_result(target_tokens)
    target_tokens[0] = 99.0

    assert isinstance(result, ReturnTargetObservationTokenResult)
    assert result.tokens.dtype == np.float64
    np.testing.assert_allclose(
        result.tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64),
    )


def test_return_relocate_token_result_derives_contract_token() -> None:
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    target_tokens[CUT_DEPTH_SEMANTIC_IDX] = 7.0
    target_tokens[CUT_PAYLOAD_IDX] = 8.0

    result = ReturnTargetPlanService.return_relocate_token_result(target_tokens)
    target_tokens[0] = 99.0

    assert isinstance(result, ReturnRelocateObservationTokenResult)
    assert result.tokens.dtype == np.float32
    assert float(result.tokens[CUT_DEPTH_SEMANTIC_IDX]) == pytest.approx(0.0)
    assert float(result.tokens[CUT_PAYLOAD_IDX]) == pytest.approx(0.0)
    assert result.tokens[0] == pytest.approx(0.0)


def test_return_start_envelope_token_result_copies_without_casting_dtype() -> None:
    envelope_tokens = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)

    result = ReturnTargetPlanService.return_start_envelope_token_result(
        envelope_tokens
    )
    envelope_tokens[0] = 99.0

    assert isinstance(result, ReturnStartEnvelopeObservationTokenResult)
    assert result.tokens.dtype == np.float64
    np.testing.assert_allclose(
        result.tokens,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64),
    )


def test_dig_cut_build_result_prefixes_source_and_preserves_payload_identity() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    result = ReturnTargetPlanService.dig_cut_build_result(
        config=ReturnTargetDigCutBuildResultConfig(
            source_prefix="return_target"
        ),
        facts=ReturnTargetDigCutBuildFacts(
            token=token,
            raw_fields=raw_fields,
            source_suffix="operator_prior_pose_clamped",
            fallback_reason="pose clamped",
            corridor_id=np.int64(7),
        ),
    )

    assert isinstance(result, ReturnTargetDigCutBuildResult)
    assert result.token is token
    assert result.raw_fields is raw_fields
    assert result.source == "return_target_operator_prior_pose_clamped"
    assert result.fallback_reason == "pose clamped"
    assert result.corridor_id == 7
    legacy_token, legacy_fields, legacy_source, legacy_fallback, legacy_corridor = (
        result.legacy_tuple()
    )
    assert legacy_token is token
    assert legacy_fields is raw_fields
    assert legacy_source == "return_target_operator_prior_pose_clamped"
    assert legacy_fallback == "pose clamped"
    assert legacy_corridor == 7


def test_dig_cut_build_context_and_parts_project_return_target_result() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    context = ReturnTargetPlanService.dig_cut_build_context(
        source_prefix=123,
        builder_kind="operator_prior_coverage",
        planner_mode="operator_prior_sweep_belief",
    )
    result = ReturnTargetPlanService.dig_cut_build_result_from_parts(
        context,
        token=token,
        raw_fields=raw_fields,
        source_suffix=context.planner_mode,
        fallback_reason=456,
        corridor_id=np.int64(9),
    )

    assert context == ReturnTargetDigCutBuildContext(
        source_prefix="123",
        builder_kind="operator_prior_coverage",
        planner_mode="operator_prior_sweep_belief",
    )
    assert isinstance(result, ReturnTargetDigCutBuildResult)
    assert result.token is token
    assert result.raw_fields is raw_fields
    assert result.source == "123_operator_prior_sweep_belief"
    assert result.fallback_reason == "456"
    assert result.corridor_id == 9


def test_dig_cut_build_result_from_plan_projects_plan_payload() -> None:
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    plan = SimpleNamespace(
        token=token,
        raw_fields=raw_fields,
        source="operator_prior_coverage",
        fallback_reason="",
    )
    context = ReturnTargetPlanService.dig_cut_build_context(
        source_prefix="return_target",
        builder_kind="operator_prior_coverage",
        planner_mode="operator_prior_sweep_belief",
    )

    result = ReturnTargetPlanService.dig_cut_build_result_from_plan(
        context=context,
        plan=plan,
        corridor_id=np.int64(7),
    )

    assert isinstance(result, ReturnTargetDigCutBuildResult)
    assert result.token is token
    assert result.raw_fields is raw_fields
    assert result.source == "return_target_operator_prior_coverage"
    assert result.fallback_reason == ""
    assert result.corridor_id == 7
