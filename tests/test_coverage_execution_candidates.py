from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_CONTRACT_VERSION_V2_4,
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_V2_3_DIM,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.primitive.coverage.execution_candidates import (
    COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA,
    COVERAGE_EXECUTION_CORRIDOR_ID_BASE,
    CoverageExecutionCandidateContractError,
    CoverageExecutionCandidateService,
    CoverageOutcomeCellState,
    NoCoverageExecutionCandidateError,
)
from testbed.planner.primitive.coverage.start_reachability import (
    CoverageTupleStartReachabilityEvaluation,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
    CoverageWallSafetyConfig,
    CoverageWallSafetyService,
)
from testbed.planner.primitive.coverage.worktool_sweep import (
    CoverageWorktoolSweepEvaluation,
)


def _wall_service() -> CoverageWallSafetyService:
    return CoverageWallSafetyService(
        CoverageWallSafetyConfig(
            enabled=True,
            profile=CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
            worktool_width_m=0.70,
            hard_clearance_m=0.30,
            soft_clearance_m=0.45,
            max_score_penalty=1.0,
            missing_geometry="fail_closed",
        )
    )


def _env_state(*, long_axis: int = 2) -> np.ndarray:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = float(long_axis)
    env[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    env[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = 1.0
    env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = 1.25
    env[
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX:
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + 6
    ] = 1.0
    env[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX] = 0.61727345
    env[
        ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
        ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
    ] = np.asarray(
        [0.0, 0.058582537, 0.067155279, 0.176210508, 0.0, 0.075160891],
        dtype=np.float32,
    )
    env[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX:
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 6
    ] = np.asarray(
        [0.0, 0.058582537, 0.067155279, 0.176210508, 0.0, 0.075160891],
        dtype=np.float32,
    )
    return env


def _raw_fields(
    *,
    entry: tuple[float, float, float],
    exit_point: tuple[float, float, float],
    depth_m: float,
    payload_kg: float = 60.0,
    effect_kg: float = 40.0,
) -> dict[str, float | int]:
    delta = np.asarray(exit_point, dtype=np.float64) - np.asarray(
        entry,
        dtype=np.float64,
    )
    length = float(np.linalg.norm(delta))
    direction = delta / length
    return {
        "operator_entry_x_m": float(entry[0]),
        "operator_entry_y_m": float(entry[1]),
        "operator_entry_z_m": float(entry[2]),
        "operator_exit_x_m": float(exit_point[0]),
        "operator_exit_y_m": float(exit_point[1]),
        "operator_exit_z_m": float(exit_point[2]),
        "operator_cut_direction_x": float(direction[0]),
        "operator_cut_direction_y": float(direction[1]),
        "operator_cut_direction_z": float(direction[2]),
        "operator_cut_length_m": length,
        "operator_cut_depth_peak_m": float(depth_m),
        "operator_cut_payload_gain_kg": float(payload_kg),
        "operator_effective_deposit_delta_kg": float(effect_kg),
        "operator_cut_valid": 1,
    }


def _prototype(
    *,
    primitive_episode_id: int,
    source_episode_id: int,
    effect_outcome_cell_id: int,
    return_envelope_cell_id: int,
    raw_fields: dict[str, float | int],
    start_removed_depth_grid_m: list[float],
    centerline: list[int],
    swept: list[int],
    execution_tail_plane_depth_reserve_m: float = 0.02,
) -> dict[str, Any]:
    token = [
        float(raw_fields["operator_entry_x_m"]) / 2.0,
        float(raw_fields["operator_entry_z_m"]) / 2.0,
        float(raw_fields["operator_exit_x_m"]) / 2.0,
        float(raw_fields["operator_exit_z_m"]) / 2.0,
        float(raw_fields["operator_cut_direction_x"]),
        float(raw_fields["operator_cut_direction_z"]),
        float(raw_fields["operator_cut_length_m"]) / 2.0,
        float(raw_fields["operator_cut_depth_peak_m"]) / 0.8,
        min(float(raw_fields["operator_cut_payload_gain_kg"]) / 60.0, 1.0),
        1.0,
    ]
    return {
        "corridor_id": (
            COVERAGE_EXECUTION_CORRIDOR_ID_BASE + primitive_episode_id
        ),
        "exemplar_id": f"episode_{primitive_episode_id}",
        "primitive_episode_id": primitive_episode_id,
        "source_episode_id": source_episode_id,
        "effect_outcome_cell_id": effect_outcome_cell_id,
        "return_envelope_cell_id": return_envelope_cell_id,
        "raw_fields": dict(raw_fields),
        "dig_cut_tokens": token,
        "start_removed_depth_grid_m": list(start_removed_depth_grid_m),
        "token_peak_local_index": 10,
        "outcome_cell_loo_nearest_distance_p99": 1.0,
        "source_sha256": "a" * 64,
        "expected_centerline_physical_cell_ids": list(centerline),
        "expected_swept_physical_cell_ids": list(swept),
        "execution_tail_plane_depth_reserve_m": (
            execution_tail_plane_depth_reserve_m
        ),
    }


def _library(
    *,
    corridors: list[dict[str, Any]],
    loo_p99: dict[int, float],
) -> dict[str, Any]:
    for record in corridors:
        record["outcome_cell_loo_nearest_distance_p99"] = loo_p99[
            int(record["effect_outcome_cell_id"])
        ]
    return {
        "schema": COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA,
        "status": "completed",
        "source_lock": {"manifest_sha256": "b" * 64},
        "source_lineage": {
            "partition": "train",
            "validation_source_episode_ids": [33, 34],
        },
        "tail_audit": {"status": "completed"},
        "source_contract": {
            "env_state_contract": "agx_env_state_v2_3_89",
            "env_state_dim": 89,
            "primitive_name": "dig",
            "primitive_storage_mode": "copy",
            "training_tier": "gold",
            "dig_cut_token_contract": "v2_4_removed_depth_cut_v3",
            "dig_cut_token_dim": 10,
        },
        "live_selection_contract": {
            "requires_env_state": ENV_STATE_CONTRACT_VERSION_V2_4,
            "geometry_profile": (
                "conservative_2d_worktool_swept_footprint_v1"
            ),
            "worktool_width_m": 0.70,
            "removed_depth_scale_m": 0.12,
            "target_cell_weight": 2.0,
            "strict_library_env_state_is_replay_89d": True,
        },
        "corridor_id_contract": {
            "base": COVERAGE_EXECUTION_CORRIDOR_ID_BASE,
            "formula": "1000000 + primitive_episode_id",
            "legacy_outcome_cell_id_range": [0, 5],
        },
        "distance_contract": {
            "removed_depth_scale_m": 0.12,
            "target_cell_weight": 2.0,
        },
        "records": corridors,
    }


EPISODE_62_RAW_FIELDS = {
    "operator_cut_depth_peak_m": 0.41321706771850586,
    "operator_cut_direction_x": -0.19451460242271423,
    "operator_cut_direction_y": -0.902667224407196,
    "operator_cut_direction_z": 0.38386964797973633,
    "operator_cut_length_m": 0.5530307292938232,
    "operator_cut_payload_gain_kg": 90.72171783447266,
    "operator_cut_valid": 1,
    "operator_effective_deposit_delta_kg": 37.2547607421875,
    "operator_entry_x_m": 0.5629100799560547,
    "operator_entry_y_m": -0.048223018646240234,
    "operator_entry_z_m": -0.998016357421875,
    "operator_exit_x_m": 0.4553375244140625,
    "operator_exit_y_m": -0.5474257469177246,
    "operator_exit_z_m": -0.7857246398925781,
}
EPISODE_168_RAW_FIELDS = {
    "operator_cut_depth_peak_m": 0.3768954277038574,
    "operator_cut_direction_x": -0.5536772608757019,
    "operator_cut_direction_y": -0.818029522895813,
    "operator_cut_direction_z": 0.15578560531139374,
    "operator_cut_length_m": 0.35362669825553894,
    "operator_cut_payload_gain_kg": 66.59883880615234,
    "operator_cut_valid": 1,
    "operator_effective_deposit_delta_kg": 76.97193145751953,
    "operator_entry_x_m": 0.4559192657470703,
    "operator_entry_y_m": -0.0542759895324707,
    "operator_entry_z_m": -0.7894229888916016,
    "operator_exit_x_m": 0.26012420654296875,
    "operator_exit_y_m": -0.3435530662536621,
    "operator_exit_z_m": -0.7343330383300781,
}


def _episode_library() -> dict[str, Any]:
    episode_62 = _prototype(
        primitive_episode_id=62,
        source_episode_id=7,
        effect_outcome_cell_id=0,
        return_envelope_cell_id=0,
        raw_fields=EPISODE_62_RAW_FIELDS,
        start_removed_depth_grid_m=[
            0.035769231617450714,
            0.19558829069137573,
            0.13905388116836548,
            0.2563498616218567,
            0.03530801087617874,
            0.17453284561634064,
        ],
        centerline=[1],
        swept=[1],
        execution_tail_plane_depth_reserve_m=0.11734294891357422,
    )
    episode_168 = _prototype(
        primitive_episode_id=168,
        source_episode_id=24,
        effect_outcome_cell_id=1,
        return_envelope_cell_id=0,
        raw_fields=EPISODE_168_RAW_FIELDS,
        start_removed_depth_grid_m=[
            0.0,
            0.0,
            0.014239903539419174,
            0.06333747506141663,
            0.0,
            0.0,
        ],
        centerline=[1],
        swept=[1, 3],
        execution_tail_plane_depth_reserve_m=0.0034275054931640625,
    )
    return _library(
        corridors=[episode_62, episode_168],
        loo_p99={
            0: 0.5103992096986051,
            1: 0.7913282430516599,
        },
    )


def test_real_tuple_is_deeply_immutable_and_legacy_cell_id_is_read_only() -> None:
    library = _episode_library()
    service = CoverageExecutionCandidateService(_wall_service())

    prototypes = service.parse_library(library)
    episode_168 = prototypes[1]
    library["records"][1]["raw_fields"]["operator_entry_x_m"] = 999.0

    assert episode_168.effect_outcome_cell_id == 1
    assert episode_168.cell_id == 1
    assert episode_168.return_envelope_cell_id == 0
    assert episode_168.corridor_id == 1_000_168
    assert episode_168.raw_fields["operator_entry_x_m"] == pytest.approx(
        0.455919
    )
    with pytest.raises(TypeError):
        episode_168.raw_fields["operator_entry_x_m"] = 0.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        episode_168.effect_outcome_cell_id = 4  # type: ignore[misc]


def test_inconsistent_real_tuple_fails_closed() -> None:
    library = _episode_library()
    library["records"][1]["raw_fields"]["operator_cut_direction_x"] = 1.0

    with pytest.raises(
        CoverageExecutionCandidateContractError,
        match="cut_direction_inconsistent",
    ):
        CoverageExecutionCandidateService(_wall_service()).parse_library(
            library
        )


def test_episode168_selected_after_higher_scored_cell0_tuple_is_ood() -> None:
    selected = CoverageExecutionCandidateService(_wall_service()).select(
        library=_episode_library(),
        env_state=_env_state(),
        outcome_states=[
            CoverageOutcomeCellState(
                effect_outcome_cell_id=0,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
        ],
        cell_scores_by_outcome_cell_id={0: 10.0, 1: 9.0},
        blocked_corridor_ids={1},
        exhausted_physical_cell_ids=set(),
    )

    assert selected.corridor_id == 1_000_168
    assert selected.exemplar_id == "episode_168"
    assert selected.source_primitive_episode_id == 168
    assert selected.source_episode_id == 24
    assert selected.effect_outcome_cell_id == 1
    assert selected.cell_id == 1
    assert selected.return_envelope_cell_id == 0
    assert selected.live_centerline_physical_cell_ids == (1,)
    assert selected.live_swept_physical_cell_ids == (1, 3)
    assert selected.wall_minimum_clearance_m == pytest.approx(
        0.3736593339760881
    )
    assert selected.removed_depth_distance == pytest.approx(
        0.6357152998262633,
        abs=1.0e-6,
    )
    assert selected.loo_p99_distance == pytest.approx(
        0.7913282430516599
    )
    assert selected.planned_hard_bottom_clearance_before_tail_m == (
        pytest.approx(0.06416751444339752, abs=1.0e-9)
    )
    assert selected.execution_tail_plane_depth_reserve_m == pytest.approx(
        0.0034275054931640625
    )
    assert selected.planned_hard_bottom_budget_after_tail_m == pytest.approx(
        0.06074000895023346,
        abs=1.0e-9,
    )
    assert selected.cell_score == pytest.approx(9.0)
    assert selected.final_score == pytest.approx(
        9.0 - selected.wall_score_penalty
    )


@pytest.mark.parametrize(
    ("long_axis", "entry", "exit_point"),
    [
        (2, (0.4, 0.0, 0.55), (0.4, -0.2, 0.75)),
        (0, (0.55, 0.0, 0.4), (0.75, -0.2, 0.4)),
    ],
)
def test_live_physical_projection_supports_both_long_axes(
    long_axis: int,
    entry: tuple[float, float, float],
    exit_point: tuple[float, float, float],
) -> None:
    raw_fields = _raw_fields(
        entry=entry,
        exit_point=exit_point,
        depth_m=0.10,
    )
    library = _library(
        corridors=[
            _prototype(
                primitive_episode_id=900,
                source_episode_id=30,
                effect_outcome_cell_id=4,
                return_envelope_cell_id=2,
                raw_fields=raw_fields,
                start_removed_depth_grid_m=[0.0] * 6,
                centerline=[5],
                swept=[5],
                execution_tail_plane_depth_reserve_m=0.01,
            )
        ],
        loo_p99={4: 1.0},
    )

    selected = CoverageExecutionCandidateService(_wall_service()).select(
        library=library,
        env_state=_env_state(long_axis=long_axis),
        outcome_states=[
            CoverageOutcomeCellState(
                effect_outcome_cell_id=4,
                attempts=0,
                attempt_limit=1,
                depleted=False,
            )
        ],
        cell_scores_by_outcome_cell_id={4: 1.0},
        blocked_corridor_ids=set(),
        exhausted_physical_cell_ids=set(),
    )

    assert selected.effect_outcome_cell_id == 4
    assert selected.return_envelope_cell_id == 2
    assert selected.live_centerline_physical_cell_ids == (5,)
    assert selected.live_swept_physical_cell_ids == (5,)


@pytest.mark.parametrize(
    "state",
    [
        CoverageOutcomeCellState(
            effect_outcome_cell_id=1,
            attempts=0,
            attempt_limit=3,
            depleted=True,
        ),
        CoverageOutcomeCellState(
            effect_outcome_cell_id=1,
            attempts=3,
            attempt_limit=3,
            depleted=False,
        ),
    ],
)
def test_depleted_or_attempt_exhausted_outcome_has_no_candidate(
    state: CoverageOutcomeCellState,
) -> None:
    library = _episode_library()
    library["records"] = [library["records"][1]]

    with pytest.raises(NoCoverageExecutionCandidateError):
        CoverageExecutionCandidateService(_wall_service()).select(
            library=library,
            env_state=_env_state(),
            outcome_states=[state],
            cell_scores_by_outcome_cell_id={1: 9.0},
            blocked_corridor_ids=set(),
            exhausted_physical_cell_ids=set(),
        )


def test_namespaced_corridor_block_and_swept_exhaustion_are_separate() -> None:
    library = _episode_library()
    library["records"] = [library["records"][1]]
    kwargs = {
        "library": library,
        "env_state": _env_state(),
        "outcome_states": [
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            )
        ],
        "cell_scores_by_outcome_cell_id": {1: 9.0},
    }

    with pytest.raises(NoCoverageExecutionCandidateError):
        CoverageExecutionCandidateService(_wall_service()).select(
            **kwargs,
            blocked_corridor_ids={1_000_168},
            exhausted_physical_cell_ids=set(),
        )
    with pytest.raises(NoCoverageExecutionCandidateError):
        CoverageExecutionCandidateService(_wall_service()).select(
            **kwargs,
            blocked_corridor_ids=set(),
            exhausted_physical_cell_ids={3},
        )


def test_missing_107d_or_library_physical_fields_fails_closed() -> None:
    service = CoverageExecutionCandidateService(_wall_service())
    library = _episode_library()
    states = [
        CoverageOutcomeCellState(
            effect_outcome_cell_id=0,
            attempts=0,
            attempt_limit=3,
            depleted=False,
        ),
        CoverageOutcomeCellState(
            effect_outcome_cell_id=1,
            attempts=0,
            attempt_limit=3,
            depleted=False,
        ),
    ]
    with pytest.raises(
        CoverageExecutionCandidateContractError,
        match="env_state_v2_4_width",
    ):
        service.select(
            library=library,
            env_state=_env_state()[:ENV_STATE_V2_3_DIM],
            outcome_states=states,
            cell_scores_by_outcome_cell_id={0: 10.0, 1: 9.0},
        )

    library = _episode_library()
    del library["records"][1]["expected_swept_physical_cell_ids"]
    with pytest.raises(
        CoverageExecutionCandidateContractError,
        match="expected_swept_physical_cell_ids",
    ):
        service.parse_library(library)

    old_library = _episode_library()
    old_library["schema"] = "strict_train_coverage_execution_library_v1"
    with pytest.raises(
        CoverageExecutionCandidateContractError,
        match="library_schema",
    ):
        service.parse_library(old_library)


def test_all_tuple_trace_and_a0_adjustment_are_immutable_and_fail_closed() -> None:
    service = CoverageExecutionCandidateService(_wall_service())
    kwargs = {
        "library": _episode_library(),
        "env_state": _env_state(),
        "outcome_states": [
            CoverageOutcomeCellState(
                effect_outcome_cell_id=0,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
        ],
        "cell_scores_by_outcome_cell_id": {0: 10.0, 1: 9.0},
    }
    adjusted_ids: list[int] = []

    selected = service.select(
        **kwargs,
        prototype_score_adjustment=lambda prototype: (
            adjusted_ids.append(prototype.source_primitive_episode_id) or 0.25
        ),
    )

    assert adjusted_ids == [168]
    assert selected.prototype_score_adjustment == pytest.approx(0.25)
    assert selected.final_score == pytest.approx(
        selected.cell_score - selected.wall_score_penalty + 0.25
    )
    assert len(selected.candidate_trace) == 2
    trace = {
        int(row["corridor_id"]): row for row in selected.candidate_trace
    }
    assert trace[1_000_062]["rejection_reason"] == (
        "removed_depth_out_of_support"
    )
    assert trace[1_000_168]["status"] == "selected"
    with pytest.raises(TypeError):
        trace[1_000_168]["status"] = "mutated"  # type: ignore[index]

    with pytest.raises(NoCoverageExecutionCandidateError) as exc_info:
        service.select(
            **kwargs,
            prototype_score_adjustment=lambda _prototype: float("-inf"),
        )
    assert len(exc_info.value.candidate_trace) == 2
    assert {
        int(row["corridor_id"]): row["rejection_reason"]
        for row in exc_info.value.candidate_trace
    }[1_000_168] == "prototype_score_adjustment_rejected"


def test_equal_state_distance_uses_a0_adjustment_as_deterministic_tie_break() -> None:
    library = _episode_library()
    library["records"] = [library["records"][1]]
    tied = copy.deepcopy(library["records"][0])
    tied["primitive_episode_id"] = 169
    tied["corridor_id"] = 1_000_169
    tied["exemplar_id"] = "episode_169"
    tied["source_sha256"] = "c" * 64
    library["records"].append(tied)

    selected = CoverageExecutionCandidateService(_wall_service()).select(
        library=library,
        env_state=_env_state(),
        outcome_states=[
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            )
        ],
        cell_scores_by_outcome_cell_id={1: 9.0},
        prototype_score_adjustment=lambda prototype: (
            0.5 if prototype.exemplar_id == "episode_169" else 0.1
        ),
    )

    assert selected.exemplar_id == "episode_169"
    assert selected.prototype_score_adjustment == pytest.approx(0.5)


class _Episode168RejectingSweep:
    def evaluate(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        live_start_qpos: Any,
    ) -> CoverageWorktoolSweepEvaluation:
        del live_start_qpos
        eligible = exemplar_id != "episode_168"
        return CoverageWorktoolSweepEvaluation(
            profile="unity_kinematic_convex_cover_worktool_sweep_v1",
            eligible=eligible,
            rejection_reason=(
                "" if eligible else "worktool_3d_clearance_below_minimum"
            ),
            exemplar_id=exemplar_id,
            raw_fields_sha256=raw_fields_sha256,
            artifact_sha256="9" * 64,
            sampled_convex_cover_clearance_m=0.60 if eligible else 0.20,
            pose_interpolation_margin_m=0.01,
            act_tracking_margin_m=0.15,
            live_start_displacement_bound_m=0.0,
            effective_clearance_m=0.44 if eligible else 0.04,
            hard_clearance_m=0.30,
            closest_link_name="bucket",
            closest_shape_name="watou.STL",
            closest_wall_name="Dig_ZMin_Board",
            closest_pose_index=12,
            closest_qpos=(0.5, 0.5, 0.5, 0.5),
            closest_worktool_point_world_m=(0.0, 0.0, 0.0),
            closest_wall_point_world_m=(0.0, 0.0, 0.2),
        )


def test_3d_gate_rejects_unsafe_high_score_before_k1_selection() -> None:
    env = _env_state()
    env[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX:
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 6
    ] = np.asarray(
        _episode_library()["records"][0]["start_removed_depth_grid_m"],
        dtype=np.float32,
    )
    selected = CoverageExecutionCandidateService(
        _wall_service(),
        worktool_sweep_service=_Episode168RejectingSweep(),
    ).select(
        library=_episode_library(),
        env_state=env,
        current_qpos=[0.5, 0.5, 0.5, 0.5],
        outcome_states=[
            CoverageOutcomeCellState(
                effect_outcome_cell_id=0,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
        ],
        cell_scores_by_outcome_cell_id={0: 1.0, 1: 100.0},
    )

    assert selected.exemplar_id == "episode_62"
    assert selected.worktool_sweep_evaluation is not None
    assert selected.worktool_sweep_evaluation.eligible is True
    trace = {
        str(item["exemplar_id"]): item for item in selected.candidate_trace
    }
    assert trace["episode_168"]["rejection_reason"] == (
        "worktool_3d_clearance_below_minimum"
    )
    assert trace["episode_168"]["worktool_sweep_3d_eligible"] == 0


class _ReachabilityService:
    def __init__(self, *, rejected: set[str] | None = None) -> None:
        self.rejected = set(rejected or ())
        self.calls: list[tuple[str, str, tuple[float, ...]]] = []

    def evaluate(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        live_return_start_facts: Any,
        selection_phase: str,
    ) -> CoverageTupleStartReachabilityEvaluation:
        live = tuple(
            np.asarray(
                [] if live_return_start_facts is None
                else live_return_start_facts,
                dtype=np.float64,
            ).reshape(-1)
        )
        self.calls.append((exemplar_id, selection_phase, live))
        eligible = exemplar_id not in self.rejected
        return CoverageTupleStartReachabilityEvaluation(
            profile="strict_train_return_start_reachability_11d_v1",
            eligible=eligible,
            rejection_reason="" if eligible else "tuple_start_out_of_support",
            selection_phase=selection_phase,
            exemplar_id=exemplar_id,
            raw_fields_sha256=raw_fields_sha256,
            artifact_sha256="8" * 64,
            cycle0_eligible=True,
            post_return_eligible=True,
            paired_return_primitive_episode_id=158,
            paired_return_exemplar_id="episode_158",
            exact_return_start_envelope_tokens=tuple([0.0] * 16 + [1.0, 1.0]),
            exact_return_start_envelope_valid_mask=(1,) * 18,
            paired_handoff_facts=(
                0.61,
                0.62,
                0.63,
                0.64,
                0.0,
                0.0,
                0.0,
                0.0,
                0.4,
                0.5,
                0.6,
            ),
            expert_dig_start_facts=(0.5,) * 11,
        )


class _RecordingSweep:
    def __init__(self) -> None:
        self.start_qpos: list[tuple[float, ...]] = []

    def evaluate(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        live_start_qpos: Any,
    ) -> CoverageWorktoolSweepEvaluation:
        qpos = tuple(np.asarray(live_start_qpos, dtype=np.float64).reshape(-1))
        self.start_qpos.append(qpos)
        return CoverageWorktoolSweepEvaluation(
            profile="unity_kinematic_convex_cover_worktool_sweep_v1",
            eligible=True,
            rejection_reason="",
            exemplar_id=exemplar_id,
            raw_fields_sha256=raw_fields_sha256,
            artifact_sha256="9" * 64,
            sampled_convex_cover_clearance_m=0.60,
            pose_interpolation_margin_m=0.01,
            act_tracking_margin_m=0.15,
            live_start_displacement_bound_m=0.0,
            effective_clearance_m=0.44,
            hard_clearance_m=0.30,
        )


def test_post_return_reachability_filters_before_k1_and_uses_paired_handoff_for_3d() -> None:
    library = _episode_library()
    library["records"] = [copy.deepcopy(library["records"][1])]
    farther = copy.deepcopy(library["records"][0])
    farther["primitive_episode_id"] = 169
    farther["corridor_id"] = 1_000_169
    farther["exemplar_id"] = "episode_169"
    farther["effect_outcome_cell_id"] = 1
    farther["return_envelope_cell_id"] = 0
    farther["source_sha256"] = "f" * 64
    farther["expected_centerline_physical_cell_ids"] = list(
        library["records"][0]["expected_centerline_physical_cell_ids"]
    )
    farther["expected_swept_physical_cell_ids"] = list(
        library["records"][0]["expected_swept_physical_cell_ids"]
    )
    farther["start_removed_depth_grid_m"] = [
        float(value) + 0.01
        for value in library["records"][0]["start_removed_depth_grid_m"]
    ]
    library["records"].append(farther)
    reachability = _ReachabilityService(rejected={"episode_168"})
    sweep = _RecordingSweep()
    live_facts = tuple(float(index) / 10.0 for index in range(11))

    selected = CoverageExecutionCandidateService(
        _wall_service(),
        worktool_sweep_service=sweep,
        tuple_start_reachability_service=reachability,
    ).select(
        library=library,
        env_state=_env_state(),
        current_qpos=[0.1, 0.2, 0.3, 0.4],
        live_return_start_facts=live_facts,
        selection_phase="post_return",
        outcome_states=[
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            )
        ],
        cell_scores_by_outcome_cell_id={1: 9.0},
    )

    assert selected.exemplar_id == "episode_169"
    assert selected.start_reachability_evaluation is not None
    assert selected.start_reachability_evaluation.eligible is True
    assert {call[0] for call in reachability.calls} == {
        "episode_168",
        "episode_169",
    }
    assert all(call[1] == "post_return" for call in reachability.calls)
    assert all(call[2] == pytest.approx(live_facts) for call in reachability.calls)
    assert sweep.start_qpos
    assert all(
        qpos == pytest.approx((0.61, 0.62, 0.63, 0.64))
        for qpos in sweep.start_qpos
    )
    trace = {
        str(item["exemplar_id"]): item for item in selected.candidate_trace
    }
    assert trace["episode_168"]["rejection_reason"] == (
        "tuple_start_out_of_support"
    )


def test_cycle0_3d_uses_current_qpos_not_paired_handoff() -> None:
    reachability = _ReachabilityService()
    sweep = _RecordingSweep()

    selected = CoverageExecutionCandidateService(
        _wall_service(),
        worktool_sweep_service=sweep,
        tuple_start_reachability_service=reachability,
    ).select(
        library=_episode_library(),
        env_state=_env_state(),
        current_qpos=[0.1, 0.2, 0.3, 0.4],
        live_return_start_facts=None,
        selection_phase="cycle0",
        outcome_states=[
            CoverageOutcomeCellState(
                effect_outcome_cell_id=0,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
            CoverageOutcomeCellState(
                effect_outcome_cell_id=1,
                attempts=0,
                attempt_limit=3,
                depleted=False,
            ),
        ],
        cell_scores_by_outcome_cell_id={0: 1.0, 1: 9.0},
    )

    assert selected.start_reachability_evaluation is not None
    assert all(
        qpos == pytest.approx((0.1, 0.2, 0.3, 0.4))
        for qpos in sweep.start_qpos
    )
