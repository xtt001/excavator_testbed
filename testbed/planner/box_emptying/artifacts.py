"""Released artifact contract for online hard-bottom box emptying."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testbed.eval.executed_cut_effect_corpus import CUT_SUPPORT_FIELDS

BOX_EMPTYING_ARTIFACT_MANIFEST_SCHEMA = (
    "box_emptying_effect_capability_manifest_v1"
)
PLANNED_EFFECT_CONTRACT_VERSION = "planned_cut_effect_v1"
CALIBRATION_ROUTE = "plan_to_executed_to_silver"
SUPPORT_FIELDS = CUT_SUPPORT_FIELDS


class BoxEmptyingArtifactContractError(RuntimeError):
    """Raised when an online artifact is absent, stale, or not released."""


@dataclass(frozen=True)
class BoxEmptyingArtifactManifest:
    manifest_path: Path
    planned_effect_artifact_path: Path
    silver_effect_artifact_path: Path
    act_freeze_bundle_path: Path
    capability_status: str
    support_envelope: Mapping[str, tuple[float, float]]
    raw: Mapping[str, Any]


def load_box_emptying_artifact_manifest(
    manifest_path: str | Path,
) -> BoxEmptyingArtifactManifest:
    """Load a released manifest; never infer a fallback artifact."""

    path = Path(manifest_path).expanduser().resolve()
    if not path.is_file():
        raise BoxEmptyingArtifactContractError(
            f"artifact_manifest_missing:{path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoxEmptyingArtifactContractError(
            f"artifact_manifest_unreadable:{path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise BoxEmptyingArtifactContractError("artifact_manifest_not_object")
    if payload.get("schema") != BOX_EMPTYING_ARTIFACT_MANIFEST_SCHEMA:
        raise BoxEmptyingArtifactContractError("artifact_manifest_schema_mismatch")
    if payload.get("status") != "released":
        raise BoxEmptyingArtifactContractError("artifact_manifest_not_released")
    if payload.get("planned_effect_contract") != PLANNED_EFFECT_CONTRACT_VERSION:
        raise BoxEmptyingArtifactContractError("planned_effect_contract_mismatch")
    if payload.get("calibration_route") != CALIBRATION_ROUTE:
        raise BoxEmptyingArtifactContractError("calibration_route_mismatch")

    planned = _require_mapping(payload, "planned_effect")
    if planned.get("held_out_reset_gate") != "passed":
        raise BoxEmptyingArtifactContractError("calibration_gate_not_passed")
    planned_path = _verified_artifact_path(path, planned, "planned_effect")
    try:
        planned_payload = json.loads(planned_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoxEmptyingArtifactContractError(
            "planned_effect_artifact_unreadable"
        ) from exc
    if not isinstance(planned_payload, Mapping):
        raise BoxEmptyingArtifactContractError(
            "planned_effect_artifact_not_object"
        )
    if planned_payload.get("status") != "present":
        raise BoxEmptyingArtifactContractError(
            "planned_effect_artifact_not_present"
        )
    if planned_payload.get("input_contract") != "planned_cut":
        raise BoxEmptyingArtifactContractError(
            "planned_effect_input_contract_mismatch"
        )

    silver_path = _verified_artifact_path(
        path,
        _require_mapping(payload, "silver_effect"),
        "silver_effect",
    )
    freeze_path = _verified_artifact_path(
        path,
        _require_mapping(payload, "act_freeze_bundle"),
        "act_freeze_bundle",
    )

    capability = _require_mapping(payload, "capability")
    capability_status = str(capability.get("status", ""))
    allowed_capability = {
        "rule_only_due_to_class_imbalance",
        "rule_and_ood_envelope",
        "learned_probability_gate_passed",
    }
    if capability_status not in allowed_capability:
        raise BoxEmptyingArtifactContractError("capability_status_invalid")
    if capability_status == "learned_probability_gate_passed":
        counts = _require_mapping(capability, "identifiability")
        if (
            int(counts.get("positive_count", -1)) < 20
            or int(counts.get("negative_count", -1)) < 20
            or int(counts.get("reset_group_count", -1)) < 3
        ):
            raise BoxEmptyingArtifactContractError(
                "capability_identifiability_gate_not_met"
            )
        _verified_artifact_path(path, capability, "capability")

    support = _require_mapping(payload, "support_envelope")
    if support.get("source") != "strict18_p01_p99":
        raise BoxEmptyingArtifactContractError("support_envelope_source_mismatch")
    fields = _require_mapping(support, "fields")
    normalized: dict[str, tuple[float, float]] = {}
    for name in SUPPORT_FIELDS:
        bounds = fields.get(name)
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            raise BoxEmptyingArtifactContractError(
                f"support_envelope_missing:{name}"
            )
        low, high = float(bounds[0]), float(bounds[1])
        if not (math.isfinite(low) and math.isfinite(high) and low <= high):
            raise BoxEmptyingArtifactContractError(
                f"support_envelope_invalid:{name}"
            )
        normalized[name] = (low, high)

    return BoxEmptyingArtifactManifest(
        manifest_path=path,
        planned_effect_artifact_path=planned_path,
        silver_effect_artifact_path=silver_path,
        act_freeze_bundle_path=freeze_path,
        capability_status=capability_status,
        support_envelope=normalized,
        raw=dict(payload),
    )


def _require_mapping(payload: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise BoxEmptyingArtifactContractError(f"{field}_missing_or_not_object")
    return value


def _verified_artifact_path(
    manifest_path: Path,
    descriptor: Mapping[str, Any],
    field: str,
) -> Path:
    raw_path = descriptor.get("artifact_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise BoxEmptyingArtifactContractError(f"{field}_path_missing")
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise BoxEmptyingArtifactContractError(f"{field}_missing:{candidate}")
    expected = descriptor.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise BoxEmptyingArtifactContractError(f"{field}_sha256_missing")
    actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual != expected:
        raise BoxEmptyingArtifactContractError(f"{field}_sha256_mismatch")
    return candidate


__all__ = [
    "BOX_EMPTYING_ARTIFACT_MANIFEST_SCHEMA",
    "BoxEmptyingArtifactContractError",
    "BoxEmptyingArtifactManifest",
    "load_box_emptying_artifact_manifest",
]
