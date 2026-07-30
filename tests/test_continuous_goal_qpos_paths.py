from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from testbed.data.continuous_goal_qpos_paths import (
    CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1,
    CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2,
    PATH_PROGRESS,
    ContinuousGoalQposPathContractError,
    ContinuousGoalWorktoolSweepInputV2,
    LegacyContinuousGoalWorktoolSweepInputV1,
    evaluate_qpos_bspline,
    fit_qpos_bspline,
    predictor_feature_map,
    read_continuous_goal_worktool_sweep_input,
    resample_qpos_path_by_joint_arc_length,
)
from testbed.data.schema import ENV_STATE_ORDER_V2_3


def _goal() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "continuous_cut_goal_v1",
        "target_cell_id": 2,
        "entry_xz_m": [0.2, 0.4],
        "exit_xz_m": [0.5, 0.8],
        "direction_xz": [0.6, 0.8],
        "cut_length_m": 0.5,
        "planned_depth_m": 0.12,
        "payload_intent_kg": 45.0,
        "effect_intent": {
            "kind": "remove_soil",
            "target_mass_kg": 45.0,
        },
        "terrain_signature": {"schema": "terrain_signature_v1"},
    }
    payload["goal_id"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _request() -> ContinuousGoalWorktoolSweepInputV2:
    return ContinuousGoalWorktoolSweepInputV2.create(
        handoff_qpos=[0.1, 0.2, 0.3, 0.4],
        handoff_qvel=[0.01, 0.02, 0.03, 0.04],
        continuous_goal=_goal(),
        terrain_signature={
            "schema": "terrain_signature_v1",
            "field_names": list(ENV_STATE_ORDER_V2_3),
            "values": np.linspace(0.0, 1.0, 89).tolist(),
        },
    )


def test_v2_input_locks_live_handoff_goal_and_89d_terrain() -> None:
    request = _request()

    assert request.schema == CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2
    assert request.handoff_qpos == pytest.approx((0.1, 0.2, 0.3, 0.4))
    assert request.handoff_qvel == pytest.approx((0.01, 0.02, 0.03, 0.04))
    assert request.terrain_signature.shape == (89,)
    assert request.terrain_signature.flags.writeable is False
    assert request.continuous_goal["goal_id"] == request.goal_sha256
    assert len(request.input_sha256) == 64


@pytest.mark.parametrize(
    "forbidden",
    [
        {"episode_id": "episode_33"},
        {"fixed_expert_id": 4},
        {"temporary_cell_binding": "r0_c1"},
        {"nearest_trajectory_id": 12},
    ],
)
def test_v2_input_rejects_runtime_binding_and_nearest_fallback_fields(
    forbidden: dict[str, object],
) -> None:
    goal = _goal()
    goal["effect_intent"] = {
        **dict(goal["effect_intent"]),
        **forbidden,
    }
    goal.pop("goal_id")

    with pytest.raises(
        ContinuousGoalQposPathContractError,
        match="forbidden model binding",
    ):
        ContinuousGoalWorktoolSweepInputV2.create(
            handoff_qpos=[0.0] * 4,
            handoff_qvel=[0.0] * 4,
            continuous_goal=goal,
            terrain_signature={
                "schema": "terrain_signature_v1",
                "values": [0.0] * 89,
            },
        )


def test_v2_input_rejects_v24_suffix_or_nonfinite_terrain() -> None:
    with pytest.raises(
        ContinuousGoalQposPathContractError,
        match="exactly 89",
    ):
        ContinuousGoalWorktoolSweepInputV2.create(
            handoff_qpos=[0.0] * 4,
            handoff_qvel=[0.0] * 4,
            continuous_goal=_goal(),
            terrain_signature={
                "schema": "terrain_signature_v1",
                "values": [0.0] * 107,
            },
        )
    values = [0.0] * 89
    values[8] = float("nan")
    with pytest.raises(
        ContinuousGoalQposPathContractError,
        match="finite",
    ):
        ContinuousGoalWorktoolSweepInputV2.create(
            handoff_qpos=[0.0] * 4,
            handoff_qvel=[0.0] * 4,
            continuous_goal=_goal(),
            terrain_signature={
                "schema": "terrain_signature_v1",
                "values": values,
            },
        )


def test_effect_intent_string_category_is_explicit_and_changes_features() -> None:
    remove_request = _request()
    compact_goal = _goal()
    compact_goal["effect_intent"] = {
        "kind": "compact_soil",
        "target_mass_kg": 45.0,
    }
    compact_goal.pop("goal_id")
    compact_request = ContinuousGoalWorktoolSweepInputV2.create(
        handoff_qpos=remove_request.handoff_qpos,
        handoff_qvel=remove_request.handoff_qvel,
        continuous_goal=compact_goal,
        terrain_signature={
            "schema": "terrain_signature_v1",
            "values": remove_request.terrain_signature,
        },
    )

    remove_features = predictor_feature_map(remove_request)
    compact_features = predictor_feature_map(compact_request)

    assert remove_features != compact_features
    assert any(
        name.startswith("categorical:goal.effect_intent.kind::value::")
        for name in remove_features
    )
    assert set(remove_features) != set(compact_features)


def test_v1_artifact_is_readable_but_explicitly_legacy() -> None:
    legacy = read_continuous_goal_worktool_sweep_input(
        {
            "schema": CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1,
            "historic_payload": {"path": [[0.0] * 4, [0.1] * 4]},
        }
    )

    assert isinstance(legacy, LegacyContinuousGoalWorktoolSweepInputV1)
    assert legacy.schema == CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1
    with pytest.raises(
        ContinuousGoalQposPathContractError,
        match="v2",
    ):
        read_continuous_goal_worktool_sweep_input(
            {
                "schema": CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1,
                "historic_payload": {},
            },
            allow_legacy_v1=False,
        )


def test_v2_reader_rejects_hidden_top_level_binding_fields() -> None:
    payload = _request().as_dict()
    payload["episode_id"] = "episode_33"

    with pytest.raises(
        ContinuousGoalQposPathContractError,
        match="unsupported fields",
    ):
        read_continuous_goal_worktool_sweep_input(payload)


def test_v2_reader_revalidates_existing_instance_lineage() -> None:
    drifted = replace(_request(), goal_sha256="0" * 64)

    with pytest.raises(
        ContinuousGoalQposPathContractError,
        match="goal_sha256 lineage mismatch",
    ):
        read_continuous_goal_worktool_sweep_input(drifted)


def test_joint_arc_length_resampling_is_time_warp_invariant() -> None:
    path = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0],
            [0.1, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )

    resampled = resample_qpos_path_by_joint_arc_length(path)

    assert resampled.shape == (64, 4)
    assert np.array_equal(PATH_PROGRESS, np.linspace(0.0, 1.0, 64))
    assert resampled[:, 0] == pytest.approx(PATH_PROGRESS, abs=1.0e-12)
    assert resampled[:, 1:] == pytest.approx(0.0, abs=1.0e-12)


def test_clamped_cubic_spline_has_12_controls_and_zero_start_offset() -> None:
    qpos_path = np.column_stack(
        (
            0.2 + 0.5 * PATH_PROGRESS,
            -0.1 + 0.2 * PATH_PROGRESS**2,
            0.3 - 0.1 * PATH_PROGRESS,
            0.4 + 0.05 * np.sin(np.pi * PATH_PROGRESS),
        )
    )

    spline = fit_qpos_bspline(qpos_path, handoff_qpos=qpos_path[0])
    reconstructed = evaluate_qpos_bspline(spline.control_points)

    assert spline.control_points.shape == (12, 4)
    assert np.array_equal(spline.control_points[0], np.zeros(4))
    assert np.array_equal(reconstructed[0], np.zeros(4))
    assert reconstructed == pytest.approx(
        spline.target_relative_path,
        abs=1.0e-4,
    )
