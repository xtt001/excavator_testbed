from __future__ import annotations

from types import MethodType

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_token_runtime_state_fresh_matches_legacy_reset_defaults() -> None:
    state = PrimitiveTokenRuntimeState.fresh()

    assert state.dig_cut_planned_cycle_id == -1
    assert state.dig_cut_tokens.dtype == np.float32
    assert state.dig_cut_tokens.shape == (DIG_CUT_TOKEN_DIM,)
    assert state.dig_depth_profile_tokens.dtype == np.float32
    assert state.dig_depth_profile_tokens.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert state.dig_cut_token_source == "none"
    assert state.dig_cut_fallback_reason == ""
    assert state.dig_cut_token_in_prior_p10_p90 is False
    assert state.dig_depth_profile_token_source == "none"
    assert state.dig_depth_profile_fallback_reason == ""
    assert state.return_target_planned_cycle_id == -1
    assert state.return_target_tokens.dtype == np.float32
    assert state.return_target_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert state.return_relocate_tokens.dtype == np.float32
    assert state.return_relocate_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert state.return_start_envelope_tokens.dtype == np.float32
    assert state.return_start_envelope_tokens.shape == (
        RETURN_START_ENVELOPE_TOKEN_DIM,
    )
    assert state.return_target_token_source == "none"
    assert state.return_target_fallback_reason == ""
    assert state.return_start_envelope_token_source == "none"
    assert state.return_start_envelope_use_prior_spatial_bounds is True
    assert state.return_start_envelope_use_prior_qpos_bounds is True
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_corridor_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_cut_tokens is None
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == []
    assert np.isnan(state.pending_dig_state_exemplar_distance)


def test_token_runtime_state_fresh_does_not_alias_mutable_values() -> None:
    first = PrimitiveTokenRuntimeState.fresh()
    second = PrimitiveTokenRuntimeState.fresh()

    first.dig_cut_tokens[0] = 7.0
    first.return_target_tokens[0] = 8.0
    first.pending_dig_state_exemplar_ids.append("changed")
    first.pending_dig_cut_raw_fields = {"x": 1.0}

    assert second.dig_cut_tokens[0] == 0.0
    assert second.return_target_tokens[0] == 0.0
    assert second.pending_dig_state_exemplar_ids == []
    assert second.pending_dig_cut_raw_fields is None
    assert first.dig_cut_tokens is not second.dig_cut_tokens
    assert first.pending_dig_state_exemplar_ids is not second.pending_dig_state_exemplar_ids


def test_policy_legacy_token_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_token_runtime_state()

    policy._dig_cut_tokens = np.ones(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    policy._pending_dig_cut_cycle_id = 42
    policy._return_target_tokens = np.full(
        RETURN_TARGET_TOKEN_DIM,
        3.0,
        dtype=np.float32,
    )
    policy._return_start_envelope_use_prior_qpos_bounds = False
    policy._pending_dig_state_exemplar_ids = ["a", "b"]

    assert policy._primitive_token_runtime_state() is state
    assert policy._dig_cut_tokens is state.dig_cut_tokens
    assert float(state.dig_cut_tokens[0]) == 1.0
    assert state.pending_dig_cut_cycle_id == 42
    assert policy._return_target_tokens is state.return_target_tokens
    assert float(state.return_target_tokens[0]) == 3.0
    assert state.return_start_envelope_use_prior_qpos_bounds is False
    assert policy._pending_dig_state_exemplar_ids is state.pending_dig_state_exemplar_ids


def test_policy_reset_application_replaces_token_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_token_runtime_state()
    old_state.dig_cut_tokens[0] = 9.0
    old_state.pending_dig_state_exemplar_ids.append("old")
    reset_state = PrimitiveTokenRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_token_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())

    assert policy._primitive_token_runtime_state() is reset_state
    assert policy._primitive_token_runtime_state() is not old_state
    assert policy._dig_cut_tokens[0] == 0.0
    assert policy._pending_dig_state_exemplar_ids == []
    assert policy._dig_cut_tokens is not old_state.dig_cut_tokens


def test_token_runtime_ports_and_clear_facade_use_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_token_runtime_state()
    policy._skill_name = "dig"
    policy._cycle_index = 0
    policy.dig_cut_planner_enabled = True
    policy.dig_cut_hold_token_until_skill_exit = False
    policy.return_target_planner_enabled = True
    policy.return_target_hold_token_until_skill_exit = False
    policy.bootstrap_policy = None
    policy._coverage_terminal_stop_requested = False
    policy._coverage_runtime_state = MethodType(
        lambda self: type(
            "_CoverageState",
            (),
            {"clear_active_state_exemplar": lambda self: None},
        )(),
        policy,
    )
    ports = policy._primitive_token_runtime_ports()

    ports.set_dig_cut_planned_cycle_id(12)
    ports.set_dig_cut_tokens(np.full(DIG_CUT_TOKEN_DIM, 5.0, dtype=np.float32))
    ports.set_pending_dig_cut_cycle_id(13)

    assert state.dig_cut_planned_cycle_id == 12
    assert ports.get_dig_cut_tokens() is state.dig_cut_tokens
    assert state.pending_dig_cut_cycle_id == 13

    policy._clear_dig_cut_plan()

    assert state.dig_cut_planned_cycle_id == -1
    assert state.dig_cut_token_source == "none"
    assert state.dig_cut_fallback_reason == ""
    assert state.dig_cut_token_in_prior_p10_p90 is False
    assert state.dig_cut_tokens.shape == (DIG_CUT_TOKEN_DIM,)
    assert state.dig_depth_profile_tokens.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
