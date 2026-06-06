from __future__ import annotations

from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import DIG_CUT_TOKEN_DIM
from testbed.planner.policy_observation import PolicyObservationTokenRequest
from testbed.planner.dig_cut_plan import DigCutPlanState
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_apply_dig_cut_plan_state_writes_metadata_and_returns_token() -> None:
    policy = _make_policy()
    token = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)

    result = policy._apply_dig_cut_plan_state(
        DigCutPlanState(
            token=token,
            source="operator_prior_pose_clamped",
            fallback_reason="",
            token_in_prior_p10_p90=True,
        )
    )

    assert result is token
    assert policy._dig_cut_token_source == "operator_prior_pose_clamped"
    assert policy._dig_cut_fallback_reason == ""
    assert policy._dig_cut_token_in_prior_p10_p90 is True


def test_apply_dig_cut_plan_state_casts_token_to_float32() -> None:
    policy = _make_policy()

    result = policy._apply_dig_cut_plan_state(
        DigCutPlanState(
            token=np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64),
            source="fallback_conservative_pose",
            fallback_reason="missing prior field",
            token_in_prior_p10_p90=False,
        )
    )

    assert result.dtype == np.float32
    np.testing.assert_allclose(result, np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32))
    assert policy._dig_cut_token_source == "fallback_conservative_pose"
    assert policy._dig_cut_fallback_reason == "missing prior field"
    assert policy._dig_cut_token_in_prior_p10_p90 is False


def test_dig_cut_tokens_for_obs_respects_request_gate() -> None:
    policy = _make_policy()
    policy._dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("disabled dig-cut token request must not build")

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._dig_cut_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_cut_tokens=False),
    )

    assert result is None


def test_dig_cut_tokens_for_obs_reuses_existing_token_for_terminal_stop() -> None:
    policy = _make_policy()
    tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)
    policy._dig_cut_tokens = tokens
    policy._coverage_terminal_stop_requested = True
    policy._skill_name = "dig"

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("terminal-stop dig-cut token reuse must not build")

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._dig_cut_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_cut_tokens=True),
    )
    tokens[0] = 99.0

    assert result.dtype == np.float64
    np.testing.assert_allclose(
        result,
        np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64),
    )


def test_dig_cut_tokens_for_obs_terminal_stop_non_dig_returns_none() -> None:
    policy = _make_policy()
    policy._dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    policy._coverage_terminal_stop_requested = True
    policy._skill_name = "return"

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("terminal-stop non-dig token request must not build")

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._dig_cut_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_cut_tokens=True),
    )

    assert result is None


def test_dig_cut_tokens_for_obs_builds_before_projection() -> None:
    policy = _make_policy()
    calls: list[str] = []

    def ensure_plan(_obs: dict[str, np.ndarray]) -> None:
        calls.append("ensure")
        policy._dig_cut_tokens = (
            np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64) + 10.0
        )

    policy._ensure_dig_cut_plan_for_cycle = ensure_plan  # type: ignore[method-assign]

    result = policy._dig_cut_tokens_for_obs(
        {},
        PolicyObservationTokenRequest(dig_cut_tokens=True),
    )
    policy._dig_cut_tokens[0] = 99.0

    assert calls == ["ensure"]
    assert result.dtype == np.float64
    np.testing.assert_allclose(
        result,
        np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64) + 10.0,
    )


def _make_policy(**kwargs: Any) -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
        **kwargs,
    )


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
