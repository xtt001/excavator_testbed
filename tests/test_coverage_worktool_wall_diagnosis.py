from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.coverage_worktool_wall_diagnosis import (
    OUTPUT_FILENAME,
    build_coverage_worktool_wall_diagnosis,
)


def _source_record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_contact_jsonl(
    path: Path,
    *,
    rollout_id: int,
    wall_shape: str = (
        "CodexFactoryLayout/CodexDigAreaBoards/Dig_ZMin_Board"
    ),
) -> None:
    env = [0.0] * ENV_STATE_V2_4_DIM
    env[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 0.59 + rollout_id * 0.01
    env[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = -0.32
    env[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = -1.01
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] = 1.0
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX] = (
        39_000.0 + rollout_id
    )
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX] = 1.0
    row = {
        "rollout_id": rollout_id,
        "step_id": 625 + rollout_id,
        "primitive_cycle_index": 1,
        "skill_name": "dig",
        "env_state": env,
        "qpos": [0.55, 0.70, 0.34, 0.19],
        "qvel": [-0.06, 0.27, -0.07, 0.19],
        "action": [0.17, -0.72, -0.15, 0.11],
        "warnings": [
            "bucket_contact_diagnostic:contact_count=1",
            "bucket_contact_diagnostic:max_normal_force_n=39000",
            (
                "bucket_contact_diagnostic:max_external_shape="
                f"{wall_shape}"
            ),
        ],
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _write_validation(
    tmp_path: Path,
    *,
    wall_shape: str = (
        "CodexFactoryLayout/CodexDigAreaBoards/Dig_ZMin_Board"
    ),
) -> Path:
    rollout_sources = []
    rollouts = []
    for rollout_id in range(3):
        jsonl = tmp_path / f"rollout_{rollout_id:03d}.jsonl"
        _write_contact_jsonl(
            jsonl,
            rollout_id=rollout_id,
            wall_shape=wall_shape,
        )
        rollout_sources.append(_source_record(jsonl))
        rollouts.append(
            {
                "rollout_id": rollout_id,
                "passed": False,
                "target_exemplar_id": "episode_168",
                "planned_depth_m": 0.3768954277038574,
                "planned_depth_crossing_step_id": (
                    637 if rollout_id == 2 else -1
                ),
                "minimum_wall_clearance_m": 0.37365931543051656,
                "wall_contact": True,
                "bottom_contact": False,
                "stuck": False,
                "timeout": False,
                "zero_action_after_trigger": True,
                "neutral_acknowledged": True,
                "terminal_requested": True,
                "bounded_trigger_kind": "wall",
                "actual_execution_tail_exceeded": rollout_id == 2,
                "actual_execution_tail_plane_depth_m": (
                    0.044127464294433594
                    if rollout_id == 2
                    else None
                ),
                "execution_tail_limit_m": 0.023427505493164063,
                "plan_checks": [
                    {
                        "target_cycle_index": 1,
                        "exemplar_id": "episode_168",
                        "corridor_id": 1_000_168,
                        "raw_fields_sha256": "c167e087",
                        "exact_library_tuple": True,
                        "minimum_wall_clearance_m": (
                            0.37365931543051656
                        ),
                    }
                ],
            }
        )
    validation = {
        "schema": "act_actual_tuple_bounded_one_dig_validation_v1",
        "status": "failed",
        "evidence_kind": "bounded_live_production_rollout",
        "target_cycle_index": 1,
        "rollout_count": 3,
        "source_lock": {"rollout_jsonl": rollout_sources},
        "contracts": {"minimum_wall_clearance_m": 0.30},
        "rollouts": rollouts,
        "functional_1x10_allowed": False,
        "next_branch": "unity_3d_worktool_sweep",
    }
    path = tmp_path / "bounded_validation.json"
    path.write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_three_bucket_wall_contacts_classify_incomplete_2d_envelope(
    tmp_path: Path,
) -> None:
    validation = _write_validation(tmp_path)

    artifact = build_coverage_worktool_wall_diagnosis(
        bounded_validation_path=validation,
        output_dir=tmp_path / "report",
    )

    assert artifact["status"] == "completed"
    assert (
        artifact["primary_classification"]
        == "bucket_3d_swept_envelope_incomplete_primary"
    )
    assert artifact["evidence_matrix"] == {
        "bounded_rollout_count": 3,
        "exact_library_tuple_count": 3,
        "planned_2d_clearance_pass_count": 3,
        "typed_wall_contact_count": 3,
        "bucket_contact_shape_identified_count": 3,
        "bottom_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "neutral_stop_contract_pass_count": 3,
        "tail_evaluable_count": 1,
        "tail_exceeded_count": 1,
    }
    assert artifact["promotion_gates"]["functional_1x10_allowed"] is False
    assert artifact["promotion_gates"]["functional_3x10_allowed"] is False
    assert artifact["next_branch"]["name"] == "unity_3d_worktool_sweep"
    assert artifact["next_branch"]["threshold_relaxation_allowed"] is False
    assert artifact["next_branch"]["temporal_window_blame_allowed"] is False
    assert {
        item["contact"]["external_shape"]
        for item in artifact["rollouts"]
    } == {
        "CodexFactoryLayout/CodexDigAreaBoards/Dig_ZMin_Board"
    }
    assert (tmp_path / "report" / OUTPUT_FILENAME).is_file()


def test_report_fails_if_frozen_jsonl_sha_has_drifted(
    tmp_path: Path,
) -> None:
    validation = _write_validation(tmp_path)
    source = tmp_path / "rollout_000.jsonl"
    payload = source.read_bytes()
    source.write_bytes(b" " + payload[1:])

    with pytest.raises(ValueError, match="source SHA256 mismatch"):
        build_coverage_worktool_wall_diagnosis(
            bounded_validation_path=validation,
            output_dir=tmp_path / "report",
        )


def test_report_is_no_overwrite(tmp_path: Path) -> None:
    validation = _write_validation(tmp_path)
    kwargs = {
        "bounded_validation_path": validation,
        "output_dir": tmp_path / "report",
    }
    build_coverage_worktool_wall_diagnosis(**kwargs)

    with pytest.raises(FileExistsError):
        build_coverage_worktool_wall_diagnosis(**kwargs)
