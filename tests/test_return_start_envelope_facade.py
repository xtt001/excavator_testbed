from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.planner.return_start_envelope import ReturnStartEnvelopeState
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_apply_return_start_envelope_token_result_writes_source_bounds_and_token() -> None:
    policy = _make_policy()
    token = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)

    result = policy._apply_return_start_envelope_token_result(
        ReturnStartEnvelopeState(
            token=token,
            source="qc6_return_start_envelope_cell_3",
            use_prior_spatial_bounds=False,
            use_prior_qpos_bounds=True,
        )
    )

    assert result is token
    assert policy._return_start_envelope_token_source == (
        "qc6_return_start_envelope_cell_3"
    )
    assert policy._return_start_envelope_use_prior_spatial_bounds is False
    assert policy._return_start_envelope_use_prior_qpos_bounds is True


def test_apply_return_start_envelope_token_result_keeps_missing_token_error() -> None:
    policy = _make_policy()

    with pytest.raises(
        RuntimeError,
        match="return start-envelope builder returned no token",
    ):
        policy._apply_return_start_envelope_token_result(ReturnStartEnvelopeState())


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
