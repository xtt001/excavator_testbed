"""Legacy FSM backend runtime-effect bridge."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from testbed.planner.runtime.contracts import (
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)
from testbed.planner.runtime.ports import (
    LegacyFsmBootstrapPorts,
    LegacyFsmDigTransitionPorts,
    LegacyFsmDumpLifecyclePorts,
    LegacyFsmPreDigAlignmentPorts,
    LegacyFsmReturnTransitionPorts,
    LegacyFsmSkillNames,
)

LEGACY_FSM_TRANSITION_EFFECT = "run_legacy_fsm_transition"
APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT = "apply_bootstrap_transition_decision"
APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT = "apply_pre_dig_align_outcome"
APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT = (
    "apply_dig_transition_runtime_projection"
)
APPLY_CARRY_TRANSITION_RUNTIME_EFFECT = "apply_carry_transition_runtime"
APPLY_DUMP_TRANSITION_RUNTIME_EFFECT = "apply_dump_transition_runtime"
APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT = (
    "apply_return_to_dig_transition_runtime"
)


class LegacyFsmTransitionRunner(Protocol):
    def __call__(
        self,
        *,
        obs: Mapping[str, Any],
        boundary_event: Any | None,
    ) -> None:
        """Apply one legacy FSM transition through the adapter."""


class BootstrapTransitionDecisionApplier(Protocol):
    def __call__(self, decision: Any) -> None:
        """Apply a bootstrap transition decision through the adapter."""


class PreDigAlignOutcomeApplier(Protocol):
    def __call__(self, outcome: Any, obs: Mapping[str, Any]) -> object:
        """Apply a pre-dig-align outcome through the adapter."""


class DigTransitionRuntimeProjectionApplier(Protocol):
    def __call__(self, projection: Any, obs: Mapping[str, Any]) -> object:
        """Apply a dig transition runtime projection through the adapter."""


class CarryTransitionRuntimeApplier(Protocol):
    def __call__(self, runtime: Any, obs: Mapping[str, Any]) -> object:
        """Apply a carry transition runtime state through the adapter."""


class DumpTransitionRuntimeApplier(Protocol):
    def __call__(self, runtime: Any, obs: Mapping[str, Any]) -> object:
        """Apply a dump transition runtime state through the adapter."""


class ReturnToDigTransitionRuntimeApplier(Protocol):
    def __call__(self, outcome: Any, projection: Any) -> object:
        """Apply a return-to-dig transition runtime effect through the adapter."""


class LegacyStateMachineBackend:
    """Backend contract wrapper for the current legacy FSM transition."""

    name = "legacy_fsm"

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        active_skill = context.blackboard.current_skill
        ports = context.ports.legacy_fsm
        if ports is None:
            return self._fallback_tick(context, active_skill=active_skill)

        skill_names = ports.skill_names
        if active_skill == skill_names.bootstrap:
            return self._tick_bootstrap(
                context,
                active_skill=active_skill,
                ports=_required_port(
                    ports.bootstrap_transition,
                    "bootstrap_transition",
                ),
                skill_names=skill_names,
            )
        if active_skill == skill_names.pre_dig_align:
            return self._tick_pre_dig_align(
                context,
                active_skill=active_skill,
                ports=_required_port(
                    ports.pre_dig_alignment,
                    "pre_dig_alignment",
                ),
            )
        if active_skill == skill_names.dig:
            return self._tick_dig(
                context,
                active_skill=active_skill,
                ports=_required_port(ports.dig_transition, "dig_transition"),
            )
        if active_skill == skill_names.carry:
            return self._tick_carry(
                context,
                active_skill=active_skill,
                ports=_required_port(ports.dump_lifecycle, "dump_lifecycle"),
            )
        if active_skill == skill_names.dump:
            return self._tick_dump(
                context,
                active_skill=active_skill,
                ports=_required_port(ports.dump_lifecycle, "dump_lifecycle"),
            )
        if active_skill == skill_names.return_skill:
            return self._tick_return(
                context,
                active_skill=active_skill,
                ports=_required_port(
                    ports.return_transition,
                    "return_transition",
                ),
            )
        return self._fallback_tick(context, active_skill=active_skill)

    def _fallback_tick(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
    ) -> PlannerTickResult:
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason="",
            effects=(
                PlannerRuntimeEffect(
                    LEGACY_FSM_TRANSITION_EFFECT,
                    {
                        "obs": context.obs,
                        "boundary_event": context.boundary_event,
                    },
                ),
            ),
            diagnostics={"active_skill": active_skill},
        )

    def _tick_bootstrap(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: LegacyFsmBootstrapPorts,
        skill_names: LegacyFsmSkillNames,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        if not ports.should_end(obs=obs, boundary_event=context.boundary_event):
            return PlannerTickResult(
                node_path=("legacy_fsm", "transition", active_skill),
                status="running",
                reason="",
                effects=(),
                diagnostics={"active_skill": active_skill},
            )

        transition_request = ports.service.end_transition_request(
            pre_dig_align_before_dig=ports.should_pre_dig_align_before_dig(),
            pre_dig_align_skill_name=skill_names.pre_dig_align,
        )
        decision = ports.service.end_transition(
            transition_request.facts,
            ports.config(),
            transition_request.transition_config,
        )
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason=str(decision.switch_reason),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT,
                    {"decision": decision},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "next_skill": str(decision.next_skill),
                "switch_reason": str(decision.switch_reason),
            },
        )

    def _tick_pre_dig_align(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: LegacyFsmPreDigAlignmentPorts,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        outcome = ports.compute_outcome(obs)
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason=str(getattr(outcome, "switch_reason", "")),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT,
                    {"outcome": outcome, "obs": obs},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "action": str(getattr(outcome, "action", "")),
                "switch_reason": str(getattr(outcome, "switch_reason", "")),
            },
        )

    def _tick_dig(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: LegacyFsmDigTransitionPorts,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        exit_guard_ready = ports.exit_guard_ready(obs)
        request = ports.lifecycle_gate.dig_transition_runtime_request(
            exit_guard_ready=exit_guard_ready,
        )
        bad_replan_ready = False
        complete_boundary_low_payload = False
        dig_to_carry_ready = False
        dig_to_carry_reason = ""
        if request.should_check_bad_replan:
            bad_replan_ready = ports.bad_replan_ready(obs)
        if request.should_check_complete_boundary_low_payload(bad_replan_ready):
            complete_boundary_low_payload = ports.complete_boundary_low_payload(
                obs,
                context.boundary_event,
            )
        if request.should_check_dig_to_carry(
            bad_replan_ready=bad_replan_ready,
            complete_boundary_low_payload=complete_boundary_low_payload,
        ):
            dig_to_carry_decision = ports.dig_to_carry_decision(
                obs=obs,
                boundary_event=context.boundary_event,
            )
            dig_to_carry_ready = bool(dig_to_carry_decision.ready)
            if dig_to_carry_ready:
                dig_to_carry_reason = str(dig_to_carry_decision.reason)
        outcome = ports.lifecycle_gate.dig_transition_runtime(
            request.facts_with_gate_results(
                bad_replan_ready=bad_replan_ready,
                dig_to_carry_reason=dig_to_carry_reason,
                complete_boundary_low_payload=complete_boundary_low_payload,
                dig_to_carry_ready=dig_to_carry_ready,
            )
        )
        projection = ports.lifecycle_gate.dig_transition_runtime_projection(outcome)
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason=str(getattr(outcome, "switch_reason", "")),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
                    {"projection": projection, "obs": obs},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "action": str(getattr(outcome, "action", "")),
                "switch_reason": str(getattr(outcome, "switch_reason", "")),
            },
        )

    def _tick_carry(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: LegacyFsmDumpLifecyclePorts,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        runtime = ports.carry_transition_runtime(
            obs=obs,
            boundary_event=context.boundary_event,
            current_dump_ready_hold_count=context.blackboard.dump_ready_hold_count,
        )
        outcome = runtime.outcome
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason=str(getattr(outcome, "switch_reason", "")),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
                    {"runtime": runtime, "obs": obs},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "action": str(getattr(outcome, "action", "")),
                "switch_reason": str(getattr(outcome, "switch_reason", "")),
            },
        )

    def _tick_dump(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: LegacyFsmDumpLifecyclePorts,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        runtime = ports.dump_transition_runtime(
            obs=obs,
            boundary_event=context.boundary_event,
            current_dump_done_hold_count=context.blackboard.dump_done_hold_count,
        )
        outcome = runtime.outcome
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason=str(getattr(outcome, "switch_reason", "")),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
                    {"runtime": runtime, "obs": obs},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "action": str(getattr(outcome, "action", "")),
                "switch_reason": str(getattr(outcome, "switch_reason", "")),
            },
        )

    def _tick_return(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: LegacyFsmReturnTransitionPorts,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        runtime = ports.return_transition_runtime(
            obs=obs,
            boundary_event=context.boundary_event,
            previous_next_dig_event_seen=(
                context.blackboard.return_next_dig_event_seen
            ),
        )
        outcome = runtime.outcome
        projection = runtime.projection
        return PlannerTickResult(
            node_path=("legacy_fsm", "transition", active_skill),
            status="running",
            reason=str(getattr(outcome, "reason_suffix", "")),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
                    {"outcome": outcome, "projection": projection},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "action": str(getattr(outcome, "action", "")),
                "reason_suffix": str(getattr(outcome, "reason_suffix", "")),
                "next_dig_event_seen": bool(
                    getattr(outcome, "next_dig_event_seen", False)
                ),
            },
        )


def apply_legacy_fsm_runtime_effects(
    effects: Iterable[PlannerRuntimeEffect],
    *,
    run_legacy_fsm_transition: LegacyFsmTransitionRunner,
    apply_bootstrap_transition_decision: (
        BootstrapTransitionDecisionApplier | None
    ) = None,
    apply_pre_dig_align_outcome: PreDigAlignOutcomeApplier | None = None,
    apply_dig_transition_runtime_projection: (
        DigTransitionRuntimeProjectionApplier | None
    ) = None,
    apply_carry_transition_runtime: CarryTransitionRuntimeApplier | None = None,
    apply_dump_transition_runtime: DumpTransitionRuntimeApplier | None = None,
    apply_return_to_dig_transition_runtime: (
        ReturnToDigTransitionRuntimeApplier | None
    ) = None,
) -> None:
    """Apply legacy FSM backend effects through adapter-owned side effects."""

    for effect in effects:
        if effect.effect_type == LEGACY_FSM_TRANSITION_EFFECT:
            run_legacy_fsm_transition(
                obs=dict(effect.payload["obs"]),
                boundary_event=effect.payload.get("boundary_event"),
            )
            continue
        if effect.effect_type == APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT:
            if apply_bootstrap_transition_decision is None:
                raise ValueError(
                    "bootstrap transition decision effect requires an adapter "
                    "callback."
                )
            apply_bootstrap_transition_decision(effect.payload["decision"])
            continue
        if effect.effect_type == APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT:
            if apply_pre_dig_align_outcome is None:
                raise ValueError(
                    "pre-dig-align outcome effect requires an adapter callback."
                )
            apply_pre_dig_align_outcome(
                effect.payload["outcome"],
                dict(effect.payload["obs"]),
            )
            continue
        if effect.effect_type == APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT:
            if apply_dig_transition_runtime_projection is None:
                raise ValueError(
                    "dig transition runtime projection effect requires an "
                    "adapter callback."
                )
            apply_dig_transition_runtime_projection(
                effect.payload["projection"],
                dict(effect.payload["obs"]),
            )
            continue
        if effect.effect_type == APPLY_CARRY_TRANSITION_RUNTIME_EFFECT:
            if apply_carry_transition_runtime is None:
                raise ValueError(
                    "carry transition runtime effect requires an adapter callback."
                )
            apply_carry_transition_runtime(
                effect.payload["runtime"],
                dict(effect.payload["obs"]),
            )
            continue
        if effect.effect_type == APPLY_DUMP_TRANSITION_RUNTIME_EFFECT:
            if apply_dump_transition_runtime is None:
                raise ValueError(
                    "dump transition runtime effect requires an adapter callback."
                )
            apply_dump_transition_runtime(
                effect.payload["runtime"],
                dict(effect.payload["obs"]),
            )
            continue
        if effect.effect_type == APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT:
            if apply_return_to_dig_transition_runtime is None:
                raise ValueError(
                    "return-to-dig transition runtime effect requires an "
                    "adapter callback."
                )
            apply_return_to_dig_transition_runtime(
                effect.payload["outcome"],
                effect.payload["projection"],
            )
            continue
        raise ValueError(f"Unsupported legacy FSM effect {effect.effect_type!r}.")


def _required_port(port: Any | None, name: str) -> Any:
    if port is None:
        raise ValueError(f"Legacy FSM backend requires typed port {name!r}.")
    return port


__all__ = [
    "APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT",
    "APPLY_CARRY_TRANSITION_RUNTIME_EFFECT",
    "APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT",
    "APPLY_DUMP_TRANSITION_RUNTIME_EFFECT",
    "APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT",
    "APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT",
    "BootstrapTransitionDecisionApplier",
    "CarryTransitionRuntimeApplier",
    "DigTransitionRuntimeProjectionApplier",
    "DumpTransitionRuntimeApplier",
    "LEGACY_FSM_TRANSITION_EFFECT",
    "LegacyFsmTransitionRunner",
    "LegacyStateMachineBackend",
    "PreDigAlignOutcomeApplier",
    "ReturnToDigTransitionRuntimeApplier",
    "apply_legacy_fsm_runtime_effects",
]
