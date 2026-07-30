"""Artifact-lineage validation for the bounded ACT causal experiment."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml


def validate_completed_schedule(
    schedule: list[dict[str, Any]],
    *,
    expected_schedule: Sequence[tuple[int, str]],
    condition_ids: Sequence[str],
    sha256_file: Callable[[Path], str],
) -> None:
    """Verify schedule order and every immutable config/source hash."""

    repeat_counts = {condition_id: 0 for condition_id in condition_ids}
    for slot_index, ((round_index, condition_id), item) in enumerate(
        zip(expected_schedule, schedule, strict=True),
        start=1,
    ):
        repeat_counts[condition_id] += 1
        expected_repeat_index = repeat_counts[condition_id]
        expected_repeat_id = (
            f"round{round_index:02d}_slot{slot_index:02d}_"
            f"{condition_id}_repeat{expected_repeat_index:02d}"
        )
        expected_fields = {
            "slot_index": slot_index,
            "round_index": round_index,
            "condition_id": condition_id,
            "repeat_index": expected_repeat_index,
            "repeat_id": expected_repeat_id,
        }
        for key, expected in expected_fields.items():
            if item.get(key) != expected:
                raise ValueError(
                    f"live matrix schedule mismatch at slot {slot_index}: "
                    f"{key}={item.get(key)!r}, expected {expected!r}"
                )
        for path_key, sha_key in (
            ("config_path", "config_sha256"),
            ("runtime_source_path", "runtime_source_sha256"),
        ):
            source = Path(str(item.get(path_key, ""))).resolve(strict=True)
            if sha256_file(source) != str(item.get(sha_key, "")):
                raise ValueError(
                    f"live matrix {path_key} SHA mismatch at slot "
                    f"{slot_index}"
                )


def validated_experiment_contract(
    manifest: dict[str, Any],
    *,
    camera_order: Sequence[str],
    temporal_contract: dict[str, Any],
    validate_base_config: Callable[[dict[str, Any]], None],
    sha256_file: Callable[[Path], str],
) -> dict[str, Any]:
    """Resolve and hash the config, four policies, stats, and Unity lineage."""

    base_path = Path(str(manifest.get("base_config_path", ""))).resolve(
        strict=True
    )
    base_sha = sha256_file(base_path)
    if base_sha != str(manifest.get("base_config_sha256", "")):
        raise ValueError("live matrix base config SHA mismatch")
    base = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    validate_base_config(base)
    manifest_camera_order = list(manifest.get("camera_order", []))
    if manifest_camera_order != list(camera_order):
        raise ValueError("live matrix manifest camera order mismatch")
    temporal = dict(manifest.get("temporal_aggregation", {}) or {})
    if temporal != temporal_contract:
        raise ValueError("live matrix manifest temporal contract mismatch")
    if (
        manifest.get("safety_enabled") is not True
        or manifest.get("carry_envelope_live_disable_allowed") is not False
    ):
        raise ValueError("live matrix manifest safety contract mismatch")

    policy = dict(base.get("policy", {}) or {})
    policy_artifacts: dict[str, dict[str, str]] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        checkpoint = Path(
            str(policy.get(f"{primitive}_ckpt_path", ""))
        ).resolve(strict=True)
        checkpoint_dir = Path(
            str(
                policy.get(
                    f"{primitive}_ckpt_dir",
                    checkpoint.parent,
                )
            )
        ).resolve(strict=True)
        stats = (checkpoint_dir / "dataset_stats.pkl").resolve(strict=True)
        policy_artifacts[primitive] = {
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": sha256_file(checkpoint),
            "stats_path": str(stats),
            "stats_sha256": sha256_file(stats),
        }
    metadata = dict(
        dict(base.get("eval", {}) or {}).get(
            "record_hdf5_metadata",
            {},
        )
        or {}
    )
    unity_lineage = {
        key: value
        for key, value in metadata.items()
        if str(key).startswith("unity_")
    }
    if not {"unity_scene_id", "unity_source_sha256"}.issubset(
        unity_lineage
    ):
        raise ValueError("live matrix Unity lineage is incomplete")
    plan_matrix = Path(
        str(manifest.get("plan_matrix_path", ""))
    ).resolve(strict=True)
    plan_matrix_sha = sha256_file(plan_matrix)
    if plan_matrix_sha != str(manifest.get("plan_matrix_sha256", "")):
        raise ValueError("live matrix plan-matrix SHA mismatch")
    return {
        "base_config_path": str(base_path),
        "base_config_sha256": base_sha,
        "camera_order": manifest_camera_order,
        "temporal_aggregation": temporal,
        "typed_safety_enabled": True,
        "carry_envelope_live_disable_allowed": False,
        "policy_artifacts": policy_artifacts,
        "unity_lineage": unity_lineage,
        "plan_matrix": {
            "path": str(plan_matrix),
            "sha256": plan_matrix_sha,
        },
    }


__all__ = [
    "validate_completed_schedule",
    "validated_experiment_contract",
]
