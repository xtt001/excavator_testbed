from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.planner.box_emptying.artifacts import (
    BoxEmptyingArtifactContractError,
    load_box_emptying_artifact_manifest,
)
from testbed.planner.box_emptying.online_provider import (
    BoxEmptyingResidualPlanService,
)


class _RecordPredictor:
    input_contract = "planned_cut"

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def predict(self, record):
        self.records.append(dict(record))
        planned = record["planned_cut"]
        # Make the selected cell observable without coupling this test to a
        # particular tie-breaking candidate direction.
        entry_x = float(planned["entry_x_m"])
        entry_z = float(planned["entry_z_m"])
        score = 0.03 + 0.002 * (entry_x + entry_z)
        return {
            "signed_depth_delta_m": [score] * 6,
            "payload_gain_kg": 40.0,
            "derived_volume": {"removed_volume_m3": score * 6 * 1.25},
            "uncertainty": {"removed_volume_m3_std": 0.001},
        }


def _obs(*, volumes: tuple[float, ...] = (0.5,) * 6) -> dict[str, object]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[17] = 0.0  # DigArea long axis is local X.
    env[28:31] = [0.2, -0.1, 0.3]
    env[33:39] = 0.10
    env[39:45] = 0.0
    env[45:51] = 0.60
    env[51:57] = 1.0
    env[64:67] = [1.0, 2.0, 3.0]
    env[67:70] = [1.0, 0.0, 0.0]
    env[70:73] = [0.0, 0.0, 1.0]
    env[73] = 1.0
    env[74] = 1.25
    env[75] = 1.25
    env[76] = 0.0
    env[77:83] = 0.0
    env[83:89] = 1.0
    env[89] = 0.60
    env[90] = 1600.0
    env[91:97] = volumes
    env[97] = sum(volumes) * 1600.0
    env[98] = 6000.0
    env[99] = env[97] / env[98]
    env[100] = 1.0
    return {
        "step_id": 10,
        "env_state": env,
        "qpos": np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        "qvel": np.asarray([0.01, 0.02, 0.03, 0.04], dtype=np.float32),
    }


def _service(predictor: _RecordPredictor) -> BoxEmptyingResidualPlanService:
    return BoxEmptyingResidualPlanService(
        record_predictor=predictor,
        support_envelope={
            "planned_depth_m": [0.05, 0.60],
            "cut_length_m": [0.75, 0.75],
            "entry_x_m": [-1.1, 1.1],
            "entry_z_m": [-0.7, 0.7],
            "exit_x_m": [-1.8, 1.8],
            "exit_z_m": [-1.45, 1.45],
            "direction_x": [-1.0, 1.0],
            "direction_z": [-1.0, 1.0],
        },
    )


def test_online_provider_builds_leakage_safe_planned_record_and_goal_fields() -> None:
    predictor = _RecordPredictor()
    service = _service(predictor)

    raw_fields, source = service.plan(_obs(), target_cycle_index=0)

    assert source == "planned_box_emptying_residual_v1"
    assert raw_fields["operator_cut_valid"] == 1
    assert raw_fields["operator_cut_length_m"] == pytest.approx(0.75)
    assert 0.05 <= raw_fields["operator_cut_depth_peak_m"] <= 0.60
    assert raw_fields["operator_cut_payload_gain_kg"] == pytest.approx(60.0)
    assert predictor.records
    record = predictor.records[-1]
    assert record["effect_input_schema"] == "terrain_effect_input_v1"
    assert record["execution_context"]["entry_qpos"] == pytest.approx(
        [0.1, 0.2, 0.3, 0.4]
    )
    assert "outcome" not in record
    assert "actual_peak_depth_m" not in record["planned_cut"]


def test_return_lock_is_reused_and_may_recompute_only_once() -> None:
    service = _service(_RecordPredictor())
    first, _ = service.plan(_obs(), target_cycle_index=1)
    same, _ = service.plan(_obs(), target_cycle_index=1)
    assert same == first

    changed = _obs(volumes=(0.504, 0.5, 0.5, 0.5, 0.5, 0.5))
    service.plan(changed, target_cycle_index=1)
    changed_again = _obs(volumes=(0.508, 0.5, 0.5, 0.5, 0.5, 0.5))
    with pytest.raises(RuntimeError, match="locked_plan_changed_more_than_once"):
        service.plan(changed_again, target_cycle_index=1)


def test_safety_blocks_selected_corridor_and_depth_exhausted_cell() -> None:
    service = _service(_RecordPredictor())
    service.plan(_obs(), target_cycle_index=0)
    corridor_id = service.active_corridor_numeric_id
    cell_id = service.active_cell_id
    assert corridor_id >= 0
    assert cell_id >= 0

    service.block_corridor_numeric_id(corridor_id)
    assert service.active_corridor_id in service.blocked_corridor_ids
    service.mark_depth_exhausted(cell_id)
    assert cell_id in service.depth_exhausted_cell_ids


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_artifact_manifest_requires_passed_calibration_and_verified_lineage(
    tmp_path: Path,
) -> None:
    planned = tmp_path / "planned.json"
    planned.write_text(
        json.dumps(
            {
                "schema": "terrain_effect_ensemble_artifact_v1",
                "status": "present",
                "input_contract": "planned_cut",
            }
        ),
        encoding="utf-8",
    )
    silver = tmp_path / "silver.json"
    silver.write_text("{}", encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    payload = {
        "schema": "box_emptying_effect_capability_manifest_v1",
        "status": "released",
        "planned_effect_contract": "planned_cut_effect_v1",
        "calibration_route": "plan_to_executed_to_silver",
        "planned_effect": {
            "artifact_path": str(planned),
            "sha256": _sha256(planned),
            "held_out_reset_gate": "passed",
        },
        "silver_effect": {
            "artifact_path": str(silver),
            "sha256": _sha256(silver),
        },
        "act_freeze_bundle": {
            "artifact_path": str(freeze),
            "sha256": _sha256(freeze),
        },
        "capability": {"status": "rule_only_due_to_class_imbalance"},
        "support_envelope": {
            "source": "strict18_p01_p99",
            "fields": {
                "planned_depth_m": [0.05, 0.60],
                "cut_length_m": [0.75, 0.75],
                "entry_x_m": [-1.1, 1.1],
                "entry_z_m": [-0.7, 0.7],
                "exit_x_m": [-1.8, 1.8],
                "exit_z_m": [-1.45, 1.45],
                "direction_x": [-1.0, 1.0],
                "direction_z": [-1.0, 1.0],
            },
        },
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_box_emptying_artifact_manifest(manifest)
    assert loaded.planned_effect_artifact_path == planned.resolve()
    assert loaded.capability_status == "rule_only_due_to_class_imbalance"

    payload["planned_effect"]["held_out_reset_gate"] = "failed"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BoxEmptyingArtifactContractError, match="calibration_gate"):
        load_box_emptying_artifact_manifest(manifest)
