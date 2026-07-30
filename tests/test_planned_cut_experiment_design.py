from __future__ import annotations

import math
from collections import Counter

import pytest

from testbed.eval.planned_cut_experiment import build_controlled_planned_cut_design


def test_controlled_design_has_108_cycles_in_18_balanced_six_cut_rollouts() -> None:
    design = build_controlled_planned_cut_design(seed=0)

    assert design["schema"] == "planned_cut_controlled_experiment_v1"
    assert design["rollout_count"] == 18
    assert design["cycle_count"] == 108
    assert all(len(rollout["cycles"]) == 6 for rollout in design["rollouts"])
    assert all(
        {cycle["cell_id"] for cycle in rollout["cycles"]} == set(range(6))
        for rollout in design["rollouts"]
    )

    combinations = Counter(
        (
            cycle["cell_id"],
            cycle["direction_axis"],
            cycle["planned_depth_m"],
        )
        for rollout in design["rollouts"]
        for cycle in rollout["cycles"]
    )
    assert len(combinations) == 6 * 2 * 3
    assert set(combinations.values()) == {3}
    assert all(
        cycle["cut_length_m"] == 0.75
        and cycle["planned_payload_target_kg"] == 60.0
        and cycle["wall_inset_m"] == 0.30
        for rollout in design["rollouts"]
        for cycle in rollout["cycles"]
    )
    assert all(
        cycle["horizontal_reach_m"]
        == pytest.approx(
            math.sqrt(
                cycle["cut_length_m"] ** 2
                - cycle["planned_depth_m"] ** 2
            )
        )
        for rollout in design["rollouts"]
        for cycle in rollout["cycles"]
    )
    assert all(
        math.hypot(*cycle["direction_local"])
        == pytest.approx(cycle["horizontal_reach_m"] / cycle["cut_length_m"])
        for rollout in design["rollouts"]
        for cycle in rollout["cycles"]
    )


def test_balanced_order_places_each_cell_three_times_in_each_rollout_position() -> None:
    design = build_controlled_planned_cut_design(seed=9)
    positions = Counter()
    for rollout in design["rollouts"]:
        for position, cycle in enumerate(rollout["cycles"]):
            positions[(position, cycle["cell_id"])] += 1

    assert set(positions.values()) == {3}


def test_each_direction_is_explicitly_toward_box_interior() -> None:
    design = build_controlled_planned_cut_design(seed=0)

    for rollout in design["rollouts"]:
        for cycle in rollout["cycles"]:
            entry = cycle["entry_local_m"]
            exit_point = cycle["exit_local_m"]
            if cycle["direction_axis"] == "long":
                assert abs(exit_point[0]) <= abs(entry[0]) or entry[0] == 0.0
                assert exit_point[1] == entry[1]
            else:
                assert abs(exit_point[1]) <= abs(entry[1])
                assert exit_point[0] == entry[0]
