from __future__ import annotations

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import build_live_dig_cut_tokens_from_pose
from testbed.planner.dig_cut_plan import (
    OperatorPriorDigCutPlanRequest,
    build_conservative_pose_dig_cut_plan,
    build_operator_prior_dig_cut_plan,
)


def test_operator_prior_clamps_pose_and_builds_token() -> None:
    plan = build_operator_prior_dig_cut_plan(
        OperatorPriorDigCutPlanRequest(
            dig_cut_prior=_prior(),
            bucket_dig_area_pose=(2.5, 0.25, -2.0),
        )
    )

    assert plan.source == "operator_prior_pose_clamped"
    assert plan.fallback_reason == ""
    assert plan.raw_fields["operator_entry_x_m"] == pytest.approx(1.0)
    assert plan.raw_fields["operator_entry_y_m"] == pytest.approx(0.25)
    assert plan.raw_fields["operator_entry_z_m"] == pytest.approx(-1.0)
    assert plan.raw_fields["operator_exit_x_m"] == pytest.approx(0.0)
    assert plan.raw_fields["operator_exit_z_m"] == pytest.approx(-1.0)
    assert plan.raw_fields["operator_cut_direction_x"] == pytest.approx(-1.0)
    assert plan.raw_fields["operator_cut_direction_z"] == pytest.approx(0.0)
    assert plan.raw_fields["operator_cut_length_m"] == pytest.approx(1.0)
    assert plan.raw_fields["operator_cut_depth_peak_m"] == pytest.approx(0.08)
    assert plan.raw_fields["operator_cut_payload_gain_kg"] == pytest.approx(40.0)
    assert plan.raw_fields["operator_effective_deposit_delta_kg"] == pytest.approx(
        38.0
    )
    np.testing.assert_allclose(
        plan.token,
        np.asarray(
            [0.5, -0.5, 0.0, -0.5, -1.0, 0.0, 0.5, 0.1, 2.0 / 3.0, 1.0],
            dtype=np.float32,
        ),
    )


def test_operator_prior_uses_median_pose_fallback_when_pose_missing() -> None:
    plan = build_operator_prior_dig_cut_plan(
        OperatorPriorDigCutPlanRequest(
            dig_cut_prior=_prior(),
            bucket_dig_area_pose=None,
        )
    )

    assert plan.source == "operator_prior_median_pose_fallback"
    assert plan.fallback_reason == "missing_bucket_dig_area_pose"
    assert plan.raw_fields["operator_entry_x_m"] == pytest.approx(0.5)
    assert plan.raw_fields["operator_entry_y_m"] == pytest.approx(0.0)
    assert plan.raw_fields["operator_entry_z_m"] == pytest.approx(-0.5)
    assert plan.raw_fields["operator_exit_x_m"] == pytest.approx(-0.5)
    assert plan.raw_fields["operator_exit_z_m"] == pytest.approx(-0.5)
    np.testing.assert_allclose(
        plan.token,
        np.asarray(
            [0.25, -0.25, -0.25, -0.25, -1.0, 0.0, 0.5, 0.1, 2.0 / 3.0, 1.0],
            dtype=np.float32,
        ),
    )


def test_operator_prior_requires_prior_json() -> None:
    with pytest.raises(
        ValueError,
        match="operator_prior mode requires a dig cut prior JSON",
    ):
        build_operator_prior_dig_cut_plan(
            OperatorPriorDigCutPlanRequest(
                dig_cut_prior={},
                bucket_dig_area_pose=(0.0, 0.0, 0.0),
            )
        )


def test_conservative_pose_plan_matches_live_token_builder() -> None:
    pose = (0.8, 0.0, -0.3)

    plan = build_conservative_pose_dig_cut_plan(
        pose,
        source="fallback_conservative_pose",
        fallback_reason="missing prior field",
    )

    assert plan.source == "fallback_conservative_pose"
    assert plan.fallback_reason == "missing prior field"
    assert plan.raw_fields["operator_entry_x_m"] == pytest.approx(0.8)
    assert plan.raw_fields["operator_exit_x_m"] == pytest.approx(-0.4)
    assert plan.raw_fields["operator_cut_valid"] == 1
    np.testing.assert_allclose(
        plan.token,
        build_live_dig_cut_tokens_from_pose(pose),
    )


def _prior() -> dict[str, object]:
    return {
        "fields": {
            "entry_x_m": _field(0.0, 0.5, 1.0),
            "entry_z_m": _field(-1.0, -0.5, 0.0),
            "exit_x_m": _field(-1.2, -0.5, 0.0),
            "exit_z_m": _field(-1.0, -0.5, 0.0),
            "cut_direction_x": _field(-1.0, -0.6, -0.2),
            "cut_direction_z": _field(-0.4, 0.0, 0.4),
            "cut_length_m": _field(0.5, 1.0, 1.5),
            "cut_depth_peak_m": _field(0.04, 0.08, 0.16),
            "payload_gain_kg": _field(20.0, 40.0, 60.0),
            "effective_deposit_delta_kg": _field(20.0, 38.0, 58.0),
        }
    }


def _field(p10: float, p50: float, p90: float) -> dict[str, float]:
    return {"p10": p10, "p50": p50, "p90": p90}
