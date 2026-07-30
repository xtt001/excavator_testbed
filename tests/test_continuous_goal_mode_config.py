from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
    validate_dig_cut_planner_config,
)
from testbed.planner.primitive.coverage.config import (
    CoverageExecutionLibraryConfig,
)
from testbed.planner.primitive.token.dig_planning import (
    DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED,
    DIG_CUT_PLANNER_MODES_REQUIRING_PRIOR,
    SUPPORTED_DIG_CUT_PLANNER_MODES,
)


def test_continuous_goal_mode_is_supported_without_a_prior() -> None:
    assert (
        DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED
        in SUPPORTED_DIG_CUT_PLANNER_MODES
    )
    assert (
        DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED
        not in DIG_CUT_PLANNER_MODES_REQUIRING_PRIOR
    )

    validate_dig_cut_planner_config(
        dig_cut_planner_enabled=True,
        dig_cut_planner_mode=(
            DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED
        ),
        dig_cut_planner_fallback_mode="raise",
        dig_cut_prior_path="",
        coverage_candidate_layout="cell_weighted_3x2",
        dig_depth_profile_source="live_plan",
        dig_depth_profile_required=False,
        dig_depth_profile_allow_live_fallback=True,
        dig_cut_prior={},
    )


def test_exact_tuple_library_is_explicitly_diagnostic_legacy() -> None:
    disabled = CoverageExecutionLibraryConfig.from_mapping(None)
    assert disabled.runtime_role == "diagnostic_legacy"

    configured = CoverageExecutionLibraryConfig.from_mapping(
        {
            "enabled": True,
            "path": "/tmp/diagnostic-library.json",
            "artifact_sha256": "a" * 64,
            "mode": "exact_k1",
            "runtime_role": "diagnostic_legacy",
        }
    )
    configured.validate_for_planner_mode("operator_prior_sweep_belief")


def test_continuous_goal_mode_rejects_enabled_exact_tuple_runtime() -> None:
    configured = CoverageExecutionLibraryConfig.from_mapping(
        {
            "enabled": True,
            "path": "/tmp/diagnostic-library.json",
            "artifact_sha256": "a" * 64,
            "mode": "exact_k1",
        }
    )
    with pytest.raises(
        ValueError,
        match="continuous_goal_conditioned.*diagnostic exact-tuple",
    ):
        configured.validate_for_planner_mode(
            DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED
        )


def test_continuous_goal_mode_does_not_require_profile_prior() -> None:
    validate_dig_cut_planner_config(
        dig_cut_planner_enabled=True,
        dig_cut_planner_mode=(
            DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED
        ),
        dig_cut_planner_fallback_mode="raise",
        dig_cut_prior_path="",
        coverage_candidate_layout="cell_weighted_3x2",
        dig_depth_profile_source="live_plan",
        dig_depth_profile_required=False,
        dig_depth_profile_allow_live_fallback=True,
        dig_cut_prior={"fields": {"unused": np.asarray([1.0])}},
    )


def test_continuous_goal_mode_requires_raise_fallback_and_locked_tokens() -> None:
    with pytest.raises(
        ValueError,
        match="continuous_goal_conditioned.*fallback_mode='raise'",
    ):
        validate_dig_cut_planner_config(
            dig_cut_planner_enabled=True,
            dig_cut_planner_mode=(
                DIG_CUT_PLANNER_MODE_CONTINUOUS_GOAL_CONDITIONED
            ),
            dig_cut_planner_fallback_mode="conservative_pose",
            dig_cut_prior_path="",
            coverage_candidate_layout="cell_weighted_3x2",
            dig_depth_profile_source="live_plan",
            dig_depth_profile_required=False,
            dig_depth_profile_allow_live_fallback=True,
            dig_cut_prior={},
        )

    for dig_hold, return_hold in ((False, True), (True, False)):
        with pytest.raises(ValueError, match="requires dig and return.*hold"):
            PrimitivePlannerAdapterConfigNormalizer.normalize(
                PrimitivePlannerAdapterConfigInputs(
                    dig_cut_planner={
                        "mode": "continuous_goal_conditioned",
                        "fallback_mode": "raise",
                        "hold_token_until_skill_exit": dig_hold,
                    },
                    return_target_planner={
                        "enabled": True,
                        "hold_token_until_skill_exit": return_hold,
                    },
                )
            )


def test_continuous_goal_mode_requires_existing_safety_and_return_gates() -> None:
    with pytest.raises(ValueError, match="requires coverage.wall_safety"):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                dig_cut_planner={
                    "mode": "continuous_goal_conditioned",
                    "fallback_mode": "raise",
                },
                return_target_planner={"enabled": True},
                box_emptying={"safety_enabled": True},
                return_to_dig_start_envelope_gate_enabled=True,
            )
        )

    state = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            dig_cut_planner={
                "mode": "continuous_goal_conditioned",
                "fallback_mode": "raise",
                "coverage": {"wall_safety": {"enabled": True}},
            },
            return_target_planner={"enabled": True},
            box_emptying={"safety_enabled": True},
            return_to_dig_start_envelope_gate_enabled=True,
        )
    )
    updates = state.as_policy_field_updates()
    assert updates["coverage_wall_safety_config"].enabled is True
    assert updates["box_emptying_safety_enabled"] is True
    assert updates["return_target_planner_enabled"] is True
    assert updates["return_to_dig_start_envelope_gate_enabled"] is True


@pytest.mark.parametrize(
    "legacy_return_config",
    [
        {"use_cell_prior": True},
        {"qpos_from_relocate": {"enabled": True}},
        {"spatial_from_relocate": {"enabled": True}},
    ],
)
def test_continuous_goal_mode_rejects_legacy_return_sources(
    legacy_return_config: dict[str, object],
) -> None:
    with pytest.raises(
        ValueError,
        match="continuous_goal_conditioned forbids legacy return",
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                dig_cut_planner={
                    "mode": "continuous_goal_conditioned",
                    "fallback_mode": "raise",
                    "return_start_envelope": legacy_return_config,
                    "coverage": {"wall_safety": {"enabled": True}},
                },
                return_target_planner={"enabled": True},
                box_emptying={"safety_enabled": True},
                return_to_dig_start_envelope_gate_enabled=True,
            )
        )
