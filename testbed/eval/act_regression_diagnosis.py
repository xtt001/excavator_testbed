"""Causal diagnosis artifact for the four-condition ACT regression matrix.

The module is deliberately offline and side-effect free except for the explicit
no-overwrite writer.  Invalid reset attempts remain auditable, but only repeats
whose initial state passed the experiment contract enter the fixed three-repeat
causal classification.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA = "act_regression_module_diagnosis_v1"
CONDITION_IDS = ("F0", "D1", "C1", "DC1")
VALID_REPEATS_PER_CONDITION = 3


class ActRegressionDiagnosisError(RuntimeError):
    """Raised when diagnosis inputs violate the experiment evidence contract."""


def build_act_regression_module_diagnosis(
    *,
    experiment_id: str,
    conditions: Mapping[str, Sequence[Mapping[str, Any]]],
    source_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the locked F0/D1/C1/DC1 causal-classification artifact.

    A condition may contain additional attempts whose initial state is invalid.
    Those attempts are counted and retained but never enter outcome counts.  A
    causal classification is emitted only when every condition has exactly
    three valid repeats.
    """

    normalized_experiment_id = str(experiment_id).strip()
    if not normalized_experiment_id:
        raise ActRegressionDiagnosisError("experiment_id_missing")
    if not isinstance(conditions, Mapping):
        raise ActRegressionDiagnosisError("conditions_must_be_mapping")
    actual_ids = set(conditions)
    required_ids = set(CONDITION_IDS)
    if actual_ids != required_ids:
        raise ActRegressionDiagnosisError(
            "condition_ids_must_be_exactly:"
            + ",".join(CONDITION_IDS)
            + ":got="
            + ",".join(sorted(str(value) for value in actual_ids))
        )
    if source_artifacts is not None and not isinstance(
        source_artifacts,
        Mapping,
    ):
        raise ActRegressionDiagnosisError("source_artifacts_must_be_mapping")

    seen_repeat_ids: set[str] = set()
    condition_summaries: dict[str, dict[str, Any]] = {}
    initial_state_by_condition: dict[str, dict[str, int]] = {}
    validation_errors: list[str] = []
    for condition_id in CONDITION_IDS:
        summary = _condition_summary(
            condition_id=condition_id,
            repeats=conditions[condition_id],
            seen_repeat_ids=seen_repeat_ids,
        )
        condition_summaries[condition_id] = summary
        initial_state_by_condition[condition_id] = {
            "attempted_repeat_count": summary["attempted_repeat_count"],
            "valid_repeat_count": summary["valid_repeat_count"],
            "invalid_repeat_count": summary["invalid_repeat_count"],
        }
        if summary["valid_repeat_count"] != VALID_REPEATS_PER_CONDITION:
            validation_errors.append(
                f"{condition_id}:exactly_{VALID_REPEATS_PER_CONDITION}"
                f"_valid_repeats_required:got_{summary['valid_repeat_count']}"
            )

    attempted_count = sum(
        values["attempted_repeat_count"]
        for values in initial_state_by_condition.values()
    )
    valid_count = sum(
        values["valid_repeat_count"]
        for values in initial_state_by_condition.values()
    )
    invalid_count = sum(
        values["invalid_repeat_count"]
        for values in initial_state_by_condition.values()
    )
    initial_state_validity = {
        "attempted_repeat_count": attempted_count,
        "valid_repeat_count": valid_count,
        "invalid_repeat_count": invalid_count,
        "required_valid_repeat_count": (
            len(CONDITION_IDS) * VALID_REPEATS_PER_CONDITION
        ),
        "by_condition": initial_state_by_condition,
    }

    f0 = condition_summaries["F0"]
    f0_reproduced = bool(
        f0["valid_repeat_count"] == VALID_REPEATS_PER_CONDITION
        and f0["wall_contact_repeat_count"] >= 2
    )
    f0_reproducibility = {
        "status": (
            "fixed_plan_failure_reproduced"
            if f0_reproduced
            else "fixed_plan_not_reproduced"
        ),
        "valid_repeat_count": f0["valid_repeat_count"],
        "wall_contact_repeat_count": f0["wall_contact_repeat_count"],
        "required_wall_contact_repeat_count": 2,
        "native_a0_control_required": bool(
            f0["valid_repeat_count"] == VALID_REPEATS_PER_CONDITION
            and not f0_reproduced
        ),
    }

    if validation_errors:
        status = "incomplete_valid_repeats"
        classification = _classification(
            category="not_classified",
            primary_modules=[],
            native_a0_control_required=False,
        )
    else:
        status = "classified"
        classification = _classify(condition_summaries)

    return {
        "schema": SCHEMA,
        "status": status,
        "experiment_id": normalized_experiment_id,
        "condition_order": list(CONDITION_IDS),
        "required_valid_repeats_per_condition": VALID_REPEATS_PER_CONDITION,
        "source_artifacts": dict(source_artifacts or {}),
        "initial_state_validity": initial_state_validity,
        "conditions": condition_summaries,
        "f0_reproducibility": f0_reproducibility,
        "root_cause_classification": classification,
        "validation_errors": validation_errors,
    }


def write_act_regression_module_diagnosis(
    *,
    experiment_id: str,
    conditions: Mapping[str, Sequence[Mapping[str, Any]]],
    output_path: str | Path,
    source_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and write one no-overwrite machine-readable diagnosis artifact."""

    destination = Path(output_path).expanduser()
    if destination.exists():
        raise FileExistsError(
            f"ACT regression diagnosis already exists: {destination}"
        )
    result = build_act_regression_module_diagnosis(
        experiment_id=experiment_id,
        conditions=conditions,
        source_artifacts=source_artifacts,
    )
    result = {**result, "output_path": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _condition_summary(
    *,
    condition_id: str,
    repeats: Sequence[Mapping[str, Any]],
    seen_repeat_ids: set[str],
) -> dict[str, Any]:
    if not _is_sequence(repeats):
        raise ActRegressionDiagnosisError(
            f"{condition_id}:repeats_must_be_sequence"
        )

    normalized_repeats: list[dict[str, Any]] = []
    valid_repeats: list[dict[str, Any]] = []
    for index, raw in enumerate(repeats):
        if not isinstance(raw, Mapping):
            raise ActRegressionDiagnosisError(
                f"{condition_id}:repeat[{index}]:must_be_mapping"
            )
        repeat_id = str(raw.get("repeat_id", "")).strip()
        if not repeat_id:
            raise ActRegressionDiagnosisError(
                f"{condition_id}:repeat[{index}]:repeat_id_missing"
            )
        if repeat_id in seen_repeat_ids:
            raise ActRegressionDiagnosisError(
                f"{condition_id}:duplicate_repeat_id:{repeat_id}"
            )
        seen_repeat_ids.add(repeat_id)
        initial_state_valid = raw.get("initial_state_valid")
        if not isinstance(initial_state_valid, bool):
            raise ActRegressionDiagnosisError(
                f"{condition_id}:{repeat_id}:initial_state_valid_must_be_bool"
            )
        if not initial_state_valid:
            invalid_repeat = {
                "repeat_id": repeat_id,
                "initial_state_valid": False,
                "included_in_classification": False,
            }
            _copy_optional_evidence(raw, invalid_repeat)
            normalized_repeats.append(invalid_repeat)
            continue

        normalized = {
            "repeat_id": repeat_id,
            "initial_state_valid": True,
            "included_in_classification": True,
            "wall_contact_count": _nonnegative_integer(
                raw.get("wall_contact_count"),
                f"{condition_id}:{repeat_id}:wall_contact_count",
            ),
            "timeout_count": _nonnegative_integer(
                raw.get("timeout_count"),
                f"{condition_id}:{repeat_id}:timeout_count",
            ),
            "envelope_ready": _boolean(
                raw.get("envelope_ready"),
                f"{condition_id}:{repeat_id}:envelope_ready",
            ),
        }
        for key in ("bottom_contact_count", "stuck_count"):
            if key in raw:
                normalized[key] = _nonnegative_integer(
                    raw.get(key),
                    f"{condition_id}:{repeat_id}:{key}",
                )
        for key in (
            "neutral_acknowledged",
            "terminal_requested",
            "zero_action_after_trigger",
        ):
            if key in raw:
                normalized[key] = _boolean(
                    raw.get(key),
                    f"{condition_id}:{repeat_id}:{key}",
                )
        if "trigger_kind" in raw:
            normalized["trigger_kind"] = str(raw.get("trigger_kind", ""))
        _copy_optional_evidence(raw, normalized)
        normalized_repeats.append(normalized)
        valid_repeats.append(normalized)

    wall_repeat_count = sum(
        int(repeat["wall_contact_count"] > 0)
        for repeat in valid_repeats
    )
    timeout_repeat_count = sum(
        int(repeat["timeout_count"] > 0)
        for repeat in valid_repeats
    )
    envelope_ready_count = sum(
        int(repeat["envelope_ready"])
        for repeat in valid_repeats
    )
    valid_repeat_count = len(valid_repeats)
    variant_passed = bool(
        condition_id != "F0"
        and valid_repeat_count == VALID_REPEATS_PER_CONDITION
        and wall_repeat_count == 0
        and envelope_ready_count >= 2
    )
    return {
        "condition_id": condition_id,
        "attempted_repeat_count": len(normalized_repeats),
        "valid_repeat_count": valid_repeat_count,
        "invalid_repeat_count": len(normalized_repeats) - valid_repeat_count,
        "wall_contact_repeat_count": wall_repeat_count,
        "timeout_repeat_count": timeout_repeat_count,
        "envelope_ready_repeat_count": envelope_ready_count,
        "wall_failure_reproduced": bool(
            valid_repeat_count == VALID_REPEATS_PER_CONDITION
            and wall_repeat_count >= 2
        ),
        "variant_passed": variant_passed,
        "repeats": normalized_repeats,
    }


def _classify(
    conditions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    f0 = conditions["F0"]
    d1 = conditions["D1"]
    c1 = conditions["C1"]
    dc1 = conditions["DC1"]

    if f0["wall_contact_repeat_count"] < 2:
        return _classification(
            category="fixed_plan_not_reproduced",
            primary_modules=[],
            native_a0_control_required=True,
        )
    if all(
        conditions[condition_id]["wall_contact_repeat_count"] >= 2
        for condition_id in CONDITION_IDS
    ):
        return _classification(
            category=(
                "all_variants_wall_requires_policy_or_upstream_diagnosis"
            ),
            primary_modules=["policy_or_upstream"],
            native_a0_control_required=False,
        )

    d1_passed = bool(d1["variant_passed"])
    c1_passed = bool(c1["variant_passed"])
    dc1_passed = bool(dc1["variant_passed"])
    if d1_passed and c1_passed:
        return _classification(
            category="multiple_primary",
            primary_modules=["planned_depth", "corridor_geometry"],
            native_a0_control_required=False,
        )
    if d1_passed:
        return _classification(
            category="planned_depth_primary",
            primary_modules=["planned_depth"],
            native_a0_control_required=False,
        )
    if c1_passed:
        return _classification(
            category="corridor_geometry_primary",
            primary_modules=["corridor_geometry"],
            native_a0_control_required=False,
        )
    if (
        c1["wall_contact_repeat_count"] == 0
        and c1["timeout_repeat_count"] == VALID_REPEATS_PER_CONDITION
    ):
        return _classification(
            category="corridor_wall_cause_with_envelope_bottleneck",
            primary_modules=[
                "corridor_geometry",
                "carry_start_envelope",
            ],
            native_a0_control_required=False,
        )
    if dc1_passed:
        return _classification(
            category="depth_corridor_interaction",
            primary_modules=["planned_depth", "corridor_geometry"],
            native_a0_control_required=False,
        )
    return _classification(
        category="unresolved_mixed_variant_evidence",
        primary_modules=[],
        native_a0_control_required=False,
    )


def _classification(
    *,
    category: str,
    primary_modules: Sequence[str],
    native_a0_control_required: bool,
) -> dict[str, Any]:
    return {
        "category": str(category),
        "primary_modules": [str(value) for value in primary_modules],
        "native_a0_control_required": bool(native_a0_control_required),
    }


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ActRegressionDiagnosisError(
            f"{label}_must_be_nonnegative_integer"
        )
    return int(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ActRegressionDiagnosisError(f"{label}_must_be_bool")
    return value


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _copy_optional_evidence(
    source: Mapping[str, Any],
    destination: dict[str, Any],
) -> None:
    for key in ("artifact", "initial_state_check"):
        value = source.get(key)
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise ActRegressionDiagnosisError(
                f"{key}_must_be_mapping_when_present"
            )
        destination[key] = dict(value)


__all__ = [
    "ActRegressionDiagnosisError",
    "CONDITION_IDS",
    "SCHEMA",
    "VALID_REPEATS_PER_CONDITION",
    "build_act_regression_module_diagnosis",
    "write_act_regression_module_diagnosis",
]
