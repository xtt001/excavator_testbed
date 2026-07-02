from __future__ import annotations

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.token.residual_cut_intent import (
    build_residual_cut_intent_dig_cut_token,
)


def _cut_intent(**overrides) -> dict[str, object]:
    intent = {
        "cut_intent_candidate_id": "cut_candidate_000009",
        "candidate_id": "cut_candidate_000009",
        "offline_only": True,
        "anchor_cell_index": 4,
        "anchor_row": 2,
        "anchor_col": 0,
        "direction": "col_forward",
        "candidate_depth_m": 0.16,
        "runner_input_status": "ready_for_eval_harness",
        "production_runtime_action": False,
    }
    intent.update(overrides)
    return intent


def test_adapter_builds_existing_dig_cut_raw_fields_and_tokens_from_explicit_cut_intent() -> None:
    result = build_residual_cut_intent_dig_cut_token(
        _cut_intent(),
        cell_centers_m={4: {"x_m": 0.4, "z_m": -0.2}},
        direction_vectors={"col_forward": [0.0, 2.0]},
        bucket_length_m=1.2,
        payload_kg=36.0,
    )

    assert result["schema"] == "residual_cut_intent_dig_cut_token_v1"
    assert result["source"] == "explicit_residual_cut_intent_dig_cut_token"
    assert result["status"] == "present"
    assert result["offline_only"] is True
    assert result["profile"] == "explicit_residual_cut_intent_dig_cut_token"
    assert result["candidate_id"] == "cut_candidate_000009"
    assert result["validation_errors"] == []

    assert result["raw_fields"] == {
        "operator_entry_x_m": 0.4,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": -0.2,
        "operator_exit_x_m": 0.4,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": 1.0,
        "operator_cut_direction_x": 0.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 1.0,
        "operator_cut_length_m": 1.2,
        "operator_cut_depth_peak_m": 0.16,
        "operator_cut_payload_gain_kg": 36.0,
        "operator_effective_deposit_delta_kg": 36.0,
        "operator_cut_valid": 1,
    }
    assert len(result["dig_cut_tokens"]) == DIG_CUT_TOKEN_DIM
    np.testing.assert_allclose(
        result["dig_cut_tokens"],
        [0.2, -0.1, 0.2, 0.5, 0.0, 1.0, 0.6, 0.2, 0.6, 1.0],
    )
    assert result["adapter_conventions"]["entry_y_m"] == "zero_height_offline_adapter_convention"
    assert result["non_goal_statuses"]["simulation_status"] == "not_run_by_adapter"
    assert result["provenance_statuses"]["cell_centers_m_status"] == "explicit_input"


def test_adapter_accepts_string_cell_keys_and_sequence_centers() -> None:
    result = build_residual_cut_intent_dig_cut_token(
        _cut_intent(),
        cell_centers_m={"4": [1.0, 0.5]},
        direction_vectors={"col_forward": [3.0, 4.0]},
        bucket_length_m=2.0,
        payload_kg=0.0,
    )

    assert result["status"] == "present"
    raw_fields = result["raw_fields"]
    assert raw_fields["operator_cut_direction_x"] == 0.6
    assert raw_fields["operator_cut_direction_z"] == 0.8
    assert raw_fields["operator_exit_x_m"] == 2.2
    assert raw_fields["operator_exit_z_m"] == 2.1
    assert raw_fields["operator_cut_payload_gain_kg"] == 0.0
    assert raw_fields["operator_effective_deposit_delta_kg"] == 0.0


def test_adapter_returns_invalid_status_for_missing_explicit_geometry() -> None:
    result = build_residual_cut_intent_dig_cut_token(
        _cut_intent(),
        cell_centers_m={3: [0.0, 0.0]},
        direction_vectors={"col_forward": [0.0, 0.0]},
        bucket_length_m=1.2,
        payload_kg=36.0,
    )

    assert result["status"] == "invalid"
    assert result["candidate_id"] == "cut_candidate_000009"
    assert result["raw_fields"] == {}
    assert result["dig_cut_tokens"] == []
    assert result["validation_errors"] == [
        "cell_centers_m must include anchor_cell_index 4",
        "direction_vectors['col_forward'] must be nonzero",
    ]
