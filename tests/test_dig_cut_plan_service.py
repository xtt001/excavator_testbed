from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
)
from testbed.data.operator_first_v2_2 import build_live_dig_cut_tokens_from_pose
from testbed.planner.dig_cut_plan import (
    DIG_CUT_PLAN_DISPATCH_FACT_FIELDS,
    DIG_CUT_RUNTIME_STATUS_CONFIG_FIELDS,
    DIG_CUT_RUNTIME_STATUS_STATE_FIELDS,
    DigCutObservationTokenResult,
    DigCutPlan,
    DigCutPlanAttempt,
    DigCutPlanCycleApplyState,
    DigCutPlanCycleConfig,
    DigCutPlanCycleFacts,
    DigCutPlanDispatchFacts,
    DigCutPlanFailureAttemptFacts,
    DigCutPlanService,
    DigCutPlanState,
    DigCutPlanSuccessAttemptFacts,
    DigCutPlanTokenResult,
    DigCutRuntimeState,
    DigCutRuntimeStatusConfig,
    DigCutRuntimeStatusState,
    OperatorPriorDigCutPlanRequest,
    build_conservative_pose_dig_cut_plan,
    build_dig_cut_plan_dispatch_facts_from_mapping,
    build_dig_cut_runtime_status_config_from_mapping,
    build_dig_cut_runtime_status_state_from_mapping,
    build_operator_prior_dig_cut_plan,
    build_raw_fields_dig_cut_plan,
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
    decision = DigCutPlanService.cycle_decision(
        config=DigCutPlanCycleConfig(
            enabled=enabled,
            hold_until_skill_exit=hold_until_skill_exit,
        ),
        facts=DigCutPlanCycleFacts(
            planned_cycle_id=planned_cycle_id,
            cycle_index=cycle_index,
        ),
    )

    assert decision.action == expected_action
    assert decision.should_build is expected_should_build


def test_cycle_decision_from_runtime_matches_explicit_cycle_decision() -> None:
    actual = DigCutPlanService.cycle_decision_from_runtime(
        enabled=np.int64(1),
        hold_until_skill_exit=np.int64(0),
        planned_cycle_id=np.int64(-1),
        cycle_index=np.int64(4),
    )
    expected = DigCutPlanService.cycle_decision(
        config=DigCutPlanCycleConfig(
            enabled=True,
            hold_until_skill_exit=False,
        ),
        facts=DigCutPlanCycleFacts(
            planned_cycle_id=-1,
            cycle_index=4,
        ),
    )

    assert actual == expected


def test_cycle_apply_state_preserves_built_token_identity_and_cycle_projection() -> None:
    dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)
    dig_depth_profile_tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)

    state = DigCutPlanService.cycle_apply_state(
        dig_cut_tokens=dig_cut_tokens,
        dig_depth_profile_tokens=dig_depth_profile_tokens,
        cycle_index=np.int64(8),
    )

    assert isinstance(state, DigCutPlanCycleApplyState)
    assert state.dig_cut_tokens is dig_cut_tokens
    assert state.dig_depth_profile_tokens is dig_depth_profile_tokens
    assert state.planned_cycle_id == 8


def test_dispatch_decision_preserves_pending_return_target_priority() -> None:
    decision = DigCutPlanService.dispatch_decision(
        DigCutPlanDispatchFacts(
            planner_mode="unsupported_mode",
            pending_tokens_present=True,
            pending_cycle_id=4,
            cycle_index=4,
        )
    )

    assert decision.action == "pending_return_target"
    assert decision.builder_kind == ""


@pytest.mark.parametrize(
    ("mode", "expected_builder_kind"),
    [
        ("conservative_pose", "conservative_pose"),
        ("operator_prior", "operator_prior"),
        ("operator_prior_coverage", "operator_prior_coverage"),
        ("operator_prior_sweep_belief", "operator_prior_coverage"),
    ],
)
def test_dispatch_decision_maps_mode_to_legacy_builder_kind(
    mode: str,
    expected_builder_kind: str,
) -> None:
    decision = DigCutPlanService.dispatch_decision(
        DigCutPlanDispatchFacts(
            planner_mode=mode,
            pending_tokens_present=True,
            pending_cycle_id=3,
            cycle_index=4,
        )
    )

    assert decision.action == "build_plan"
    assert decision.builder_kind == expected_builder_kind


def test_dispatch_decision_preserves_unsupported_mode_error() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported dig_cut_planner mode 'unsupported_mode'",
    ):
        DigCutPlanService.dispatch_decision(
            DigCutPlanDispatchFacts(
                planner_mode="unsupported_mode",
                pending_tokens_present=False,
                pending_cycle_id=4,
                cycle_index=4,
            )
        )


def test_dispatch_facts_mapping_preserves_planner_field_projection() -> None:
    pending_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    values = {
        "planner_mode": 123,
        "pending_tokens": pending_tokens,
        "pending_cycle_id": np.int64(4),
        "cycle_index": np.int64(5),
        "ignored": object(),
    }

    facts = build_dig_cut_plan_dispatch_facts_from_mapping(values)
    missing = build_dig_cut_plan_dispatch_facts_from_mapping(
        {**values, "pending_tokens": None}
    )

    assert {key for key, _ in DIG_CUT_PLAN_DISPATCH_FACT_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert facts.planner_mode == "123"
    assert facts.pending_tokens_present is True
    assert facts.pending_cycle_id == 4
    assert facts.cycle_index == 5
    assert missing.pending_tokens_present is False


def test_dispatch_facts_mapping_allows_pending_presence_override() -> None:
    values = {
        "planner_mode": "operator_prior",
        "pending_tokens": np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32),
        "pending_cycle_id": 4,
        "cycle_index": 4,
    }

    facts = build_dig_cut_plan_dispatch_facts_from_mapping(
        values,
        pending_tokens_present=False,
    )
    decision = DigCutPlanService.dispatch_decision(facts)

    assert facts.pending_tokens_present is False
    assert decision.action == "build_plan"
    assert decision.builder_kind == "operator_prior"


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = DigCutPlanService.initial_runtime_state()
    other_state = DigCutPlanService.initial_runtime_state()

    assert isinstance(state, DigCutRuntimeState)
    assert state.tokens.shape == (DIG_CUT_TOKEN_DIM,)
    assert state.tokens.dtype == np.float32
    assert float(np.max(np.abs(state.tokens))) == pytest.approx(0.0)
    assert state.token_injected is False
    assert state.planned_cycle_id == -1
    assert state.token_source == "none"
    assert state.fallback_reason == ""
    assert state.token_in_prior_p10_p90 is False

    state.tokens[0] = 99.0
    assert other_state.tokens[0] == pytest.approx(0.0)


def test_cleared_plan_state_preserves_legacy_clear_defaults() -> None:
    state = DigCutPlanService.cleared_plan_state()
    other_state = DigCutPlanService.cleared_plan_state()

    assert state.planned_cycle_id == -1
    assert state.dig_cut_tokens.shape == (DIG_CUT_TOKEN_DIM,)
    assert state.dig_cut_tokens.dtype == np.float32
    assert float(np.max(np.abs(state.dig_cut_tokens))) == pytest.approx(0.0)
    assert state.dig_depth_profile_tokens.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert state.dig_depth_profile_tokens.dtype == np.float32
    assert float(np.max(np.abs(state.dig_depth_profile_tokens))) == pytest.approx(0.0)
    assert state.token_source == "none"
    assert state.fallback_reason == ""
    assert state.token_in_prior_p10_p90 is False

    state.dig_cut_tokens[0] = 99.0
    state.dig_depth_profile_tokens[0] = 99.0
    assert other_state.dig_cut_tokens[0] == pytest.approx(0.0)
    assert other_state.dig_depth_profile_tokens[0] == pytest.approx(0.0)


def test_operator_prior_clamps_pose_and_builds_token() -> None:
    plan = build_operator_prior_dig_cut_plan(
        OperatorPriorDigCutPlanRequest(
            dig_cut_prior=_prior(),
            bucket_dig_area_pose=(2.5, 0.25, -2.0),
        )
    )

    assert plan.source == "operator_prior_pose_clamped"
    assert plan.fallback_reason == ""
    assert plan.raw_fields["operator_entry_x_m"] == pytest.approx(1.0)
    assert plan.raw_fields["operator_entry_y_m"] == pytest.approx(0.25)
    assert plan.raw_fields["operator_entry_z_m"] == pytest.approx(-1.0)
    assert plan.raw_fields["operator_exit_x_m"] == pytest.approx(0.0)
    assert plan.raw_fields["operator_exit_z_m"] == pytest.approx(-1.0)
    assert plan.raw_fields["operator_cut_direction_x"] == pytest.approx(-1.0)
    assert plan.raw_fields["operator_cut_direction_z"] == pytest.approx(0.0)
    assert plan.raw_fields["operator_cut_length_m"] == pytest.approx(1.0)
    assert plan.raw_fields["operator_cut_depth_peak_m"] == pytest.approx(0.08)
    assert plan.raw_fields["operator_cut_payload_gain_kg"] == pytest.approx(40.0)
    assert plan.raw_fields["operator_effective_deposit_delta_kg"] == pytest.approx(
        38.0
    )
    np.testing.assert_allclose(
        plan.token,
        np.asarray(
            [0.5, -0.5, 0.0, -0.5, -1.0, 0.0, 0.5, 0.1, 2.0 / 3.0, 1.0],
            dtype=np.float32,
        ),
    )


def test_operator_prior_uses_median_pose_fallback_when_pose_missing() -> None:
    plan = build_operator_prior_dig_cut_plan(
        OperatorPriorDigCutPlanRequest(
            dig_cut_prior=_prior(),
            bucket_dig_area_pose=None,
        )
    )

    assert plan.source == "operator_prior_median_pose_fallback"
    assert plan.fallback_reason == "missing_bucket_dig_area_pose"
    assert plan.raw_fields["operator_entry_x_m"] == pytest.approx(0.5)
    assert plan.raw_fields["operator_entry_y_m"] == pytest.approx(0.0)
    assert plan.raw_fields["operator_entry_z_m"] == pytest.approx(-0.5)
    assert plan.raw_fields["operator_exit_x_m"] == pytest.approx(-0.5)
    assert plan.raw_fields["operator_exit_z_m"] == pytest.approx(-0.5)
    np.testing.assert_allclose(
        plan.token,
        np.asarray(
            [0.25, -0.25, -0.25, -0.25, -1.0, 0.0, 0.5, 0.1, 2.0 / 3.0, 1.0],
            dtype=np.float32,
        ),
    )


def test_operator_prior_requires_prior_json() -> None:
    with pytest.raises(
        ValueError,
        match="operator_prior mode requires a dig cut prior JSON",
    ):
        build_operator_prior_dig_cut_plan(
            OperatorPriorDigCutPlanRequest(
                dig_cut_prior={},
                bucket_dig_area_pose=(0.0, 0.0, 0.0),
            )
        )


def test_conservative_pose_plan_matches_live_token_builder() -> None:
    pose = (0.8, 0.0, -0.3)

    plan = build_conservative_pose_dig_cut_plan(
        pose,
        source="fallback_conservative_pose",
        fallback_reason="missing prior field",
    )

    assert plan.source == "fallback_conservative_pose"
    assert plan.fallback_reason == "missing prior field"
    assert plan.raw_fields["operator_entry_x_m"] == pytest.approx(0.8)
    assert plan.raw_fields["operator_exit_x_m"] == pytest.approx(-0.4)
    assert plan.raw_fields["operator_cut_valid"] == 1
    np.testing.assert_allclose(
        plan.token,
        build_live_dig_cut_tokens_from_pose(pose),
    )


def test_raw_fields_plan_builds_token_and_preserves_raw_field_identity() -> None:
    pose = (0.8, 0.0, -0.3)
    raw_fields = {
        "operator_entry_x_m": 0.8,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": -0.3,
        "operator_exit_x_m": -0.4,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": -0.3,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.2,
        "operator_cut_depth_peak_m": 0.08,
        "operator_cut_payload_gain_kg": 55.0,
        "operator_effective_deposit_delta_kg": 55.0,
        "operator_cut_valid": 1,
    }

    plan = build_raw_fields_dig_cut_plan(
        raw_fields,
        source=123,
        fallback_reason=456,
    )

    assert plan.raw_fields is raw_fields
    assert plan.source == "123"
    assert plan.fallback_reason == "456"
    np.testing.assert_allclose(plan.token, build_live_dig_cut_tokens_from_pose(pose))


def test_plan_service_success_attempt_builds_plan_and_copies_raw_fields() -> None:
    token = np.arange(10, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5}

    attempt = DigCutPlanService.success_attempt(
        DigCutPlanSuccessAttemptFacts(
            token=token,
            raw_fields=raw_fields,
            source="operator_prior_pose_clamped",
            fallback_reason="",
            raw_fields_in_prior_range=True,
        )
    )
    raw_fields["operator_entry_x_m"] = 99.0

    assert attempt.plan is not None
    assert attempt.plan.token is token
    assert attempt.plan.raw_fields["operator_entry_x_m"] == pytest.approx(0.5)
    assert attempt.plan.source == "operator_prior_pose_clamped"
    assert attempt.plan.fallback_reason == ""
    assert attempt.raw_fields_in_prior_range is True
    assert attempt.failure_reason is None
    assert attempt.fallback_plan is None


def test_plan_service_failure_attempt_preserves_fallback_plan() -> None:
    failure = RuntimeError("missing prior field")
    fallback = build_conservative_pose_dig_cut_plan(
        (0.8, 0.0, -0.3),
        source="fallback_conservative_pose",
        fallback_reason=str(failure),
    )

    attempt = DigCutPlanService.failure_attempt(
        DigCutPlanFailureAttemptFacts(
            reason=failure,
            fallback_plan=fallback,
        )
    )

    assert attempt.plan is None
    assert attempt.raw_fields_in_prior_range is False
    assert attempt.failure_reason is failure
    assert attempt.fallback_plan is fallback


def test_plan_service_success_state_preserves_plan_metadata() -> None:
    token = np.arange(10, dtype=np.float64)
    plan = DigCutPlan(
        token=token,
        raw_fields={"operator_entry_x_m": 0.5},
        source="operator_prior_pose_clamped",
        fallback_reason="",
    )

    state = DigCutPlanService.state_from_attempt(
        DigCutPlanAttempt.success(
            plan=plan,
            raw_fields_in_prior_range=True,
        )
    )

    np.testing.assert_allclose(state.token, token)
    assert state.token.dtype == np.float32
    assert state.source == "operator_prior_pose_clamped"
    assert state.fallback_reason == ""
    assert state.token_in_prior_p10_p90


def test_plan_service_success_plan_state_matches_attempt_path() -> None:
    token = np.arange(10, dtype=np.float64)
    plan = DigCutPlan(
        token=token,
        raw_fields={"operator_entry_x_m": 0.5},
        source="conservative_pose",
        fallback_reason="",
    )

    actual = DigCutPlanService.state_from_success_plan(
        plan,
        raw_fields_in_prior_range=False,
    )
    expected = DigCutPlanService.state_from_attempt(
        DigCutPlanAttempt.success(
            plan=plan,
            raw_fields_in_prior_range=False,
        )
    )

    np.testing.assert_allclose(actual.token, expected.token)
    assert actual.token.dtype == expected.token.dtype
    assert actual.source == expected.source
    assert actual.fallback_reason == expected.fallback_reason
    assert actual.token_in_prior_p10_p90 == expected.token_in_prior_p10_p90


def test_plan_service_failure_state_uses_fallback_plan() -> None:
    fallback = build_conservative_pose_dig_cut_plan(
        (0.8, 0.0, -0.3),
        source="fallback_conservative_pose",
        fallback_reason="missing prior field",
    )

    state = DigCutPlanService.state_from_attempt(
        DigCutPlanAttempt.failure(
            reason=RuntimeError("missing prior field"),
            fallback_plan=fallback,
        )
    )

    np.testing.assert_allclose(state.token, fallback.token)
    assert state.source == "fallback_conservative_pose"
    assert state.fallback_reason == "missing prior field"
    assert not state.token_in_prior_p10_p90


def test_plan_service_builder_attempt_success_resolves_state() -> None:
    token = np.arange(10, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5}
    calls: list[dict[str, float | int]] = []

    def build_plan() -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return token, raw_fields, "operator_prior_pose_clamped", ""

    def raw_fields_in_prior_range(fields: dict[str, float | int]) -> bool:
        calls.append(fields)
        return True

    state = DigCutPlanService.state_from_builder_attempt(
        build_plan=build_plan,
        raw_fields_in_prior_range=raw_fields_in_prior_range,
        fallback_mode="raise",
        fallback_plan=lambda _exc: pytest.fail("fallback should not build"),
    )

    assert calls == [raw_fields]
    np.testing.assert_allclose(state.token, token)
    assert state.token.dtype == np.float32
    assert state.source == "operator_prior_pose_clamped"
    assert state.fallback_reason == ""
    assert state.token_in_prior_p10_p90 is True


def test_plan_service_builder_attempt_falls_back_to_conservative_plan() -> None:
    failure = RuntimeError("missing prior")
    fallback = build_conservative_pose_dig_cut_plan(
        (0.8, 0.0, -0.3),
        source="fallback_conservative_pose",
        fallback_reason=str(failure),
    )
    fallback_calls: list[object] = []

    def build_plan() -> tuple[np.ndarray, dict[str, float | int], str, str]:
        raise failure

    def fallback_plan(exc: Exception) -> DigCutPlan:
        fallback_calls.append(exc)
        return fallback

    state = DigCutPlanService.state_from_builder_attempt(
        build_plan=build_plan,
        raw_fields_in_prior_range=lambda _fields: pytest.fail(
            "range check should not run after builder failure"
        ),
        fallback_mode="conservative_pose",
        fallback_plan=fallback_plan,
    )

    assert fallback_calls == [failure]
    np.testing.assert_allclose(state.token, fallback.token)
    assert state.token.dtype == np.float32
    assert state.source == "fallback_conservative_pose"
    assert state.fallback_reason == "missing prior"
    assert state.token_in_prior_p10_p90 is False


def test_plan_service_builder_attempt_reraises_without_fallback() -> None:
    failure = RuntimeError("missing prior")

    def build_plan() -> tuple[np.ndarray, dict[str, float | int], str, str]:
        raise failure

    with pytest.raises(RuntimeError, match="missing prior"):
        DigCutPlanService.state_from_builder_attempt(
            build_plan=build_plan,
            raw_fields_in_prior_range=lambda _fields: pytest.fail(
                "range check should not run after builder failure"
            ),
            fallback_mode="raise",
            fallback_plan=lambda _exc: pytest.fail("fallback should not build"),
        )


def test_plan_service_token_result_projects_state_metadata() -> None:
    token = np.arange(10, dtype=np.float32)
    result = DigCutPlanService.token_result(
        DigCutPlanState(
            token=token,
            source="operator_prior_pose_clamped",
            fallback_reason="",
            token_in_prior_p10_p90=True,
        )
    )

    assert isinstance(result, DigCutPlanTokenResult)
    assert result.token is token
    assert result.token.dtype == np.float32
    assert result.source == "operator_prior_pose_clamped"
    assert result.fallback_reason == ""
    assert result.token_in_prior_p10_p90 is True


def test_plan_service_token_result_casts_token_to_float32() -> None:
    token = np.arange(10, dtype=np.float64)
    result = DigCutPlanService.token_result(
        DigCutPlanState(
            token=token,
            source="fallback_conservative_pose",
            fallback_reason="missing prior field",
            token_in_prior_p10_p90=False,
        )
    )

    assert result.token.dtype == np.float32
    np.testing.assert_allclose(result.token, np.arange(10, dtype=np.float32))
    assert result.source == "fallback_conservative_pose"
    assert result.fallback_reason == "missing prior field"
    assert result.token_in_prior_p10_p90 is False


def test_observation_token_result_copies_without_casting_dtype() -> None:
    tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)

    result = DigCutPlanService.observation_token_result(tokens)
    tokens[0] = 99.0

    assert isinstance(result, DigCutObservationTokenResult)
    assert result.token.dtype == np.float64
    np.testing.assert_allclose(
        result.token,
        np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64),
    )


def test_runtime_status_snapshot_projects_config_and_runtime_state() -> None:
    tokens = np.arange(10, dtype=np.float64)
    snapshot = DigCutPlanService.runtime_status_snapshot(
        config=DigCutRuntimeStatusConfig(
            planner_mode="operator_prior_coverage",
            prior_id="prior_a",
        ),
        state=DigCutRuntimeStatusState(
            pending_cycle_id=6,
            pending_corridor_id=7,
            token_injected=True,
            token_source="pending_return_target",
            tokens=tokens,
            token_in_prior_p10_p90=True,
            fallback_reason="",
        ),
    )
    tokens[0] = 99.0

    assert snapshot.pending_cycle_id == 6
    assert snapshot.pending_corridor_id == 7
    assert snapshot.token_injected is True
    assert snapshot.planner_mode == "operator_prior_coverage"
    assert snapshot.prior_id == "prior_a"
    assert snapshot.token_source == "pending_return_target"
    assert snapshot.tokens.dtype == np.float32
    np.testing.assert_allclose(snapshot.tokens, np.arange(10, dtype=np.float32))
    assert snapshot.token_in_prior_p10_p90 is True
    assert snapshot.fallback_reason == ""


def test_runtime_status_config_mapping_preserves_legacy_projection() -> None:
    values = {
        "planner_mode": 123,
        "prior_id": 456,
        "ignored": object(),
    }

    config = build_dig_cut_runtime_status_config_from_mapping(values)

    assert {key for key, _ in DIG_CUT_RUNTIME_STATUS_CONFIG_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert config == DigCutRuntimeStatusConfig(
        planner_mode="123",
        prior_id="456",
    )


def test_runtime_status_state_mapping_preserves_legacy_projection() -> None:
    tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)
    values = {
        "pending_cycle_id": "6",
        "pending_corridor_id": "7",
        "token_injected": 1,
        "token_source": 123,
        "tokens": tokens,
        "token_in_prior_p10_p90": 0,
        "fallback_reason": 456,
        "ignored": object(),
    }

    state = build_dig_cut_runtime_status_state_from_mapping(values)

    assert {key for key, _ in DIG_CUT_RUNTIME_STATUS_STATE_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state.pending_cycle_id == 6
    assert state.pending_corridor_id == 7
    assert state.token_injected is True
    assert state.token_source == "123"
    assert state.tokens is tokens
    assert state.token_in_prior_p10_p90 is False
    assert state.fallback_reason == "456"


def test_runtime_status_snapshot_from_mappings_matches_explicit_snapshot() -> None:
    tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)
    config_values = {
        "planner_mode": 123,
        "prior_id": 456,
    }
    state_values = {
        "pending_cycle_id": "6",
        "pending_corridor_id": "7",
        "token_injected": 1,
        "token_source": 123,
        "tokens": tokens,
        "token_in_prior_p10_p90": 0,
        "fallback_reason": 456,
    }

    actual = DigCutPlanService.runtime_status_snapshot_from_mappings(
        config_values=config_values,
        state_values=state_values,
    )
    expected = DigCutPlanService.runtime_status_snapshot(
        config=build_dig_cut_runtime_status_config_from_mapping(config_values),
        state=build_dig_cut_runtime_status_state_from_mapping(state_values),
    )

    assert actual.pending_cycle_id == expected.pending_cycle_id
    assert actual.pending_corridor_id == expected.pending_corridor_id
    assert actual.token_injected == expected.token_injected
    assert actual.planner_mode == expected.planner_mode
    assert actual.prior_id == expected.prior_id
    assert actual.token_source == expected.token_source
    np.testing.assert_array_equal(actual.tokens, expected.tokens)
    assert actual.token_in_prior_p10_p90 == expected.token_in_prior_p10_p90
    assert actual.fallback_reason == expected.fallback_reason
    assert actual.tokens is not tokens


def _prior() -> dict[str, object]:
    return {
        "fields": {
            "entry_x_m": _field(0.0, 0.5, 1.0),
            "entry_z_m": _field(-1.0, -0.5, 0.0),
            "exit_x_m": _field(-1.2, -0.5, 0.0),
            "exit_z_m": _field(-1.0, -0.5, 0.0),
            "cut_direction_x": _field(-1.0, -0.6, -0.2),
            "cut_direction_z": _field(-0.4, 0.0, 0.4),
            "cut_length_m": _field(0.5, 1.0, 1.5),
            "cut_depth_peak_m": _field(0.04, 0.08, 0.16),
            "payload_gain_kg": _field(20.0, 40.0, 60.0),
            "effective_deposit_delta_kg": _field(20.0, 38.0, 58.0),
        }
    }


def _field(p10: float, p50: float, p90: float) -> dict[str, float]:
    return {"p10": p10, "p50": p50, "p90": p90}
