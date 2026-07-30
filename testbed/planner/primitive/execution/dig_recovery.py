"""Failed-dig and restart recovery boundary for primitive planner runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState


@dataclass(frozen=True)
class PrimitiveDigRecoveryPorts:
    """Explicit ports for failed-dig restart and recovery behavior."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    coverage_state: CoverageRuntimeState
    token_state: PrimitiveTokenRuntimeState
    pre_dig_align_state: PrimitivePreDigAlignRuntimeState
    reset_active_policy: Callable[[], None]
    invalidate_pending_dig_cut_plan: Callable[[], None]
    clear_dig_cut_plan: Callable[[], None]
    build_operator_prior_coverage_dig_cut_tokens: Callable[
        [dict[str, Any]],
        tuple[np.ndarray, dict[str, float | int], str, str],
    ]
    raw_fields_in_prior_range: Callable[[dict[str, float | int]], bool]
    pre_dig_align_entry_error: Callable[[dict[str, Any]], float]
    pre_dig_align_timeout_can_handoff: Callable[[dict[str, Any]], bool]
    set_skill: Callable[[str, str], None]
    record_coverage_decision_event: Callable[..., None]
    request_coverage_terminal_stop: Callable[..., None]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    should_pre_dig_align_before_dig: Callable[[], bool]
    should_pre_dig_align_after_failed_dig: Callable[[], bool]
    dig_cut_planner_mode: Callable[[], str]
    dig_failed_replan_next_skill: Callable[[], str]
    pre_dig_align_skill_name: str
    dig_skill_name: str = "dig"


@dataclass(frozen=True)
class PrimitiveDigRecoveryService:
    """Own failed-dig recovery and restart orchestration."""

    ports: PrimitiveDigRecoveryPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveDigRecoveryPorts,
    ) -> PrimitiveDigRecoveryService:
        return cls(ports=ports)

    def restart_pre_dig_align(self, reason: str) -> None:
        ports = self.ports
        ports.execution_state.set_skill_name(ports.pre_dig_align_skill_name)
        ports.execution_state.set_switch_reason(str(reason))
        ports.pre_dig_align_state.step_count = 0
        ports.pre_dig_align_state.hold_count = 0
        ports.pre_dig_align_state.replan_count += 1
        ports.pre_dig_align_state.entry_intent_handoff_ready = False
        ports.pre_dig_align_state.timeout_handoff_reason = ""
        ports.pre_dig_align_state.surface_guard_triggered = False
        ports.cycle_state.reset_dig_progress()
        ports.coverage_state.set_current_payload_gain_kg(0.0)
        ports.coverage_state.set_active_corridor_id(-1)
        ports.return_state.clear_next_dig_event_seen()
        ports.invalidate_pending_dig_cut_plan()
        ports.clear_dig_cut_plan()

    def try_replan_pre_dig_align_handoff(
        self,
        obs: dict[str, Any],
        *,
        reason: str = "pre_dig_align_replan_to_dig_entry_close",
    ) -> bool:
        ports = self.ports
        if ports.dig_cut_planner_mode() not in {
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
        }:
            return False
        ports.coverage_state.set_active_corridor_id(-1)
        ports.invalidate_pending_dig_cut_plan()
        ports.clear_dig_cut_plan()
        try:
            token, raw_fields, source, fallback_reason = (
                ports.build_operator_prior_coverage_dig_cut_tokens(obs)
            )
        except Exception:
            return False
        ports.token_state.dig_cut_tokens = np.asarray(
            token,
            dtype=np.float32,
        ).copy()
        ports.token_state.dig_cut_planned_cycle_id = int(
            ports.cycle_state.cycle_index
        )
        ports.token_state.dig_cut_token_source = str(source)
        ports.token_state.dig_cut_fallback_reason = str(fallback_reason)
        ports.token_state.dig_cut_token_in_prior_p10_p90 = (
            ports.raw_fields_in_prior_range(raw_fields)
        )
        ports.pre_dig_align_state.entry_error_m = float(
            ports.pre_dig_align_entry_error(obs)
        )
        if not ports.pre_dig_align_timeout_can_handoff(obs):
            return False
        ports.pre_dig_align_state.replan_count += 1
        ports.pre_dig_align_state.completed_count += 1
        ports.pre_dig_align_state.step_count = 0
        ports.pre_dig_align_state.hold_count = 0
        ports.set_skill(ports.dig_skill_name, str(reason))
        return True

    def replan_or_restart_pre_dig_align(
        self,
        obs: dict[str, Any],
        *,
        replan_reason: str,
        restart_reason: str,
    ) -> None:
        if self.try_replan_pre_dig_align_handoff(obs, reason=replan_reason):
            return
        self.restart_pre_dig_align(restart_reason)

    def restart_dig_with_new_cut(self, reason: str) -> None:
        ports = self.ports
        ports.execution_state.set_skill_name(ports.dig_skill_name)
        ports.execution_state.set_switch_reason(str(reason))
        ports.reset_active_policy()
        ports.cycle_state.reset_dig_progress()
        ports.coverage_state.set_current_payload_gain_kg(0.0)
        ports.coverage_state.set_active_corridor_id(-1)
        ports.invalidate_pending_dig_cut_plan()
        ports.clear_dig_cut_plan()

    def stop_after_failed_dig(self, reason: str, obs: dict[str, Any]) -> None:
        ports = self.ports
        corridor = ports.coverage_state.active_corridor()
        bucket_mass = float(ports.observation_facts(obs).mass_in_bucket_kg)
        payload_gain = max(
            float(ports.coverage_state.coverage_current_payload_gain_kg),
            float(ports.cycle_state.dig_best_mass_kg),
            bucket_mass,
            0.0,
        )
        ports.execution_state.set_switch_reason(f"dig_failed_stop_{reason}")
        ports.record_coverage_decision_event(
            "failed_dig_stop",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "payload_gain_kg": float(payload_gain),
                "current_bucket_mass_kg": float(bucket_mass),
                "dig_best_mass_kg": float(ports.cycle_state.dig_best_mass_kg),
                "dig_step_count": int(ports.cycle_state.dig_step_count),
            },
        )
        ports.request_coverage_terminal_stop(
            f"dig_failed_{reason}",
            replace=True,
        )

    def restart_after_failed_dig(self, reason: str, obs: dict[str, Any]) -> None:
        ports = self.ports
        if (
            ports.should_pre_dig_align_before_dig()
            or ports.should_pre_dig_align_after_failed_dig()
        ):
            self.restart_pre_dig_align(f"dig_to_pre_dig_align_{reason}")
            return
        if ports.dig_failed_replan_next_skill() == "stop":
            self.stop_after_failed_dig(reason, obs)
            return
        self.restart_dig_with_new_cut(f"dig_retry_{reason}")


__all__ = [
    "PrimitiveDigRecoveryPorts",
    "PrimitiveDigRecoveryService",
]
