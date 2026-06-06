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
    DIG_DEPTH_PROFILE_CONFIG_FIELDS,
    DIG_DEPTH_PROFILE_RUNTIME_STATUS_STATE_FIELDS,
    DigDepthProfileBuildRequest,
    DigDepthProfileConfig,
    DigDepthProfileInputFacts,
    DigDepthProfileInputSourceCallbacks,
    DigDepthProfileInputSourceFacts,
    DigDepthProfileInputSourcePlan,
    DigDepthProfileMissingPriorError,
    DigDepthProfileObservationTokenResult,
    DigDepthProfileRuntimeState,
    DigDepthProfileRuntimeStatusState,
    DigDepthProfileService,
    DigDepthProfileState,
    DigDepthProfileTokenResult,
    build_dig_depth_profile_config_from_mapping,
    build_dig_depth_profile_input_facts,
    build_dig_depth_profile_runtime_status_state_from_mapping,
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


def test_build_token_from_input_facts_resolves_cell_and_raw_fields() -> None:
    service = DigDepthProfileService()
    env_state = np.zeros(64, dtype=np.float32)
    raw_fields = _raw_fields()

    actual = service.build_token_from_input_facts(
        DigDepthProfileInputFacts(
            cycle_index=7,
            pending_cycle_id=7,
            pending_corridor_id=11,
            pending_corridor_cell_id=2,
            pending_raw_fields=raw_fields,
            active_corridor_cell_id=5,
            active_corridor_raw_fields={"operator_entry_x_m": 99.0},
            env_state=env_state,
        ),
        config=DigDepthProfileConfig(source="live_plan"),
    )
    expected = service.build_token(
        DigDepthProfileBuildRequest(
            cell_id=2,
            raw_fields=raw_fields,
            env_state=env_state,
            config=DigDepthProfileConfig(source="live_plan"),
        )
    )

    assert actual.source == expected.source
    assert actual.fallback_reason == expected.fallback_reason
    np.testing.assert_allclose(actual.token, expected.token)


def test_token_result_projects_state_metadata() -> None:
    token = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    result = DigDepthProfileService.token_result(
        DigDepthProfileState(
            token=token,
            source="qc6_dig_depth_profile_cell_3",
            fallback_reason="",
        )
    )

    assert isinstance(result, DigDepthProfileTokenResult)
    assert result.token is token
    assert result.token.dtype == np.float32
    assert result.source == "qc6_dig_depth_profile_cell_3"
    assert result.fallback_reason == ""


def test_token_result_casts_token_to_float32() -> None:
    result = DigDepthProfileService.token_result(
        DigDepthProfileState(
            token=np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64),
            source="fallback_live_plan",
            fallback_reason="missing dig_depth_profile_cells entry for cell 5",
        )
    )

    assert result.token.dtype == np.float32
    np.testing.assert_allclose(
        result.token,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )
    assert result.source == "fallback_live_plan"
    assert (
        result.fallback_reason == "missing dig_depth_profile_cells entry for cell 5"
    )


def test_observation_token_result_copies_without_casting_dtype() -> None:
    tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)

    result = DigDepthProfileService.observation_token_result(tokens)
    tokens[0] = 99.0

    assert isinstance(result, DigDepthProfileObservationTokenResult)
    assert result.token.dtype == np.float64
    np.testing.assert_allclose(
        result.token,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64),
    )


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = DigDepthProfileService.initial_runtime_state()
    other_state = DigDepthProfileService.initial_runtime_state()

    assert isinstance(state, DigDepthProfileRuntimeState)
    assert state.tokens.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert state.tokens.dtype == np.float32
    assert float(np.max(np.abs(state.tokens))) == pytest.approx(0.0)
    assert state.token_injected is False
    assert state.token_source == "none"
    assert state.fallback_reason == ""

    state.tokens[0] = 99.0
    assert other_state.tokens[0] == pytest.approx(0.0)


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


def test_input_facts_preserves_current_pending_sources() -> None:
    pending_raw = {"operator_entry_x_m": 1.5}
    active_raw = {"operator_entry_x_m": 2.5}
    live_raw = {"operator_entry_x_m": 3.5}
    token = _dig_cut_token()
    env_state = np.zeros(64, dtype=np.float32)

    facts = build_dig_depth_profile_input_facts(
        DigDepthProfileInputSourceFacts(
            cycle_index=7,
            pending_cycle_id=7,
            pending_corridor_id=11,
            pending_raw_fields=pending_raw,
            pending_corridor_cell_id=4,
            active_corridor_raw_fields=active_raw,
            active_corridor_cell_id=2,
            live_raw_fields=live_raw,
            current_dig_cut_tokens=token,
            env_state=env_state,
        )
    )

    assert facts.pending_raw_fields is pending_raw
    assert facts.pending_corridor_cell_id == 4
    assert facts.active_corridor_raw_fields is None
    assert facts.active_corridor_cell_id is None
    assert facts.live_raw_fields is None
    assert facts.current_dig_cut_tokens is token
    assert facts.env_state is None


def test_input_source_plan_preserves_current_pending_sources() -> None:
    pending_raw = {"operator_entry_x_m": 1.5}

    initial_plan = DigDepthProfileService.input_source_plan(
        cycle_index=7,
        pending_cycle_id=7,
        pending_corridor_id=11,
        pending_raw_fields=pending_raw,
    )

    assert isinstance(initial_plan, DigDepthProfileInputSourcePlan)
    assert initial_plan.pending_raw_fields is pending_raw
    assert initial_plan.sample_pending_corridor is True
    assert initial_plan.sample_active_corridor is True
    assert initial_plan.sample_active_raw_fields is False
    assert initial_plan.sample_live_raw_fields is False
    assert initial_plan.sample_env_state is False

    final_plan = DigDepthProfileService.input_source_plan(
        cycle_index=7,
        pending_cycle_id=7,
        pending_corridor_id=11,
        pending_raw_fields=pending_raw,
        pending_corridor_cell_id=4,
        pending_corridor_sampled=True,
        active_corridor_sampled=True,
    )

    assert final_plan.pending_raw_fields is pending_raw
    assert final_plan.pending_corridor_cell_id == 4
    assert final_plan.sample_pending_corridor is False
    assert final_plan.sample_active_corridor is False
    assert final_plan.sample_active_raw_fields is False
    assert final_plan.sample_active_corridor_cell_id is False
    assert final_plan.sample_live_raw_fields is False
    assert final_plan.sample_env_state is False


def test_input_facts_from_source_callbacks_preserves_order_and_identity() -> None:
    pending_raw = {"operator_entry_x_m": 1.5}
    token = _dig_cut_token()
    active_corridor = {"cell_id": 4}
    calls: list[str] = []

    def pending_corridor_cell_id(corridor_id: int) -> int | None:
        calls.append(f"pending:{corridor_id}")
        return None

    def active_corridor_callback() -> dict[str, int]:
        calls.append("active")
        return active_corridor

    def fail_active_raw_fields(_corridor: object) -> dict[str, float | int]:
        raise AssertionError("pending raw fields should suppress active raw fields")

    def fail_live_raw_fields() -> dict[str, float | int]:
        raise AssertionError("pending raw fields should suppress live raw fields")

    def fail_env_state() -> np.ndarray:
        raise AssertionError("active cell fallback should suppress env_state")

    facts = DigDepthProfileService.input_facts_from_source_callbacks(
        cycle_index=8,
        pending_cycle_id=8,
        pending_corridor_id=99,
        pending_raw_fields=pending_raw,
        current_dig_cut_tokens=token,
        callbacks=DigDepthProfileInputSourceCallbacks(
            pending_corridor_cell_id=pending_corridor_cell_id,
            active_corridor=active_corridor_callback,
            active_corridor_raw_fields=fail_active_raw_fields,
            active_corridor_cell_id=lambda corridor: int(corridor["cell_id"]),
            live_raw_fields=fail_live_raw_fields,
            env_state=fail_env_state,
        ),
    )

    assert calls == ["pending:99", "active"]
    assert facts.pending_raw_fields is pending_raw
    assert facts.pending_corridor_cell_id is None
    assert facts.active_corridor_raw_fields is None
    assert facts.active_corridor_cell_id == 4
    assert facts.live_raw_fields is None
    assert facts.current_dig_cut_tokens is token
    assert facts.env_state is None


def test_input_facts_ignores_stale_pending_and_uses_active_sources() -> None:
    pending_raw = {"operator_entry_x_m": 1.5}
    active_raw = {"operator_entry_x_m": 2.5}
    live_raw = {"operator_entry_x_m": 3.5}
    env_state = np.zeros(64, dtype=np.float32)

    facts = DigDepthProfileService.input_facts(
        DigDepthProfileInputSourceFacts(
            cycle_index=7,
            pending_cycle_id=6,
            pending_corridor_id=11,
            pending_raw_fields=pending_raw,
            pending_corridor_cell_id=4,
            active_corridor_raw_fields=active_raw,
            active_corridor_cell_id=2,
            live_raw_fields=live_raw,
            env_state=env_state,
        )
    )

    assert facts.pending_raw_fields is None
    assert facts.pending_corridor_cell_id is None
    assert facts.active_corridor_raw_fields is active_raw
    assert facts.active_corridor_cell_id == 2
    assert facts.live_raw_fields is None
    assert facts.env_state is None


def test_input_source_plan_ignores_stale_pending_and_waits_for_active() -> None:
    pending_raw = {"operator_entry_x_m": 1.5}
    active_raw = {"operator_entry_x_m": 2.5}

    initial_plan = DigDepthProfileService.input_source_plan(
        cycle_index=7,
        pending_cycle_id=6,
        pending_corridor_id=11,
        pending_raw_fields=pending_raw,
    )

    assert initial_plan.pending_raw_fields is None
    assert initial_plan.sample_pending_corridor is False
    assert initial_plan.sample_active_corridor is True
    assert initial_plan.sample_live_raw_fields is False
    assert initial_plan.sample_env_state is False

    final_plan = DigDepthProfileService.input_source_plan(
        cycle_index=7,
        pending_cycle_id=6,
        pending_corridor_id=11,
        pending_raw_fields=pending_raw,
        active_corridor_raw_fields=active_raw,
        active_corridor_cell_id=2,
        pending_corridor_sampled=True,
        active_corridor_sampled=True,
    )

    assert final_plan.pending_raw_fields is None
    assert final_plan.active_corridor_raw_fields is active_raw
    assert final_plan.active_corridor_cell_id == 2
    assert final_plan.sample_active_corridor is False
    assert final_plan.sample_live_raw_fields is False
    assert final_plan.sample_env_state is False


def test_input_facts_uses_live_raw_and_env_without_corridor_cell() -> None:
    live_raw = {"operator_entry_x_m": 3.5}
    env_state = np.zeros(64, dtype=np.float32)

    facts = DigDepthProfileService.input_facts(
        DigDepthProfileInputSourceFacts(
            cycle_index=7,
            live_raw_fields=live_raw,
            env_state=env_state,
        )
    )

    assert facts.live_raw_fields is live_raw
    assert facts.env_state is env_state


def test_input_source_plan_uses_live_and_env_after_active_miss() -> None:
    plan = DigDepthProfileService.input_source_plan(
        cycle_index=7,
        pending_corridor_sampled=True,
        active_corridor_sampled=True,
    )

    assert plan.sample_pending_corridor is False
    assert plan.sample_active_corridor is False
    assert plan.sample_active_raw_fields is False
    assert plan.sample_active_corridor_cell_id is False
    assert plan.sample_live_raw_fields is True
    assert plan.sample_env_state is True


def test_input_facts_include_env_state_overrides_available_cell() -> None:
    env_state = np.zeros(64, dtype=np.float32)

    facts = DigDepthProfileService.input_facts(
        DigDepthProfileInputSourceFacts(
            cycle_index=7,
            active_corridor_cell_id=2,
            env_state=env_state,
            include_env_state=True,
        )
    )

    assert facts.active_corridor_cell_id == 2
    assert facts.env_state is env_state


def test_input_source_plan_include_env_state_overrides_available_cell() -> None:
    plan = DigDepthProfileService.input_source_plan(
        cycle_index=7,
        active_corridor_cell_id=2,
        active_corridor_sampled=True,
        include_env_state=True,
    )

    assert plan.active_corridor_cell_id == 2
    assert plan.sample_env_state is True


def test_runtime_status_snapshot_projects_config_and_runtime_state() -> None:
    tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)
    snapshot = DigDepthProfileService.runtime_status_snapshot(
        config=DigDepthProfileConfig(source="prior_profile", required=True),
        state=DigDepthProfileRuntimeStatusState(
            token_injected=True,
            token_source="qc6_dig_depth_profile_cell_3",
            fallback_reason="",
            tokens=tokens,
        ),
    )
    tokens[0] = 99.0

    assert snapshot.source == "prior_profile"
    assert snapshot.required is True
    assert snapshot.token_injected is True
    assert snapshot.token_source == "qc6_dig_depth_profile_cell_3"
    assert snapshot.fallback_reason == ""
    assert snapshot.tokens.dtype == np.float32
    np.testing.assert_allclose(
        snapshot.tokens,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )


def test_config_mapping_preserves_legacy_projection() -> None:
    values = {
        "source": 123,
        "required": 1,
        "allow_live_fallback": 0,
        "allow_global_fallback": 1,
        "ignored": object(),
    }

    config = build_dig_depth_profile_config_from_mapping(values)

    assert {key for key, _ in DIG_DEPTH_PROFILE_CONFIG_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert config == DigDepthProfileConfig(
        source="123",
        required=True,
        allow_live_fallback=False,
        allow_global_fallback=True,
    )


def test_runtime_status_state_mapping_preserves_legacy_projection() -> None:
    tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)
    values = {
        "token_injected": 1,
        "token_source": 123,
        "fallback_reason": 456,
        "tokens": tokens,
        "ignored": object(),
    }

    state = build_dig_depth_profile_runtime_status_state_from_mapping(values)

    assert {key for key, _ in DIG_DEPTH_PROFILE_RUNTIME_STATUS_STATE_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state.token_injected is True
    assert state.token_source == "123"
    assert state.fallback_reason == "456"
    assert state.tokens is tokens


def test_runtime_status_snapshot_from_mappings_matches_explicit_snapshot() -> None:
    tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float64)
    config_values = {
        "source": 123,
        "required": 1,
        "allow_live_fallback": 0,
        "allow_global_fallback": 1,
    }
    state_values = {
        "token_injected": 1,
        "token_source": 123,
        "fallback_reason": 456,
        "tokens": tokens,
    }

    actual = DigDepthProfileService.runtime_status_snapshot_from_mappings(
        config_values=config_values,
        state_values=state_values,
    )
    expected = DigDepthProfileService.runtime_status_snapshot(
        config=build_dig_depth_profile_config_from_mapping(config_values),
        state=build_dig_depth_profile_runtime_status_state_from_mapping(
            state_values
        ),
    )

    assert actual.source == expected.source
    assert actual.required == expected.required
    assert actual.token_injected == expected.token_injected
    assert actual.token_source == expected.token_source
    assert actual.fallback_reason == expected.fallback_reason
    np.testing.assert_array_equal(actual.tokens, expected.tokens)
    assert actual.tokens is not tokens


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
