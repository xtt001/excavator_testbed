"""Aggregate purpose-specific usability from semantic replay episode gates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "terrain_replay_batch_assessment_v1"


def build_replay_batch_assessment(
    episode_gates: Sequence[Mapping[str, Any]],
    *,
    source_cycle_records: Sequence[Mapping[str, Any]],
    expected_episode_ids: Sequence[str],
) -> dict[str, Any]:
    """Summarize source ACT, episode semantics, and selective effect relabels."""

    expected = tuple(dict.fromkeys(str(value) for value in expected_episode_ids))
    expected_set = set(expected)
    validation_errors: list[str] = []
    gates_by_episode: dict[str, Mapping[str, Any]] = {}
    for gate_index, gate in enumerate(episode_gates):
        episode_id = str(gate.get("required_source_episode_id", ""))
        if not episode_id:
            validation_errors.append(f"episode_gates[{gate_index}] has no episode id")
            continue
        if episode_id in gates_by_episode:
            validation_errors.append(f"duplicate gate for {episode_id}")
            continue
        gates_by_episode[episode_id] = gate
        if episode_id not in expected_set:
            validation_errors.append(f"unexpected gate for {episode_id}")
        if gate.get("status") != "present":
            validation_errors.append(
                f"gate for {episode_id} has status {gate.get('status')}"
            )
    for episode_id in expected:
        if episode_id not in gates_by_episode:
            validation_errors.append(f"missing gate for {episode_id}")

    selected_source_records = [
        record
        for record in source_cycle_records
        if str(record.get("source_episode_id", "")) in expected_set
    ]
    source_replay_candidate_count = sum(
        bool(record.get("replay_candidate", False))
        for record in selected_source_records
    )
    source_replay_candidates_by_episode: Counter[str] = Counter(
        str(record.get("source_episode_id", ""))
        for record in selected_source_records
        if bool(record.get("replay_candidate", False))
    )
    source_act_eligible_count = sum(
        bool(record.get("act_training_eligible", False))
        for record in selected_source_records
    )

    episodes: list[dict[str, Any]] = []
    semantic_usable_cycle_count = 0
    effect_process_stable_cycle_count = 0
    effect_strict_cycle_count = 0
    grade_counts: Counter[str] = Counter()
    variance_counts: Counter[str] = Counter()
    for episode_id in expected:
        gate = gates_by_episode.get(episode_id)
        if gate is None:
            continue
        passed = bool(gate.get("pass", False)) and gate.get("status") == "present"
        process_integrity_pass = bool(
            gate.get("process_integrity_pass", passed)
        ) and gate.get("status") == "present"
        episode_semantic_pass = bool(
            gate.get("episode_semantic_pass", passed)
        ) and gate.get("status") == "present"
        source_cycle_count = _nonnegative_int(
            gate.get("source_complete_cycle_count")
        )
        effect_cycle_count = _nonnegative_int(
            gate.get("effect_usable_source_cycle_count")
        )
        manifest_source_cycle_count = source_replay_candidates_by_episode[episode_id]
        if source_cycle_count != manifest_source_cycle_count:
            validation_errors.append(
                "gate/source replay cycle count mismatch for "
                f"{episode_id}: {source_cycle_count} != {manifest_source_cycle_count}"
            )
        grade = str(gate.get("semantic_grade", "C"))
        if grade not in {"A", "B", "C"}:
            grade = "C"
        grade_counts[grade] += 1
        if passed:
            semantic_usable_cycle_count += source_cycle_count
            effect_strict_cycle_count += min(effect_cycle_count, source_cycle_count)
        if process_integrity_pass:
            effect_process_stable_cycle_count += min(
                effect_cycle_count,
                source_cycle_count,
            )
        for tier, count in _mapping(gate.get("variance_tier_counts")).items():
            if str(tier) in {"A", "B", "C"}:
                variance_counts[str(tier)] += _nonnegative_int(count)
        episodes.append(
            {
                "source_episode_id": episode_id,
                "semantic_replay_usable": passed,
                "process_integrity_pass": process_integrity_pass,
                "episode_semantic_pass": episode_semantic_pass,
                "semantic_grade": grade,
                "source_replay_candidate_cycle_count": source_cycle_count,
                "effect_relabel_usable_source_cycle_count": (
                    min(effect_cycle_count, source_cycle_count)
                    if process_integrity_pass
                    else 0
                ),
                "effect_relabel_cycle_status": (
                    "strict_use_a_b_only_mask_c"
                    if passed
                    else (
                        "local_a_b_candidate_episode_semantic_failed"
                        if process_integrity_pass
                        else "not_admitted_process_failed"
                    )
                ),
                "failed_checks": list(gate.get("failed_checks", [])),
                "gate_validation_errors": list(gate.get("validation_errors", [])),
            }
        )

    semantic_usable_episode_count = sum(
        bool(record["semantic_replay_usable"]) for record in episodes
    )
    return {
        "schema": SCHEMA,
        "status": "present" if not validation_errors else "invalid_batch_assessment",
        "expected_episode_count": len(expected),
        "assessed_episode_count": len(episodes),
        "semantic_usable_episode_count": semantic_usable_episode_count,
        "semantic_rejected_episode_count": len(episodes)
        - semantic_usable_episode_count,
        "source_replay_candidate_cycle_count": source_replay_candidate_count,
        "source_act_training_eligible_cycle_count": source_act_eligible_count,
        "act_training_cycle_decision": "source_cleaning_only_not_rejected_by_replay",
        "semantic_replay_usable_source_cycle_count": semantic_usable_cycle_count,
        "effect_relabel_process_stable_source_cycle_count": (
            effect_process_stable_cycle_count
        ),
        "effect_relabel_strict_source_cycle_count": effect_strict_cycle_count,
        "effect_relabel_strict_fraction_of_semantic_cycles": (
            effect_strict_cycle_count / semantic_usable_cycle_count
            if semantic_usable_cycle_count
            else 0.0
        ),
        "grade_counts": {grade: grade_counts[grade] for grade in ("A", "B", "C")},
        "effect_target_record_tier_counts": {
            tier: variance_counts[tier] for tier in ("A", "B", "C")
        },
        "episodes": episodes,
        "validation_errors": validation_errors,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


__all__ = ["SCHEMA", "build_replay_batch_assessment"]
