from __future__ import annotations

from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    CUT_DEPTH_SEMANTIC_IDX,
    CUT_PAYLOAD_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.policy_observation import PolicyObservationTokenRequest
from testbed.planner.return_target_plan import ReturnRelocateObservationTokenResult
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_return_target_tokens_for_obs_applies_service_result() -> None:
    policy = _make_policy()
    tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    policy._return_target_tokens = tokens
    calls: list[str] = []

    def ensure_plan(_obs: dict[str, np.ndarray]) -> None:
        calls.append("ensure")

    policy._ensure_return_target_plan_for_cycle = ensure_plan  # type: ignore[method-assign]

    result = policy._return_target_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(return_target_tokens=True),
    )
    tokens[0] = 99.0

    assert calls == ["ensure"]
    assert result.dtype == np.float64
    np.testing.assert_allclose(
        result,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64),
    )


def test_return_target_tokens_for_obs_respects_token_request_gate() -> None:
    policy = _make_policy()
    policy._return_target_tokens = np.arange(
        RETURN_TARGET_TOKEN_DIM,
        dtype=np.float32,
    )

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("disabled return-target token request must not build")

    policy._ensure_return_target_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._return_target_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(return_target_tokens=False),
    )

    assert result is None
    np.testing.assert_allclose(
        policy._return_target_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )


def test_return_relocate_tokens_for_obs_applies_service_result() -> None:
    policy = _make_policy()
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    target_tokens[CUT_DEPTH_SEMANTIC_IDX] = 7.0
    target_tokens[CUT_PAYLOAD_IDX] = 8.0
    policy._return_target_tokens = target_tokens.copy()
    calls: list[str] = []

    def ensure_plan(_obs: dict[str, np.ndarray]) -> None:
        calls.append("ensure")

    policy._ensure_return_target_plan_for_cycle = ensure_plan  # type: ignore[method-assign]

    result = policy._return_relocate_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(return_relocate_tokens=True),
    )

    assert calls == ["ensure"]
    assert result is policy._return_relocate_tokens
    assert result.dtype == np.float32
    assert float(result[CUT_DEPTH_SEMANTIC_IDX]) == 0.0
    assert float(result[CUT_PAYLOAD_IDX]) == 0.0
    np.testing.assert_allclose(policy._return_target_tokens, target_tokens)


def test_return_relocate_tokens_for_obs_respects_token_request_gate() -> None:
    policy = _make_policy()
    policy._return_relocate_tokens = np.arange(
        RETURN_TARGET_TOKEN_DIM,
        dtype=np.float32,
    )

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("disabled return-relocate token request must not build")

    policy._ensure_return_target_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._return_relocate_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(return_relocate_tokens=False),
    )

    assert result is None
    np.testing.assert_allclose(
        policy._return_relocate_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )


def test_apply_return_relocate_token_result_writes_tokens() -> None:
    policy = _make_policy()
    tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)

    result = policy._apply_return_relocate_token_result(
        ReturnRelocateObservationTokenResult(tokens=tokens)
    )

    assert result is tokens
    assert policy._return_relocate_tokens is tokens


def test_return_start_envelope_tokens_for_obs_applies_service_result() -> None:
    policy = _make_policy()
    tokens = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    policy._return_start_envelope_tokens = tokens
    calls: list[str] = []

    def ensure_plan(_obs: dict[str, np.ndarray]) -> None:
        calls.append("ensure")

    policy._ensure_return_target_plan_for_cycle = ensure_plan  # type: ignore[method-assign]

    result = policy._return_start_envelope_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(return_start_envelope_tokens=True),
    )
    tokens[0] = 99.0

    assert calls == ["ensure"]
    assert result.dtype == np.float64
    np.testing.assert_allclose(
        result,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64),
    )


def test_return_start_envelope_tokens_for_obs_respects_token_request_gate() -> None:
    policy = _make_policy()
    policy._return_start_envelope_tokens = np.arange(
        RETURN_START_ENVELOPE_TOKEN_DIM,
        dtype=np.float32,
    )

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError(
            "disabled return-start-envelope token request must not build"
        )

    policy._ensure_return_target_plan_for_cycle = fail_ensure  # type: ignore[method-assign]

    result = policy._return_start_envelope_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(return_start_envelope_tokens=False),
    )

    assert result is None
    np.testing.assert_allclose(
        policy._return_start_envelope_tokens,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
    )


def _obs() -> dict[str, np.ndarray]:
    return {
        "env_state": np.zeros(64, dtype=np.float32),
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
