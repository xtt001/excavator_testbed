from __future__ import annotations

from dataclasses import fields
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.primitive.facts.observation import (
    PrimitiveObservationInjectionRuntimeState,
    PrimitivePolicyObservationAssembler,
    PrimitivePolicyObservationAssemblerPorts,
    PrimitivePolicyObservationAssemblyResult,
    PrimitiveTokenInjectionState,
)
from testbed.planner.primitive.token.observation_runtime import (
    PrimitiveTokenObservationRuntime,
    PrimitiveTokenObservationRuntimePorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_INJECTED_FLAG_NAMES = {
    "cell_entry_token_injected",
    "dig_cut_token_injected",
    "dig_depth_profile_token_injected",
    "return_target_token_injected",
    "return_relocate_token_injected",
    "return_start_envelope_token_injected",
}

_TOKEN_OBSERVATION_RUNTIME_WRAPPER_NAMES = {
    "policy_obs",
    "policy_observation_assembler",
    "policy_observation_assembler_ports",
    "clear_policy_observation_injected_flags",
    "apply_policy_observation_assembly",
    "return_target_tokens_for_obs",
    "return_relocate_tokens_for_obs",
    "return_start_envelope_tokens_for_obs",
    "ensure_return_target_plan_for_cycle",
    "dig_cut_tokens_for_obs",
    "dig_depth_profile_tokens_for_obs",
    "ensure_dig_cut_plan_for_cycle",
    "primitive_token_runtime",
    "primitive_token_runtime_ports",
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


def test_policy_no_longer_exposes_old_token_observation_runtime_wrappers() -> None:
    removed_names = {f"_{name}" for name in _TOKEN_OBSERVATION_RUNTIME_WRAPPER_NAMES}

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


def test_policy_action_dispatch_port_uses_token_observation_runtime() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"qpos": [1.0]}
    assembled_obs = {"qpos": [1.0], "dig_cut_tokens": object()}
    calls: list[str] = []

    class _FakeRuntime:
        def policy_obs(self, got_obs: dict[str, Any]) -> dict[str, Any]:
            assert got_obs is obs
            calls.append("policy_obs")
            return assembled_obs

    planner._primitive_token_observation_runtime = lambda: _FakeRuntime()
    planner.action_dim = 4
    planner.dig_policy = None
    planner.carry_policy = None
    planner.dump_policy = None
    planner.return_policy = None
    planner.first_dig_policy = None
    planner.bootstrap_policy = None

    result = planner._action_dispatch_ports().policy_observation(obs)

    assert result is assembled_obs
    assert calls == ["policy_obs"]


def test_token_observation_runtime_assembles_policy_obs_and_owns_injected_flags() -> None:
    injection_state = PrimitiveObservationInjectionRuntimeState.fresh()
    injection_state.apply_token_injection_state(
        PrimitiveTokenInjectionState(return_target_token_injected=True)
    )
    dig_cut = np.ones(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    dig_depth_profile = np.full(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        2.0,
        dtype=np.float32,
    )
    return_target = np.full(RETURN_TARGET_TOKEN_DIM, 3.0, dtype=np.float32)

    runtime = PrimitiveTokenObservationRuntime.from_ports(
        PrimitiveTokenObservationRuntimePorts(
            observation_injection_state=injection_state,
            token_state=PrimitiveTokenRuntimeState.fresh(),
            coverage_state=CoverageRuntimeState(),
            goal_tokens=lambda: None,
            current_skill_name=lambda: "dig",
            bootstrap_policy_available=lambda: False,
            cycle_index=lambda: 0,
            dig_cut_planner_enabled=lambda: True,
            dig_cut_hold_token_until_skill_exit=lambda: False,
            coverage_terminal_stop_requested=lambda: False,
            return_target_planner_enabled=lambda: True,
            return_target_hold_token_until_skill_exit=lambda: False,
            build_dig_cut_tokens_for_obs=lambda obs: dig_cut,
            build_dig_depth_profile_tokens_for_obs=lambda obs: dig_depth_profile,
            build_next_dig_cut_plan_for_return=lambda obs: (
                return_target,
                {},
                "test",
                "",
                0,
            ),
            build_return_start_envelope_tokens_for_obs=(
                lambda obs, raw_fields, *, corridor_id: np.zeros(
                    RETURN_START_ENVELOPE_TOKEN_DIM,
                    dtype=np.float32,
                )
            ),
            plan_return_relocate_tokens=lambda token: token.copy(),
        )
    )

    result = runtime.policy_obs({"id": "obs"})

    np.testing.assert_allclose(result["dig_cut_tokens"], dig_cut)
    np.testing.assert_allclose(
        result["dig_depth_profile_tokens_v1"],
        dig_depth_profile,
    )
    assert "return_target_tokens" not in result
    assert injection_state.to_token_injection_state() == PrimitiveTokenInjectionState(
        dig_cut_token_injected=True,
        dig_depth_profile_token_injected=True,
    )
