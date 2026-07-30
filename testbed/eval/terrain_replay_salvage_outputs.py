"""Postprocess and compose strict versus partial replay salvage outputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py

from testbed.data.terrain_replay_postprocess import build_selected_replay_postprocess
from testbed.eval.terrain_replay_salvage import PARENT_SELECTED_EPISODE_IDS
from testbed.eval.terrain_replay_salvage_views import (
    COMBINED_STRICT_VIEW,
    LAYERED_SALVAGE_VIEW,
    build_composite_clean_vds,
)


def summarize_partial_coverage(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Count coverage from the one retained candidate per source identity."""

    source_ids = [str(row.get("source_episode_id", "")) for row in rows]
    if any(not value for value in source_ids):
        raise ValueError("Selected partial candidate is missing source identity.")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Selected partial candidates contain duplicate source identity.")
    cycle_count = sum(int(row.get("eligible_cycle_count", 0)) for row in rows)
    step_count = sum(int(row.get("valid_action_step_count", 0)) for row in rows)
    if cycle_count < 0 or step_count < 0:
        raise ValueError("Selected partial coverage cannot be negative.")
    return {
        "eligible_cycle_count": cycle_count,
        "valid_action_step_count": step_count,
    }


def postprocess_selected_group(
    *,
    output_root: Path,
    selected_root: Path,
    episode_ids: tuple[int, ...],
    replay_config: Path,
    group_name: str,
    evidence_kind: str,
) -> Path | None:
    """Run one fresh postprocess attempt, reusing only a complete exact result."""

    if not episode_ids:
        return None
    runs_root = output_root / "postprocess_runs"
    completed: list[Path] = []
    for path in sorted(runs_root.glob(f"{group_name}_attempt_*")):
        report_path = path / "post_replay_qc.json"
        if not report_path.is_file():
            continue
        report = _read_json(report_path)
        if report.get("selected_episode_ids") != list(episode_ids):
            raise ValueError(f"Postprocess resume inventory mismatch: {path}")
        if report.get("evidence_kind") != evidence_kind:
            raise ValueError(f"Postprocess resume evidence mismatch: {path}")
        completed.append(path)
    if len(completed) > 1:
        raise ValueError(f"Multiple completed postprocess runs exist: {completed}")
    if completed:
        return completed[0] / "selected_replay_clean_vds"
    attempt_index = len(list(runs_root.glob(f"{group_name}_attempt_*")))
    run_root = runs_root / f"{group_name}_attempt_{attempt_index:02d}"
    run_root.mkdir(parents=True, exist_ok=False)
    build_selected_replay_postprocess(
        selected_root=selected_root,
        output_root=run_root,
        label_config_path=replay_config,
        selected_episode_ids=episode_ids,
        complete_inventory=False,
        evidence_kind=evidence_kind,
        training_usage=(
            "strict_replay_addition_intermediate"
            if group_name == "strict_additions"
            else "partial_replay_salvage_ablation_only"
        ),
        training_config_name=f"{group_name}.yaml",
    )
    return run_root / "selected_replay_clean_vds"


def build_final_views(
    *,
    output_root: Path,
    parent_root: Path,
    strict_addition_ids: tuple[int, ...],
    strict_clean_dir: Path | None,
    partial_ids: tuple[int, ...],
    partial_clean_dir: Path | None,
) -> dict[str, Any]:
    """Build source-deduplicated strict and opt-in layered clean VDS views."""

    strict_sources = {
        episode_id: parent_root
        / "selected_replay_clean_vds"
        / f"episode_{episode_id}.hdf5"
        for episode_id in PARENT_SELECTED_EPISODE_IDS
    }
    strict_evidence = {
        episode_id: "strict_parent_selected_replay"
        for episode_id in PARENT_SELECTED_EPISODE_IDS
    }
    if strict_addition_ids:
        if strict_clean_dir is None:
            raise ValueError("Strict additions exist without a clean postprocess root.")
        for episode_id in strict_addition_ids:
            strict_sources[episode_id] = strict_clean_dir / f"episode_{episode_id}.hdf5"
            strict_evidence[episode_id] = "strict_salvage_addition"
    combined_dir = output_root / COMBINED_STRICT_VIEW
    if combined_dir.exists():
        combined = _validate_composite_view(
            combined_dir,
            expected_ids=tuple(sorted(strict_sources)),
            view_kind=COMBINED_STRICT_VIEW,
        )
    else:
        combined = build_composite_clean_vds(
            output_dir=combined_dir,
            source_by_episode=strict_sources,
            evidence_by_episode=strict_evidence,
            view_kind=COMBINED_STRICT_VIEW,
        )

    layered_sources = dict(strict_sources)
    layered_evidence = dict(strict_evidence)
    if partial_ids:
        if partial_clean_dir is None:
            raise ValueError("Partial salvage exists without a clean postprocess root.")
        for episode_id in partial_ids:
            if episode_id in layered_sources:
                raise ValueError(f"Partial source duplicates strict source {episode_id}.")
            layered_sources[episode_id] = partial_clean_dir / f"episode_{episode_id}.hdf5"
            layered_evidence[episode_id] = "partial_or_corrected_salvage_ablation"
    layered_dir = output_root / LAYERED_SALVAGE_VIEW
    if layered_dir.exists():
        layered = _validate_composite_view(
            layered_dir,
            expected_ids=tuple(sorted(layered_sources)),
            view_kind=LAYERED_SALVAGE_VIEW,
        )
    else:
        layered = build_composite_clean_vds(
            output_dir=layered_dir,
            source_by_episode=layered_sources,
            evidence_by_episode=layered_evidence,
            view_kind=LAYERED_SALVAGE_VIEW,
        )
    return {"combined_strict": combined, "layered_salvage": layered}


def _validate_composite_view(
    path: Path,
    *,
    expected_ids: tuple[int, ...],
    view_kind: str,
) -> dict[str, Any]:
    manifest_path = path / "view_manifest.jsonl"
    lineage_path = path / "lineage.json"
    if not manifest_path.is_file() or not lineage_path.is_file():
        raise ValueError(f"Incomplete composite view blocks resume: {path}")
    rows = _read_jsonl(manifest_path)
    ids = tuple(sorted(_episode_number(str(row["source_episode_id"])) for row in rows))
    if ids != expected_ids:
        raise ValueError(f"Composite view resume inventory mismatch: {path}")
    lineage = _read_json(lineage_path)
    if lineage.get("view_kind") != view_kind:
        raise ValueError(f"Composite view kind mismatch: {path}")
    for episode_id in ids:
        wrapper = path / f"episode_{episode_id}.hdf5"
        with h5py.File(wrapper, "r") as handle:
            if int(handle["observations/env_state"].shape[1]) != 89:
                raise ValueError(f"Composite env-state contract mismatch: {wrapper}")
            if "v2/cycle" not in handle:
                raise ValueError(f"Composite cycle payload missing: {wrapper}")
    return {
        "schema": "terrain_replay_composite_view_summary_v1",
        "view_kind": view_kind,
        "output_dir": str(path.resolve()),
        "episode_ids": list(ids),
        "episode_count": len(ids),
        "manifest_path": str(manifest_path.resolve()),
    }


def _episode_number(value: str) -> int:
    return int(str(value).rsplit("_", 1)[1])


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


__all__ = [
    "build_final_views",
    "postprocess_selected_group",
    "summarize_partial_coverage",
]
