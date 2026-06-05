from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.planner.dig_depth_profile import (
    DigDepthProfileBuildRequest,
    DigDepthProfileConfig,
    DigDepthProfileMissingPriorError,
    DigDepthProfileService,
)


def test_live_plan_builds_finite_profile_token() -> None:
    state = DigDepthProfileService().build_token(
        DigDepthProfileBuildRequest(
            cell_id=2,
            raw_fields=_raw_fields(),
            env_state=np.zeros(64, dtype=np.float32),
            config=DigDepthProfileConfig(source="live_plan"),
        )
    )

    assert state.source == "live_plan"
    assert state.fallback_reason == ""
    assert state.token.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert np.all(np.isfinite(state.token))
    assert state.token[-1] == pytest.approx(1.0)


def test_prior_profile_prefers_state_exemplar_token() -> None:
    exemplar = np.linspace(0.0, 1.0, DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)

    state = DigDepthProfileService().build_token(
        DigDepthProfileBuildRequest(
            cell_id=2,
            raw_fields=_raw_fields(),
            env_state=np.zeros(64, dtype=np.float32),
            config=DigDepthProfileConfig(source="prior_profile", required=True),
            dig_cut_prior={"dig_depth_profile_cells": []},
            state_exemplar_profile_token=exemplar,
        )
    )

    assert state.source == "qc6_state_conditioned_exemplar"
    assert state.fallback_reason == ""
    np.testing.assert_allclose(state.token, exemplar)


def test_prior_profile_uses_cell_prior_before_global() -> None:
    cell_token = np.full(DIG_DEPTH_PROFILE_TOKEN_DIM, 0.25, dtype=np.float32)
    cell_token[-1] = 1.0
    global_token = np.full(DIG_DEPTH_PROFILE_TOKEN_DIM, 0.75, dtype=np.float32)
    global_token[-1] = 1.0

    state = DigDepthProfileService().build_token(
        DigDepthProfileBuildRequest(
            cell_id=2,
            raw_fields=_raw_fields(),
            env_state=np.zeros(64, dtype=np.float32),
            config=DigDepthProfileConfig(source="prior_profile"),
            dig_cut_prior={
                "dig_depth_profile_cells": [
                    {"cell_id": 2, "token_median": cell_token}
                ],
                "dig_depth_profile_global": {"token_median": global_token},
            },
        )
    )

    assert state.source == "qc6_dig_depth_profile_cell_2"
    assert state.fallback_reason == ""
    np.testing.assert_allclose(state.token, cell_token)


def test_required_prior_profile_missing_cell_raises_with_reason() -> None:
    service = DigDepthProfileService()

    with pytest.raises(DigDepthProfileMissingPriorError) as excinfo:
        service.build_token(
            DigDepthProfileBuildRequest(
                cell_id=5,
                raw_fields=_raw_fields(),
                env_state=np.zeros(64, dtype=np.float32),
                config=DigDepthProfileConfig(
                    source="prior_profile",
                    required=True,
                    allow_live_fallback=False,
                    allow_global_fallback=False,
                ),
                dig_cut_prior={"dig_depth_profile_cells": []},
            )
        )

    assert excinfo.value.cell_id == 5
    assert excinfo.value.reason == "missing dig_depth_profile_cells entry for cell 5"
    assert "requires a matching" in str(excinfo.value)


def _raw_fields() -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.5,
        "operator_entry_y_m": -0.03,
        "operator_entry_z_m": 0.2,
        "operator_exit_x_m": 1.2,
        "operator_exit_y_m": -0.10,
        "operator_exit_z_m": 0.7,
        "operator_cut_length_m": 0.8,
        "operator_cut_depth_peak_m": 0.12,
        "operator_cut_payload_gain_kg": 30.0,
        "operator_effective_deposit_delta_kg": 28.0,
        "operator_cut_valid": 1,
    }
