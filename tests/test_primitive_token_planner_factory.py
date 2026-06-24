from __future__ import annotations

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.v2_1 import build_goal_tokens
from testbed.planner.primitive.token.factory import (
    PrimitiveTokenPlannerFactory,
    PrimitiveTokenPlannerFactoryConfig,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


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
        },
        "dig_depth_profile_cells": [
            {
                "cell_id": 3,
                "token_median": np.arange(
                    DIG_DEPTH_PROFILE_TOKEN_DIM,
                    dtype=np.float32,
                ).tolist(),
            }
        ],
        "return_start_envelope_cells": [
            {
                "cell_id": 3,
                "source_count": 4,
                "source_fraction": 0.75,
                "token_median": np.arange(
                    RETURN_START_ENVELOPE_TOKEN_DIM,
                    dtype=np.float32,
                ).tolist(),
            }
        ],
    }


def _factory() -> PrimitiveTokenPlannerFactory:
    qpos_coefficients = np.zeros((4, 8), dtype=np.float32)
    qpos_coefficients[:, 0] = [0.11, 0.22, 0.33, 0.44]
    spatial_coefficients = np.zeros((2, 8), dtype=np.float32)
    spatial_coefficients[:, 0] = [-0.5, 0.6]
    return PrimitiveTokenPlannerFactory(
        PrimitiveTokenPlannerFactoryConfig(
            goal_sequence=(1, 0, 2),
            goal_scenario_id="s0_truck",
            goal_depth_norm=0.25,
            goal_dump_target_norm=0.75,
            dig_cut_prior=_prior(),
            dig_depth_profile_source="prior_profile",
            dig_depth_profile_required=True,
            dig_depth_profile_allow_live_fallback=False,
            dig_depth_profile_allow_global_fallback=True,
            return_target_token_source_prefix="conditioned_return",
            return_start_envelope_use_cell_prior=True,
            return_start_envelope_min_source_count=2,
            return_start_envelope_min_source_fraction=0.5,
            return_start_envelope_qpos_from_relocate_enabled=True,
            return_start_envelope_qpos_from_relocate_coefficients=qpos_coefficients,
            return_start_envelope_qpos_from_relocate_min=np.full(
                4,
                -1.0,
                dtype=np.float32,
            ),
            return_start_envelope_qpos_from_relocate_max=np.full(
                4,
                1.0,
                dtype=np.float32,
            ),
            return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds=False,
            return_start_envelope_spatial_from_relocate_enabled=True,
            return_start_envelope_spatial_from_relocate_coefficients=(
                spatial_coefficients
            ),
            return_start_envelope_spatial_from_relocate_min=np.full(
                2,
                -1.0,
                dtype=np.float32,
            ),
            return_start_envelope_spatial_from_relocate_max=np.full(
                2,
                1.0,
                dtype=np.float32,
            ),
            return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds=(
                False
            ),
        )
    )


def test_token_planner_factory_builds_goal_tokens_and_sector_ids() -> None:
    factory = _factory()

    token = factory.goal_tokens_for_cycle(0)

    expected = build_goal_tokens(
        "s0_truck",
        curr_sector_id=1,
        curr_cut_depth_norm=0.25,
        next_sector_id=0,
        next_cut_depth_norm=0.25,
        dst_target_norm=0.75,
        has_lookahead=True,
    )
    assert token is not None
    np.testing.assert_allclose(token, expected)
    assert factory.goal_sector_id(0) == 1
    assert factory.next_goal_sector_id(0) == 0


def test_token_planner_factory_preserves_dig_and_return_planner_config() -> None:
    factory = _factory()

    assert factory.dig_cut_token_planner().prior == _prior()

    depth_planner = factory.dig_depth_profile_token_planner()
    assert depth_planner.prior == _prior()
    assert depth_planner.source == "prior_profile"
    assert depth_planner.required is True
    assert depth_planner.allow_live_fallback is False
    assert depth_planner.allow_global_fallback is True

    target_planner = factory.return_target_token_planner()
    assert target_planner.source_prefix == "conditioned_return"
    assert target_planner.dig_cut_planner.prior == _prior()

    relocate_token = factory.return_relocate_token_planner().plan(
        np.arange(10, dtype=np.float32)
    )
    assert float(relocate_token[7]) == 0.0
    assert float(relocate_token[8]) == 0.0


def test_token_planner_factory_preserves_return_start_envelope_config() -> None:
    factory = _factory()

    planner = factory.return_start_envelope_token_planner()

    assert planner.prior == _prior()
    assert planner.use_cell_prior is True
    assert planner.min_source_count == 2
    assert planner.min_source_fraction == 0.5
    assert planner.conditioning.qpos_enabled is True
    assert planner.conditioning.spatial_enabled is True
    assert planner.conditioning.qpos_use_prior_bounds is False
    assert planner.conditioning.spatial_use_prior_bounds is False
    np.testing.assert_allclose(
        planner.conditioning.qpos_coefficients[:, 0],
        [0.11, 0.22, 0.33, 0.44],
    )
    np.testing.assert_allclose(
        planner.conditioning.spatial_coefficients[:, 0],
        [-0.5, 0.6],
    )


def test_policy_no_longer_exposes_private_token_planner_factory_methods() -> None:
    retired_names = (
        "_prior_percentile",
        "_clamp_to_prior",
        "_goal_tokens",
        "_goal_sector_id",
        "_next_goal_sector_id",
        "_goal_token_provider",
        "_dig_cut_token_planner",
        "_dig_depth_profile_token_planner",
        "_return_target_token_planner",
        "_return_relocate_token_planner",
        "_return_start_envelope_token_planner",
    )

    for name in retired_names:
        assert not hasattr(PrimitivePlannerACTPolicy, name)
