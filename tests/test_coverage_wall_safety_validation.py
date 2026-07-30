from __future__ import annotations

import copy

import pytest

from testbed.eval.coverage_wall_safety_validation import (
    CoverageWallSafetyRolloutValidationError,
    load_coverage_wall_safety_rollout_contract,
    validate_coverage_wall_safety_rollout,
)


def _resolved_config() -> dict[str, object]:
    return {
        "task": {
            "camera_names": [
                "stick_up",
                "stick_down",
                "eye_left",
                "eye_right",
            ]
        },
        "eval": {
            "record_hdf5_metadata": {
                "temporal_variant": "A0",
                "planner_safety_variant": "coverage_wall_safety_v1",
            }
        },
        "policy": {
            "act_params": {
                "temporal_agg_window": 100,
                "temporal_agg_weight_order": "legacy_oldest_first",
            },
            "dig_cut_planner": {
                "coverage": {
                    "wall_safety": {
                        "enabled": True,
                        "profile": (
                            "conservative_2d_worktool_swept_footprint_v1"
                        ),
                        "worktool_width_m": 0.70,
                        "hard_clearance_m": 0.30,
                        "soft_clearance_m": 0.45,
                        "max_score_penalty": 1.0,
                        "missing_geometry": "fail_closed",
                    }
                }
            },
        },
    }


def _wall_safe_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cycle in range(10):
        corridor_id = 2 + cycle % 4
        cell_id = corridor_id
        candidate_scores = [
            {
                "corridor_id": 0,
                "cell_id": 0,
                "selectable": 0,
                "depleted": 0,
                "wall_safety_eligible": 0,
                "wall_minimum_clearance_m": 0.12,
                "rejection_reason": "wall_hard_clearance",
            },
            {
                "corridor_id": corridor_id,
                "cell_id": cell_id,
                "selectable": 1,
                "depleted": 0,
                "wall_safety_eligible": 1,
                "wall_minimum_clearance_m": 0.31,
                "rejection_reason": "",
            },
        ]
        rows.append(
            {
                "step_id": cycle,
                "primitive_cycle_index": cycle,
                "skill_name": "dig",
                "planned_cut_cell_id": cell_id,
                "coverage_corridor_id": corridor_id,
                "coverage_wall_safety_profile": (
                    "conservative_2d_worktool_swept_footprint_v1"
                ),
                "coverage_wall_safety_class": "near_wall",
                "coverage_wall_safety_eligible": True,
                "coverage_wall_minimum_clearance_m": 0.31,
                "coverage_wall_rejected_corridor_ids": [],
                "coverage_wall_rejected_cell_ids": [],
                "coverage_candidate_scores": candidate_scores,
            }
        )
    return rows


def test_wall_safe_rollout_contract_locks_a0_and_accepts_safe_selections() -> None:
    contract = load_coverage_wall_safety_rollout_contract(_resolved_config())

    evidence = validate_coverage_wall_safety_rollout(
        rows=_wall_safe_rows(),
        contract=contract,
    )

    assert evidence["status"] == "passed"
    assert evidence["temporal_agg_window"] == 100
    assert evidence["temporal_agg_weight_order"] == "legacy_oldest_first"
    assert evidence["selected_corridor_count"] == 10
    assert evidence["minimum_selected_clearance_m"] == pytest.approx(0.31)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda rows: rows[3].update(
                {"coverage_wall_minimum_clearance_m": 0.299}
            ),
            "selected_clearance_below_hard_limit",
        ),
        (
            lambda rows: rows[3]["coverage_candidate_scores"][1].update(
                {"selectable": 0, "rejection_reason": "corridor_depleted"}
            ),
            "selected_candidate_not_selectable",
        ),
        (
            lambda rows: rows[3].update(
                {"coverage_wall_rejected_corridor_ids": [5]}
            ),
            "selected_corridor_was_wall_rejected",
        ),
        (
            lambda rows: rows[3]["coverage_candidate_scores"][1].update(
                {"depleted": 1}
            ),
            "selected_candidate_depleted",
        ),
    ],
)
def test_wall_safe_rollout_contract_fails_closed_on_execution_evidence(
    mutate,
    reason: str,
) -> None:
    rows = _wall_safe_rows()
    mutate(rows)

    with pytest.raises(
        CoverageWallSafetyRolloutValidationError,
        match=reason,
    ):
        validate_coverage_wall_safety_rollout(
            rows=rows,
            contract=load_coverage_wall_safety_rollout_contract(
                _resolved_config()
            ),
        )


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (
            ("policy", "act_params", "temporal_agg_window"),
            20,
            "a0_temporal_agg_window_mismatch",
        ),
        (
            ("policy", "act_params", "temporal_agg_weight_order"),
            "newest_first",
            "a0_temporal_agg_weight_order_mismatch",
        ),
        (
            (
                "eval",
                "record_hdf5_metadata",
                "planner_safety_variant",
            ),
            "",
            "planner_safety_variant_mismatch",
        ),
    ],
)
def test_wall_safe_rollout_contract_rejects_non_a0_resolved_config(
    path: tuple[str, ...],
    value: object,
    reason: str,
) -> None:
    config = copy.deepcopy(_resolved_config())
    node = config
    for key in path[:-1]:
        node = node[key]  # type: ignore[index,assignment]
    node[path[-1]] = value  # type: ignore[index]

    with pytest.raises(
        CoverageWallSafetyRolloutValidationError,
        match=reason,
    ):
        load_coverage_wall_safety_rollout_contract(config)
