"""Deterministic 108-cycle frozen-ACT planned-cut experiment design."""

from __future__ import annotations

import math
import random
from typing import Any

SCHEMA = "planned_cut_controlled_experiment_v1"
DEPTHS_M = (0.10, 0.35, 0.55)
DIRECTION_AXES = ("long", "short")


def build_controlled_planned_cut_design(*, seed: int = 0) -> dict[str, Any]:
    """Build 18 six-cut rollouts with balanced cell order and three resets."""

    base_order = list(range(6))
    random.Random(int(seed)).shuffle(base_order)
    strata = [
        (direction_axis, depth_m, reset_index)
        for reset_index in range(3)
        for direction_axis in DIRECTION_AXES
        for depth_m in DEPTHS_M
    ]
    rollouts: list[dict[str, Any]] = []
    global_cycle_index = 0
    for rollout_index, (direction_axis, depth_m, reset_index) in enumerate(strata):
        shift = rollout_index % 6
        cell_order = base_order[shift:] + base_order[:shift]
        cycles: list[dict[str, Any]] = []
        cut_length_m = 0.75
        horizontal_reach_m = math.sqrt(cut_length_m**2 - depth_m**2)
        horizontal_direction_scale = horizontal_reach_m / cut_length_m
        for rollout_position, cell_id in enumerate(cell_order):
            row, col = divmod(cell_id, 2)
            long_coordinate = float(row - 1)
            short_coordinate = float((col - 0.5) * 1.25)
            if direction_axis == "long":
                direction_sign = 1.0 if long_coordinate <= 0.0 else -1.0
                exit_point = [
                    long_coordinate + horizontal_reach_m * direction_sign,
                    short_coordinate,
                ]
                direction = [
                    direction_sign * horizontal_direction_scale,
                    0.0,
                ]
            else:
                direction_sign = 1.0 if short_coordinate < 0.0 else -1.0
                exit_point = [
                    long_coordinate,
                    short_coordinate + horizontal_reach_m * direction_sign,
                ]
                direction = [
                    0.0,
                    direction_sign * horizontal_direction_scale,
                ]
            cycles.append(
                {
                    "schema": "planned_cut_experiment_cycle_v1",
                    "global_cycle_index": global_cycle_index,
                    "rollout_position": rollout_position,
                    "cell_id": cell_id,
                    "cell_row": row,
                    "cell_col": col,
                    "entry_local_m": [long_coordinate, short_coordinate],
                    "exit_local_m": exit_point,
                    "direction_local": direction,
                    "direction_axis": direction_axis,
                    "planned_depth_m": float(depth_m),
                    "cut_length_m": cut_length_m,
                    "horizontal_reach_m": horizontal_reach_m,
                    "direction_y": -float(depth_m) / cut_length_m,
                    "planned_payload_target_kg": 60.0,
                    "wall_inset_m": 0.30,
                }
            )
            global_cycle_index += 1
        rollouts.append(
            {
                "rollout_id": f"planned-cut-{rollout_index:02d}",
                "independent_reset_index": int(reset_index),
                "direction_axis": direction_axis,
                "planned_depth_m": float(depth_m),
                "cell_order": cell_order,
                "cycles": cycles,
            }
        )
    return {
        "schema": SCHEMA,
        "source": "frozen_act_controlled_planned_cut_design",
        "seed": int(seed),
        "rollout_count": len(rollouts),
        "cycle_count": global_cycle_index,
        "cell_count": 6,
        "depths_m": list(DEPTHS_M),
        "direction_axes": list(DIRECTION_AXES),
        "repeats_per_combination": 3,
        "rollouts": rollouts,
    }


__all__ = ["build_controlled_planned_cut_design"]
