from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from testbed.cli.salvage_terrain_replay_dataset import build_parser
from testbed.eval.terrain_replay_attempt_runner import (
    candidate_is_locally_auditable,
    remove_retained_attempt_hdf5,
)
from testbed.eval.terrain_replay_run_contract import (
    HardReplayContractError,
    recorded_replay_step_id,
    replay_step_id_semantics,
)
from testbed.eval.terrain_replay_salvage import (
    CORRECTED_MAX_ATTEMPTS,
    SALVAGE_EPISODE_IDS,
    STRICT_ATTEMPT_BUDGETS,
    STRICT_REPLAY_ORDER,
    build_local_action_mask,
    evaluate_local_cycle_eligibility,
    initialize_salvage_root,
    select_best_local_candidate,
    validate_parent_salvage_inventory,
)
from testbed.eval.terrain_replay_salvage_candidates import existing_partial_record
from testbed.eval.terrain_replay_salvage_execution import (
    _load_attempt_results,
    run_episode_phase,
)
from testbed.eval.terrain_replay_salvage_outputs import summarize_partial_coverage
from testbed.eval.terrain_replay_salvage_preflight import build_salvage_run_contract


def test_salvage_inventory_and_attempt_budgets_are_fixed() -> None:
    assert SALVAGE_EPISODE_IDS == (1, 4, 9, 10, 12, 14, 20)
    assert STRICT_REPLAY_ORDER == (4, 9, 12, 10, 1, 14, 20)
    assert STRICT_ATTEMPT_BUDGETS == {
        4: 10,
        9: 10,
        12: 5,
        10: 5,
        1: 5,
        14: 1,
        20: 1,
    }
    assert CORRECTED_MAX_ATTEMPTS == 3


def test_corrected_replay_records_causal_action_index_as_step_id() -> None:
    """A pose-realign RPC may advance/repeat the backend id without consuming action."""

    assert recorded_replay_step_id(
        record_step_index=16721,
        backend_step_id=16722,
        corrected=False,
    ) == 16722
    assert replay_step_id_semantics(corrected=False) == "backend_step_id_v1"

    assert recorded_replay_step_id(
        record_step_index=16721,
        backend_step_id=16722,
        corrected=True,
    ) == 16721
    assert replay_step_id_semantics(corrected=True) == (
        "causal_source_action_index_v1"
    )


def test_salvage_cli_exposes_readonly_preflight_resume_and_strict_stop() -> None:
    args = build_parser().parse_args(
        ["--preflight-only", "--resume", "--stop-after-strict"]
    )

    assert args.preflight_only is True
    assert args.resume is True
    assert args.stop_after_strict is True


def test_parent_inventory_requires_exact_17_selected_and_7_exhausted() -> None:
    payload = {
        "status": "partial",
        "selected_episode_ids": [
            3,
            6,
            7,
            8,
            13,
            16,
            19,
            23,
            24,
            25,
            27,
            28,
            29,
            30,
            32,
            33,
            34,
        ],
        "exhausted_episode_ids": list(SALVAGE_EPISODE_IDS),
    }

    normalized = validate_parent_salvage_inventory(payload)

    assert normalized["selected_episode_count"] == 17
    assert normalized["exhausted_episode_ids"] == list(SALVAGE_EPISODE_IDS)

    with pytest.raises(ValueError, match="exhausted inventory"):
        validate_parent_salvage_inventory(
            {**payload, "exhausted_episode_ids": [1, 4, 9]}
        )


def test_salvage_root_is_no_overwrite_and_exact_resume(tmp_path: Path) -> None:
    root = tmp_path / "salvage"
    contract = {"schema": "salvage-test", "parent_sha256": "abc"}

    first = initialize_salvage_root(
        output_root=root,
        contract=contract,
        resume=False,
    )
    assert first["resumed"] is False

    with pytest.raises(FileExistsError, match="no-overwrite"):
        initialize_salvage_root(
            output_root=root,
            contract=contract,
            resume=False,
        )

    resumed = initialize_salvage_root(
        output_root=root,
        contract=contract,
        resume=True,
    )
    assert resumed["resumed"] is True

    with pytest.raises(ValueError, match="run contract mismatch"):
        initialize_salvage_root(
            output_root=root,
            contract={**contract, "parent_sha256": "changed"},
            resume=True,
        )


def test_salvage_run_contract_locks_parent_runtime_and_source_hashes(
    tmp_path: Path,
) -> None:
    config = tmp_path / "replay.yaml"
    config.write_text("agx: {}\n", encoding="utf-8")
    contract = build_salvage_run_contract(
        output_root=tmp_path / "out",
        replay_config=config,
        preflight={
            "parent_root": "/fixed/parent",
            "parent_artifacts": {
                "completion_report.json": {"sha256": "parent-report"}
            },
            "parent_selected_files": [
                {"episode_id": 3, "manifest_sha256": "selected-3"}
            ],
            "source_files": [{"episode_id": 1, "sha256": "source-1"}],
            "runtime_contract": {"runtime_build_id": "fixed-build"},
        },
    )

    assert contract["parent_artifacts"]["completion_report.json"]["sha256"] == (
        "parent-report"
    )
    assert contract["parent_selected_sha256"] == {"3": "selected-3"}
    assert contract["source_sha256"] == {"1": "source-1"}
    assert contract["runtime_contract"]["runtime_build_id"] == "fixed-build"
    assert contract["corrected_realign_contract"] == {
        "axis": "all",
        "error_threshold": 0.04,
        "hold_steps": 3,
        "min_steps_between": 200,
        "burn_in_steps": 15,
        "max_count": 20,
    }


def test_attempt_resume_rejects_a_directory_gap(tmp_path: Path) -> None:
    attempts = tmp_path / "strict_attempts"
    (attempts / "episode_4" / "attempt_01").mkdir(parents=True)

    with pytest.raises(ValueError, match="sequence has a gap"):
        _load_attempt_results(
            attempts_root=attempts,
            selected_root=tmp_path / "selected",
            episode_id=4,
            attempt_kind="strict",
            max_attempts=10,
        )


def test_partial_candidate_recovers_after_atomic_move_before_record(
    tmp_path: Path,
) -> None:
    output = tmp_path / "salvage"
    attempt = output / "strict_attempts" / "episode_4" / "attempt_00"
    attempt.mkdir(parents=True)
    target = output / "partial_salvage_full_hdf5" / "episode_4.hdf5"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"moved-partial-candidate")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    record = {
        "schema": "terrain_replay_partial_salvage_episode_v1",
        "source_episode_id": "episode_4",
        "selected_attempt_id": "strict:attempt_00",
        "selected_hdf5_path": str(target.resolve()),
        "sha256": digest,
        "size_bytes": target.stat().st_size,
        "default_enabled": False,
        "strict_pool_eligible": False,
    }
    (attempt / "partial_move_intent.json").write_text(
        json.dumps(
            {
                "schema": "terrain_replay_partial_move_intent_v1",
                "source_path": str(
                    (attempt / "recorded" / "episode_0.hdf5").resolve()
                ),
                "selected_path": str(target.resolve()),
                "sha256": digest,
                "size_bytes": target.stat().st_size,
                "attempt_uid": "strict:attempt_00",
                "record": record,
            }
        ),
        encoding="utf-8",
    )

    recovered = existing_partial_record(output, episode_id=4)

    assert recovered == record
    assert json.loads((attempt / "partial_record.json").read_text()) == record
    retention = json.loads((attempt / "partial_retention.json").read_text())
    assert retention["retained"] is True
    assert retention["reason"] == "recovered_after_partial_move"


def test_episode_4_technical_smoke_stops_before_second_attempt(tmp_path: Path) -> None:
    attempts = tmp_path / "strict_attempts"
    attempt = attempts / "episode_4" / "attempt_00"
    attempt.mkdir(parents=True)
    (attempt / "attempt_result.json").write_text(
        json.dumps(
            {
                "source_episode_id": "episode_4",
                "attempt_id": "attempt_00",
                "attempt_kind": "strict",
                "pass": False,
                "candidate_technical_pass": False,
                "hard_contract_errors": [],
                "retained_hdf5_path": None,
                "selected_record": None,
                "gate_path": str(attempt / "gate.json"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HardReplayContractError, match="live smoke"):
        run_episode_phase(
            output_root=tmp_path,
            attempts_root=attempts,
            selected_root=tmp_path / "selected",
            episode_id=4,
            selection_manifest=tmp_path / "selection.jsonl",
            replay_config=tmp_path / "replay.yaml",
            calibrated_source_path=tmp_path / "source.hdf5",
            expected_steps=20_000,
            source_reference={},
            source_cycles=(),
            attempt_kind="strict",
            max_attempts=10,
            expected_runtime_build_id="build",
            require_first_attempt_technical_smoke=True,
        )

    assert not (attempts / "episode_4" / "attempt_01").exists()


def test_local_candidate_ranking_is_deterministic_and_prefers_pure_on_tie() -> None:
    candidates = [
        {
            "attempt_id": "corrected_00",
            "attempt_kind": "corrected",
            "eligible_cycle_count": 4,
            "valid_action_step_count": 500,
            "attempt_index": 0,
        },
        {
            "attempt_id": "strict_03",
            "attempt_kind": "strict",
            "eligible_cycle_count": 4,
            "valid_action_step_count": 500,
            "attempt_index": 3,
        },
        {
            "attempt_id": "strict_04",
            "attempt_kind": "strict",
            "eligible_cycle_count": 3,
            "valid_action_step_count": 900,
            "attempt_index": 4,
        },
    ]

    selected = select_best_local_candidate(candidates)

    assert selected is not None
    assert selected["attempt_id"] == "strict_03"


def test_completion_coverage_counts_only_selected_partial_candidates() -> None:
    coverage = summarize_partial_coverage(
        (
            {
                "source_episode_id": "episode_4",
                "eligible_cycle_count": 22,
                "valid_action_step_count": 16_264,
            },
            {
                "source_episode_id": "episode_14",
                "eligible_cycle_count": 9,
                "valid_action_step_count": 7_184,
            },
        )
    )

    assert coverage == {
        "eligible_cycle_count": 31,
        "valid_action_step_count": 23_448,
    }

    with pytest.raises(ValueError, match="duplicate source identity"):
        summarize_partial_coverage(
            (
                {
                    "source_episode_id": "episode_4",
                    "eligible_cycle_count": 1,
                    "valid_action_step_count": 10,
                },
                {
                    "source_episode_id": "episode_4",
                    "eligible_cycle_count": 2,
                    "valid_action_step_count": 20,
                },
            )
        )


def test_local_action_mask_only_tightens_source_and_guards_realign() -> None:
    source_mask = np.ones(20, dtype=np.uint8)
    source_mask[4] = 0
    cycles = [
        {"cycle_id": 0, "start_step": 2, "end_step_exclusive": 6},
        {"cycle_id": 1, "start_step": 8, "end_step_exclusive": 12},
        {"cycle_id": 2, "start_step": 14, "end_step_exclusive": 18},
    ]

    result = build_local_action_mask(
        source_mask=source_mask,
        replay_qc_mask=np.ones(20, dtype=np.uint8),
        cycle_windows=cycles,
        eligible_cycle_ids=(0, 1, 2),
        realign_steps=(10,),
        guard_steps=1,
    )

    expected = np.zeros(20, dtype=np.uint8)
    expected[2:8] = 1  # cycle 0 plus transition into cycle 1
    expected[8:9] = 1
    expected[12:14] = 1  # clean transition from cycle 1 to cycle 2
    expected[14:18] = 1
    expected[4] = 0
    expected[9:12] = 0  # realign guard masks step 9, 10, 11
    np.testing.assert_array_equal(result, expected)
    assert np.all(result <= source_mask)


def test_local_action_mask_does_not_open_transition_for_ineligible_neighbor() -> None:
    result = build_local_action_mask(
        source_mask=np.ones(12, dtype=np.uint8),
        replay_qc_mask=np.ones(12, dtype=np.uint8),
        cycle_windows=(
            {"cycle_id": 0, "start_step": 1, "end_step_exclusive": 4},
            {"cycle_id": 1, "start_step": 7, "end_step_exclusive": 10},
        ),
        eligible_cycle_ids=(0,),
        realign_steps=(),
        guard_steps=0,
    )

    expected = np.zeros(12, dtype=np.uint8)
    expected[1:4] = 1
    np.testing.assert_array_equal(result, expected)


def test_local_cycle_eligibility_requires_boundary_qpos_geometry_and_contact() -> None:
    source_qpos = np.zeros((24, 4), dtype=np.float32)
    replay_qpos = np.zeros((24, 4), dtype=np.float32)
    replay_qpos[12, 0] = 0.03
    source_env = np.zeros((24, 64), dtype=np.float32)
    replay_env = np.zeros((24, 89), dtype=np.float32)
    source_env[3, 61] = 1.0
    replay_env[3, 61] = 1.0
    source_env[13, 61] = 1.0
    replay_env[13, 61] = 1.0
    source_cycles = (
        {"cycle_id": 0, "start_step": 2, "end_step_exclusive": 8},
        {"cycle_id": 1, "start_step": 12, "end_step_exclusive": 18},
    )
    records = []
    for cycle_id, start, end in ((0, 2, 8), (1, 12, 18)):
        for target_id in (
            "recording_depth_0p08_full_grid_diagnostic",
            "t1_large_shallow_rectangular_pit_default",
            "t2_long_shallow_trench_default",
        ):
            records.append(
                {
                    "cycle_index": cycle_id,
                    "cycle_start_observation_index": start,
                    "cycle_end_observation_index": end - 1,
                    "target_id": target_id,
                    "grid_geometry_stable": True,
                    "surface_valid_fraction_start": 1.0,
                    "surface_valid_fraction_end": 1.0,
                }
            )

    result = evaluate_local_cycle_eligibility(
        source_qpos=source_qpos,
        source_env_state=source_env,
        replay_qpos=replay_qpos,
        replay_env_state=replay_env,
        source_cycles=source_cycles,
        candidate_records=records,
        realign_steps=(),
        control_hz=50.0,
    )

    assert result["eligible_source_cycle_ids"] == [0]
    assert result["cycle_rows"][0]["eligible"] is True
    assert result["cycle_rows"][1]["eligible"] is False
    assert "cycle_entry_qpos_error_exceeded" in result["cycle_rows"][1][
        "reason_codes"
    ]


def test_local_cycle_eligibility_rejects_realign_guard_without_poisoning_neighbor() -> None:
    qpos = np.zeros((30, 4), dtype=np.float32)
    source_env = np.zeros((30, 64), dtype=np.float32)
    replay_env = np.zeros((30, 89), dtype=np.float32)
    records = []
    cycles = []
    for cycle_id, start, end in ((0, 1, 8), (1, 12, 19), (2, 22, 29)):
        source_env[start + 1, 61] = 1.0
        replay_env[start + 1, 61] = 1.0
        cycles.append(
            {"cycle_id": cycle_id, "start_step": start, "end_step_exclusive": end}
        )
        for target_id in (
            "recording_depth_0p08_full_grid_diagnostic",
            "t1_large_shallow_rectangular_pit_default",
            "t2_long_shallow_trench_default",
        ):
            records.append(
                {
                    "cycle_index": cycle_id,
                    "cycle_start_observation_index": start,
                    "cycle_end_observation_index": end - 1,
                    "target_id": target_id,
                    "grid_geometry_stable": True,
                    "surface_valid_fraction_start": 1.0,
                    "surface_valid_fraction_end": 1.0,
                }
            )

    result = evaluate_local_cycle_eligibility(
        source_qpos=qpos,
        source_env_state=source_env,
        replay_qpos=qpos,
        replay_env_state=replay_env,
        source_cycles=cycles,
        candidate_records=records,
        realign_steps=(15,),
        control_hz=2.0,
    )

    assert result["eligible_source_cycle_ids"] == [0, 2], [
        row["reason_codes"] for row in result["cycle_rows"]
    ]
    assert result["cycle_rows"][1]["reason_codes"] == [
        "cycle_or_guard_contains_pose_realign"
    ]


def test_local_cycle_eligibility_isolates_a_camera_damaged_cycle() -> None:
    qpos = np.zeros((24, 4), dtype=np.float32)
    source_env = np.zeros((24, 64), dtype=np.float32)
    replay_env = np.zeros((24, 89), dtype=np.float32)
    source_env[[3, 13], 61] = 1.0
    replay_env[[3, 13], 61] = 1.0
    cycles = (
        {"cycle_id": 0, "start_step": 2, "end_step_exclusive": 8},
        {"cycle_id": 1, "start_step": 12, "end_step_exclusive": 18},
    )
    records = [
        {
            "cycle_index": cycle_id,
            "cycle_start_observation_index": start,
            "cycle_end_observation_index": end - 1,
            "target_id": target_id,
            "grid_geometry_stable": True,
            "surface_valid_fraction_start": 1.0,
            "surface_valid_fraction_end": 1.0,
        }
        for cycle_id, start, end in ((0, 2, 8), (1, 12, 18))
        for target_id in (
            "recording_depth_0p08_full_grid_diagnostic",
            "t1_large_shallow_rectangular_pit_default",
            "t2_long_shallow_trench_default",
        )
    ]
    camera_mask = np.ones(24, dtype=np.uint8)
    camera_mask[14] = 0

    result = evaluate_local_cycle_eligibility(
        source_qpos=qpos,
        source_env_state=source_env,
        replay_qpos=qpos,
        replay_env_state=replay_env,
        source_cycles=cycles,
        candidate_records=records,
        realign_steps=(),
        camera_step_valid_mask=camera_mask,
        control_hz=50.0,
    )

    assert result["eligible_source_cycle_ids"] == [0]
    assert result["cycle_rows"][1]["reason_codes"] == [
        "cycle_contains_invalid_camera_step"
    ]


def test_local_cycle_eligibility_checks_every_pre_contact_qpos_step() -> None:
    source_qpos = np.zeros((12, 4), dtype=np.float32)
    replay_qpos = np.zeros((12, 4), dtype=np.float32)
    replay_qpos[3, 2] = 0.03
    source_env = np.zeros((12, 64), dtype=np.float32)
    replay_env = np.zeros((12, 89), dtype=np.float32)
    source_env[5, 61] = 1.0
    replay_env[5, 61] = 1.0
    records = [
        {
            "cycle_index": 0,
            "cycle_start_observation_index": 2,
            "cycle_end_observation_index": 8,
            "target_id": target_id,
            "grid_geometry_stable": True,
            "surface_valid_fraction_start": 1.0,
            "surface_valid_fraction_end": 1.0,
        }
        for target_id in (
            "recording_depth_0p08_full_grid_diagnostic",
            "t1_large_shallow_rectangular_pit_default",
            "t2_long_shallow_trench_default",
        )
    ]

    result = evaluate_local_cycle_eligibility(
        source_qpos=source_qpos,
        source_env_state=source_env,
        replay_qpos=replay_qpos,
        replay_env_state=replay_env,
        source_cycles=(
            {
                "cycle_id": 0,
                "start_step": 2,
                "dump_end_step": 8,
                "end_step_exclusive": 10,
            },
        ),
        candidate_records=records,
        realign_steps=(),
        control_hz=50.0,
    )

    assert result["eligible_source_cycle_ids"] == []
    assert "pre_contact_qpos_error_exceeded" in result["cycle_rows"][0][
        "reason_codes"
    ]
    assert result["cycle_rows"][0]["pre_contact_qpos_error"] == pytest.approx(
        0.03
    )


def test_local_cycle_eligibility_rejects_target_boundary_disagreement_and_nan() -> None:
    qpos = np.zeros((12, 4), dtype=np.float32)
    source_env = np.zeros((12, 64), dtype=np.float32)
    replay_env = np.zeros((12, 89), dtype=np.float32)
    source_env[3, 61] = 1.0
    replay_env[3, 61] = 1.0
    targets = (
        "recording_depth_0p08_full_grid_diagnostic",
        "t1_large_shallow_rectangular_pit_default",
        "t2_long_shallow_trench_default",
    )
    records = [
        {
            "cycle_index": 0,
            "cycle_start_observation_index": 2,
            "cycle_end_observation_index": 8 if index < 2 else 7,
            "target_id": target_id,
            "grid_geometry_stable": True,
            "surface_valid_fraction_start": 1.0,
            "surface_valid_fraction_end": float("nan") if index == 0 else 1.0,
        }
        for index, target_id in enumerate(targets)
    ]

    result = evaluate_local_cycle_eligibility(
        source_qpos=qpos,
        source_env_state=source_env,
        replay_qpos=qpos,
        replay_env_state=replay_env,
        source_cycles=(
            {"cycle_id": 0, "start_step": 2, "end_step_exclusive": 9},
        ),
        candidate_records=records,
        realign_steps=(),
        control_hz=50.0,
    )

    reasons = result["cycle_rows"][0]["reason_codes"]
    assert "replay_snapshot_boundary_disagreement" in reasons
    assert "target_cell_valid_fraction_below_minimum" in reasons


def test_realign_in_transition_masks_the_whole_transition_only() -> None:
    result = build_local_action_mask(
        source_mask=np.ones(20, dtype=np.uint8),
        replay_qc_mask=np.ones(20, dtype=np.uint8),
        cycle_windows=(
            {
                "cycle_id": 0,
                "start_step": 2,
                "work_end_step_exclusive": 6,
                "end_step_exclusive": 8,
            },
            {
                "cycle_id": 1,
                "start_step": 10,
                "work_end_step_exclusive": 14,
                "end_step_exclusive": 16,
            },
        ),
        eligible_cycle_ids=(0, 1),
        realign_steps=(8,),
        guard_steps=1,
    )

    expected = np.zeros(20, dtype=np.uint8)
    expected[2:6] = 1
    expected[10:14] = 1
    np.testing.assert_array_equal(result, expected)


def test_local_action_mask_is_three_way_intersection() -> None:
    source = np.ones(8, dtype=np.uint8)
    source[2] = 0
    replay_qc = np.ones(8, dtype=np.uint8)
    replay_qc[3] = 0

    result = build_local_action_mask(
        source_mask=source,
        replay_qc_mask=replay_qc,
        cycle_windows=(
            {"cycle_id": 0, "start_step": 1, "end_step_exclusive": 6},
        ),
        eligible_cycle_ids=(0,),
        realign_steps=(),
        guard_steps=0,
    )

    np.testing.assert_array_equal(
        result,
        np.asarray([0, 1, 0, 0, 1, 1, 0, 0], dtype=np.uint8),
    )
    assert np.all(result <= source)
    assert np.all(result <= replay_qc)


def test_local_candidate_allows_isolated_jpeg_damage_but_not_contract_damage() -> None:
    diagnostic = {
        "exception_count": 0,
        "step_sequence_complete": True,
        "pose_realign_count": 2,
    }
    isolated_jpeg = {
        "recorded_step_count": 100,
        "expected_step_count": 100,
        "errors": ["camera_jpeg_invalid:stick_up:50"],
    }

    assert candidate_is_locally_auditable(
        process_returncode=0,
        hdf5_audit=isolated_jpeg,
        diagnostic_summary=diagnostic,
    )

    contract_damage = {
        **isolated_jpeg,
        "errors": ["metadata_mismatch:env_state_contract_version"],
    }
    assert not candidate_is_locally_auditable(
        process_returncode=0,
        hdf5_audit=contract_damage,
        diagnostic_summary=diagnostic,
    )

    assert not candidate_is_locally_auditable(
        process_returncode=0,
        hdf5_audit=isolated_jpeg,
        diagnostic_summary={**diagnostic, "exception_count": 1},
    )


def test_retained_candidate_cleanup_is_locked_to_its_exact_attempt(
    tmp_path: Path,
) -> None:
    attempts = tmp_path / "strict_attempts"
    current = attempts / "episode_4" / "attempt_00"
    sibling = attempts / "episode_4" / "attempt_01"
    for attempt in (current, sibling):
        (attempt / "recorded").mkdir(parents=True)
        (attempt / "gate.json").write_text("{}", encoding="utf-8")
        (attempt / "hdf5_audit.json").write_text("{}", encoding="utf-8")
        (attempt / "diagnostics.jsonl").write_text("{}\n", encoding="utf-8")
    current_hdf5 = current / "recorded" / "episode_0.hdf5"
    sibling_hdf5 = sibling / "recorded" / "episode_0.hdf5"
    current_hdf5.write_bytes(b"current")
    sibling_hdf5.write_bytes(b"sibling")

    with pytest.raises(ValueError, match="exact current attempt"):
        remove_retained_attempt_hdf5(
            path=sibling_hdf5,
            attempts_root=attempts,
            attempt_dir=current,
            reason="ranking_replaced",
        )

    result = remove_retained_attempt_hdf5(
        path=current_hdf5,
        attempts_root=attempts,
        attempt_dir=current,
        reason="ranking_replaced",
    )
    assert result["removed"] is True
    assert sibling_hdf5.read_bytes() == b"sibling"
