"""Policy-audit evidence manifest for eval readiness checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "policy_audit_manifest_v1"

EXPECTED_AUDITS = {
    "dig_ckpt_audit": "dig_ckpt_offline_audit_v1",
    "dig_depth_audit": "dig_depth_semantics_audit_v1",
    "return_ckpt_audit": "return_ckpt_offline_audit_v1",
}


def build_policy_audit_manifest(
    *,
    dig_ckpt_audit: str | Path | None = None,
    dig_depth_audit: str | Path | None = None,
    return_ckpt_audit: str | Path | None = None,
) -> dict[str, Any]:
    """Build a manifest summarizing existing policy-audit JSON artifacts."""

    paths = {
        "dig_ckpt_audit": dig_ckpt_audit,
        "dig_depth_audit": dig_depth_audit,
        "return_ckpt_audit": return_ckpt_audit,
    }
    audits = {
        name: _audit_entry(name=name, path_value=paths[name])
        for name in EXPECTED_AUDITS
    }
    evidence_gaps = [
        f"{name}:{entry['status']}"
        for name, entry in audits.items()
        if entry["status"] != "present"
    ]
    eval_ready = not evidence_gaps
    return {
        "schema_version": SCHEMA_VERSION,
        "overall_status": (
            "ready_for_rollout_eval"
            if eval_ready
            else "missing_or_invalid_policy_audit"
        ),
        "eval_ready": bool(eval_ready),
        "evidence_gaps": evidence_gaps,
        "audits": audits,
        "next_steps": _next_steps(evidence_gaps),
    }


def write_policy_audit_manifest(
    *,
    output: str | Path,
    dig_ckpt_audit: str | Path | None = None,
    dig_depth_audit: str | Path | None = None,
    return_ckpt_audit: str | Path | None = None,
) -> Path:
    """Write the policy-audit manifest JSON and return the output path."""

    manifest = build_policy_audit_manifest(
        dig_ckpt_audit=dig_ckpt_audit,
        dig_depth_audit=dig_depth_audit,
        return_ckpt_audit=return_ckpt_audit,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output_path


def _audit_entry(name: str, path_value: str | Path | None) -> dict[str, Any]:
    expected_schema = EXPECTED_AUDITS[name]
    if path_value is None:
        return {
            "status": "missing",
            "path": "",
            "expected_schema_version": expected_schema,
            "schema_version": "",
            "summary_headline": {},
        }
    path = Path(path_value)
    if not path.exists():
        return {
            "status": "missing",
            "path": str(path),
            "expected_schema_version": expected_schema,
            "schema_version": "",
            "summary_headline": {},
        }
    payload = json.loads(path.read_text())
    schema_version = str(payload.get("schema_version", ""))
    status = "present" if schema_version == expected_schema else "schema_mismatch"
    summary = dict(payload.get("summary", {}) or {})
    headline = summary.get("headline", summary)
    return {
        "status": status,
        "path": str(path),
        "expected_schema_version": expected_schema,
        "schema_version": schema_version,
        "summary_headline": headline if isinstance(headline, dict) else {},
    }


def _next_steps(evidence_gaps: list[str]) -> list[str]:
    if not evidence_gaps:
        return ["policy_audit_complete_run_rollout_review_after_eval"]
    steps: list[str] = []
    for gap in evidence_gaps:
        audit_name, status = gap.split(":", 1)
        if status == "missing":
            steps.append(f"run_or_attach_{audit_name}")
        else:
            steps.append(f"inspect_{audit_name}_{status}")
    return steps


__all__ = [
    "EXPECTED_AUDITS",
    "SCHEMA_VERSION",
    "build_policy_audit_manifest",
    "write_policy_audit_manifest",
]
