from __future__ import annotations

import pytest

from testbed.eval.box_emptying_acceptance import (
    BoxEmptyingAcceptanceError,
    evaluate_box_emptying_rollouts,
)


def _rollout(reset_id: str) -> dict[str, object]:
    cycles = []
    remaining = 1.0
    for index in range(20):
        next_remaining = remaining - 0.048 if index < 19 else 0.045
        cycles.append(
            {
                "cycle_index": index,
                "cell_id": index % 6,
                "stable_remaining_fraction_before": remaining,
                "stable_remaining_fraction_after": next_remaining,
                "effective_move": index % 10 != 9,
                "hard_bottom_contact": False,
            }
        )
        remaining = next_remaining
    return {
        "schema": "box_emptying_rollout_v1",
        "reset_id": reset_id,
        "completed_cycle_count": 20,
        "final_remaining_mass_fraction": 0.045,
        "success_hold_observation_count": 3,
        "terminal_payload_kg": 0.0,
        "terminal_dump_completed": True,
        "wall_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "cycles": cycles,
        "hard_bottom_events": [],
    }


def test_formal_box_emptying_gate_accepts_three_independent_safe_rollouts() -> None:
    result = evaluate_box_emptying_rollouts(
        [_rollout(f"reset-{index}") for index in range(3)]
    )

    assert result["status"] == "passed"
    assert result["passed_rollout_count"] == 3
    assert result["required_rollout_count"] == 3


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda rows: rows[:2], "exactly_3_rollouts_required"),
        (
            lambda rows: [{**rows[0], "completed_cycle_count": 121}, *rows[1:]],
            "cycle_limit_exceeded",
        ),
        (
            lambda rows: [
                {**rows[0], "final_remaining_mass_fraction": 0.051},
                *rows[1:],
            ],
            "remaining_fraction_above_5pct",
        ),
        (
            lambda rows: [{**rows[0], "wall_contact_count": 1}, *rows[1:]],
            "wall_contact_present",
        ),
        (
            lambda rows: [
                {
                    **rows[0],
                    "cycles": [
                        {**cycle, "effective_move": False}
                        if 3 <= index <= 5
                        else cycle
                        for index, cycle in enumerate(rows[0]["cycles"])
                    ],
                },
                *rows[1:],
            ],
            "three_consecutive_ineffective",
        ),
    ],
)
def test_formal_box_emptying_gate_rejects_failed_rollout(
    mutation,
    reason: str,
) -> None:
    rows = [_rollout(f"reset-{index}") for index in range(3)]
    with pytest.raises(BoxEmptyingAcceptanceError, match=reason):
        evaluate_box_emptying_rollouts(mutation(rows))


def test_hard_bottom_event_requires_neutral_ack_replan_and_no_repeat_cell() -> None:
    rows = [_rollout(f"reset-{index}") for index in range(3)]
    first = rows[0]
    first["hard_bottom_events"] = [
        {
            "cycle_index": 4,
            "cell_id": 2,
            "neutral_action_sent": True,
            "neutral_step_acknowledged": True,
            "replanned": True,
        }
    ]
    for cycle in first["cycles"]:
        if cycle["cycle_index"] == 4:
            cycle["hard_bottom_contact"] = True
        if cycle["cycle_index"] > 4 and cycle["cell_id"] == 2:
            cycle["cell_id"] = 1

    assert evaluate_box_emptying_rollouts(rows)["status"] == "passed"

    first["cycles"][-1]["cell_id"] = 2
    with pytest.raises(
        BoxEmptyingAcceptanceError,
        match="repeated_depth_exhausted_cell",
    ):
        evaluate_box_emptying_rollouts(rows)
