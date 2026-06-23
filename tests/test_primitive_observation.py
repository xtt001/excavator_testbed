from __future__ import annotations

from dataclasses import fields
from types import MethodType
from typing import Any

from testbed.planner.primitive_observation import (
    PrimitiveObservationInjectionRuntimeState,
    PrimitivePolicyObservationAssembler,
    PrimitivePolicyObservationAssemblerPorts,
    PrimitivePolicyObservationAssemblyResult,
    PrimitiveTokenInjectionState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_INJECTED_FLAG_NAMES = {
    "cell_entry_token_injected",
    "dig_cut_token_injected",
    "dig_depth_profile_token_injected",
    "return_target_token_injected",
    "return_relocate_token_injected",
    "return_start_envelope_token_injected",
}


def _ports(
    events: list[str],
    *,
    goal: Any = None,
    dig_cut: Any = None,
    dig_depth_profile: Any = None,
    return_target: Any = None,
    return_relocate: Any = None,
    return_start_envelope: Any = None,
) -> PrimitivePolicyObservationAssemblerPorts:
    def record(name: str, value: Any) -> Any:
        events.append(name)
        return value

    return PrimitivePolicyObservationAssemblerPorts(
        goal_tokens=lambda: record("goal", goal),
        dig_cut_tokens=lambda obs: record("dig_cut", dig_cut),
        dig_depth_profile_tokens=lambda obs: record(
            "dig_depth_profile",
            dig_depth_profile,
        ),
        return_target_tokens=lambda obs: record("return_target", return_target),
        return_relocate_tokens=lambda obs: record("return_relocate", return_relocate),
        return_start_envelope_tokens=lambda obs: record(
            "return_start_envelope",
            return_start_envelope,
        ),
    )


def test_policy_observation_assembler_returns_original_obs_when_no_tokens() -> None:
    events: list[str] = []
    obs = {"qpos": [1.0], "env_state": [0.0]}

    result = PrimitivePolicyObservationAssembler(
        ports=_ports(events),
    ).assemble(obs)

    assert result.policy_obs is obs
    assert result.token_injection_state == PrimitiveTokenInjectionState()
    assert events == [
        "goal",
        "dig_cut",
        "dig_depth_profile",
        "return_target",
        "return_relocate",
        "return_start_envelope",
    ]


def test_policy_observation_assembler_injects_tokens_into_copy_in_legacy_order() -> None:
    events: list[str] = []
    obs = {"qpos": [1.0]}
    tokens = {
        "goal": object(),
        "dig_cut": object(),
        "dig_depth_profile": object(),
        "return_target": object(),
        "return_relocate": object(),
        "return_start_envelope": object(),
    }

    result = PrimitivePolicyObservationAssembler(
        ports=_ports(events, **tokens),
    ).assemble(obs)

    assert result.policy_obs is not obs
    assert obs == {"qpos": [1.0]}
    assert result.policy_obs["goal_tokens"] is tokens["goal"]
    assert result.policy_obs["dig_cut_tokens"] is tokens["dig_cut"]
    assert (
        result.policy_obs["dig_depth_profile_tokens_v1"]
        is tokens["dig_depth_profile"]
    )
    assert result.policy_obs["return_target_tokens"] is tokens["return_target"]
    assert result.policy_obs["return_relocate_tokens_v1"] is tokens["return_relocate"]
    assert (
        result.policy_obs["return_start_envelope_tokens_v1"]
        is tokens["return_start_envelope"]
    )
    assert "cell_entry_tokens" not in result.policy_obs
    assert result.token_injection_state == PrimitiveTokenInjectionState(
        dig_cut_token_injected=True,
        dig_depth_profile_token_injected=True,
        return_target_token_injected=True,
        return_relocate_token_injected=True,
        return_start_envelope_token_injected=True,
    )
    assert events == [
        "goal",
        "dig_cut",
        "dig_depth_profile",
        "return_target",
        "return_relocate",
        "return_start_envelope",
    ]


def test_policy_observation_assembler_goal_token_has_no_legacy_injected_flag() -> None:
    result = PrimitivePolicyObservationAssembler(
        ports=_ports([], goal=object()),
    ).assemble({"qpos": [1.0]})

    assert "goal_tokens" in result.policy_obs
    assert result.token_injection_state == PrimitiveTokenInjectionState()


def test_policy_observation_assembler_has_no_cell_entry_runtime_provider() -> None:
    port_fields = {field.name for field in fields(PrimitivePolicyObservationAssemblerPorts)}

    assert "cell_entry_tokens" not in port_fields

    result = PrimitivePolicyObservationAssembler(
        ports=_ports([]),
    ).assemble({"qpos": [1.0]})

    assert "cell_entry_tokens" not in result.policy_obs
    assert result.token_injection_state == PrimitiveTokenInjectionState()


def test_observation_injection_runtime_state_clear_apply_and_projection() -> None:
    state = PrimitiveObservationInjectionRuntimeState.fresh()

    assert state.to_token_injection_state() == PrimitiveTokenInjectionState()

    state.apply_token_injection_state(
        PrimitiveTokenInjectionState(
            cell_entry_token_injected=True,
            dig_cut_token_injected=True,
            dig_depth_profile_token_injected=True,
            return_target_token_injected=True,
            return_relocate_token_injected=True,
            return_start_envelope_token_injected=True,
        )
    )

    assert state.to_token_injection_state() == PrimitiveTokenInjectionState(
        cell_entry_token_injected=True,
        dig_cut_token_injected=True,
        dig_depth_profile_token_injected=True,
        return_target_token_injected=True,
        return_relocate_token_injected=True,
        return_start_envelope_token_injected=True,
    )

    state.clear()

    assert state.to_token_injection_state() == PrimitiveTokenInjectionState()


def test_policy_no_longer_exposes_old_observation_injection_flag_facades() -> None:
    removed_names = {f"_{name}" for name in _INJECTED_FLAG_NAMES}

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


def test_policy_reset_application_replaces_observation_injection_state_owner() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    old_state = planner._primitive_observation_injection_runtime_state()
    old_state.apply_token_injection_state(
        PrimitiveTokenInjectionState(dig_cut_token_injected=True)
    )
    reset_state = PrimitiveObservationInjectionRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_observation_injection_state": reset_state}

    planner._apply_reset_lifecycle_state(_ResetState())
    reset_state.return_target_token_injected = True

    assert planner._primitive_observation_injection_runtime_state() is reset_state
    assert planner._primitive_observation_injection_runtime_state() is not old_state
    assert reset_state.to_token_injection_state() == PrimitiveTokenInjectionState(
        return_target_token_injected=True,
    )
    assert old_state.to_token_injection_state() == PrimitiveTokenInjectionState(
        dig_cut_token_injected=True,
    )


def test_policy_obs_delegates_to_assembler_and_writes_legacy_flags() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    state = planner._primitive_observation_injection_runtime_state()
    state.apply_token_injection_state(
        PrimitiveTokenInjectionState(
            cell_entry_token_injected=True,
            dig_cut_token_injected=True,
            dig_depth_profile_token_injected=True,
            return_target_token_injected=True,
            return_relocate_token_injected=True,
            return_start_envelope_token_injected=True,
        )
    )
    obs = {"qpos": [1.0]}
    assembled_obs = {"qpos": [1.0], "dig_cut_tokens": object()}

    class _FakeAssembler:
        def assemble(
            self,
            got_obs: dict[str, Any],
        ) -> PrimitivePolicyObservationAssemblyResult:
            assert got_obs is obs
            assert state.to_token_injection_state() == PrimitiveTokenInjectionState()
            return PrimitivePolicyObservationAssemblyResult(
                policy_obs=assembled_obs,
                token_injection_state=PrimitiveTokenInjectionState(
                    dig_cut_token_injected=True,
                    return_target_token_injected=True,
                ),
            )

    planner._policy_observation_assembler = MethodType(
        lambda self: _FakeAssembler(),
        planner,
    )

    result = planner._policy_obs(obs)

    assert result is assembled_obs
    assert state.to_token_injection_state() == PrimitiveTokenInjectionState(
        dig_cut_token_injected=True,
        return_target_token_injected=True,
    )
