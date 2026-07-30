"""Validation and split contracts for frozen-ACT planned-cut experiments."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import numpy as np

from testbed.eval.executed_cut_effect_samples import (
    EFFECT_INPUT_SCHEMA,
    LabelLeakageError,
    find_planned_input_leakage,
    vectorize_effect_input,
)

PLANNED_CUT_CYCLE_SCHEMA = "planned_cut_cycle_v1"
PLANNED_CALIBRATION_DATASET_SCHEMA = "planned_cut_calibration_dataset_v1"
CAPABILITY_LABELS = (
    "effective_move",
    "low_payload",
    "stuck_no_motion",
    "timeout",
    "wall_contact",
    "bottom_contact",
    "recovery_required",
    "completed_dig",
    "completed_full_cycle",
)
ADVERSE_CAPABILITY_LABELS = (
    "low_payload",
    "stuck_no_motion",
    "timeout",
    "wall_contact",
    "bottom_contact",
    "recovery_required",
)
STABLE_OUTCOME_STATUS = "stable_post_terrain_present"
CAPABILITY_MIN_POSITIVE_COUNT = 20
CAPABILITY_MIN_NEGATIVE_COUNT = 20
CAPABILITY_MIN_RESET_GROUPS_PER_CLASS = 3


def build_planned_cut_cycle_record(
    *,
    episode_id: str,
    reset_group_id: str,
    cycle_id: int,
    provenance: Mapping[str, Any],
    pre_terrain: Mapping[str, Any],
    execution_context: Mapping[str, Any],
    planned_cut: Mapping[str, Any],
    execution: Mapping[str, Any],
    outcome: Mapping[str, Any],
    capability_labels: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct and validate one controlled frozen-ACT calibration record."""

    record = {
        "schema": PLANNED_CUT_CYCLE_SCHEMA,
        "effect_input_schema": EFFECT_INPUT_SCHEMA,
        "episode_id": str(episode_id),
        "reset_group_id": str(reset_group_id),
        "cycle_id": int(cycle_id),
        "provenance": deepcopy(dict(provenance)),
        "pre_terrain": deepcopy(dict(pre_terrain)),
        "execution_context": deepcopy(dict(execution_context)),
        "planned_cut": deepcopy(dict(planned_cut)),
        "execution": deepcopy(dict(execution)),
        "outcome": deepcopy(dict(outcome)),
        "capability_labels": deepcopy(dict(capability_labels)),
    }
    return validate_planned_cut_cycle(record)


def validate_planned_cut_cycle(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one record while keeping execution failures as valid negatives."""

    errors: list[str] = []
    if not isinstance(record, Mapping):
        return {
            "status": "invalid",
            "record": None,
            "validation_errors": ["record must be an object"],
        }
    if record.get("schema") != PLANNED_CUT_CYCLE_SCHEMA:
        errors.append(f"schema must be {PLANNED_CUT_CYCLE_SCHEMA!r}")
    if not _nonempty_string(record.get("episode_id")):
        errors.append("episode_id must be a non-empty string")
    if not _nonempty_string(record.get("reset_group_id")):
        errors.append("reset_group_id must be a non-empty string")
    if not _integer(record.get("cycle_id")):
        errors.append("cycle_id must be an integer")

    execution_context = record.get("execution_context")
    if isinstance(execution_context, Mapping) and _integer(record.get("cycle_id")):
        if execution_context.get("cycle_index") != record.get("cycle_id"):
            errors.append("execution_context.cycle_index must equal cycle_id")

    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        errors.append("provenance must be an object")
    else:
        if not _nonempty_string(provenance.get("source")):
            errors.append("provenance.source must be a non-empty string")
        if not _nonempty_string(provenance.get("act_checkpoint_sha256")):
            errors.append(
                "provenance.act_checkpoint_sha256 must identify the frozen ACT"
            )

    planned = record.get("planned_cut")
    if not isinstance(planned, Mapping):
        errors.append("planned_cut must be an object")
    else:
        errors.extend(
            f"forbidden post-execution field in planned input: {path}"
            for path in find_planned_input_leakage(record)
        )
        if not isinstance(planned.get("valid"), (bool, np.bool_)):
            errors.append("planned_cut.valid must be an explicit boolean")

    try:
        vectorize_effect_input(record, input_contract="planned_cut")
    except (LabelLeakageError, TypeError, ValueError) as exc:
        message = str(exc)
        if message not in errors and not any(message in item for item in errors):
            errors.append(message)

    execution = record.get("execution")
    if not isinstance(execution, Mapping):
        errors.append("execution must be an object")
    else:
        for field in (
            "actual_surface_penetration_peak_m",
            "actual_peak_depth_m",
        ):
            if field in execution and not _finite_number(execution[field]):
                errors.append(f"execution.{field} must be finite when present")
        for field in ("completed_dig", "completed_full_cycle"):
            if field in execution and not isinstance(
                execution[field], (bool, np.bool_)
            ):
                errors.append(f"execution.{field} must be boolean when present")

    outcome = record.get("outcome")
    if not isinstance(outcome, Mapping):
        errors.append("outcome must be an object")
    else:
        status = outcome.get("status")
        if not _nonempty_string(status):
            errors.append("outcome.status must be a non-empty string")
        elif status == STABLE_OUTCOME_STATUS:
            _validate_stable_outcome(outcome, errors)

    labels = record.get("capability_labels")
    if not isinstance(labels, Mapping):
        errors.append("capability_labels must be an object")
    else:
        for label in CAPABILITY_LABELS:
            if label not in labels:
                errors.append(f"capability_labels.{label} is required")
            elif not isinstance(labels[label], (bool, np.bool_)):
                errors.append(f"capability_labels.{label} must be boolean")

    return {
        "status": "invalid" if errors else "valid",
        "record": None if errors else deepcopy(dict(record)),
        "validation_errors": errors,
        "negative_preservation_status": (
            "preserved" if not errors else "not_applicable_invalid_record"
        ),
    }


def build_planned_cut_calibration_dataset(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Separate stable effect rows from the full negative-preserving capability set."""

    capability_records: list[dict[str, Any]] = []
    effect_records: list[dict[str, Any]] = []
    rejected_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        result = validate_planned_cut_cycle(record)
        if result["status"] != "valid":
            rejected_records.append(
                {
                    "record_index": index,
                    "validation_errors": result["validation_errors"],
                }
            )
            continue
        normalized = result["record"]
        capability_records.append(normalized)
        if normalized["outcome"]["status"] == STABLE_OUTCOME_STATUS:
            effect_records.append(normalized)

    adverse_counts = {
        label: sum(
            bool(record["capability_labels"][label]) for record in capability_records
        )
        for label in ADVERSE_CAPABILITY_LABELS
    }
    adverse_counts.update(
        {
            "ineffective_move": sum(
                not bool(record["capability_labels"]["effective_move"])
                for record in capability_records
            ),
            "incomplete_dig": sum(
                not bool(record["capability_labels"]["completed_dig"])
                for record in capability_records
            ),
            "incomplete_full_cycle": sum(
                not bool(record["capability_labels"]["completed_full_cycle"])
                for record in capability_records
            ),
        }
    )
    return {
        "schema": PLANNED_CALIBRATION_DATASET_SCHEMA,
        "source": "controlled_frozen_act_planned_cut_calibration",
        "status": "present" if capability_records else "no_valid_records",
        "input_contract": "planned_cut",
        "capability_negative_preservation": "all_valid_cycles_including_failures",
        "effect_row_policy": "stable_post_terrain_required",
        "input_record_count": len(records),
        "capability_record_count": len(capability_records),
        "effect_record_count": len(effect_records),
        "rejected_record_count": len(rejected_records),
        "negative_label_counts": adverse_counts,
        "capability_records": capability_records,
        "effect_records": effect_records,
        "rejected_records": rejected_records,
    }


def assign_episode_grouped_folds(
    records: Sequence[Mapping[str, Any]],
    *,
    fold_count: int = 6,
    salt: str = "terrain_effect_episode_grouped_v1",
) -> dict[str, int]:
    """Assign whole episodes to deterministic, approximately balanced folds."""

    if isinstance(fold_count, bool) or int(fold_count) != fold_count or fold_count <= 0:
        raise ValueError("fold_count must be a positive integer.")
    episode_ids: set[str] = set()
    for record in records:
        episode_id = record.get("episode_id")
        if not _nonempty_string(episode_id):
            raise ValueError("Every record requires a non-empty episode_id.")
        episode_ids.add(str(episode_id))
    ordered = sorted(
        episode_ids,
        key=lambda episode_id: (
            hashlib.sha256(f"{salt}\0{episode_id}".encode()).hexdigest(),
            episode_id,
        ),
    )
    return {
        episode_id: index % int(fold_count) for index, episode_id in enumerate(ordered)
    }


def assess_capability_label_support(
    records: Sequence[Mapping[str, Any]],
    *,
    min_positive_count: int = CAPABILITY_MIN_POSITIVE_COUNT,
    min_negative_count: int = CAPABILITY_MIN_NEGATIVE_COUNT,
    min_reset_groups_per_class: int = CAPABILITY_MIN_RESET_GROUPS_PER_CLASS,
) -> dict[str, Any]:
    """Gate learned capability heads on class and independent-reset support."""

    if min_positive_count <= 0 or min_negative_count <= 0:
        raise ValueError("Capability class-count minima must be positive.")
    if min_reset_groups_per_class <= 0:
        raise ValueError("min_reset_groups_per_class must be positive.")
    label_names = sorted(
        {
            str(label)
            for record in records
            if isinstance(record.get("capability_labels"), Mapping)
            for label in record["capability_labels"]
        }
    )
    label_results: dict[str, Any] = {}
    for label in label_names:
        positive_groups: set[str] = set()
        negative_groups: set[str] = set()
        positive_count = 0
        negative_count = 0
        missing_or_non_boolean_count = 0
        for record in records:
            labels = record.get("capability_labels")
            value = labels.get(label) if isinstance(labels, Mapping) else None
            reset_group_id = record.get("reset_group_id")
            if not isinstance(value, (bool, np.bool_)) or not _nonempty_string(
                reset_group_id
            ):
                missing_or_non_boolean_count += 1
                continue
            if bool(value):
                positive_count += 1
                positive_groups.add(str(reset_group_id))
            else:
                negative_count += 1
                negative_groups.add(str(reset_group_id))
        eligible = (
            missing_or_non_boolean_count == 0
            and positive_count >= min_positive_count
            and negative_count >= min_negative_count
            and len(positive_groups) >= min_reset_groups_per_class
            and len(negative_groups) >= min_reset_groups_per_class
        )
        label_results[label] = {
            "status": (
                "eligible_for_learned_classifier" if eligible else "rule_only_or_ood"
            ),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "positive_reset_group_count": len(positive_groups),
            "negative_reset_group_count": len(negative_groups),
            "missing_or_non_boolean_count": missing_or_non_boolean_count,
            "minimum_positive_count": min_positive_count,
            "minimum_negative_count": min_negative_count,
            "minimum_reset_groups_per_class": min_reset_groups_per_class,
        }
    overall_eligible = bool(label_results) and all(
        result["status"] == "eligible_for_learned_classifier"
        for result in label_results.values()
    )
    return {
        "schema": "capability_label_support_v1",
        "overall_status": (
            "eligible_for_learned_classifier"
            if overall_eligible
            else "rule_only_or_ood"
        ),
        "labels": label_results,
    }


def _validate_stable_outcome(outcome: Mapping[str, Any], errors: list[str]) -> None:
    delta = np.asarray(outcome.get("signed_depth_delta_m"), dtype=np.float64).reshape(
        -1
    )
    if delta.size != 6 or not np.isfinite(delta).all():
        errors.append("outcome.signed_depth_delta_m must contain 6 finite values")
    for field in ("payload_gain_kg", "removed_volume_m3"):
        if not _finite_number(outcome.get(field)):
            errors.append(f"outcome.{field} must be finite for a stable outcome")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _integer(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(
        value, (bool, np.bool_)
    )


def _finite_number(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


__all__ = [
    "ADVERSE_CAPABILITY_LABELS",
    "CAPABILITY_MIN_NEGATIVE_COUNT",
    "CAPABILITY_MIN_POSITIVE_COUNT",
    "CAPABILITY_MIN_RESET_GROUPS_PER_CLASS",
    "CAPABILITY_LABELS",
    "PLANNED_CALIBRATION_DATASET_SCHEMA",
    "PLANNED_CUT_CYCLE_SCHEMA",
    "STABLE_OUTCOME_STATUS",
    "assign_episode_grouped_folds",
    "assess_capability_label_support",
    "build_planned_cut_cycle_record",
    "build_planned_cut_calibration_dataset",
    "validate_planned_cut_cycle",
]
