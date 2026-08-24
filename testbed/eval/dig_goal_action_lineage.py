"""Resolve precheck inputs from the final frozen Dig dispatch manifest."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


class IdentifiabilityLineageError(ValueError):
    """Raised when the data-identifiability input chain is incomplete."""


@dataclass(frozen=True)
class LockedFile:
    path: Path
    sha256: str
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class IdentifiabilityLineage:
    dispatch_manifest: LockedFile
    dispatch_decision: LockedFile
    variants: LockedFile
    split: LockedFile
    stats: LockedFile
    support: LockedFile
    checkpoint: LockedFile
    source_variant_inventory: LockedFile
    dataset_dir: Path
    low_dim_order: tuple[str, ...]
    camera_order: tuple[str, ...]
    token_order: tuple[str, ...]
    support_p01: np.ndarray
    support_p99: np.ndarray
    action_p01: np.ndarray
    action_p99: np.ndarray
    action_std: np.ndarray
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    variant_count: int
    state_lineage_sha256: str
    python_head: str
    python_dirty: bool
    dispatch_decision_classification: str

    def as_manifest(self) -> dict[str, Any]:
        return {
            "status": "complete",
            "files": {
                name: getattr(self, name).as_dict()
                for name in (
                    "dispatch_manifest",
                    "dispatch_decision",
                    "variants",
                    "split",
                    "stats",
                    "support",
                    "checkpoint",
                    "source_variant_inventory",
                )
            },
            "dataset_dir": str(self.dataset_dir),
            "orders": {
                "low_dim": list(self.low_dim_order),
                "camera": list(self.camera_order),
                "token": list(self.token_order),
            },
            "support": {
                "p01": self.support_p01.tolist(),
                "p99": self.support_p99.tolist(),
                "action_p01": self.action_p01.tolist(),
                "action_p99": self.action_p99.tolist(),
                "action_std": self.action_std.tolist(),
            },
            "sources": {
                "train": list(self.train_source_episode_ids),
                "historical_validation_not_used": list(
                    self.validation_source_episode_ids
                ),
            },
            "variant_count": self.variant_count,
            "state_lineage_sha256": self.state_lineage_sha256,
            "python": {
                "head": self.python_head,
                "dirty": self.python_dirty,
            },
            "dispatch_decision_classification": self.dispatch_decision_classification,
        }


def require_complete_identifiability_lineage(value: Mapping[str, Any]) -> None:
    for key in ("dispatch_manifest", "variants", "split", "support"):
        record = value.get(key)
        if not isinstance(record, Mapping):
            raise IdentifiabilityLineageError(f"{key}_missing")
        if not str(record.get("path", "")) or not _is_sha256(record.get("sha256")):
            raise IdentifiabilityLineageError(f"{key}_invalid")
    for key, length in (
        ("low_dim_order", 3),
        ("camera_order", 4),
        ("token_order", 10),
    ):
        order = value.get(key)
        if (
            not isinstance(order, Sequence)
            or isinstance(order, (str, bytes))
            or len(order) != length
            or any(not str(item) for item in order)
        ):
            raise IdentifiabilityLineageError(f"{key}_missing")


def resolve_identifiability_lineage(
    dispatch_manifest_path: str | Path,
) -> IdentifiabilityLineage:
    manifest_path = Path(dispatch_manifest_path).expanduser().resolve(strict=True)
    manifest_identity = _identity(manifest_path)
    payload = _json(manifest_path)
    if payload.get("schema") != "dig_act_receding_horizon_dispatch_input_manifest_v1":
        raise IdentifiabilityLineageError("dispatch_manifest_schema_mismatch")
    if payload.get("status") != "completed":
        raise IdentifiabilityLineageError("dispatch_manifest_status_invalid")
    decision_path = manifest_path.parent / "decision.json"
    decision_identity = _identity(decision_path)
    decision = _json(decision_path)
    classification = str(decision.get("classification", ""))
    if classification != "temporal_dispatch_not_primary":
        raise IdentifiabilityLineageError(
            "dispatch_precondition_classification_mismatch"
        )

    variants = _identity_from_record(payload.get("selected_variants"), "variants")
    variant_count = sum(
        1 for line in variants.path.open(encoding="utf-8") if line.strip()
    )
    if variant_count != 112 or int(payload.get("selected_variant_count", -1)) != 112:
        raise IdentifiabilityLineageError("selected_variant_count_mismatch")
    authoritative = _mapping(
        payload.get("authoritative_lineage"), "authoritative lineage"
    )
    files = _mapping(authoritative.get("files"), "authoritative files")
    split = _identity_from_record(files.get("split"), "split")
    stats = _identity_from_record(files.get("stats"), "stats")
    support = _identity_from_record(files.get("support"), "support")
    checkpoint = _identity_from_record(
        files.get("checkpoint"), "checkpoint", hash_content=False
    )
    source_variants = _identity_from_record(
        files.get("variant_jsonl"), "source variant inventory"
    )
    dataset_dir = Path(str(authoritative.get("dataset_dir", ""))).resolve(strict=True)
    orders = _mapping(authoritative.get("orders"), "authoritative orders")
    low_dim_order = tuple(str(value) for value in orders.get("low_dim", ()))
    camera_order = tuple(str(value) for value in orders.get("camera", ()))
    token_order = tuple(str(value) for value in orders.get("token", ()))
    if low_dim_order != ("qpos", "qvel", "dig_cut_tokens"):
        raise IdentifiabilityLineageError("low_dim_order_mismatch")
    if len(camera_order) != 4 or len(set(camera_order)) != 4:
        raise IdentifiabilityLineageError("camera_order_invalid")
    if len(token_order) != 10 or len(set(token_order)) != 10:
        raise IdentifiabilityLineageError("token_order_invalid")
    support_values = _mapping(authoritative.get("support"), "support values")
    support_p01 = _vector(support_values.get("p01"), 18, "support p01")
    support_p99 = _vector(support_values.get("p99"), 18, "support p99")
    action_p01 = _vector(support_values.get("action_p01"), 4, "action p01")
    action_p99 = _vector(support_values.get("action_p99"), 4, "action p99")
    if np.any(support_p01 > support_p99) or np.any(action_p01 > action_p99):
        raise IdentifiabilityLineageError("support_bounds_invalid")
    collection = _mapping(payload.get("collection"), "dispatch collection")
    policy = _mapping(collection.get("policy"), "dispatch policy")
    baseline_policy = _mapping(policy.get("baseline"), "baseline policy")
    action_std = _vector(baseline_policy.get("action_std"), 4, "action std")
    if np.any(action_std <= 0.0):
        raise IdentifiabilityLineageError("action_std_invalid")
    sources = _mapping(authoritative.get("sources"), "source contract")
    train_sources = tuple(int(value) for value in sources.get("strict_train", ()))
    validation_sources = tuple(
        int(value) for value in sources.get("historical_validation_not_used", ())
    )
    if set(validation_sources) != {33, 34} or set(train_sources) & {33, 34}:
        raise IdentifiabilityLineageError("source_33_34_contract_invalid")
    runtime = _mapping(payload.get("runtime"), "dispatch runtime")
    git = _mapping(runtime.get("git"), "dispatch git")
    state_sha = str(payload.get("state_lineage_sha256", ""))
    if not _is_sha256(state_sha):
        raise IdentifiabilityLineageError("state_lineage_sha256_missing")
    return IdentifiabilityLineage(
        dispatch_manifest=manifest_identity,
        dispatch_decision=decision_identity,
        variants=variants,
        split=split,
        stats=stats,
        support=support,
        checkpoint=checkpoint,
        source_variant_inventory=source_variants,
        dataset_dir=dataset_dir,
        low_dim_order=low_dim_order,
        camera_order=camera_order,
        token_order=token_order,
        support_p01=support_p01,
        support_p99=support_p99,
        action_p01=action_p01,
        action_p99=action_p99,
        action_std=action_std,
        train_source_episode_ids=train_sources,
        validation_source_episode_ids=validation_sources,
        variant_count=variant_count,
        state_lineage_sha256=state_sha,
        python_head=str(git.get("head", "")),
        python_dirty=bool(git.get("dirty")),
        dispatch_decision_classification=classification,
    )


def _identity_from_record(
    value: Any, label: str, *, hash_content: bool = True
) -> LockedFile:
    record = _mapping(value, label)
    path = Path(str(record.get("path", ""))).expanduser().resolve(strict=True)
    expected_sha = str(record.get("sha256", ""))
    if not _is_sha256(expected_sha):
        raise IdentifiabilityLineageError(f"{label}_sha256_missing")
    if hash_content:
        actual = _identity(path)
        if actual.sha256 != expected_sha:
            raise IdentifiabilityLineageError(f"{label}_sha256_mismatch")
    else:
        actual = LockedFile(path, expected_sha, path.stat().st_size)
    if int(record.get("size_bytes", -1)) != actual.size_bytes:
        raise IdentifiabilityLineageError(f"{label}_size_mismatch")
    return actual


def _identity(path: Path) -> LockedFile:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return LockedFile(path, digest.hexdigest(), path.stat().st_size)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, str(path)))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IdentifiabilityLineageError(f"{label}_missing")
    return value


def _vector(value: Any, length: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).reshape(-1)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise IdentifiabilityLineageError(f"{label}_invalid")
    return result


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


__all__ = [
    "IdentifiabilityLineage",
    "IdentifiabilityLineageError",
    "LockedFile",
    "require_complete_identifiability_lineage",
    "resolve_identifiability_lineage",
]
