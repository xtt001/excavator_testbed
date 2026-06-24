from __future__ import annotations

from dataclasses import fields
from types import MethodType
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.dig_recovery import (
    PrimitiveDigRecoveryPorts,
    PrimitiveDigRecoveryService,
)
from testbed.planner.primitive.execution.state import (
    PrimitiveExecutionRuntimeState,
)
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _corridor(corridor_id: int) -> CoverageCorridorState:
    return CoverageCorridorState(
        corridor_id=int(corridor_id),
        entry_x_m=0.1,
        entry_z_m=0.2,
        exit_x_m=0.3,
        exit_z_m=0.4,
    )


def _service(
    *,
    events: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[
    PrimitiveDigRecoveryService,
    dict[str, Any],
    list[str],
    list[dict[str, Any]],
    dict[str, Any],
]:
    events = events if events is not None else []
    config = {
        "dig_failed_replan_next_skill": "dig",
        "dig_cut_planner_mode": "operator_prior_coverage",
        "mass_in_bucket": 0.0,
        "pre_dig_entry_error": 0.0,
        "pre_dig_timeout_can_handoff": True,
        "should_pre_dig_align_before_dig": False,
        "should_pre_dig_align_after_failed_dig": False,
        "raw_fields_in_prior_range": True,
        **(config or {}),
    }
    captured_events: list[dict[str, Any]] = []
    execution_state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name="carry",
        switch_reason="old",
    )
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    token_state = PrimitiveTokenRuntimeState.fresh()
    pre_dig_align_state = PrimitivePreDigAlignRuntimeState.fresh(action_dim=4)

    def _set_skill(skill_name: str, reason: str) -> None:
        events.append(f"set_skill:{skill_name}:{reason}")
        execution_state.set_skill_name(skill_name)
        execution_state.set_switch_reason(reason)

    def _record_event(
        event: str,
        *,
        obs: dict[str, Any],
        corridor: CoverageCorridorState | None,
        extra: dict[str, Any],
    ) -> None:
        events.append(f"record:{event}")
        captured_events.append(
            {
                "event": event,
                "obs": obs,
                "corridor": corridor,
                "extra": dict(extra),
            }
        )

    def _request_terminal_stop(reason: str, *, replace: bool) -> None:
        events.append(f"terminal:{reason}:{replace}")
        coverage_state.set_terminal_stop(requested=True, reason=reason)

    def _observation_facts(obs: dict[str, Any]) -> PrimitiveObservationFacts:
        events.append(f"facts:{obs['id']}")
        return PrimitiveObservationFacts.from_obs(
            {
                **obs,
                "task_metrics": {
                    **dict(obs.get("task_metrics", {}) or {}),
                    "mass_in_bucket_kg": float(config["mass_in_bucket"]),
                },
            },
            action_dim=4,
        )

    def _build_tokens(obs: dict[str, Any]):
        events.append(f"build_tokens:{obs['id']}")
        token = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32) + 10.0
        return token, {"x": 1.0}, "operator_prior_coverage", "fallback"

    def _raw_fields_in_prior_range(raw_fields: dict[str, float | int]) -> bool:
        events.append(f"raw_range:{raw_fields['x']}")
        return bool(config["raw_fields_in_prior_range"])

    def _pre_dig_entry_error(obs: dict[str, Any]) -> float:
        events.append(f"entry_error:{obs['id']}")
        return float(config["pre_dig_entry_error"])

    def _pre_dig_timeout_can_handoff(obs: dict[str, Any]) -> bool:
        events.append(f"timeout_gate:{obs['id']}")
        return bool(config["pre_dig_timeout_can_handoff"])

    ports = PrimitiveDigRecoveryPorts(
        execution_state=execution_state,
        cycle_state=cycle_state,
        return_state=return_state,
        coverage_state=coverage_state,
        token_state=token_state,
        pre_dig_align_state=pre_dig_align_state,
        reset_active_policy=lambda: events.append("active_reset"),
        invalidate_pending_dig_cut_plan=lambda: events.append("invalidate"),
        clear_dig_cut_plan=lambda: events.append("clear"),
        build_operator_prior_coverage_dig_cut_tokens=_build_tokens,
        raw_fields_in_prior_range=_raw_fields_in_prior_range,
        pre_dig_align_entry_error=_pre_dig_entry_error,
        pre_dig_align_timeout_can_handoff=_pre_dig_timeout_can_handoff,
        set_skill=_set_skill,
        record_coverage_decision_event=_record_event,
        request_coverage_terminal_stop=_request_terminal_stop,
        observation_facts=_observation_facts,
        should_pre_dig_align_before_dig=lambda: bool(
            config["should_pre_dig_align_before_dig"]
        ),
        should_pre_dig_align_after_failed_dig=lambda: bool(
            config["should_pre_dig_align_after_failed_dig"]
        ),
        dig_cut_planner_mode=lambda: str(config["dig_cut_planner_mode"]),
        dig_failed_replan_next_skill=lambda: str(
            config["dig_failed_replan_next_skill"]
        ),
        pre_dig_align_skill_name="pre_dig_align",
    )
    owners = {
        "execution": execution_state,
        "cycle": cycle_state,
        "return": return_state,
        "coverage": coverage_state,
        "token": token_state,
        "pre_dig_align": pre_dig_align_state,
    }
    return (
        PrimitiveDigRecoveryService.from_ports(ports),
        owners,
        events,
        captured_events,
        config,
    )


def test_restart_dig_with_new_cut_resets_live_owners_and_actions_in_order() -> None:
    service, owners, events, _captured, _config = _service()
    owners["cycle"].dig_step_count = 8
    owners["cycle"].dig_best_mass_kg = 9.0
    owners["cycle"].dig_mass_plateau_count = 10
    owners["cycle"].dig_to_carry_reason = "old"
    owners["coverage"].coverage_current_payload_gain_kg = 2.5
    owners["coverage"].coverage_active_corridor_id = 6

    service.restart_dig_with_new_cut("dig_retry_bad_dig_low_payload")

    assert events == ["active_reset", "invalidate", "clear"]
    assert owners["execution"].skill_name == "dig"
    assert owners["execution"].switch_reason == "dig_retry_bad_dig_low_payload"
    assert owners["cycle"].dig_step_count == 0
    assert owners["cycle"].dig_best_mass_kg == 0.0
    assert owners["cycle"].dig_mass_plateau_count == 0
    assert owners["cycle"].dig_to_carry_reason == ""
    assert owners["coverage"].coverage_current_payload_gain_kg == 0.0
    assert owners["coverage"].coverage_active_corridor_id == -1


def test_stop_after_failed_dig_preserves_payload_event_and_terminal_stop() -> None:
    service, owners, events, captured, config = _service(
        config={"mass_in_bucket": 4.0},
    )
    corridor = _corridor(7)
    owners["coverage"].coverage_corridors = [corridor]
    owners["coverage"].coverage_active_corridor_id = 7
    owners["coverage"].coverage_current_payload_gain_kg = 3.0
    owners["cycle"].dig_best_mass_kg = 8.0
    owners["cycle"].dig_step_count = 11
    obs = {"id": "obs_stop"}

    service.stop_after_failed_dig("bad_dig_low_payload", obs)

    assert events == [
        "facts:obs_stop",
        "record:failed_dig_stop",
        "terminal:dig_failed_bad_dig_low_payload:True",
    ]
    assert owners["execution"].switch_reason == "dig_failed_stop_bad_dig_low_payload"
    assert captured[0]["event"] == "failed_dig_stop"
    assert captured[0]["obs"] is obs
    assert captured[0]["corridor"] is corridor
    assert captured[0]["extra"] == {
        "reason": "bad_dig_low_payload",
        "payload_gain_kg": 8.0,
        "current_bucket_mass_kg": float(config["mass_in_bucket"]),
        "dig_best_mass_kg": 8.0,
        "dig_step_count": 11,
    }
    assert owners["coverage"].coverage_terminal_stop_requested is True
    assert (
        owners["coverage"].coverage_terminal_stop_reason
        == "dig_failed_bad_dig_low_payload"
    )


def test_restart_after_failed_dig_preserves_branch_reasons() -> None:
    service, owners, events, _captured, _config = _service()
    owners["return"].return_next_dig_event_seen = True
    owners["cycle"].dig_step_count = 3

    service.restart_after_failed_dig("bad_dig_low_payload", {"id": "retry"})

    assert owners["execution"].skill_name == "dig"
    assert owners["execution"].switch_reason == "dig_retry_bad_dig_low_payload"
    assert owners["cycle"].dig_step_count == 0
    assert events == ["active_reset", "invalidate", "clear"]

    service, owners, events, captured, _config = _service(
        config={
            "dig_failed_replan_next_skill": "stop",
            "mass_in_bucket": 1.0,
        },
    )
    service.restart_after_failed_dig("bad_dig_exit_guard", {"id": "stop"})
    assert owners["execution"].switch_reason == "dig_failed_stop_bad_dig_exit_guard"
    assert captured[0]["extra"]["reason"] == "bad_dig_exit_guard"
    assert events[-1] == "terminal:dig_failed_bad_dig_exit_guard:True"

    service, owners, events, _captured, _config = _service()
    service.restart_after_failed_dig("bad_dig_plateau", {"id": "retry"})
    assert owners["execution"].skill_name == "dig"
    assert owners["execution"].switch_reason == "dig_retry_bad_dig_plateau"
    assert events == ["active_reset", "invalidate", "clear"]


def test_restart_after_failed_dig_routes_to_pre_dig_align_when_runtime_requests_it() -> None:
    service, owners, events, _captured, _config = _service(
        config={"should_pre_dig_align_after_failed_dig": True},
    )
    owners["cycle"].dig_step_count = 5
    owners["coverage"].coverage_current_payload_gain_kg = 4.0
    owners["coverage"].coverage_active_corridor_id = 12
    owners["return"].return_next_dig_event_seen = True
    owners["pre_dig_align"].step_count = 6
    owners["pre_dig_align"].hold_count = 2
    owners["pre_dig_align"].timeout_handoff_reason = "old_timeout"
    owners["pre_dig_align"].surface_guard_triggered = True

    service.restart_after_failed_dig("bad_dig_low_payload", {"id": "retry"})

    assert events == ["invalidate", "clear"]
    assert owners["execution"].skill_name == "pre_dig_align"
    assert (
        owners["execution"].switch_reason
        == "dig_to_pre_dig_align_bad_dig_low_payload"
    )
    assert owners["cycle"].dig_step_count == 0
    assert owners["coverage"].coverage_current_payload_gain_kg == 0.0
    assert owners["coverage"].coverage_active_corridor_id == -1
    assert owners["return"].return_next_dig_event_seen is False
    assert owners["pre_dig_align"].step_count == 0
    assert owners["pre_dig_align"].hold_count == 0
    assert owners["pre_dig_align"].replan_count == 1
    assert owners["pre_dig_align"].timeout_handoff_reason == ""
    assert owners["pre_dig_align"].surface_guard_triggered is False


def test_try_replan_pre_dig_align_handoff_preserves_writeback_and_gate() -> None:
    service, owners, events, _captured, _config = _service(
        config={"pre_dig_entry_error": 0.42},
    )
    owners["cycle"].cycle_index = 5
    owners["coverage"].coverage_active_corridor_id = 9
    returned_token = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32) + 10.0

    assert service.try_replan_pre_dig_align_handoff(
        {"id": "success"},
        reason="pre_dig_align_replan_to_dig_entry_close",
    ) is True

    assert events == [
        "invalidate",
        "clear",
        "build_tokens:success",
        "raw_range:1.0",
        "entry_error:success",
        "timeout_gate:success",
        "set_skill:dig:pre_dig_align_replan_to_dig_entry_close",
    ]
    assert owners["coverage"].coverage_active_corridor_id == -1
    assert np.allclose(owners["token"].dig_cut_tokens, returned_token)
    assert owners["token"].dig_cut_tokens is not returned_token
    assert owners["token"].dig_cut_planned_cycle_id == 5
    assert owners["token"].dig_cut_token_source == "operator_prior_coverage"
    assert owners["token"].dig_cut_fallback_reason == "fallback"
    assert owners["token"].dig_cut_token_in_prior_p10_p90 is True
    assert owners["pre_dig_align"].entry_error_m == 0.42
    assert owners["pre_dig_align"].replan_count == 1
    assert owners["pre_dig_align"].completed_count == 1
    assert owners["pre_dig_align"].step_count == 0
    assert owners["pre_dig_align"].hold_count == 0
    assert owners["execution"].skill_name == "dig"
    assert (
        owners["execution"].switch_reason
        == "pre_dig_align_replan_to_dig_entry_close"
    )


def test_replan_or_restart_pre_dig_align_restarts_when_replan_unavailable() -> None:
    service, owners, events, _captured, config = _service()
    config["dig_cut_planner_mode"] = "learned"
    owners["return"].return_next_dig_event_seen = True
    owners["cycle"].dig_step_count = 8
    owners["pre_dig_align"].step_count = 6
    owners["pre_dig_align"].hold_count = 3
    owners["pre_dig_align"].timeout_handoff_reason = "old"
    owners["pre_dig_align"].surface_guard_triggered = True

    service.replan_or_restart_pre_dig_align(
        {"id": "retry"},
        replan_reason="pre_dig_align_replan_to_dig_entry_close",
        restart_reason="pre_dig_align_retry_entry_gap",
    )

    assert events == ["invalidate", "clear"]
    assert owners["execution"].skill_name == "pre_dig_align"
    assert owners["execution"].switch_reason == "pre_dig_align_retry_entry_gap"
    assert owners["return"].return_next_dig_event_seen is False
    assert owners["cycle"].dig_step_count == 0
    assert owners["pre_dig_align"].step_count == 0
    assert owners["pre_dig_align"].hold_count == 0
    assert owners["pre_dig_align"].replan_count == 1
    assert owners["pre_dig_align"].timeout_handoff_reason == ""
    assert owners["pre_dig_align"].surface_guard_triggered is False


def test_policy_recovery_ports_share_focused_owners_and_runtime_boundaries() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    policy.dig_cut_planner_mode = "operator_prior_coverage"
    policy.dig_failed_replan_next_skill = "dig"
    events: list[str] = []

    class _ActivePolicy:
        def reset(self) -> None:
            events.append("active_reset")

    class _ActionDispatchService:
        def active_policy(self) -> _ActivePolicy:
            return _ActivePolicy()

    policy._action_dispatch_service = MethodType(
        lambda self: _ActionDispatchService(),
        policy,
    )

    ports = policy._primitive_dig_recovery_ports()
    port_names = {field.name for field in fields(PrimitiveDigRecoveryPorts)}

    assert ports.execution_state is policy._primitive_execution_runtime_state()
    assert ports.cycle_state is policy._primitive_cycle_runtime_state()
    assert ports.return_state is policy._primitive_return_runtime_state()
    assert ports.coverage_state is policy._coverage_runtime_state()
    assert ports.token_state is policy._primitive_token_runtime_state()
    assert ports.pre_dig_align_state is policy._primitive_pre_dig_align_runtime_state()
    assert "planner" not in port_names
    assert "self" not in port_names
    assert "observation_facts" in port_names
    assert "build_operator_prior_coverage_dig_cut_tokens" in port_names
    assert "should_pre_dig_align_before_dig" in port_names
    assert "should_pre_dig_align_after_failed_dig" in port_names
    assert "mass_in_bucket" not in port_names
    assert not hasattr(policy, "_restart_pre_dig_align")
    assert not hasattr(policy, "_try_replan_pre_dig_align_handoff")

    policy._primitive_cycle_runtime_state().dig_step_count = 5
    policy._coverage_runtime_state().coverage_current_payload_gain_kg = 6.0
    policy._coverage_runtime_state().coverage_active_corridor_id = 7
    token_state = policy._primitive_token_runtime_state()
    token_state.pending_dig_cut_cycle_id = 2
    token_state.pending_dig_cut_raw_fields = {"operator_entry_x_m": 1.0}
    token_state.pending_dig_cut_tokens = object()
    token_state.dig_cut_planned_cycle_id = 2
    policy._coverage_runtime_state().coverage_active_state_exemplar_ids = ["ex_a"]

    policy._primitive_dig_recovery().restart_dig_with_new_cut("policy_retry")

    assert events == ["active_reset"]
    assert policy._primitive_execution_runtime_state().skill_name == "dig"
    assert policy._primitive_execution_runtime_state().switch_reason == "policy_retry"
    assert policy._primitive_cycle_runtime_state().dig_step_count == 0
    assert policy._coverage_runtime_state().coverage_current_payload_gain_kg == 0.0
    assert policy._coverage_runtime_state().coverage_active_corridor_id == -1
    assert token_state.pending_dig_cut_cycle_id == -1
    assert token_state.pending_dig_cut_raw_fields is None
    assert token_state.pending_dig_cut_tokens is None
    assert token_state.dig_cut_planned_cycle_id == -1
    assert policy._coverage_runtime_state().coverage_active_state_exemplar_ids == []


def test_policy_no_longer_exposes_recovery_token_plan_private_wrappers() -> None:
    removed_names = {
        "_clear_dig_cut_plan",
        "_invalidate_pending_dig_cut_plan",
        "_restart_dig_with_new_cut",
        "_stop_after_failed_dig",
        "_restart_after_failed_dig",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)
