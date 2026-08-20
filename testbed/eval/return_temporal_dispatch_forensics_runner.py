"""No-overwrite artifact writer for frozen Return temporal-dispatch forensics."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from testbed.eval.return_temporal_dispatch_forensics import (
    RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA,
)
from testbed.eval.return_temporal_dispatch_forensics_replay import (
    run_return_temporal_dispatch_forensics_replay,
)

RETURN_TEMPORAL_DISPATCH_FORENSICS_MANIFEST_SCHEMA = (
    "return_temporal_dispatch_forensics_manifest_v1"
)
RETURN_TEMPORAL_DISPATCH_FORENSICS_RESULTS_SCHEMA = (
    "return_temporal_dispatch_forensics_results_v1"
)


def run_return_temporal_dispatch_forensics_artifact(
    *,
    return_stability_output_root: str | Path,
    output_root: str | Path,
    device: str = "cuda",
    replay_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write one immutable, diagnostic-only contributor-forensics artifact."""

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"Return temporal-forensics output already exists: {destination}"
        )
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError("Return temporal-forensics requires a clean Git worktree")
    stability_root = Path(return_stability_output_root).expanduser().resolve(strict=True)
    runner = replay_runner or run_return_temporal_dispatch_forensics_replay
    result = runner(return_stability_output_root=stability_root, device=str(device))
    _validate_result(result)
    artifact = {
        "schema": RETURN_TEMPORAL_DISPATCH_FORENSICS_RESULTS_SCHEMA,
        **dict(result),
    }
    manifest = {
        "schema": RETURN_TEMPORAL_DISPATCH_FORENSICS_MANIFEST_SCHEMA,
        "status": artifact["status"],
        "evidence_kind": artifact["evidence_kind"],
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "runtime_change": False,
        "source_lineage": {
            "return_goal_response_stability_root": str(stability_root),
            "return_goal_response_stability_manifest": _source_record(
                stability_root / "manifest.json"
            ),
            "return_goal_response_stability_results": _source_record(
                stability_root / "return_segments.json"
            ),
            "code": clean_code,
        },
        "output_files": ["manifest.json", "forensics.json", "report.md"],
    }
    report = _render_report(artifact)
    destination.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(destination / "manifest.json", manifest)
    _write_json_exclusive(destination / "forensics.json", artifact)
    _write_text_exclusive(destination / "report.md", report)
    return {"status": artifact["status"], "output_root": str(destination), "manifest": manifest}


def _validate_result(result: Mapping[str, Any]) -> None:
    if result.get("schema") != RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA:
        raise ValueError("Return temporal-forensics result schema mismatch")
    if result.get("status") != "completed":
        raise ValueError("Return temporal-forensics replay did not complete")
    if (
        result.get("diagnostic_only") is not True
        or result.get("promotion_eligible") is not False
        or result.get("closed_loop_claim") is not False
    ):
        raise ValueError("Return temporal-forensics evidence boundary mismatch")


def _render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Return temporal dispatch 历史贡献取证",
        "",
        "本工件只解释旧 oldest-first 聚合如何压低目标响应；它不选择或启用新 runtime 策略。",
        "",
    ]
    for segment in result.get("segments", ()):  # Defensive for injected tests.
        if not isinstance(segment, Mapping):
            continue
        summary = segment.get("forensics", {}).get("suppression_mechanism_summary", {})
        if not isinstance(summary, Mapping):
            summary = {}
        lines.append(
            "- `{segment}`：受抑制帧 {count}；历史净反向 {opposes}；"
            "最新权重稀释 {diluted}；最新 query 权重 {low:.4%}–{high:.4%}。".format(
                segment=segment.get("baseline_segment_id", "unknown"),
                count=segment.get("forensics", {}).get(
                    "latest_response_suppressed_frame_count", "unknown"
                )
                if isinstance(segment.get("forensics"), Mapping)
                else "unknown",
                opposes=summary.get(
                    "historical_net_opposes_latest_response_frame_count", "unknown"
                ),
                diluted=summary.get(
                    "latest_weight_dilution_without_net_opposition_frame_count",
                    "unknown",
                ),
                low=float(summary.get("latest_query_weight_min", 0.0)),
                high=float(summary.get("latest_query_weight_max", 0.0)),
            )
        )
    lines.extend(
        [
            "",
            "替代策略必须先经过 source-disjoint Return 验证，不能依据这两段失败样本选择窗口或权重。",
            "",
        ]
    )
    return "\n".join(lines)


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def _clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, check=False, capture_output=True, text=True
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_text_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


__all__ = [
    "RETURN_TEMPORAL_DISPATCH_FORENSICS_MANIFEST_SCHEMA",
    "RETURN_TEMPORAL_DISPATCH_FORENSICS_RESULTS_SCHEMA",
    "run_return_temporal_dispatch_forensics_artifact",
]
