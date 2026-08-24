from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from testbed.eval.dig_receding_horizon_lineage import (
    DiagnosticLineageError,
    require_complete_lineage,
    resolve_authoritative_lineage,
    select_source_episode_balanced_variants,
    validate_planner_variant,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "runs/eval/dig_token_swap_effect_consistency_20260822T150051+0800"


def _complete_lineage() -> dict:
    return {
        "checkpoint": {"path": "/tmp/checkpoint", "sha256": "a" * 64},
        "stats": {"path": "/tmp/stats", "sha256": "b" * 64},
        "support": {"path": "/tmp/support", "sha256": "c" * 64},
        "token_order": [f"token_{index}" for index in range(10)],
        "observation_order": ["qpos", "qvel", "dig_cut_tokens"],
        "camera_order": ["a", "b", "c", "d"],
        "state_lineage_sha256": "d" * 64,
    }


@pytest.mark.parametrize(
    "missing, reason",
    [
        ("support", "support_missing"),
        ("token_order", "token_order_missing"),
        ("observation_order", "observation_order_missing"),
        ("state_lineage_sha256", "state_lineage_missing"),
    ],
)
def test_token_support_or_lineage_missing_fails_closed(
    missing: str,
    reason: str,
) -> None:
    value = _complete_lineage()
    value.pop(missing)

    with pytest.raises(DiagnosticLineageError, match=reason):
        require_complete_lineage(value)


def test_source_episode_balanced_selection_excludes_33_34_and_overlap() -> None:
    records = []
    for source in (3, 6, 33, 34):
        for episode in range(4):
            records.append(
                {
                    "source_episode_id": source,
                    "primitive_episode_id": source * 10 + episode,
                    "variant_id": f"{source}-{episode}",
                    "variant_type": "position_translation",
                }
            )

    selected = select_source_episode_balanced_variants(records, count=8)

    assert {row["source_episode_id"] for row in selected} == {3, 6}
    assert len({row["primitive_episode_id"] for row in selected}) == 8


def test_balanced_selection_can_require_full_support_episode_coverage() -> None:
    records = []
    for source, count in ((3, 8), (24, 7)):
        for episode in range(count):
            records.append(
                {
                    "source_episode_id": source,
                    "primitive_episode_id": source * 100 + episode,
                    "variant_id": f"{source}-{episode}",
                    "variant_type": "position_translation",
                }
            )

    selected = select_source_episode_balanced_variants(
        records,
        count=8,
        minimum_episodes_per_source=8,
    )

    assert {row["source_episode_id"] for row in selected} == {3}


def test_variant_revalidates_18d_support_geometry_and_cell() -> None:
    base = np.asarray(
        [0.1, 0.2, 0.0, 0.2, -1.0, 0.0, 0.1, 0.2, 1.0, 1.0],
        dtype=np.float32,
    )
    alternate = base.copy()
    alternate[[0, 2]] += 0.05
    row = {
        "schema": "planner_reachable_dig_variant_v1",
        "variant_type": "position_translation",
        "target_cell_id": 2,
        "base_token": base.tolist(),
        "variant_token": alternate.tolist(),
        "base_goal": {
            "entry_xz_m": [0.2, 0.4],
            "exit_xz_m": [0.0, 0.4],
            "direction_xz": [-1.0, 0.0],
            "target_cell_id": 2,
        },
        "variant_goal": {
            "entry_xz_m": [0.3, 0.4],
            "exit_xz_m": [0.1, 0.4],
            "direction_xz": [-1.0, 0.0],
            "target_cell_id": 2,
        },
    }
    qpos = np.full((10, 4), 0.5, dtype=np.float32)
    qvel = np.zeros((10, 4), dtype=np.float32)

    result = validate_planner_variant(
        row,
        qpos=qpos,
        qvel=qvel,
        support_p01=np.full(18, -2.0, dtype=np.float32),
        support_p99=np.full(18, 2.0, dtype=np.float32),
        valid_cell_ids={0, 1, 2, 3, 4, 5},
    )

    assert result["valid"] is True
    assert result["full_18d_support"] is True
    assert result["geometry_self_consistent"] is True
    assert result["valid_cell"] is True


@pytest.mark.skipif(not HISTORY.exists(), reason="authoritative history unavailable")
def test_resolve_authoritative_lineage_reads_orders_and_paths_from_artifacts() -> None:
    base = HISTORY / "predictor_source_grouped_v1/bucket_only_v1"
    lineage = resolve_authoritative_lineage(
        reanchor_decision_path=base / "reanchor_eval_v2/decision.json",
        structure_decision_path=base / "structure_comparison_full_v1/decision.json",
        comparison_artifact_path=base / "comparison_full_v1/artifact.json",
    )

    assert lineage.checkpoint.path.name == "policy_best.ckpt"
    assert lineage.stats.path.name == "dataset_stats.pkl"
    assert lineage.low_dim_order == ("qpos", "qvel", "dig_cut_tokens")
    assert lineage.camera_order == (
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    )
    assert lineage.token_order == (
        "entry_x",
        "entry_z",
        "exit_x",
        "exit_z",
        "cut_direction_x",
        "cut_direction_z",
        "cut_length",
        "cut_depth_semantic",
        "payload_gain",
        "valid",
    )
    assert 33 not in lineage.train_source_episode_ids
    assert 34 not in lineage.train_source_episode_ids
    assert lineage.short_horizon_gate["horizon_5_passed"] is True
    assert lineage.short_horizon_gate["horizon_10_passed"] is True
    json.dumps(lineage.as_manifest())
