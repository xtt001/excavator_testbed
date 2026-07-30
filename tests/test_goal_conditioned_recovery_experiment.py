from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest
import yaml

from testbed.eval.goal_conditioned_recovery_contracts import (
    qpos_path_sha256,
)
from testbed.eval.goal_conditioned_recovery_experiment import (
    CONDITION_IDS,
    ExperimentContractError,
    assert_three_way_single_factor_configs,
    build_goal_conditioned_functional_config,
    build_goal_conditioned_recovery_preflight,
    canonical_goal_id,
    collect_goal_conditioned_recovery_evidence,
    validate_goal_conditioned_functional_record,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_config(tmp_path: Path) -> Path:
    checkpoints: dict[str, str] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        path = tmp_path / "ckpts" / primitive / "policy_best.ckpt"
        path.parent.mkdir(parents=True)
        path.write_bytes(f"{primitive}-a0".encode())
        checkpoints[f"{primitive}_ckpt_path"] = str(path)
    path = tmp_path / "a0.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "task": {
                    "camera_names": [
                        "stick_up",
                        "stick_down",
                        "eye_left",
                        "eye_right",
                    ]
                },
                "eval": {
                    "num_rollouts": 1,
                    "no_overwrite": True,
                    "save_video": True,
                    "record_hdf5": True,
                    "save_rollout_logs": True,
                    "video_dir": "/old/videos",
                    "results_dir": "/old/results",
                    "rollout_log_dir": "/old/results/rollouts",
                    "hdf5_dir": "/old/results/hdf5_rollouts",
                    "record_hdf5_metadata": {"temporal_variant": "A0"},
                    "target_cycle_gate": None,
                    "target_cycle_gate_terminal_hold_steps": 0,
                },
                "policy": {
                    **checkpoints,
                    "dig_cut_planner": {
                        "enabled": True,
                        "mode": "operator_prior_sweep_belief",
                        "fallback_mode": "raise",
                        "hold_token_until_skill_exit": True,
                    },
                    "act_params": {
                        "temporal_agg_window": 100,
                        "temporal_agg_weight_order": "legacy_oldest_first",
                        "temporal_agg_decay": 0.01,
                    },
                    "box_emptying": {
                        "safety_enabled": True,
                        "carry_start_envelope": {
                            "enabled": True,
                            "hold_steps": 3,
                        },
                        "functional_cycle_gate": {
                            "enabled": True,
                            "target_cycles": 10,
                        },
                        "safety": {
                            "stuck_window_steps": 50,
                            "wall_high_force_n": 100000.0,
                        },
                    },
                    "switch": {
                        "return_to_dig_start_envelope_gate_enabled": True,
                        "return_max_steps": 420,
                    },
                },
                "boundary": {"profile": "v2_4_5_spatial_mass"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _goal(condition_index: int) -> dict[str, object]:
    entry = [0.2 + 0.01 * condition_index, 0.4]
    exit_ = [0.5 + 0.01 * condition_index, 0.8]
    length = 0.5
    goal: dict[str, object] = {
        "schema": "continuous_cut_goal_v1",
        "target_cell_id": condition_index,
        "entry_xz_m": entry,
        "exit_xz_m": exit_,
        "direction_xz": [0.6, 0.8],
        "cut_length_m": length,
        "planned_depth_m": 0.12,
        "payload_intent_kg": 45.0,
        "effect_intent": {"kind": "remove_soil", "target_mass_kg": 45.0},
        "terrain_signature": {
            "schema": "terrain_signature_v1",
            "surface_depth_m": [0.08] * 6,
        },
    }
    goal["goal_id"] = canonical_goal_id(goal)
    return goal


def _condition_set(tmp_path: Path) -> Path:
    conditions: dict[str, object] = {}
    for index, condition_id in enumerate(CONDITION_IDS):
        goal = _goal(index)
        token = [0.0] * 18
        token[2:6] = [0.08, 0.05, 0.06, 0.10]
        token[6] = 1.0
        token[7:11] = [0.5, 0.4, 0.6, 0.2]
        token[11:15] = [0.03] * 4
        token[15] = 0.10
        token[16:18] = [1.0, 1.0]
        conditions[condition_id] = {
            "goal": goal,
            "derived_return_envelope": {
                "schema": "cut_goal_return_envelope_v1",
                "goal_id": goal["goal_id"],
                "derivation": "continuous_cut_goal",
                "token": token,
                "prior_independent_local_depth_m": 0.08,
                "prior_independent_plane_depth_m": 0.06,
                "handoff_reference": {
                    "goal_id": goal["goal_id"],
                    "qpos": [0.5, 0.4, 0.6, 0.2],
                    "qpos_half_width": [0.03] * 4,
                    "qvel_abs_max": 0.10,
                    "spatial_half_width_norm": 0.05,
                    "expected_contact": True,
                    "predictor_profile": "continuous_goal_reference_v1",
                    "predictor_version": "1",
                    "predictor_code_sha256": "a" * 64,
                },
            },
            "support_ood": {
                "schema": "continuous_goal_support_diagnostic_v1",
                "support_status": "supported",
                "whole_goal_distance": 0.2,
                "episode_snap_applied": False,
                "diagnostic_only": True,
            },
            "provenance": (
                {"source_episode_id": 171, "diagnostic_only": True}
                if condition_id == "E0_expert_goal"
                else {"generator": condition_id}
            ),
        }
    path = tmp_path / "condition_set.json"
    path.write_text(
        json.dumps(
            {
                "schema": "goal_conditioned_three_way_condition_set_v1",
                "conditions": conditions,
            }
        ),
        encoding="utf-8",
    )
    return path


def _predictor_manifest(condition_set_path: Path, tmp_path: Path) -> Path:
    condition_set = json.loads(condition_set_path.read_text())
    conditions: dict[str, object] = {}
    for condition_id in CONDITION_IDS:
        goal_id = condition_set["conditions"][condition_id]["goal"]["goal_id"]
        qpos_path = [
            [0.5, 0.4, 0.6, 0.2],
            [0.51, 0.41, 0.61, 0.21],
        ]
        path_sha256 = hashlib.sha256(
            b"".join(
                struct.pack("<f", value)
                for row in qpos_path
                for value in row
            )
        ).hexdigest()
        conditions[condition_id] = {
            "status": "passed",
            "goal_id": goal_id,
            "predictor": {
                "provider": "test_predictor",
                "profile": "continuous_goal_reference_v1",
                "version": "1",
                "code_sha256": "a" * 64,
            },
            "handoff_qpos": qpos_path[0],
            "handoff_qvel": [0.0] * 4,
            "qpos_order": ["swing", "boom", "stick", "bucket"],
            "planned_qpos_path": qpos_path,
            "path_sha256": path_sha256,
            "unity_measurement": {
                "schema": "continuous_goal_worktool_sweep_measurement_v1",
                "goal_id": goal_id,
                "goal_sha256": goal_id,
                "path_sha256": path_sha256,
                "predictor_profile": "continuous_goal_reference_v1",
                "predictor_version": "1",
                "predictor_code_sha256": "a" * 64,
                "nominal_minimum_clearance_m": 0.31,
                "witnesses": [
                    {
                        "link": link,
                        "wall": wall,
                        "minimum_clearance_m": 0.31,
                    }
                    for link in ("boom", "stick", "bucket")
                    for wall in ("x_min", "x_max", "z_min", "z_max")
                ],
            },
        }
    path = tmp_path / "predictor.json"
    path.write_text(
        json.dumps(
            {
                "schema": "continuous_goal_qpos_sweep_predictor_manifest_v1",
                "conditions": conditions,
            }
        ),
        encoding="utf-8",
    )
    return path


def _live_record(condition_id: str, *, passed: bool = True) -> dict[str, object]:
    return {
        "schema": "goal_conditioned_return_to_dig_probe_record_v1",
        "condition_id": condition_id,
        "attempt_index": 1,
        "retry_count": 0,
        "live_sequence_index": CONDITION_IDS.index(condition_id) + 1,
        "status": "passed" if passed else "failed",
        "initial_state_valid": True,
        "reset_fairness": {
            "qpos_max_abs_delta": 0.0,
            "qvel_abs_max": 0.0,
            "qvel_cross_condition_max_abs_delta": 0.0,
            "bucket_tip_displacement_m": 0.0,
            "terrain_depth_max_abs_delta_m": 0.0,
            "remaining_mass_abs_delta_kg": 0.0,
            "soil_seed_controlled": False,
            "soil_seed_note": "seed unavailable; measured state recorded",
        },
        "return_handoff_passed": passed,
        "worktool_3d_guard_passed": True,
        "actual_path_within_reference_sweep": True,
        "wall_contact_count": 0,
        "bottom_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "terminal_zero_action": True,
        "neutral_acknowledged": True,
        "abort_reason": None if passed else "dig_not_completed",
    }


def test_missing_predictor_builds_blocked_offline_preflight_and_locked_configs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "goal_conditioned_runtime_recovery_v1"
    manifest = build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=_condition_set(tmp_path),
        output_root=root,
    )

    assert manifest["status"] == "blocked"
    assert manifest["primary_blocker"] == "continuous_goal_3d_predictor_missing"
    assert manifest["live_allowed"] is False
    assert manifest["functional_1x10_allowed"] is False
    assert manifest["exact_diagnostic_artifact"] is None
    assert len(manifest["a0_contract"]["checkpoints"]) == 4
    assert all(
        len(item["sha256"]) == 64
        for item in manifest["a0_contract"]["checkpoints"].values()
    )
    records = [
        json.loads(
            (root / "offline" / f"{condition_id}.json").read_text()
        )
        for condition_id in CONDITION_IDS
    ]
    assert {record["status"] for record in records} == {"blocked"}
    assert all(
        record["blockers"] == ["continuous_goal_3d_predictor_missing"]
        for record in records
    )
    configs = {
        condition_id: root / "configs" / f"{condition_id}.yaml"
        for condition_id in CONDITION_IDS
    }
    assert_three_way_single_factor_configs(configs)
    e0 = yaml.safe_load(configs["E0_expert_goal"].read_text())
    assert e0["policy"]["dig_cut_planner"]["mode"] == (
        "continuous_goal_conditioned"
    )
    return_envelope = e0["policy"]["dig_cut_planner"][
        "return_start_envelope"
    ]
    assert return_envelope["use_cell_prior"] is False
    assert return_envelope["qpos_from_relocate"]["enabled"] is False
    assert return_envelope["spatial_from_relocate"]["enabled"] is False
    assert "source_episode_id" not in json.dumps(e0)

    with pytest.raises(FileExistsError):
        build_goal_conditioned_recovery_preflight(
            base_config_path=_base_config(tmp_path / "other"),
            condition_set_path=_condition_set(tmp_path / "other"),
            output_root=root,
        )


def test_missing_predictor_does_not_require_a_fabricated_return_envelope(
    tmp_path: Path,
) -> None:
    condition_path = _condition_set(tmp_path)
    payload = json.loads(condition_path.read_text())
    for condition in payload["conditions"].values():
        condition.pop("derived_return_envelope")
    condition_path.write_text(json.dumps(payload))

    root = tmp_path / "experiment"
    manifest = build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_path,
        output_root=root,
    )

    assert manifest["status"] == "blocked"
    assert manifest["primary_blocker"] == (
        "continuous_goal_3d_predictor_missing"
    )
    record = json.loads(
        (root / "offline" / "G1_planner_continuous_goal.json").read_text()
    )
    assert record["blockers"] == ["continuous_goal_3d_predictor_missing"]
    assert record["return_envelope_contract_status"] == (
        "not_evaluated_predictor_missing"
    )


def test_predictor_pass_still_rejects_incomplete_return_envelope(
    tmp_path: Path,
) -> None:
    condition_path = _condition_set(tmp_path)
    payload = json.loads(condition_path.read_text())
    payload["conditions"]["E0_expert_goal"]["derived_return_envelope"].pop(
        "prior_independent_plane_depth_m"
    )
    condition_path.write_text(json.dumps(payload))
    predictor_path = _predictor_manifest(condition_path, tmp_path)

    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_path,
        predictor_manifest_path=predictor_path,
        output_root=root,
    )

    record = json.loads(
        (root / "offline" / "E0_expert_goal.json").read_text()
    )
    assert record["status"] == "failed"
    assert "return_envelope_contract_invalid" in record["blockers"]


def test_three_way_guard_detects_non_condition_a0_drift(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=_condition_set(tmp_path),
        output_root=root,
    )
    configs = {
        condition_id: root / "configs" / f"{condition_id}.yaml"
        for condition_id in CONDITION_IDS
    }
    changed = yaml.safe_load(configs["G1_planner_continuous_goal"].read_text())
    changed["policy"]["act_params"]["temporal_agg_window"] = 20
    configs["G1_planner_continuous_goal"].write_text(
        yaml.safe_dump(changed),
        encoding="utf-8",
    )

    with pytest.raises(ExperimentContractError, match="a0_contract_drift"):
        assert_three_way_single_factor_configs(configs)


def test_passed_offline_and_three_live_passes_unlock_only_conditional_1x10(
    tmp_path: Path,
) -> None:
    condition_set = _condition_set(tmp_path)
    root = tmp_path / "experiment"
    manifest = build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        predictor_manifest_path=_predictor_manifest(condition_set, tmp_path),
        output_root=root,
    )
    assert manifest["status"] == "passed"
    assert manifest["live_allowed"] is True
    assert manifest["functional_1x10_allowed"] is False

    live_paths: dict[str, Path] = {}
    for condition_id in CONDITION_IDS:
        path = tmp_path / f"{condition_id}.json"
        path.write_text(json.dumps(_live_record(condition_id)))
        live_paths[condition_id] = path
    evidence_root = tmp_path / "evidence"
    result = collect_goal_conditioned_recovery_evidence(
        experiment_manifest_path=root / "experiment_manifest.json",
        live_record_paths=live_paths,
        output_dir=evidence_root,
    )

    decision = result["causal_decision"]
    assert decision["classification"] == (
        "exact_tuple_runtime_constraint_unnecessary"
    )
    assert decision["functional_1x10_allowed"] is True
    assert decision["retraining_allowed"] is False
    assert decision["effect_model_allowed"] is False

    functional_root = tmp_path / "goal_conditioned_functional_10cycle_validation_v1"
    functional = build_goal_conditioned_functional_config(
        causal_decision_path=evidence_root / "causal_decision.json",
        output_dir=functional_root,
    )
    config = yaml.safe_load(
        Path(functional["config_path"]).read_text(encoding="utf-8")
    )
    assert config["eval"]["num_rollouts"] == 1
    assert config["policy"]["act_params"]["temporal_agg_window"] == 100
    assert config["policy"]["box_emptying"]["functional_cycle_gate"] == {
        "enabled": True,
        "target_cycles": 10,
        "max_bucket_mass_kg": 15.0,
    }
    source = config["policy"]["dig_cut_planner"][
        "continuous_goal_conditioned"
    ]["source"]
    assert source == {"kind": "planner_continuous_goal"}


def test_qpos_path_hash_and_unity_lineage_are_cross_language_locked(
    tmp_path: Path,
) -> None:
    path = [
        [0.5, 0.4, 0.6, 0.2],
        [0.51, 0.41, 0.61, 0.21],
    ]
    assert qpos_path_sha256(path) == (
        "d1227501b292edf686f569b9ba515d164"
        "4801775f207ed2dd0f7d85c31b73781"
    )
    condition_set = _condition_set(tmp_path)
    predictor_path = _predictor_manifest(condition_set, tmp_path)
    predictor = json.loads(predictor_path.read_text())
    predictor["conditions"]["G1_planner_continuous_goal"][
        "unity_measurement"
    ]["predictor_version"] = "drifted"
    predictor_path.write_text(json.dumps(predictor))

    manifest = build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        predictor_manifest_path=predictor_path,
        output_root=tmp_path / "experiment",
    )

    assert manifest["status"] == "blocked"
    record = json.loads(
        (
            tmp_path
            / "experiment/offline/G1_planner_continuous_goal.json"
        ).read_text()
    )
    assert record["blockers"] == ["continuous_goal_3d_predictor_missing"]


def test_causal_priority_keeps_return_blocker_separate_from_planner(
    tmp_path: Path,
) -> None:
    condition_set = _condition_set(tmp_path)
    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        predictor_manifest_path=_predictor_manifest(condition_set, tmp_path),
        output_root=root,
    )
    live_paths: dict[str, Path] = {}
    for condition_id in CONDITION_IDS:
        record = _live_record(condition_id)
        if condition_id == "G1_planner_continuous_goal":
            record["status"] = "failed"
            record["return_handoff_passed"] = False
            record["abort_reason"] = "return_envelope_timeout"
        path = tmp_path / f"{condition_id}.json"
        path.write_text(json.dumps(record))
        live_paths[condition_id] = path

    result = collect_goal_conditioned_recovery_evidence(
        experiment_manifest_path=root / "experiment_manifest.json",
        live_record_paths=live_paths,
        output_dir=tmp_path / "evidence",
    )

    assert result["causal_decision"]["classification"] == (
        "return_handoff_blocker"
    )
    assert result["causal_decision"]["planner_filter_change_allowed"] is False
    assert result["causal_decision"]["functional_1x10_allowed"] is False


def test_e0_pass_g1_execution_fail_classifies_goal_conditioning_gap(
    tmp_path: Path,
) -> None:
    condition_set = _condition_set(tmp_path)
    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        predictor_manifest_path=_predictor_manifest(condition_set, tmp_path),
        output_root=root,
    )
    live_paths: dict[str, Path] = {}
    for condition_id in CONDITION_IDS:
        record = _live_record(condition_id)
        if condition_id == "G1_planner_continuous_goal":
            record["status"] = "failed"
            record["abort_reason"] = "dig_not_completed"
        path = tmp_path / f"{condition_id}.json"
        path.write_text(json.dumps(record))
        live_paths[condition_id] = path

    decision = collect_goal_conditioned_recovery_evidence(
        experiment_manifest_path=root / "experiment_manifest.json",
        live_record_paths=live_paths,
        output_dir=tmp_path / "evidence",
    )["causal_decision"]

    assert decision["classification"] == (
        "act_goal_conditioning_or_support_insufficient"
    )
    assert decision["retraining_allowed"] is False
    assert decision["new_recording_allowed"] is False


def test_typed_safety_abort_cannot_be_labeled_as_passing_probe(
    tmp_path: Path,
) -> None:
    condition_set = _condition_set(tmp_path)
    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        predictor_manifest_path=_predictor_manifest(condition_set, tmp_path),
        output_root=root,
    )
    live_paths: dict[str, Path] = {}
    for condition_id in CONDITION_IDS:
        record = _live_record(condition_id)
        if condition_id == "W1_internal_wall_safe_goal":
            record["wall_contact_count"] = 1
        path = tmp_path / f"{condition_id}.json"
        path.write_text(json.dumps(record))
        live_paths[condition_id] = path

    with pytest.raises(ExperimentContractError, match="passed_with_safety_abort"):
        collect_goal_conditioned_recovery_evidence(
            experiment_manifest_path=root / "experiment_manifest.json",
            live_record_paths=live_paths,
            output_dir=tmp_path / "evidence",
        )


def test_reset_fairness_violation_is_invalid_without_retry(
    tmp_path: Path,
) -> None:
    condition_set = _condition_set(tmp_path)
    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        predictor_manifest_path=_predictor_manifest(condition_set, tmp_path),
        output_root=root,
    )
    live_paths: dict[str, Path] = {}
    for condition_id in CONDITION_IDS:
        record = _live_record(condition_id)
        if condition_id == "G1_planner_continuous_goal":
            record["status"] = "invalid"
            record["initial_state_valid"] = False
            record["reset_fairness"]["qpos_max_abs_delta"] = 0.006
        path = tmp_path / f"{condition_id}.json"
        path.write_text(json.dumps(record))
        live_paths[condition_id] = path

    result = collect_goal_conditioned_recovery_evidence(
        experiment_manifest_path=root / "experiment_manifest.json",
        live_record_paths=live_paths,
        output_dir=tmp_path / "evidence",
    )

    assert result["causal_decision"]["classification"] == (
        "reset_fairness_invalid"
    )
    assert result["causal_decision"]["automatic_retry_allowed"] is False


def test_functional_validation_requires_single_strong_ten_cycle_record(
    tmp_path: Path,
) -> None:
    record = {
        "schema": "goal_conditioned_functional_10cycle_record_v1",
        "status": "passed",
        "run_count": 1,
        "temporal_agg_window": 100,
        "wall_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "hard_bottom_events": [
            {"neutral_action_sent": True, "replan_completed": True}
        ],
        "terminal_return_handoff_ready": True,
        "terminal_zero_action": True,
        "terminal_neutral_acknowledged": True,
        "cycles": [
            {
                "cycle_index": cycle,
                "goal_id": f"{cycle + 1:064x}",
                "return_goal_id": f"{cycle + 1:064x}",
                "geometry_consistent": True,
                "worktool_3d_guard_passed": True,
                "exhausted_physical_cell_reused": False,
                "return_handoff_ready": True,
                "next_dig_started": cycle < 9,
            }
            for cycle in range(10)
        ],
    }
    path = tmp_path / "functional_record.json"
    path.write_text(json.dumps(record))

    artifact = validate_goal_conditioned_functional_record(
        record_path=path,
        output_dir=tmp_path / "validation",
    )

    assert artifact["schema"] == (
        "goal_conditioned_functional_10cycle_validation_v1"
    )
    assert artifact["status"] == "passed"
    assert artifact["formal_bundle_allowed"] is False
    assert artifact["functional_3x10_allowed"] is False

    record["cycles"][4]["return_goal_id"] = "f" * 64
    bad = tmp_path / "bad_record.json"
    bad.write_text(json.dumps(record))
    with pytest.raises(ExperimentContractError, match="goal_identity_drift"):
        validate_goal_conditioned_functional_record(
            record_path=bad,
            output_dir=tmp_path / "bad-validation",
        )


def test_source_drift_blocks_collection_without_partial_outputs(
    tmp_path: Path,
) -> None:
    condition_set = _condition_set(tmp_path)
    root = tmp_path / "experiment"
    build_goal_conditioned_recovery_preflight(
        base_config_path=_base_config(tmp_path),
        condition_set_path=condition_set,
        output_root=root,
    )
    condition_set.write_text(condition_set.read_text() + " ")
    output = tmp_path / "evidence"

    with pytest.raises(ExperimentContractError, match="source_artifact_drift"):
        collect_goal_conditioned_recovery_evidence(
            experiment_manifest_path=root / "experiment_manifest.json",
            live_record_paths=None,
            output_dir=output,
        )
    assert not output.exists()
