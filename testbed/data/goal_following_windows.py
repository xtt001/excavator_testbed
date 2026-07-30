"""Frozen offline window inventory for the goal-following mainline.

This module owns only dataset membership and label eligibility.  Source
episode identity is retained for offline leakage prevention; it is never
exposed as a predictor or runtime matching feature.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPERT_WINDOW_COUNT = 433
EXPERT_TRAIN_WINDOW_COUNT = 374
EXPERT_HELDOUT_WINDOW_COUNT = 59
HELDOUT_SOURCE_EPISODE_IDS = (33, 34)
ROLLOUT_COMPLETED_DIG_SEGMENT_COUNT = 9
ROLLOUT_CENSORED_HANDOFF_COUNT = 1


@dataclass(frozen=True)
class GoalFollowingWindowAssignment:
    """One offline sample with explicit, non-runtime label eligibility."""

    window_id: str
    partition: str
    source_episode_id: int | None
    rollout_cycle: int | None
    completed_dig_segment: bool
    censored_handoff: bool
    predictor_training_label: bool
    predictor_evaluation_label: bool
    act_tracking_label: bool
    domain_shift_evidence: bool


@dataclass(frozen=True)
class GoalFollowingCorpus:
    """Validated expert and current-rollout membership."""

    expert_windows: tuple[GoalFollowingWindowAssignment, ...]
    rollout_windows: tuple[GoalFollowingWindowAssignment, ...]

    @property
    def train_windows(self) -> tuple[GoalFollowingWindowAssignment, ...]:
        return tuple(row for row in self.expert_windows if row.partition == "train")

    @property
    def heldout_windows(self) -> tuple[GoalFollowingWindowAssignment, ...]:
        return tuple(
            row for row in self.expert_windows if row.partition == "source_heldout"
        )

    @property
    def rollout_tracking_segments(
        self,
    ) -> tuple[GoalFollowingWindowAssignment, ...]:
        return tuple(row for row in self.rollout_windows if row.act_tracking_label)

    @property
    def censored_handoffs(
        self,
    ) -> tuple[GoalFollowingWindowAssignment, ...]:
        return tuple(row for row in self.rollout_windows if row.censored_handoff)


def build_goal_following_corpus(
    *,
    expert_windows: Sequence[Mapping[str, Any]],
    rollout_cycles: Sequence[Mapping[str, Any]],
) -> GoalFollowingCorpus:
    """Validate the fixed 433-window source split and 9+1 rollout evidence."""

    experts = _build_expert_assignments(expert_windows)
    rollout = _build_rollout_assignments(rollout_cycles)
    all_ids = [row.window_id for row in (*experts, *rollout)]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("goal-following expert and rollout window ids must be unique")
    return GoalFollowingCorpus(
        expert_windows=experts,
        rollout_windows=rollout,
    )


def load_goal_following_expert_windows(
    manifest_path: str | Path,
) -> tuple[dict[str, Any], ...]:
    """Read and validate the fixed gold dig rows from a window manifest."""

    path = Path(manifest_path).expanduser().resolve(strict=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("goal-following window manifest must be a JSON list")
    selected: list[tuple[int, dict[str, Any]]] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"goal-following window manifest row {index} is not a mapping"
            )
        row = dict(raw)
        if str(row.get("primitive_name", "")).strip().lower() != "dig":
            continue
        if str(row.get("training_tier", "")).strip().lower() != "gold":
            continue
        primitive_episode_id = _nonnegative_int(
            row.get("primitive_episode_id"),
            label=f"manifest row {index}.primitive_episode_id",
        )
        row["window_id"] = f"expert_dig_{primitive_episode_id}"
        row["primitive_episode_id"] = primitive_episode_id
        row["primitive_name"] = "dig"
        row["training_tier"] = "gold"
        selected.append((primitive_episode_id, row))
    selected.sort(key=lambda item: item[0])
    rows = tuple(row for _, row in selected)
    _build_expert_assignments(rows)
    return rows


def _build_expert_assignments(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[GoalFollowingWindowAssignment, ...]:
    if len(rows) != EXPERT_WINDOW_COUNT:
        raise ValueError(
            "goal-following expert corpus must contain exactly "
            f"{EXPERT_WINDOW_COUNT} dig windows"
        )
    assignments: list[GoalFollowingWindowAssignment] = []
    for index, raw in enumerate(rows):
        row = dict(raw)
        window_id = _window_id(row, index=index, kind="expert")
        if str(row.get("primitive_name", "")).strip().lower() != "dig":
            raise ValueError(f"expert window {window_id!r} must be a dig window")
        source_episode_id = _source_episode_id(
            row.get("source_episode_id"),
            window_id=window_id,
        )
        partition = (
            "source_heldout"
            if source_episode_id in HELDOUT_SOURCE_EPISODE_IDS
            else "train"
        )
        supplied_split = row.get("split")
        if supplied_split is not None and str(supplied_split).strip() != partition:
            raise ValueError(
                "goal-following split must be source-grouped; primitive "
                f"window {window_id!r} cannot override source episode "
                f"{source_episode_id} into {supplied_split!r}"
            )
        assignments.append(
            GoalFollowingWindowAssignment(
                window_id=window_id,
                partition=partition,
                source_episode_id=source_episode_id,
                rollout_cycle=None,
                completed_dig_segment=True,
                censored_handoff=False,
                # The source partition is fixed, but these historical windows
                # do not contain an authoritative planner-issued continuous
                # goal.  A future approved pseudo-goal builder must establish
                # label eligibility explicitly; partition membership alone
                # must not make hindsight outcomes trainable.
                predictor_training_label=False,
                predictor_evaluation_label=False,
                act_tracking_label=True,
                domain_shift_evidence=False,
            )
        )
    _require_unique_window_ids(assignments, kind="expert")
    train = [row for row in assignments if row.partition == "train"]
    heldout = [row for row in assignments if row.partition == "source_heldout"]
    if len(train) != EXPERT_TRAIN_WINDOW_COUNT:
        raise ValueError(
            "source-grouped expert split must contain exactly "
            f"{EXPERT_TRAIN_WINDOW_COUNT} train windows"
        )
    if len(heldout) != EXPERT_HELDOUT_WINDOW_COUNT:
        raise ValueError(
            "source-grouped expert split must contain exactly "
            f"{EXPERT_HELDOUT_WINDOW_COUNT} held-out windows"
        )
    observed_heldout_sources = {row.source_episode_id for row in heldout}
    if observed_heldout_sources != set(HELDOUT_SOURCE_EPISODE_IDS):
        raise ValueError(
            "source-grouped held-out windows must come only from sources "
            "33 and 34, with both sources represented"
        )
    return tuple(assignments)


def _build_rollout_assignments(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[GoalFollowingWindowAssignment, ...]:
    expected_count = (
        ROLLOUT_COMPLETED_DIG_SEGMENT_COUNT + ROLLOUT_CENSORED_HANDOFF_COUNT
    )
    if len(rows) != expected_count:
        raise ValueError(
            "current rollout evidence must contain nine completed dig "
            "segments and one censored tenth handoff"
        )
    assignments: list[GoalFollowingWindowAssignment] = []
    for index, raw in enumerate(rows):
        row = dict(raw)
        window_id = _window_id(row, index=index, kind="rollout")
        cycle = _positive_int(
            row.get("rollout_cycle"),
            label=f"{window_id}.rollout_cycle",
        )
        completed = _strict_bool(
            row.get("completed_dig_segment"),
            label=f"{window_id}.completed_dig_segment",
        )
        censored = _strict_bool(
            row.get("censored_handoff"),
            label=f"{window_id}.censored_handoff",
        )
        if completed == censored:
            raise ValueError(
                "each rollout record must be either one completed dig segment "
                "or one censored handoff"
            )
        assignments.append(
            GoalFollowingWindowAssignment(
                window_id=window_id,
                partition="rollout_eval",
                source_episode_id=None,
                rollout_cycle=cycle,
                completed_dig_segment=completed,
                censored_handoff=censored,
                predictor_training_label=False,
                predictor_evaluation_label=False,
                act_tracking_label=completed,
                domain_shift_evidence=completed,
            )
        )
    _require_unique_window_ids(assignments, kind="rollout")
    observed_cycles = sorted(
        row.rollout_cycle for row in assignments if row.rollout_cycle is not None
    )
    if observed_cycles != list(range(1, expected_count + 1)):
        raise ValueError("current rollout cycles must be exactly 1 through 10")
    completed = [row for row in assignments if row.completed_dig_segment]
    censored = [row for row in assignments if row.censored_handoff]
    if (
        len(completed) != ROLLOUT_COMPLETED_DIG_SEGMENT_COUNT
        or len(censored) != ROLLOUT_CENSORED_HANDOFF_COUNT
        or censored[0].rollout_cycle != 10
    ):
        raise ValueError(
            "current rollout must have nine completed dig segments and a "
            "censored tenth handoff"
        )
    return tuple(sorted(assignments, key=lambda row: int(row.rollout_cycle or 0)))


def _window_id(
    row: Mapping[str, Any],
    *,
    index: int,
    kind: str,
) -> str:
    value = str(row.get("window_id", "")).strip()
    if not value:
        raise ValueError(f"{kind} window at index {index} is missing window_id")
    return value


def _source_episode_id(value: Any, *, window_id: str) -> int:
    text = str(value).strip()
    if text.startswith("episode_"):
        text = text.removeprefix("episode_")
    try:
        parsed = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{window_id}.source_episode_id must be a non-negative integer"
        ) from exc
    if parsed < 0:
        raise ValueError(
            f"{window_id}.source_episode_id must be a non-negative integer"
        )
    return parsed


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0 or parsed != value:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def _nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if parsed < 0 or parsed != value:
        raise ValueError(f"{label} must be a non-negative integer")
    return parsed


def _strict_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a bool")
    return value


def _require_unique_window_ids(
    rows: Sequence[GoalFollowingWindowAssignment],
    *,
    kind: str,
) -> None:
    ids = [row.window_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{kind} window ids must be unique")


__all__ = [
    "EXPERT_HELDOUT_WINDOW_COUNT",
    "EXPERT_TRAIN_WINDOW_COUNT",
    "EXPERT_WINDOW_COUNT",
    "GoalFollowingCorpus",
    "GoalFollowingWindowAssignment",
    "HELDOUT_SOURCE_EPISODE_IDS",
    "ROLLOUT_CENSORED_HANDOFF_COUNT",
    "ROLLOUT_COMPLETED_DIG_SEGMENT_COUNT",
    "build_goal_following_corpus",
    "load_goal_following_expert_windows",
]
