"""Strict-manifest orchestration for replay-derived executed-cut samples."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.executed_cut_effect_samples import (
    StableTerrainWindowConfig,
    build_executed_cut_silver_samples_from_hdf5,
)

CORPUS_SCHEMA = "executed_cut_silver_corpus_v1"
CUT_SUPPORT_FIELD_SOURCES = {
    "planned_depth_m": "actual_surface_penetration_peak_m",
    "cut_length_m": "length_m",
    "entry_x_m": "entry_x_m",
    "entry_z_m": "entry_z_m",
    "exit_x_m": "exit_x_m",
    "exit_z_m": "exit_z_m",
    "direction_x": "direction_x",
    "direction_z": "direction_z",
}
CUT_SUPPORT_FIELDS = tuple(CUT_SUPPORT_FIELD_SOURCES)
STRICT_REPLAY_EVIDENCE_KINDS = frozenset(
    {
        "strict_parent_selected_replay",
        "strict_salvage_addition",
    }
)


def load_strict_replay_manifest(
    source_root: str | Path,
    *,
    expected_episode_count: int | None = None,
) -> list[dict[str, Any]]:
    """Load a composite view manifest and reject every non-strict source row."""

    root = Path(source_root).resolve()
    manifest_path = root / "view_manifest.jsonl"
    rows: list[dict[str, Any]] = []
    seen_episode_ids: set[str] = set()
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, Mapping):
                raise ValueError(f"Manifest line {line_number} must be an object.")
            row = dict(parsed)
            if row.get("schema") != "terrain_replay_composite_episode_v1":
                raise ValueError(f"Manifest line {line_number} has an unknown schema.")
            evidence_kind = str(row.get("evidence_kind", ""))
            if evidence_kind not in STRICT_REPLAY_EVIDENCE_KINDS:
                raise ValueError(
                    f"Manifest line {line_number} is not strict: {evidence_kind!r}."
                )
            episode_id = str(row.get("source_episode_id", "")).strip()
            if not episode_id:
                raise ValueError(
                    f"Manifest line {line_number} lacks source_episode_id."
                )
            if episode_id in seen_episode_ids:
                raise ValueError(f"Duplicate strict episode_id: {episode_id!r}.")
            seen_episode_ids.add(episode_id)
            wrapper_path = Path(str(row.get("wrapper_path", ""))).resolve()
            if not wrapper_path.is_relative_to(root):
                raise ValueError(
                    f"Manifest wrapper escapes the strict source root: {wrapper_path}."
                )
            if not wrapper_path.is_file():
                raise ValueError(f"Manifest wrapper is missing: {wrapper_path}.")
            row["source_episode_id"] = episode_id
            row["wrapper_path"] = str(wrapper_path)
            rows.append(row)
    if not rows:
        raise ValueError("Strict replay manifest contains no episode rows.")
    if expected_episode_count is not None:
        if expected_episode_count <= 0:
            raise ValueError("expected_episode_count must be positive.")
        if len(rows) != expected_episode_count:
            raise ValueError(
                "Strict replay episode-count mismatch: "
                f"expected {expected_episode_count}, found {len(rows)}."
            )
    return sorted(rows, key=lambda row: str(row["source_episode_id"]))


def build_executed_cut_effect_corpus(
    source_root: str | Path,
    *,
    expected_episode_count: int | None = None,
    config: StableTerrainWindowConfig | None = None,
    effective_move_min_volume_m3: float | None = None,
) -> dict[str, Any]:
    """Extract a provenance-preserving corpus from strict wrappers only."""

    root = Path(source_root).resolve()
    manifest_rows = load_strict_replay_manifest(
        root,
        expected_episode_count=expected_episode_count,
    )
    records: list[dict[str, Any]] = []
    episode_results: list[dict[str, Any]] = []
    evidence_counts: Counter[str] = Counter()
    total_eligible = 0
    total_rejected = 0
    total_skipped = 0
    for manifest_row in manifest_rows:
        episode_id = str(manifest_row["source_episode_id"])
        evidence_kind = str(manifest_row["evidence_kind"])
        result = build_executed_cut_silver_samples_from_hdf5(
            Path(str(manifest_row["wrapper_path"])),
            episode_id=episode_id,
            config=config,
            effective_move_min_volume_m3=effective_move_min_volume_m3,
        )
        evidence_counts[evidence_kind] += 1
        total_eligible += int(result.get("eligible_cycle_count", 0))
        total_rejected += int(result.get("rejected_eligible_cycle_count", 0))
        total_skipped += int(result.get("skipped_ineligible_cycle_count", 0))
        for source_record in result.get("records", []):
            record = dict(source_record)
            record["strict_replay_evidence_kind"] = evidence_kind
            records.append(record)
        episode_results.append(
            {
                "episode_id": episode_id,
                "evidence_kind": evidence_kind,
                "wrapper_path": str(manifest_row["wrapper_path"]),
                "status": result.get("status"),
                "eligible_cycle_count": int(result.get("eligible_cycle_count", 0)),
                "record_count": int(result.get("record_count", 0)),
                "rejected_eligible_cycle_count": int(
                    result.get("rejected_eligible_cycle_count", 0)
                ),
                "skipped_ineligible_cycle_count": int(
                    result.get("skipped_ineligible_cycle_count", 0)
                ),
                "rejections": list(result.get("rejections", [])),
            }
        )
    if not records:
        status = "no_usable_samples"
    elif total_rejected:
        status = "partial"
    else:
        status = "present"
    explicit_effective_move_labels = [
        bool(record["capability_labels"]["effective_move"])
        for record in records
        if isinstance(record.get("capability_labels"), Mapping)
        and isinstance(
            record["capability_labels"].get("effective_move"),
            bool,
        )
    ]
    capability_model_status = (
        "eligible_for_grouped_classifier_evaluation"
        if len(set(explicit_effective_move_labels)) >= 2
        else "rule_only_due_to_class_imbalance"
    )
    return {
        "schema": CORPUS_SCHEMA,
        "source": "strict_replay_view_manifest",
        "status": status,
        "evidence_tier": "replay_derived_silver",
        "input_contract": "executed_cut",
        "strict_only": True,
        "partial_salvage_inclusion": False,
        "source_root": str(root),
        "source_manifest_path": str(root / "view_manifest.jsonl"),
        "expected_episode_count": expected_episode_count,
        "episode_count": len(manifest_rows),
        "strict_evidence_kind_counts": dict(sorted(evidence_counts.items())),
        "eligible_cycle_count": total_eligible,
        "record_count": len(records),
        "rejected_eligible_cycle_count": total_rejected,
        "skipped_ineligible_cycle_count": total_skipped,
        "effective_move_label_status": (
            "explicit_volume_threshold"
            if effective_move_min_volume_m3 is not None
            else "threshold_not_configured"
        ),
        "capability_model_status": capability_model_status,
        "strict_cut_support_envelope": _strict_cut_support_envelope(
            records,
            episode_count=len(manifest_rows),
        ),
        "explicit_effective_move_label_count": len(explicit_effective_move_labels),
        "episode_results": episode_results,
        "records": records,
    }


def _strict_cut_support_envelope(
    records: list[dict[str, Any]],
    *,
    episode_count: int,
) -> dict[str, Any]:
    fields: dict[str, list[float]] = {}
    for output_name, executed_name in CUT_SUPPORT_FIELD_SOURCES.items():
        values: list[float] = []
        for index, record in enumerate(records):
            executed = record.get("executed_cut")
            if not isinstance(executed, Mapping):
                raise ValueError(f"record {index} executed_cut must be an object")
            try:
                value = float(executed[executed_name])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"record {index} executed_cut.{executed_name} must be finite"
                ) from exc
            if not np.isfinite(value):
                raise ValueError(
                    f"record {index} executed_cut.{executed_name} must be finite"
                )
            values.append(value)
        low, high = np.quantile(np.asarray(values), [0.01, 0.99])
        fields[output_name] = [float(low), float(high)]
    return {
        "schema": "strict_cut_support_envelope_v1",
        "source": (
            "strict18_p01_p99"
            if int(episode_count) == 18
            else "strict_replay_p01_p99"
        ),
        "record_count": len(records),
        "quantiles": [0.01, 0.99],
        "fields": fields,
    }


def write_executed_cut_effect_corpus(
    corpus: Mapping[str, Any],
    *,
    records_jsonl_path: str | Path,
    manifest_json_path: str | Path,
) -> dict[str, Any]:
    """Write JSONL records and a compact manifest without overwriting evidence."""

    records_path = Path(records_jsonl_path)
    manifest_path = Path(manifest_json_path)
    existing = [str(path) for path in (records_path, manifest_path) if path.exists()]
    if existing:
        return {
            "schema": "executed_cut_silver_corpus_write_result_v1",
            "status": "output_path_already_exists",
            "existing_paths": existing,
        }
    records = corpus.get("records")
    if not isinstance(records, list):
        raise ValueError("corpus.records must be a list.")
    records_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    manifest = {key: value for key, value in corpus.items() if key != "records"}
    manifest["records_jsonl_path"] = str(records_path.resolve())
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "schema": "executed_cut_silver_corpus_write_result_v1",
        "status": "present",
        "record_count": len(records),
        "records_jsonl_path": str(records_path.resolve()),
        "manifest_json_path": str(manifest_path.resolve()),
    }


__all__ = [
    "CORPUS_SCHEMA",
    "CUT_SUPPORT_FIELDS",
    "CUT_SUPPORT_FIELD_SOURCES",
    "STRICT_REPLAY_EVIDENCE_KINDS",
    "build_executed_cut_effect_corpus",
    "load_strict_replay_manifest",
    "write_executed_cut_effect_corpus",
]
