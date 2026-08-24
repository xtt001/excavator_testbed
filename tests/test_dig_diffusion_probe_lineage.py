from __future__ import annotations

from pathlib import Path

import pytest

from testbed.eval.dig_diffusion_probe_lineage import resolve_minimal_dp_probe_lineage

ROOT = Path(__file__).resolve().parents[1]
DISPATCH = (
    ROOT
    / "runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/input_manifest.json"
)
IDENT = (
    ROOT
    / "runs/eval/dig_goal_action_identifiability_precheck_20260823T205439+0800/decision.json"
)


@pytest.mark.skipif(not DISPATCH.exists(), reason="dispatch manifest unavailable")
def test_probe_lineage_resolves_formal_windows_stats_variants_and_failed_data_gate() -> (
    None
):
    lineage = resolve_minimal_dp_probe_lineage(
        dispatch_manifest_path=DISPATCH,
        identifiability_decision_path=IDENT,
    )

    assert lineage.rollout_window_count == 38853
    assert lineage.variant_count == 112
    assert lineage.camera_order == (
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    )
    assert lineage.low_dim_order == ("qpos", "qvel", "dig_cut_tokens")
    assert set(lineage.train_source_episode_ids) == {
        3,
        6,
        7,
        8,
        9,
        13,
        16,
        19,
        23,
        24,
        25,
        27,
        28,
        29,
        30,
        32,
    }
    assert 33 not in lineage.train_source_episode_ids
    assert 34 not in lineage.train_source_episode_ids
    assert lineage.identifiability_classification == "data_supervision_unidentifiable"
    assert lineage.identifiability_training_allowed is False
