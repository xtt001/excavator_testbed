from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from testbed.eval.worktool_tracking_calibration import (
    ACT_TRACKING_REPEAT_COUNT,
    EXPERT_REPLAY_REPEAT_COUNT,
    _validate_locked_primitive_lineage,
    build_margin_recommendation,
    contact_snapshot,
    write_json_exclusive,
)


def _geometry_measurement(
    *,
    expert_clearances: list[float] | None = None,
    act_clearances: list[float] | None = None,
    p95_m: float = 0.49,
    p99_m: float = 0.53,
) -> dict:
    clearances = expert_clearances or [0.288, 0.291, 0.286]
    observed_act_clearances = act_clearances or [
        0.249,
        0.248,
        0.252,
        0.245,
        0.250,
    ]
    return {
        "schema": "worktool_trajectory_geometry_measurement_v1",
        "status": "completed",
        "reference": {
            "path_id": "recorded_expert_episode_168",
            "minimum_3d_clearance_m": 0.288379,
        },
        "paths": [
            *[
                {
                    "path_id": f"expert_replay_{index:02d}",
                    "kind": "expert_action_replay",
                    "minimum_3d_clearance_m": clearance,
                }
                for index, clearance in enumerate(clearances)
            ],
            *[
                {
                    "path_id": f"act_repeat_{index:02d}",
                    "kind": "act_same_goal_repeat",
                    "minimum_3d_clearance_m": clearance,
                }
                for index, clearance in enumerate(
                    observed_act_clearances
                )
            ],
        ],
        "act_deviation_from_recorded_expert": {
            "metric": "maximum_corresponding_convex_cover_point_displacement_m",
            "alignment": "monotonic_dtw",
            "sample_count": 125,
            "p95_m": p95_m,
            "p99_m": p99_m,
            "max_m": 0.18,
        },
    }


def _live_manifest(
    *,
    expert_contact: bool = False,
    act_contact: bool = False,
) -> dict:
    return {
        "schema": "expert_act_same_goal_live_measurement_v1",
        "status": "completed",
        "promotion_eligible": False,
        "formal_1x10_executed": False,
        "training_data_written": False,
        "trials": [
            *[
                {
                    "trial_id": f"expert_replay_{index:02d}",
                    "kind": "expert_action_replay",
                    "wall_contact": bool(expert_contact and index == 0),
                    "bottom_contact": False,
                    "neutral_ack": True,
                }
                for index in range(EXPERT_REPLAY_REPEAT_COUNT)
            ],
            *[
                {
                    "trial_id": f"act_repeat_{index:02d}",
                    "kind": "act_same_goal_repeat",
                    "wall_contact": bool(act_contact and index == 0),
                    "bottom_contact": False,
                    "neutral_ack": True,
                }
                for index in range(ACT_TRACKING_REPEAT_COUNT)
            ],
        ],
    }


def test_contact_snapshot_requires_107d_and_preserves_typed_sessions() -> None:
    env = np.zeros(107, dtype=np.float32)
    env[101:107] = [1.0, 1234.0, 2.0, 0.0, 0.0, 3.0]

    result = contact_snapshot(env)

    assert result == {
        "wall_contact": True,
        "wall_step_max_force_n": pytest.approx(1234.0),
        "wall_session_count": 2,
        "bottom_contact": False,
        "bottom_step_max_force_n": pytest.approx(0.0),
        "bottom_session_count": 3,
    }
    with pytest.raises(ValueError, match="107D"):
        contact_snapshot(np.zeros(89, dtype=np.float32))


def test_locked_primitive_lineage_comes_from_window_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "full_episode_repaired_vds" / "episode_24.hdf5"
    source.parent.mkdir()
    source.touch()
    primitive = tmp_path / "primitives_copy" / "dig" / "episode_168.hdf5"
    primitive.parent.mkdir(parents=True)
    primitive.touch()
    manifest = primitive.parent.parent / "window_manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "primitive_episode_id": 168,
                    "primitive_name": "dig",
                    "source_episode_id": "episode_24",
                    "source_episode_path": str(source),
                    "source_start_step": 899,
                    "source_end_step_exclusive": 1050,
                }
            ]
        ),
        encoding="utf-8",
    )

    lineage = _validate_locked_primitive_lineage(
        primitive_path=primitive,
        source_episode_path=source,
    )
    assert lineage["source_episode_id"] == "episode_24"

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload[0]["source_start_step"] = 898
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="lineage mismatch"):
        _validate_locked_primitive_lineage(
            primitive_path=primitive,
            source_episode_path=source,
        )


def test_recommendation_uses_wall_clearance_loss_not_tangential_3d_norm() -> None:
    result = build_margin_recommendation(
        live_manifest=_live_manifest(),
        geometry_measurement=_geometry_measurement(),
    )

    assert result["status"] == "completed"
    assert result["schema"] == "expert_act_tracking_margin_recommendation_v2"
    assert result["apply_to_planner"] is True
    assert result["old_contract"] == {
        "act_tracking_margin_m": pytest.approx(0.15),
        "hard_clearance_m": pytest.approx(0.30),
    }
    assert result["recommended_contract"] == {
        "act_tracking_margin_m": pytest.approx(0.05),
        "hard_clearance_m": pytest.approx(0.24),
        "pose_interpolation_bound_m": pytest.approx(0.01),
        "total_nominal_clearance_requirement_m": pytest.approx(0.30),
    }
    assert result["act_repeat"]["p95_3d_deviation_m"] == pytest.approx(0.49)
    assert result["act_repeat"]["p99_3d_deviation_m"] == pytest.approx(0.53)
    assert result["act_repeat"]["wall_clearance_loss_p99_m"] == pytest.approx(
        0.043259
    )
    assert result["derivation"]["tracking_basis"] == (
        "ceil_cm(max_wall_clearance_loss + fk_error)"
    )
    assert result["derivation"]["hard_basis"] == (
        "floor_cm(min_contact_free_act_clearance - fk_error)"
    )
    assert result["derivation"]["full_3d_deviation_role"] == (
        "diagnostic_not_wall_normal_margin"
    )
    assert result["expert_replay"]["all_typed_contact_free"] is True


def test_recommendation_fails_closed_on_any_typed_contact() -> None:
    contact = build_margin_recommendation(
        live_manifest=_live_manifest(expert_contact=True),
        geometry_measurement=_geometry_measurement(),
    )
    assert contact["status"] == "blocked"
    assert contact["apply_to_planner"] is False
    assert contact["reason"] == "expert_replay_typed_contact_present"

    act_contact = build_margin_recommendation(
        live_manifest=_live_manifest(act_contact=True),
        geometry_measurement=_geometry_measurement(),
    )
    assert act_contact["status"] == "blocked"
    assert act_contact["apply_to_planner"] is False
    assert act_contact["reason"] == "act_repeat_typed_contact_present"


def test_recommendation_rejects_nonpositive_measured_safe_clearance() -> None:
    result = build_margin_recommendation(
        live_manifest=_live_manifest(),
        geometry_measurement=_geometry_measurement(
            act_clearances=[0.001] * ACT_TRACKING_REPEAT_COUNT
        ),
    )

    assert result["status"] == "blocked"
    assert result["apply_to_planner"] is False
    assert result["reason"] == "measured_hard_clearance_nonpositive"


def test_recommendation_requires_three_expert_and_five_act_trials() -> None:
    live = _live_manifest()
    live["trials"] = live["trials"][:-1]
    with pytest.raises(ValueError, match="five ACT"):
        build_margin_recommendation(
            live_manifest=live,
            geometry_measurement=_geometry_measurement(),
        )


def test_diagnostic_json_is_no_overwrite_and_self_hashable(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    payload = {
        "schema": "expert_act_tracking_margin_recommendation_v2",
        "status": "completed",
        "formal_1x10_executed": False,
        "training_data_written": False,
    }
    write_json_exclusive(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert len(hashlib.sha256(path.read_bytes()).hexdigest()) == 64
    with pytest.raises(FileExistsError):
        write_json_exclusive(path, payload)
