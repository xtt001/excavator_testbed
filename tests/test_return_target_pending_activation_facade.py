from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import RETURN_TARGET_TOKEN_DIM
from testbed.data.schema import ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
from testbed.planner.return_target_plan import (
    PendingReturnTargetActivation,
    build_pending_return_target_activation_facts,
)
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_pending_return_target_without_raw_fields_skips_prior_range_check() -> None:
    policy = _make_policy()
    policy._cycle_index = 4
    token = np.linspace(0.0, 1.0, RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    policy._pending_dig_cut_cycle_id = 4
    policy._pending_dig_cut_corridor_id = 7
    policy._pending_dig_cut_raw_fields = None
    policy._pending_dig_cut_tokens = token

    def fail_prior_range(_fields: dict[str, float | int]) -> bool:
        raise AssertionError("missing pending raw fields must not check prior range")

    policy._raw_fields_in_prior_range = fail_prior_range  # type: ignore[method-assign]

    result = policy._build_dig_cut_tokens_for_obs(_obs(deposited_mass=12.5))

    np.testing.assert_allclose(result, token)
    assert result.dtype == np.float32
    assert policy._dig_cut_token_source == "pending_return_target"
    assert policy._dig_cut_fallback_reason == ""
    assert policy._dig_cut_token_in_prior_p10_p90 is False
    assert policy._coverage_active_corridor_id == 7
    assert policy._coverage_last_selected_corridor_id == 7
    assert policy._coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert policy._coverage_cycle_start_deposit_kg == pytest.approx(12.5)


def test_pending_activation_facts_skip_prior_range_without_raw_fields() -> None:
    policy = _make_policy()
    policy._cycle_index = 4
    token = np.linspace(0.0, 1.0, RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    profile_token = np.arange(12, dtype=np.float64)
    policy._pending_dig_cut_cycle_id = 4
    policy._pending_dig_cut_corridor_id = 7
    policy._pending_dig_cut_raw_fields = None
    policy._pending_dig_cut_tokens = token
    policy._pending_dig_depth_profile_tokens = profile_token
    policy._pending_dig_state_exemplar_ids = ["cell7_deep"]
    policy._pending_dig_state_exemplar_distance = 0.25

    def fail_prior_range(_fields: dict[str, float | int]) -> bool:
        raise AssertionError("missing pending raw fields must not check prior range")

    policy._raw_fields_in_prior_range = fail_prior_range  # type: ignore[method-assign]

    facts = policy._pending_return_target_activation_facts(
        _obs(deposited_mass=12.5)
    )
    expected = build_pending_return_target_activation_facts(
        pending_dig_cut_tokens=token,
        pending_dig_cut_raw_fields=None,
        pending_dig_cut_corridor_id=7,
        pending_dig_depth_profile_tokens=profile_token,
        pending_dig_state_exemplar_ids=policy._pending_dig_state_exemplar_ids,
        pending_dig_state_exemplar_distance=0.25,
        raw_fields_in_prior_range=False,
        cycle_start_deposit_kg=12.5,
    )

    assert facts.pending_dig_cut_tokens is expected.pending_dig_cut_tokens
    assert facts.pending_dig_cut_raw_fields is expected.pending_dig_cut_raw_fields
    assert facts.pending_dig_cut_corridor_id == expected.pending_dig_cut_corridor_id
    assert (
        facts.pending_dig_depth_profile_tokens
        is expected.pending_dig_depth_profile_tokens
    )
    assert (
        facts.pending_dig_state_exemplar_ids
        is expected.pending_dig_state_exemplar_ids
    )
    assert facts.pending_dig_state_exemplar_distance == pytest.approx(
        expected.pending_dig_state_exemplar_distance
    )
    assert facts.raw_fields_in_prior_range is expected.raw_fields_in_prior_range
    assert facts.cycle_start_deposit_kg == pytest.approx(
        expected.cycle_start_deposit_kg
    )
    assert facts.pending_dig_cut_tokens is token
    assert facts.pending_dig_cut_raw_fields is None
    assert facts.pending_dig_cut_corridor_id == 7
    assert facts.pending_dig_depth_profile_tokens is profile_token
    assert facts.pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert facts.pending_dig_state_exemplar_distance == pytest.approx(0.25)
    assert facts.raw_fields_in_prior_range is False
    assert facts.cycle_start_deposit_kg == pytest.approx(12.5)


def test_apply_pending_return_target_activation_writes_state_and_copies_tokens() -> None:
    policy = _make_policy()
    token = np.linspace(0.0, 1.0, RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    profile_token = np.arange(12, dtype=np.float64)

    result = policy._apply_pending_return_target_activation(
        PendingReturnTargetActivation(
            dig_cut_tokens=token,
            dig_cut_token_source="pending_return_target",
            dig_cut_fallback_reason="",
            dig_cut_token_in_prior_p10_p90=True,
            coverage_active_corridor_id=7,
            coverage_last_selected_corridor_id=7,
            coverage_current_payload_gain_kg=0.0,
            coverage_cycle_start_deposit_kg=12.5,
            active_state_exemplar_ids=("cell7_deep",),
            active_state_exemplar_distance=0.25,
            active_state_exemplar_profile_token=profile_token,
        )
    )
    token[0] = 99.0
    profile_token[0] = 99.0

    np.testing.assert_allclose(
        result,
        np.linspace(0.0, 1.0, RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    assert result.dtype == np.float32
    assert policy._dig_cut_token_source == "pending_return_target"
    assert policy._dig_cut_fallback_reason == ""
    assert policy._dig_cut_token_in_prior_p10_p90 is True
    assert policy._coverage_active_corridor_id == 7
    assert policy._coverage_last_selected_corridor_id == 7
    assert policy._coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert policy._coverage_cycle_start_deposit_kg == pytest.approx(12.5)
    assert policy._coverage_active_state_exemplar_ids == ["cell7_deep"]
    assert policy._coverage_active_state_exemplar_distance == pytest.approx(0.25)
    np.testing.assert_allclose(
        policy._coverage_active_state_exemplar_profile_token,
        np.arange(12, dtype=np.float64),
    )
    assert policy._coverage_active_state_exemplar_profile_token.dtype == np.float64


def _obs(*, deposited_mass: float = 0.0) -> dict[str, np.ndarray]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited_mass)
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
