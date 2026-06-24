from __future__ import annotations

from dataclasses import fields
from typing import Any, get_type_hints

from testbed.planner.primitive.decision.backends import (
    legacy_fsm as primitive_backend_module,
)
from testbed.planner.primitive.decision.backends.legacy_fsm import (
    LegacyFSMBranchPorts,
    LegacyFSMBranchSet,
    LegacyFSMDecisionBackendFactory,
    LegacyFSMDecisionBackendFactoryPorts,
    LegacyFSMRequestedDecisionBackend,
    LegacyFSMCompatibilityDecisionBackend,
    PrimitiveCompatibilityDecisionBackend,
    PrimitiveDecisionBackend,
    PrimitiveDecisionBackendFactory,
)
from testbed.planner.primitive.facts.backend import PrimitiveBackendFactsAccess
from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
    PrimitiveFSMCapabilityProviderConfig,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.facts.decision import (
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
)
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState


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


def _branch_ports() -> LegacyFSMBranchPorts:
    return LegacyFSMBranchPorts(
        bootstrap_skill_name="bootstrap",
        dig_skill_name="dig",
        carry_skill_name="carry",
        dump_skill_name="dump",
        return_skill_name="return",
        facts_source=_FactoryFactsSource(),
        compatibility_actions=_FactoryCompatibilityActions(),
    )


class _ReturnHandoffReadinessService:
    def handoff_ready(self, obs: dict[str, Any]) -> bool:
        return True


def _capability_provider_config() -> PrimitiveFSMCapabilityProviderConfig:
    return PrimitiveFSMCapabilityProviderConfig(
        action_dim=4,
        dig_to_carry_min_distance_to_dig_area_m=0.0,
        dig_to_carry_min_bucket_mass_kg=0.0,
        dig_to_carry_target_bucket_mass_kg=0.0,
        dig_to_carry_mass_plateau_enabled=False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=0.0,
        dig_to_carry_mass_plateau_hold_steps=1,
        dig_to_carry_mass_plateau_min_steps=1,
        dump_ready_min_bucket_mass_kg=0.0,
        dig_bad_replan_enabled=False,
        dig_bad_replan_max_steps=1,
        dig_bad_replan_min_bucket_mass_kg=0.0,
        dig_exit_guard_enabled=False,
        dig_exit_guard_min_steps=1,
        dig_exit_guard_min_bucket_mass_kg=0.0,
        dig_exit_guard_overshoot_m=0.0,
        dump_ready_hold_steps=1,
        dump_ready_min_height_above_rim_m=0.0,
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=False,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="footprint",
        dump_ready_max_dump_area_footprint_outside_distance_m=None,
        dump_ready_min_dump_area_relative_x_m=None,
        dump_ready_max_dump_area_relative_x_m=None,
        dump_ready_min_dump_area_relative_z_m=None,
        dump_ready_max_dump_area_relative_z_m=None,
        dump_ready_near_window_enabled=False,
        dump_ready_near_window_x_tolerance_m=0.0,
        dump_ready_near_window_z_tolerance_m=0.0,
        dump_ready_near_window_outside_tolerance_m=0.0,
        dump_ready_near_window_require_over_footprint=False,
        dump_done_max_bucket_mass_kg=0.0,
        dump_done_min_deposit_delta_kg=0.0,
        dump_done_use_boundary_event=False,
        dump_done_hold_steps=1,
        return_to_dig_start_envelope_direct_handoff_enabled=False,
        return_to_dig_start_envelope_gate_enabled=False,
        return_to_dig_shallow_guard_enabled=False,
        return_to_dig_max_bucket_mass_kg=0.0,
        return_to_dig_touch_tolerance_m=0.0,
        return_to_dig_min_depth_m=0.0,
        return_to_dig_max_depth_m=0.0,
        return_to_dig_max_entry_error_m=None,
    )


def _factory_runtime_ports(
    **overrides: Any,
) -> LegacyFSMDecisionBackendFactoryPorts:
    values: dict[str, Any] = {
        "capability_provider_config": _capability_provider_config(),
        "semantic_boundary_profile_active": lambda: False,
        "cycle_state": PrimitiveCycleRuntimeState.fresh(),
        "coverage_state": CoverageRuntimeState(),
        "return_state": PrimitiveReturnRuntimeState.fresh(),
        "return_handoff_readiness_service": _ReturnHandoffReadinessService(),
        "current_skill_name": lambda: "dig",
        "current_switch_reason": lambda: "",
        "should_end_bootstrap": lambda *, obs, boundary_event: False,
        "bootstrap_end_mode": lambda: "first_qualified_dig_start",
        "bootstrap_skill_name": "bootstrap",
        "dig_skill_name": "dig",
        "carry_skill_name": "carry",
        "dump_skill_name": "dump",
        "return_skill_name": "return",
    }
    values.update(overrides)
    return LegacyFSMDecisionBackendFactoryPorts(**values)


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


def test_backend_factory_protocol_uses_generic_backend_annotations() -> None:
    requested_hints = get_type_hints(
        PrimitiveDecisionBackendFactory.requested_decision_backend,
        globalns=vars(primitive_backend_module),
    )
    compatibility_hints = get_type_hints(
        PrimitiveDecisionBackendFactory.compatibility_decision_backend,
        globalns=vars(primitive_backend_module),
    )

    assert requested_hints["return"] is PrimitiveDecisionBackend
    assert compatibility_hints["return"] is PrimitiveCompatibilityDecisionBackend


def test_legacy_fsm_backend_factory_from_runtime_ports_builds_branch_set() -> None:
    factory = LegacyFSMDecisionBackendFactory.from_runtime_ports(
        _factory_runtime_ports()
    )

    branch_set = factory.branch_set()

    assert isinstance(branch_set, LegacyFSMBranchSet)
    assert branch_set.bootstrap_branch.config.bootstrap_skill_name == "bootstrap"
    assert branch_set.dig_branch.config.dig_skill_name == "dig"
    assert branch_set.carry_branch.config.carry_skill_name == "carry"
    assert branch_set.dump_branch.config.dump_skill_name == "dump"
    assert branch_set.return_branch.config.return_skill_name == "return"
    assert factory.requested_decision_backend().branch_set is branch_set
    assert factory.compatibility_decision_backend().branch_set is branch_set


def test_legacy_fsm_backend_factory_runtime_ports_are_explicit_typed_inputs() -> None:
    field_names = {field.name for field in fields(LegacyFSMDecisionBackendFactoryPorts)}

    assert {
        "capability_provider_config",
        "semantic_boundary_profile_active",
        "cycle_state",
        "coverage_state",
        "return_state",
        "return_handoff_readiness_service",
        "current_skill_name",
        "current_switch_reason",
        "should_end_bootstrap",
        "bootstrap_end_mode",
    }.issubset(field_names)
    assert {
        "planner",
        "self",
        "policy",
        "callback",
        "__dict__",
        "mapping",
        "config",
    }.isdisjoint(field_names - {"capability_provider_config"})


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
