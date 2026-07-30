from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.return_handoff_owner_diagnostic import (
    analyze_return_handoff_owner_replay,
    build_return_handoff_owner_config,
    validate_return_handoff_owner_config,
)
from testbed.eval.return_handoff_owner_probe import (
    _validate_owner_control_evidence,
    summarize_bounded_rollout,
)
from testbed.planner.primitive.effects.return_handoff import (
    ReturnStartEnvelopeGateConfig,
    ReturnStartEnvelopeGateInputs,
    ReturnStartEnvelopeGateService,
)


def _gate_config() -> ReturnStartEnvelopeGateConfig:
    return ReturnStartEnvelopeGateConfig(
        enabled=True,
        action_dim=4,
        spatial_tolerance=0.10,
        depth_tolerance_m=0.08,
        local_depth_tolerance_m=0.005,
        plane_depth_tolerance_m=0.0,
        plane_depth_mode="p50_floor",
        qpos_tolerance=0.04,
        require_contact=True,
    )


def _state(
    *,
    qpos_1: float,
    local_depth_m: float,
    plane_depth_m: float,
    contact: float,
) -> dict[str, object]:
    env_state = [0.0] * ENV_STATE_V2_4_DIM
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = -0.9449
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.3614
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = (
        local_depth_m
    )
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = (
        plane_depth_m
    )
    env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = contact
    return {
        "qpos": [0.5533, qpos_1, 0.3373, 0.2099],
        "qvel": [-0.01, 0.207, -0.18, 0.098],
        "env_state": env_state,
    }


def _recorded_rows() -> list[dict[str, object]]:
    token = np.asarray(
        [
            -0.750741,
            0.394141,
            0.0,
            0.2,
            0.0,
            0.08,
            0.0,
            0.539822,
            0.531652,
            0.395799,
            0.182682,
            0.02,
            0.068013,
            0.030954,
            0.030223,
            0.614021,
            1.0,
            1.0,
        ],
        dtype=np.float32,
    )
    lower = token.copy()
    upper = token.copy()
    lower[0], upper[0] = -0.930583, -0.511237
    lower[1], upper[1] = 0.172753, 0.535514
    qpos_lower = [0.525625, 0.431589, 0.261897, 0.100964]
    qpos_upper = [0.552781, 0.608137, 0.514475, 0.360878]
    for offset in range(4):
        lower[7 + offset] = qpos_lower[offset]
        upper[7 + offset] = qpos_upper[offset]
    prior_mapping = {
        "dig_start_local_depth_m": {
            "p05": 0.005717,
            "p50": 0.012831,
            "p95": 0.037086,
        },
        "dig_start_plane_depth_m": {
            "p05": 0.027709,
            "p50": 0.304557,
            "p95": 0.472971,
        },
    }
    states = [
        {
            "step_id": 9,
            "cycle_id": 7,
            "skill_name": "return",
            **_state(
                qpos_1=0.6479075,
                local_depth_m=0.0016637,
                plane_depth_m=0.1775981,
                contact=0.0,
            ),
        },
        {
            "step_id": 10,
            "cycle_id": 7,
            "skill_name": "return",
            **_state(
                qpos_1=0.6520577,
                local_depth_m=0.0142121,
                plane_depth_m=0.1850844,
                contact=1.0,
            ),
        },
        {
            "step_id": 11,
            "cycle_id": 7,
            "skill_name": "return",
            **_state(
                qpos_1=0.6561982,
                local_depth_m=0.0266070,
                plane_depth_m=0.1925670,
                contact=1.0,
            ),
        },
    ]
    service = ReturnStartEnvelopeGateService(_gate_config())
    for index in (1, 2):
        previous = states[index - 1]
        result = service.evaluate(
            ReturnStartEnvelopeGateInputs(
                token=token,
                env_state=previous["env_state"],
                qpos=previous["qpos"],
                qvel=previous["qvel"],
                prior_bounds=lambda: (lower, upper),
                prior_mapping=lambda: prior_mapping,
                use_prior_spatial_bounds=True,
                use_prior_qpos_bounds=True,
                use_prior_depth_bounds=True,
            )
        )
        states[index].update(
            {
                "return_start_envelope_tokens": token.tolist(),
                "return_to_dig_start_envelope_ready": result.ready,
                "return_to_dig_start_envelope_error": result.error,
                "return_to_dig_start_envelope_checks": result.checks,
            }
        )
    return states


def _source_config() -> dict[str, object]:
    return {
        "agx": {"host": "127.0.0.1", "port": 5057, "timeout": 10.0},
        "eval": {
            "num_rollouts": 1,
            "seed": 1000,
            "target_cycle_gate": 10,
            "no_overwrite": True,
            "video_dir": "/source/videos",
            "results_dir": "/source/results",
            "rollout_log_dir": "/source/results/rollouts",
            "record_hdf5": False,
            "hdf5_dir": "/source/disabled_hdf5",
            "record_hdf5_metadata": {"diagnostic_only": True},
        },
        "policy": {
            "switch": {
                "return_to_dig_start_envelope_gate_enabled": True,
                "return_to_dig_start_envelope_spatial_tolerance": 0.10,
                "return_to_dig_start_envelope_depth_tolerance_m": 0.08,
                "return_to_dig_start_envelope_local_depth_tolerance_m": 0.005,
                "return_to_dig_start_envelope_plane_depth_tolerance_m": 0.0,
                "return_to_dig_start_envelope_plane_depth_mode": "p50_floor",
                "return_to_dig_start_envelope_qpos_tolerance": 0.04,
                "return_to_dig_start_envelope_require_contact": True,
                "return_max_steps": 420,
            },
            "box_emptying": {
                "safety": {
                    "wall_high_force_n": 100_000.0,
                    "stuck_window_steps": 50,
                }
            },
        },
    }


def test_offline_replay_exposes_contact_to_plane_depth_coupling() -> None:
    result = analyze_return_handoff_owner_replay(
        _recorded_rows(),
        gate_config=_gate_config(),
        cycle_id=7,
    )

    assert result["source_replay"]["fidelity"] == "exact"
    assert result["contact_only"]["first_ready_step"] is None
    assert result["contact_only"]["ready_before_qpos_violation"] is False
    assert result["depth_owner_audit"] == {
        "contact_to_plane_depth_coupling_observed": True,
        "contact_only_blocker": "plane_depth_m",
        "source_plane_floor_source": "p05_local_contact_prior",
        "contact_only_plane_floor_source": "p50",
        "effective_depth_owner": "runtime_prior",
        "token_depth_simultaneously_applied": False,
    }


def test_owner_isolated_replay_preserves_depth_bounds_and_readies_first() -> None:
    result = analyze_return_handoff_owner_replay(
        _recorded_rows(),
        gate_config=_gate_config(),
        cycle_id=7,
    )

    isolated = result["owner_isolated"]
    assert isolated["contact_owner"] == "return_start_envelope_token[6]"
    assert isolated["depth_owner"] == "runtime_prior_p05_p95"
    assert isolated["depth_bounds_unchanged_from_source"] is True
    assert isolated["first_ready_step"] == 10
    assert isolated["first_qpos_violation_step"] == 11
    assert isolated["ready_before_qpos_violation"] is True
    assert result["bounded_diagnostic_allowed"] is True


def test_request_local_config_changes_only_owners_and_run_outputs(
    tmp_path: Path,
) -> None:
    source = _source_config()
    frozen = copy.deepcopy(source)
    run_root = tmp_path / "run"

    candidate = build_return_handoff_owner_config(
        source,
        run_root=run_root,
    )
    validate_return_handoff_owner_config(
        source=source,
        candidate=candidate,
        run_root=run_root,
    )

    assert source == frozen
    switch = candidate["policy"]["switch"]
    assert switch["return_to_dig_start_envelope_require_contact"] is False
    assert switch["return_to_dig_start_envelope_plane_depth_mode"] == "range"
    assert candidate["policy"]["box_emptying"]["safety"] == (
        source["policy"]["box_emptying"]["safety"]
    )
    assert candidate["eval"]["target_cycle_gate"] == 8
    assert candidate["eval"]["num_rollouts"] == 1
    assert candidate["eval"]["record_hdf5"] is False
    assert candidate["eval"]["results_dir"] == str(run_root / "results")


def test_target_scoped_config_preserves_first_seven_handoff_semantics(
    tmp_path: Path,
) -> None:
    source = _source_config()
    run_root = tmp_path / "run"

    candidate = build_return_handoff_owner_config(
        source,
        run_root=run_root,
        min_completed_dump_count=7,
        attempt_id="target_scoped",
        diagnostic_schema="target_scoped_v2",
    )
    validate_return_handoff_owner_config(
        source=source,
        candidate=candidate,
        run_root=run_root,
        min_completed_dump_count=7,
        attempt_id="target_scoped",
        diagnostic_schema="target_scoped_v2",
    )

    switch = candidate["policy"]["switch"]
    assert switch["return_to_dig_start_envelope_require_contact"] is True
    assert switch["return_to_dig_start_envelope_plane_depth_mode"] == (
        "p50_floor"
    )
    control = candidate["policy"]["box_emptying"][
        "return_start_envelope_owner_control"
    ]
    assert control == {
        "enabled": True,
        "diagnostic_only": True,
        "min_completed_dump_count": 7,
        "contact_owner": "token",
        "depth_owner": "runtime_prior_p05_p95",
    }


def test_target_scoped_config_can_bound_the_same_diagnostic_at_ten_dumps(
    tmp_path: Path,
) -> None:
    source = _source_config()
    frozen = copy.deepcopy(source)
    run_root = tmp_path / "run"

    candidate = build_return_handoff_owner_config(
        source,
        run_root=run_root,
        min_completed_dump_count=7,
        target_completed_dumps=10,
        attempt_id="target_scoped_gate10",
        diagnostic_schema="target_scoped_multicycle_v1",
    )
    validate_return_handoff_owner_config(
        source=source,
        candidate=candidate,
        run_root=run_root,
        min_completed_dump_count=7,
        target_completed_dumps=10,
        attempt_id="target_scoped_gate10",
        diagnostic_schema="target_scoped_multicycle_v1",
    )

    assert source == frozen
    assert candidate["eval"]["target_cycle_gate"] == 10
    assert candidate["eval"]["num_rollouts"] == 1
    assert candidate["eval"]["record_hdf5"] is False
    assert candidate["policy"]["switch"] == source["policy"]["switch"]


def test_bounded_rollout_summary_reports_eighth_handoff_and_dump() -> None:
    rows = [
        {
            "step_id": 3554,
            "cycle_id": 7,
            "skill_name": "return",
            "return_to_dig_start_envelope_ready": True,
            "return_to_dig_start_envelope_checks": {
                "qpos_1": {
                    "value": 0.6479,
                    "min": 0.3915,
                    "max": 0.6481,
                    "ok": True,
                }
            },
            "box_safety_reason": "",
        },
        {
            "step_id": 3555,
            "cycle_id": 7,
            "skill_name": "dig",
            "skill_switch_reason": "return_to_dig_start_envelope_ready",
            "box_safety_reason": "",
        },
        {
            "step_id": 3900,
            "cycle_id": 7,
            "skill_name": "dump",
            "dump_end_mask": 1.0,
            "box_safety_reason": "",
        },
    ]
    result = summarize_bounded_rollout(
        rows=rows,
        summary={
            "completed_dump_count": 8,
            "rollout_stop_reason": "target_cycle_gate_terminal_hold_reached",
            "target_cycle_gate": 8,
            "target_cycle_gate_success": True,
        },
    )

    assert result["entered_eighth_dig"] is True
    assert result["completed_eighth_dump"] is True
    assert result["first_eighth_dig_step"] == 3555
    assert result["handoff_ready_step"] == 3554
    assert result["termination_category"] == "target_eighth_dump_completed"


def test_bounded_rollout_summary_targets_tenth_handoff_and_dump() -> None:
    rows = [
        {
            "step_id": 3475,
            "cycle_id": 7,
            "skill_name": "dig",
            "return_to_dig_start_envelope_ready": True,
            "box_safety_reason": "",
        },
        {
            "step_id": 4200,
            "cycle_id": 9,
            "skill_name": "return",
            "return_to_dig_start_envelope_ready": True,
            "box_safety_reason": "",
        },
        {
            "step_id": 4201,
            "cycle_id": 9,
            "skill_name": "dig",
            "return_to_dig_start_envelope_ready": True,
            "box_safety_reason": "",
        },
        {
            "step_id": 4550,
            "cycle_id": 9,
            "skill_name": "dump",
            "dump_end_mask": 1.0,
            "box_safety_reason": "",
        },
    ]

    result = summarize_bounded_rollout(
        rows=rows,
        summary={
            "completed_dump_count": 9,
            "target_cycle_completed_dump_count": 10,
            "dump_end_count": 10,
            "rollout_stop_reason": "target_cycle_gate_terminal_hold_reached",
        },
        target_completed_dumps=10,
    )

    assert result["target_completed_dumps"] == 10
    assert result["entered_target_dig"] is True
    assert result["completed_target_dump"] is True
    assert result["first_target_dig_step"] == 4201
    assert result["handoff_ready_step"] == 4200
    assert result["termination_category"] == "target_10_dump_completed"


def test_bounded_summary_does_not_relabel_earlier_ready_as_eighth_handoff() -> None:
    result = summarize_bounded_rollout(
        rows=[
            {
                "step_id": 2011,
                "cycle_id": 4,
                "skill_name": "return",
                "return_to_dig_start_envelope_ready": True,
                "box_safety_reason": "",
            },
            {
                "step_id": 2268,
                "cycle_id": 4,
                "skill_name": "return",
                "return_to_dig_start_envelope_ready": False,
                "box_safety_reason": "timeout",
            },
        ],
        summary={
            "completed_dump_count": 4,
            "rollout_stop_reason": "box_safety:timeout",
            "target_cycle_gate": 8,
            "target_cycle_gate_success": False,
        },
    )

    assert result["entered_eighth_dig"] is False
    assert result["handoff_ready_step"] is None
    assert result["termination_category"] == "timeout_stop"


def test_bounded_summary_uses_terminal_target_cycle_count() -> None:
    result = summarize_bounded_rollout(
        rows=[
            {
                "step_id": 3475,
                "cycle_id": 7,
                "skill_name": "dig",
                "skill_switch_reason": "return_to_dig_next_dig_entry_ready",
                "return_to_dig_start_envelope_ready": True,
                "box_safety_reason": "",
            },
            {
                "step_id": 3799,
                "cycle_id": 7,
                "skill_name": "dump",
                "dump_end_mask": 1.0,
                "box_safety_reason": "",
            },
        ],
        summary={
            "completed_dump_count": 7,
            "target_cycle_completed_dump_count": 8,
            "dump_end_count": 8,
            "target_cycle_gate": 8,
            "target_cycle_gate_success": True,
            "rollout_stop_reason": "target_cycle_gate_terminal_hold_reached",
        },
    )

    assert result["completed_dump_count"] == 8
    assert result["completed_dump_count_sources"] == {
        "completed_dump_count": 7,
        "target_cycle_completed_dump_count": 8,
        "dump_end_count": 8,
    }
    assert result["completed_eighth_dump"] is True
    assert result["termination_category"] == "target_eighth_dump_completed"


def test_owner_evidence_reports_valid_early_stop_before_activation() -> None:
    result = _validate_owner_control_evidence(
        [
            {
                "step_id": 844,
                "cycle_id": 2,
                "skill_name": "return",
                "return_to_dig_start_envelope_checks": {
                    "diagnostic_owner_control": {
                        "enabled": True,
                        "diagnostic_only": True,
                        "active": False,
                        "completed_dump_count": 2,
                        "min_completed_dump_count": 7,
                        "contact_owner": "token",
                        "depth_owner": "runtime_prior_p05_p95",
                    }
                },
            }
        ]
    )

    assert result["activation_boundary_exercised"] is False
    assert result["inactive_sample_count"] == 1
    assert result["active_sample_count"] == 0
    assert result["first_active_step"] is None
    assert result["max_observed_completed_dump_count"] == 2
