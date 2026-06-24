from __future__ import annotations

import numpy as np

from testbed.data.operator_first_v2_2 import _build_dig_cut_token
from testbed.planner.primitive.token.tokens import (
    DigCutTokenPlanner,
    ReturnTargetTokenPlanner,
)


def _prior() -> dict[str, object]:
    def field(p10: float, p50: float, p90: float) -> dict[str, float]:
        return {"p10": p10, "p50": p50, "p90": p90}

    return {
        "fields": {
            "entry_x_m": field(-1.0, -0.5, 0.0),
            "entry_z_m": field(0.0, 0.25, 1.0),
            "exit_x_m": field(-2.0, -1.0, -0.5),
            "exit_z_m": field(0.0, 0.25, 1.0),
            "cut_direction_x": field(-1.0, -1.0, 0.0),
            "cut_direction_z": field(-0.5, 0.0, 0.5),
            "cut_length_m": field(0.5, 1.0, 1.5),
            "cut_depth_peak_m": field(0.03, 0.08, 0.12),
            "payload_gain_kg": field(20.0, 55.0, 90.0),
            "effective_deposit_delta_kg": field(10.0, 45.0, 80.0),
        }
    }


def test_return_target_token_planner_builds_conservative_pose_plan() -> None:
    planner = ReturnTargetTokenPlanner(
        dig_cut_planner=DigCutTokenPlanner(prior={}),
        source_prefix="conditioned_return",
    )

    plan = planner.plan_conservative_pose((0.0, 0.25, 0.75))

    assert plan.source == "conditioned_return_conservative_pose"
    assert plan.fallback_reason == ""
    assert plan.corridor_id == -1
    np.testing.assert_allclose(plan.token, _build_dig_cut_token(plan.raw_fields))


def test_return_target_token_planner_prefixes_operator_prior_source() -> None:
    planner = ReturnTargetTokenPlanner(
        dig_cut_planner=DigCutTokenPlanner(prior=_prior()),
        source_prefix="conditioned_return",
    )

    plan = planner.plan_operator_prior((0.0, 0.25, 0.75))

    assert plan.source == "conditioned_return_operator_prior_pose_clamped"
    assert plan.fallback_reason == ""
    assert plan.corridor_id == -1
    np.testing.assert_allclose(plan.token, _build_dig_cut_token(plan.raw_fields))


def test_return_target_token_planner_wraps_coverage_raw_fields() -> None:
    dig_cut_planner = DigCutTokenPlanner(prior=_prior())
    planner = ReturnTargetTokenPlanner(
        dig_cut_planner=dig_cut_planner,
        source_prefix="conditioned_return",
    )
    raw_fields = dig_cut_planner.raw_fields_from_live_pose((0.0, 0.25, 0.75))

    plan = planner.plan_from_coverage_raw_fields(
        raw_fields,
        dig_cut_planner_mode="operator_prior_sweep_belief",
        corridor_id=4,
    )

    assert plan.source == "conditioned_return_operator_prior_sweep_belief"
    assert plan.fallback_reason == ""
    assert plan.corridor_id == 4
    np.testing.assert_allclose(plan.token, _build_dig_cut_token(raw_fields))
