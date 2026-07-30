"""Build source-identity-safe VDS and training views for replay salvage."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.terrain_replay_postprocess import ACTION_LOSS_MASK_SCOPE
from testbed.data.vds import STORAGE_MODE_VDS, write_lineage_json, write_vds_episode
from testbed.eval.terrain_replay_salvage import (
    PARENT_SELECTED_EPISODE_IDS,
    SALVAGE_EPISODE_IDS,
)

COMBINED_STRICT_VIEW = "combined_strict_clean_vds"
LAYERED_SALVAGE_VIEW = "layered_salvage_clean_vds"
COMPOSITE_VIEW_KINDS = (COMBINED_STRICT_VIEW, LAYERED_SALVAGE_VIEW)
VALIDATION_EPISODE_IDS = (33, 34)
FIXED_SOURCE_EPISODE_IDS = tuple(
    sorted((*PARENT_SELECTED_EPISODE_IDS, *SALVAGE_EPISODE_IDS))
)


def build_composite_clean_vds(
    *,
    output_dir: str | Path,
    source_by_episode: Mapping[int, str | Path],
    evidence_by_episode: Mapping[int, str],
    view_kind: str,
) -> dict[str, Any]:
    """Create one thin cross-root clean view with exactly one path per source id."""

    view = str(view_kind)
    if view not in COMPOSITE_VIEW_KINDS:
        raise ValueError(f"Unknown composite replay view: {view!r}")
    output = Path(output_dir).expanduser()
    if output.exists():
        raise FileExistsError(f"Composite view is no-overwrite: {output}")
    sources = {
        int(key): Path(value).expanduser().resolve(strict=True)
        for key, value in source_by_episode.items()
    }
    evidence = {int(key): str(value) for key, value in evidence_by_episode.items()}
    if not sources:
        raise ValueError("Composite replay view requires at least one source episode.")
    if set(sources) != set(evidence):
        raise ValueError("Composite source and evidence inventories must match exactly.")
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Composite temporary view already exists: {temporary}")
    temporary.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    source_roots: set[Path] = set()
    for episode_id in sorted(sources):
        source = sources[episode_id]
        if source.name != f"episode_{episode_id}.hdf5":
            raise ValueError(
                f"Composite source filename does not match episode_{episode_id}: {source}"
            )
        source_roots.add(source.parent)
        with h5py.File(source, "r") as handle:
            step_count = int(handle["action"].shape[0])
            metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
            cycle_group = handle.get("v2/cycle")
            if cycle_group is None:
                raise KeyError(f"Composite clean source has no /v2/cycle: {source}")
            cycle_payload = {
                str(name): np.asarray(dataset[()])
                for name, dataset in cycle_group.items()
            }
        metadata.update(
            {
                "composite_view_kind": view,
                "composite_evidence_kind": evidence[episode_id],
                "composite_source_realpath": str(source),
                "source_episode_id": f"episode_{episode_id}",
                "source_identity_policy": "one_source_one_replay_identity",
                "gold_status": "not_gold",
            }
        )
        target = temporary / f"episode_{episode_id}.hdf5"
        if target.exists():
            raise FileExistsError(f"Composite wrapper is no-overwrite: {target}")
        write_vds_episode(
            target,
            source_path=source,
            crop=slice(0, step_count),
            metadata=metadata,
            v2_cycle_payload=cycle_payload,
        )
        rows.append(
            {
                "schema": "terrain_replay_composite_episode_v1",
                "source_episode_id": f"episode_{episode_id}",
                "source_path": str(source),
                "wrapper_path": str((output / target.name).resolve()),
                "step_count": step_count,
                "evidence_kind": evidence[episode_id],
                "gold_status": "not_gold",
            }
        )
    write_lineage_json(
        temporary,
        builder="tb-salvage-terrain-replay-dataset:composite_clean_vds",
        storage_mode=STORAGE_MODE_VDS,
        source_roots=sorted(source_roots),
        input_dataset_ids=[path.name for path in sorted(source_roots)],
        schema_versions={"composite_replay_view": "v1"},
        extra={
            "view_kind": view,
            "source_identity_policy": "one_source_one_replay_identity",
            "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
            "default_enabled": False,
            "gold_status": "not_gold",
        },
    )
    lineage_path = temporary / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["output_root"] = str(output)
    lineage_path.write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(temporary / "view_manifest.jsonl", rows)
    temporary.replace(output)
    return {
        "schema": "terrain_replay_composite_view_summary_v1",
        "view_kind": view,
        "output_dir": str(output.resolve()),
        "episode_ids": sorted(sources),
        "episode_count": len(sources),
        "manifest_path": str((output / "view_manifest.jsonl").resolve()),
    }


def rebuild_strict_composite_clean_vds(
    *,
    source_view_dir: str | Path,
    output_dir: str | Path,
    strict_episode_ids: Sequence[int],
) -> dict[str, Any]:
    """Rebuild one strict view only when its manifest matches the allowlist.

    The manifest's immutable source episodes are used instead of wrapping the
    existing composite wrappers again. This both repairs legacy text encoding
    and keeps the rebuilt VDS dependency chain as short as possible.
    """

    source_view = Path(source_view_dir).expanduser().resolve(strict=True)
    manifest_path = source_view / "view_manifest.jsonl"
    rows = _read_jsonl(manifest_path)
    if not rows:
        raise ValueError(f"Strict source view manifest is empty: {manifest_path}")
    allowed = tuple(sorted(set(int(value) for value in strict_episode_ids)))
    if not allowed:
        raise ValueError("Strict source identity allowlist must not be empty.")

    source_by_episode: dict[int, Path] = {}
    evidence_by_episode: dict[int, str] = {}
    for row in rows:
        episode_id = _parse_source_episode_id(row.get("source_episode_id"))
        if episode_id in source_by_episode:
            raise ValueError(
                f"Strict source view repeats source identity episode_{episode_id}."
            )
        evidence_kind = str(row.get("evidence_kind", ""))
        if not evidence_kind.startswith("strict_"):
            raise ValueError(
                "Strict rebuild rejects non-strict manifest evidence: "
                f"episode_{episode_id}={evidence_kind!r}."
            )
        source_by_episode[episode_id] = Path(str(row["source_path"]))
        evidence_by_episode[episode_id] = evidence_kind

    observed = tuple(sorted(source_by_episode))
    if observed != allowed:
        raise ValueError(
            "Strict source identities must exactly match the strict allowlist: "
            f"observed={list(observed)}, allowed={list(allowed)}."
        )

    report = build_composite_clean_vds(
        output_dir=output_dir,
        source_by_episode=source_by_episode,
        evidence_by_episode=evidence_by_episode,
        view_kind=COMBINED_STRICT_VIEW,
    )
    lineage_path = Path(output_dir).expanduser().resolve() / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage.update(
        {
            "strict_source_episode_ids": list(allowed),
            "source_view_dir": str(source_view),
            "text_encoding_repair": "canonical_nested_bytes_literal_decode_v1",
        }
    )
    lineage_path.write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def write_salvage_training_configs(
    *,
    output_root: str | Path,
    combined_strict_dir: str | Path,
    layered_salvage_dir: str | Path,
    strict_episode_ids: Sequence[int],
    layered_episode_ids: Sequence[int],
) -> dict[str, Path]:
    """Write completely separate strict and opt-in salvage training configs."""

    output = Path(output_root).expanduser()
    config_dir = output / "training_configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    strict_ids = tuple(sorted(set(int(value) for value in strict_episode_ids)))
    layered_ids = tuple(sorted(set(int(value) for value in layered_episode_ids)))
    if not set(strict_ids).issubset(FIXED_SOURCE_EPISODE_IDS):
        raise ValueError("Strict training inventory escapes the fixed 24 sources.")
    if not set(layered_ids).issubset(FIXED_SOURCE_EPISODE_IDS):
        raise ValueError("Layered training inventory escapes the fixed 24 sources.")
    if not set(strict_ids).issubset(layered_ids):
        raise ValueError("Layered inventory must contain every strict source identity.")
    strict_complete = strict_ids == FIXED_SOURCE_EPISODE_IDS
    strict_path = config_dir / "combined_strict_replay_22train_2val.yaml"
    salvage_path = config_dir / "layered_salvage_ablation.yaml"
    _write_yaml(
        strict_path,
        _training_payload(
            dataset_dir=Path(combined_strict_dir),
            episode_ids=strict_ids,
            usage="strict_replay_training_candidate",
            default_enabled=strict_complete,
            evidence_kind="replay_derived_selected_pass",
        ),
    )
    _write_yaml(
        salvage_path,
        _training_payload(
            dataset_dir=Path(layered_salvage_dir),
            episode_ids=layered_ids,
            usage="partial_replay_salvage_ablation_only",
            default_enabled=False,
            evidence_kind="layered_strict_and_partial_replay_salvage",
        ),
    )
    return {"strict": strict_path.resolve(), "salvage": salvage_path.resolve()}


def _training_payload(
    *,
    dataset_dir: Path,
    episode_ids: tuple[int, ...],
    usage: str,
    default_enabled: bool,
    evidence_kind: str,
) -> dict[str, Any]:
    val_set = set(VALIDATION_EPISODE_IDS)
    return {
        "schema": "terrain_replay_salvage_training_view_v1",
        "usage": usage,
        "default_enabled": bool(default_enabled),
        "dataset_dir": str(dataset_dir.expanduser().resolve()),
        "source_identity_policy": "one_source_one_replay_identity",
        "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
        "train_ids": [value for value in episode_ids if value not in val_set],
        "val_ids": [value for value in VALIDATION_EPISODE_IDS if value in set(episode_ids)],
        "expected_val_ids": list(VALIDATION_EPISODE_IDS),
        "episode_ids": list(episode_ids),
        "missing_episode_ids": sorted(set(FIXED_SOURCE_EPISODE_IDS) - set(episode_ids)),
        "evidence_kind": evidence_kind,
        "repeatability_status": "not_assessed_single_attempt",
        "gold_status": "not_gold",
    }


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    content = "\n".join(
        json.dumps(dict(row), sort_keys=True, allow_nan=False) for row in rows
    )
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Composite view manifest does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(
                f"Composite view manifest row {line_number} is not a mapping: {path}"
            )
        rows.append(dict(value))
    return rows


def _parse_source_episode_id(value: Any) -> int:
    text = str(value)
    if text.startswith("episode_"):
        text = text[len("episode_") :]
    try:
        episode_id = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid source episode identity: {value!r}") from exc
    if episode_id < 0:
        raise ValueError(f"Source episode identity must be non-negative: {value!r}")
    return episode_id


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    content = yaml.safe_dump(dict(payload), sort_keys=False)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Resume training config content mismatch: {path}")
        return
    path.write_text(content, encoding="utf-8")


__all__ = [
    "COMBINED_STRICT_VIEW",
    "LAYERED_SALVAGE_VIEW",
    "build_composite_clean_vds",
    "rebuild_strict_composite_clean_vds",
    "write_salvage_training_configs",
]
