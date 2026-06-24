from __future__ import annotations

import numpy as np

from testbed.data.operator_first_v2_2 import (
    _build_dig_cut_token,
    build_live_dig_cut_tokens_from_pose,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner


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


def test_dig_cut_token_planner_builds_conservative_pose_plan() -> None:
    planner = DigCutTokenPlanner(prior={})

    plan = planner.plan_conservative_pose((0.5, 0.25, 0.75))

    np.testing.assert_allclose(
        plan.token,
        build_live_dig_cut_tokens_from_pose((0.5, 0.25, 0.75)),
    )
    assert plan.source == "conservative_pose"
    assert plan.fallback_reason == ""
    assert plan.in_prior_p10_p90 is False
    assert plan.raw_fields["operator_entry_x_m"] == 0.5
    assert plan.raw_fields["operator_cut_valid"] == 1


def test_dig_cut_token_planner_builds_operator_prior_pose_clamped_plan() -> None:
    planner = DigCutTokenPlanner(prior=_prior())

    plan = planner.plan_operator_prior((0.5, 0.25, 0.75))

    assert plan.source == "operator_prior_pose_clamped"
    assert plan.fallback_reason == ""
    assert plan.in_prior_p10_p90 is True
    assert plan.raw_fields["operator_entry_x_m"] == 0.0
    assert plan.raw_fields["operator_entry_y_m"] == 0.25
    np.testing.assert_allclose(plan.token, _build_dig_cut_token(plan.raw_fields))


def test_dig_cut_token_planner_uses_prior_median_when_pose_missing() -> None:
    planner = DigCutTokenPlanner(prior=_prior())

    plan = planner.plan_operator_prior(None)

    assert plan.source == "operator_prior_median_pose_fallback"
    assert plan.fallback_reason == "missing_bucket_dig_area_pose"
    assert plan.in_prior_p10_p90 is True
    assert plan.raw_fields["operator_entry_x_m"] == -0.5
    assert plan.raw_fields["operator_entry_y_m"] == 0.0


def test_dig_cut_token_planner_copies_pending_return_target_tokens() -> None:
    planner = DigCutTokenPlanner(prior=_prior())
    token = np.arange(10, dtype=np.float32)
    raw_fields = planner.raw_fields_from_live_pose((0.0, 0.25, 0.75))

    plan = planner.plan_pending_return_target(tokens=token, raw_fields=raw_fields)

    token[0] = 99.0
    assert plan.source == "pending_return_target"
    assert plan.fallback_reason == ""
    assert plan.in_prior_p10_p90 is True
    assert float(plan.token[0]) == 0.0


def test_dig_cut_token_planner_builds_coverage_raw_fields_plan() -> None:
    planner = DigCutTokenPlanner(prior=_prior())
    raw_fields = planner.raw_fields_from_live_pose((0.0, 0.25, 0.75))

    plan = planner.plan_from_raw_fields(
        raw_fields,
        source="operator_prior_coverage",
    )

    assert plan.source == "operator_prior_coverage"
    assert plan.fallback_reason == ""
    assert plan.in_prior_p10_p90 is True
    np.testing.assert_allclose(plan.token, _build_dig_cut_token(raw_fields))
