from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    CUT_DEPTH_SEMANTIC_IDX,
    CUT_DIR_X_IDX,
    CUT_DIR_Z_IDX,
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    CUT_EXIT_X_IDX,
    CUT_EXIT_Z_IDX,
    CUT_LENGTH_IDX,
    CUT_PAYLOAD_IDX,
    CUT_VALID_IDX,
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
)
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX
from testbed.planner.dig_depth_profile import (
    DigDepthProfileBuildRequest,
    DigDepthProfileConfig,
    DigDepthProfileInputFacts,
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


def test_resolve_raw_fields_prefers_pending_current_cycle() -> None:
    raw_fields = DigDepthProfileService.resolve_raw_fields(
        DigDepthProfileInputFacts(
            cycle_index=7,
            pending_cycle_id=7,
            pending_raw_fields={"operator_entry_x_m": 1.5},
            active_corridor_raw_fields={"operator_entry_x_m": 2.5},
            live_raw_fields={"operator_entry_x_m": 3.5},
            current_dig_cut_tokens=_dig_cut_token(),
        )
    )

    assert raw_fields == {"operator_entry_x_m": 1.5}


def test_resolve_raw_fields_uses_active_corridor_before_live_overlay() -> None:
    raw_fields = DigDepthProfileService.resolve_raw_fields(
        DigDepthProfileInputFacts(
            cycle_index=7,
            pending_cycle_id=6,
            pending_raw_fields={"operator_entry_x_m": 1.5},
            active_corridor_raw_fields={"operator_entry_x_m": 2.5},
            live_raw_fields={"operator_entry_x_m": 3.5},
            current_dig_cut_tokens=_dig_cut_token(),
        )
    )

    assert raw_fields == {"operator_entry_x_m": 2.5}


def test_resolve_raw_fields_overlays_current_dig_cut_token_on_live_fields() -> None:
    token = _dig_cut_token()

    raw_fields = DigDepthProfileService.resolve_raw_fields(
        DigDepthProfileInputFacts(
            cycle_index=7,
            live_raw_fields={"operator_entry_y_m": -0.1},
            current_dig_cut_tokens=token,
        )
    )

    assert raw_fields["operator_entry_y_m"] == pytest.approx(-0.1)
    assert raw_fields["operator_entry_x_m"] == pytest.approx(
        float(token[CUT_ENTRY_X_IDX]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw_fields["operator_entry_z_m"] == pytest.approx(
        float(token[CUT_ENTRY_Z_IDX]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw_fields["operator_exit_x_m"] == pytest.approx(
        float(token[CUT_EXIT_X_IDX]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw_fields["operator_exit_z_m"] == pytest.approx(
        float(token[CUT_EXIT_Z_IDX]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw_fields["operator_cut_direction_x"] == pytest.approx(
        float(token[CUT_DIR_X_IDX])
    )
    assert raw_fields["operator_cut_direction_z"] == pytest.approx(
        float(token[CUT_DIR_Z_IDX])
    )
    assert raw_fields["operator_cut_length_m"] == pytest.approx(
        float(token[CUT_LENGTH_IDX]) * DIG_CUT_LENGTH_SCALE_M
    )
    assert raw_fields["operator_cut_depth_peak_m"] == pytest.approx(
        float(token[CUT_DEPTH_SEMANTIC_IDX]) * DIG_CUT_DEPTH_SCALE_M
    )
    assert raw_fields["operator_cut_payload_gain_kg"] == pytest.approx(
        float(token[CUT_PAYLOAD_IDX]) * DIG_CUT_PAYLOAD_SCALE_KG
    )
    assert raw_fields["operator_cut_valid"] == 1


def test_resolve_cell_id_prefers_pending_active_env_then_zero() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 5.0

    assert (
        DigDepthProfileService.resolve_cell_id(
            DigDepthProfileInputFacts(
                cycle_index=7,
                pending_cycle_id=7,
                pending_corridor_id=11,
                pending_corridor_cell_id=4,
                active_corridor_cell_id=2,
                env_state=env_state,
            )
        )
        == 4
    )
    assert (
        DigDepthProfileService.resolve_cell_id(
            DigDepthProfileInputFacts(
                cycle_index=7,
                pending_cycle_id=6,
                pending_corridor_id=11,
                pending_corridor_cell_id=4,
                active_corridor_cell_id=2,
                env_state=env_state,
            )
        )
        == 2
    )
    assert (
        DigDepthProfileService.resolve_cell_id(
            DigDepthProfileInputFacts(cycle_index=7, env_state=env_state)
        )
        == 5
    )
    assert DigDepthProfileService.resolve_cell_id(DigDepthProfileInputFacts(7)) == 0


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


def _dig_cut_token() -> np.ndarray:
    token = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    token[CUT_ENTRY_X_IDX] = 0.1
    token[CUT_ENTRY_Z_IDX] = 0.2
    token[CUT_EXIT_X_IDX] = 0.7
    token[CUT_EXIT_Z_IDX] = 0.8
    token[CUT_DIR_X_IDX] = 0.6
    token[CUT_DIR_Z_IDX] = 0.4
    token[CUT_LENGTH_IDX] = 0.5
    token[CUT_DEPTH_SEMANTIC_IDX] = 0.3
    token[CUT_PAYLOAD_IDX] = 0.9
    token[CUT_VALID_IDX] = 1.0
    return token
