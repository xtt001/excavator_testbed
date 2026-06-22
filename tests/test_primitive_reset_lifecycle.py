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
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_reset_lifecycle import (
    PrimitiveResetLifecyclePorts,
    PrimitiveResetLifecycleService,
)
from testbed.policies.hybrid.primitive_planner import (
    BOOTSTRAP_SKILL_NAME,
    PRE_DIG_ALIGN_SKILL_NAME,
    PrimitivePlannerACTPolicy,
)


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
    pre_dig_align_before_dig: bool = False,
    action_dim: int = 4,
) -> tuple[PrimitiveResetLifecyclePorts, list[str]]:
    events = events if events is not None else []
    policies = [_Policy(name, events) for name in ("dig", "carry", "dump", "return")]

    return (
        PrimitiveResetLifecyclePorts(
            all_policies=lambda: policies,
            reset_boundary_detector=lambda: events.append("boundary_reset"),
            reset_cell_entry_planner=lambda: events.append("cell_entry_reset"),
            bootstrap_end_mode=lambda: bootstrap_end_mode,
            bootstrap_policy_available=lambda: bootstrap_policy_available,
            scripted_bootstrap_enabled=lambda: scripted_bootstrap_enabled,
            should_pre_dig_align_before_dig=lambda: pre_dig_align_before_dig,
            action_dim=action_dim,
            bootstrap_skill_name=BOOTSTRAP_SKILL_NAME,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
            dig_skill_name="dig",
        ),
        events,
    )


def test_reset_service_resets_policies_then_boundary_then_cell_entry() -> None:
    ports, events = _ports()

    PrimitiveResetLifecycleService.from_ports(ports).reset()

    assert events == [
        "reset:dig",
        "reset:carry",
        "reset:dump",
        "reset:return",
        "boundary_reset",
        "cell_entry_reset",
    ]


@pytest.mark.parametrize(
    (
        "bootstrap_end_mode",
        "bootstrap_policy_available",
        "scripted_bootstrap_enabled",
        "pre_dig_align_before_dig",
        "expected_skill",
    ),
    [
        ("first_qualified_dig_start", True, False, False, BOOTSTRAP_SKILL_NAME),
        ("scripted_qpos", False, True, False, BOOTSTRAP_SKILL_NAME),
        ("disabled", False, False, True, PRE_DIG_ALIGN_SKILL_NAME),
        ("disabled", False, False, False, "dig"),
    ],
)
def test_reset_service_selects_initial_skill_from_bootstrap_and_pre_dig_gates(
    bootstrap_end_mode: str,
    bootstrap_policy_available: bool,
    scripted_bootstrap_enabled: bool,
    pre_dig_align_before_dig: bool,
    expected_skill: str,
) -> None:
    ports, _ = _ports(
        bootstrap_end_mode=bootstrap_end_mode,
        bootstrap_policy_available=bootstrap_policy_available,
        scripted_bootstrap_enabled=scripted_bootstrap_enabled,
        pre_dig_align_before_dig=pre_dig_align_before_dig,
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

    assert state.dump_ready_hold_count == 0
    assert state.dump_done_hold_count == 0
    assert state.return_step_count == 0
    assert state.scripted_bootstrap_step_count == 0
    assert state.scripted_bootstrap_hold_count == 0
    assert state.scripted_bootstrap_timeout_count == 0
    assert state.pre_dig_align_step_count == 0
    assert state.pre_dig_align_hold_count == 0
    assert state.pre_dig_align_timeout_count == 0
    assert state.pre_dig_align_completed_count == 0
    assert state.pre_dig_align_replan_count == 0
    assert state.pre_dig_align_target_qpos.dtype == np.float32
    assert state.pre_dig_align_target_qpos.shape == (4,)
    assert state.pre_dig_align_error.dtype == np.float32
    assert state.pre_dig_align_error.shape == (4,)
    assert np.isnan(state.pre_dig_align_entry_error_m)
    assert state.pre_dig_align_start_envelope_ready is False
    assert state.pre_dig_align_entry_close_handoff_ready is False
    assert state.pre_dig_align_entry_intent_handoff_ready is False
    assert state.pre_dig_align_timeout_handoff_reason == ""
    assert np.isnan(state.pre_dig_align_surface_depth_m)
    assert state.pre_dig_align_surface_guard_triggered is False
    assert state.pre_dig_align_surface_guard_count == 0
    assert state.dig_step_count == 0
    assert state.dig_best_mass_kg == 0.0
    assert state.dig_mass_plateau_count == 0
    assert state.dig_to_carry_reason == ""
    assert state.dig_bad_replan_count == 0
    assert state.dig_exit_guard_replan_count == 0
    assert state.completed_transition_count == 0
    assert state.transition_timeout_count == 0
    assert state.cycle_index == 0
    assert state.dump_start_deposited_mass_kg == 0.0
    assert state.cell_entry_goal is None
    assert state.cell_entry_goal_cycle_id == -1
    assert state.cell_entry_audit is None
    assert state.cell_entry_tokens.dtype == np.float32
    assert state.cell_entry_tokens.shape == (CELL_ENTRY_TOKEN_DIM,)
    assert state.cell_entry_token_injected is False
    assert state.dig_cut_tokens.dtype == np.float32
    assert state.dig_cut_tokens.shape == (DIG_CUT_TOKEN_DIM,)
    assert state.dig_cut_token_injected is False
    assert state.dig_cut_token_source == "none"
    assert state.dig_cut_fallback_reason == ""
    assert state.dig_cut_token_in_prior_p10_p90 is False
    assert state.dig_depth_profile_tokens.dtype == np.float32
    assert state.dig_depth_profile_tokens.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert state.dig_depth_profile_token_injected is False
    assert state.dig_depth_profile_token_source == "none"
    assert state.dig_depth_profile_fallback_reason == ""
    assert state.return_target_tokens.dtype == np.float32
    assert state.return_target_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert state.return_target_token_injected is False
    assert state.return_relocate_tokens.dtype == np.float32
    assert state.return_relocate_tokens.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert state.return_relocate_token_injected is False
    assert state.return_start_envelope_tokens.dtype == np.float32
    assert state.return_start_envelope_tokens.shape == (
        RETURN_START_ENVELOPE_TOKEN_DIM,
    )
    assert state.return_start_envelope_token_injected is False
    assert state.return_start_envelope_token_source == "none"
    assert state.return_start_envelope_use_prior_spatial_bounds is True
    assert state.return_start_envelope_use_prior_qpos_bounds is True
    assert state.return_target_planned_cycle_id == -1
    assert state.return_target_token_source == "none"
    assert state.return_target_fallback_reason == ""
    assert np.isnan(state.return_to_dig_entry_error_m)
    assert state.return_to_dig_entry_close_state is True
    assert state.return_next_dig_event_seen is False
    assert state.return_to_dig_start_envelope_ready_state is True
    assert np.isnan(state.return_to_dig_start_envelope_error)
    assert state.return_to_dig_start_envelope_checks == {}
    assert state.pending_dig_cut_cycle_id == -1
    assert state.pending_dig_cut_corridor_id == -1
    assert state.pending_dig_cut_raw_fields is None
    assert state.pending_dig_cut_tokens is None
    assert state.pending_dig_depth_profile_tokens is None
    assert state.pending_dig_state_exemplar_ids == []
    assert np.isnan(state.pending_dig_state_exemplar_distance)
    assert state.cell_entry_seen_cell_id == -1
    assert state.cell_entry_trace == []
    assert state.dig_cut_planned_cycle_id == -1
    assert isinstance(state.coverage_state, CoverageRuntimeState)
    assert state.coverage_state.coverage_corridors == []
    assert state.coverage_state.coverage_active_corridor_id == -1


def test_reset_service_returns_fresh_mutable_arrays_and_containers() -> None:
    ports, _ = _ports()
    service = PrimitiveResetLifecycleService.from_ports(ports)

    first = service.reset()
    second = service.reset()
    first.dig_cut_tokens[0] = 99.0
    first.cell_entry_trace.append({"changed": True})
    first.return_to_dig_start_envelope_checks["changed"] = True

    assert second.dig_cut_tokens[0] == 0.0
    assert second.cell_entry_trace == []
    assert second.return_to_dig_start_envelope_checks == {}
    assert first.dig_cut_tokens is not second.dig_cut_tokens
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
    policy._make_debug_state = MethodType(
        lambda self, *, transition_timeout, transition_completed: (
            events.append(f"debug:{transition_timeout}:{transition_completed}"),
            debug_state,
        )[1],
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
