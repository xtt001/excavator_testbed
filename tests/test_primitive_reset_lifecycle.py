from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
from types import MethodType
from typing import Any

import numpy as np
import pytest

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.reset_lifecycle import (
    PrimitiveResetLifecyclePorts,
    PrimitiveResetLifecycleService,
)
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import (
    BOOTSTRAP_SKILL_NAME,
    PRE_DIG_ALIGN_SKILL_NAME,
    PrimitivePlannerACTPolicy,
)


_OBSERVATION_INJECTION_FLAG_NAMES = {
    "cell_entry_token_injected",
    "dig_cut_token_injected",
    "dig_depth_profile_token_injected",
    "return_target_token_injected",
    "return_relocate_token_injected",
    "return_start_envelope_token_injected",
}

_CYCLE_PROGRESS_FIELD_NAMES = {
    "dump_ready_hold_count",
    "dump_done_hold_count",
    "dig_step_count",
    "dig_best_mass_kg",
    "dig_mass_plateau_count",
    "dig_to_carry_reason",
    "dig_bad_replan_count",
    "dig_exit_guard_replan_count",
    "completed_transition_count",
    "transition_timeout_count",
    "cycle_index",
    "dump_start_deposited_mass_kg",
}

_RETURN_RUNTIME_FIELD_NAMES = {
    "return_step_count",
    "return_to_dig_entry_error_m",
    "return_to_dig_entry_close_state",
    "return_next_dig_event_seen",
    "return_to_dig_start_envelope_ready_state",
    "return_to_dig_start_envelope_error",
    "return_to_dig_start_envelope_checks",
}

_TOKEN_RUNTIME_FIELD_NAMES = {
    "dig_cut_planned_cycle_id",
    "dig_cut_tokens",
    "dig_depth_profile_tokens",
    "dig_cut_token_source",
    "dig_cut_fallback_reason",
    "dig_cut_token_in_prior_p10_p90",
    "dig_depth_profile_token_source",
    "dig_depth_profile_fallback_reason",
    "return_target_planned_cycle_id",
    "return_target_tokens",
    "return_relocate_tokens",
    "return_start_envelope_tokens",
    "return_target_token_source",
    "return_target_fallback_reason",
    "return_start_envelope_token_source",
    "return_start_envelope_use_prior_spatial_bounds",
    "return_start_envelope_use_prior_qpos_bounds",
    "pending_dig_cut_cycle_id",
    "pending_dig_cut_corridor_id",
    "pending_dig_cut_raw_fields",
    "pending_dig_cut_tokens",
    "pending_dig_depth_profile_tokens",
    "pending_dig_state_exemplar_ids",
    "pending_dig_state_exemplar_distance",
}

_COVERAGE_RUNTIME_FIELD_NAMES = {
    "coverage_corridors",
    "coverage_active_corridor_id",
    "coverage_last_selected_corridor_id",
    "coverage_current_payload_gain_kg",
    "coverage_cycle_start_deposit_kg",
    "coverage_last_payload_gain_kg",
    "coverage_last_effective_deposit_delta_kg",
    "coverage_global_low_productivity_streak",
    "coverage_completed_dump_count",
    "coverage_pass_index",
    "coverage_terminal_stop_requested",
    "coverage_terminal_stop_reason",
    "coverage_candidate_scores",
    "coverage_decision_trace",
    "coverage_active_state_exemplar_ids",
    "coverage_rejected_state_exemplar_ids",
    "coverage_active_state_exemplar_distance",
    "coverage_active_state_exemplar_profile_token",
}

_SCRIPTED_BOOTSTRAP_COUNTER_FIELD_NAMES = {
    "scripted_bootstrap_step_count",
    "scripted_bootstrap_hold_count",
    "scripted_bootstrap_timeout_count",
}


class _Policy:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def reset(self) -> None:
        self.events.append(f"reset:{self.name}")


def _ports(
    *,
    events: list[str] | None = None,
    bootstrap_end_mode: str = "disabled",
    bootstrap_policy_available: bool = False,
    scripted_bootstrap_enabled: bool = False,
    should_pre_dig_align_before_dig: bool = False,
    action_dim: int = 4,
) -> tuple[PrimitiveResetLifecyclePorts, list[str]]:
    events = events if events is not None else []
    policies = [_Policy(name, events) for name in ("dig", "carry", "dump", "return")]

    return (
        PrimitiveResetLifecyclePorts(
            all_policies=lambda: policies,
            reset_boundary_detector=lambda: events.append("boundary_reset"),
            bootstrap_end_mode=lambda: bootstrap_end_mode,
            bootstrap_policy_available=lambda: bootstrap_policy_available,
            scripted_bootstrap_enabled=lambda: scripted_bootstrap_enabled,
            should_pre_dig_align_before_dig=lambda: should_pre_dig_align_before_dig,
            action_dim=action_dim,
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            dig_skill_name="dig",
        ),
        events,
    )


def test_reset_service_resets_policies_then_boundary() -> None:
    ports, events = _ports()

    PrimitiveResetLifecycleService.from_ports(ports).reset()

    assert events == [
        "reset:dig",
        "reset:carry",
        "reset:dump",
        "reset:return",
        "boundary_reset",
    ]


@pytest.mark.parametrize(
    (
        "bootstrap_end_mode",
        "bootstrap_policy_available",
        "scripted_bootstrap_enabled",
        "should_pre_dig_align_before_dig",
        "expected_skill",
    ),
    [
        ("first_qualified_dig_start", True, False, True, BOOTSTRAP_SKILL_NAME),
        ("scripted_qpos", False, True, True, BOOTSTRAP_SKILL_NAME),
        ("disabled", False, False, True, PRE_DIG_ALIGN_SKILL_NAME),
        ("disabled", False, False, False, "dig"),
    ],
)
def test_reset_service_selects_initial_skill_from_bootstrap_pre_dig_or_dig(
    bootstrap_end_mode: str,
    bootstrap_policy_available: bool,
    scripted_bootstrap_enabled: bool,
    should_pre_dig_align_before_dig: bool,
    expected_skill: str,
) -> None:
    ports, _ = _ports(
        bootstrap_end_mode=bootstrap_end_mode,
        bootstrap_policy_available=bootstrap_policy_available,
        scripted_bootstrap_enabled=scripted_bootstrap_enabled,
        should_pre_dig_align_before_dig=should_pre_dig_align_before_dig,
    )

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()

    assert state.skill_name == expected_skill
    assert state.switch_reason == "reset"
    assert state.prev_action is None
    assert state.debug_transition_timeout is False
    assert state.debug_transition_completed is False


def test_reset_state_matches_legacy_counter_token_pending_and_coverage_defaults() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()

    assert state.cycle_state.dump_ready_hold_count == 0
    assert state.cycle_state.dump_done_hold_count == 0
    assert state.return_state.return_step_count == 0
    assert state.scripted_bootstrap_state.step_count == 0
    assert state.scripted_bootstrap_state.hold_count == 0
    assert state.scripted_bootstrap_state.timeout_count == 0
    assert state.cycle_state.dig_step_count == 0
    assert state.cycle_state.dig_best_mass_kg == 0.0
    assert state.cycle_state.dig_mass_plateau_count == 0
    assert state.cycle_state.dig_to_carry_reason == ""
    assert state.cycle_state.dig_bad_replan_count == 0
    assert state.cycle_state.dig_exit_guard_replan_count == 0
    assert state.cycle_state.completed_transition_count == 0
    assert state.cycle_state.transition_timeout_count == 0
    assert state.cycle_state.cycle_index == 0
    assert state.cycle_state.dump_start_deposited_mass_kg == 0.0
    assert state.observation_injection_state.to_token_injection_state() == (
        state.observation_injection_state.fresh().to_token_injection_state()
    )
    token_state = state.token_state
    assert token_state.dig_cut_tokens.dtype == np.float32
    assert token_state.dig_cut_tokens.shape == (DIG_CUT_TOKEN_DIM,)
    assert token_state.dig_cut_token_source == "none"
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is False
    assert token_state.dig_depth_profile_tokens.dtype == np.float32
    assert token_state.dig_depth_profile_tokens.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert token_state.dig_depth_profile_token_source == "none"
    assert token_state.dig_depth_profile_fallback_reason == ""
    assert token_state.return_target_tokens.dtype == np.float32
    assert token_state.return_target_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert token_state.return_relocate_tokens.dtype == np.float32
    assert token_state.return_relocate_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert token_state.return_start_envelope_tokens.dtype == np.float32
    assert token_state.return_start_envelope_tokens.shape == (
        RETURN_START_ENVELOPE_TOKEN_DIM,
    )
    assert token_state.return_start_envelope_token_source == "none"
    assert token_state.return_start_envelope_use_prior_spatial_bounds is True
    assert token_state.return_start_envelope_use_prior_qpos_bounds is True


def test_reset_lifecycle_no_longer_emits_cycle_progress_field_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_policy_update_names = {f"_{name}" for name in _CYCLE_PROGRESS_FIELD_NAMES}

    assert _CYCLE_PROGRESS_FIELD_NAMES.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert "_cycle_state" in updates
    assert updates["_cycle_state"] is state.cycle_state


def test_reset_lifecycle_no_longer_emits_return_runtime_field_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_policy_update_names = {f"_{name}" for name in _RETURN_RUNTIME_FIELD_NAMES}

    assert _RETURN_RUNTIME_FIELD_NAMES.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert "_return_state" in updates
    assert updates["_return_state"] is state.return_state


def test_reset_lifecycle_no_longer_emits_observation_injection_flag_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_policy_update_names = {
        f"_{name}" for name in _OBSERVATION_INJECTION_FLAG_NAMES
    }

    assert _OBSERVATION_INJECTION_FLAG_NAMES.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert "_observation_injection_state" in updates
    assert updates["_observation_injection_state"] is state.observation_injection_state


def test_reset_lifecycle_no_longer_emits_cell_entry_runtime_field_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_field_names = {
        "cell_entry_state",
        "cell_entry_goal",
        "cell_entry_goal_cycle_id",
        "cell_entry_audit",
        "cell_entry_tokens",
        "cell_entry_seen_cell_id",
        "cell_entry_trace",
    }
    removed_policy_update_names = {
        "_cell_entry_state",
        "_cell_entry_goal",
        "_cell_entry_goal_cycle_id",
        "_cell_entry_audit",
        "_cell_entry_tokens",
        "_cell_entry_seen_cell_id",
        "_cell_entry_trace",
    }

    assert removed_field_names.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert state.token_state.return_target_planned_cycle_id == -1
    assert state.token_state.return_target_token_source == "none"
    assert state.token_state.return_target_fallback_reason == ""
    assert np.isnan(state.return_state.return_to_dig_entry_error_m)
    assert state.return_state.return_to_dig_entry_close_state is True
    assert state.return_state.return_next_dig_event_seen is False
    assert state.return_state.return_to_dig_start_envelope_ready_state is True
    assert np.isnan(state.return_state.return_to_dig_start_envelope_error)
    assert state.return_state.return_to_dig_start_envelope_checks == {}
    assert state.token_state.pending_dig_cut_cycle_id == -1
    assert state.token_state.pending_dig_cut_corridor_id == -1
    assert state.token_state.pending_dig_cut_raw_fields is None
    assert state.token_state.pending_dig_cut_tokens is None
    assert state.token_state.pending_dig_depth_profile_tokens is None
    assert state.token_state.pending_dig_state_exemplar_ids == []
    assert np.isnan(state.token_state.pending_dig_state_exemplar_distance)
    assert state.token_state.dig_cut_planned_cycle_id == -1
    assert isinstance(state.coverage_state, CoverageRuntimeState)
    assert state.coverage_state.coverage_corridors == []
    assert state.coverage_state.coverage_active_corridor_id == -1


def test_reset_lifecycle_no_longer_emits_pre_dig_align_runtime_field_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_field_names = {
        "pre_dig_align_state",
        "pre_dig_align_step_count",
        "pre_dig_align_hold_count",
        "pre_dig_align_timeout_count",
        "pre_dig_align_completed_count",
        "pre_dig_align_replan_count",
        "pre_dig_align_target_qpos",
        "pre_dig_align_error",
        "pre_dig_align_entry_error_m",
        "pre_dig_align_start_envelope_ready",
        "pre_dig_align_entry_close_handoff_ready",
        "pre_dig_align_entry_intent_handoff_ready",
        "pre_dig_align_timeout_handoff_reason",
        "pre_dig_align_surface_depth_m",
        "pre_dig_align_surface_guard_triggered",
        "pre_dig_align_surface_guard_count",
    }
    removed_policy_update_names = {f"_{name}" for name in removed_field_names}

    assert removed_field_names.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)


def test_reset_lifecycle_resets_live_pre_dig_align_runtime_state_owner() -> None:
    ports, _ = _ports(action_dim=6)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()

    assert isinstance(
        state.pre_dig_align_runtime_state,
        PrimitivePreDigAlignRuntimeState,
    )
    assert state.pre_dig_align_runtime_state.step_count == 0
    assert state.pre_dig_align_runtime_state.hold_count == 0
    assert state.pre_dig_align_runtime_state.timeout_count == 0
    assert state.pre_dig_align_runtime_state.completed_count == 0
    assert state.pre_dig_align_runtime_state.replan_count == 0
    assert state.pre_dig_align_runtime_state.target_qpos.shape == (6,)
    assert state.pre_dig_align_runtime_state.error.shape == (6,)
    assert "_pre_dig_align_runtime_state" in updates
    assert updates["_pre_dig_align_runtime_state"] is state.pre_dig_align_runtime_state


def test_reset_lifecycle_no_longer_emits_token_runtime_field_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_policy_update_names = {f"_{name}" for name in _TOKEN_RUNTIME_FIELD_NAMES}

    assert _TOKEN_RUNTIME_FIELD_NAMES.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert "_token_state" in updates
    assert state.token_state.dig_cut_planned_cycle_id == -1
    assert state.token_state.return_target_planned_cycle_id == -1
    assert state.token_state.pending_dig_cut_cycle_id == -1


def test_reset_lifecycle_no_longer_emits_coverage_runtime_field_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_policy_update_names = {f"_{name}" for name in _COVERAGE_RUNTIME_FIELD_NAMES}

    assert _COVERAGE_RUNTIME_FIELD_NAMES.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert "_coverage_state" in updates
    assert updates["_coverage_state"] is state.coverage_state


def test_reset_lifecycle_no_longer_emits_scripted_bootstrap_counter_updates() -> None:
    ports, _ = _ports(action_dim=4)

    state = PrimitiveResetLifecycleService.from_ports(ports).reset()
    updates = state.as_policy_field_updates()
    removed_policy_update_names = {
        f"_{name}" for name in _SCRIPTED_BOOTSTRAP_COUNTER_FIELD_NAMES
    }

    assert _SCRIPTED_BOOTSTRAP_COUNTER_FIELD_NAMES.isdisjoint(
        {field.name for field in fields(type(state))}
    )
    assert removed_policy_update_names.isdisjoint(updates)
    assert "_scripted_bootstrap_state" in updates
    assert updates["_scripted_bootstrap_state"] is state.scripted_bootstrap_state


def test_reset_service_returns_fresh_mutable_arrays_and_containers() -> None:
    ports, _ = _ports()
    service = PrimitiveResetLifecycleService.from_ports(ports)

    first = service.reset()
    second = service.reset()
    first.token_state.dig_cut_tokens[0] = 99.0
    first.return_state.return_to_dig_start_envelope_checks["changed"] = True

    assert second.token_state.dig_cut_tokens[0] == 0.0
    assert second.return_state.return_to_dig_start_envelope_checks == {}
    assert first.token_state.dig_cut_tokens is not second.token_state.dig_cut_tokens
    assert first.coverage_state is not second.coverage_state


def test_policy_reset_delegates_to_service_and_finalizes_initial_debug_state() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    reset_state = SimpleNamespace(
        debug_transition_timeout=False,
        debug_transition_completed=False,
    )
    debug_state = object()
    events: list[str] = []

    class _FakeResetService:
        def reset(self) -> object:
            events.append("service_reset")
            return reset_state

    policy._primitive_reset_lifecycle_service = MethodType(
        lambda self: _FakeResetService(),
        policy,
    )
    policy._apply_reset_lifecycle_state = MethodType(
        lambda self, state: events.append(f"apply:{state is reset_state}"),
        policy,
    )
    class _FakeTickFinalizationRuntime:
        def make_debug_state(
            self,
            *,
            transition_timeout: bool,
            transition_completed: bool,
        ) -> object:
            events.append(f"debug:{transition_timeout}:{transition_completed}")
            return debug_state

    policy._primitive_tick_finalization_runtime = MethodType(
        lambda self: _FakeTickFinalizationRuntime(),
        policy,
    )

    policy.reset()

    assert events == ["service_reset", "apply:True", "debug:False:False"]
    assert policy._debug_state is debug_state


def test_reset_lifecycle_boundary_uses_typed_ports_without_planner_self() -> None:
    port_fields = {field.name for field in fields(PrimitiveResetLifecyclePorts)}
    service_fields = {field.name for field in fields(PrimitiveResetLifecycleService)}

    assert "planner" not in port_fields
    assert "self" not in port_fields
    assert service_fields == {"ports"}
