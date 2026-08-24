from __future__ import annotations

from pathlib import Path

import pytest

from testbed.eval.dig_goal_action_lineage import (
    IdentifiabilityLineageError,
    require_complete_identifiability_lineage,
    resolve_identifiability_lineage,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/input_manifest.json"
)


@pytest.mark.skipif(not MANIFEST.exists(), reason="dispatch manifest unavailable")
def test_precheck_resolves_all_data_contracts_from_final_dispatch_manifest() -> None:
    lineage = resolve_identifiability_lineage(MANIFEST)

    assert lineage.variant_count == 112
    assert lineage.low_dim_order == ("qpos", "qvel", "dig_cut_tokens")
    assert lineage.camera_order == (
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    )
    assert lineage.support_p01.shape == (18,)
    assert lineage.support_p99.shape == (18,)
    assert lineage.action_std.shape == (4,)
    assert set(lineage.validation_source_episode_ids) == {33, 34}
    assert 33 not in lineage.train_source_episode_ids
    assert 34 not in lineage.train_source_episode_ids
    assert lineage.dispatch_decision_classification == "temporal_dispatch_not_primary"


def test_missing_support_or_variant_lock_fails_closed() -> None:
    value = {
        "dispatch_manifest": {"path": "/tmp/manifest", "sha256": "a" * 64},
        "variants": {"path": "/tmp/variants", "sha256": "b" * 64},
        "split": {"path": "/tmp/split", "sha256": "c" * 64},
        "support": {"path": "/tmp/support", "sha256": "d" * 64},
        "low_dim_order": ["qpos", "qvel", "dig_cut_tokens"],
        "camera_order": ["a", "b", "c", "d"],
        "token_order": [f"token_{index}" for index in range(10)],
    }
    require_complete_identifiability_lineage(value)
    value.pop("support")
    with pytest.raises(IdentifiabilityLineageError, match="support_missing"):
        require_complete_identifiability_lineage(value)
