from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from testbed.eval import act_goal_condition_sensitivity_prerequisite_binding as binding

RETURN_CANDIDATE = "joint_regularized_mahalanobis_p99_v2"
RETURN_SEGMENT_IDS = (
    "return:898-1043:bb329f176aba",
    "return:3959-4161:4afcef2eee82",
)
RETURN_ALTERNATES = {
    "return:898-1043:bb329f176aba": "return:3959-4161:4afcef2eee82",
    "return:3959-4161:4afcef2eee82": "return:2323-2534:87aa0fb8c981",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _clean_code() -> dict[str, Any]:
    return {
        "git_head": "a" * 40,
        "git_branch": "tx/continous_follow_dev",
        "worktree_clean": True,
    }


def _fixture(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "results"
    (source / "rollouts").mkdir(parents=True)
    (source / "hdf5_rollouts").mkdir()
    source_paths = {
        "eval_resolved_config": source / "eval_resolved_config.yaml",
        "eval_run_metadata": source / "eval_run_metadata.json",
        "rollout_jsonl": source / "rollouts" / "rollout_000.jsonl",
        "rollout_hdf5": source / "hdf5_rollouts" / "episode_0.hdf5",
    }
    for name, path in source_paths.items():
        path.write_text(f"{name}\n", encoding="utf-8")
    dig_config = tmp_path / "dig.yaml"
    return_config = tmp_path / "return.yaml"
    dig_config.write_text("dig\n", encoding="utf-8")
    return_config.write_text("return\n", encoding="utf-8")

    stage_v1 = tmp_path / "stage_a_v1"
    stage_v1.mkdir()
    for name in ("baseline.json", "dig.json", "return.json"):
        (stage_v1 / name).write_text("{}\n", encoding="utf-8")
    stage_v1_lineage = {
        "source_results_root": str(source.resolve()),
        **{name: _record(path) for name, path in source_paths.items()},
        "dig_training_config": _record(dig_config),
        "return_training_config": _record(return_config),
    }
    _write_json(
        stage_v1 / "manifest.json",
        {
            "schema": "act_goal_condition_sensitivity_manifest_v1",
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
            "clean_code": _clean_code(),
            "source_lineage": stage_v1_lineage,
        },
    )

    support = tmp_path / "support_contract_v2_audit"
    support.mkdir()
    _write_json(
        support / "candidates.json",
        {
            "schema": "act_support_contract_candidates_v1",
            "support_contract_version": "support_contract_v2",
            "primitives": {"return": [{"candidate_id": RETURN_CANDIDATE}]},
        },
    )
    _write_json(
        support / "validation.json",
        {
            "schema": "act_support_contract_validation_v1",
            "support_contract_version": "support_contract_v2",
            "target_rollout_used_for_selection": False,
        },
    )
    support_lineage = {
        "source_results_root": str(source.resolve()),
        **{name: _record(path) for name, path in source_paths.items()},
        "stage_a_manifest": _record(stage_v1 / "manifest.json"),
        "stage_a_baseline": _record(stage_v1 / "baseline.json"),
        "stage_a_dig": _record(stage_v1 / "dig.json"),
        "stage_a_return": _record(stage_v1 / "return.json"),
        "dig_training_config": _record(dig_config),
        "return_training_config": _record(return_config),
        "code": _clean_code(),
    }
    _write_json(
        support / "manifest.json",
        {
            "schema": "act_support_contract_audit_manifest_v1",
            "status": "support_contract_not_selected",
            "support_contract_version": "support_contract_v2",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
            "target_rollout_used_for_selection": False,
            "selected_candidate_by_primitive": {
                "dig": None,
                "return": RETURN_CANDIDATE,
            },
            "selection_status_by_primitive": {
                "dig": "no_qualified_candidate",
                "return": "selected",
            },
            "source_lineage": support_lineage,
        },
    )

    stage_v2 = tmp_path / "stage_a_v2_return"
    stage_v2.mkdir()
    for name in ("baseline.json", "dig.json", "return.json"):
        (stage_v2 / name).write_text("{}\n", encoding="utf-8")
    stage_v2_lineage = {
        "source_results_root": str(source.resolve()),
        **{name: _record(path) for name, path in source_paths.items()},
        "dig_training_config": _record(dig_config),
        "return_training_config": _record(return_config),
        "applied_support_contract_by_primitive": {
            "return": {
                "support_contract_version": "support_contract_v2",
                "candidate_id": RETURN_CANDIDATE,
                "support_audit_manifest": _record(support / "manifest.json"),
                "support_audit_candidates": _record(support / "candidates.json"),
            }
        },
    }
    _write_json(
        stage_v2 / "manifest.json",
        {
            "schema": "act_goal_condition_sensitivity_manifest_v1",
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
            "clean_code": _clean_code(),
            "source_lineage": stage_v2_lineage,
            "applied_support_contract_by_primitive": {
                "dig": {
                    "support_contract_version": "support_contract_v1",
                    "candidate_id": "axis_p01_p99_v1",
                },
                "return": stage_v2_lineage["applied_support_contract_by_primitive"][
                    "return"
                ],
            },
        },
    )

    return_stability = tmp_path / "return_goal_response_stability_audit_v1"
    return_stability.mkdir()
    _write_json(
        return_stability / "return_segments.json",
        {
            "schema": "return_goal_response_stability_audit_results_v1",
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "segments": [
                {
                    "status": "completed",
                    "baseline_segment": {"segment_id": segment_id},
                    "alternate_segment": {
                        "segment_id": RETURN_ALTERNATES[segment_id]
                    },
                    "causal_status": {"status": "not_explained_by_frozen_inputs"},
                }
                for segment_id in RETURN_SEGMENT_IDS
            ],
        },
    )
    return_stability_lineage = {
        "stage_a_v2_manifest": _record(stage_v2 / "manifest.json"),
        "stage_a_v2_baseline": _record(stage_v2 / "baseline.json"),
        "stage_a_v2_return": _record(stage_v2 / "return.json"),
        "source_results_root": str(source.resolve()),
        **{name: _record(path) for name, path in source_paths.items()},
        "return_training_config": _record(return_config),
        "code": _clean_code(),
    }
    _write_json(
        return_stability / "manifest.json",
        {
            "schema": "return_goal_response_stability_audit_manifest_v1",
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
            "fixed_gate": {
                "required_responsive_frame_fraction": 0.8,
                "change_policy": "no_threshold_change_permitted",
            },
            "target_segment_ids": list(RETURN_SEGMENT_IDS),
            "source_lineage": return_stability_lineage,
        },
    )

    dig_validation = tmp_path / "dig_joint_support_validation_v1"
    dig_validation.mkdir()
    _write_json(
        dig_validation / "candidates.json",
        {
            "schema": "dig_joint_support_validation_candidates_v1",
            "support_contract_version": "support_contract_v2_dig_joint_v1",
            "primitive": "dig",
            "target_rollout_used_for_selection": False,
            "selected_candidate_id": None,
            "selection_status": "not_selected",
            "candidates": [],
        },
    )
    _write_json(
        dig_validation / "validation.json",
        {
            "schema": "dig_joint_support_validation_validation_v1",
            "support_contract_version": "support_contract_v2_dig_joint_v1",
            "primitive": "dig",
            "target_rollout_used_for_selection": False,
            "selection_input_scope": "strict_train_and_held_validation_only",
            "selected_candidate_id": None,
            "selection_status": "not_selected",
        },
    )
    _write_json(
        dig_validation / "manifest.json",
        {
            "schema": "dig_joint_support_validation_manifest_v1",
            "status": "support_contract_not_selected",
            "support_contract_version": "support_contract_v2_dig_joint_v1",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "runtime_support_change": False,
            "target_rollout_used_for_selection": False,
            "selection_input_scope": "strict_train_and_held_validation_only",
            "selected_candidate_id": None,
            "selection_status": "not_selected",
            "source_lineage": {
                "dig_training_config": _record(dig_config),
                "code": _clean_code(),
            },
        },
    )
    return {
        "source": source,
        "stage_v1": stage_v1,
        "support": support,
        "stage_v2": stage_v2,
        "return_stability": return_stability,
        "dig_validation": dig_validation,
        "dig_config": dig_config,
        "return_config": return_config,
    }


def _run(
    paths: dict[str, Path],
    *,
    output_root: Path,
    calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    captured = calls if calls is not None else []

    def fake_primitive_scoped_runner(**kwargs: Any) -> dict[str, Any]:
        captured.append(dict(kwargs))
        return {"status": "completed", "output_root": str(kwargs["output_root"])}

    return binding.run_stage_a_v3_after_prerequisite_audits(
        source_results_root=paths["source"],
        stage_a_v1_output_root=paths["stage_v1"],
        support_audit_output_root=paths["support"],
        stage_a_v2_output_root=paths["stage_v2"],
        return_stability_output_root=paths["return_stability"],
        dig_joint_validation_output_root=paths["dig_validation"],
        dig_training_config_path=paths["dig_config"],
        return_training_config_path=paths["return_config"],
        output_root=output_root,
        device="cpu",
        primitive_scoped_runner=fake_primitive_scoped_runner,
    )


def test_v3_binds_all_a2_lineage_and_explicitly_keeps_dig_v1(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    calls: list[dict[str, Any]] = []

    result = _run(paths, output_root=tmp_path / "stage_a_v3", calls=calls)

    assert result["status"] == "completed"
    assert result["dig_support_decision"] == {
        "decision": "keep_support_contract_v1",
        "candidate_id": "axis_p01_p99_v1",
        "reason": "independent_dig_joint_validation_support_contract_not_selected",
    }
    assert len(calls) == 1
    call = calls[0]
    assert call["stage_a_v1_output_root"] == paths["stage_v1"].resolve()
    lineage = call["additional_source_lineage"]["a2_prerequisite_audits"]
    assert lineage["stage_a_v1"]["manifest"] == _record(paths["stage_v1"] / "manifest.json")
    assert lineage["support_contract_v2"]["candidates"] == _record(
        paths["support"] / "candidates.json"
    )
    assert lineage["return_goal_response_stability"]["return_segments"] == _record(
        paths["return_stability"] / "return_segments.json"
    )
    assert lineage["return_goal_response_stability"]["segment_causal_status"] == {
        segment_id: "not_explained_by_frozen_inputs" for segment_id in RETURN_SEGMENT_IDS
    }
    assert lineage["dig_joint_support_validation"]["decision"] == "keep_support_contract_v1"
    assert lineage["stage_b_eligible"] is False


def test_v3_rejects_return_input_contract_mismatch_before_replay(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    payload_path = paths["return_stability"] / "return_segments.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["segments"][0]["causal_status"] = {"status": "normalization_mismatch"}
    _write_json(payload_path, payload)
    calls: list[dict[str, Any]] = []

    with pytest.raises(binding.StageAV3PrerequisiteBindingError, match="normalization_mismatch"):
        _run(paths, output_root=tmp_path / "stage_a_v3", calls=calls)
    assert calls == []


def test_v3_rejects_changed_return_alternate_before_replay(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    payload_path = paths["return_stability"] / "return_segments.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["segments"][0]["alternate_segment"] = {
        "segment_id": "return:2323-2534:87aa0fb8c981"
    }
    _write_json(payload_path, payload)

    with pytest.raises(binding.StageAV3PrerequisiteBindingError, match="alternate segment changed"):
        _run(paths, output_root=tmp_path / "stage_a_v3")


def test_v3_fails_closed_when_dig_joint_validation_selects_candidate(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    manifest_path = paths["dig_validation"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": "completed",
            "selected_candidate_id": "dig_joint_p999",
            "selection_status": "selected",
        }
    )
    _write_json(manifest_path, manifest)
    for filename in ("candidates.json", "validation.json"):
        path = paths["dig_validation"] / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(
            {
                "selected_candidate_id": "dig_joint_p999",
                "selection_status": "selected",
            }
        )
        _write_json(path, payload)

    with pytest.raises(binding.StageAV3PrerequisiteBindingError, match="selected a Dig candidate"):
        _run(paths, output_root=tmp_path / "stage_a_v3")


def test_v3_rejects_existing_or_nested_immutable_output_root(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        _run(paths, output_root=existing)
    with pytest.raises(binding.StageAV3PrerequisiteBindingError, match="distinct"):
        _run(paths, output_root=paths["return_stability"] / "nested")


def test_v3_rejects_source_sha_drift_before_replay(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["source"].joinpath("rollouts", "rollout_000.jsonl").write_text(
        "drift\n", encoding="utf-8"
    )
    calls: list[dict[str, Any]] = []

    with pytest.raises(binding.StageAV3PrerequisiteBindingError, match="SHA mismatch"):
        _run(paths, output_root=tmp_path / "stage_a_v3", calls=calls)
    assert calls == []
