from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from testbed.policies.dig_effect_fk import (
    FIXED_TIP_FK_ARTIFACT_SCHEMA,
    DifferentiableFixedTipFK,
    load_fixed_tip_fk_artifact,
)


def _matrix(*, translation: tuple[float, float, float] = (0.0, 0.0, 0.0)):
    x, y, z = translation
    return [
        [1.0, 0.0, 0.0, x],
        [0.0, 1.0, 0.0, y],
        [0.0, 0.0, 1.0, z],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _artifact() -> dict:
    return {
        "schema": FIXED_TIP_FK_ARTIFACT_SCHEMA,
        "status": "completed",
        "candidate_id": "bucket_center_tooth_leading_edge_midpoint_v0_1",
        "qpos_order": ["swing", "boom", "stick", "bucket"],
        "raw_qpos_min_rad": [0.0, 0.0, 0.0, 0.0],
        "raw_qpos_max_rad": [3.141592653589793, 1.0, 1.0, 1.0],
        "reference_normalized_qpos": [0.0, 0.0, 0.0, 0.0],
        "reference_raw_qpos_rad": [0.0, 0.0, 0.0, 0.0],
        "joint_direction_signs": [1.0, 1.0, 1.0, 1.0],
        "joint_anchor_world_m": [[0.0, 0.0, 0.0]] * 4,
        "joint_axis_world": [[0.0, 0.0, 1.0]] * 4,
        "bucket_link_reference_world": _matrix(translation=(1.0, 0.0, 0.0)),
        "fixed_tip_in_bucket_link_m": [0.0, 0.0, 0.0],
        "dig_area_world_to_local": _matrix(),
        "fixtures": [
            {
                "normalized_qpos": [0.5, 0.0, 0.0, 0.0],
                "fixed_tip_dig_area_xyz_m": [0.0, 1.0, 0.0],
            }
        ],
        "source_lock": {"unity_head": "abc1234"},
    }


def test_fixed_tip_fk_rotates_bucket_and_preserves_action_gradient(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "fk.json"
    artifact_path.write_text(json.dumps(_artifact()))
    contract = load_fixed_tip_fk_artifact(artifact_path)
    fk = DifferentiableFixedTipFK(contract)
    qpos = torch.tensor([[0.5, 0.0, 0.0, 0.0]], requires_grad=True)

    tip = fk(qpos)

    torch.testing.assert_close(
        tip,
        torch.tensor([[0.0, 1.0, 0.0]]),
        atol=1.0e-6,
        rtol=0.0,
    )
    tip[:, 0].sum().backward()
    assert qpos.grad is not None
    assert abs(float(qpos.grad[0, 0])) > 1.0e-3


def test_fixed_tip_fk_validates_all_unity_fixtures(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fk.json"
    artifact_path.write_text(json.dumps(_artifact()))
    contract = load_fixed_tip_fk_artifact(artifact_path)

    assessment = DifferentiableFixedTipFK(contract).validate_fixtures(max_error_m=0.002)

    assert assessment["passed"] is True
    assert assessment["fixture_count"] == 1
    assert assessment["max_error_m"] == pytest.approx(0.0, abs=1.0e-6)


def test_fixed_tip_fk_rejects_wrong_candidate(tmp_path: Path) -> None:
    payload = _artifact()
    payload["candidate_id"] = "moving_lowest_point"
    artifact_path = tmp_path / "fk.json"
    artifact_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="fixed tooth candidate"):
        load_fixed_tip_fk_artifact(artifact_path)
