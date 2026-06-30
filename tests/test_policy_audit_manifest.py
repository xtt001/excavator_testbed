from __future__ import annotations

import json
from pathlib import Path

from testbed.eval.policy_audit_manifest import build_policy_audit_manifest


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def test_policy_audit_manifest_marks_eval_ready_when_expected_audits_exist(
    tmp_path: Path,
) -> None:
    dig = _write_json(
        tmp_path / "dig_ckpt.json",
        {
            "schema_version": "dig_ckpt_offline_audit_v1",
            "summary": {"first_action": {"count": 3}, "chunks": {"count": 1}},
        },
    )
    depth = _write_json(
        tmp_path / "dig_depth.json",
        {
            "schema_version": "dig_depth_semantics_audit_v1",
            "summary": {"headline": {"count": 3, "payload_p50_kg": 42.0}},
        },
    )
    ret = _write_json(
        tmp_path / "return_ckpt.json",
        {
            "schema_version": "return_ckpt_offline_audit_v1",
            "summary": {"headline": {"record_count": 5}},
        },
    )

    manifest = build_policy_audit_manifest(
        dig_ckpt_audit=dig,
        dig_depth_audit=depth,
        return_ckpt_audit=ret,
    )

    assert manifest["schema_version"] == "policy_audit_manifest_v1"
    assert manifest["overall_status"] == "ready_for_rollout_eval"
    assert manifest["eval_ready"] is True
    assert manifest["evidence_gaps"] == []
    assert manifest["audits"]["dig_ckpt_audit"]["status"] == "present"
    assert manifest["audits"]["dig_depth_audit"]["schema_version"] == (
        "dig_depth_semantics_audit_v1"
    )
    assert manifest["audits"]["return_ckpt_audit"]["summary_headline"] == {
        "record_count": 5
    }


def test_policy_audit_manifest_records_missing_and_schema_mismatch_without_passing(
    tmp_path: Path,
) -> None:
    dig = _write_json(
        tmp_path / "dig_ckpt.json",
        {
            "schema_version": "unexpected_schema_v0",
            "summary": {"first_action": {"count": 1}},
        },
    )

    manifest = build_policy_audit_manifest(dig_ckpt_audit=dig)

    assert manifest["overall_status"] == "missing_or_invalid_policy_audit"
    assert manifest["eval_ready"] is False
    assert manifest["audits"]["dig_ckpt_audit"]["status"] == "schema_mismatch"
    assert manifest["audits"]["dig_depth_audit"]["status"] == "missing"
    assert manifest["audits"]["return_ckpt_audit"]["status"] == "missing"
    assert "dig_ckpt_audit:schema_mismatch" in manifest["evidence_gaps"]
    assert "dig_depth_audit:missing" in manifest["evidence_gaps"]
    assert "return_ckpt_audit:missing" in manifest["evidence_gaps"]
