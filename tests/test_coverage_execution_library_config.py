from __future__ import annotations

import pytest

from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.planner.primitive.coverage.config import (
    CoverageExecutionLibraryConfig,
)
from testbed.planner.primitive.coverage.worktool_sweep import (
    UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE,
)


def test_execution_library_config_is_disabled_by_default() -> None:
    config = CoverageExecutionLibraryConfig.from_mapping(None)

    assert config.enabled is False
    assert config.path == ""
    assert config.artifact_sha256 == ""
    assert config.mode == "exact_k1"
    assert config.missing_contract == "fail_closed"
    assert config.hard_bottom_margin_m == 0.02
    assert config.first_plan_pose_stability.enabled is False
    assert config.worktool_sweep_3d.enabled is False
    assert config.start_reachability.enabled is False


def test_enabled_execution_library_requires_path_and_sha() -> None:
    with pytest.raises(ValueError, match="requires path"):
        CoverageExecutionLibraryConfig.from_mapping({"enabled": True})

    with pytest.raises(ValueError, match="requires artifact_sha256"):
        CoverageExecutionLibraryConfig.from_mapping(
            {"enabled": True, "path": "/tmp/library.json"}
        )


def test_execution_library_rejects_semantic_fallbacks() -> None:
    with pytest.raises(ValueError, match="mode must be 'exact_k1'"):
        CoverageExecutionLibraryConfig.from_mapping(
            {
                "enabled": True,
                "path": "/tmp/library.json",
                "artifact_sha256": "a" * 64,
                "mode": "weighted_k5",
            }
        )
    with pytest.raises(ValueError, match="missing_contract must be 'fail_closed'"):
        CoverageExecutionLibraryConfig.from_mapping(
            {
                "enabled": True,
                "path": "/tmp/library.json",
                "artifact_sha256": "a" * 64,
                "missing_contract": "median_fallback",
            }
        )


def test_adapter_exposes_exact_tuple_library_config() -> None:
    state = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            dig_cut_planner={
                "coverage": {
                    "actual_tuple_execution_library": {
                        "enabled": True,
                        "path": "/tmp/library.json",
                        "artifact_sha256": "b" * 64,
                        "mode": "exact_k1",
                        "missing_contract": "fail_closed",
                        "hard_bottom_margin_m": 0.02,
                        "first_plan_pose_stability": {
                            "enabled": True,
                            "hold_steps": 3,
                            "max_step_delta_m": 0.05,
                            "max_wait_steps": 30,
                        },
                        "worktool_sweep_3d": {
                            "enabled": True,
                            "profile": (
                                UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE
                            ),
                            "hard_clearance_m": 0.30,
                            "act_tracking_margin_m": 0.15,
                            "pose_interpolation_bound_m": 0.01,
                            "artifact_path": "/tmp/sweep.json",
                            "artifact_sha256": "c" * 64,
                            "execution_library_sha256": "b" * 64,
                            "pose_library_sha256": "d" * 64,
                            "missing_contract": "fail_closed",
                        },
                        "start_reachability": {
                            "enabled": True,
                            "profile": (
                                "strict_train_return_start_reachability_11d_v1"
                            ),
                            "artifact_path": "/tmp/return-transitions.json",
                            "artifact_sha256": "e" * 64,
                            "execution_library_sha256": "b" * 64,
                            "missing_contract": "fail_closed",
                        },
                    }
                }
            }
        )
    )

    config = state.as_policy_field_updates()[
        "coverage_execution_library_config"
    ]
    assert isinstance(config, CoverageExecutionLibraryConfig)
    assert config.enabled is True
    assert config.path == "/tmp/library.json"
    assert config.artifact_sha256 == "b" * 64
    assert config.first_plan_pose_stability.enabled is True
    assert config.first_plan_pose_stability.hold_steps == 3
    assert config.first_plan_pose_stability.max_step_delta_m == 0.05
    assert config.first_plan_pose_stability.max_wait_steps == 30
    assert config.worktool_sweep_3d.enabled is True
    assert config.worktool_sweep_3d.hard_clearance_m == 0.30
    assert config.worktool_sweep_3d.execution_library_sha256 == "b" * 64
    assert config.start_reachability.enabled is True
    assert config.start_reachability.execution_library_sha256 == "b" * 64


def test_3d_sweep_execution_sha_must_match_parent_library() -> None:
    with pytest.raises(ValueError, match="execution_library_sha256"):
        CoverageExecutionLibraryConfig.from_mapping(
            {
                "enabled": True,
                "path": "/tmp/library.json",
                "artifact_sha256": "a" * 64,
                "worktool_sweep_3d": {
                    "enabled": True,
                    "artifact_path": "/tmp/sweep.json",
                    "artifact_sha256": "b" * 64,
                    "execution_library_sha256": "c" * 64,
                    "pose_library_sha256": "d" * 64,
                },
            }
        )


def test_start_reachability_execution_sha_must_match_parent_library() -> None:
    with pytest.raises(ValueError, match="start_reachability"):
        CoverageExecutionLibraryConfig.from_mapping(
            {
                "enabled": True,
                "path": "/tmp/library.json",
                "artifact_sha256": "a" * 64,
                "start_reachability": {
                    "enabled": True,
                    "artifact_path": "/tmp/return-transitions.json",
                    "artifact_sha256": "b" * 64,
                    "execution_library_sha256": "c" * 64,
                },
            }
        )
