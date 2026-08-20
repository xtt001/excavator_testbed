from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from testbed.eval import return_closed_loop_runtime as runtime


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validation_payload() -> dict[str, Any]:
    return {
        "schema": "return_temporal_dispatch_validation_artifact_v1",
        "primitive": "return",
        "target_stage_a_failures_used": False,
        "input_scope": {
            "fit_partition": "strict_train",
            "evaluation_partition": "held_out_source_disjoint_return",
            "counterfactual_tokens": "real_held_validation_tokens_only",
            "stage_a_artifact_input_accepted": False,
            "target_rollout_input_accepted": False,
        },
        "selection": {
            "runtime_default_changed": False,
            "selected_strategy_id": None,
            "candidate_frozen_for_opt_in_shadow_only": False,
        },
        "policy_verification": {"all_pairs_passed": True},
        "metric_contract": {
            "discontinuity_threshold": [0.1, 0.2, 0.3, 0.4],
            "jitter_and_discontinuity_definition": (
                "strict_train_action_delta_abs_p99_per_axis"
            ),
        },
    }


def _fixture_set(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        camera_names=("stick_up", "stick_down", "eye_left", "eye_right"),
        source_lineage={
            "recorded_reset_context": {
                "unity_scene_id": "Assets/Test.unity@sha256:" + "b" * 64,
                "runtime_build_id": "editor:test:agx_env_state_v2_4_107",
                "action_order": ["swing", "boom", "stick", "bucket"],
                "qpos_order": ["q0", "q1", "q2", "q3"],
                "qvel_order": ["v0", "v1", "v2", "v3"],
            },
            "rollout_hdf5": {"path": str(tmp_path / "source.hdf5")},
        },
    )


def _stage_root(tmp_path: Path) -> tuple[Path, Path]:
    checkpoint = tmp_path / "checkpoint.ckpt"
    stats = tmp_path / "dataset_stats.pkl"
    training_config = tmp_path / "return.yaml"
    checkpoint.write_bytes(b"checkpoint")
    stats.write_bytes(b"stats")
    training_config.write_text("task: {}\n", encoding="utf-8")
    root = tmp_path / "stage-a-v3"
    _write_json(
        root / "manifest.json",
        {
            "source_lineage": {
                "checkpoints_and_stats": {
                    "return": {
                        "checkpoint": {
                            "path": str(checkpoint),
                            "sha256": _sha256(checkpoint),
                        },
                        "dataset_stats": {
                            "path": str(stats),
                            "sha256": _sha256(stats),
                        },
                    }
                },
                "return_training_config": {
                    "path": str(training_config),
                    "sha256": _sha256(training_config),
                },
            }
        },
    )
    return root, training_config


def test_runtime_lock_binds_disjoint_validation_and_records_current_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_root, training_config = _stage_root(tmp_path)
    validation_path = tmp_path / "validation.json"
    _write_json(validation_path, _validation_payload())
    unity_root = tmp_path / "unity"
    unity_root.mkdir()
    monkeypatch.setattr(
        runtime,
        "load_frozen_recorded_return_closed_loop_fixture_set",
        lambda **_: _fixture_set(tmp_path),
    )
    monkeypatch.setattr(
        runtime,
        "_recorded_unity_metadata",
        lambda _path: {
            "unity_git_commit": "u" * 40,
            "unity_git_dirty": True,
        },
    )

    def fake_git(root: Path, *args: str) -> str:
        if args == ("status", "--short"):
            return " M dirty.cs" if root == unity_root else ""
        if root == unity_root:
            return "u" * 40
        return "p" * 40

    monkeypatch.setattr(runtime, "_git_output", fake_git)

    lock = runtime.build_current_return_closed_loop_runtime_lock(
        stage_a_v3_root=stage_root,
        return_validation_path=validation_path,
        unity_repo=unity_root,
    )

    assert lock["source_sha"] == "p" * 40
    assert lock["return_training_config"]["path"] == str(training_config)
    assert lock["return_training_config"]["sha256"] == _sha256(training_config)
    assert lock["stage_a_v3_manifest"]["sha256"] == _sha256(
        stage_root / "manifest.json"
    )
    assert lock["return_validation"]["sha256"] == _sha256(validation_path)
    assert lock["action_discontinuity_threshold"] == [0.1, 0.2, 0.3, 0.4]
    assert lock["unity_worktree_clean"] is False
    assert lock["unity_source_rebuildable"] is False
    assert lock["qvel_fixture_application_supported"] is False
    assert lock["terrain_state_restore_supported"] is False
    assert lock["official_handoff_evaluator_confirmed"] is False


def test_runtime_lock_rejects_target_tuned_or_non_disjoint_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_root, _ = _stage_root(tmp_path)
    validation = _validation_payload()
    validation["target_stage_a_failures_used"] = True
    validation_path = tmp_path / "validation.json"
    _write_json(validation_path, validation)
    unity_root = tmp_path / "unity"
    unity_root.mkdir()
    monkeypatch.setattr(
        runtime,
        "load_frozen_recorded_return_closed_loop_fixture_set",
        lambda **_: _fixture_set(tmp_path),
    )

    with pytest.raises(ValueError, match="target failures"):
        runtime.build_current_return_closed_loop_runtime_lock(
            stage_a_v3_root=stage_root,
            return_validation_path=validation_path,
            unity_repo=unity_root,
        )
