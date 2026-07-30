"""Non-default behavior-tree decision backend for primitive planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from testbed.planner.primitive.decision.backends.legacy_fsm import (
    PrimitiveCompatibilityDecisionBackend,
    PrimitiveDecisionBackend,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.decision.contracts import (
    CompleteReturnTransitionEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    SwitchToNextSkillAfterReturnEffect,
)
from testbed.planner.primitive.decision.input import (
    PrimitiveBackendDecisionInput,
    PrimitiveBackendDecisionInputBuilder,
)
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation

BEHAVIOR_TREE_DECISION_BACKEND_NAME = "behavior_tree_shadow"
BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE = "behavior_tree_continue_current_skill"
BEHAVIOR_TREE_RETURN_COMPLETED_DECISION_SOURCE = (
    "behavior_tree_return_completed_transition"
)

BehaviorTreeNodeStatus = Literal["success", "failure"]


@dataclass(frozen=True)
class BehaviorTreeNodeTrace:
    """Consumer-neutral behavior-tree node outcome for decision explanation."""

    node_name: str
    status: BehaviorTreeNodeStatus
    reason: str = ""


@dataclass(frozen=True)
class BehaviorTreeDecisionOutcome:
    """Decision plus BT-specific trace payload for a generic trace adapter."""

    result: PrimitiveDecisionResult
    trace: tuple[BehaviorTreeNodeTrace, ...]


@dataclass(frozen=True)
class BehaviorTreeTickResult:
    """Internal behavior-tree tick result."""

    status: BehaviorTreeNodeStatus
    result: PrimitiveDecisionResult | None
    trace: tuple[BehaviorTreeNodeTrace, ...]


class BehaviorTreeDecisionNode(Protocol):
    """Behavior-tree decision node over one backend input packet."""

    name: str

    def tick(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> BehaviorTreeTickResult: ...


@dataclass(frozen=True)
class ContinueCurrentSkillNode:
    """Fallback node that explicitly requests no planner state change."""

    name: str = "continue_current_skill"

    def tick(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> BehaviorTreeTickResult:
        skill_name = str(decision_input.common.skill_name_before_decision)
        return BehaviorTreeTickResult(
            status="success",
            result=PrimitiveDecisionResult.from_requested_effects(
                decision_source=BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE,
                status="no_change",
                skill_before=skill_name,
                skill_after=skill_name,
                switch_reason="",
                effects=(),
            ),
            trace=(
                BehaviorTreeNodeTrace(
                    node_name=self.name,
                    status="success",
                    reason="continue_current_skill",
                ),
            ),
        )


@dataclass(frozen=True)
class ReturnCompletedTransitionNode:
    """Return-to-next-skill branch using existing return transition facts."""

    return_skill_name: str = "return"
    name: str = "return_completed_transition"

    def tick(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> BehaviorTreeTickResult:
        common = decision_input.common
        skill_before = str(common.skill_name_before_decision)
        if not common.is_current_skill(self.return_skill_name):
            return _bt_failure(self.name, "not_return_skill")

        status = decision_input.backend_facts.return_transition().status
        if not bool(status.completed_transition):
            return _bt_failure(self.name, "return_transition_incomplete")

        next_skill = str(status.next_skill).strip()
        reason_suffix = _return_transition_reason_suffix(status)
        if not next_skill or not reason_suffix:
            return _bt_failure(self.name, "return_transition_missing_reason")

        switch_reason = str(status.switch_reason).strip()
        if not switch_reason:
            switch_reason = f"return_to_{next_skill}_{reason_suffix}"

        effects: list[
            MarkReturnNextDigEventSeenEffect
            | CompleteReturnTransitionEffect
            | SwitchToNextSkillAfterReturnEffect
        ] = []
        if bool(status.next_dig_event):
            effects.append(MarkReturnNextDigEventSeenEffect())
        effects.append(CompleteReturnTransitionEffect())
        effects.append(SwitchToNextSkillAfterReturnEffect(reason_suffix=reason_suffix))
        return BehaviorTreeTickResult(
            status="success",
            result=PrimitiveDecisionResult.from_requested_effects(
                decision_source=BEHAVIOR_TREE_RETURN_COMPLETED_DECISION_SOURCE,
                status="skill_switch",
                skill_before=skill_before,
                skill_after=next_skill,
                switch_reason=switch_reason,
                effects=tuple(effects),
            ),
            trace=(
                BehaviorTreeNodeTrace(
                    node_name=self.name,
                    status="success",
                    reason=switch_reason,
                ),
            ),
        )


@dataclass(frozen=True)
class BehaviorTreeSelectorNode:
    """Ordered fallback selector for behavior-tree decision nodes."""

    name: str
    children: tuple[BehaviorTreeDecisionNode, ...]

    def tick(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> BehaviorTreeTickResult:
        child_traces: list[BehaviorTreeNodeTrace] = []
        for child in self.children:
            child_result = child.tick(decision_input)
            child_traces.extend(child_result.trace)
            if child_result.status == "success" and child_result.result is not None:
                return BehaviorTreeTickResult(
                    status="success",
                    result=child_result.result,
                    trace=(
                        BehaviorTreeNodeTrace(
                            node_name=self.name,
                            status="success",
                            reason=f"selected:{child.name}",
                        ),
                        *child_traces,
                    ),
                )
        return BehaviorTreeTickResult(
            status="failure",
            result=None,
            trace=(
                BehaviorTreeNodeTrace(
                    node_name=self.name,
                    status="failure",
                    reason="no_child_selected",
                ),
                *child_traces,
            ),
        )


def default_behavior_tree_root() -> BehaviorTreeSelectorNode:
    """Build the initial shadow BT root with an explicit continue fallback."""

    return BehaviorTreeSelectorNode(
        name="behavior_tree_root",
        children=(ReturnCompletedTransitionNode(), ContinueCurrentSkillNode()),
    )


@dataclass(frozen=True)
class BehaviorTreeDecisionBackend:
    """Requested-effect backend backed by a small behavior tree."""

    input_builder: PrimitiveBackendDecisionInputBuilder
    root: BehaviorTreeDecisionNode = field(default_factory=default_behavior_tree_root)

    def decide_context_with_trace(
        self,
        context: PrimitiveDecisionContext,
    ) -> BehaviorTreeDecisionOutcome:
        decision_input = self.input_builder.build(context)
        tick_result = self.root.tick(decision_input)
        if tick_result.result is None:
            raise PrimitiveDecisionContractError(
                "behavior tree decision root failed without a fallback result"
            )
        return BehaviorTreeDecisionOutcome(
            result=tick_result.result,
            trace=tick_result.trace,
        )

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult:
        return self.decide_context_with_trace(context).result

    def decide_tick(
        self,
        *,
        obs: dict[str, object],
        boundary_event: object | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


@dataclass(frozen=True)
class BehaviorTreeCompatibilityDecisionBackend:
    """No legacy compatibility decision is provided by the BT shadow backend."""

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        del context
        return None

    def decide_tick(
        self,
        *,
        obs: dict[str, object],
        boundary_event: object | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        del obs, boundary_event, preparation
        return None


@dataclass(frozen=True)
class BehaviorTreeDecisionBackendFactoryPorts:
    """Typed construction ports for the non-default BT shadow backend."""

    input_builder: PrimitiveBackendDecisionInputBuilder
    root: BehaviorTreeDecisionNode | None = None


@dataclass(frozen=True)
class BehaviorTreeDecisionBackendFactory:
    """Build behavior-tree requested and compatibility backend instances."""

    ports: BehaviorTreeDecisionBackendFactoryPorts

    @classmethod
    def from_ports(
        cls,
        ports: BehaviorTreeDecisionBackendFactoryPorts,
    ) -> BehaviorTreeDecisionBackendFactory:
        return cls(ports=ports)

    def requested_decision_backend(self) -> PrimitiveDecisionBackend:
        return BehaviorTreeDecisionBackend(
            input_builder=self.ports.input_builder,
            root=(
                self.ports.root
                if self.ports.root is not None
                else default_behavior_tree_root()
            ),
        )

    def compatibility_decision_backend(
        self,
    ) -> PrimitiveCompatibilityDecisionBackend:
        return BehaviorTreeCompatibilityDecisionBackend()


def _bt_failure(name: str, reason: str) -> BehaviorTreeTickResult:
    return BehaviorTreeTickResult(
        status="failure",
        result=None,
        trace=(
            BehaviorTreeNodeTrace(
                node_name=name,
                status="failure",
                reason=reason,
            ),
        ),
    )


def _return_transition_reason_suffix(status: object) -> str:
    if bool(getattr(status, "next_or_seen_dig_event", False)) and bool(
        getattr(status, "handoff_ready", False)
    ):
        return "next_dig_entry_ready"
    if bool(getattr(status, "direct_handoff_ready", False)):
        return "start_envelope_ready"
    if bool(getattr(status, "shallow_guard_allowed", False)):
        return "shallow_entry_guard"
    return ""


__all__ = [
    "BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE",
    "BEHAVIOR_TREE_DECISION_BACKEND_NAME",
    "BEHAVIOR_TREE_RETURN_COMPLETED_DECISION_SOURCE",
    "BehaviorTreeCompatibilityDecisionBackend",
    "BehaviorTreeDecisionBackend",
    "BehaviorTreeDecisionBackendFactory",
    "BehaviorTreeDecisionBackendFactoryPorts",
    "BehaviorTreeDecisionNode",
    "BehaviorTreeDecisionOutcome",
    "BehaviorTreeNodeStatus",
    "BehaviorTreeNodeTrace",
    "BehaviorTreeSelectorNode",
    "BehaviorTreeTickResult",
    "ContinueCurrentSkillNode",
    "ReturnCompletedTransitionNode",
    "default_behavior_tree_root",
]
