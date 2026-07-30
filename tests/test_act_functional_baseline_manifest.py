from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "testbed/configs/baselines/yulong_aggregate_tx24_functional_10cycle_v1.json"
)


def test_old_tx24_ten_cycle_baseline_manifest_locks_all_artifact_hashes() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert payload["schema"] == "act_functional_baseline_manifest_v1"
    assert payload["status"] == "functional_baseline_only"
    assert payload["artifact_availability"] == "external_append_only"
    assert payload["functional_evidence"] == {
        "qualified_dig_start_count": 10,
        "dump_start_count": 10,
        "dump_end_count": 10,
        "completed_dump_count": 10,
        "completed_intermediate_return_handoff_count": 9,
        "rollout_stop_reason": "dig_area_depleted",
    }
    entries = [
        *payload["artifacts"].values(),
        *payload["checkpoints"].values(),
    ]
    for entry in entries:
        assert Path(entry["path"]).is_absolute() is False
        assert len(entry["sha256"]) == 64
        assert all(character in "0123456789abcdef" for character in entry["sha256"])
        path = ROOT / entry["path"]
        if path.is_file():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_old_baseline_cannot_be_misread_as_current_typed_safety_proof() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    limits = payload["evidence_limits"]

    assert limits["observed_rollout_env_state_width"] == 64
    assert limits["typed_wall_contact_available"] is False
    assert limits["typed_bottom_contact_available"] is False
    assert limits["current_107d_safety_contract_proven"] is False
    assert limits["formal_act_freeze_bundle"] is False
