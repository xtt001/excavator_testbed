from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.eval.hard_bottom_recovery_probe import (
    HardBottomRecoveryProbeError,
    build_hard_bottom_recovery_probe,
)


def _row(step_id: int, **updates: object) -> dict[str, object]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[8] = 0.60
    env[89] = 0.60
    row: dict[str, object] = {
        "step_id": step_id,
        "primitive_cycle_index": 0,
        "skill_name": "dig",
        "planned_cut_cell_id": 2,
        "action": [0.0, 0.0, 0.0, 0.0],
        "box_safety_reason": "",
        "box_safety_awaiting_neutral_ack": False,
        "transition_timeout": False,
        "pre_dig_align_timeout_count": 0,
        "env_state": env.tolist(),
    }
    row.update(updates)
    return row


def _passing_probe_rows() -> list[dict[str, object]]:
    event = {
        "box_safety_event_id": "hard-bottom-1",
        "box_safety_depth_exhausted_cell_id": 2,
    }
    rows = [
        _row(
            0,
            **event,
            box_safety_reason="hard_bottom_contact",
            box_safety_hard_bottom_contact=True,
            box_safety_awaiting_neutral_ack=True,
        ),
        _row(
            1,
            **event,
            box_safety_neutral_acknowledged=True,
            box_safety_policy_restarted=True,
            box_safety_replan=True,
        ),
        _row(2, **event, box_safety_clearance_active=True),
        _row(3, **event, box_safety_clearance_completed=True),
        _row(
            4,
            **event,
            box_safety_clearance_neutral_acknowledged=True,
            box_safety_replan=True,
        ),
        _row(
            5,
            primitive_cycle_index=1,
            skill_name="dig",
            planned_cut_cell_id=4,
        ),
    ]
    for index in (2, 3, 4):
        env = np.asarray(rows[index]["env_state"], dtype=np.float32)
        env[8] = 0.57
        rows[index]["env_state"] = env.tolist()
    return rows


def test_hard_bottom_probe_writes_independent_no_overwrite_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "rollout_000.jsonl"
    source.write_text(
        "\n".join(json.dumps(row) for row in _passing_probe_rows()) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "hard_bottom_probe.json"

    record = build_hard_bottom_recovery_probe(
        rollout_jsonl_path=source,
        reset_id="probe-reset-0",
        output_path=output,
    )

    assert record["schema"] == "hard_bottom_recovery_probe_v1"
    assert record["status"] == "passed"
    assert record["hard_bottom_event_count"] == 1
    assert record["hard_bottom_events"][0]["cell_id"] == 2
    assert output.is_file()

    with pytest.raises(FileExistsError, match="already exists"):
        build_hard_bottom_recovery_probe(
            rollout_jsonl_path=source,
            reset_id="probe-reset-0",
            output_path=output,
        )


def test_hard_bottom_probe_requires_observed_recovery_event(
    tmp_path: Path,
) -> None:
    source = tmp_path / "rollout_000.jsonl"
    source.write_text(
        json.dumps(_row(0)) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        HardBottomRecoveryProbeError,
        match="hard_bottom_event_missing",
    ):
        build_hard_bottom_recovery_probe(
            rollout_jsonl_path=source,
            reset_id="probe-reset-0",
            output_path=tmp_path / "probe.json",
        )


def test_hard_bottom_probe_rejects_recontact_in_exhausted_cell(
    tmp_path: Path,
) -> None:
    rows = _passing_probe_rows()
    repeated_event = {
        "box_safety_event_id": "hard-bottom-2",
        "box_safety_depth_exhausted_cell_id": 2,
    }
    rows.extend(
        [
            _row(
                6,
                primitive_cycle_index=1,
                skill_name="return",
                **repeated_event,
                box_safety_reason="hard_bottom_contact",
                box_safety_hard_bottom_contact=True,
                box_safety_awaiting_neutral_ack=True,
            ),
            _row(
                7,
                primitive_cycle_index=1,
                skill_name="return",
                **repeated_event,
                box_safety_neutral_acknowledged=True,
                box_safety_policy_restarted=True,
                box_safety_replan=True,
            ),
            _row(
                8,
                primitive_cycle_index=1,
                skill_name="return",
                **repeated_event,
                box_safety_clearance_active=True,
            ),
            _row(
                9,
                primitive_cycle_index=1,
                skill_name="return",
                **repeated_event,
                box_safety_clearance_completed=True,
            ),
            _row(
                10,
                primitive_cycle_index=1,
                skill_name="return",
                **repeated_event,
                box_safety_clearance_neutral_acknowledged=True,
                box_safety_replan=True,
            ),
        ]
    )
    for index in (6, 7, 8, 9, 10):
        env = np.asarray(rows[index]["env_state"], dtype=np.float32)
        env[8] = 0.57
        rows[index]["env_state"] = env.tolist()
    source = tmp_path / "rollout_000.jsonl"
    source.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        HardBottomRecoveryProbeError,
        match="hard-bottom-2:exhausted_cell_recontacted:2",
    ):
        build_hard_bottom_recovery_probe(
            rollout_jsonl_path=source,
            reset_id="probe-reset-0",
            output_path=tmp_path / "probe.json",
        )
