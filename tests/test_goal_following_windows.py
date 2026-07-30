from __future__ import annotations

import json
from pathlib import Path

import pytest

from testbed.data.goal_following_windows import (
    EXPERT_HELDOUT_WINDOW_COUNT,
    EXPERT_TRAIN_WINDOW_COUNT,
    EXPERT_WINDOW_COUNT,
    build_goal_following_corpus,
    load_goal_following_expert_windows,
)


def _expert_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(EXPERT_TRAIN_WINDOW_COUNT):
        rows.append(
            {
                "window_id": f"expert_train_{index:03d}",
                "primitive_name": "dig",
                "source_episode_id": index % 33,
            }
        )
    for index in range(EXPERT_HELDOUT_WINDOW_COUNT):
        rows.append(
            {
                "window_id": f"expert_heldout_{index:03d}",
                "primitive_name": "dig",
                "source_episode_id": 33 + index % 2,
            }
        )
    return rows


def _rollout_rows() -> list[dict[str, object]]:
    return [
        {
            "window_id": f"rollout_cycle_{cycle}",
            "rollout_cycle": cycle,
            "completed_dig_segment": True,
            "censored_handoff": False,
        }
        for cycle in range(1, 10)
    ] + [
        {
            "window_id": "rollout_cycle_10_handoff",
            "rollout_cycle": 10,
            "completed_dig_segment": False,
            "censored_handoff": True,
        }
    ]


def test_goal_following_corpus_freezes_source_split_and_rollout_scope() -> None:
    corpus = build_goal_following_corpus(
        expert_windows=_expert_rows(),
        rollout_cycles=_rollout_rows(),
    )

    assert len(corpus.expert_windows) == EXPERT_WINDOW_COUNT == 433
    assert len(corpus.train_windows) == EXPERT_TRAIN_WINDOW_COUNT == 374
    assert len(corpus.heldout_windows) == EXPERT_HELDOUT_WINDOW_COUNT == 59
    assert {row.source_episode_id for row in corpus.heldout_windows} == {33, 34}
    assert all(
        not row.predictor_training_label and not row.predictor_evaluation_label
        for row in corpus.expert_windows
    )
    assert len(corpus.rollout_tracking_segments) == 9
    assert all(
        row.partition == "rollout_eval"
        and row.domain_shift_evidence
        and row.act_tracking_label
        and not row.predictor_training_label
        for row in corpus.rollout_tracking_segments
    )
    assert len(corpus.censored_handoffs) == 1
    censored = corpus.censored_handoffs[0]
    assert censored.rollout_cycle == 10
    assert censored.act_tracking_label is False
    assert censored.predictor_training_label is False
    assert censored.predictor_evaluation_label is False


def test_goal_following_corpus_rejects_primitive_random_split_or_source_leak() -> None:
    rows = _expert_rows()
    rows[0]["split"] = "source_heldout"
    with pytest.raises(ValueError, match="source-grouped"):
        build_goal_following_corpus(
            expert_windows=rows,
            rollout_cycles=_rollout_rows(),
        )

    rows = _expert_rows()
    rows[-1]["source_episode_id"] = 32
    rows[-1]["split"] = "source_heldout"
    with pytest.raises(ValueError, match="source-grouped"):
        build_goal_following_corpus(
            expert_windows=rows,
            rollout_cycles=_rollout_rows(),
        )


def test_goal_following_corpus_rejects_wrong_fixed_counts_or_uncensored_tenth() -> None:
    with pytest.raises(ValueError, match="433"):
        build_goal_following_corpus(
            expert_windows=_expert_rows()[:-1],
            rollout_cycles=_rollout_rows(),
        )

    rollout = _rollout_rows()
    rollout[-1]["censored_handoff"] = False
    rollout[-1]["completed_dig_segment"] = True
    with pytest.raises(ValueError, match="nine completed"):
        build_goal_following_corpus(
            expert_windows=_expert_rows(),
            rollout_cycles=rollout,
        )


def test_rollout_cycle_rejects_boolean_integer_alias() -> None:
    rollout = _rollout_rows()
    rollout[0]["rollout_cycle"] = True

    with pytest.raises(ValueError, match="positive integer"):
        build_goal_following_corpus(
            expert_windows=_expert_rows(),
            rollout_cycles=rollout,
        )


def test_expert_manifest_loader_maps_real_fields_and_excludes_silver(
    tmp_path: Path,
) -> None:
    gold_rows = []
    for primitive_episode_id, row in enumerate(_expert_rows()):
        gold_rows.append(
            {
                "primitive_episode_id": primitive_episode_id,
                "primitive_name": row["primitive_name"],
                "source_episode_id": (f"episode_{row['source_episode_id']}"),
                "training_tier": "gold",
                "source_start_step": primitive_episode_id * 10,
            }
        )
    manifest_rows = [
        *gold_rows,
        *[
            {
                "primitive_episode_id": EXPERT_WINDOW_COUNT + index,
                "primitive_name": "dig",
                "source_episode_id": "episode_33",
                "training_tier": "silver",
            }
            for index in range(7)
        ],
        {
            "primitive_episode_id": 999,
            "primitive_name": "carry",
            "source_episode_id": "episode_33",
            "training_tier": "gold",
        },
    ]
    manifest_path = tmp_path / "window_manifest.json"
    manifest_path.write_text(json.dumps(manifest_rows), encoding="utf-8")

    loaded = load_goal_following_expert_windows(manifest_path)
    corpus = build_goal_following_corpus(
        expert_windows=loaded,
        rollout_cycles=_rollout_rows(),
    )

    assert len(loaded) == 433
    assert loaded[0]["window_id"] == "expert_dig_0"
    assert loaded[-1]["window_id"] == "expert_dig_432"
    assert all(row["training_tier"] == "gold" for row in loaded)
    assert len(corpus.train_windows) == 374
    assert len(corpus.heldout_windows) == 59
