"""Current Unity contact-code lock rooted in a frozen source manifest."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from testbed.eval.unity_contact_observe_only_report import (
    UnityContactObserveOnlyReportError,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    artifact_refs_aggregate_sha256,
    load_json,
)
from testbed.eval.wall_contact_rollout_integrity import required_file

_ALLOWED_PARENT_CONTACT_CODE_DRIFT = {
    "BucketContactForceMonitor.cs",
    "AgxSimStepAckServer.cs",
}
_REQUIRED_CURRENT_CONTACT_CODE = {
    *_ALLOWED_PARENT_CONTACT_CODE_DRIFT,
    "AgxSimJpegCameraCapture.cs",
    "WorktoolFactoryFloorContactDetail.cs",
}
_ADDITIONAL_CONTACT_CODE_SIBLINGS = {
    "AgxSimJpegCameraCapture.cs": "AgxSimStepAckServer.cs",
    "WorktoolFactoryFloorContactDetail.cs": "BucketContactForceMonitor.cs",
}


def lock_unity_contact_environment(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Lock current contact code while preserving frozen scene/norm lineage."""

    manifest = load_json(required_file(manifest_path, "environment_manifest"))
    source_lock = _mapping(
        manifest.get("source_lock"),
        "environment.source_lock",
    )
    unity = _mapping(source_lock.get("unity"), "environment.unity")
    scene = _locked_frozen_file(
        unity,
        path_key="scene_path",
        sha_key="scene_sha256",
        label="scene",
    )
    normalization = _locked_frozen_file(
        unity,
        path_key="normalization_path",
        sha_key="normalization_sha256",
        label="normalization",
    )
    raw_files = unity.get("contact_lineage_files")
    if not isinstance(raw_files, list) or not raw_files:
        raise UnityContactObserveOnlyReportError(
            "environment_contact_lineage_missing"
        )
    parent_current = [
        artifact_ref(
            required_file(
                _mapping(item, "contact_lineage_file").get("path"),
                "contact_lineage_file",
            )
        )
        for item in raw_files
    ]
    for parent, observed in zip(raw_files, parent_current, strict=True):
        parent_ref = _mapping(parent, "parent_contact_lineage_file")
        name = Path(str(observed["path"])).name
        if (
            name not in _ALLOWED_PARENT_CONTACT_CODE_DRIFT
            and (
                parent_ref.get("sha256") != observed["sha256"]
                or parent_ref.get("size_bytes") != observed["size_bytes"]
            )
        ):
            raise UnityContactObserveOnlyReportError(
                f"artifact_drift:unapproved_unity_contact_file:{name}"
            )
    current = list(parent_current)
    names = {Path(str(item["path"])).name for item in current}
    for required_name, sibling_name in (
        _ADDITIONAL_CONTACT_CODE_SIBLINGS.items()
    ):
        if required_name in names:
            continue
        sibling = next(
            (
                Path(str(item["path"]))
                for item in current
                if Path(str(item["path"])).name
                == sibling_name
            ),
            None,
        )
        if sibling is None:
            raise UnityContactObserveOnlyReportError(
                "unity_contact_lineage_required_file_missing"
            )
        current.append(
            artifact_ref(
                required_file(
                    sibling.with_name(required_name),
                    required_name,
                )
            )
        )
        names.add(required_name)
    if not _REQUIRED_CURRENT_CONTACT_CODE <= names:
        raise UnityContactObserveOnlyReportError(
            "unity_contact_lineage_required_file_missing"
        )
    return {
        "scene": scene,
        "normalization": normalization,
        "contact_lineage_files": current,
        "contact_lineage_aggregate_sha256": (
            artifact_refs_aggregate_sha256(current)
        ),
        "parent_contact_lineage_files": [
            dict(_mapping(item, "parent_contact_lineage_file"))
            for item in raw_files
        ],
        "source_manifest_contact_lineage_aggregate_sha256": str(
            unity.get("contact_lineage_aggregate_sha256", "")
        ),
        "parent_contact_lineage_drift_expected_due_to_this_diagnostic": True,
        "allowed_parent_contact_lineage_drift_files": sorted(
            _REQUIRED_CURRENT_CONTACT_CODE
        ),
    }


def verify_unity_contact_environment(
    lock: Mapping[str, Any],
    manifest_path: str | Path,
) -> None:
    """Reject any scene, normalization, contact-file, or aggregate drift."""

    if dict(lock) != lock_unity_contact_environment(manifest_path):
        raise UnityContactObserveOnlyReportError(
            "artifact_drift:unity_contact_environment"
        )


def _locked_frozen_file(
    value: Mapping[str, Any],
    *,
    path_key: str,
    sha_key: str,
    label: str,
) -> dict[str, Any]:
    observed = artifact_ref(required_file(value.get(path_key), label))
    if str(value.get(sha_key, "")).lower() != observed["sha256"]:
        raise UnityContactObserveOnlyReportError(
            f"artifact_drift:{label}"
        )
    return observed


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UnityContactObserveOnlyReportError(
            f"{label}_must_be_mapping"
        )
    return value


__all__ = [
    "lock_unity_contact_environment",
    "verify_unity_contact_environment",
]
