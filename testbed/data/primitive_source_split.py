"""Deterministic primitive train/validation splits by replay source identity."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.data.primitives_v2_2 import PRIMITIVE_NAMES


def write_primitive_source_splits(
    *,
    primitive_root: str | Path,
    output_dir: str | Path,
    train_source_episode_ids: Sequence[int],
    val_source_episode_ids: Sequence[int],
    required_training_tier: str | None = "gold",
) -> dict[str, Path]:
    """Partition every primitive episode by immutable replay source identity.

    The union of train and validation source ids is an exact allowlist for the
    primitive window manifest. A replay source therefore cannot leak between
    train and validation even though each source emits many primitive windows.
    """

    root = Path(primitive_root).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().resolve()
    train_sources = _normalise_source_ids(
        train_source_episode_ids,
        label="train source ids",
    )
    val_sources = _normalise_source_ids(
        val_source_episode_ids,
        label="validation source ids",
    )
    overlap = sorted(set(train_sources) & set(val_sources))
    if overlap:
        raise ValueError(
            "Train and validation source identities overlap: "
            + ", ".join(f"episode_{value}" for value in overlap)
        )
    allowed_sources = tuple(sorted((*train_sources, *val_sources)))
    training_tier = (
        None
        if required_training_tier is None
        else str(required_training_tier).strip()
    )
    if required_training_tier is not None and not training_tier:
        raise ValueError("Required training tier must not be empty.")

    manifest_path = root / "window_manifest.json"
    rows = _read_window_manifest(manifest_path)
    entries_by_primitive: dict[str, list[tuple[int, int, str]]] = {
        name: [] for name in PRIMITIVE_NAMES
    }
    observed_sources: set[int] = set()
    for row in rows:
        primitive_name = str(row.get("primitive_name", ""))
        if primitive_name not in entries_by_primitive:
            raise ValueError(
                f"Unexpected primitive name in window manifest: {primitive_name!r}"
            )
        primitive_episode_id = _parse_nonnegative_int(
            row.get("primitive_episode_id"),
            label="primitive_episode_id",
        )
        source_episode_id = _parse_source_episode_id(row.get("source_episode_id"))
        row_training_tier = str(row.get("training_tier", "")).strip()
        if training_tier is not None and not row_training_tier:
            raise ValueError(
                "Primitive window manifest is missing training_tier for "
                f"{primitive_name} episode_{primitive_episode_id}."
            )
        entries_by_primitive[primitive_name].append(
            (primitive_episode_id, source_episode_id, row_training_tier)
        )
        observed_sources.add(source_episode_id)

    if tuple(sorted(observed_sources)) != allowed_sources:
        raise ValueError(
            "Primitive manifest source identities must exactly match the split "
            f"allowlist: observed={sorted(observed_sources)}, "
            f"allowed={list(allowed_sources)}."
        )

    payloads: dict[str, dict[str, Any]] = {}
    train_source_set = set(train_sources)
    val_source_set = set(val_sources)
    for primitive_name in PRIMITIVE_NAMES:
        entries = sorted(entries_by_primitive[primitive_name])
        if not entries:
            raise ValueError(
                f"Primitive manifest has no windows for {primitive_name!r}."
            )
        all_episode_ids = [episode_id for episode_id, _, _ in entries]
        if len(all_episode_ids) != len(set(all_episode_ids)):
            raise ValueError(
                f"Primitive manifest repeats {primitive_name} primitive episode ids."
            )
        dataset_dir = root / primitive_name
        discovered = sorted(
            int(path.stem.removeprefix("episode_"))
            for path in dataset_dir.glob("episode_*.hdf5")
        )
        if discovered != all_episode_ids:
            raise ValueError(
                f"{primitive_name} manifest/file inventory mismatch: "
                f"manifest={all_episode_ids}, files={discovered}."
            )
        selected_entries = [
            (episode_id, source_episode_id)
            for episode_id, source_episode_id, row_training_tier in entries
            if training_tier is None or row_training_tier == training_tier
        ]
        episode_ids = [episode_id for episode_id, _ in selected_entries]
        source_by_episode = dict(selected_entries)
        train_ids = [
            episode_id
            for episode_id in episode_ids
            if source_by_episode[episode_id] in train_source_set
        ]
        val_ids = [
            episode_id
            for episode_id in episode_ids
            if source_by_episode[episode_id] in val_source_set
        ]
        if not train_ids or not val_ids:
            raise ValueError(
                f"{primitive_name} source-aware split must have non-empty train and val."
            )
        if set(train_ids) & set(val_ids):
            raise AssertionError(f"{primitive_name} source-aware split leaked episodes.")
        if sorted((*train_ids, *val_ids)) != episode_ids:
            raise AssertionError(
                f"{primitive_name} source-aware split did not cover every episode."
            )
        payloads[primitive_name] = {
            "schema_version": 1,
            "split_policy": "source_identity_exact_allowlist_v1",
            "dataset_dir": str(dataset_dir),
            "available_episode_ids": episode_ids,
            "train_ids": train_ids,
            "val_ids": val_ids,
            "train_source_episode_ids": list(train_sources),
            "val_source_episode_ids": list(val_sources),
            "allowed_source_episode_ids": list(allowed_sources),
            "required_training_tier": training_tier,
            "excluded_training_tier_episode_ids": sorted(
                set(all_episode_ids) - set(episode_ids)
            ),
            "source_episode_id_by_primitive_episode_id": source_by_episode,
            "window_manifest_path": str(manifest_path),
        }

    rendered = {
        primitive_name: yaml.safe_dump(payload, sort_keys=False)
        for primitive_name, payload in payloads.items()
    }
    paths = {
        primitive_name: output / f"{primitive_name}_source_split.yaml"
        for primitive_name in PRIMITIVE_NAMES
    }
    for primitive_name, path in paths.items():
        if path.exists() and path.read_text(encoding="utf-8") != rendered[primitive_name]:
            raise ValueError(f"Existing primitive split content mismatch: {path}")
    output.mkdir(parents=True, exist_ok=True)
    for primitive_name, path in paths.items():
        if not path.exists():
            path.write_text(rendered[primitive_name], encoding="utf-8")
    return {name: path.resolve() for name, path in paths.items()}


def _read_window_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Primitive window manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError(f"Primitive window manifest must be a non-empty list: {path}")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"Primitive window manifest row {index} is not a mapping.")
        rows.append(dict(row))
    return rows


def _normalise_source_ids(values: Sequence[int], *, label: str) -> tuple[int, ...]:
    normalised = tuple(sorted(set(_parse_nonnegative_int(value, label=label) for value in values)))
    if not normalised:
        raise ValueError(f"{label} must not be empty.")
    return normalised


def _parse_source_episode_id(value: Any) -> int:
    text = str(value)
    if text.startswith("episode_"):
        text = text[len("episode_") :]
    return _parse_nonnegative_int(text, label="source_episode_id")


def _parse_nonnegative_int(value: Any, *, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{label} must be non-negative: {value!r}")
    return parsed


__all__ = ["write_primitive_source_splits"]
