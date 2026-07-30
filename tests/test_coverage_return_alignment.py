from __future__ import annotations

from pathlib import Path

import pytest

from testbed.eval.coverage_execution_eval_config import (
    PURPOSE_BOUNDED_ONE_DIG,
    build_coverage_execution_eval_config,
)
from testbed.eval.coverage_return_alignment import (
    OUTPUT_FILENAME,
    build_tuple_start_alignment_diagnosis,
)

ROOT = Path(__file__).parents[1]
DATA_ROOT = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0"
)
RUN_ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0"
)
ROLLOUT_RESULTS = (
    RUN_ROOT
    / "act_goal_execution_contract_recovery_v1/"
    "bounded_one_dig_pose_stable_v2/results"
)
ORIGINAL_CONFIG = ROLLOUT_RESULTS / "eval_resolved_config.yaml"
BASE_CONFIG = (
    ROOT
    / "testbed/configs/"
    "eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml"
)
EXECUTION_LIBRARY = (
    DATA_ROOT / "qc/strict_train_coverage_execution_library_v1_1.json"
)
EXECUTION_SHA = (
    "b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614"
)
TRANSITION_LIBRARY = (
    DATA_ROOT / "qc/strict_train_coverage_return_transition_library_v1.json"
)
TRANSITION_SHA = (
    "65952a2932a1d1373a74b825eb4d79c24d43224ca3e2449abcd7515395ab1e86"
)
SWEEP_LIBRARY = (
    RUN_ROOT
    / "unity_3d_worktool_sweep_v1/"
    "coverage_worktool_sweep_library_v1_1.json"
)
SWEEP_SHA = (
    "e29be1667731f537af8b4d66f931869467dfc9a6dfc53471a0d09b07ee9fbc21"
)
POSE_SHA = (
    "cf93063fb47b81dc2083a8fd56dc696d1f0f6911ac385c5331414653190f16a2"
)
HAS_EVIDENCE = all(
    path.is_file()
    for path in (
        ORIGINAL_CONFIG,
        BASE_CONFIG,
        EXECUTION_LIBRARY,
        TRANSITION_LIBRARY,
        SWEEP_LIBRARY,
        *(ROLLOUT_RESULTS / "rollouts").glob("rollout_*.jsonl"),
        *(ROLLOUT_RESULTS / "hdf5_rollouts").glob("episode_*.hdf5"),
    )
)


def _fake_teacher_forced_runner(**kwargs):
    assert len(kwargs["replay_inputs"]) == 3
    assert kwargs["exact_token"].shape == (18,)
    return {
        "status": "completed",
        "evidence_kind": "teacher_forced_recorded_observation",
        "independent_temporal_state": True,
        "closed_loop_claim": False,
    }


@pytest.mark.skipif(
    not HAS_EVIDENCE,
    reason="frozen bounded rollout evidence is unavailable",
)
def test_alignment_rejects_wrong_tuple_and_stops_at_independent_3d_blocker(
    tmp_path: Path,
) -> None:
    production_config = tmp_path / "production.yaml"
    build_coverage_execution_eval_config(
        base_config_path=BASE_CONFIG,
        output_path=production_config,
        run_root=tmp_path / "live_not_started",
        strict_execution_library_path=EXECUTION_LIBRARY,
        strict_execution_library_sha256=EXECUTION_SHA,
        worktool_sweep_artifact_path=SWEEP_LIBRARY,
        worktool_sweep_artifact_sha256=SWEEP_SHA,
        worktool_sweep_pose_library_sha256=POSE_SHA,
        return_transition_artifact_path=TRANSITION_LIBRARY,
        return_transition_artifact_sha256=TRANSITION_SHA,
        purpose=PURPOSE_BOUNDED_ONE_DIG,
    )
    output_dir = tmp_path / "diagnosis"
    kwargs = {
        "rollout_results_dir": ROLLOUT_RESULTS,
        "original_eval_config_path": ORIGINAL_CONFIG,
        "production_preflight_config_path": production_config,
        "return_transition_artifact_path": TRANSITION_LIBRARY,
        "execution_library_path": EXECUTION_LIBRARY,
        "worktool_sweep_artifact_path": SWEEP_LIBRARY,
        "output_dir": output_dir,
        "teacher_forced_runner": _fake_teacher_forced_runner,
    }
    artifact = build_tuple_start_alignment_diagnosis(**kwargs)

    assert artifact["status"] == "completed_blocked_before_live"
    assert artifact["contract_identity"]["paired_gold_return"] == "episode_158"
    assert artifact["return_start_support"][
        "global_p01_p99_all_three_in_support"
    ] is True
    assert artifact["return_start_support"][
        "episode_168_rejected_all_three"
    ] is True
    assert artifact["return_start_support"][
        "reachable_alternative_count_by_rollout"
    ] == [35, 40, 61]
    assert artifact["handoff_contract"][
        "old_cell_token_reported_ready_all_three"
    ] is True
    assert artifact["handoff_contract"][
        "exact_episode_158_gate_rejects_all_three"
    ] is True
    assert artifact["production_preflight"][
        "pre_return_qpos_used_as_3d_dig_start"
    ] is False
    clearance = artifact["optimistic_3d_clearance_contract"]
    assert clearance["maximum_nominal_clearance_m"] == pytest.approx(
        0.340938926
    )
    assert clearance[
        "maximum_effective_clearance_with_zero_start_displacement_m"
    ] == pytest.approx(0.180938926)
    assert clearance["candidate_count_at_or_above_hard_clearance"] == 0
    assert artifact["gate_decision"]["bounded_live_allowed"] is False
    assert artifact["gate_decision"]["bounded_live_started"] is False
    assert artifact["gate_decision"]["functional_1x10_started"] is False
    assert (output_dir / OUTPUT_FILENAME).is_file()

    with pytest.raises(FileExistsError):
        build_tuple_start_alignment_diagnosis(**kwargs)
