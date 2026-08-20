from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from testbed.eval import dig_support_outlier_audit as audit


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _clean_code() -> dict[str, Any]:
    return {
        "git_head": "a" * 40,
        "git_branch": "tx/continous_follow_dev",
        "worktree_clean": True,
    }


def _alignment() -> dict[str, Any]:
    frames = []
    for index in range(2):
        frames.append(
            {
                "qpos": [0.1, 0.2, 0.3, 0.4],
                "qvel": [0.0, 0.33 + index * 0.01, 0.0, 0.0],
                "token": [0.0] * 10,
            }
        )
    return {
        "schema": "dig_support_outlier_alignment_audit_v1",
        "status": "completed",
        "frame_table": frames,
        "alignment": {"all_actions_use_immediate_pre_action_observation": True},
    }


def _distribution() -> dict[str, Any]:
    populations = {
        "strict_train_action_loss_mask_1": {
            "within_target_interval_row_count": 4,
        }
    }
    return {
        "segment_qvel1_excursion_measurement": {
            "qvel1_v1_outside_frame_count": 2,
            "v1_excursion_topology": "one_contiguous_multi_frame_run",
        },
        "qvel1_same_numeric_range_populations": populations,
        "qvel1_v1_outside_numeric_range_populations": populations,
    }


def _fixture(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "results"
    source.mkdir()
    rollout_hdf5 = source / "episode_0.hdf5"
    rollout_jsonl = source / "rollout_000.jsonl"
    training = tmp_path / "dig.yaml"
    for path in (rollout_hdf5, rollout_jsonl, training):
        path.write_text(path.name, encoding="utf-8")

    joint = tmp_path / "dig_joint"
    joint.mkdir()
    joint_manifest = joint / "manifest.json"
    joint_validation = joint / "validation.json"
    _write_json(
        joint_manifest,
        {"status": "support_contract_not_selected", "selected_candidate_id": None},
    )
    _write_json(joint_validation, {"selection_status": "not_selected"})

    stage = tmp_path / "stage_a_v3"
    stage.mkdir()
    manifest = stage / "manifest.json"
    dig = stage / "dig.json"
    source_lineage = {
        "source_results_root": str(source.resolve()),
        "rollout_hdf5": _record(rollout_hdf5),
        "rollout_jsonl": _record(rollout_jsonl),
        "dig_training_config": _record(training),
        "additional_audit_lineage": {
            "a2_prerequisite_audits": {
                "dig_joint_support_validation": {
                    "manifest": _record(joint_manifest),
                    "validation": _record(joint_validation),
                }
            }
        },
    }
    _write_json(
        manifest,
        {
            "schema": "act_goal_condition_sensitivity_manifest_v1",
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
            "clean_code": _clean_code(),
            "source_lineage": source_lineage,
        },
    )
    _write_json(
        dig,
        {
            "primitive": "dig",
            "status": "completed",
            "segment_pair_records": [
                {
                    "segment": {"segment_id": audit.TARGET_SEGMENT_ID},
                    "result": {
                        "status": "completed",
                        "conditions": {
                            "alternate": {
                                "classification": "out_of_support",
                                "support": {
                                    "baseline": {
                                        "status": "out_of_support",
                                        "violations": [[{"field": "qvel[1]"}]],
                                    },
                                    "counterfactual": {
                                        "status": "out_of_support",
                                        "violations": [[{"field": "qvel[1]"}]],
                                    },
                                },
                            }
                        },
                    },
                }
            ],
        },
    )
    return {"stage": stage, "training": training}


def test_decision_keeps_v1_when_alignment_is_valid_but_no_joint_rule_qualifies() -> None:
    result = audit.derive_dig_support_outlier_decision(
        alignment={"status": "completed"},
        distribution=_distribution(),
        joint_validation={"status": "support_contract_not_selected", "selected_candidate_id": None},
    )

    assert result["decision"] == "retain_v1_runtime_rejection_or_stop"
    assert result["recording_assessment"] == "not_a_single_frame_spike"
    assert result["numeric_coverage_assessment"] == "qvel1_has_strict_train_numeric_precedents"


def test_decision_requires_contract_repair_before_capability_interpretation() -> None:
    result = audit.derive_dig_support_outlier_decision(
        alignment={"status": "alignment_invalid"},
        distribution=_distribution(),
        joint_validation={"status": "support_contract_not_selected", "selected_candidate_id": None},
    )

    assert result["decision"] == "repair_data_contract_then_rerun_stage_a"


def test_runner_writes_exclusive_artifact_after_validating_immutable_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path)
    monkeypatch.setattr(audit, "_clean_code_record", _clean_code)
    monkeypatch.setattr(
        audit, "audit_dig_support_outlier_alignment_from_paths", lambda **_: _alignment()
    )
    monkeypatch.setattr(audit, "load_dig_support_outlier_distribution_references", lambda **_: object())
    monkeypatch.setattr(
        audit,
        "analyze_dig_support_outlier_segment",
        lambda **_: SimpleNamespace(as_dict=_distribution),
    )
    output = tmp_path / "outlier"

    result = audit.run_dig_support_outlier_audit(
        stage_a_v3_output_root=paths["stage"],
        dig_training_config_path=paths["training"],
        output_root=output,
    )

    assert result["status"] == "completed"
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "stage_a_v3_pair.json",
        "frame_table.json",
        "alignment.json",
        "distribution.json",
        "decision.json",
        "report.md",
    }
    decision = json.loads((output / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "retain_v1_runtime_rejection_or_stop"
    with pytest.raises(FileExistsError, match="already exists"):
        audit.run_dig_support_outlier_audit(
            stage_a_v3_output_root=paths["stage"],
            dig_training_config_path=paths["training"],
            output_root=output,
        )


def test_runner_rejects_target_when_v3_no_longer_attributes_oos_to_qvel1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path)
    dig_path = paths["stage"] / "dig.json"
    payload = json.loads(dig_path.read_text(encoding="utf-8"))
    support = payload["segment_pair_records"][0]["result"]["conditions"]["alternate"]["support"]
    for value in support.values():
        value["violations"] = [[{"field": "qvel[2]"}]]
    _write_json(dig_path, payload)
    monkeypatch.setattr(audit, "_clean_code_record", _clean_code)

    with pytest.raises(audit.DigSupportOutlierAuditError, match=r"qvel\[1\]"):
        audit.run_dig_support_outlier_audit(
            stage_a_v3_output_root=paths["stage"],
            dig_training_config_path=paths["training"],
            output_root=tmp_path / "outlier",
        )
