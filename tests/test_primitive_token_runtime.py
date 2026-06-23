from __future__ import annotations

from dataclasses import fields
from types import MethodType

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.primitive_token_runtime import (
    PrimitiveTokenRuntimeCoordinator,
    PrimitiveTokenRuntimePorts,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _token(size: int, value: float) -> np.ndarray:
    return np.full(size, value, dtype=np.float32)


_TOKEN_STATE_FIELD_NAMES = set(PrimitiveTokenRuntimeState.__dataclass_fields__)


class _PortState:
    def __init__(
        self,
        facts: dict[str, object],
        token_state: PrimitiveTokenRuntimeState,
    ) -> None:
        self._facts = facts
        self.token_state = token_state

    def __getitem__(self, name: str) -> object:
        if name in _TOKEN_STATE_FIELD_NAMES:
            return getattr(self.token_state, name)
        return self._facts[name]

    def __setitem__(self, name: str, value: object) -> None:
        if name in _TOKEN_STATE_FIELD_NAMES:
            setattr(self.token_state, name, value)
            return
        self._facts[name] = value


def _ports(
    *,
    state: dict[str, object] | None = None,
    events: list[str] | None = None,
) -> tuple[PrimitiveTokenRuntimePorts, _PortState, list[str]]:
    defaults = {
        "skill": "dig",
        "bootstrap_policy_available": True,
        "dig_cut_planner_enabled": True,
        "dig_cut_hold_token_until_skill_exit": False,
        "coverage_terminal_stop_requested": False,
        "cycle_index": 3,
        "dig_cut_planned_cycle_id": -1,
        "dig_cut_tokens": _token(DIG_CUT_TOKEN_DIM, 1.0),
        "dig_depth_profile_tokens": _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 2.0),
        "dig_cut_token_source": "old",
        "dig_cut_fallback_reason": "old_reason",
        "dig_cut_token_in_prior_p10_p90": True,
        "return_target_planner_enabled": True,
        "return_target_hold_token_until_skill_exit": False,
        "return_target_planned_cycle_id": -1,
        "return_target_tokens": _token(RETURN_TARGET_TOKEN_DIM, 3.0),
        "return_relocate_tokens": np.zeros(4, dtype=np.float32),
        "return_start_envelope_tokens": _token(
            RETURN_START_ENVELOPE_TOKEN_DIM,
            4.0,
        ),
        "return_target_token_source": "old_return",
        "return_start_envelope_token_source": "old_start",
        "return_target_fallback_reason": "old_fallback",
        "pending_dig_cut_cycle_id": 8,
        "pending_dig_cut_corridor_id": 9,
        "pending_dig_cut_raw_fields": {"old": 1.0},
        "pending_dig_cut_tokens": _token(DIG_CUT_TOKEN_DIM, 5.0),
        "pending_dig_depth_profile_tokens": _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 6.0),
        "pending_dig_state_exemplar_ids": ["old"],
        "pending_dig_state_exemplar_distance": 7.0,
    }
    defaults.update(state or {})
    facts = {
        name: value
        for name, value in defaults.items()
        if name not in _TOKEN_STATE_FIELD_NAMES
    }
    token_state = PrimitiveTokenRuntimeState.fresh()
    for name, value in defaults.items():
        if name in _TOKEN_STATE_FIELD_NAMES:
            setattr(token_state, name, value)
    coverage_state = CoverageRuntimeState()
    coverage_state.coverage_active_state_exemplar_ids = ["ex_a", "ex_b"]
    coverage_state.coverage_active_state_exemplar_distance = 1.25
    coverage_state.coverage_active_state_exemplar_profile_token = _token(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        8.0,
    )
    state_view = _PortState(facts=facts, token_state=token_state)
    facts["coverage_state"] = coverage_state
    events = events if events is not None else []

    def build_dig_cut(obs: dict) -> np.ndarray:
        events.append(f"build_dig_cut:{obs['id']}")
        return _token(DIG_CUT_TOKEN_DIM, 11.0)

    def build_depth(obs: dict) -> np.ndarray:
        events.append(f"build_depth:{obs['id']}")
        return _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 12.0)

    def build_return_plan(obs: dict):
        events.append(f"build_return_plan:{obs['id']}")
        return (
            _token(RETURN_TARGET_TOKEN_DIM, 13.0),
            {"operator_entry_x_m": 1.5},
            "operator_prior_coverage",
            "",
            42,
        )

    def build_start_envelope(
        obs: dict,
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int,
    ) -> np.ndarray:
        events.append(
            "build_start_envelope:"
            f"{obs['id']}:{raw_fields['operator_entry_x_m']}:{corridor_id}"
        )
        return _token(RETURN_START_ENVELOPE_TOKEN_DIM, 14.0)

    def plan_relocate(return_target_tokens: np.ndarray) -> np.ndarray:
        events.append(f"plan_relocate:{float(return_target_tokens[0])}")
        return np.asarray([15.0, 16.0, 17.0], dtype=np.float32)

    return (
        PrimitiveTokenRuntimePorts(
            state=token_state,
            coverage_state=coverage_state,
            current_skill_name=lambda: str(state_view["skill"]),
            bootstrap_policy_available=lambda: bool(
                state_view["bootstrap_policy_available"]
            ),
            cycle_index=lambda: int(state_view["cycle_index"]),
            dig_cut_planner_enabled=lambda: bool(
                state_view["dig_cut_planner_enabled"]
            ),
            dig_cut_hold_token_until_skill_exit=lambda: bool(
                state_view["dig_cut_hold_token_until_skill_exit"]
            ),
            coverage_terminal_stop_requested=lambda: bool(
                state_view["coverage_terminal_stop_requested"]
            ),
            return_target_planner_enabled=lambda: bool(
                state_view["return_target_planner_enabled"]
            ),
            return_target_hold_token_until_skill_exit=lambda: bool(
                state_view["return_target_hold_token_until_skill_exit"]
            ),
            build_dig_cut_tokens_for_obs=build_dig_cut,
            build_dig_depth_profile_tokens_for_obs=build_depth,
            build_next_dig_cut_plan_for_return=build_return_plan,
            build_return_start_envelope_tokens_for_obs=build_start_envelope,
            plan_return_relocate_tokens=plan_relocate,
        ),
        state_view,
        events,
    )


def test_dig_cut_disabled_returns_none_without_builders() -> None:
    ports, _, events = _ports(state={"dig_cut_planner_enabled": False})

    result = PrimitiveTokenRuntimeCoordinator.from_ports(ports).dig_cut_tokens_for_obs(
        {"id": "obs"}
    )

    assert result is None
    assert events == []


def test_terminal_stop_returns_cached_dig_copies_only_for_active_dig() -> None:
    ports, state, events = _ports(
        state={"coverage_terminal_stop_requested": True, "skill": "dig"}
    )

    token = PrimitiveTokenRuntimeCoordinator.from_ports(ports).dig_cut_tokens_for_obs(
        {"id": "obs"}
    )
    depth = (
        PrimitiveTokenRuntimeCoordinator.from_ports(
            ports
        ).dig_depth_profile_tokens_for_obs({"id": "obs"})
    )

    assert events == []
    assert token is not state["dig_cut_tokens"]
    assert depth is not state["dig_depth_profile_tokens"]
    np.testing.assert_allclose(token, state["dig_cut_tokens"])
    np.testing.assert_allclose(depth, state["dig_depth_profile_tokens"])
    token[0] = 99.0
    assert float(state["dig_cut_tokens"][0]) == 1.0

    non_dig_ports, _, _ = _ports(
        state={"coverage_terminal_stop_requested": True, "skill": "carry"}
    )
    runtime = PrimitiveTokenRuntimeCoordinator.from_ports(non_dig_ports)
    assert runtime.dig_cut_tokens_for_obs({"id": "obs"}) is None
    assert runtime.dig_depth_profile_tokens_for_obs({"id": "obs"}) is None


def test_dig_tokens_skip_non_dig_except_bootstrap_policy_exception() -> None:
    ports, _, events = _ports(state={"skill": "carry"})

    assert (
        PrimitiveTokenRuntimeCoordinator.from_ports(ports).dig_cut_tokens_for_obs(
            {"id": "obs"}
        )
        is None
    )
    assert events == []

    bootstrap_ports, _, bootstrap_events = _ports(
        state={"skill": "bootstrap", "bootstrap_policy_available": True}
    )
    result = PrimitiveTokenRuntimeCoordinator.from_ports(
        bootstrap_ports
    ).dig_cut_tokens_for_obs({"id": "boot"})

    np.testing.assert_allclose(result, _token(DIG_CUT_TOKEN_DIM, 11.0))
    assert bootstrap_events == ["build_dig_cut:boot", "build_depth:boot"]


def test_dig_hold_cycle_hit_skips_rebuild_and_miss_builds_both_tokens() -> None:
    ports, _, events = _ports(
        state={
            "dig_cut_hold_token_until_skill_exit": True,
            "dig_cut_planned_cycle_id": 3,
        }
    )
    runtime = PrimitiveTokenRuntimeCoordinator.from_ports(ports)

    token = runtime.dig_cut_tokens_for_obs({"id": "held"})

    np.testing.assert_allclose(token, _token(DIG_CUT_TOKEN_DIM, 1.0))
    assert events == []

    miss_ports, state, miss_events = _ports(
        state={
            "dig_cut_hold_token_until_skill_exit": True,
            "dig_cut_planned_cycle_id": 2,
        }
    )
    miss_runtime = PrimitiveTokenRuntimeCoordinator.from_ports(miss_ports)

    token = miss_runtime.dig_depth_profile_tokens_for_obs({"id": "miss"})

    np.testing.assert_allclose(token, _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 12.0))
    assert miss_events == ["build_dig_cut:miss", "build_depth:miss"]
    assert int(state["dig_cut_planned_cycle_id"]) == 3


def test_return_tokens_disabled_or_non_return_return_none() -> None:
    disabled_ports, _, disabled_events = _ports(
        state={"return_target_planner_enabled": False, "skill": "return"}
    )
    assert (
        PrimitiveTokenRuntimeCoordinator.from_ports(
            disabled_ports
        ).return_target_tokens_for_obs({"id": "obs"})
        is None
    )
    assert disabled_events == []

    carry_ports, _, carry_events = _ports(state={"skill": "carry"})
    runtime = PrimitiveTokenRuntimeCoordinator.from_ports(carry_ports)
    assert runtime.return_target_tokens_for_obs({"id": "obs"}) is None
    assert runtime.return_relocate_tokens_for_obs({"id": "obs"}) is None
    assert runtime.return_start_envelope_tokens_for_obs({"id": "obs"}) is None
    assert carry_events == []


def test_return_hold_cycle_hit_skips_rebuild_and_returns_copies() -> None:
    ports, state, events = _ports(
        state={
            "skill": "return",
            "return_target_hold_token_until_skill_exit": True,
            "return_target_planned_cycle_id": 3,
        }
    )
    runtime = PrimitiveTokenRuntimeCoordinator.from_ports(ports)

    target = runtime.return_target_tokens_for_obs({"id": "held"})
    relocate = runtime.return_relocate_tokens_for_obs({"id": "held"})
    envelope = runtime.return_start_envelope_tokens_for_obs({"id": "held"})

    assert events == ["plan_relocate:3.0"]
    assert target is not state["return_target_tokens"]
    assert relocate is not state["return_relocate_tokens"]
    assert envelope is not state["return_start_envelope_tokens"]
    np.testing.assert_allclose(
        state["return_relocate_tokens"],
        np.asarray([15.0, 16.0, 17.0], dtype=np.float32),
    )
    target[0] = 99.0
    assert float(state["return_target_tokens"][0]) == 3.0


def test_ensure_return_target_success_writes_tokens_and_pending_plan() -> None:
    ports, state, events = _ports(state={"skill": "return"})

    PrimitiveTokenRuntimeCoordinator.from_ports(ports).ensure_return_target_plan_for_cycle(
        {"id": "ret"}
    )

    assert events == [
        "build_return_plan:ret",
        "build_start_envelope:ret:1.5:42",
    ]
    np.testing.assert_allclose(
        state["return_target_tokens"],
        _token(RETURN_TARGET_TOKEN_DIM, 13.0),
    )
    np.testing.assert_allclose(
        state["return_start_envelope_tokens"],
        _token(RETURN_START_ENVELOPE_TOKEN_DIM, 14.0),
    )
    assert state["return_target_token_source"] == "operator_prior_coverage"
    assert state["return_target_fallback_reason"] == ""
    assert int(state["return_target_planned_cycle_id"]) == 3
    assert int(state["pending_dig_cut_cycle_id"]) == 4
    assert state["pending_dig_cut_raw_fields"] == {"operator_entry_x_m": 1.5}
    np.testing.assert_allclose(
        state["pending_dig_cut_tokens"],
        _token(RETURN_TARGET_TOKEN_DIM, 13.0),
    )
    assert int(state["pending_dig_cut_corridor_id"]) == 42
    np.testing.assert_allclose(
        state["pending_dig_depth_profile_tokens"],
        _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 8.0),
    )
    coverage_state = state["coverage_state"]
    assert isinstance(coverage_state, CoverageRuntimeState)
    assert (
        state["pending_dig_depth_profile_tokens"]
        is not coverage_state.coverage_active_state_exemplar_profile_token
    )
    assert state["pending_dig_state_exemplar_ids"] == ["ex_a", "ex_b"]
    assert float(state["pending_dig_state_exemplar_distance"]) == 1.25


def test_ensure_return_target_exception_writes_fallback_and_invalidates_pending() -> None:
    def fail_build_return_plan(obs: dict):
        raise RuntimeError("bad return plan")

    ports, state, events = _ports(state={"skill": "return"})
    ports = PrimitiveTokenRuntimePorts(
        **{
            field.name: (
                fail_build_return_plan
                if field.name == "build_next_dig_cut_plan_for_return"
                else getattr(ports, field.name)
            )
            for field in fields(PrimitiveTokenRuntimePorts)
        }
    )

    PrimitiveTokenRuntimeCoordinator.from_ports(ports).ensure_return_target_plan_for_cycle(
        {"id": "ret"}
    )

    np.testing.assert_allclose(
        state["return_target_tokens"],
        np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    np.testing.assert_allclose(
        state["return_start_envelope_tokens"],
        np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
    )
    assert state["return_target_token_source"] == "fallback_zero"
    assert state["return_start_envelope_token_source"] == "fallback_zero"
    assert state["return_target_fallback_reason"] == "bad return plan"
    assert int(state["return_target_planned_cycle_id"]) == 3
    assert int(state["pending_dig_cut_cycle_id"]) == -1
    assert state["pending_dig_cut_raw_fields"] is None
    assert state["pending_dig_cut_tokens"] is None
    assert state["pending_dig_depth_profile_tokens"] is None
    assert state["pending_dig_state_exemplar_ids"] == []
    assert np.isnan(float(state["pending_dig_state_exemplar_distance"]))
    assert events == []


def test_clear_dig_cut_plan_and_invalidate_pending_plan_reset_exact_fields() -> None:
    ports, state, events = _ports()
    runtime = PrimitiveTokenRuntimeCoordinator.from_ports(ports)

    runtime.clear_dig_cut_plan()
    runtime.invalidate_pending_dig_cut_plan()

    assert int(state["dig_cut_planned_cycle_id"]) == -1
    np.testing.assert_allclose(
        state["dig_cut_tokens"],
        np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32),
    )
    np.testing.assert_allclose(
        state["dig_depth_profile_tokens"],
        np.zeros(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )
    assert state["dig_cut_token_source"] == "none"
    assert state["dig_cut_fallback_reason"] == ""
    assert state["dig_cut_token_in_prior_p10_p90"] is False
    coverage_state = state["coverage_state"]
    assert isinstance(coverage_state, CoverageRuntimeState)
    assert coverage_state.coverage_active_state_exemplar_ids == []
    assert np.isnan(coverage_state.coverage_active_state_exemplar_distance)
    assert coverage_state.coverage_active_state_exemplar_profile_token is None
    assert int(state["pending_dig_cut_cycle_id"]) == -1
    assert int(state["pending_dig_cut_corridor_id"]) == -1
    assert state["pending_dig_cut_raw_fields"] is None
    assert state["pending_dig_cut_tokens"] is None
    assert state["pending_dig_depth_profile_tokens"] is None
    assert state["pending_dig_state_exemplar_ids"] == []
    assert np.isnan(float(state["pending_dig_state_exemplar_distance"]))


def test_token_runtime_boundary_uses_typed_ports_without_planner_self() -> None:
    port_fields = {field.name for field in fields(PrimitiveTokenRuntimePorts)}
    coordinator_fields = {field.name for field in fields(PrimitiveTokenRuntimeCoordinator)}

    assert "state" in port_fields
    assert "coverage_state" in port_fields
    assert "get_dig_cut_tokens" not in port_fields
    assert "set_dig_cut_tokens" not in port_fields
    assert "set_return_target_tokens" not in port_fields
    assert "set_pending_dig_cut_cycle_id" not in port_fields
    assert "get_coverage_active_state_exemplar_ids" not in port_fields
    assert "get_coverage_active_state_exemplar_distance" not in port_fields
    assert "get_coverage_active_state_exemplar_profile_token" not in port_fields
    assert "clear_active_state_exemplar" not in port_fields
    assert "planner" not in port_fields
    assert "self" not in port_fields
    assert coordinator_fields == {"ports"}


def test_policy_token_runtime_facades_delegate_to_coordinator() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    calls: list[tuple[str, str]] = []

    class _FakeRuntime:
        def dig_cut_tokens_for_obs(self, obs: dict) -> np.ndarray:
            calls.append(("dig_cut", obs["id"]))
            return _token(DIG_CUT_TOKEN_DIM, 21.0)

        def ensure_return_target_plan_for_cycle(self, obs: dict) -> None:
            calls.append(("ensure_return", obs["id"]))

        def clear_dig_cut_plan(self) -> None:
            calls.append(("clear", ""))

    planner._primitive_token_runtime = MethodType(lambda self: _FakeRuntime(), planner)

    np.testing.assert_allclose(
        planner._dig_cut_tokens_for_obs({"id": "dig"}),
        _token(DIG_CUT_TOKEN_DIM, 21.0),
    )
    planner._ensure_return_target_plan_for_cycle({"id": "ret"})
    planner._clear_dig_cut_plan()

    assert calls == [("dig_cut", "dig"), ("ensure_return", "ret"), ("clear", "")]
