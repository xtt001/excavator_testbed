"""Legacy FSM backend runtime-effect bridge."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from testbed.planner.runtime.contracts import (
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
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
        bootstrap_skill_name = context.services.get("bootstrap_skill_name")
        if (
            bootstrap_skill_name is not None
            and active_skill == str(bootstrap_skill_name)
        ):
            return self._tick_bootstrap(context, active_skill=active_skill)
        pre_dig_align_skill_name = context.services.get("pre_dig_align_skill_name")
        if (
            pre_dig_align_skill_name is not None
            and active_skill == str(pre_dig_align_skill_name)
        ):
            return self._tick_pre_dig_align(context, active_skill=active_skill)
        dig_skill_name = context.services.get("dig_skill_name")
        if dig_skill_name is not None and active_skill == str(dig_skill_name):
            return self._tick_dig(context, active_skill=active_skill)
        carry_skill_name = context.services.get("carry_skill_name")
        if carry_skill_name is not None and active_skill == str(carry_skill_name):
            return self._tick_carry(context, active_skill=active_skill)
        dump_skill_name = context.services.get("dump_skill_name")
        if dump_skill_name is not None and active_skill == str(dump_skill_name):
            return self._tick_dump(context, active_skill=active_skill)
        return_skill_name = context.services.get("return_skill_name")
        if return_skill_name is not None and active_skill == str(return_skill_name):
            return self._tick_return(context, active_skill=active_skill)
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
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        should_end_bootstrap = _required_service(
            context.services,
            "should_end_bootstrap",
        )
        if not should_end_bootstrap(obs=obs, boundary_event=context.boundary_event):
            return PlannerTickResult(
                node_path=("legacy_fsm", "transition", active_skill),
                status="running",
                reason="",
                effects=(),
                diagnostics={"active_skill": active_skill},
            )

        bootstrap_service = _required_service(context.services, "bootstrap_service")
        should_pre_dig_align_before_dig = _required_service(
            context.services,
            "should_pre_dig_align_before_dig",
        )
        bootstrap_config = _required_service(context.services, "bootstrap_config")
        transition_request = bootstrap_service.end_transition_request(
            pre_dig_align_before_dig=should_pre_dig_align_before_dig(),
            pre_dig_align_skill_name=str(
                context.services.get("pre_dig_align_skill_name", "pre_dig_align")
            ),
        )
        decision = bootstrap_service.end_transition(
            transition_request.facts,
            bootstrap_config(),
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
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        pre_dig_align_outcome = _required_service(
            context.services,
            "pre_dig_align_outcome",
        )
        outcome = pre_dig_align_outcome(obs)
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
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        dig_lifecycle_gate = _required_service(
            context.services,
            "dig_lifecycle_gate",
        )
        exit_guard_ready = _required_service(
            context.services,
            "dig_exit_guard_ready",
        )(obs)
        request = dig_lifecycle_gate.dig_transition_runtime_request(
            exit_guard_ready=exit_guard_ready,
        )
        bad_replan_ready = False
        complete_boundary_low_payload = False
        dig_to_carry_ready = False
        dig_to_carry_reason = ""
        if request.should_check_bad_replan:
            bad_replan_ready = _required_service(
                context.services,
                "dig_bad_replan_ready",
            )(obs)
        if request.should_check_complete_boundary_low_payload(bad_replan_ready):
            complete_boundary_low_payload = _required_service(
                context.services,
                "dig_complete_boundary_low_payload",
            )(obs, context.boundary_event)
        if request.should_check_dig_to_carry(
            bad_replan_ready=bad_replan_ready,
            complete_boundary_low_payload=complete_boundary_low_payload,
        ):
            dig_to_carry_ready = _required_service(
                context.services,
                "dig_to_carry_ready",
            )(obs=obs, boundary_event=context.boundary_event)
            if dig_to_carry_ready:
                dig_to_carry_reason = str(
                    _required_service(context.services, "dig_to_carry_reason")()
                )
        outcome = dig_lifecycle_gate.dig_transition_runtime(
            request.facts_with_gate_results(
                bad_replan_ready=bad_replan_ready,
                dig_to_carry_reason=dig_to_carry_reason,
                complete_boundary_low_payload=complete_boundary_low_payload,
                dig_to_carry_ready=dig_to_carry_ready,
            )
        )
        projection = dig_lifecycle_gate.dig_transition_runtime_projection(outcome)
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
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        release_safety_done = _required_service(
            context.services,
            "carry_release_safety_done",
        )(obs)
        build_request = _required_service(
            context.services,
            "build_carry_transition_runtime_request",
        )
        request = build_request(
            release_safety_done=release_safety_done,
            boundary_event=context.boundary_event,
            semantic_boundary_profile_active=_required_service(
                context.services,
                "semantic_boundary_profile_active",
            )(),
            current_dump_ready_hold_count=context.blackboard.dump_ready_hold_count,
        )
        dump_ready = False
        if request.should_check_dump_ready:
            dump_ready = bool(_required_service(context.services, "dump_ready")(obs))
        runtime = _required_service(
            context.services,
            "dump_lifecycle_gate",
        ).carry_transition_runtime(
            request.facts_with_dump_ready(dump_ready),
            dump_ready_hold_steps=_required_service(
                context.services,
                "dump_ready_hold_steps",
            )(),
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
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        build_request = _required_service(
            context.services,
            "build_dump_transition_runtime_request",
        )
        request = build_request(
            dump_done_use_boundary_event=_required_service(
                context.services,
                "dump_done_use_boundary_event",
            )(),
            boundary_event=context.boundary_event,
            semantic_boundary_profile_active=_required_service(
                context.services,
                "semantic_boundary_profile_active",
            )(),
            current_dump_done_hold_count=context.blackboard.dump_done_hold_count,
        )
        dump_done = False
        if request.should_check_dump_done:
            dump_done = bool(_required_service(context.services, "dump_done")(obs))
        runtime = _required_service(
            context.services,
            "dump_lifecycle_gate",
        ).dump_transition_runtime(
            request.facts_with_dump_done(dump_done),
            dump_done_hold_steps=_required_service(
                context.services,
                "dump_done_hold_steps",
            )(),
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
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        return_transition_service = _required_service(
            context.services,
            "return_transition_service",
        )
        handoff_ready = _required_service(
            context.services,
            "return_to_dig_handoff_ready",
        )(obs)
        request = return_transition_service.transition_request(
            handoff_ready=handoff_ready,
            boundary_event=context.boundary_event,
            previous_next_dig_event_seen=(
                context.blackboard.return_next_dig_event_seen
            ),
            semantic_boundary_profile_active=_required_service(
                context.services,
                "semantic_boundary_profile_active",
            )(),
        )
        direct_handoff_ready = False
        shallow_guard_ready = False
        if request.should_check_direct_handoff:
            direct_handoff_ready = _required_service(
                context.services,
                "return_to_dig_direct_handoff_ready",
            )(obs, handoff_ready=handoff_ready)
        if request.should_check_shallow_guard(direct_handoff_ready):
            shallow_guard_ready = _required_service(
                context.services,
                "return_to_dig_shallow_guard_ready",
            )(obs=obs, boundary_event=context.boundary_event)
        outcome = return_transition_service.classify(
            request.facts_with_gate_results(
                direct_handoff_ready=direct_handoff_ready,
                shallow_guard_ready=shallow_guard_ready,
            ),
            request.config,
        )
        projection = return_transition_service.transition_runtime_projection(outcome)
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


def _required_service(services: Mapping[str, Any], name: str) -> Any:
    try:
        return services[name]
    except KeyError as exc:
        raise ValueError(f"Legacy FSM backend requires service {name!r}.") from exc


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
