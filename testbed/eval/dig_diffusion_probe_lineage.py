"""Formal input resolution for the non-promotable minimal DP probe."""

from __future__ import annotations

import hashlib
import json
import pickle
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.dig_goal_action_lineage import (
    IdentifiabilityLineage,
    resolve_identifiability_lineage,
)


@dataclass(frozen=True)
class ProbeFileIdentity:
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
class MinimalDPProbeLineage:
    base: IdentifiabilityLineage
    curriculum_artifact: ProbeFileIdentity
    rollout_windows: ProbeFileIdentity
    rollout_manifest: ProbeFileIdentity
    identifiability_decision: ProbeFileIdentity
    identifiability_summary: ProbeFileIdentity
    final_pair_metrics: ProbeFileIdentity
    camera_order: tuple[str, ...]
    low_dim_order: tuple[str, ...]
    train_source_episode_ids: tuple[int, ...]
    rollout_window_count: int
    variant_count: int
    identifiability_classification: str
    identifiability_training_allowed: bool
    norm_stats: dict[str, np.ndarray]
    action_p01: np.ndarray
    action_p99: np.ndarray
    act_reference_support_violation_rate: float

    def as_manifest(self) -> dict[str, Any]:
        return {
            "status": "complete",
            "base": self.base.as_manifest(),
            "files": {
                name: getattr(self, name).as_dict()
                for name in (
                    "curriculum_artifact",
                    "rollout_windows",
                    "rollout_manifest",
                    "identifiability_decision",
                    "identifiability_summary",
                    "final_pair_metrics",
                )
            },
            "camera_order": list(self.camera_order),
            "low_dim_order": list(self.low_dim_order),
            "train_source_episode_ids": list(self.train_source_episode_ids),
            "rollout_window_count": self.rollout_window_count,
            "variant_count": self.variant_count,
            "identifiability": {
                "classification": self.identifiability_classification,
                "training_allowed": self.identifiability_training_allowed,
            },
            "act_reference_support_violation_rate": (
                self.act_reference_support_violation_rate
            ),
        }


def resolve_minimal_dp_probe_lineage(
    *,
    dispatch_manifest_path: str | Path,
    identifiability_decision_path: str | Path,
) -> MinimalDPProbeLineage:
    base = resolve_identifiability_lineage(dispatch_manifest_path)
    dispatch_payload = _json(base.dispatch_manifest.path)
    files = _mapping(
        dispatch_payload["authoritative_lineage"]["files"],
        "dispatch authoritative files",
    )
    curriculum = _identity_from_record(
        files.get("curriculum_artifact"), "curriculum artifact"
    )
    curriculum_payload = _json(curriculum.path)
    if curriculum_payload.get("schema") != "dig_closed_loop_rollout_curriculum_v1":
        raise ValueError("minimal DP curriculum artifact schema mismatch")
    rollout = _identity_from_record(
        curriculum_payload.get("rollout_cache"), "rollout windows"
    )
    rollout_manifest_path = rollout.path.with_suffix(".json")
    rollout_manifest = _identity(rollout_manifest_path)
    rollout_payload = _json(rollout_manifest.path)
    if rollout_payload.get("schema") != "dig_joint_rollout_windows_v1":
        raise ValueError("minimal DP rollout manifest schema mismatch")
    if bool(rollout_payload.get("window_random_split")):
        raise ValueError("minimal DP cannot use random window splits")
    sources = tuple(int(value) for value in rollout_payload["source_episode_ids"])
    if set(sources) != set(base.train_source_episode_ids) or set(sources) & {33, 34}:
        raise ValueError("minimal DP rollout source contract mismatch")
    decision_path = (
        Path(identifiability_decision_path).expanduser().resolve(strict=True)
    )
    ident_decision = _identity(decision_path)
    ident_payload = _json(decision_path)
    classification = str(ident_payload.get("classification", ""))
    training_allowed = bool(ident_payload.get("act_dp_training_allowed"))
    if classification != "data_supervision_unidentifiable" or training_allowed:
        raise ValueError("minimal DP probe requires the frozen failed data precheck")
    ident_summary = _identity(decision_path.parent / "summary.json")
    pair_metrics = _identity(base.dispatch_manifest.path.parent / "pair_metrics.json")
    pair_payload = _json(pair_metrics.path)
    act_support = float(
        pair_payload["horizon_10"]["latest"]["action_support_violation_rate"]
    )
    with base.stats.path.open("rb") as handle:
        stats_payload = pickle.load(handle)
    stats = {
        name: np.asarray(stats_payload[name], dtype=np.float32)
        for name in ("proprio_mean", "proprio_std", "action_mean", "action_std")
    }
    if (
        stats["proprio_mean"].shape != (18,)
        or stats["proprio_std"].shape != (18,)
        or stats["action_mean"].shape != (4,)
        or stats["action_std"].shape != (4,)
    ):
        raise ValueError("minimal DP normalization contract mismatch")
    return MinimalDPProbeLineage(
        base=base,
        curriculum_artifact=curriculum,
        rollout_windows=rollout,
        rollout_manifest=rollout_manifest,
        identifiability_decision=ident_decision,
        identifiability_summary=ident_summary,
        final_pair_metrics=pair_metrics,
        camera_order=base.camera_order,
        low_dim_order=base.low_dim_order,
        train_source_episode_ids=sources,
        rollout_window_count=int(rollout_payload["window_count"]),
        variant_count=base.variant_count,
        identifiability_classification=classification,
        identifiability_training_allowed=training_allowed,
        norm_stats=stats,
        action_p01=base.action_p01,
        action_p99=base.action_p99,
        act_reference_support_violation_rate=act_support,
    )


def _identity_from_record(value: Any, label: str) -> ProbeFileIdentity:
    record = _mapping(value, label)
    path = Path(str(record["path"])).expanduser().resolve(strict=True)
    identity = _identity(path)
    if identity.sha256 != str(record.get("sha256")):
        raise ValueError(f"{label} SHA mismatch")
    if "size_bytes" in record and identity.size_bytes != int(record["size_bytes"]):
        raise ValueError(f"{label} size mismatch")
    return identity


def _identity(path: Path) -> ProbeFileIdentity:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return ProbeFileIdentity(path, digest.hexdigest(), path.stat().st_size)


def _json(path: Path) -> dict[str, Any]:
    return dict(_mapping(json.loads(path.read_text(encoding="utf-8")), str(path)))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


__all__ = [
    "MinimalDPProbeLineage",
    "ProbeFileIdentity",
    "resolve_minimal_dp_probe_lineage",
]
