"""Independent offline gate for a live hard-bottom recovery probe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from testbed.eval.act_functional_10cycle_validation import (
    ActFunctional10CycleValidationError,
    validate_hard_bottom_recovery_events,
)

SCHEMA = "hard_bottom_recovery_probe_v1"


class HardBottomRecoveryProbeError(RuntimeError):
    """Raised when a rollout cannot prove the recovery handshake."""


def build_hard_bottom_recovery_probe(
    *,
    rollout_jsonl_path: str | Path,
    reset_id: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate one real rollout and write one no-overwrite probe record."""

    destination = Path(output_path).expanduser()
    if destination.exists():
        raise FileExistsError(
            f"hard-bottom recovery probe already exists: {destination}"
        )
    source = Path(rollout_jsonl_path).expanduser()
    if not source.is_file():
        raise HardBottomRecoveryProbeError(
            f"rollout_jsonl_missing:{source}"
        )
    normalized_reset_id = str(reset_id).strip()
    if not normalized_reset_id:
        raise HardBottomRecoveryProbeError("reset_id_missing")
    try:
        rows = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise HardBottomRecoveryProbeError(
            f"rollout_jsonl_invalid:{source}"
        ) from exc
    try:
        events = validate_hard_bottom_recovery_events(rows)
    except ActFunctional10CycleValidationError as exc:
        raise HardBottomRecoveryProbeError(str(exc)) from exc
    if not events:
        raise HardBottomRecoveryProbeError("hard_bottom_event_missing")

    record = {
        "schema": SCHEMA,
        "status": "passed",
        "reset_id": normalized_reset_id,
        "hard_bottom_event_count": len(events),
        "hard_bottom_events": events,
        "source_artifact_path": str(source.resolve()),
        "source_artifact_sha256": _sha256(source),
        "gate": {
            "contact_observed": True,
            "contact_neutral_ack": True,
            "same_skill_act_restart": True,
            "scripted_clearance": True,
            "clearance_neutral_ack": True,
            "fresh_replan": True,
            "post_contact_depth_increase_max_m": 0.002,
            "exhausted_cell_redug": False,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "HardBottomRecoveryProbeError",
    "SCHEMA",
    "build_hard_bottom_recovery_probe",
]
