from __future__ import annotations

from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.schema import ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
from testbed.planner.dig_coverage.models import CoverageCorridorState
from testbed.planner.dig_depth_profile import (
    DigDepthProfileConfig,
    DigDepthProfileInputFacts,
    DigDepthProfileInputSourceCallbacks,
    DigDepthProfileState,
)
from testbed.planner.policy_observation import PolicyObservationTokenRequest
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_build_depth_profile_tokens_uses_input_facts_service() -> None:
    policy = _make_policy()
    policy._cycle_index = 8
    policy._pending_dig_cut_cycle_id = 8
    policy._pending_dig_cut_corridor_id = 7
    raw_fields = _raw_fields()
    policy._pending_dig_cut_raw_fields = raw_fields
    depth_profile = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)
    captured: dict[str, object] = {}

    def corridor_by_id(corridor_id: int) -> CoverageCorridorState:
        assert corridor_id == 7
        return CoverageCorridorState(
            corridor_id=7,
            entry_x_m=0.5,
            entry_z_m=-0.25,
            exit_x_m=-0.5,
            exit_z_m=-0.25,
            cell_id=3,
        )

    def build_from_facts(
        facts: DigDepthProfileInputFacts,
        *,
        config: DigDepthProfileConfig,
        dig_cut_prior: dict[str, Any] | None = None,
        state_exemplar_profile_token: object | None = None,
    ) -> DigDepthProfileState:
        captured["facts"] = facts
        captured["config"] = config
        captured["dig_cut_prior"] = dig_cut_prior
        captured["state_exemplar_profile_token"] = state_exemplar_profile_token
        return DigDepthProfileState(
            token=depth_profile,
            source="qc6_dig_depth_profile_cell_3",
            fallback_reason="",
        )

    policy._coverage_corridor_by_id = corridor_by_id  # type: ignore[method-assign]
    policy.dig_depth_profile_service.build_token_from_input_facts = (  # type: ignore[method-assign]
        build_from_facts
    )

    token = policy._build_dig_depth_profile_tokens_for_obs(_obs())

    facts = captured["facts"]
    assert isinstance(facts, DigDepthProfileInputFacts)
    assert facts.cycle_index == 8
    assert facts.pending_cycle_id == 8
    assert facts.pending_corridor_id == 7
    assert facts.pending_corridor_cell_id == 3
    assert facts.pending_raw_fields is raw_fields
    assert facts.env_state is not None
    assert captured["dig_cut_prior"] is policy.dig_cut_prior
    assert (
        captured["state_exemplar_profile_token"]
        is policy._coverage_active_state_exemplar_profile_token
    )
    np.testing.assert_allclose(
        token,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )
    assert token.dtype == np.float32
    assert policy._dig_depth_profile_token_source == "qc6_dig_depth_profile_cell_3"
    assert policy._dig_depth_profile_fallback_reason == ""


def test_apply_depth_profile_token_result_writes_source_fallback_and_token() -> None:
    policy = _make_policy()
    token = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)

    result = policy._apply_dig_depth_profile_token_result(
        DigDepthProfileState(
            token=token,
            source="qc6_dig_depth_profile_cell_3",
            fallback_reason="",
        )
    )

    assert result is token
    assert policy._dig_depth_profile_token_source == "qc6_dig_depth_profile_cell_3"
    assert policy._dig_depth_profile_fallback_reason == ""


def test_apply_depth_profile_token_result_casts_token_to_float32() -> None:
    policy = _make_policy()

    result = policy._apply_dig_depth_profile_token_result(
        DigDepthProfileState(
            token=np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64),
            source="fallback_live_plan",
            fallback_reason="missing dig_depth_profile_cells entry for cell 5",
        )
    )

    assert result.dtype == np.float32
    np.testing.assert_allclose(
        result,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )
    assert policy._dig_depth_profile_token_source == "fallback_live_plan"
    assert (
        policy._dig_depth_profile_fallback_reason
        == "missing dig_depth_profile_cells entry for cell 5"
    )


def test_dig_depth_profile_tokens_for_obs_respects_request_gate() -> None:
    policy = _make_policy()
    policy._dig_depth_profile_tokens = np.arange(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        dtype=np.float32,
    )

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("disabled depth-profile token request must not build")

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._dig_depth_profile_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_depth_profile_tokens=False),
    )

    assert result is None


def test_dig_depth_profile_tokens_for_obs_reuses_existing_token_for_terminal_stop() -> None:
    policy = _make_policy()
    tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)
    policy._dig_depth_profile_tokens = tokens
    policy._coverage_terminal_stop_requested = True
    policy._skill_name = "dig"

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("terminal-stop depth-profile token reuse must not build")

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._dig_depth_profile_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_depth_profile_tokens=True),
    )
    tokens[0] = 99.0

    assert result.dtype == np.float64
    np.testing.assert_allclose(
        result,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64),
    )


def test_dig_depth_profile_tokens_for_obs_terminal_stop_non_dig_returns_none() -> None:
    policy = _make_policy()
    policy._dig_depth_profile_tokens = np.arange(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        dtype=np.float32,
    )
    policy._coverage_terminal_stop_requested = True
    policy._skill_name = "return"

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("terminal-stop non-dig token request must not build")

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._dig_depth_profile_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_depth_profile_tokens=True),
    )

    assert result is None


def test_dig_depth_profile_tokens_for_obs_builds_before_projection() -> None:
    policy = _make_policy()
    calls: list[str] = []

    def ensure_plan(_obs: dict[str, np.ndarray]) -> None:
        calls.append("ensure")
        policy._dig_depth_profile_tokens = (
            np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64) + 10.0
        )

    policy._ensure_dig_cut_plan_for_cycle = ensure_plan  # type: ignore[method-assign]

    result = policy._dig_depth_profile_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_depth_profile_tokens=True),
    )
    policy._dig_depth_profile_tokens[0] = 99.0

    assert calls == ["ensure"]
    assert result.dtype == np.float64
    np.testing.assert_allclose(
        result,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64) + 10.0,
    )


def test_input_facts_use_active_when_pending_stale() -> None:
    policy = _make_policy()
    policy._cycle_index = 8
    policy._pending_dig_cut_cycle_id = 7
    policy._pending_dig_cut_corridor_id = 7
    policy._pending_dig_cut_raw_fields = {"operator_entry_x_m": 99.0}
    active_raw = _raw_fields()
    active_corridor = _corridor(cell_id=2)

    def raw_fields(
        corridor: CoverageCorridorState,
        *,
        obs: dict[str, np.ndarray],
    ) -> dict[str, float | int]:
        assert corridor is active_corridor
        return active_raw

    policy._coverage_active_corridor = lambda: active_corridor  # type: ignore[method-assign]
    policy._coverage_raw_fields = raw_fields  # type: ignore[method-assign]
    policy._raw_fields_from_live_pose = _fail_live  # type: ignore[method-assign]
    policy._env_state = _fail_env  # type: ignore[method-assign]

    facts = policy._dig_depth_profile_input_facts(_obs())

    assert facts.pending_raw_fields is None
    assert facts.pending_corridor_cell_id is None
    assert facts.active_corridor_raw_fields is active_raw
    assert facts.active_corridor_cell_id == 2
    assert facts.live_raw_fields is None
    assert facts.env_state is None


def test_input_facts_keep_pending_raw_and_fill_missing_cell_from_active() -> None:
    policy = _make_policy()
    policy._cycle_index = 8
    policy._pending_dig_cut_cycle_id = 8
    policy._pending_dig_cut_corridor_id = 99
    pending_raw = _raw_fields()
    policy._pending_dig_cut_raw_fields = pending_raw
    active_corridor = _corridor(cell_id=4)

    policy._coverage_corridor_by_id = lambda _id: None  # type: ignore[method-assign]
    policy._coverage_active_corridor = lambda: active_corridor  # type: ignore[method-assign]

    def fail_active_raw(
        _corridor: CoverageCorridorState,
        *,
        obs: dict[str, np.ndarray],
    ) -> dict[str, float | int]:
        raise AssertionError("pending raw fields should suppress active raw fields")

    policy._coverage_raw_fields = fail_active_raw  # type: ignore[method-assign]
    policy._raw_fields_from_live_pose = _fail_live  # type: ignore[method-assign]
    policy._env_state = _fail_env  # type: ignore[method-assign]

    facts = policy._dig_depth_profile_input_facts(_obs())

    assert facts.pending_raw_fields is pending_raw
    assert facts.pending_corridor_cell_id is None
    assert facts.active_corridor_raw_fields is None
    assert facts.active_corridor_cell_id == 4
    assert facts.live_raw_fields is None
    assert facts.env_state is None


def test_input_facts_sampling_plan_preserves_call_order_and_identity() -> None:
    policy = _make_policy()
    policy._cycle_index = 8
    policy._pending_dig_cut_cycle_id = 8
    policy._pending_dig_cut_corridor_id = 99
    pending_raw = _raw_fields()
    token = np.arange(8, dtype=np.float32)
    policy._pending_dig_cut_raw_fields = pending_raw
    policy._dig_cut_tokens = token
    active_corridor = _corridor(cell_id=4)
    calls: list[str] = []

    def corridor_by_id(corridor_id: int) -> None:
        calls.append(f"pending:{corridor_id}")
        return None

    def active() -> CoverageCorridorState:
        calls.append("active")
        return active_corridor

    def fail_active_raw(
        _corridor: CoverageCorridorState,
        *,
        obs: dict[str, np.ndarray],
    ) -> dict[str, float | int]:
        raise AssertionError("pending raw fields should suppress active raw fields")

    def fail_live(_obs: dict[str, np.ndarray]) -> dict[str, float | int]:
        raise AssertionError("pending raw fields should suppress live raw fields")

    def fail_env(_obs: dict[str, np.ndarray]) -> np.ndarray:
        raise AssertionError("active cell fallback should suppress env_state")

    policy._coverage_corridor_by_id = corridor_by_id  # type: ignore[method-assign]
    policy._coverage_active_corridor = active  # type: ignore[method-assign]
    policy._coverage_raw_fields = fail_active_raw  # type: ignore[method-assign]
    policy._raw_fields_from_live_pose = fail_live  # type: ignore[method-assign]
    policy._env_state = fail_env  # type: ignore[method-assign]

    facts = policy._dig_depth_profile_input_facts(_obs())

    assert calls == ["pending:99", "active"]
    assert facts.pending_raw_fields is pending_raw
    assert facts.pending_corridor_cell_id is None
    assert facts.active_corridor_raw_fields is None
    assert facts.active_corridor_cell_id == 4
    assert facts.live_raw_fields is None
    assert facts.current_dig_cut_tokens is token
    assert facts.env_state is None


def test_input_facts_facade_matches_service_callback_assembly() -> None:
    policy = _make_policy()
    policy._cycle_index = 8
    policy._pending_dig_cut_cycle_id = 8
    policy._pending_dig_cut_corridor_id = 99
    pending_raw = _raw_fields()
    token = np.arange(8, dtype=np.float32)
    policy._pending_dig_cut_raw_fields = pending_raw
    policy._dig_cut_tokens = token
    active_corridor = _corridor(cell_id=4)
    obs = _obs()

    policy._coverage_corridor_by_id = lambda _id: None  # type: ignore[method-assign]
    policy._coverage_active_corridor = lambda: active_corridor  # type: ignore[method-assign]
    policy._coverage_raw_fields = _fail_active_raw_fields  # type: ignore[method-assign]
    policy._raw_fields_from_live_pose = _fail_live  # type: ignore[method-assign]
    policy._env_state = _fail_env  # type: ignore[method-assign]

    def pending_corridor_cell_id(pending_corridor_id: int) -> int | None:
        corridor = policy._coverage_corridor_by_id(pending_corridor_id)
        if corridor is None:
            return None
        return int(corridor.cell_id)

    expected = policy.dig_depth_profile_service.input_facts_from_source_callbacks(
        cycle_index=int(policy._cycle_index),
        pending_cycle_id=int(policy._pending_dig_cut_cycle_id),
        pending_corridor_id=int(policy._pending_dig_cut_corridor_id),
        pending_raw_fields=policy._pending_dig_cut_raw_fields,
        current_dig_cut_tokens=policy._dig_cut_tokens,
        callbacks=DigDepthProfileInputSourceCallbacks(
            pending_corridor_cell_id=pending_corridor_cell_id,
            active_corridor=policy._coverage_active_corridor,
            active_corridor_raw_fields=lambda corridor: policy._coverage_raw_fields(
                corridor,
                obs=obs,
            ),
            active_corridor_cell_id=lambda corridor: int(corridor.cell_id),
            live_raw_fields=lambda: policy._raw_fields_from_live_pose(obs),
            env_state=lambda: policy._env_state(obs),
        ),
    )

    actual = policy._dig_depth_profile_input_facts(obs)

    _assert_input_facts_match(actual, expected)


def test_input_facts_include_env_when_no_pending_or_active_cell() -> None:
    policy = _make_policy()
    policy._cycle_index = 8
    live_raw = _raw_fields()
    env_state = np.arange(64, dtype=np.float32)

    policy._coverage_active_corridor = lambda: None  # type: ignore[method-assign]
    policy._raw_fields_from_live_pose = lambda _obs: live_raw  # type: ignore[method-assign]
    policy._env_state = lambda _obs: env_state  # type: ignore[method-assign]

    facts = policy._dig_depth_profile_input_facts(_obs())

    assert facts.pending_raw_fields is None
    assert facts.active_corridor_raw_fields is None
    assert facts.live_raw_fields is live_raw
    assert facts.pending_corridor_cell_id is None
    assert facts.active_corridor_cell_id is None
    assert facts.env_state is env_state


def _fail_live(_obs: dict[str, np.ndarray]) -> dict[str, float | int]:
    raise AssertionError("live raw fields should not be sampled")


def _fail_active_raw_fields(
    _corridor: CoverageCorridorState,
    *,
    obs: dict[str, np.ndarray],
) -> dict[str, float | int]:
    raise AssertionError("pending raw fields should suppress active raw fields")


def _fail_env(_obs: dict[str, np.ndarray]) -> np.ndarray:
    raise AssertionError("env_state should not be sampled")


def _assert_input_facts_match(
    actual: DigDepthProfileInputFacts,
    expected: DigDepthProfileInputFacts,
) -> None:
    assert actual.cycle_index == expected.cycle_index
    assert actual.pending_cycle_id == expected.pending_cycle_id
    assert actual.pending_corridor_id == expected.pending_corridor_id
    assert actual.pending_raw_fields is expected.pending_raw_fields
    assert actual.pending_corridor_cell_id == expected.pending_corridor_cell_id
    assert actual.active_corridor_raw_fields is expected.active_corridor_raw_fields
    assert actual.active_corridor_cell_id == expected.active_corridor_cell_id
    assert actual.live_raw_fields is expected.live_raw_fields
    assert actual.current_dig_cut_tokens is expected.current_dig_cut_tokens
    assert actual.env_state is expected.env_state


def _corridor(*, cell_id: int) -> CoverageCorridorState:
    return CoverageCorridorState(
        corridor_id=3,
        entry_x_m=0.5,
        entry_z_m=-0.25,
        exit_x_m=-0.5,
        exit_z_m=-0.25,
        cell_id=int(cell_id),
    )


def _obs() -> dict[str, np.ndarray]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 0.0
    return {
        "env_state": env_state,
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
    }


def _make_policy(**kwargs: Any) -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
        **kwargs,
    )


def _raw_fields() -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.5,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": -0.25,
        "operator_exit_x_m": -0.5,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": -0.25,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.0,
        "operator_cut_depth_peak_m": 0.08,
        "operator_cut_payload_gain_kg": 40.0,
        "operator_effective_deposit_delta_kg": 38.0,
        "operator_cut_valid": 1,
    }


class _ConstantPolicy(Policy):
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    def __init__(self) -> None:
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": "legacy"},
        )()

    def reset(self) -> None:
        pass

    def update(self, obs: dict, action: np.ndarray | None = None) -> Any:
        return None
