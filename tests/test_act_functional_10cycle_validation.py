from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.act_functional_10cycle_validation import (
    ActFunctional10CycleValidationError,
    build_act_functional_10cycle_record,
    build_act_functional_10cycle_records,
    evaluate_act_functional_10cycle_records,
)


def _env(
    *,
    wall_sessions: int = 0,
    current_mass_kg: float = 900.0,
    payload_kg: float = 0.0,
) -> list[float]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX] = wall_sessions
    env[ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX] = 1000.0
    env[ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX] = current_mass_kg
    env[ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX] = 1.0
    env[ENV_STATE_MASS_IN_BUCKET_IDX] = payload_kg
    return env.tolist()


def _row(*, cycle: int, skill: str, cell_id: int) -> dict[str, object]:
    return {
        "step_id": -1,
        "primitive_cycle_index": cycle,
        "skill_name": skill,
        "planned_cut_cell_id": cell_id,
        "action": [0.0, 0.0, 0.0, 0.0],
        "box_safety_reason": "",
        "box_safety_awaiting_neutral_ack": False,
        "transition_timeout": False,
        "pre_dig_align_timeout_count": 0,
        "policy_inference_latency_ms": 125.0,
        "cycle_effective_move": False,
        "env_state": _env(
            current_mass_kg=900.0 + cycle,
            payload_kg=0.0,
        ),
    }


def _passing_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cycle in range(10):
        cell_id = cycle % 6
        for skill in ("dig", "carry", "dump", "return"):
            rows.append(_row(cycle=cycle, skill=skill, cell_id=cell_id))
    rows[-1].update(
        {
            "functional_terminal_return_ready": True,
            "functional_terminal_awaiting_neutral_ack": True,
        }
    )
    terminal_ack = _row(cycle=9, skill="return", cell_id=3)
    terminal_ack["functional_terminal_neutral_acknowledged"] = True
    rows.append(terminal_ack)
    for step_id, row in enumerate(rows):
        row["step_id"] = step_id
    return rows


def _passing_wall_safe_rows() -> list[dict[str, object]]:
    rows = _passing_rows()
    for row in rows:
        corridor_id = 2 + int(row["primitive_cycle_index"]) % 4
        row.update(
            {
                "planned_cut_cell_id": corridor_id,
                "coverage_corridor_id": corridor_id,
                "coverage_wall_safety_profile": (
                    "conservative_2d_worktool_swept_footprint_v1"
                ),
                "coverage_wall_safety_class": "near_wall",
                "coverage_wall_safety_eligible": True,
                "coverage_wall_minimum_clearance_m": 0.31,
                "coverage_wall_rejected_corridor_ids": [],
                "coverage_wall_rejected_cell_ids": [],
                "coverage_candidate_scores": [
                    {
                        "corridor_id": corridor_id,
                        "cell_id": corridor_id,
                        "selectable": 1,
                        "depleted": 0,
                        "wall_safety_eligible": 1,
                        "wall_minimum_clearance_m": 0.31,
                        "rejection_reason": "",
                    }
                ],
            }
        )
    return rows


def _wall_safe_resolved_config() -> dict[str, object]:
    return {
        "task": {
            "camera_names": [
                "stick_up",
                "stick_down",
                "eye_left",
                "eye_right",
            ]
        },
        "eval": {
            "record_hdf5_metadata": {
                "temporal_variant": "A0",
                "planner_safety_variant": "coverage_wall_safety_v1",
            }
        },
        "policy": {
            "act_params": {
                "temporal_agg_window": 100,
                "temporal_agg_weight_order": "legacy_oldest_first",
            },
            "dig_cut_planner": {
                "coverage": {
                    "wall_safety": {
                        "enabled": True,
                        "profile": (
                            "conservative_2d_worktool_swept_footprint_v1"
                        ),
                        "worktool_width_m": 0.70,
                        "hard_clearance_m": 0.30,
                        "soft_clearance_m": 0.45,
                        "max_score_penalty": 1.0,
                        "missing_geometry": "fail_closed",
                    }
                }
            },
        },
    }


def _insert_hard_bottom_event(
    rows: list[dict[str, object]],
    *,
    cycle: int = 3,
    cell_id: int = 3,
) -> None:
    insert_at = next(
        index + 1
        for index, row in enumerate(rows)
        if row["primitive_cycle_index"] == cycle and row["skill_name"] == "dig"
    )

    def event_row(**fields: object) -> dict[str, object]:
        row = _row(cycle=cycle, skill="dig", cell_id=cell_id)
        row.update(
            {
                "box_safety_event_id": "hard-bottom-3",
                "box_safety_depth_exhausted_cell_id": cell_id,
                **fields,
            }
        )
        return row

    event_rows = [
        event_row(
            box_safety_hard_bottom_contact=True,
            box_safety_reason="hard_bottom_contact",
            box_safety_awaiting_neutral_ack=True,
        ),
        event_row(
            box_safety_neutral_acknowledged=True,
            box_safety_policy_restarted=True,
            box_safety_replan=True,
        ),
        event_row(box_safety_clearance_active=True),
        event_row(box_safety_clearance_completed=True),
        event_row(
            box_safety_clearance_neutral_acknowledged=True,
            box_safety_replan=True,
        ),
    ]
    rows[insert_at:insert_at] = event_rows
    for row in rows:
        if (
            int(row["primitive_cycle_index"]) > cycle
            and row["skill_name"] == "dig"
        ):
            row["planned_cut_cell_id"] = 5
    for step_id, row in enumerate(rows):
        row["step_id"] = step_id


def test_single_reset_accepts_ten_complete_cycles_and_keeps_diagnostics_nonblocking(
) -> None:
    record = build_act_functional_10cycle_record(
        rows=_passing_rows(),
        reset_id="seed-1000",
        source_artifact_path="/runs/rollout_000.jsonl",
        source_artifact_sha256="a" * 64,
    )

    assert record["schema"] == "act_functional_10cycle_validation_v1"
    assert record["status"] == "passed"
    assert record["completed_cycle_count"] == 10
    assert record["wall_contact_count"] == 0
    assert record["stuck_count"] == 0
    assert record["timeout_count"] == 0
    assert record["terminal_return_ready_step"] == 39
    assert record["terminal_neutral_ack_step"] == 40
    assert record["diagnostics"]["remaining_mass_drop_fraction"] == pytest.approx(
        0.091
    )
    assert record["diagnostics"]["inference_p95_ms"] == pytest.approx(125.0)
    assert record["diagnostics"]["effective_move_cycle_count"] == 0


def test_effective_move_diagnostic_is_derived_from_stable_107d_windows() -> None:
    rows: list[dict[str, object]] = []
    step_id = 0
    for cycle in range(10):
        start_volume = 0.20 - cycle * 0.006
        end_volume = start_volume - 0.001
        for skill, volume, repeat in (
            ("dig", start_volume, 10),
            ("carry", end_volume, 10),
            ("dump", end_volume, 10),
            ("return", end_volume, 10),
        ):
            for _ in range(repeat):
                row = _row(cycle=cycle, skill=skill, cell_id=cycle % 6)
                row.pop("cycle_effective_move")
                env = np.asarray(row["env_state"], dtype=np.float32)
                env[75] = 1.0
                env[89] = 0.60
                env[90] = 1600.0
                env[91:97] = volume
                row["env_state"] = env.tolist()
                row["step_id"] = step_id
                step_id += 1
                rows.append(row)
    rows[-1].update(
        {
            "functional_terminal_return_ready": True,
            "functional_terminal_awaiting_neutral_ack": True,
        }
    )
    terminal_ack = dict(rows[-1])
    terminal_ack["step_id"] = step_id
    terminal_ack["functional_terminal_awaiting_neutral_ack"] = False
    terminal_ack["functional_terminal_neutral_acknowledged"] = True
    rows.append(terminal_ack)

    record = build_act_functional_10cycle_record(
        rows=rows,
        reset_id="seed-stable",
    )

    assert record["diagnostics"]["effective_move_cycle_count"] == 10
    assert record["diagnostics"]["effective_move_observed_cycle_count"] == 10
    assert all(
        cycle["effective_move"] is True
        for cycle in record["diagnostics"]["cycle_outcomes"]
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda rows: [
                row
                for row in rows
                if not (
                    row["primitive_cycle_index"] == 4
                    and row["skill_name"] == "carry"
                )
            ],
            "cycle_4:primitive_sequence_invalid",
        ),
        (
            lambda rows: [
                row
                for row in rows
                if not (
                    row["primitive_cycle_index"] == 6
                    and row["skill_name"] == "dig"
                )
            ],
            "cycle_inventory_not_0_through_9",
        ),
        (
            lambda rows: [
                {
                    key: value
                    for key, value in row.items()
                    if key != "functional_terminal_return_ready"
                }
                for row in rows
            ],
            "terminal_return_ready_missing",
        ),
        (
            lambda rows: [
                {
                    key: value
                    for key, value in row.items()
                    if key != "functional_terminal_neutral_acknowledged"
                }
                for row in rows
            ],
            "terminal_neutral_ack_missing",
        ),
        (
            lambda rows: [
                (
                    {
                        **row,
                        "env_state": _env(wall_sessions=1),
                    }
                    if index == 5
                    else row
                )
                for index, row in enumerate(rows)
            ],
            "wall_contact_present",
        ),
        (
            lambda rows: [
                (
                    {
                        **row,
                        "box_safety_reason": "stuck_joint_motion",
                        "box_safety_awaiting_neutral_ack": True,
                    }
                    if index == 5
                    else row
                )
                for index, row in enumerate(rows)
            ],
            "stuck_present",
        ),
        (
            lambda rows: [
                ({**row, "transition_timeout": True} if index == 5 else row)
                for index, row in enumerate(rows)
            ],
            "timeout_present",
        ),
        (
            lambda rows: [
                (
                    {key: value for key, value in row.items() if key != "box_safety_reason"}
                    if index == 5
                    else row
                )
                for index, row in enumerate(rows)
            ],
            "required_row_field_missing:box_safety_reason",
        ),
    ],
)
def test_single_reset_fails_closed_on_missing_or_failed_gate_evidence(
    mutation,
    reason: str,
) -> None:
    with pytest.raises(ActFunctional10CycleValidationError, match=reason):
        build_act_functional_10cycle_record(
            rows=mutation(_passing_rows()),
            reset_id="seed-1000",
        )


def test_hard_bottom_event_requires_full_ordered_recovery_proof() -> None:
    rows = _passing_rows()
    _insert_hard_bottom_event(rows)

    record = build_act_functional_10cycle_record(
        rows=rows,
        reset_id="seed-1000",
    )

    assert record["hard_bottom_event_count"] == 1
    assert record["hard_bottom_events"][0]["event_id"] == "hard-bottom-3"
    assert record["hard_bottom_events"][0]["replan_step"] > record[
        "hard_bottom_events"
    ][0]["contact_step"]

    broken = [dict(row) for row in rows]
    restart = next(
        row for row in broken if row.get("box_safety_policy_restarted")
    )
    restart.pop("box_safety_policy_restarted")
    with pytest.raises(
        ActFunctional10CycleValidationError,
        match="hard-bottom-3:policy_restart_missing",
    ):
        build_act_functional_10cycle_record(rows=broken, reset_id="seed-1000")


def test_hard_bottom_event_rejects_later_dig_in_exhausted_cell() -> None:
    rows = _passing_rows()
    _insert_hard_bottom_event(rows)
    later_dig = next(
        row
        for row in rows
        if int(row["primitive_cycle_index"]) > 3 and row["skill_name"] == "dig"
    )
    later_dig["planned_cut_cell_id"] = 3

    with pytest.raises(
        ActFunctional10CycleValidationError,
        match="hard-bottom-3:exhausted_cell_redug",
    ):
        build_act_functional_10cycle_record(rows=rows, reset_id="seed-1000")


def test_non_hard_bottom_replan_does_not_invent_a_hard_bottom_event() -> None:
    rows = _passing_rows()
    rows[8]["box_safety_replan"] = True

    record = build_act_functional_10cycle_record(
        rows=rows,
        reset_id="seed-1000",
    )

    assert record["hard_bottom_event_count"] == 0


def test_three_reset_aggregate_requires_independent_passing_records() -> None:
    records = [
        build_act_functional_10cycle_record(
            rows=_passing_rows(),
            reset_id=f"seed-{index}",
        )
        for index in range(3)
    ]

    result = evaluate_act_functional_10cycle_records(records)

    assert result["schema"] == "act_functional_10cycle_aggregate_v1"
    assert result["status"] == "passed"
    assert result["passed_reset_count"] == 3

    records[2]["reset_id"] = "seed-1"
    with pytest.raises(
        ActFunctional10CycleValidationError,
        match="independent_reset_id_invalid",
    ):
        evaluate_act_functional_10cycle_records(records)


def test_three_reset_aggregate_fails_closed_on_missing_terminal_evidence() -> None:
    records = [
        build_act_functional_10cycle_record(
            rows=_passing_rows(),
            reset_id=f"seed-{index}",
        )
        for index in range(3)
    ]
    records[1].pop("terminal_neutral_ack_step")

    with pytest.raises(
        ActFunctional10CycleValidationError,
        match="terminal_neutral_ack_invalid",
    ):
        evaluate_act_functional_10cycle_records(records)


def test_builder_writes_no_overwrite_records_and_three_reset_manifest(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    rollouts = results / "rollouts"
    rollouts.mkdir(parents=True)
    for rollout_id in range(3):
        (rollouts / f"rollout_{rollout_id:03d}.jsonl").write_text(
            "\n".join(json.dumps(row) for row in _passing_rows()) + "\n",
            encoding="utf-8",
        )

    output = tmp_path / "functional-validation"
    records = build_act_functional_10cycle_records(
        results_dir=results,
        output_dir=output,
        expected_rollout_count=3,
        seed_base=1200,
    )

    assert [record["reset_id"] for record in records] == [
        "seed-1200",
        "seed-1201",
        "seed-1202",
    ]
    manifest = json.loads(
        (output / "validation_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "act_functional_10cycle_validation_manifest_v1"
    assert manifest["aggregate"]["status"] == "passed"
    assert len(manifest["records"]) == 3
    assert all(
        len(record["source_artifact_sha256"]) == 64 for record in records
    )

    with pytest.raises(FileExistsError):
        build_act_functional_10cycle_records(
            results_dir=results,
            output_dir=output,
            expected_rollout_count=3,
        )


def test_builder_does_not_create_output_when_inventory_is_incomplete(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    rollouts = results / "rollouts"
    rollouts.mkdir(parents=True)
    (rollouts / "rollout_000.jsonl").write_text(
        "\n".join(json.dumps(row) for row in _passing_rows()) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "functional-validation"

    with pytest.raises(
        ActFunctional10CycleValidationError,
        match="rollout_inventory_mismatch",
    ):
        build_act_functional_10cycle_records(
            results_dir=results,
            output_dir=output,
            expected_rollout_count=3,
        )

    assert not output.exists()


def test_builder_auto_applies_wall_safe_a0_contract_from_resolved_config(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    rollouts = results / "rollouts"
    rollouts.mkdir(parents=True)
    (rollouts / "rollout_000.jsonl").write_text(
        "\n".join(json.dumps(row) for row in _passing_wall_safe_rows()) + "\n",
        encoding="utf-8",
    )
    (results / "eval_resolved_config.yaml").write_text(
        yaml.safe_dump(_wall_safe_resolved_config(), sort_keys=False),
        encoding="utf-8",
    )

    records = build_act_functional_10cycle_records(
        results_dir=results,
        output_dir=tmp_path / "validation",
        expected_rollout_count=1,
    )

    evidence = records[0]["coverage_wall_safety"]
    assert evidence["status"] == "passed"
    assert evidence["minimum_selected_clearance_m"] == pytest.approx(0.31)
    assert records[0]["gate"]["minimum_wall_clearance_m"] == pytest.approx(
        0.30
    )
