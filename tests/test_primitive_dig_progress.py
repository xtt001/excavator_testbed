from __future__ import annotations

from dataclasses import fields
import numpy as np

from testbed.data.schema import ENV_STATE_MASS_IN_BUCKET_IDX
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_dig_progress import (
    PrimitiveDigProgressRuntimeConfig,
    PrimitiveDigProgressRuntimePorts,
    PrimitiveDigProgressRuntimeService,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _facts_provider(action_dim: int = 4):
    from testbed.planner.primitive_capabilities import PrimitiveObservationFacts

    return lambda obs: PrimitiveObservationFacts.from_obs(obs, action_dim=action_dim)


def test_dig_progress_ports_expose_state_owners_and_typed_fact_source() -> None:
    port_fields = {field.name for field in fields(PrimitiveDigProgressRuntimePorts)}

    assert {
        "cycle_state",
        "coverage_state",
        "observation_facts",
        "config",
    }.issubset(port_fields)
    assert "mass_in_bucket" not in port_fields


def test_dig_progress_service_updates_cycle_and_coverage_from_task_metrics() -> None:
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    service = PrimitiveDigProgressRuntimeService.from_ports(
        PrimitiveDigProgressRuntimePorts(
            cycle_state=cycle_state,
            coverage_state=coverage_state,
            observation_facts=_facts_provider(),
            config=PrimitiveDigProgressRuntimeConfig(plateau_epsilon_kg=0.5),
        )
    )

    service.update({"task_metrics": {"mass_in_bucket_kg": 12.0}})
    service.update({"task_metrics": {"mass_in_bucket_kg": 12.25}})

    assert cycle_state.dig_step_count == 2
    assert cycle_state.dig_best_mass_kg == 12.25
    assert cycle_state.dig_mass_plateau_count == 1
    assert coverage_state.coverage_current_payload_gain_kg == 12.25


def test_dig_progress_service_uses_env_state_fallback_without_lowering_payload() -> None:
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    coverage_state.coverage_current_payload_gain_kg = 20.0
    service = PrimitiveDigProgressRuntimeService.from_ports(
        PrimitiveDigProgressRuntimePorts(
            cycle_state=cycle_state,
            coverage_state=coverage_state,
            observation_facts=_facts_provider(),
            config=PrimitiveDigProgressRuntimeConfig(plateau_epsilon_kg=0.5),
        )
    )
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 8.0

    service.update({"env_state": env_state})

    assert cycle_state.dig_step_count == 1
    assert cycle_state.dig_best_mass_kg == 8.0
    assert cycle_state.dig_mass_plateau_count == 0
    assert coverage_state.coverage_current_payload_gain_kg == 20.0


def test_policy_update_dig_progress_delegates_without_old_mass_wrapper() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    policy.dig_to_carry_mass_plateau_epsilon_kg = 0.5

    policy._update_dig_progress({"task_metrics": {"mass_in_bucket_kg": 9.0}})

    assert policy._primitive_cycle_runtime_state().dig_step_count == 1
    assert policy._primitive_cycle_runtime_state().dig_best_mass_kg == 9.0
    assert policy._coverage_runtime_state().coverage_current_payload_gain_kg == 9.0
