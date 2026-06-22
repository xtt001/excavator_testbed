from __future__ import annotations

from dataclasses import fields
from typing import Any

from testbed.planner.primitive_backend import (
    LegacyFSMBranchPorts,
    LegacyFSMBranchSet,
    LegacyFSMDecisionBackendFactory,
    LegacyFSMRequestedDecisionBackend,
    LegacyFSMCompatibilityDecisionBackend,
    PrimitiveDecisionBackendFactory,
)
from testbed.planner.primitive_backend_facts import PrimitiveBackendFactsAccess
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import (
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
)


class _FactoryFactsSource:
    def decision_facts(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionFacts:
        return PrimitiveDecisionFacts.from_context(
            context,
            current_skill_name=str(context.skill_name_before_decision),
            current_switch_reason="",
        )

    def backend_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveBackendFactsAccess:
        raise AssertionError("factory tests must not read backend facts")


class _FactoryCompatibilityActions:
    def sync_dig_transition_reason(
        self,
        dig_facts: PrimitiveDigTransitionFacts,
    ) -> None:
        raise AssertionError("factory tests must not sync dig reason")

    def refresh_return_transition_state(
        self,
        context: PrimitiveDecisionContext,
    ) -> None:
        raise AssertionError("factory tests must not refresh return")

    def handle_residual_pre_dig_align(
        self,
        context: PrimitiveDecisionContext,
    ) -> bool:
        raise AssertionError("factory tests must not handle residual")


def _branch_ports() -> LegacyFSMBranchPorts:
    return LegacyFSMBranchPorts(
        bootstrap_skill_name="bootstrap",
        pre_dig_align_skill_name="pre_dig_align",
        dig_skill_name="dig",
        carry_skill_name="carry",
        dump_skill_name="dump",
        return_skill_name="return",
        facts_source=_FactoryFactsSource(),
        compatibility_actions=_FactoryCompatibilityActions(),
    )


def test_legacy_fsm_backend_factory_reuses_branch_set_for_backend_construction() -> None:
    factory = LegacyFSMDecisionBackendFactory.from_ports(_branch_ports())

    branch_set = factory.branch_set()
    requested = factory.requested_decision_backend()
    compatibility = factory.compatibility_decision_backend()

    assert isinstance(branch_set, LegacyFSMBranchSet)
    assert isinstance(requested, LegacyFSMRequestedDecisionBackend)
    assert isinstance(compatibility, LegacyFSMCompatibilityDecisionBackend)
    assert requested.branch_set is branch_set
    assert compatibility.branch_set is branch_set
    assert factory.branch_set() is branch_set


def test_backend_factory_contract_exposes_backend_construction_only() -> None:
    public_names = {
        name for name in dir(PrimitiveDecisionBackendFactory) if not name.startswith("_")
    }

    assert "requested_decision_backend" in public_names
    assert "compatibility_decision_backend" in public_names
    assert {
        "planner",
        "self",
        "policy",
        "callback",
        "effect_applier",
        "apply_effects",
        "set_skill",
    }.isdisjoint(public_names)


def test_legacy_fsm_backend_factory_fields_do_not_expose_shell_objects() -> None:
    field_names = {field.name for field in fields(LegacyFSMDecisionBackendFactory)}

    assert {
        "planner",
        "self",
        "policy",
        "callback",
        "effect_applier",
        "apply_effects",
        "set_skill",
    }.isdisjoint(field_names)
