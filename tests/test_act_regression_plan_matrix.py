from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from testbed.cli import build_act_regression_plan_matrix as cli
from testbed.eval.act_regression_plan_matrix import (
    ACT_REGRESSION_PLAN_MATRIX_SCHEMA,
    ActRegressionPlanMatrixError,
    assert_allowed_condition_diff,
    build_act_regression_plan_matrix,
)
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
    load_explicit_residual_cut_intent_plan_source,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner


def _prior() -> dict[str, object]:
    return {
        "prior_id": "strict18-test-prior",
        "fields": {
            "entry_x_m": {"p10": 0.383834, "p50": 0.731882, "p90": 1.009634},
            "entry_z_m": {"p10": -1.169713, "p50": -0.387444, "p90": 0.701805},
            "exit_x_m": {"p10": -0.277553, "p50": 0.554963, "p90": 1.031759},
            "exit_z_m": {"p10": -1.052679, "p50": -0.341561, "p90": 0.725329},
            "cut_direction_x": {"p10": -0.894669, "p50": -0.3383, "p90": 0.460661},
            "cut_direction_z": {"p10": -0.465885, "p50": 0.053986, "p90": 0.575655},
            "cut_length_m": {"p10": 0.525479, "p50": 0.721231, "p90": 1.183649},
            "cut_depth_peak_m": {"p10": 0.24369, "p50": 0.458796, "p90": 0.600003},
            "payload_gain_kg": {"p10": 61.345787, "p50": 75.018345, "p90": 98.589323},
            "effective_deposit_delta_kg": {
                "p10": 14.643884,
                "p50": 52.529617,
                "p90": 86.885482,
            },
        },
        "coverage_cells": [
            {
                "cell_id": 0,
                "entry": {"x_m": 0.552648, "z_m": -1.029915},
                "exit": {"x_m": 0.308558, "z_m": -1.014107},
                "cut_depth_peak_m": 0.419068,
                "payload_gain_kg": 83.479198,
                "effective_deposit_delta_kg": 47.556427,
            },
            {
                "cell_id": 2,
                "entry": {"x_m": 0.615094, "z_m": -0.439306},
                "exit": {"x_m": 0.516926, "z_m": -0.276453},
                "cut_depth_peak_m": 0.405455,
                "payload_gain_kg": 73.342262,
                "effective_deposit_delta_kg": 42.470093,
            },
            {
                "cell_id": 4,
                "entry": {"x_m": 0.635571, "z_m": 0.549191},
                "exit": {"x_m": 0.41758, "z_m": 0.717073},
                "cut_depth_peak_m": 0.364648,
                "payload_gain_kg": 75.810196,
                "effective_deposit_delta_kg": 37.394043,
            },
        ],
    }


def _baseline_raw_fields(cell_id: int) -> dict[str, float | int]:
    if cell_id == 4:
        return {
            "operator_entry_x_m": 0.635571,
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": 0.549191,
            "operator_exit_x_m": 0.41758,
            "operator_exit_y_m": 0.0,
            "operator_exit_z_m": 0.717073,
            "operator_cut_direction_x": -0.7922785211657819,
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": 0.575655,
            "operator_cut_length_m": 0.525479,
            "operator_cut_depth_peak_m": 0.364648,
            "operator_cut_payload_gain_kg": 75.810196,
            "operator_effective_deposit_delta_kg": 37.394043,
            "operator_cut_valid": 1,
        }
    if cell_id == 0:
        return {
            "operator_entry_x_m": 0.552648,
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": -1.029915,
            "operator_exit_x_m": 0.308558,
            "operator_exit_y_m": 0.0,
            "operator_exit_z_m": -1.014107,
            "operator_cut_direction_x": -0.894669,
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": 0.06462760703640359,
            "operator_cut_length_m": 0.525479,
            "operator_cut_depth_peak_m": 0.419068,
            "operator_cut_payload_gain_kg": 83.479198,
            "operator_effective_deposit_delta_kg": 47.556427,
            "operator_cut_valid": 1,
        }
    raise AssertionError(cell_id)


def _token(raw_fields: dict[str, float | int]) -> list[float]:
    plan = DigCutTokenPlanner(prior={}).plan_from_raw_fields(
        raw_fields,
        source="test",
    )
    return [float(value) for value in plan.token.tolist()]


def _write_a0_artifact(tmp_path: Path) -> tuple[Path, Path]:
    prior_path = tmp_path / "strict18_prior.json"
    prior_path.write_text(json.dumps(_prior()), encoding="utf-8")
    results = tmp_path / "a0" / "results"
    rollouts = results / "rollouts"
    rollouts.mkdir(parents=True)
    rollout_path = rollouts / "rollout_000.jsonl"
    rows = [
        {
            "t": 10,
            "primitive_cycle_index": 0,
            "skill_name": "dig",
            "dig_cut_token_injected": True,
            "coverage_corridor_id": 4,
            "dig_cut_tokens": _token(_baseline_raw_fields(4)),
        },
        {
            "t": 11,
            "primitive_cycle_index": 0,
            "skill_name": "dig",
            "dig_cut_token_injected": True,
            "coverage_corridor_id": 4,
            "dig_cut_tokens": _token(_baseline_raw_fields(4)),
        },
        {
            "t": 20,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "dig_cut_token_injected": True,
            "coverage_corridor_id": 0,
            "dig_cut_tokens": _token(_baseline_raw_fields(0)),
        },
    ]
    rollout_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    (rollouts / "rollout_000_planner_trace.json").write_text(
        json.dumps({"dig_cut_prior_path": str(prior_path)}),
        encoding="utf-8",
    )
    return results.parent, prior_path


def _load_condition(manifest: dict[str, object], condition: str) -> dict[str, object]:
    condition_record = manifest["conditions"][condition]  # type: ignore[index]
    path = Path(condition_record["runtime_source_path"])  # type: ignore[index]
    return json.loads(path.read_text(encoding="utf-8"))


def test_builds_exact_four_condition_cycle01_matrix_and_guards_diffs(
    tmp_path: Path,
) -> None:
    artifact, prior_path = _write_a0_artifact(tmp_path)
    output_dir = tmp_path / "matrix"

    manifest = build_act_regression_plan_matrix(
        a0_rollout_artifact_path=artifact,
        planner_prior_path=prior_path,
        output_dir=output_dir,
    )

    assert manifest["schema"] == ACT_REGRESSION_PLAN_MATRIX_SCHEMA
    assert manifest["status"] == "present"
    assert list(manifest["conditions"]) == ["F0", "D1", "C1", "DC1"]
    assert manifest["locked_cycle_indices"] == [0, 1]
    assert manifest["diagnostic_only"] is True
    assert manifest["promotion_eligible"] is False

    payloads = {
        condition: _load_condition(manifest, condition)
        for condition in ("F0", "D1", "C1", "DC1")
    }
    for condition, payload in payloads.items():
        assert payload["schema"] == RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA
        path = manifest["conditions"][condition]["runtime_source_path"]
        loaded = load_explicit_residual_cut_intent_plan_source(path)
        assert sorted(loaded.plans_by_cycle) == [0, 1]

    f0 = payloads["F0"]
    f0_cycle0 = f0["plans"][0]["plan"]
    f0_cycle1 = f0["plans"][1]["plan"]
    assert f0_cycle0["dig_cut_tokens"] == _token(_baseline_raw_fields(4))
    assert f0_cycle1["dig_cut_tokens"] == _token(_baseline_raw_fields(0))

    d1_cycle1 = payloads["D1"]["plans"][1]["plan"]
    assert d1_cycle1["raw_fields"]["operator_cut_depth_peak_m"] == pytest.approx(
        0.24369
    )
    assert d1_cycle1["dig_cut_tokens"][7] == pytest.approx(0.24369 / 0.80)

    c1_cycle1 = payloads["C1"]["plans"][1]["plan"]
    assert c1_cycle1["raw_fields"]["operator_entry_x_m"] == pytest.approx(0.615094)
    assert c1_cycle1["raw_fields"]["operator_entry_z_m"] == pytest.approx(-0.439306)
    assert c1_cycle1["raw_fields"]["operator_exit_x_m"] == pytest.approx(0.516926)
    assert c1_cycle1["raw_fields"]["operator_exit_z_m"] == pytest.approx(-0.276453)
    assert c1_cycle1["raw_fields"]["operator_cut_depth_peak_m"] == pytest.approx(
        0.419068
    )
    assert c1_cycle1["raw_fields"]["operator_cut_payload_gain_kg"] == pytest.approx(
        83.479198
    )
    assert c1_cycle1["raw_fields"][
        "operator_effective_deposit_delta_kg"
    ] == pytest.approx(47.556427)
    assert c1_cycle1["raw_fields"]["operator_cut_length_m"] == pytest.approx(0.525479)

    dc1_cycle1 = payloads["DC1"]["plans"][1]["plan"]
    assert dc1_cycle1["raw_fields"]["operator_entry_x_m"] == pytest.approx(
        c1_cycle1["raw_fields"]["operator_entry_x_m"]
    )
    assert dc1_cycle1["raw_fields"]["operator_cut_depth_peak_m"] == pytest.approx(
        d1_cycle1["raw_fields"]["operator_cut_depth_peak_m"]
    )

    assert manifest["conditions"]["F0"]["allowed_diff_guard"]["changed_paths"] == []
    assert manifest["conditions"]["D1"]["allowed_diff_guard"]["changed_paths"] == [
        "plans[1].plan.dig_cut_tokens[7]",
        "plans[1].plan.raw_fields.operator_cut_depth_peak_m",
    ]
    assert manifest["conditions"]["C1"]["allowed_diff_guard"]["changed_paths"] == [
        "plans[1].plan.dig_cut_tokens[0]",
        "plans[1].plan.dig_cut_tokens[1]",
        "plans[1].plan.dig_cut_tokens[2]",
        "plans[1].plan.dig_cut_tokens[3]",
        "plans[1].plan.dig_cut_tokens[4]",
        "plans[1].plan.dig_cut_tokens[5]",
        "plans[1].plan.raw_fields.operator_cut_direction_x",
        "plans[1].plan.raw_fields.operator_cut_direction_z",
        "plans[1].plan.raw_fields.operator_entry_x_m",
        "plans[1].plan.raw_fields.operator_entry_z_m",
        "plans[1].plan.raw_fields.operator_exit_x_m",
        "plans[1].plan.raw_fields.operator_exit_z_m",
    ]


def test_allowed_diff_guard_rejects_an_extra_payload_change(
    tmp_path: Path,
) -> None:
    artifact, prior_path = _write_a0_artifact(tmp_path)
    manifest = build_act_regression_plan_matrix(
        a0_rollout_artifact_path=artifact,
        planner_prior_path=prior_path,
        output_dir=tmp_path / "matrix",
    )
    f0 = _load_condition(manifest, "F0")
    d1 = _load_condition(manifest, "D1")
    broken = copy.deepcopy(d1)
    broken["plans"][1]["plan"]["raw_fields"]["operator_cut_payload_gain_kg"] += 1.0

    with pytest.raises(
        ActRegressionPlanMatrixError,
        match="allowed_field_diff_guard_failed.*operator_cut_payload_gain_kg",
    ):
        assert_allowed_condition_diff(
            baseline_source=f0,
            candidate_source=broken,
            condition="D1",
        )


def test_builder_auto_discovers_prior_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    artifact, _prior_path = _write_a0_artifact(tmp_path)
    output_dir = tmp_path / "matrix"

    build_act_regression_plan_matrix(
        a0_rollout_artifact_path=artifact,
        output_dir=output_dir,
    )

    with pytest.raises(FileExistsError, match="already exists"):
        build_act_regression_plan_matrix(
            a0_rollout_artifact_path=artifact,
            output_dir=output_dir,
        )


def test_cli_is_a_thin_builder_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "a0"
    output = tmp_path / "matrix"
    calls: list[dict[str, object]] = []

    def fake_build(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "schema": ACT_REGRESSION_PLAN_MATRIX_SCHEMA,
            "status": "present",
            "manifest_path": str((output / "manifest.json").resolve()),
            "conditions": {"F0": {}, "D1": {}, "C1": {}, "DC1": {}},
        }

    monkeypatch.setattr(cli, "build_act_regression_plan_matrix", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-build-act-regression-plan-matrix",
            "--a0-rollout-artifact",
            str(artifact),
            "--output-dir",
            str(output),
        ],
    )

    cli.main()

    assert calls == [
        {
            "a0_rollout_artifact_path": artifact,
            "planner_prior_path": None,
            "output_dir": output,
        }
    ]
    assert json.loads(capsys.readouterr().out) == {
        "condition_count": 4,
        "manifest_path": str((output / "manifest.json").resolve()),
        "schema": ACT_REGRESSION_PLAN_MATRIX_SCHEMA,
        "status": "present",
    }
