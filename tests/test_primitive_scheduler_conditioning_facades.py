from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.operator_first_v2_2 import _build_dig_cut_token
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
)
from testbed.planner.cell_entry import CellGridSpec
from testbed.planner.dig_coverage.models import (
    CoverageActiveStateExemplarState,
    CoverageCorridorState,
)
from testbed.planner.dig_cut_plan import (
    DIG_CUT_PLAN_DISPATCH_FACT_FIELDS,
    DigCutPlanClearState,
    DigCutPlanCycleApplyState,
    DigCutRuntimeState,
    build_dig_cut_plan_dispatch_facts_from_mapping,
)
from testbed.planner.dig_depth_profile import (
    DigDepthProfileRuntimeState,
)
from testbed.planner.return_target_plan import (
    PendingDigCutPlanState,
    ReturnTargetConditioningRuntimeState,
    ReturnTargetDigCutBuildContext,
    ReturnTargetDigCutBuildResult,
    ReturnTargetPlanRuntimeUpdate,
    ReturnTargetPlanState,
)
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_return_target_disabled_skips_builder_side_effects() -> None:
    policy = _make_policy()
    policy.return_target_planner_enabled = False
    policy._cycle_index = 4
    policy._return_target_planned_cycle_id = 3
    original_tokens = policy._return_target_tokens.copy()

    def fail_build(_obs: dict[str, np.ndarray]) -> tuple[np.ndarray, dict, str, str, int]:
        raise AssertionError("disabled return target planner must not build")

    policy._build_next_dig_cut_plan_for_return = fail_build  # type: ignore[method-assign]

    policy._ensure_return_target_plan_for_cycle(_obs())

    np.testing.assert_allclose(policy._return_target_tokens, original_tokens)
    assert policy._return_target_planned_cycle_id == 3


def test_return_target_envelope_failure_writes_fallback_zero() -> None:
    policy = _make_policy()
    policy.return_target_planner_enabled = True
    policy._cycle_index = 2
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    def build_plan(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        return token, raw_fields, "return_target_operator_prior", "", 7

    def fail_envelope(
        _obs: dict[str, np.ndarray],
        fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        assert fields == raw_fields
        assert corridor_id == 7
        raise RuntimeError("bad envelope")

    policy._build_next_dig_cut_plan_for_return = build_plan  # type: ignore[method-assign]
    policy._build_return_start_envelope_tokens_for_obs = fail_envelope  # type: ignore[method-assign]

    policy._ensure_return_target_plan_for_cycle(_obs())

    assert policy._return_target_token_source == "fallback_zero"
    assert policy._return_start_envelope_token_source == "fallback_zero"
    assert policy._return_target_fallback_reason == "bad envelope"
    assert policy._return_target_planned_cycle_id == 2
    assert float(np.max(np.abs(policy._return_target_tokens))) == pytest.approx(0.0)
    assert float(np.max(np.abs(policy._return_start_envelope_tokens))) == pytest.approx(
        0.0
    )
    assert policy._pending_dig_cut_cycle_id == -1
    assert policy._pending_dig_cut_raw_fields is None
    assert policy._pending_dig_cut_tokens is None
    assert policy._pending_dig_cut_corridor_id == -1
    assert policy._pending_dig_depth_profile_tokens is None
    assert policy._pending_dig_state_exemplar_ids == []
    assert np.isnan(policy._pending_dig_state_exemplar_distance)


def test_build_next_dig_cut_plan_for_return_prefixes_operator_prior_source() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = "operator_prior"
    token = np.linspace(0.0, 1.0, DIG_CUT_TOKEN_DIM, dtype=np.float64)
    raw_fields = _raw_fields()

    def build_operator_prior(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return token, raw_fields, "operator_prior_pose_clamped", "pose clamped"

    policy._build_operator_prior_dig_cut_tokens = build_operator_prior  # type: ignore[method-assign]

    result_token, result_fields, source, fallback_reason, corridor_id = (
        policy._build_next_dig_cut_plan_for_return(_obs())
    )

    np.testing.assert_allclose(result_token, token)
    assert result_token.dtype == np.float64
    assert result_fields is raw_fields
    assert source == "return_target_operator_prior_pose_clamped"
    assert fallback_reason == "pose clamped"
    assert corridor_id == -1


def test_build_next_dig_cut_plan_for_return_delegates_result_projection() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = "operator_prior"
    policy.return_target_token_source_prefix = "return_target"
    token = np.linspace(0.0, 1.0, DIG_CUT_TOKEN_DIM, dtype=np.float64)
    raw_fields = _raw_fields()
    calls: list[tuple[ReturnTargetDigCutBuildContext, str, int]] = []

    def build_operator_prior(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return token, raw_fields, "operator_prior_pose_clamped", "pose clamped"

    def dig_cut_build_context(
        *,
        source_prefix: object,
        builder_kind: object,
        planner_mode: object,
    ) -> ReturnTargetDigCutBuildContext:
        return ReturnTargetDigCutBuildContext(
            source_prefix=str(source_prefix),
            builder_kind=str(builder_kind),
            planner_mode=str(planner_mode),
        )

    def dig_cut_build_result_from_parts(
        context: ReturnTargetDigCutBuildContext,
        *,
        token: np.ndarray,
        raw_fields: dict[str, float | int],
        source_suffix: object,
        fallback_reason: object = "",
        corridor_id: object = -1,
    ) -> ReturnTargetDigCutBuildResult:
        assert token is token_for_assert
        assert raw_fields is raw_fields_for_assert
        calls.append((context, str(source_suffix), int(corridor_id)))
        return ReturnTargetDigCutBuildResult(
            token=token,
            raw_fields=raw_fields,
            source="projected_source",
            fallback_reason=str(fallback_reason),
            corridor_id=42,
        )

    token_for_assert = token
    raw_fields_for_assert = raw_fields
    policy._build_operator_prior_dig_cut_tokens = build_operator_prior  # type: ignore[method-assign]
    policy.return_target_plan_service.dig_cut_build_context = (  # type: ignore[method-assign]
        dig_cut_build_context
    )
    policy.return_target_plan_service.dig_cut_build_result_from_parts = (  # type: ignore[method-assign]
        dig_cut_build_result_from_parts
    )

    result_token, result_fields, source, fallback_reason, corridor_id = (
        policy._build_next_dig_cut_plan_for_return(_obs())
    )

    assert calls == [
        (
            ReturnTargetDigCutBuildContext(
                source_prefix="return_target",
                builder_kind="operator_prior",
                planner_mode="operator_prior",
            ),
            "operator_prior_pose_clamped",
            -1,
        )
    ]
    assert result_token is token
    assert result_fields is raw_fields
    assert source == "projected_source"
    assert fallback_reason == "pose clamped"
    assert corridor_id == 42


def test_build_next_dig_cut_plan_for_return_conservative_source_and_no_coverage_side_effect() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = "conservative_pose"
    policy._coverage_active_corridor_id = 11

    def fail_select(_obs: dict[str, np.ndarray]) -> CoverageCorridorState:
        raise AssertionError("conservative return target must not select coverage")

    def fail_coverage_raw_fields(
        _corridor: CoverageCorridorState,
        *,
        obs: dict[str, np.ndarray],
        update_state: bool = False,
    ) -> dict[str, float | int]:
        raise AssertionError("conservative return target must not build coverage raw fields")

    policy._select_next_coverage_corridor = fail_select  # type: ignore[method-assign]
    policy._coverage_raw_fields = fail_coverage_raw_fields  # type: ignore[method-assign]

    token, raw_fields, source, fallback_reason, corridor_id = (
        policy._build_next_dig_cut_plan_for_return(
            _obs(bucket_pose=(0.25, 0.1, -0.35))
        )
    )

    assert source == "return_target_conservative_pose"
    assert fallback_reason == ""
    assert corridor_id == -1
    assert policy._coverage_active_corridor_id == 11
    assert raw_fields["operator_entry_x_m"] == pytest.approx(0.25)
    assert raw_fields["operator_entry_y_m"] == pytest.approx(0.1)
    assert raw_fields["operator_entry_z_m"] == pytest.approx(-0.35)
    np.testing.assert_allclose(token, _build_dig_cut_token(raw_fields))
    assert token.dtype == np.float32


@pytest.mark.parametrize(
    ("mode", "expected_source"),
    [
        ("operator_prior_coverage", "return_target_operator_prior_coverage"),
        (
            "operator_prior_sweep_belief",
            "return_target_operator_prior_sweep_belief",
        ),
    ],
)
def test_build_next_dig_cut_plan_for_return_coverage_updates_corridor_state(
    mode: str,
    expected_source: str,
) -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = mode
    corridor = CoverageCorridorState(
        corridor_id=7,
        entry_x_m=0.5,
        entry_z_m=-0.25,
        exit_x_m=-0.5,
        exit_z_m=-0.25,
    )
    calls: list[tuple[int, bool]] = []
    raw_fields = _raw_fields()

    def select_corridor(_obs: dict[str, np.ndarray]) -> CoverageCorridorState:
        return corridor

    def coverage_raw_fields(
        selected: CoverageCorridorState,
        *,
        obs: dict[str, np.ndarray],
        update_state: bool = False,
    ) -> dict[str, float | int]:
        calls.append((int(selected.corridor_id), bool(update_state)))
        return raw_fields

    policy._select_next_coverage_corridor = select_corridor  # type: ignore[method-assign]
    policy._coverage_raw_fields = coverage_raw_fields  # type: ignore[method-assign]

    token, result_fields, source, fallback_reason, corridor_id = (
        policy._build_next_dig_cut_plan_for_return(_obs())
    )

    assert calls == [(7, True)]
    assert policy._coverage_active_corridor_id == 7
    np.testing.assert_allclose(token, _build_dig_cut_token(raw_fields))
    assert result_fields is raw_fields
    assert source == expected_source
    assert fallback_reason == ""
    assert corridor_id == 7


def test_build_next_dig_cut_plan_for_return_unsupported_mode_error_text() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = "unknown_mode"

    with pytest.raises(ValueError) as exc_info:
        policy._build_next_dig_cut_plan_for_return(_obs())

    assert str(exc_info.value) == "Unsupported dig_cut_planner mode 'unknown_mode'."


def test_dig_cut_plan_dispatch_facts_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = 123
    policy._pending_dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    policy._pending_dig_cut_cycle_id = np.int64(4)
    policy._cycle_index = np.int64(5)

    expected = build_dig_cut_plan_dispatch_facts_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for field_name, attr_name in DIG_CUT_PLAN_DISPATCH_FACT_FIELDS
        }
    )

    actual = policy._dig_cut_plan_dispatch_facts()
    override = policy._dig_cut_plan_dispatch_facts(pending_tokens_present=False)

    assert actual == expected
    assert actual.planner_mode == "123"
    assert actual.pending_tokens_present is True
    assert actual.pending_cycle_id == 4
    assert actual.cycle_index == 5
    assert override.pending_tokens_present is False


def test_ensure_dig_cut_plan_for_cycle_builds_cut_before_depth_profile() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_enabled = True
    policy._cycle_index = 8
    policy._dig_cut_planned_cycle_id = 7
    calls: list[str] = []
    dig_cut_token = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    depth_profile = np.arange(12, dtype=np.float32)

    def build_dig_cut(_obs: dict[str, np.ndarray]) -> np.ndarray:
        calls.append("dig_cut")
        assert policy._dig_cut_planned_cycle_id == 7
        return dig_cut_token

    def build_depth(_obs: dict[str, np.ndarray]) -> np.ndarray:
        calls.append("depth")
        assert policy._dig_cut_planned_cycle_id == 7
        np.testing.assert_allclose(policy._dig_cut_tokens, dig_cut_token)
        return depth_profile

    policy._build_dig_cut_tokens_for_obs = build_dig_cut  # type: ignore[method-assign]
    policy._build_dig_depth_profile_tokens_for_obs = build_depth  # type: ignore[method-assign]

    policy._ensure_dig_cut_plan_for_cycle(_obs())

    assert calls == ["dig_cut", "depth"]
    np.testing.assert_allclose(policy._dig_cut_tokens, dig_cut_token)
    np.testing.assert_allclose(policy._dig_depth_profile_tokens, depth_profile)
    assert policy._dig_cut_planned_cycle_id == 8


def test_ensure_dig_cut_plan_for_cycle_applies_service_cycle_state() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_enabled = True
    policy._cycle_index = 8
    policy._dig_cut_planned_cycle_id = 7
    built_dig_cut = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    built_depth_profile = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    service_dig_cut = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32) + 20.0
    service_depth_profile = (
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32) + 30.0
    )
    calls: list[tuple[bool, bool, int]] = []

    def build_dig_cut(_obs: dict[str, np.ndarray]) -> np.ndarray:
        return built_dig_cut

    def build_depth(_obs: dict[str, np.ndarray]) -> np.ndarray:
        return built_depth_profile

    def cycle_apply_state(
        *,
        dig_cut_tokens: np.ndarray,
        dig_depth_profile_tokens: np.ndarray,
        cycle_index: int,
    ) -> DigCutPlanCycleApplyState:
        calls.append(
            (
                dig_cut_tokens is built_dig_cut,
                dig_depth_profile_tokens is built_depth_profile,
                int(cycle_index),
            )
        )
        return DigCutPlanCycleApplyState(
            dig_cut_tokens=service_dig_cut,
            dig_depth_profile_tokens=service_depth_profile,
            planned_cycle_id=9,
        )

    policy._build_dig_cut_tokens_for_obs = build_dig_cut  # type: ignore[method-assign]
    policy._build_dig_depth_profile_tokens_for_obs = build_depth  # type: ignore[method-assign]
    policy.dig_cut_plan_service.cycle_apply_state = cycle_apply_state  # type: ignore[method-assign]

    policy._ensure_dig_cut_plan_for_cycle(_obs())

    assert calls == [(True, True, 8)]
    np.testing.assert_allclose(policy._dig_cut_tokens, service_dig_cut)
    np.testing.assert_allclose(policy._dig_depth_profile_tokens, service_depth_profile)
    assert policy._dig_cut_planned_cycle_id == 9


def test_dig_cut_disabled_skips_builder_side_effects() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_enabled = False
    policy._cycle_index = 8
    policy._dig_cut_planned_cycle_id = 7
    original_tokens = policy._dig_cut_tokens.copy()

    def fail_build(_obs: dict[str, np.ndarray]) -> np.ndarray:
        raise AssertionError("disabled dig-cut planner must not build")

    policy._build_dig_cut_tokens_for_obs = fail_build  # type: ignore[method-assign]
    policy._build_dig_depth_profile_tokens_for_obs = fail_build  # type: ignore[method-assign]

    policy._ensure_dig_cut_plan_for_cycle(_obs())

    np.testing.assert_allclose(policy._dig_cut_tokens, original_tokens)
    assert policy._dig_cut_planned_cycle_id == 7


def test_dig_cut_hold_existing_cycle_skips_builders() -> None:
    policy = _make_policy()
    policy.dig_cut_planner_enabled = True
    policy.dig_cut_hold_token_until_skill_exit = True
    policy._cycle_index = 8
    policy._dig_cut_planned_cycle_id = 8
    original_tokens = policy._dig_cut_tokens.copy()

    def fail_build(_obs: dict[str, np.ndarray]) -> np.ndarray:
        raise AssertionError("held dig-cut plan must not rebuild")

    policy._build_dig_cut_tokens_for_obs = fail_build  # type: ignore[method-assign]
    policy._build_dig_depth_profile_tokens_for_obs = fail_build  # type: ignore[method-assign]

    policy._ensure_dig_cut_plan_for_cycle(_obs())

    np.testing.assert_allclose(policy._dig_cut_tokens, original_tokens)
    assert policy._dig_cut_planned_cycle_id == 8


def test_apply_return_target_plan_state_copies_pending_payloads() -> None:
    policy = _make_policy()
    target = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    pending_token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0
    pending_profile = np.arange(12, dtype=np.float32)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    state = ReturnTargetPlanState(
        return_target_tokens=target,
        return_start_envelope_tokens=envelope,
        return_target_token_source="return_target_operator_prior",
        return_target_fallback_reason="",
        return_target_planned_cycle_id=4,
        pending_dig_cut_cycle_id=5,
        pending_dig_cut_raw_fields=raw_fields,
        pending_dig_cut_tokens=pending_token,
        pending_dig_cut_corridor_id=7,
        pending_dig_depth_profile_tokens=pending_profile,
        pending_dig_state_exemplar_ids=("cell7_deep",),
        pending_dig_state_exemplar_distance=0.25,
        return_start_envelope_token_source="qc6_return_start_envelope_cell_7",
    )

    policy._apply_return_target_plan_state(state)
    target[0] = 99.0
    envelope[0] = 99.0
    pending_token[0] = 99.0
    pending_profile[0] = 99.0
    raw_fields["operator_entry_x_m"] = 99.0

    assert policy._return_target_tokens.dtype == np.float32
    assert policy._return_start_envelope_tokens.dtype == np.float32
    np.testing.assert_allclose(
        policy._return_target_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    np.testing.assert_allclose(
        policy._return_start_envelope_tokens,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
    )
    assert policy._return_target_token_source == "return_target_operator_prior"
    assert (
        policy._return_start_envelope_token_source
        == "qc6_return_start_envelope_cell_7"
    )
    assert policy._return_target_planned_cycle_id == 4
    assert policy._pending_dig_cut_cycle_id == 5
    assert policy._pending_dig_cut_raw_fields == {
        "operator_entry_x_m": 0.5,
        "operator_cut_valid": 1,
    }
    np.testing.assert_allclose(
        policy._pending_dig_cut_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0,
    )
    np.testing.assert_allclose(
        policy._pending_dig_depth_profile_tokens,
        np.arange(12, dtype=np.float32),
    )
    assert policy._pending_dig_cut_corridor_id == 7
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_apply_return_target_plan_state_uses_service_pending_projection() -> None:
    policy = _make_policy()
    state = ReturnTargetPlanState(
        return_target_tokens=np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64),
        return_start_envelope_tokens=np.arange(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float64,
        ),
        return_target_token_source="return_target_operator_prior",
        return_target_fallback_reason="",
        return_target_planned_cycle_id=4,
        pending_dig_cut_cycle_id=99,
        pending_dig_cut_raw_fields={"ignored": 1},
        pending_dig_cut_tokens=np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
        pending_dig_cut_corridor_id=99,
        pending_dig_depth_profile_tokens=None,
        pending_dig_state_exemplar_ids=(),
        pending_dig_state_exemplar_distance=float("nan"),
    )
    projected_token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 30.0
    projected_profile = np.arange(12, dtype=np.float64) + 40.0
    projected_raw_fields = {"operator_entry_x_m": 0.5}
    calls: list[ReturnTargetPlanState] = []

    def runtime_update_from_plan_state(
        plan_state: ReturnTargetPlanState,
    ) -> ReturnTargetPlanRuntimeUpdate:
        calls.append(plan_state)
        return ReturnTargetPlanRuntimeUpdate(
            return_target_tokens=np.asarray(
                plan_state.return_target_tokens,
                dtype=np.float32,
            ),
            return_start_envelope_tokens=np.asarray(
                plan_state.return_start_envelope_tokens,
                dtype=np.float32,
            ),
            return_target_token_source=str(plan_state.return_target_token_source),
            return_start_envelope_token_source=(
                plan_state.return_start_envelope_token_source
            ),
            return_target_fallback_reason=str(plan_state.return_target_fallback_reason),
            return_target_planned_cycle_id=int(
                plan_state.return_target_planned_cycle_id
            ),
            pending_plan=PendingDigCutPlanState(
                cycle_id=5,
                corridor_id=7,
                raw_fields=projected_raw_fields,
                tokens=projected_token,
                depth_profile_tokens=projected_profile,
                state_exemplar_ids=("cell7_deep",),
                state_exemplar_distance=0.25,
            ),
        )

    policy.return_target_plan_service.runtime_update_from_plan_state = (  # type: ignore[method-assign]
        runtime_update_from_plan_state
    )

    policy._apply_return_target_plan_state(state)
    projected_token[0] = 99.0
    projected_profile[0] = 99.0
    projected_raw_fields["operator_entry_x_m"] = 99.0

    assert calls == [state]
    assert policy._pending_dig_cut_cycle_id == 5
    assert policy._pending_dig_cut_corridor_id == 7
    assert policy._pending_dig_cut_raw_fields == {"operator_entry_x_m": 0.5}
    np.testing.assert_allclose(
        policy._pending_dig_cut_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 30.0,
    )
    np.testing.assert_allclose(
        policy._pending_dig_depth_profile_tokens,
        np.arange(12, dtype=np.float32) + 40.0,
    )
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_invalidate_pending_dig_cut_plan_applies_service_state() -> None:
    policy = _make_policy()
    pending_token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 10.0
    pending_profile = np.arange(12, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    def invalidated_pending_dig_cut_plan() -> PendingDigCutPlanState:
        return PendingDigCutPlanState(
            cycle_id=5,
            corridor_id=7,
            raw_fields=raw_fields,
            tokens=pending_token,
            depth_profile_tokens=pending_profile,
            state_exemplar_ids=("cell7_deep",),
            state_exemplar_distance=0.25,
        )

    policy.return_target_plan_service.invalidated_pending_dig_cut_plan = (  # type: ignore[method-assign]
        invalidated_pending_dig_cut_plan
    )

    policy._invalidate_pending_dig_cut_plan()
    pending_token[0] = 99.0
    pending_profile[0] = 99.0
    raw_fields["operator_entry_x_m"] = 99.0

    assert policy._pending_dig_cut_cycle_id == 5
    assert policy._pending_dig_cut_corridor_id == 7
    assert policy._pending_dig_cut_raw_fields == {
        "operator_entry_x_m": 0.5,
        "operator_cut_valid": 1,
    }
    np.testing.assert_allclose(
        policy._pending_dig_cut_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0,
    )
    np.testing.assert_allclose(
        policy._pending_dig_depth_profile_tokens,
        np.arange(12, dtype=np.float32),
    )
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_reset_return_target_conditioning_runtime_applies_service_state() -> None:
    policy = _make_policy()
    target = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    relocate = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 10.0
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64) + 20.0
    pending = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 30.0
    profile = np.arange(12, dtype=np.float64) + 40.0
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    def initial_conditioning_state() -> ReturnTargetConditioningRuntimeState:
        return ReturnTargetConditioningRuntimeState(
            target_tokens=target,
            target_token_injected=True,
            target_token_source="return_target_operator_prior",
            target_fallback_reason="",
            relocate_tokens=relocate,
            relocate_token_injected=True,
            start_envelope_tokens=envelope,
            start_envelope_token_injected=True,
            start_envelope_token_source="qc6_return_start_envelope_cell_7",
            start_envelope_use_prior_spatial_bounds=False,
            start_envelope_use_prior_qpos_bounds=False,
            planned_cycle_id=4,
            pending_dig_cut_cycle_id=5,
            pending_dig_cut_corridor_id=7,
            pending_dig_cut_raw_fields=raw_fields,
            pending_dig_cut_tokens=pending,
            pending_dig_depth_profile_tokens=profile,
            pending_dig_state_exemplar_ids=("cell7_deep",),
            pending_dig_state_exemplar_distance=0.25,
        )

    policy.return_target_plan_service.initial_conditioning_state = (  # type: ignore[method-assign]
        initial_conditioning_state
    )

    policy.reset()
    target[0] = 99.0
    relocate[0] = 99.0
    envelope[0] = 99.0
    pending[0] = 99.0
    profile[0] = 99.0
    raw_fields["operator_entry_x_m"] = 99.0

    np.testing.assert_allclose(
        policy._return_target_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    assert policy._return_target_tokens.dtype == np.float32
    assert policy._return_target_token_injected is True
    assert policy._return_target_token_source == "return_target_operator_prior"
    assert policy._return_target_fallback_reason == ""
    np.testing.assert_allclose(
        policy._return_relocate_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0,
    )
    assert policy._return_relocate_tokens.dtype == np.float32
    assert policy._return_relocate_token_injected is True
    np.testing.assert_allclose(
        policy._return_start_envelope_tokens,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32) + 20.0,
    )
    assert policy._return_start_envelope_tokens.dtype == np.float32
    assert policy._return_start_envelope_token_injected is True
    assert (
        policy._return_start_envelope_token_source
        == "qc6_return_start_envelope_cell_7"
    )
    assert policy._return_start_envelope_use_prior_spatial_bounds is False
    assert policy._return_start_envelope_use_prior_qpos_bounds is False
    assert policy._return_target_planned_cycle_id == 4
    assert policy._pending_dig_cut_cycle_id == 5
    assert policy._pending_dig_cut_corridor_id == 7
    assert policy._pending_dig_cut_raw_fields == {
        "operator_entry_x_m": 0.5,
        "operator_cut_valid": 1,
    }
    np.testing.assert_allclose(
        policy._pending_dig_cut_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 30.0,
    )
    np.testing.assert_allclose(
        policy._pending_dig_depth_profile_tokens,
        np.arange(12, dtype=np.float32) + 40.0,
    )
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_apply_return_target_conditioning_runtime_uses_service_pending_projection() -> None:
    policy = _make_policy()
    state = ReturnTargetConditioningRuntimeState(
        target_tokens=np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64),
        target_token_injected=True,
        target_token_source="return_target_operator_prior",
        target_fallback_reason="",
        relocate_tokens=np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 10.0,
        relocate_token_injected=True,
        start_envelope_tokens=np.arange(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            dtype=np.float64,
        )
        + 20.0,
        start_envelope_token_injected=True,
        start_envelope_token_source="qc6_return_start_envelope_cell_7",
        start_envelope_use_prior_spatial_bounds=False,
        start_envelope_use_prior_qpos_bounds=False,
        planned_cycle_id=4,
        pending_dig_cut_cycle_id=99,
        pending_dig_cut_corridor_id=99,
        pending_dig_cut_raw_fields={"ignored": 1},
        pending_dig_cut_tokens=np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
        pending_dig_depth_profile_tokens=None,
        pending_dig_state_exemplar_ids=(),
        pending_dig_state_exemplar_distance=float("nan"),
    )
    projected_token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64) + 30.0
    projected_profile = np.arange(12, dtype=np.float64) + 40.0
    projected_raw_fields = {"operator_entry_x_m": 0.5}
    calls: list[ReturnTargetConditioningRuntimeState] = []

    def pending_plan_state_from_conditioning_state(
        runtime_state: ReturnTargetConditioningRuntimeState,
    ) -> PendingDigCutPlanState:
        calls.append(runtime_state)
        return PendingDigCutPlanState(
            cycle_id=5,
            corridor_id=7,
            raw_fields=projected_raw_fields,
            tokens=projected_token,
            depth_profile_tokens=projected_profile,
            state_exemplar_ids=("cell7_deep",),
            state_exemplar_distance=0.25,
        )

    policy.return_target_plan_service.pending_plan_state_from_conditioning_state = (  # type: ignore[method-assign]
        pending_plan_state_from_conditioning_state
    )

    policy._apply_return_target_conditioning_runtime_state(state)
    projected_token[0] = 99.0
    projected_profile[0] = 99.0
    projected_raw_fields["operator_entry_x_m"] = 99.0

    assert calls == [state]
    assert policy._return_target_planned_cycle_id == 4
    assert policy._pending_dig_cut_cycle_id == 5
    assert policy._pending_dig_cut_corridor_id == 7
    assert policy._pending_dig_cut_raw_fields == {"operator_entry_x_m": 0.5}
    np.testing.assert_allclose(
        policy._pending_dig_cut_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 30.0,
    )
    np.testing.assert_allclose(
        policy._pending_dig_depth_profile_tokens,
        np.arange(12, dtype=np.float32) + 40.0,
    )
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_clear_dig_cut_plan_applies_service_state_without_resetting_injection_flags() -> None:
    policy = _make_policy()
    dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64) + 10.0
    depth_profile_tokens = (
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64) + 20.0
    )
    exemplar_profile = (
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64) + 30.0
    )

    def cleared_plan_state() -> DigCutPlanClearState:
        return DigCutPlanClearState(
            planned_cycle_id=5,
            dig_cut_tokens=dig_cut_tokens,
            dig_depth_profile_tokens=depth_profile_tokens,
            token_source="operator_prior_pose_clamped",
            fallback_reason="missing_bucket_dig_area_pose",
            token_in_prior_p10_p90=True,
        )

    def cleared_active_state_exemplar_state() -> CoverageActiveStateExemplarState:
        return CoverageActiveStateExemplarState(
            ids=("cell7_deep",),
            distance=0.25,
            profile_token=exemplar_profile,
        )

    policy.dig_cut_plan_service.cleared_plan_state = cleared_plan_state  # type: ignore[method-assign]
    policy.coverage_service.cleared_active_state_exemplar_state = (  # type: ignore[method-assign]
        cleared_active_state_exemplar_state
    )
    policy._dig_cut_token_injected = True
    policy._dig_depth_profile_token_injected = True
    policy._dig_depth_profile_token_source = "qc6_dig_depth_profile_cell_7"
    policy._dig_depth_profile_fallback_reason = "kept_depth_profile_reason"

    policy._clear_dig_cut_plan()
    dig_cut_tokens[0] = 99.0
    depth_profile_tokens[0] = 99.0
    exemplar_profile[0] = 99.0

    assert policy._dig_cut_planned_cycle_id == 5
    np.testing.assert_allclose(
        policy._dig_cut_tokens,
        np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32) + 10.0,
    )
    np.testing.assert_allclose(
        policy._dig_depth_profile_tokens,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32) + 20.0,
    )
    assert policy._dig_cut_token_source == "operator_prior_pose_clamped"
    assert policy._dig_cut_fallback_reason == "missing_bucket_dig_area_pose"
    assert policy._dig_cut_token_in_prior_p10_p90 is True
    assert policy._coverage_active_state_exemplar_ids == ["cell7_deep"]
    assert policy._coverage_active_state_exemplar_distance == pytest.approx(0.25)
    np.testing.assert_allclose(
        policy._coverage_active_state_exemplar_profile_token,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32) + 30.0,
    )
    assert policy._dig_cut_token_injected is True
    assert policy._dig_depth_profile_token_injected is True
    assert (
        policy._dig_depth_profile_token_source == "qc6_dig_depth_profile_cell_7"
    )
    assert (
        policy._dig_depth_profile_fallback_reason == "kept_depth_profile_reason"
    )


def test_return_to_dig_config_is_applied_by_planner_init() -> None:
    policy = _make_policy(
        return_to_dig_shallow_guard_enabled=True,
        return_to_dig_max_bucket_mass_kg=2.5,
        return_to_dig_touch_tolerance_m=0.15,
        return_to_dig_min_depth_m=0.03,
        return_to_dig_max_depth_m=0.18,
        return_to_dig_max_entry_error_m="0.55",
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_start_envelope_spatial_tolerance=0.20,
        return_to_dig_start_envelope_depth_tolerance_m=0.07,
        return_to_dig_start_envelope_local_depth_tolerance_m=0.006,
        return_to_dig_start_envelope_plane_depth_tolerance_m=0.025,
        return_to_dig_start_envelope_plane_depth_mode="median-floor",
        return_to_dig_start_envelope_qpos_tolerance=0.08,
        return_to_dig_start_envelope_require_contact=False,
        return_to_dig_start_envelope_direct_handoff_enabled=True,
        return_max_steps=12,
    )

    assert policy.return_to_dig_shallow_guard_enabled is True
    assert policy.return_to_dig_max_bucket_mass_kg == pytest.approx(2.5)
    assert policy.return_to_dig_touch_tolerance_m == pytest.approx(0.15)
    assert policy.return_to_dig_min_depth_m == pytest.approx(0.03)
    assert policy.return_to_dig_max_depth_m == pytest.approx(0.18)
    assert policy.return_to_dig_max_entry_error_m == pytest.approx(0.55)
    assert policy.return_to_dig_start_envelope_gate_enabled is True
    assert policy.return_to_dig_start_envelope_spatial_tolerance == pytest.approx(0.20)
    assert policy.return_to_dig_start_envelope_depth_tolerance_m == pytest.approx(0.07)
    assert policy.return_to_dig_start_envelope_local_depth_tolerance_m == pytest.approx(
        0.006
    )
    assert policy.return_to_dig_start_envelope_plane_depth_tolerance_m == pytest.approx(
        0.025
    )
    assert policy.return_to_dig_start_envelope_plane_depth_mode == "p50_floor"
    assert policy.return_to_dig_start_envelope_qpos_tolerance == pytest.approx(0.08)
    assert policy.return_to_dig_start_envelope_require_contact is False
    assert policy.return_to_dig_start_envelope_direct_handoff_enabled is True
    assert policy.return_max_steps == 12


def test_dump_lifecycle_config_is_applied_by_planner_init() -> None:
    policy = _make_policy(
        dump_ready_min_bucket_mass_kg=12.0,
        dump_ready_min_height_above_rim_m=-0.1,
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=False,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m=0.3,
        dump_ready_min_dump_area_relative_x_m=-0.2,
        dump_ready_max_dump_area_relative_x_m=0.4,
        dump_ready_min_dump_area_relative_z_m="0.5",
        dump_ready_max_dump_area_relative_z_m="1.5",
        dump_ready_hold_steps=0,
        dump_ready_near_window_enabled=True,
        dump_ready_near_window_x_tolerance_m=0.03,
        dump_ready_near_window_z_tolerance_m=0.04,
        dump_ready_near_window_outside_tolerance_m=0.02,
        dump_ready_near_window_require_over_footprint=False,
        dump_done_max_bucket_mass_kg=8.0,
        dump_done_min_deposit_delta_kg=2.5,
        dump_done_hold_steps=0,
        dump_done_use_boundary_event=False,
    )

    assert policy.dump_ready_min_bucket_mass_kg == pytest.approx(12.0)
    assert policy.dump_ready_min_height_above_rim_m == pytest.approx(-0.1)
    assert policy.dump_ready_require_over_footprint is False
    assert policy.dump_ready_require_clearance is False
    assert policy.dump_ready_max_horizontal_distance_m is None
    assert policy.dump_ready_position_mode == "dump_area_relative"
    assert (
        policy.dump_ready_max_dump_area_footprint_outside_distance_m
        == pytest.approx(0.3)
    )
    assert policy.dump_ready_min_dump_area_relative_x_m == pytest.approx(-0.2)
    assert policy.dump_ready_max_dump_area_relative_x_m == pytest.approx(0.4)
    assert policy.dump_ready_min_dump_area_relative_z_m == pytest.approx(0.5)
    assert policy.dump_ready_max_dump_area_relative_z_m == pytest.approx(1.5)
    assert policy.dump_ready_hold_steps == 1
    assert policy.dump_ready_near_window_enabled is True
    assert policy.dump_ready_near_window_x_tolerance_m == pytest.approx(0.03)
    assert policy.dump_ready_near_window_z_tolerance_m == pytest.approx(0.04)
    assert policy.dump_ready_near_window_outside_tolerance_m == pytest.approx(0.02)
    assert policy.dump_ready_near_window_require_over_footprint is False
    assert policy.dump_done_max_bucket_mass_kg == pytest.approx(8.0)
    assert policy.dump_done_min_deposit_delta_kg == pytest.approx(2.5)
    assert policy.dump_done_hold_steps == 1
    assert policy.dump_done_use_boundary_event is False


def test_bootstrap_config_is_applied_by_planner_init() -> None:
    policy = _make_policy(
        bootstrap_end_mode="scripted_qpos",
        bootstrap_end_min_bucket_mass_kg=12.0,
        bootstrap_end_min_distance_to_dig_area_m=0.5,
        scripted_bootstrap_target_qpos=[0.1, 0.2, 0.3, 0.4],
        scripted_bootstrap_kp=3.0,
        scripted_bootstrap_kd=0.75,
        scripted_bootstrap_action_clip=[0.1, 0.2, 0.3, 0.4],
        scripted_bootstrap_action_signs=[1.0, -1.0, 1.0, -1.0],
        scripted_bootstrap_qpos_tolerance=0.03,
        scripted_bootstrap_qvel_abs_max=0.09,
        scripted_bootstrap_hold_steps=0,
        scripted_bootstrap_max_steps=0,
    )

    assert policy.bootstrap_end_mode == "scripted_qpos"
    assert policy.bootstrap_end_min_bucket_mass_kg == pytest.approx(12.0)
    assert policy.bootstrap_end_min_distance_to_dig_area_m == pytest.approx(0.5)
    np.testing.assert_allclose(
        policy.scripted_bootstrap_target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert policy.scripted_bootstrap_target_qpos.dtype == np.float32
    assert policy.scripted_bootstrap_kp == pytest.approx(3.0)
    assert policy.scripted_bootstrap_kd == pytest.approx(0.75)
    assert policy.scripted_bootstrap_action_clip == [0.1, 0.2, 0.3, 0.4]
    np.testing.assert_allclose(
        policy.scripted_bootstrap_action_signs,
        np.asarray([1.0, -1.0, 1.0, -1.0], dtype=np.float32),
    )
    assert policy.scripted_bootstrap_action_signs.dtype == np.float32
    assert policy.scripted_bootstrap_qpos_tolerance == pytest.approx(0.03)
    assert policy.scripted_bootstrap_qvel_abs_max == pytest.approx(0.09)
    assert policy.scripted_bootstrap_hold_steps == 1
    assert policy.scripted_bootstrap_max_steps == 1


def test_goal_sequence_config_is_applied_by_planner_init() -> None:
    policy = _make_policy(
        goal_sequence=["right", "mid"],
        goal_scenario_id=321,
        goal_depth_norm="0.4",
        goal_dump_target_norm=2,
    )

    assert policy.goal_sequence == (2, 1)
    assert policy.goal_scenario_id == "321"
    assert policy.goal_depth_norm == pytest.approx(0.4)
    assert policy.goal_dump_target_norm == pytest.approx(2.0)
    assert policy._goal_sector_id(0) == 2
    assert policy._next_goal_sector_id() == 1


def test_cell_entry_config_is_applied_by_planner_init() -> None:
    policy = _make_policy(
        cell_entry_enabled=True,
        cell_entry_grid={
            "half_long_m": 2.0,
            "half_short_m": 1.0,
            "entry_margin_m": 0.1,
        },
        cell_entry_low_productivity_payload_gain_kg=45,
    )

    assert policy.cell_entry_enabled is True
    assert isinstance(policy.cell_entry_grid, CellGridSpec)
    assert policy.cell_entry_grid.half_long_m == pytest.approx(2.0)
    assert policy.cell_entry_grid.half_short_m == pytest.approx(1.0)
    assert policy.cell_entry_grid.entry_margin_m == pytest.approx(0.1)
    assert policy.cell_entry_planner.grid is policy.cell_entry_grid
    assert policy.cell_entry_auditor.grid is policy.cell_entry_grid
    assert (
        policy.cell_entry_low_productivity_payload_gain_kg == pytest.approx(45.0)
    )
    assert (
        policy.cell_entry_auditor.low_productivity_payload_gain_kg
        == pytest.approx(45.0)
    )


def test_dig_lifecycle_config_is_applied_by_planner_init() -> None:
    policy = _make_policy(
        dig_to_carry_min_bucket_mass_kg=15.0,
        dig_to_carry_min_distance_to_dig_area_m=0.25,
        dig_to_carry_target_bucket_mass_kg=45.0,
        dig_to_carry_mass_plateau_enabled=True,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=25.0,
        dig_to_carry_mass_plateau_epsilon_kg=0.5,
        dig_to_carry_mass_plateau_hold_steps=0,
        dig_to_carry_mass_plateau_min_steps=0,
        dig_bad_replan_enabled=True,
        dig_bad_replan_max_steps=0,
        dig_bad_replan_min_bucket_mass_kg=5.0,
        dig_exit_guard_enabled=True,
        dig_exit_guard_min_steps=0,
        dig_exit_guard_overshoot_m=0.2,
        dig_exit_guard_min_bucket_mass_kg=7.0,
        dig_failed_replan_next_skill="terminal-stop",
    )

    assert policy.dig_to_carry_min_bucket_mass_kg == pytest.approx(15.0)
    assert policy.dig_to_carry_min_distance_to_dig_area_m == pytest.approx(0.25)
    assert policy.dig_to_carry_target_bucket_mass_kg == pytest.approx(45.0)
    assert policy.dig_to_carry_mass_plateau_enabled is True
    assert policy.dig_to_carry_mass_plateau_min_bucket_mass_kg == pytest.approx(25.0)
    assert policy.dig_to_carry_mass_plateau_epsilon_kg == pytest.approx(0.5)
    assert policy.dig_to_carry_mass_plateau_hold_steps == 1
    assert policy.dig_to_carry_mass_plateau_min_steps == 1
    assert policy.dig_bad_replan_enabled is True
    assert policy.dig_bad_replan_max_steps == 1
    assert policy.dig_bad_replan_min_bucket_mass_kg == pytest.approx(5.0)
    assert policy.dig_exit_guard_enabled is True
    assert policy.dig_exit_guard_min_steps == 1
    assert policy.dig_exit_guard_overshoot_m == pytest.approx(0.2)
    assert policy.dig_exit_guard_min_bucket_mass_kg == pytest.approx(7.0)
    assert policy.dig_failed_replan_next_skill == "stop"


def test_reset_dig_cut_runtime_applies_service_state() -> None:
    policy = _make_policy()
    tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)

    def initial_runtime_state() -> DigCutRuntimeState:
        return DigCutRuntimeState(
            tokens=tokens,
            token_injected=True,
            planned_cycle_id=8,
            token_source="operator_prior_pose_clamped",
            fallback_reason="missing_bucket_dig_area_pose",
            token_in_prior_p10_p90=True,
        )

    policy.dig_cut_plan_service.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()
    tokens[0] = 99.0

    np.testing.assert_allclose(
        policy._dig_cut_tokens,
        np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32),
    )
    assert policy._dig_cut_tokens.dtype == np.float32
    assert policy._dig_cut_token_injected is True
    assert policy._dig_cut_planned_cycle_id == 8
    assert policy._dig_cut_token_source == "operator_prior_pose_clamped"
    assert policy._dig_cut_fallback_reason == "missing_bucket_dig_area_pose"
    assert policy._dig_cut_token_in_prior_p10_p90 is True


def test_reset_dig_depth_profile_runtime_applies_service_state() -> None:
    policy = _make_policy()
    tokens = np.arange(12, dtype=np.float64)

    def initial_runtime_state() -> DigDepthProfileRuntimeState:
        return DigDepthProfileRuntimeState(
            tokens=tokens,
            token_injected=True,
            token_source="qc6_dig_depth_profile_cell_3",
            fallback_reason="missing_dig_depth_profile_prior",
        )

    policy.dig_depth_profile_service.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()
    tokens[0] = 99.0

    np.testing.assert_allclose(
        policy._dig_depth_profile_tokens,
        np.arange(12, dtype=np.float32),
    )
    assert policy._dig_depth_profile_tokens.dtype == np.float32
    assert policy._dig_depth_profile_token_injected is True
    assert (
        policy._dig_depth_profile_token_source == "qc6_dig_depth_profile_cell_3"
    )
    assert (
        policy._dig_depth_profile_fallback_reason
        == "missing_dig_depth_profile_prior"
    )


def _obs(
    *,
    bucket_pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
    deposited_mass: float = 0.0,
) -> dict[str, np.ndarray]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited_mass)
    return {
        "env_state": env_state,
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
    }


def _make_policy(**kwargs: Any) -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
        **kwargs,
    )


def _raw_fields() -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.5,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": -0.25,
        "operator_exit_x_m": -0.5,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": -0.25,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.0,
        "operator_cut_depth_peak_m": 0.08,
        "operator_cut_payload_gain_kg": 40.0,
        "operator_effective_deposit_delta_kg": 38.0,
        "operator_cut_valid": 1,
    }


class _ConstantPolicy(Policy):
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    def __init__(self) -> None:
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": "legacy"},
        )()

    def reset(self) -> None:
        pass

    def update(self, obs: dict, action: np.ndarray | None = None) -> Any:
        return None
