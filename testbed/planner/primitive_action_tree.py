"""Shadow-only legacy-equivalent action tree for primitive scheduler ticks."""

from __future__ import annotations

import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np
from testbed.policies.hybrid.primitive_planner import (
    BOOTSTRAP_SKILL_NAME,
    PRE_DIG_ALIGN_SKILL_NAME,
)

if TYPE_CHECKING:
    from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


@dataclass(frozen=True)
class PrimitiveActionTreeTrace:
    """Trace emitted by one shadow action-tree tick."""

    active_skill_before: str
    active_skill_after: str
    switch_reason: str
    transition_timeout: bool
    transition_completed: bool
    node_path: tuple[str, ...]
    node_status: str = "running"
    service_outcome: str = ""
    guard_facts: dict[str, object] = field(default_factory=dict)
    policy_dispatch: str = ""
    reset_count_delta: int = 0
    return_step_count_delta: int = 0
    transition_timeout_count_delta: int = 0


@dataclass(frozen=True)
class _ActionTreeTickResult:
    node_path: tuple[str, ...]
    node_status: str = "running"
    service_outcome: str = ""
    guard_facts: dict[str, object] = field(default_factory=dict)


class PrimitiveActionTreeRunner:
    """Memoryful shadow runner that mirrors the legacy primitive FSM tick.

    The runner intentionally mutates the supplied policy instance. It is a
    shadow-only alternate shell around the existing private planner facades and
    services, not a new source of gate semantics.
    """

    def __init__(self) -> None:
        self.last_trace: PrimitiveActionTreeTrace | None = None

    def predict(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
    ) -> np.ndarray:
        """Run a legacy-equivalent planner tick on ``policy``."""

        reset_count_before = _policy_reset_count_total(policy)
        return_step_count_before = int(policy._return_step_count)
        transition_timeout_count_before = int(policy._transition_timeout_count)
        boundary_event = None
        if policy._prev_action is not None:
            detector_facts = policy._boundary_detector_update_facts(obs)
            boundary_event = policy.boundary_detector.update(
                env_state=detector_facts.env_state,
                action=detector_facts.action,
                qpos=detector_facts.qpos,
                reward_phase=detector_facts.reward_phase,
                task_step_successes=detector_facts.task_step_successes,
                task_metrics=detector_facts.task_metrics,
            )

        policy._switch_reason = ""
        transition_timeout = False
        transition_completed = False
        if policy._skill_name == "dig":
            policy._update_dig_progress(obs)
        transition_trace = self.tick_transition(
            policy,
            obs,
            boundary_event,
        )

        if policy._skill_name == "return":
            policy._return_step_count += 1
            if policy.return_max_steps > 0 and (
                policy._return_step_count >= policy.return_max_steps
            ):
                transition_timeout = True
                policy._transition_timeout_count += 1

        if (
            policy._skill_name == BOOTSTRAP_SKILL_NAME
            and policy._scripted_bootstrap_enabled()
        ):
            action = policy._scripted_bootstrap_action(obs)
            policy_dispatch = "scripted_bootstrap"
        elif policy._skill_name == PRE_DIG_ALIGN_SKILL_NAME:
            action = policy._pre_dig_align_action(obs)
            policy_dispatch = PRE_DIG_ALIGN_SKILL_NAME
        else:
            active_policy = policy._active_policy()
            policy_obs = policy._policy_obs(obs)
            action = np.asarray(
                active_policy.predict(policy_obs),
                dtype=np.float32,
            ).reshape(policy.action_dim)
            policy_dispatch = str(policy._skill_name)
        policy._prev_action = action.copy()

        if policy._switch_reason.startswith(
            ("return_to_dig_", "return_to_pre_dig_align_")
        ):
            transition_completed = True

        policy._debug_state = policy._make_debug_state(
            transition_timeout=transition_timeout,
            transition_completed=transition_completed,
        )
        self.last_trace = replace(
            transition_trace,
            active_skill_after=str(policy._skill_name),
            switch_reason=str(policy._switch_reason),
            transition_timeout=transition_timeout,
            transition_completed=transition_completed,
            policy_dispatch=policy_dispatch,
            reset_count_delta=(
                _policy_reset_count_total(policy) - reset_count_before
            ),
            return_step_count_delta=(
                int(policy._return_step_count) - return_step_count_before
            ),
            transition_timeout_count_delta=(
                int(policy._transition_timeout_count)
                - transition_timeout_count_before
            ),
        )
        return action

    def tick_transition(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> PrimitiveActionTreeTrace:
        """Run only the transition subtree for the currently active skill."""

        active_skill_before = str(policy._skill_name)
        node_path = ("transition", active_skill_before)
        if active_skill_before == BOOTSTRAP_SKILL_NAME:
            tick = self._tick_bootstrap(policy, obs, boundary_event)
        elif active_skill_before == PRE_DIG_ALIGN_SKILL_NAME:
            tick = self._tick_pre_dig_align(policy, obs)
        elif active_skill_before == "dig":
            tick = self._tick_dig(policy, obs, boundary_event)
        elif active_skill_before == "carry":
            tick = self._tick_carry(policy, obs, boundary_event)
        elif active_skill_before == "dump":
            tick = self._tick_dump(policy, obs, boundary_event)
        elif active_skill_before == "return":
            tick = self._tick_return(policy, obs, boundary_event)
        else:
            tick = _ActionTreeTickResult(
                node_path=("unknown_skill",),
                node_status="running",
                service_outcome="unknown_skill",
            )
        node_path += tick.node_path

        trace = PrimitiveActionTreeTrace(
            active_skill_before=active_skill_before,
            active_skill_after=str(policy._skill_name),
            switch_reason=str(policy._switch_reason),
            transition_timeout=False,
            transition_completed=policy._switch_reason.startswith(
                ("return_to_dig_", "return_to_pre_dig_align_")
            ),
            node_path=node_path,
            node_status=tick.node_status,
            service_outcome=tick.service_outcome,
            guard_facts=tick.guard_facts,
        )
        self.last_trace = trace
        return trace

    def _tick_bootstrap(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> _ActionTreeTickResult:
        if not policy._should_end_bootstrap(
            obs=obs,
            boundary_event=boundary_event,
        ):
            return _ActionTreeTickResult(
                node_path=("running",),
                service_outcome="running",
            )
        transition_request = policy.bootstrap_service.end_transition_request(
            pre_dig_align_before_dig=policy._should_pre_dig_align_before_dig(),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )
        transition = policy.bootstrap_service.end_transition(
            transition_request.facts,
            policy._bootstrap_config(),
            transition_request.transition_config,
        )
        policy._apply_bootstrap_transition_decision(transition)
        return _ActionTreeTickResult(
            node_path=("end_transition", str(transition.next_skill)),
            node_status=_node_status(
                active_skill_before=BOOTSTRAP_SKILL_NAME,
                active_skill_after=str(policy._skill_name),
                switch_reason=str(policy._switch_reason),
                service_outcome=str(transition.next_skill),
            ),
            service_outcome=str(transition.next_skill),
            guard_facts={
                "should_end_bootstrap": True,
                "next_skill": str(transition.next_skill),
            },
        )

    def _tick_pre_dig_align(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
    ) -> _ActionTreeTickResult:
        active_skill_before = str(policy._skill_name)
        outcome = policy._pre_dig_align_outcome(obs)
        policy._apply_pre_dig_align_outcome(outcome, obs)
        return _ActionTreeTickResult(
            node_path=(str(outcome.action),),
            node_status=_node_status(
                active_skill_before=active_skill_before,
                active_skill_after=str(policy._skill_name),
                switch_reason=str(policy._switch_reason),
                service_outcome=str(outcome.action),
            ),
            service_outcome=str(outcome.action),
            guard_facts={
                "outcome_action": str(outcome.action),
                "reject_reason": str(outcome.reject_reason),
            },
        )

    def _tick_dig(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> _ActionTreeTickResult:
        active_skill_before = str(policy._skill_name)
        projection = policy._dig_transition_runtime(
            obs=obs,
            boundary_event=boundary_event,
        )
        outcome = projection.outcome
        policy._apply_dig_transition_runtime_projection(projection, obs)
        action = str(getattr(outcome, "action", ""))
        failed_dig_reason = str(getattr(outcome, "failed_dig_reason", ""))
        dig_to_carry_reason = str(
            getattr(projection, "dig_to_carry_reason", "")
        )
        return _ActionTreeTickResult(
            node_path=(action,),
            node_status=_node_status(
                active_skill_before=active_skill_before,
                active_skill_after=str(policy._skill_name),
                switch_reason=str(policy._switch_reason),
                service_outcome=action,
            ),
            service_outcome=action,
            guard_facts={
                "exit_guard_ready": (
                    failed_dig_reason == "exit_overshoot_low_payload"
                ),
                "bad_replan_ready": failed_dig_reason == "bad_dig_low_payload",
                "complete_boundary_low_payload": (
                    failed_dig_reason == "complete_low_payload"
                ),
                "dig_to_carry_ready": action == "carry",
                "dig_to_carry_reason": (
                    dig_to_carry_reason if action == "carry" else ""
                ),
            },
        )

    def _tick_carry(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> _ActionTreeTickResult:
        active_skill_before = str(policy._skill_name)
        runtime = policy._carry_transition_runtime(
            obs=obs,
            boundary_event=boundary_event,
            current_dump_ready_hold_count=policy._dump_ready_hold_count,
        )
        policy._apply_carry_transition_runtime(runtime, obs)
        action = str(getattr(runtime.outcome, "action", ""))
        switch_reason = str(getattr(runtime.outcome, "switch_reason", ""))
        return _ActionTreeTickResult(
            node_path=(action,),
            node_status=_node_status(
                active_skill_before=active_skill_before,
                active_skill_after=str(policy._skill_name),
                switch_reason=str(policy._switch_reason),
                service_outcome=action,
            ),
            service_outcome=action,
            guard_facts={
                "release_safety_done": switch_reason.endswith(
                    "release_safety"
                ),
                "dump_ready": switch_reason.endswith("target_ready"),
            },
        )

    def _tick_dump(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> _ActionTreeTickResult:
        active_skill_before = str(policy._skill_name)
        runtime = policy._dump_transition_runtime(
            obs=obs,
            boundary_event=boundary_event,
            current_dump_done_hold_count=policy._dump_done_hold_count,
        )
        policy._apply_dump_transition_runtime(runtime, obs)
        action = str(getattr(runtime.outcome, "action", ""))
        switch_reason = str(getattr(runtime.outcome, "switch_reason", ""))
        return _ActionTreeTickResult(
            node_path=(action,),
            node_status=_node_status(
                active_skill_before=active_skill_before,
                active_skill_after=str(policy._skill_name),
                switch_reason=str(policy._switch_reason),
                service_outcome=action,
            ),
            service_outcome=action,
            guard_facts={
                "dump_done": switch_reason == "dump_to_return_mass_low",
                "dump_done_use_boundary_event": bool(
                    policy.dump_done_use_boundary_event
                ),
            },
        )

    def _tick_return(
        self,
        policy: PrimitivePlannerACTPolicy,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> _ActionTreeTickResult:
        active_skill_before = str(policy._skill_name)
        handoff_ready = policy._return_to_dig_handoff_ready(obs)
        request = policy.return_transition_service.transition_request(
            handoff_ready=handoff_ready,
            boundary_event=boundary_event,
            previous_next_dig_event_seen=policy._return_next_dig_event_seen,
            semantic_boundary_profile_active=policy._semantic_boundary_profile_active(),
        )
        direct_handoff_ready = False
        shallow_guard_ready = False
        if request.should_check_direct_handoff:
            direct_handoff_ready = policy._return_to_dig_direct_handoff_ready(
                obs,
                handoff_ready=handoff_ready,
            )
        if request.should_check_shallow_guard(direct_handoff_ready):
            shallow_guard_ready = policy._return_to_dig_shallow_guard_ready(
                obs=obs,
                boundary_event=boundary_event,
            )
        outcome = policy.return_transition_service.classify(
            request.facts_with_gate_results(
                direct_handoff_ready=direct_handoff_ready,
                shallow_guard_ready=shallow_guard_ready,
            ),
            request.config,
        )
        projection = policy.return_transition_service.transition_runtime_projection(
            outcome
        )
        if not policy._apply_return_to_dig_transition_runtime_projection(projection):
            return _ActionTreeTickResult(
                node_path=(str(outcome.action),),
                node_status=_node_status(
                    active_skill_before=active_skill_before,
                    active_skill_after=str(policy._skill_name),
                    switch_reason=str(policy._switch_reason),
                    service_outcome=str(outcome.action),
                ),
                service_outcome=str(outcome.action),
                guard_facts={
                    "handoff_ready": bool(handoff_ready),
                    "direct_handoff_ready": bool(direct_handoff_ready),
                    "shallow_guard_ready": bool(shallow_guard_ready),
                },
            )
        completion_request = policy.return_transition_service.completion_request(
            pre_dig_align_before_dig=policy._should_pre_dig_align_before_dig(),
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )
        completion = policy.return_transition_service.transition_completion(
            outcome,
            completion_request.facts,
            completion_request.config,
        )
        policy._apply_return_to_dig_transition_completion(completion)
        return _ActionTreeTickResult(
            node_path=(str(outcome.action), "completion"),
            node_status=_node_status(
                active_skill_before=active_skill_before,
                active_skill_after=str(policy._skill_name),
                switch_reason=str(policy._switch_reason),
                service_outcome=str(outcome.action),
            ),
            service_outcome=str(outcome.action),
            guard_facts={
                "handoff_ready": bool(handoff_ready),
                "direct_handoff_ready": bool(direct_handoff_ready),
                "shallow_guard_ready": bool(shallow_guard_ready),
            },
        )


@contextmanager
def patch_primitive_action_tree_predict() -> (
    Iterator[weakref.WeakKeyDictionary[Any, PrimitiveActionTreeRunner]]
):
    """Temporarily route primitive planner ``predict`` through the shadow runner.

    This helper is intentionally process-scoped and shadow-only. It exists so
    eval scripts can compare the action-tree shell without adding a production
    config flag or changing the live planner entry point.
    """

    from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy

    original_predict = PrimitivePlannerACTPolicy.predict
    runners: weakref.WeakKeyDictionary[Any, PrimitiveActionTreeRunner]
    runners = weakref.WeakKeyDictionary()

    def _shadow_predict(policy: PrimitivePlannerACTPolicy, obs: dict[str, Any]) -> np.ndarray:
        runner = runners.get(policy)
        if runner is None:
            runner = PrimitiveActionTreeRunner()
            runners[policy] = runner
        return runner.predict(policy, obs)

    PrimitivePlannerACTPolicy.predict = _shadow_predict  # type: ignore[method-assign]
    try:
        yield runners
    finally:
        PrimitivePlannerACTPolicy.predict = original_predict  # type: ignore[method-assign]


def _node_status(
    *,
    active_skill_before: str,
    active_skill_after: str,
    switch_reason: str,
    service_outcome: str,
) -> str:
    if str(active_skill_after) != str(active_skill_before):
        return "switched"
    if str(switch_reason) or str(service_outcome) not in {"", "none", "running"}:
        return "handled"
    return "running"


def _policy_reset_count_total(policy: PrimitivePlannerACTPolicy) -> int:
    total = 0
    try:
        policies = policy._all_policies()
    except Exception:
        return 0
    for active_policy in policies:
        try:
            total += int(getattr(active_policy, "reset_count", 0))
        except Exception:
            continue
    return total
