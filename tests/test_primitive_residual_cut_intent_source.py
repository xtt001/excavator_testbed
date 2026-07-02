from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
    ResidualCutIntentPlanSourceError,
    build_residual_cut_intent_plan_provider_from_source_path,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _raw_fields(entry_x_m: float) -> dict[str, float | int]:
    return {
        "operator_entry_x_m": entry_x_m,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": -0.2,
        "operator_exit_x_m": entry_x_m,
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


def _adapter_output(candidate_id: str, entry_x_m: float) -> dict[str, object]:
    return {
        "schema": "residual_cut_intent_dig_cut_token_v1",
        "source": "explicit_residual_cut_intent_dig_cut_token",
        "status": "present",
        "offline_only": True,
        "candidate_id": candidate_id,
        "raw_fields": _raw_fields(entry_x_m),
        "dig_cut_tokens": [entry_x_m] * DIG_CUT_TOKEN_DIM,
        "validation_errors": [],
    }


def _write_source(path: Path, *, plans: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
                "source": "explicit_residual_cut_intent_runtime_source",
                "status": "present",
                "offline_only": True,
                "plans": plans,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_source_provider_loads_explicit_adapter_output_by_cycle(tmp_path: Path) -> None:
    source_path = _write_source(
        tmp_path / "residual_cut_intent_source.json",
        plans=[
            {
                "cycle_index": 0,
                "plan": _adapter_output("cut_candidate_000000", 0.25),
            },
            {
                "cycle_index": 2,
                "plan": _adapter_output("cut_candidate_000002", 0.75),
                "fallback_reason": "explicit_unit_test_reason",
            },
        ],
    )

    provider = build_residual_cut_intent_plan_provider_from_source_path(
        source_path,
        cycle_index=lambda: 2,
    )
    assert provider is not None

    token, raw_fields, source, fallback_reason = provider({"id": "obs"})

    np.testing.assert_allclose(token, [0.75] * DIG_CUT_TOKEN_DIM)
    assert raw_fields["operator_entry_x_m"] == 0.75
    assert source == "explicit_residual_cut_intent_dig_cut_token"
    assert fallback_reason == "explicit_unit_test_reason"


def test_source_provider_missing_cycle_fails_deterministically(tmp_path: Path) -> None:
    source_path = _write_source(
        tmp_path / "residual_cut_intent_source.json",
        plans=[
            {
                "cycle_index": 0,
                "plan": _adapter_output("cut_candidate_000000", 0.25),
            },
        ],
    )
    provider = build_residual_cut_intent_plan_provider_from_source_path(
        source_path,
        cycle_index=lambda: 3,
    )
    assert provider is not None

    with pytest.raises(
        ResidualCutIntentPlanSourceError,
        match="missing plan for cycle_index 3",
    ):
        provider({"id": "obs"})


def test_source_provider_surfaces_invalid_and_missing_source_facts(tmp_path: Path) -> None:
    with pytest.raises(
        ResidualCutIntentPlanSourceError,
        match="source path does not exist",
    ):
        build_residual_cut_intent_plan_provider_from_source_path(
            tmp_path / "missing.json",
            cycle_index=lambda: 0,
        )

    invalid_path = _write_source(
        tmp_path / "invalid_source.json",
        plans=[
            {
                "cycle_index": 0,
                "plan": {
                    "schema": "residual_cut_intent_dig_cut_token_v1",
                    "source": "explicit_residual_cut_intent_dig_cut_token",
                    "status": "invalid",
                    "raw_fields": {},
                    "dig_cut_tokens": [],
                },
            },
        ],
    )

    with pytest.raises(
        ResidualCutIntentPlanSourceError,
        match="plans\\[0\\] plan status must be present",
    ):
        build_residual_cut_intent_plan_provider_from_source_path(
            invalid_path,
            cycle_index=lambda: 0,
        )


def test_no_provider_is_created_without_explicit_source_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    hidden_runs_source = tmp_path / "runs/eval/current/results/source.json"
    hidden_runs_source.parent.mkdir(parents=True)
    _write_source(
        hidden_runs_source,
        plans=[
            {
                "cycle_index": 0,
                "plan": _adapter_output("cut_candidate_000000", 0.25),
            },
        ],
    )

    assert (
        build_residual_cut_intent_plan_provider_from_source_path(
            "",
            cycle_index=lambda: 0,
        )
        is None
    )


def test_primitive_planner_exposes_residual_source_provider_as_thin_port(
    tmp_path: Path,
) -> None:
    source_path = _write_source(
        tmp_path / "residual_cut_intent_source.json",
        plans=[
            {
                "cycle_index": 0,
                "plan": _adapter_output("cut_candidate_000000", 0.5),
            },
        ],
    )

    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.residual_cut_intent_source_path = str(source_path)

    provider = policy._residual_cut_intent_plan_provider()

    assert provider is not None
    _token, raw_fields, _source, _fallback_reason = provider({"id": "obs"})
    assert raw_fields["operator_entry_x_m"] == 0.5

    policy.residual_cut_intent_source_path = ""
    assert policy._residual_cut_intent_plan_provider() is None


def test_primitive_planner_exposes_next_cycle_residual_return_target_provider(
    tmp_path: Path,
) -> None:
    source_path = _write_source(
        tmp_path / "residual_cut_intent_source.json",
        plans=[
            {
                "cycle_index": 0,
                "plan": _adapter_output("cut_candidate_000000", 0.5),
            },
            {
                "cycle_index": 1,
                "plan": _adapter_output("cut_candidate_000001", 0.75),
            },
        ],
    )

    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.residual_cut_intent_source_path = str(source_path)
    policy._primitive_cycle_runtime_state().cycle_index = 0

    provider = policy._residual_cut_intent_return_target_plan_provider()

    assert provider is not None
    _token, raw_fields, _source, _fallback_reason = provider({"id": "obs"})
    assert raw_fields["operator_entry_x_m"] == 0.75

    policy.residual_cut_intent_source_path = ""
    assert policy._residual_cut_intent_return_target_plan_provider() is None
