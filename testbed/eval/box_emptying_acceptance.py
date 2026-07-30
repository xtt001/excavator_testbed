"""Formal 3/3 acceptance gate for hard-bottom box emptying."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "box_emptying_rollout_v1"


class BoxEmptyingAcceptanceError(RuntimeError):
    """Raised when any formal rollout violates the locked gate."""


def evaluate_box_emptying_rollouts(
    rollouts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(rollouts) != 3:
        raise BoxEmptyingAcceptanceError("exactly_3_rollouts_required")
    reset_ids: set[str] = set()
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, rollout in enumerate(rollouts):
        prefix = f"rollout[{index}]"
        if rollout.get("schema") != SCHEMA:
            errors.append(f"{prefix}:schema_mismatch")
            continue
        reset_id = str(rollout.get("reset_id", "")).strip()
        if not reset_id or reset_id in reset_ids:
            errors.append(f"{prefix}:independent_reset_id_invalid")
        reset_ids.add(reset_id)
        cycle_count = _integer(rollout.get("completed_cycle_count"), -1)
        if cycle_count < 0 or cycle_count > 120:
            errors.append(f"{prefix}:cycle_limit_exceeded")
        final_fraction = _number(
            rollout.get("final_remaining_mass_fraction"),
            default=float("nan"),
        )
        if not math.isfinite(final_fraction) or final_fraction > 0.05 + 1.0e-12:
            errors.append(f"{prefix}:remaining_fraction_above_5pct")
        if _integer(rollout.get("success_hold_observation_count"), -1) < 3:
            errors.append(f"{prefix}:success_hold_below_3")
        terminal_payload = _number(
            rollout.get("terminal_payload_kg"),
            default=float("nan"),
        )
        if not math.isfinite(terminal_payload):
            errors.append(f"{prefix}:terminal_payload_missing")
        elif terminal_payload >= 15.0 and not bool(
            rollout.get("terminal_dump_completed", False)
        ):
            errors.append(f"{prefix}:payload_not_dumped_before_stop")
        for field, reason in (
            ("wall_contact_count", "wall_contact_present"),
            ("stuck_count", "stuck_present"),
            ("timeout_count", "timeout_present"),
        ):
            if _integer(rollout.get(field), -1) != 0:
                errors.append(f"{prefix}:{reason}")

        cycles = rollout.get("cycles")
        if not _sequence(cycles) or len(cycles) != cycle_count:
            errors.append(f"{prefix}:cycle_records_mismatch")
            continue
        decrease_count = 0
        ineffective_streak = 0
        max_ineffective_streak = 0
        for cycle_index, cycle in enumerate(cycles):
            if not isinstance(cycle, Mapping):
                errors.append(f"{prefix}:cycle_record_invalid")
                continue
            before = _number(
                cycle.get("stable_remaining_fraction_before"),
                default=float("nan"),
            )
            after = _number(
                cycle.get("stable_remaining_fraction_after"),
                default=float("nan"),
            )
            if math.isfinite(before) and math.isfinite(after) and after < before:
                decrease_count += 1
            effective = bool(cycle.get("effective_move", False))
            ineffective_streak = 0 if effective else ineffective_streak + 1
            max_ineffective_streak = max(
                max_ineffective_streak,
                ineffective_streak,
            )
            if _integer(cycle.get("cycle_index"), -1) != cycle_index:
                errors.append(f"{prefix}:cycle_index_not_contiguous")
        decrease_fraction = decrease_count / cycle_count if cycle_count > 0 else 0.0
        if decrease_fraction < 0.80 - 1.0e-12:
            errors.append(f"{prefix}:stable_mass_decrease_below_80pct")
        if max_ineffective_streak >= 3:
            errors.append(f"{prefix}:three_consecutive_ineffective")
        errors.extend(
            _hard_bottom_errors(
                prefix=prefix,
                cycles=cycles,
                events=rollout.get("hard_bottom_events"),
            )
        )
        summaries.append(
            {
                "reset_id": reset_id,
                "completed_cycle_count": cycle_count,
                "final_remaining_mass_fraction": final_fraction,
                "stable_mass_decrease_cycle_fraction": decrease_fraction,
                "max_ineffective_streak": max_ineffective_streak,
            }
        )
    if errors:
        raise BoxEmptyingAcceptanceError(";".join(errors))
    return {
        "schema": "box_emptying_formal_acceptance_v1",
        "source": "three_independent_hard_bottom_box_rollouts",
        "status": "passed",
        "required_rollout_count": 3,
        "passed_rollout_count": 3,
        "rollouts": summaries,
    }


def _hard_bottom_errors(
    *,
    prefix: str,
    cycles: Sequence[Any],
    events: Any,
) -> list[str]:
    if not _sequence(events):
        return [f"{prefix}:hard_bottom_events_missing"]
    errors: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            errors.append(f"{prefix}:hard_bottom_event_invalid")
            continue
        cycle_index = _integer(event.get("cycle_index"), -1)
        cell_id = _integer(event.get("cell_id"), -1)
        if not all(
            bool(event.get(field, False))
            for field in (
                "neutral_action_sent",
                "neutral_step_acknowledged",
                "replanned",
            )
        ):
            errors.append(f"{prefix}:hard_bottom_neutral_replan_invalid")
        if cycle_index < 0 or cycle_index >= len(cycles) or cell_id < 0:
            errors.append(f"{prefix}:hard_bottom_event_index_invalid")
            continue
        cycle = cycles[cycle_index]
        if not isinstance(cycle, Mapping) or not bool(
            cycle.get("hard_bottom_contact", False)
        ):
            errors.append(f"{prefix}:hard_bottom_event_cycle_mismatch")
        for later in cycles[cycle_index + 1 :]:
            if isinstance(later, Mapping) and _integer(later.get("cell_id"), -1) == cell_id:
                errors.append(f"{prefix}:repeated_depth_exhausted_cell")
                break
    return errors


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _integer(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _number(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "BoxEmptyingAcceptanceError",
    "evaluate_box_emptying_rollouts",
]
