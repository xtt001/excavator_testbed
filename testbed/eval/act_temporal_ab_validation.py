"""Promotion contract for one-factor ACT temporal-aggregation A/B runs."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.eval.act_functional_10cycle_validation import (
    ActFunctional10CycleValidationError,
    evaluate_act_functional_10cycle_records,
)

SCHEMA = "act_temporal_aggregation_ab_validation_v1"
_TRACKING_FIELDS = (
    "entry_error_mean_m",
    "exit_error_mean_m",
    "local_depth_abs_error_mean_m",
)
_TRANSPORT_FIELDS = (
    "payload_bonus_mean_kg",
    "deposited_fraction_mean",
)


class TemporalABValidationError(RuntimeError):
    """Raised when an A/B candidate violates sequencing or promotion gates."""


def evaluate_temporal_ab_candidate(
    *,
    candidate_name: str,
    predecessor_temporal_contract: Mapping[str, Any],
    candidate_temporal_contract: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
    functional_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate A1/A2 without allowing a failed ten-cycle run to be promoted."""

    name = str(candidate_name).strip().upper()
    predecessor = _temporal_contract(predecessor_temporal_contract)
    candidate = _temporal_contract(candidate_temporal_contract)
    changed = [
        field
        for field in ("window", "weight_order", "decay")
        if predecessor[field] != candidate[field]
    ]
    if len(changed) != 1:
        raise TemporalABValidationError(
            f"one_factor_at_a_time_required:changed={changed}"
        )
    changed_factor = changed[0]
    if name == "A1":
        if changed_factor != "window" or candidate["window"] != 20:
            raise TemporalABValidationError(
                "A1_requires_only_window_change_to_20"
            )
    elif name == "A2":
        if (
            changed_factor != "weight_order"
            or candidate["weight_order"] != "newest_first"
            or candidate["decay"] != 0.01
        ):
            raise TemporalABValidationError(
                "A2_requires_only_true_age_newest_first_decay_0p01"
            )
    else:
        raise TemporalABValidationError(f"unknown_candidate:{name}")

    reset_count = len(functional_records)
    if reset_count == 1:
        _validate_single_functional_record(functional_records[0])
        functional_status = "one_reset_passed"
    elif reset_count == 3:
        try:
            evaluate_act_functional_10cycle_records(functional_records)
        except ActFunctional10CycleValidationError as exc:
            raise TemporalABValidationError(
                f"functional_record_failed:{exc}"
            ) from exc
        functional_status = "three_resets_passed"
    else:
        raise TemporalABValidationError(
            "functional_records_must_contain_one_or_three_resets"
        )

    baseline = _metrics(baseline_metrics)
    observed = _metrics(candidate_metrics)
    tracking_ratios = {
        field: _lower_is_better_ratio(observed[field], baseline[field])
        for field in _TRACKING_FIELDS
    }
    over_limit = [
        field
        for field, ratio in tracking_ratios.items()
        if ratio > 1.10 + 1.0e-12
    ]
    if over_limit:
        raise TemporalABValidationError(
            "tracking_metric_worsened_over_10pct:"
            + ",".join(over_limit)
        )
    combined_ratio = sum(tracking_ratios.values()) / len(
        tracking_ratios
    )
    combined_improvement = 1.0 - combined_ratio
    if combined_improvement < 0.10 - 1.0e-12:
        raise TemporalABValidationError(
            "tracking_combined_improvement_below_10pct"
        )

    transport_ratios = {
        "payload_bonus_mean_kg": _higher_is_better_ratio(
            min(observed["payload_bonus_mean_kg"], 60.0),
            min(baseline["payload_bonus_mean_kg"], 60.0),
        ),
        "deposited_fraction_mean": _higher_is_better_ratio(
            observed["deposited_fraction_mean"],
            baseline["deposited_fraction_mean"],
        ),
    }
    transport_regressions = [
        field
        for field, ratio in transport_ratios.items()
        if ratio < 0.90 - 1.0e-12
    ]
    if transport_regressions:
        raise TemporalABValidationError(
            "transport_metric_worsened_over_10pct:"
            + ",".join(transport_regressions)
        )

    replacement = reset_count == 3
    return {
        "schema": SCHEMA,
        "status": (
            "accepted_functional_bundle_replacement"
            if replacement
            else "eligible_for_3x10"
        ),
        "candidate_name": name,
        "changed_factor": changed_factor,
        "predecessor_temporal_contract": predecessor,
        "candidate_temporal_contract": candidate,
        "functional_gate": {
            "reset_count": reset_count,
            "status": functional_status,
        },
        "tracking_ratios": tracking_ratios,
        "tracking_combined_improvement_fraction": combined_improvement,
        "transport_ratios": transport_ratios,
        "functional_bundle_replacement": replacement,
        "formal_freeze_unlocked": False,
    }


def _validate_single_functional_record(
    record: Mapping[str, Any],
) -> None:
    errors: list[str] = []
    if record.get("schema") != "act_functional_10cycle_validation_v1":
        errors.append("schema")
    if record.get("status") != "passed":
        errors.append("status")
    if int(record.get("completed_cycle_count", -1)) != 10:
        errors.append("cycle_count")
    cycles = record.get("cycles")
    if not isinstance(cycles, Sequence) or isinstance(cycles, (str, bytes)):
        errors.append("cycles")
    elif [
        int(cycle.get("cycle_index", -1))
        for cycle in cycles
        if isinstance(cycle, Mapping)
    ] != list(range(10)):
        errors.append("cycles")
    ready = int(record.get("terminal_return_ready_step", -1))
    ack = int(record.get("terminal_neutral_ack_step", -1))
    if ready < 0 or ack <= ready:
        errors.append("terminal_ack")
    for field in ("wall_contact_count", "stuck_count", "timeout_count"):
        if int(record.get(field, -1)) != 0:
            errors.append(field)
    if errors:
        raise TemporalABValidationError(
            "functional_record_failed:" + ",".join(errors)
        )


def _temporal_contract(values: Mapping[str, Any]) -> dict[str, Any]:
    window = values.get("window")
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise TemporalABValidationError("temporal_window_invalid")
    order = values.get("weight_order")
    if order not in {"legacy_oldest_first", "newest_first"}:
        raise TemporalABValidationError("temporal_weight_order_invalid")
    decay = _finite_nonnegative(values.get("decay"), "temporal_decay")
    return {
        "window": window,
        "weight_order": str(order),
        "decay": decay,
    }


def _metrics(values: Mapping[str, Any]) -> dict[str, float]:
    result = {
        field: _finite_nonnegative(values.get(field), field)
        for field in (*_TRACKING_FIELDS, *_TRANSPORT_FIELDS)
    }
    if result["deposited_fraction_mean"] > 1.0 + 1.0e-12:
        raise TemporalABValidationError(
            "deposited_fraction_mean_above_one"
        )
    return result


def _finite_nonnegative(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise TemporalABValidationError(f"{label}_invalid") from exc
    if not math.isfinite(parsed) or parsed < 0.0:
        raise TemporalABValidationError(f"{label}_invalid")
    return parsed


def _lower_is_better_ratio(candidate: float, baseline: float) -> float:
    if baseline == 0.0:
        return 0.0 if candidate == 0.0 else float("inf")
    return candidate / baseline


def _higher_is_better_ratio(candidate: float, baseline: float) -> float:
    if baseline == 0.0:
        return 1.0
    return candidate / baseline


__all__ = [
    "SCHEMA",
    "TemporalABValidationError",
    "evaluate_temporal_ab_candidate",
]
