from __future__ import annotations

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


def _ports(
    events: list[str],
    *,
    goal: Any = None,
    cell_entry: Any = None,
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
        cell_entry_tokens=lambda obs: record("cell_entry", cell_entry),
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
        "cell_entry",
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
        "cell_entry": object(),
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
    assert result.policy_obs["cell_entry_tokens"] is tokens["cell_entry"]
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
    assert result.token_injection_state == PrimitiveTokenInjectionState(
        cell_entry_token_injected=True,
        dig_cut_token_injected=True,
        dig_depth_profile_token_injected=True,
        return_target_token_injected=True,
        return_relocate_token_injected=True,
        return_start_envelope_token_injected=True,
    )
    assert events == [
        "goal",
        "cell_entry",
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


def test_policy_observation_assembler_cell_entry_flag_is_compatibility_only() -> None:
    # Cell-entry token injection remains a compatibility-only legacy token path.
    result = PrimitivePolicyObservationAssembler(
        ports=_ports([], cell_entry=object()),
    ).assemble({"qpos": [1.0]})

    assert "cell_entry_tokens" in result.policy_obs
    assert result.token_injection_state == PrimitiveTokenInjectionState(
        cell_entry_token_injected=True,
    )


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


def test_policy_legacy_injected_flags_are_backed_by_one_observation_state() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    state = planner._primitive_observation_injection_runtime_state()

    planner._cell_entry_token_injected = 1
    planner._dig_cut_token_injected = True
    planner._dig_depth_profile_token_injected = False
    planner._return_target_token_injected = True
    planner._return_relocate_token_injected = False
    planner._return_start_envelope_token_injected = True

    assert planner._primitive_observation_injection_runtime_state() is state
    assert state.to_token_injection_state() == PrimitiveTokenInjectionState(
        cell_entry_token_injected=True,
        dig_cut_token_injected=True,
        dig_depth_profile_token_injected=False,
        return_target_token_injected=True,
        return_relocate_token_injected=False,
        return_start_envelope_token_injected=True,
    )
    assert planner._cell_entry_token_injected is True
    assert planner._dig_cut_token_injected is True
    assert planner._dig_depth_profile_token_injected is False
    assert planner._return_target_token_injected is True
    assert planner._return_relocate_token_injected is False
    assert planner._return_start_envelope_token_injected is True


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
    planner._return_target_token_injected = True

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
    planner._cell_entry_token_injected = True
    planner._dig_cut_token_injected = True
    planner._dig_depth_profile_token_injected = True
    planner._return_target_token_injected = True
    planner._return_relocate_token_injected = True
    planner._return_start_envelope_token_injected = True
    obs = {"qpos": [1.0]}
    assembled_obs = {"qpos": [1.0], "dig_cut_tokens": object()}

    class _FakeAssembler:
        def assemble(
            self,
            got_obs: dict[str, Any],
        ) -> PrimitivePolicyObservationAssemblyResult:
            assert got_obs is obs
            assert planner._cell_entry_token_injected is False
            assert planner._dig_cut_token_injected is False
            assert planner._dig_depth_profile_token_injected is False
            assert planner._return_target_token_injected is False
            assert planner._return_relocate_token_injected is False
            assert planner._return_start_envelope_token_injected is False
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
    assert planner._cell_entry_token_injected is False
    assert planner._dig_cut_token_injected is True
    assert planner._dig_depth_profile_token_injected is False
    assert planner._return_target_token_injected is True
    assert planner._return_relocate_token_injected is False
    assert planner._return_start_envelope_token_injected is False
